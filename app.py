#!/usr/bin/env python3
"""
SpecieScan Web Application
A web-based interface for ZooMS (Zooarchaeology Mass Spectrometry) analysis
Integrates R preprocessing and Python species identification workflows
"""

import os
import csv
import io
import json
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory, Response
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

# Reference data file names
REFERENCE_DB_FILENAME = 'Mammals_reference_Eurasia_2024.csv'
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
    'current_step': 1,
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
}

# Keys excluded from /api/state responses
HEAVY_STATE_KEYS = {
    'spectra', 'processed_spectra', 'peaks', 'averaged_spectra'
}

# Allowed file extensions
ALLOWED_EXTENSIONS = {'mzML', 'mzml'}


def allowed_file(filename):
    """Check if file has allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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
        1: "Data Upload",
        2: "Visualize Spectra",
        3: "Quality Control",
        4: "Pre-process",
        5: "Determine SNR",
        6: "Peak Picking",
        7: "Peak Distribution",
        8: "Average Replicates",
        9: "Export & Analysis"
    }
    return render_template('workflow.html', state=processing_state, step_titles=step_titles)


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
    """Step 2: Load spectra from R for visualization"""
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


def rank_species_matches(sample_masses, reference_df, mass_columns,
                         tolerance=MATCH_TOLERANCE, top_n=6):
    """Rank reference species by the fraction of reference markers matched"""
    if sample_masses.size == 0:
        return []

    results = []
    for _, row in reference_df.iterrows():
        ref_values = row[mass_columns].astype(float).values
        ref_masses = ref_values[~np.isnan(ref_values)]
        if ref_masses.size == 0:
            continue

        matched = sum(1 for rm in ref_masses if _find_nearest(sample_masses, rm, tolerance))
        score = matched / float(ref_masses.size)

        results.append({
            'ZooMS_taxon': str(row.get('ZooMS_taxon', '')),
            'species': str(row.get('Species', '')),
            'common_name': '',
            'family': str(row.get('Family', '')),
            'order': str(row.get('Order', '')),
            'reference_peaks': [float(x) for x in ref_masses],
            'correlation': round(float(score), 3),
            'matched_peaks': int(matched),
            'total_reference_peaks': int(ref_masses.size)
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

    reference_path = find_data_file(REFERENCE_DB_FILENAME)
    if not reference_path:
        raise Exception(
            f'Reference database "{REFERENCE_DB_FILENAME}" not found. '
            f'Place it next to the application folder.'
        )

    import pandas as pd
    reference_df = pd.read_csv(reference_path)
    if reference_df.shape[1] <= 4:
        raise Exception('Reference database does not contain marker mass columns')

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
        'message': f'Species identification completed for {len(all_sample_results)} samples',
        'total_samples': len(all_sample_results),
        'sample_results': all_sample_results,
        'reference_database': os.path.basename(reference_path)
    })


@app.route('/api/state')
def get_state():
    """Get current application state (without heavy spectral arrays)"""
    state = {k: v for k, v in processing_state.items() if k not in HEAVY_STATE_KEYS}
    return jsonify(state)


@app.route('/api/spectra/<int:index>')
def get_spectrum_data(index):
    """Get spectrum data for visualization"""
    try:
        arrays = data_store.get('spectra_arrays')
        if not arrays:
            return jsonify({
                'error': 'No spectra loaded. Please complete Step 2 (Visualize Spectra) first.',
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
    """Get peak data for visualization"""
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
        'current_step': 1,
        'uploaded_files': [],
        'session_id': str(uuid.uuid4()),
        'processing_data': {},
        'status': 'ready',
        'spectrum_count': 0,
    }
    clear_derived_data()

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
        'current_step': 1,
        'uploaded_files': [],
        'session_id': str(uuid.uuid4()),
        'processing_data': {},
        'status': 'ready',
        'spectrum_count': 0,
    }
    clear_derived_data()

    print("State reset on startup - all previous data cleared")


if __name__ == '__main__':
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs('downloads', exist_ok=True)

    # Reset state and clear files on startup
    reset_state_on_startup()

    print("\n" + "=" * 70)
    print("SPEC SCAN WEB APPLICATION - v3.0 (Real R data, no simulation)")
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
