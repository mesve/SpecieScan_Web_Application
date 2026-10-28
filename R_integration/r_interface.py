"""
R Integration Layer for SpecieScan
Handles communication between Python and R processing scripts using rpy2
"""

import os
import sys
import threading
import functools
import traceback
from pathlib import Path
import rpy2.robjects as robjects
from rpy2.robjects.packages import importr
import numpy as np
from typing import List, Dict, Any, Tuple

# Embedded R is single-threaded; serialise every R call across Flask threads.
_r_lock = threading.RLock()


def _serialized(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _r_lock:
            return fn(*args, **kwargs)
    return wrapper

# NOTE: We intentionally do NOT call pandas2ri.activate() here. rpy2 stores
# conversion rules in a contextvars.ContextVar; calling activate() from a
# worker thread (as Flask does) builds a converter from an empty snapshot and
# breaks all R calls. SpecieScan only exchanges plain Python/numpy values with
# R, so rpy2's default converter is sufficient.


def ensure_conversion():
    """
    Ensure the current thread has an active rpy2 conversion context.

    rpy2 keeps its conversion rules in a contextvars.ContextVar that is set
    at import time in the main thread. Flask handles requests in worker
    threads whose context is the "missing converter" sentinel, which makes
    every R call fail. Re-seed the default converter in that thread.
    """
    conversion = robjects.conversion
    if conversion.get_conversion() is conversion.missingconverter:
        conversion.set_conversion(robjects.default_converter)


class RIntegrationError(Exception):
    """Custom exception for R integration errors"""
    pass


class SpecieScanR:
    """Main class for R integration with SpecieScan processing"""

    def __init__(self):
        # Seed the rpy2 conversion context for whatever thread constructs this
        # instance. The contextvar is only set in the importing (main) thread,
        # so a lazy construction inside a Flask worker thread would otherwise
        # fail on the first R call below.
        ensure_conversion()
        self.base = importr('base')
        self.utils = importr('utils')
        self.maldiquant = None
        self.maldiquant_foreign = None

        # Check if required R packages are installed
        self._check_r_packages()

    def _check_r_packages(self):
        """Check if required R packages are installed"""
        ensure_conversion()
        required_packages = ['MALDIquant', 'MALDIquantForeign']

        for package in required_packages:
            try:
                robjects.r(
                    f'if (!require("{package}", character.only = TRUE)) '
                    f'install.packages("{package}", repos="https://cran.r-project.org")'
                )
            except Exception as e:
                print(f"Warning: Could not check/install R package '{package}': {e}")

        # Import the packages
        try:
            self.maldiquant = importr('MALDIquant')
            self.maldiquant_foreign = importr('MALDIquantForeign')
            print("✓ R packages loaded successfully: MALDIquant, MALDIquantForeign")
        except Exception as e:
            raise RIntegrationError(
                f"Failed to import R packages: {str(e)}. "
                f"Please ensure MALDIquant and MALDIquantForeign are installed in R."
            )

    # ------------------------------------------------------------------
    # Data extraction helpers
    # ------------------------------------------------------------------
    @_serialized
    def spectrum_arrays(self, spectrum) -> Tuple[np.ndarray, np.ndarray]:
        """
        Extract mass and intensity as numpy arrays from a MALDIquant S4
        object (MassSpectrum or MassPeaks).

        MALDIquant objects are S4 objects and can NOT be indexed like Python
        lists. The package accessors `mass()` and `intensity()` must be used.
        """
        try:
            ensure_conversion()
            mass = np.array(list(self.maldiquant.mass(spectrum)), dtype=float)
            intensity = np.array(list(self.maldiquant.intensity(spectrum)), dtype=float)
            return mass, intensity
        except Exception as e:
            raise RIntegrationError(f"Error extracting spectrum arrays: {str(e)}\n{traceback.format_exc()}")

    @_serialized
    def spectra_arrays(self, spectra) -> List[Tuple[np.ndarray, np.ndarray]]:
        """Extract mass/intensity arrays for every object in a list of spectra/peaks"""
        try:
            ensure_conversion()
            return [self.spectrum_arrays(spectra[i]) for i in range(len(spectra))]
        except Exception as e:
            raise RIntegrationError(f"Error extracting spectra arrays: {str(e)}\n{traceback.format_exc()}")

    @_serialized
    def spectrum_at(self, spectra, index: int):
        """Return a single spectrum from an R list (thread-safe)"""
        try:
            ensure_conversion()
            return spectra[index]
        except Exception as e:
            raise RIntegrationError(f"Error selecting spectrum {index}: {str(e)}\n{traceback.format_exc()}")

    @_serialized
    def spectra_length(self, spectra) -> int:
        """Return the number of spectra in an R list (thread-safe)"""
        try:
            ensure_conversion()
            return len(spectra)
        except Exception as e:
            raise RIntegrationError(f"Error counting spectra: {str(e)}\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    @_serialized
    def load_mzml_files(self, file_paths: List[str]) -> Any:
        """Load .mzML files using MALDIquantForeign"""
        try:
            ensure_conversion()
            r_paths = robjects.StrVector(file_paths)
            spectra = self.maldiquant_foreign.importMzMl(r_paths)
            return spectra
        except Exception as e:
            raise RIntegrationError(f"Error loading mzML files: {str(e)}\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Optional Step 0: convert Bruker Flex data to .mzML
    # ------------------------------------------------------------------
    @_serialized
    def convert_bruker_flex(self, input_path: str, output_path: str) -> int:
        """
        Import a Bruker Flex data folder with MALDIquantForeign and export
        every spectrum as .mzML.

        Returns the number of imported spectra.
        """
        try:
            ensure_conversion()
            os.makedirs(output_path, exist_ok=True)
            spectra = self.maldiquant_foreign.importBrukerFlex(
                input_path, verbose=False
            )
            count = int(len(spectra))
            if count == 0:
                raise RIntegrationError(
                    'No Bruker Flex spectra were found in the uploaded archive.'
                )
            self.maldiquant_foreign.exportMzMl(
                spectra, path=output_path, force=True
            )
            return count
        except RIntegrationError:
            raise
        except Exception as e:
            raise RIntegrationError(
                f'Error converting Bruker Flex data: {str(e)}\n'
                f'{traceback.format_exc()}'
            )

    # ------------------------------------------------------------------
    # Quality control
    # ------------------------------------------------------------------
    @_serialized
    def quality_control(self, spectra) -> Dict[str, Any]:
        """Perform quality control on spectra"""
        try:
            ensure_conversion()
            spectrum_list = list(spectra)
            empty_flags = [bool(self.maldiquant.isEmpty(s)[0]) for s in spectrum_list]
            regular_flags = [bool(self.maldiquant.isRegular(s)[0]) for s in spectrum_list]
            lengths = [int(len(self.maldiquant.mass(s))) for s in spectrum_list]

            length_distribution = {}
            for length in lengths:
                key = str(length)
                length_distribution[key] = length_distribution.get(key, 0) + 1

            return {
                'has_empty': any(empty_flags),
                'all_regular': all(regular_flags),
                'empty_count': int(sum(empty_flags)),
                'irregular_count': int(sum(1 for r in regular_flags if not r)),
                'lengths': lengths,
                'length_distribution': length_distribution,
                'qc_passed': (not any(empty_flags)) and all(regular_flags),
                'shape': {
                    'count': len(lengths),
                    'avg_length': float(np.mean(lengths)) if lengths else 0.0
                }
            }
        except Exception as e:
            raise RIntegrationError(f"Error in quality control: {str(e)}\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Pre-processing
    # ------------------------------------------------------------------
    @_serialized
    def preprocess_spectra(self, spectra) -> Any:
        """Apply smoothing, baseline removal and TIC calibration"""
        try:
            ensure_conversion()
            spectra_smooth = self.maldiquant.smoothIntensity(
                spectra, method="SavitzkyGolay", halfWindowSize=10
            )
            spectra_baseline = self.maldiquant.removeBaseline(
                spectra_smooth, method="SNIP", iterations=100
            )
            spectra_calibrated = self.maldiquant.calibrateIntensity(
                spectra_baseline, method="TIC"
            )
            return spectra_calibrated
        except Exception as e:
            raise RIntegrationError(f"Error in preprocessing: {str(e)}\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Noise estimation
    # ------------------------------------------------------------------
    @_serialized
    def estimate_noise(self, spectrum) -> Dict[str, Any]:
        """
        Estimate noise for a single spectrum.

        MALDIquant's estimateNoise returns a matrix whose two columns are
        the mass values and the estimated noise intensity.
        """
        try:
            ensure_conversion()
            noise = self.maldiquant.estimateNoise(spectrum)
            arr = np.array(noise, dtype=float)
            return {
                'noise_mass': arr[:, 0].tolist(),
                'noise_intensity': arr[:, 1].tolist()
            }
        except Exception as e:
            raise RIntegrationError(f"Error estimating noise: {str(e)}\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Peak picking
    # ------------------------------------------------------------------
    @_serialized
    def detect_peaks(self, spectra, snr: float = 3.5, half_window_size: int = 20) -> Any:
        """Detect peaks in spectra"""
        try:
            ensure_conversion()
            peaks = self.maldiquant.detectPeaks(
                spectra,
                method="SuperSmoother",
                halfWindowSize=int(half_window_size),
                SNR=float(snr)
            )
            return peaks
        except Exception as e:
            raise RIntegrationError(f"Error detecting peaks: {str(e)}\n{traceback.format_exc()}")

    @_serialized
    def monoisotopic_peaks(self, peaks, min_cor: float = 0.95,
                           tolerance: float = 1e-4, distance: float = 1.00235,
                           size_range: str = "2:10") -> Any:
        """Perform monoisotopic peak detection"""
        try:
            ensure_conversion()
            size_parts = str(size_range).split(":")
            min_size = int(size_parts[0])
            max_size = int(size_parts[1])
            size_vector = robjects.IntVector(range(min_size, max_size + 1))

            monoisotopic = self.maldiquant.monoisotopicPeaks(
                peaks,
                minCor=float(min_cor),
                tolerance=float(tolerance),
                distance=float(distance),
                size=size_vector
            )
            return monoisotopic
        except Exception as e:
            raise RIntegrationError(f"Error in monoisotopic peak detection: {str(e)}\n{traceback.format_exc()}")

    @_serialized
    def get_peak_counts(self, peaks) -> List[int]:
        """Get count of peaks for each spectrum"""
        try:
            ensure_conversion()
            return [int(len(self.maldiquant.mass(p))) for p in list(peaks)]
        except Exception as e:
            raise RIntegrationError(f"Error getting peak counts: {str(e)}\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Averaging
    # ------------------------------------------------------------------
    @_serialized
    def average_spectra(self, spectra, labels: List[str]) -> Any:
        """Average spectra by technical replicates"""
        try:
            ensure_conversion()
            r_labels = robjects.StrVector(labels)
            averaged = self.maldiquant.averageMassSpectra(
                spectra,
                labels=r_labels,
                method="mean"
            )
            return averaged
        except Exception as e:
            raise RIntegrationError(f"Error averaging spectra: {str(e)}\n{traceback.format_exc()}")


# Global R integration instance
_r_integration = None
_r_integration_lock = threading.Lock()


def get_r_integration():
    """Get or create R integration instance (thread-safe)"""
    global _r_integration
    if _r_integration is None:
        ensure_conversion()
        with _r_integration_lock:
            if _r_integration is None:
                _r_integration = SpecieScanR()
    return _r_integration
