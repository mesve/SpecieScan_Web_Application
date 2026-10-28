#!/usr/bin/env python3
"""
SpecieScan Web Application
A web-based interface for ZooMS (Zooarchaeology Mass Spectrometry) analysis
Integrates R pre-processing and Python species identification workflows
"""

import os
import csv
import io
import json
import re
import shutil
import stat
import tempfile
import uuid
import zipfile
from pathlib import Path
from flask import (
    Flask, render_template, request, jsonify, send_file, send_from_directory,
    has_request_context, Response
)
from werkzeug.utils import secure_filename
import threading
import time
import sys

import numpy as np

# Add our modules to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import our analysis modules
R_INTEGRATION_AVAILABLE = False
R_INTEGRATION_ERROR = None

try:
    from R_integration.r_interface import get_r_integration
    from python_analysis.species_identification import get_python_analysis

    # Test R integration on startup
    print("=" * 60)
    print("TESTING R INTEGRATION ON STARTUP")
    print("=" * 60)

    try:
        test_r = get_r_integration()
        if test_r.maldiquant and test_r.maldiquant_foreign:
            R_INTEGRATION_AVAILABLE = True
            print("✓ R integration test: SUCCESS")
            print("  - MALDIquant: Available")
            print("  - MALDIquantForeign: Available")
        else:
            R_INTEGRATION_ERROR = "R packages not properly loaded"
            print(f"✗ R integration test: FAILED - {R_INTEGRATION_ERROR}")
    except Exception as e:
        R_INTEGRATION_ERROR = str(e)
        print(f"✗ R integration test: FAILED - {e}")
        import traceback
        traceback.print_exc()

    print("=" * 60)

except ImportError as e:
    R_INTEGRATION_ERROR = str(e)
    print(f"Warning: Could not import analysis modules: {e}")
    print("=" * 60)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['SECRET_KEY'] = 'specie_scan_secret_key_2024'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Step 0 (optional Bruker -> mzML conversion) working area
STEP0_WORK_DIR = os.path.join(BASE_DIR, 'step0_work')
STEP0_MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
STEP0_MAX_ENTRIES = 20000
STEP0_BRUKER_MARKERS = {'acqu', 'acqus', 'fid', 'fid.ser'}

# Reference data file names
REFERENCE_DB_DIR = os.path.join(BASE_DIR, 'reference_databases')
REFERENCE_DATABASES = {
    'eurasia_mammals': {
        'label': 'Eurasia Mammals',
        'filename': 'Mammals_reference_Eurasia.csv',
    },
    'african_mammals': {
        'label': 'African Mammals',
        'filename': 'Mammals_reference_Africa.csv',
    },
    'new_world_mammals': {
        'label': 'New World Mammals',
        'filename': 'Mammals_reference_new_world.csv',
    },
    'birds': {
        'label': 'Birds',
        'filename': 'Bird_reference_db.csv',
    },
    'fish': {
        'label': 'Fish',
        'filename': 'Fish_reference_db_1.csv',
    },
    'amphibians': {
        'label': 'Amphibians',
        'filename': 'Amphibians_reference_db.csv',
    },
    'reptiles': {
        'label': 'Reptiles',
        'filename': 'Reptiles_reference_db.csv',
    },
}
DEFAULT_REFERENCE_DB_KEY = 'eurasia_mammals'
REFERENCE_DB_LABEL_YEAR = '2024'
REFERENCE_METADATA_COLUMNS = ('Order', 'Family', 'Species', 'ZooMS_taxon')
REFERENCE_MAX_BYTES = 20 * 1024 * 1024
REFERENCE_MAX_ROWS = 10000
REFERENCE_MAX_MARKER_COLUMNS = 1000

# Custom reference databases are stored outside static/ and removed on reset.
STEP9_WORK_DIR = os.path.join(BASE_DIR, 'step9_work')
STEP9_REFERENCE_DIR = os.path.join(STEP9_WORK_DIR, 'reference')

CONTAMINANTS_FILENAME = 'contaminants_list_2024.csv'

# Mass window used for ZooMS marker matching (Da)
ZOO_MS_MASS_MIN = 800.0
ZOO_MS_MASS_MAX = 3500.0
MATCH_TOLERANCE = 1.0  # Da
CONTAMINANT_TOLERANCE = 0.5  # Da


def find_data_file(filename):
    """Locate a reference data file next to the app or in parent folders"""
    candidates = [
        BASE_DIR,
        os.path.dirname(BASE_DIR),
        os.path.dirname(os.path.dirname(BASE_DIR)),
    ]
    for directory in candidates:
        candidate = os.path.join(directory, filename)
        if os.path.exists(candidate):
            return candidate
    return None


# Global storage for serialisable processing state (no heavy arrays!)
processing_state = {
    'current_step': 0,
    'uploaded_files': [],
    'session_id': str(uuid.uuid4()),
    'processing_data': {},
    'status': 'ready',
    'spectrum_count': 0,
}

# Heavy non-serialisable data (R objects and numpy arrays) kept separately so
# that /api/state never tries to JSON-encode them.
data_store = {
    'spectra': None,            # R list of MassSpectrum
    'spectra_arrays': None,     # list of (np.mass, np.intensity)
    'processed_spectra': None,  # R list of MassSpectrum
    'processed_arrays': None,
    'peaks': None,              # R list of MassPeaks (monoisotopic)
    'peaks_arrays': None,
    'averaged_spectra': None,
    'averaged_arrays': None,
    'noise_cache': {},          # index -> {'noise_mass','noise_intensity'}
    'reference_db': None,       # selected/custom reference database metadata
}

# Keys excluded from /api/state responses
HEAVY_STATE_KEYS = {
    'spectra', 'processed_spectra', 'peaks', 'averaged_spectra'
}

# Allowed file extensions
ALLOWED_EXTENSIONS = {'mzML', 'mzml'}


def _step9_cleanup():
    """Remove custom Step 9 reference databases (built-in files are untouched)."""
    data_store['reference_db'] = None
    shutil.rmtree(STEP9_WORK_DIR, ignore_errors=True)

# Step 0 state: optional conversion of Bruker Flex data to .mzML
step0_state = {
    'status': 'idle',        # idle | uploaded | converted
    'work_dir': None,
    'upload_name': None,
    'extract_dir': None,
    'output_dir': None,
    'source_file_count': 0,
    'files': [],
    'message': '',
}
_step0_lock = threading.Lock()


def allowed_file(filename):
    """Check if file has allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _step0_summary():
    """Serialisable summary of the optional Step 0 state"""
    return {
        'status': step0_state['status'],
        'upload_name': step0_state['upload_name'],
        'source_file_count': step0_state['source_file_count'],
        'files': step0_state['files'],
        'message': step0_state['message'],
        'available': R_INTEGRATION_AVAILABLE,
    }


def _step0_reset(remove_work_dir=True):
    """Forget Step 0 files and (optionally) delete its working directory"""
    work_dir = step0_state.get('work_dir')
    if remove_work_dir and work_dir and os.path.isdir(work_dir):
        shutil.rmtree(work_dir, ignore_errors=True)
    step0_state.update({
        'status': 'idle',
        'work_dir': None,
        'upload_name': None,
        'extract_dir': None,
        'output_dir': None,
        'source_file_count': 0,
        'files': [],
        'message': '',
    })


def _step0_cleanup_all():
    """Remove every Step 0 working directory (startup/reset)"""
    _step0_reset()
    if os.path.isdir(STEP0_WORK_DIR):
        shutil.rmtree(STEP0_WORK_DIR, ignore_errors=True)
    os.makedirs(STEP0_WORK_DIR, exist_ok=True)


def _safe_extract_zip(zip_path, dest_dir):
    """
    Extract a ZIP archive, rejecting unsafe paths and excessive sizes.

    Returns (file_count, bruker_file_count).
    """
    os.makedirs(dest_dir, exist_ok=True)
    dest_real = os.path.realpath(dest_dir)
    total_uncompressed = 0
    file_count = 0
    bruker_count = 0

    with zipfile.ZipFile(zip_path) as archive:
        members = archive.infolist()
        if len(members) > STEP0_MAX_ENTRIES:
            raise ValueError(
                f'The ZIP contains too many entries ({len(members)}). '
                f'The limit is {STEP0_MAX_ENTRIES}.'
            )

        checked = []
        for member in members:
            name = member.filename
            if not name or name.endswith('/'):
                continue
            # Reject absolute paths, drive letters and traversal
            normalized = name.replace('\\', '/')
            if normalized.startswith('/') or os.path.isabs(normalized) or ':' in normalized.split('/')[0]:
                raise ValueError(f'Unsafe path in ZIP archive: {name}')
            target = os.path.realpath(os.path.join(dest_dir, normalized))
            if target != dest_real and not target.startswith(dest_real + os.sep):
                raise ValueError(f'Unsafe path in ZIP archive: {name}')
            # Reject symlinks
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f'ZIP archive contains a symbolic link: {name}')
            total_uncompressed += member.file_size
            if total_uncompressed > STEP0_MAX_UNCOMPRESSED_BYTES:
                raise ValueError(
                    'The ZIP expands to more than 2 GB. Please split the '
                    'Bruker folder into smaller archives.'
                )
            checked.append(member)

        for member in checked:
            normalized = member.filename.replace('\\', '/')
            parts = [p for p in normalized.split('/') if p]
            # Ignore macOS metadata
            if parts and (parts[0] == '__MACOSX' or parts[-1].startswith('._')):
                continue
            # Normalise path separators before extraction
            member.filename = '/'.join(parts)
            archive.extract(member, dest_dir)
            file_count += 1
            if parts and parts[-1].lower() in STEP0_BRUKER_MARKERS:
                bruker_count += 1

    return file_count, bruker_count


def _step0_source_files(extract_dir):
    """Return every extracted file (excluding macOS metadata)"""
    results = []
    for root, dirs, files in os.walk(extract_dir):
        dirs[:] = [d for d in dirs if d != '__MACOSX']
        for name in files:
            if name.startswith('._'):
                continue
            results.append(os.path.join(root, name))
    return results


def clear_derived_data():
    """Clear everything that depends on the currently uploaded files"""
    for key in data_store:
        if key == 'noise_cache':
            data_store[key] = {}
        else:
            data_store[key] = None
    processing_state['spectrum_count'] = 0
    processing_state['processing_data'] = {}
    processing_state['status'] = 'ready'


@app.route('/')
def index():
    """Main application interface"""
    step_titles = {
        0: "Convert File (Optional)",
        1: "Data Upload",
        2: "Visualise Spectra",
        3: "Quality Control",
        4: "Pre-process",
        5: "Determine SNR",
        6: "Peak Picking",
        7: "Peak Distribution",
        8: "Average Replicates",
        9: "Export & Analysis"
    }
    return render_template(
        'workflow.html',
        state=processing_state,
        step_titles=step_titles,
        reference_databases=REFERENCE_DATABASES,
        default_reference_db=DEFAULT_REFERENCE_DB_KEY
    )


@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle file upload"""
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400

        files = request.files.getlist('files')
        uploaded_files = []

        for file in files:
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                uploaded_files.append({
                    'name': filename,
                    'path': filepath,
                    'size': os.path.getsize(filepath)
                })

        # A new upload invalidates any previously processed data
        clear_derived_data()
        processing_state['uploaded_files'] = uploaded_files
        processing_state['status'] = 'files_uploaded'

        return jsonify({
            'success': True,
            'files': uploaded_files,
            'count': len(uploaded_files)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/step0/upload', methods=['POST'])
def step0_upload():
    """Upload a ZIP containing a Bruker Flex data folder and extract it"""
    if not R_INTEGRATION_AVAILABLE:
        return jsonify({
            'error': 'R integration is not available. Bruker conversion requires '
                     'R with MALDIquant and MALDIquantForeign.'
        }), 503

    upload = request.files.get('file')
    if upload is None:
        files = request.files.getlist('files')
        upload = files[0] if files else None
    if upload is None or not upload.filename:
        return jsonify({'error': 'No file provided. Please choose a .zip archive.'}), 400
    if not upload.filename.lower().endswith('.zip'):
        return jsonify({
            'error': 'Please upload a .zip archive of your Bruker Flex data folder.'
        }), 400

    with _step0_lock:
        _step0_reset()
        os.makedirs(STEP0_WORK_DIR, exist_ok=True)
        work_dir = tempfile.mkdtemp(prefix='bruker_', dir=STEP0_WORK_DIR)
        zip_path = os.path.join(work_dir, 'bruker_upload.zip')
        extract_dir = os.path.join(work_dir, 'bruker')
        try:
            upload.save(zip_path)
            if not zipfile.is_zipfile(zip_path):
                raise ValueError('The uploaded file is not a valid ZIP archive.')

            file_count, bruker_count = _safe_extract_zip(zip_path, extract_dir)
            if bruker_count == 0:
                raise ValueError(
                    'No Bruker Flex files were found in the ZIP. The archive '
                    'should contain the MALDI folder with files such as '
                    '"acqu", "acqus" and "fid".'
                )

            step0_state.update({
                'status': 'uploaded',
                'work_dir': work_dir,
                'upload_name': secure_filename(upload.filename),
                'extract_dir': extract_dir,
                'output_dir': os.path.join(work_dir, 'mzml'),
                'source_file_count': file_count,
                'files': [],
                'message': f'Bruker data extracted ({file_count} files).',
            })
        except Exception as e:
            _step0_reset()
            return jsonify({'error': str(e)}), 400
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)

        return jsonify({
            'success': True,
            'step0': _step0_summary(),
            'file_count': file_count,
            'bruker_file_count': bruker_count,
        })


@app.route('/api/step0/convert', methods=['POST'])
def step0_convert():
    """Convert the uploaded Bruker Flex spectra to .mzML using R"""
    if not R_INTEGRATION_AVAILABLE:
        return jsonify({
            'error': 'R integration is not available. Bruker conversion requires '
                     'R with MALDIquant and MALDIquantForeign.'
        }), 503
    if step0_state['status'] not in ('uploaded', 'converted') or not step0_state['extract_dir']:
        return jsonify({'error': 'Please upload a Bruker ZIP archive first.'}), 400

    with _step0_lock:
        output_dir = step0_state['output_dir']
        try:
            if os.path.isdir(output_dir):
                shutil.rmtree(output_dir)
            os.makedirs(output_dir, exist_ok=True)

            r = get_r_integration()
            spectrum_count = r.convert_bruker_flex(
                step0_state['extract_dir'], output_dir
            )

            converted = []
            for name in sorted(os.listdir(output_dir)):
                if not name.lower().endswith('.mzml'):
                    continue
                path = os.path.join(output_dir, name)
                converted.append({
                    'name': name,
                    'size': os.path.getsize(path),
                })

            if not converted:
                raise ValueError(
                    'R did not create any .mzML files. Please check that the ZIP '
                    'contains valid Bruker Flex spectra.'
                )

            step0_state.update({
                'status': 'converted',
                'files': converted,
                'message': f'{len(converted)} .mzML file(s) created from '
                           f'{spectrum_count} spectrum/spectra.',
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

        return jsonify({
            'success': True,
            'step0': _step0_summary(),
            'spectrum_count': spectrum_count,
        })


@app.route('/api/step0/download')
def step0_download_all():
    """Download every converted .mzML file as one ZIP archive"""
    files = step0_state.get('files') or []
    output_dir = step0_state.get('output_dir')
    if not files or not output_dir:
        return jsonify({'error': 'No converted .mzML files are available yet.'}), 404

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for item in files:
            path = os.path.join(output_dir, item['name'])
            if os.path.isfile(path):
                archive.write(path, item['name'])
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='SpecieScan_converted_mzML.zip'
    )


@app.route('/api/step0/file/<int:index>')
def step0_download_file(index):
    """Download a single converted .mzML file"""
    files = step0_state.get('files') or []
    output_dir = step0_state.get('output_dir')
    if not files or not output_dir:
        return jsonify({'error': 'No converted .mzML files are available yet.'}), 404
    if index < 0 or index >= len(files):
        return jsonify({'error': 'Invalid file index.'}), 404

    return send_file(
        os.path.join(output_dir, files[index]['name']),
        mimetype='application/octet-stream',
        as_attachment=True,
        download_name=files[index]['name']
    )


@app.route('/api/step0/clear', methods=['POST'])
def step0_clear():
    """Discard uploaded Bruker data and converted files"""
    with _step0_lock:
        _step0_reset()
    return jsonify({'success': True, 'step0': _step0_summary()})


@app.route('/api/step/<int:step>', methods=['GET', 'POST'])
def workflow_step(step):
    """Handle workflow step operations"""
    try:
        if request.method == 'GET':
            return jsonify(get_step_status(step))
        else:
            return jsonify(process_step(step))

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def get_step_status(step):
    """Get current status of a workflow step"""
    return {
        'step': step,
        'status': processing_state['processing_data'].get(f'step_{step}_status', 'pending'),
        'data': processing_state['processing_data'].get(f'step_{step}_data', {}),
        'current_step': processing_state['current_step']
    }


def process_step(step):
    """Process a workflow step"""
    print(f"Processing step {step}")
    processing_state['current_step'] = step

    try:
        if step == 1:
            return process_step_1()
        elif step == 2:
            return process_step_2()
        elif step == 3:
            return process_step_3()
        elif step == 4:
            return process_step_4()
        elif step == 5:
            return process_step_5()
        elif step == 6:
            return process_step_6()
        elif step == 7:
            return process_step_7()
        elif step == 8:
            return process_step_8()
        elif step == 9:
            return process_step_9()
        else:
            raise ValueError(f"Invalid step: {step}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        step_data = {
            'status': 'error',
            'message': f'Step {step} failed: {str(e)}'
        }
        processing_state['processing_data'][f'step_{step}_status'] = 'error'
        processing_state['processing_data'][f'step_{step}_data'] = step_data
        return step_data


def _save_step(step, step_data):
    processing_state['processing_data'][f'step_{step}_status'] = step_data['status']
    processing_state['processing_data'][f'step_{step}_data'] = step_data
    return step_data


def process_step_1():
    """Step 1: File upload (already handled separately)"""
    return _save_step(1, {
        'status': 'completed',
        'message': 'Files uploaded successfully',
        'file_count': len(processing_state['uploaded_files'])
    })


def process_step_2():
    """Step 2: Load spectra from R for visualisation"""
    if not processing_state['uploaded_files']:
        raise Exception('No files uploaded')

    if not R_INTEGRATION_AVAILABLE:
        raise Exception(
            f'R integration not available: {R_INTEGRATION_ERROR}. '
            f'Real spectra cannot be loaded.'
        )

    r_integration = get_r_integration()
    file_paths = [f['path'] for f in processing_state['uploaded_files']]

    print(f"Loading {len(file_paths)} spectra from R...")
    spectra = r_integration.load_mzml_files(file_paths)
    arrays = r_integration.spectra_arrays(spectra)

    if not arrays:
        raise Exception("R returned no spectra")

    data_store['spectra'] = spectra
    data_store['spectra_arrays'] = arrays
    data_store['noise_cache'] = {}
    processing_state['spectrum_count'] = len(arrays)

    first_mass, first_intensity = arrays[0]
    print(f"✓ Loaded {len(arrays)} spectra from R "
          f"({first_mass.size} points, m/z {first_mass.min():.1f}-{first_mass.max():.1f})")

    return _save_step(2, {
        'status': 'completed',
        'message': f'Loaded {len(arrays)} spectra from R',
        'spectrum_count': len(arrays),
        'source': 'R',
        'data_type': 'real',
        'points': int(first_mass.size),
        'mass_range': [float(first_mass.min()), float(first_mass.max())]
    })


def process_step_3():
    """Step 3: Quality control"""
    spectra = data_store.get('spectra')
    if spectra is None:
        raise Exception('Spectra not loaded. Complete Step 2 first.')

    r_integration = get_r_integration()
    qc_results = r_integration.quality_control(spectra)
    return _save_step(3, {
        'status': 'completed',
        'message': 'Quality control completed',
        'results': qc_results
    })


def process_step_4():
    """Step 4: Pre-processing"""
    spectra = data_store.get('spectra')
    if spectra is None:
        raise Exception('Spectra not loaded. Complete Step 2 first.')

    r_integration = get_r_integration()
    processed = r_integration.preprocess_spectra(spectra)
    data_store['processed_spectra'] = processed
    data_store['processed_arrays'] = r_integration.spectra_arrays(processed)
    data_store['noise_cache'] = {}

    # Pre-processing invalidates anything derived from the raw spectra
    data_store['peaks'] = None
    data_store['peaks_arrays'] = None
    data_store['averaged_spectra'] = None
    data_store['averaged_arrays'] = None

    return _save_step(4, {
        'status': 'completed',
        'message': 'Pre-processing completed',
        'methods': ['Savitzky-Golay smoothing', 'SNIP baseline removal', 'TIC calibration'],
        'spectrum_count': len(data_store['processed_arrays'])
    })


def process_step_5():
    """Step 5: Signal-to-noise ratio analysis"""
    arrays = data_store.get('processed_arrays') or data_store.get('spectra_arrays')
    if not arrays:
        raise Exception('Spectra not loaded. Complete Step 2 first.')

    # Noise is estimated lazily per spectrum via /api/noise/<index>. Here we
    # simply validate the data and report how many spectra are available.
    return _save_step(5, {
        'status': 'completed',
        'message': f'Noise estimation ready for {len(arrays)} spectra',
        'spectrum_count': len(arrays)
    })


def process_step_6():
    """Step 6: Peak picking"""
    spectra = data_store.get('processed_spectra')
    if spectra is None:
        raise Exception('Pre-processed spectra not available. Complete Step 4 first.')

    params = request.get_json(silent=True) or {}
    snr = float(params.get('snr', 3.5))
    half_window_size = int(params.get('half_window_size', 20))
    min_cor = float(params.get('min_cor', 0.95))
    tolerance = float(params.get('tolerance', 1e-4))
    distance = float(params.get('distance', 1.00235))
    size_range = str(params.get('size_range', '2:10'))

    r_integration = get_r_integration()
    peaks = r_integration.detect_peaks(spectra, snr=snr, half_window_size=half_window_size)
    monoisotopic = r_integration.monoisotopic_peaks(
        peaks, min_cor=min_cor, tolerance=tolerance,
        distance=distance, size_range=size_range
    )

    data_store['peaks'] = monoisotopic
    data_store['peaks_arrays'] = r_integration.spectra_arrays(monoisotopic)
    peak_counts = r_integration.get_peak_counts(monoisotopic)

    print(f"✓ Detected peaks: {peak_counts}")

    return _save_step(6, {
        'status': 'completed',
        'message': 'Peak picking completed',
        'peak_count': peak_counts,
        'params': {
            'snr': snr,
            'half_window_size': half_window_size,
            'min_cor': min_cor,
            'tolerance': tolerance,
            'distance': distance,
            'size_range': size_range
        }
    })


def process_step_7():
    """Step 7: Peak distribution analysis"""
    peaks_arrays = data_store.get('peaks_arrays')
    if peaks_arrays is None:
        raise Exception('No peaks available. Complete Step 6 first.')

    peak_counts = [int(len(mass)) for mass, _ in peaks_arrays]
    bins = []
    if peak_counts:
        start = int(min(peak_counts))
        end = int(max(peak_counts))
        bins = list(range(start, end + 5, 5))

    return _save_step(7, {
        'status': 'completed',
        'message': 'Peak distribution analysis completed',
        'peak_counts': peak_counts,
        'histogram_data': {'counts': peak_counts, 'bins': bins}
    })


def extract_sample_labels():
    """Extract sample labels from filenames based on prefix before '_'
    Files with same prefix are technical replicates
    e.g., DC16000_A1.mzML, DC16000_C1.mzML, DC16000_D1.mzML all get label 'DC16000'"""
    labels = []
    sample_groups = {}

    for file_info in processing_state['uploaded_files']:
        filename = file_info['name']
        name_without_ext = filename.replace('.mzML', '').replace('.mzml', '')
        if '_' in name_without_ext:
            sample_prefix = name_without_ext.split('_')[0]
        else:
            sample_prefix = name_without_ext

        labels.append(sample_prefix)

        if sample_prefix not in sample_groups:
            sample_groups[sample_prefix] = []
        sample_groups[sample_prefix].append(filename)

    return labels, sample_groups


def process_step_8():
    """Step 8: Average technical replicates by sample name"""
    spectra = data_store.get('processed_spectra')
    if spectra is None:
        raise Exception('Pre-processed spectra not available. Complete Step 4 first.')

    r_integration = get_r_integration()
    labels, sample_groups = extract_sample_labels()

    unique_samples = list(dict.fromkeys(labels))
    print(f"Averaging {len(labels)} spectra into {len(unique_samples)} samples")

    averaged = r_integration.average_spectra(spectra, labels)
    data_store['averaged_spectra'] = averaged
    data_store['averaged_arrays'] = r_integration.spectra_arrays(averaged)

    groups_info = [f"{sample}: {len(files)} replicates" for sample, files in sample_groups.items()]

    return _save_step(8, {
        'status': 'completed',
        'message': f'Technical replicates averaged: {len(unique_samples)} samples from {len(labels)} spectra',
        'averaged_count': len(unique_samples),
        'original_count': len(labels),
        'sample_groups': sample_groups,
        'groups_summary': groups_info
    })


# ----------------------------------------------------------------------
# Species identification (Step 9)
# ----------------------------------------------------------------------
def _find_nearest(sample_masses, target, tolerance):
    """Return True if any sample mass is within tolerance of target"""
    if sample_masses.size == 0:
        return False
    idx = int(np.argmin(np.abs(sample_masses - target)))
    return abs(sample_masses[idx] - target) <= tolerance


_MARKER_SPLIT_PATTERN = re.compile(r'[/•;,\s]+')


def parse_marker_masses(value):
    """Parse one marker cell into a list of alternative masses.

    Most reference cells contain one mass. The Fish database (and some custom
    databases) can contain alternatives such as "1600/ 1588" or "2450/2541".
    """
    if value is None:
        return []

    if isinstance(value, (int, float, np.integer, np.floating)):
        mass = float(value)
        if not np.isfinite(mass) or mass <= 0:
            return []
        return [mass]

    text = str(value).strip()
    if not text:
        return []

    masses = []
    for token in _MARKER_SPLIT_PATTERN.split(text):
        token = token.strip()
        if not token:
            continue
        try:
            mass = float(token)
        except (TypeError, ValueError):
            raise ValueError(f'marker value {value!r} is not numeric')
        if not np.isfinite(mass) or mass <= 0:
            raise ValueError(f'marker value {value!r} is not a positive mass')
        masses.append(mass)
    return masses


def validate_reference_dataframe(df):
    """Return a cleaned reference DataFrame or raise a user-facing error."""
    if df is None or df.empty:
        raise ValueError('The reference database is empty.')

    if len(df) > REFERENCE_MAX_ROWS:
        raise ValueError(
            f'The reference database has too many rows (max {REFERENCE_MAX_ROWS}).'
        )

    # Excel exports often add an unnamed index column before the real header.
    if len(df.columns) > 0 and str(df.columns[0]).startswith('Unnamed:'):
        df = df.drop(columns=df.columns[0])

    df = df.rename(columns={c: str(c).strip() for c in df.columns})

    lower_to_column = {}
    for column in df.columns:
        lower_to_column.setdefault(column.lower(), column)

    missing = [
        column for column in REFERENCE_METADATA_COLUMNS
        if column.lower() not in lower_to_column
    ]
    if missing:
        raise ValueError(
            'The reference database is missing required column(s): '
            + ', '.join(missing) + '. Expected Order, Family, Species, ZooMS_taxon.'
        )

    metadata_columns = [lower_to_column[c.lower()] for c in REFERENCE_METADATA_COLUMNS]
    marker_columns = [c for c in df.columns if c not in metadata_columns]

    if not marker_columns:
        raise ValueError('The reference database does not contain marker mass columns.')
    if len(marker_columns) > REFERENCE_MAX_MARKER_COLUMNS:
        raise ValueError(
            f'The reference database has too many marker columns '
            f'(max {REFERENCE_MAX_MARKER_COLUMNS}).'
        )

    df = df[metadata_columns + marker_columns].copy()
    df.columns = list(REFERENCE_METADATA_COLUMNS) + marker_columns

    # Keep only rows that actually describe a species.
    df['Species'] = df['Species'].astype(str).str.strip()
    df = df[(df['Species'] != '') & (df['Species'].str.lower() != 'nan')]
    if df.empty:
        raise ValueError('The reference database does not contain any species rows.')

    usable_marker_columns = []
    for column in marker_columns:
        has_mass = False
        for value in df[column]:
            try:
                masses = parse_marker_masses(value)
            except ValueError as exc:
                raise ValueError(f"Column '{column}': {exc}") from exc
            if masses:
                has_mass = True
        if has_mass:
            usable_marker_columns.append(column)
        else:
            df = df.drop(columns=[column])

    if not usable_marker_columns:
        raise ValueError('The reference database does not contain any valid marker masses.')

    return df[list(REFERENCE_METADATA_COLUMNS) + usable_marker_columns]


def load_reference_dataframe(path):
    """Read and validate a reference CSV."""
    import pandas as pd

    try:
        df = pd.read_csv(path, encoding='utf-8-sig')
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(path, encoding='latin-1')
        except Exception as exc:
            raise ValueError(f'Could not read the reference database: {exc}') from exc
    except Exception as exc:
        raise ValueError(f'Could not read the reference database: {exc}') from exc

    return validate_reference_dataframe(df)


def get_builtin_reference_database(key):
    """Resolve one of the bundled databases to (path, display label)."""
    entry = REFERENCE_DATABASES.get(key)
    if not entry:
        raise ValueError('Unknown default reference database selection.')

    path = os.path.join(REFERENCE_DB_DIR, entry['filename'])
    if not os.path.exists(path):
        fallback = find_data_file(entry['filename'])
        if fallback:
            path = fallback
    if not os.path.exists(path):
        raise ValueError(
            f'Default reference database "{entry["filename"]}" is missing from '
            f'the reference_databases folder.'
        )

    return path, f"{entry['label']} (SpecieScan {REFERENCE_DB_LABEL_YEAR})"


def save_custom_reference_database(upload):
    """Persist and validate an uploaded reference CSV.

    Returns (path, original filename). Files live outside static/ and are
    removed on reset.
    """
    if not upload or not upload.filename:
        raise ValueError('Choose a reference database CSV file, or use a default database.')

    original_name = secure_filename(upload.filename) or 'reference_database.csv'
    if not original_name.lower().endswith('.csv'):
        raise ValueError('The reference database must be a .csv file.')

    content = upload.read(REFERENCE_MAX_BYTES + 1)
    if len(content) > REFERENCE_MAX_BYTES:
        raise ValueError(
            f'The reference database is too large (max {REFERENCE_MAX_BYTES // (1024 * 1024)} MB).'
        )
    if not content.strip():
        raise ValueError('The reference database file is empty.')

    os.makedirs(STEP9_REFERENCE_DIR, exist_ok=True)
    target_path = os.path.join(
        STEP9_REFERENCE_DIR, f'{uuid.uuid4().hex}_{original_name}'
    )

    try:
        with open(target_path, 'wb') as handle:
            handle.write(content)
        load_reference_dataframe(target_path)
    except Exception:
        try:
            os.remove(target_path)
        except OSError:
            pass
        raise

    # Keep only the most recently uploaded custom database.
    for name in os.listdir(STEP9_REFERENCE_DIR):
        existing = os.path.join(STEP9_REFERENCE_DIR, name)
        if existing != target_path and os.path.isfile(existing):
            try:
                os.remove(existing)
            except OSError:
                pass

    return target_path, original_name


def resolve_reference_database():
    """Resolve the database chosen in Step 9.

    Returns (path, display label, source). Falls back to the default database
    when the endpoint is called without form data.
    """
    mode = 'default'
    key = DEFAULT_REFERENCE_DB_KEY
    upload = None

    if has_request_context():
        mode = (request.form.get('reference_mode') or 'default').strip().lower()
        key = (request.form.get('reference_db_key') or DEFAULT_REFERENCE_DB_KEY).strip()
        upload = request.files.get('reference_db')

    if mode == 'custom':
        if upload and upload.filename:
            path, label = save_custom_reference_database(upload)
            data_store['reference_db'] = {
                'path': path, 'label': label, 'source': 'custom'
            }
            return path, label, 'custom'

        existing = data_store.get('reference_db')
        if (
            existing
            and existing.get('source') == 'custom'
            and os.path.exists(existing.get('path', ''))
        ):
            return existing['path'], existing['label'], 'custom'

        raise ValueError(
            'Choose a reference database CSV file, or switch to a default database.'
        )

    path, label = get_builtin_reference_database(key)
    data_store['reference_db'] = {
        'path': path, 'label': label, 'source': 'specie_scan_2024'
    }
    return path, label, 'specie_scan_2024'


def rank_species_matches(sample_masses, reference_df, mass_columns,
                         tolerance=MATCH_TOLERANCE, top_n=6):
    """Rank reference species by the fraction of reference markers matched.

    A marker cell may contain several alternative masses; the marker counts as
    matched when any alternative is within tolerance.
    """
    if sample_masses.size == 0:
        return []

    results = []
    for _, row in reference_df.iterrows():
        marker_sets = []
        for column in mass_columns:
            alternatives = parse_marker_masses(row[column])
            if alternatives:
                marker_sets.append(alternatives)

        if not marker_sets:
            continue

        matched = sum(
            1 for alternatives in marker_sets
            if any(_find_nearest(sample_masses, mass, tolerance) for mass in alternatives)
        )
        score = matched / float(len(marker_sets))

        results.append({
            'ZooMS_taxon': str(row.get('ZooMS_taxon', '')),
            'species': str(row.get('Species', '')),
            'common_name': '',
            'family': str(row.get('Family', '')),
            'order': str(row.get('Order', '')),
            'reference_peaks': [
                float(mass) for alternatives in marker_sets for mass in alternatives
            ],
            'correlation': round(float(score), 3),
            'matched_peaks': int(matched),
            'total_reference_peaks': int(len(marker_sets))
        })

    results.sort(key=lambda r: (-r['correlation'], -r['matched_peaks'], r['species']))
    for rank, match in enumerate(results[:top_n], start=1):
        match['rank'] = rank
    return results[:top_n]


def find_contaminants(sample_masses, tolerance=CONTAMINANT_TOLERANCE):
    """Match sample peaks against the contaminants list"""
    contam_path = find_data_file(CONTAMINANTS_FILENAME)
    if not contam_path:
        return []

    import pandas as pd
    df = pd.read_csv(contam_path)
    if 'mass' not in df.columns or 'contaminant' not in df.columns:
        return []

    hits = {}
    for _, row in df.iterrows():
        try:
            mass = float(row['mass'])
        except (TypeError, ValueError):
            continue
        if _find_nearest(sample_masses, mass, tolerance):
            hits.setdefault(str(row['contaminant']), []).append(round(mass, 4))

    return [
        {'contaminant': name, 'masses': masses, 'count': len(masses)}
        for name, masses in sorted(hits.items(), key=lambda kv: -len(kv[1]))
    ]


def process_step_9():
    """Step 9: Export and species identification for all samples"""
    peaks_arrays = data_store.get('peaks_arrays')
    if peaks_arrays is None:
        raise Exception('No peaks available. Complete Step 6 (Peak Picking) first.')

    reference_path, reference_label, reference_source = resolve_reference_database()
    reference_df = load_reference_dataframe(reference_path)
    mass_columns = list(reference_df.columns[4:])

    step8_data = processing_state.get('processing_data', {}).get('step_8_data', {})
    sample_groups = step8_data.get('sample_groups')
    if not sample_groups:
        _, sample_groups = extract_sample_labels()

    uploaded_files = processing_state['uploaded_files']
    name_to_index = {f['name']: i for i, f in enumerate(uploaded_files)}

    all_sample_results = {}
    for sample_name, sample_files in sample_groups.items():
        sample_masses_list = []
        for filename in sample_files:
            index = name_to_index.get(filename)
            if index is None or index >= len(peaks_arrays):
                continue
            masses = peaks_arrays[index][0]
            in_range = masses[(masses >= ZOO_MS_MASS_MIN) & (masses <= ZOO_MS_MASS_MAX)]
            sample_masses_list.extend(in_range.tolist())

        sample_masses = np.array(sorted(sample_masses_list), dtype=float)
        top_matches = rank_species_matches(sample_masses, reference_df, mass_columns)
        contaminants = find_contaminants(sample_masses)

        all_sample_results[sample_name] = {
            'files': sample_files,
            'num_replicates': len(sample_files),
            'marker_count': int(sample_masses.size),
            'top_matches': top_matches,
            'contaminants': contaminants
        }

    return _save_step(9, {
        'status': 'completed',
        'message': (
            f'Species identification completed for {len(all_sample_results)} '
            f'samples using {reference_label}'
        ),
        'total_samples': len(all_sample_results),
        'sample_results': all_sample_results,
        'reference_database': reference_label,
        'reference_source': reference_source
    })


@app.route('/api/state')
def get_state():
    """Get current application state (without heavy spectral arrays)"""
    state = {k: v for k, v in processing_state.items() if k not in HEAVY_STATE_KEYS}
    state['step0'] = _step0_summary()
    return jsonify(state)


@app.route('/api/spectra/<int:index>')
def get_spectrum_data(index):
    """Get spectrum data for visualisation"""
    try:
        arrays = data_store.get('spectra_arrays')
        if not arrays:
            return jsonify({
                'error': 'No spectra loaded. Please complete Step 2 (Visualise Spectra) first.',
                'hint': 'Navigate to Step 2 and process the spectra first.'
            }), 400

        if index < 0 or index >= len(arrays):
            return jsonify({
                'error': f'Spectrum index {index} out of range. Valid range: 0-{len(arrays)-1}'
            }), 400

        mass, intensity = arrays[index]
        metadata = {}
        if index < len(processing_state.get('uploaded_files', [])):
            metadata['filename'] = processing_state['uploaded_files'][index]['name']

        print(f"DEBUG: Serving spectrum {index}: {metadata.get('filename', 'Unknown')} "
              f"({mass.size} points, m/z {mass.min():.1f}-{mass.max():.1f})")

        return jsonify({
            'success': True,
            'index': index,
            'total': len(arrays),
            'mass': mass.tolist(),
            'intensity': intensity.tolist(),
            'metadata': metadata,
            'source': 'R'
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to load spectrum: {str(e)}'}), 500


@app.route('/api/peaks/<int:index>')
def get_peak_data(index):
    """Get peak data for visualisation"""
    try:
        peaks_arrays = data_store.get('peaks_arrays')
        if not peaks_arrays:
            return jsonify({
                'error': 'No peaks detected yet. Run Step 6 (Peak Picking) first.'
            }), 400

        if index < 0 or index >= len(peaks_arrays):
            return jsonify({'error': 'Peak index out of range'}), 400

        peak_mass, peak_intensity = peaks_arrays[index]

        spectrum_mass = []
        spectrum_intensity = []
        spectra_arrays = data_store.get('processed_arrays') or data_store.get('spectra_arrays')
        if spectra_arrays and index < len(spectra_arrays):
            spectrum_mass = spectra_arrays[index][0].tolist()
            spectrum_intensity = spectra_arrays[index][1].tolist()

        return jsonify({
            'success': True,
            'index': index,
            'total': len(peaks_arrays),
            'peak_mass': peak_mass.tolist(),
            'peak_intensity': peak_intensity.tolist(),
            'spectrum_mass': spectrum_mass,
            'spectrum_intensity': spectrum_intensity
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/noise/<int:index>')
def get_noise_data(index):
    """Estimate and return the noise for a single spectrum"""
    try:
        spectra = data_store.get('processed_spectra') or data_store.get('spectra')
        if spectra is None:
            return jsonify({'error': 'Spectra not loaded. Complete Step 2 first.'}), 400

        r_integration = get_r_integration()
        total = r_integration.spectra_length(spectra)
        if index < 0 or index >= total:
            return jsonify({'error': 'Spectrum index out of range'}), 400

        cache = data_store.setdefault('noise_cache', {})
        if index not in cache:
            cache[index] = r_integration.estimate_noise(r_integration.spectrum_at(spectra, index))

        noise = cache[index]
        filename = None
        if index < len(processing_state.get('uploaded_files', [])):
            filename = processing_state['uploaded_files'][index]['name']

        spectrum_mass = []
        spectrum_intensity = []
        spectra_arrays = data_store.get('processed_arrays') or data_store.get('spectra_arrays')
        if spectra_arrays and index < len(spectra_arrays):
            spectrum_mass = spectra_arrays[index][0].tolist()
            spectrum_intensity = spectra_arrays[index][1].tolist()
        source = 'processed' if data_store.get('processed_arrays') else 'raw'

        return jsonify({
            'success': True,
            'index': index,
            'total': total,
            'filename': filename,
            'noise_mass': noise['noise_mass'],
            'noise_intensity': noise['noise_intensity'],
            'spectrum_mass': spectrum_mass,
            'spectrum_intensity': spectrum_intensity,
            'source': source
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/export/peaks')
def export_peaks():
    """Export the real detected peaks for every spectrum as CSV"""
    peaks_arrays = data_store.get('peaks_arrays')
    if not peaks_arrays:
        return jsonify({'error': 'No peaks available. Complete Step 6 first.'}), 400

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Filename', 'Mass', 'Intensity'])

    uploaded_files = processing_state.get('uploaded_files', [])
    for index, (mass, intensity) in enumerate(peaks_arrays):
        filename = uploaded_files[index]['name'] if index < len(uploaded_files) \
            else f'spectrum_{index + 1}'
        for m, i in zip(mass, intensity):
            writer.writerow([filename, f'{float(m):.4f}', f'{float(i):.6g}'])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=SpecieScan_peaks.csv'}
    )


@app.route('/reset', methods=['POST'])
def reset_workflow():
    """Reset the workflow"""
    global processing_state
    processing_state = {
        'current_step': 0,
        'uploaded_files': [],
        'session_id': str(uuid.uuid4()),
        'processing_data': {},
        'status': 'ready',
        'spectrum_count': 0,
    }
    clear_derived_data()
    _step0_cleanup_all()
    _step9_cleanup()

    upload_folder = app.config['UPLOAD_FOLDER']
    if os.path.exists(upload_folder):
        for file in os.listdir(upload_folder):
            os.remove(os.path.join(upload_folder, file))

    return jsonify({'success': True, 'state': processing_state})


@app.route('/clear-files', methods=['POST'])
def clear_files():
    """Clear all uploaded files but keep workflow state"""
    processing_state['uploaded_files'] = []
    clear_derived_data()
    _step9_cleanup()

    upload_folder = app.config['UPLOAD_FOLDER']
    files_removed = 0
    if os.path.exists(upload_folder):
        for file in os.listdir(upload_folder):
            file_path = os.path.join(upload_folder, file)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    files_removed += 1
            except Exception as e:
                print(f"Error removing file {file_path}: {e}")

    return jsonify({
        'success': True,
        'files_removed': files_removed,
        'state': processing_state
    })


@app.route('/downloads/<filename>')
def download_file(filename):
    """Download processed files"""
    return send_from_directory('downloads', filename, as_attachment=True)


def reset_state_on_startup():
    """Reset the global state and clear uploaded files on startup"""
    global processing_state

    upload_folder = app.config['UPLOAD_FOLDER']
    if os.path.exists(upload_folder):
        for filename in os.listdir(upload_folder):
            file_path = os.path.join(upload_folder, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error removing file {file_path}: {e}")

    processing_state = {
        'current_step': 0,
        'uploaded_files': [],
        'session_id': str(uuid.uuid4()),
        'processing_data': {},
        'status': 'ready',
        'spectrum_count': 0,
    }
    clear_derived_data()
    _step0_cleanup_all()
    _step9_cleanup()

    print("State reset on startup - all previous data cleared")


if __name__ == '__main__':
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs('downloads', exist_ok=True)
    os.makedirs(STEP0_WORK_DIR, exist_ok=True)

    # Reset state and clear files on startup
    reset_state_on_startup()

    print("\n" + "=" * 70)
    print("SPEC SCAN WEB APPLICATION - v4.2 (Optional Bruker conversion + reference database selection)")
    print("=" * 70)
    print(f"R Integration: {'✓ AVAILABLE' if R_INTEGRATION_AVAILABLE else '✗ NOT AVAILABLE'}")
    if not R_INTEGRATION_AVAILABLE and R_INTEGRATION_ERROR:
        print(f"  Error: {R_INTEGRATION_ERROR}")
    print(f"Upload Folder: {app.config['UPLOAD_FOLDER']}")
    print(f"Max File Size: {app.config['MAX_CONTENT_LENGTH'] / 1024 / 1024} MB")
    print("=" * 70 + "\n")

    print("Starting SpecieScan Web Application...")

    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '8080'))
    browser_host = 'localhost' if host in ('0.0.0.0', '127.0.0.1') else host
    url = f'http://{browser_host}:{port}'
    print(f"Open in your browser: {url}")

    if os.environ.get('OPEN_BROWSER', '1') != '0':
        import webbrowser

        def open_browser():
            time.sleep(1.5)
            webbrowser.open(url)

        threading.Thread(target=open_browser, daemon=True).start()

    app.run(host=host, port=port, debug=False)
