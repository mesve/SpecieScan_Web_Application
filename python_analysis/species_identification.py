"""
Python Analysis Module for SpecieScan
Handles species identification and database matching
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path
import glob
import csv
from typing import List, Dict, Any, Optional, Tuple

class SpecieScanPython:
    """Main class for Python-based species identification"""
    
    def __init__(self, reference_db_path: str = None):
        self.reference_db_path = reference_db_path
        self.reference_data = None
        self.contaminants_db = None
        
    def load_reference_database(self, db_path: str) -> pd.DataFrame:
        """
        Load reference database
        
        Args:
            db_path: Path to reference database CSV
            
        Returns:
            DataFrame with reference data
        """
        try:
            df = pd.read_csv(db_path)
            self.reference_data = df
            return df
        except Exception as e:
            raise ValueError(f"Error loading reference database: {str(e)}")
    
    def load_contaminants_database(self, db_path: str) -> pd.DataFrame:
        """
        Load contaminants database
        
        Args:
            db_path: Path to contaminants CSV
            
        Returns:
            DataFrame with contaminants data
        """
        try:
            df = pd.read_csv(db_path)
            self.contaminants_db = df
            return df
        except Exception as e:
            raise ValueError(f"Error loading contaminants database: {str(e)}")
    
    def load_peak_csv(self, csv_path: str) -> pd.DataFrame:
        """
        Load peak data from CSV file
        
        Args:
            csv_path: Path to peak CSV file
            
        Returns:
            DataFrame with peak data
        """
        try:
            df = pd.read_csv(csv_path)
            return df
        except Exception as e:
            raise ValueError(f"Error loading peak CSV: {str(e)}")
    
    def correlate_with_database(self, sample_peaks: pd.DataFrame, 
                             reference_db: pd.DataFrame) -> pd.DataFrame:
        """
        Correlate sample peaks with reference database
        
        Args:
            sample_peaks: DataFrame with sample peak masses
            reference_db: DataFrame with reference species data
            
        Returns:
            DataFrame with correlation scores
        """
        try:
            correlations = []
            sample_masses = sample_peaks['mass'].values if 'mass' in sample_peaks.columns else sample_peaks.iloc[:, 0].values
            
            # Get unique species from reference database
            species_list = reference_db['species'].unique() if 'species' in reference_db.columns else reference_db.columns[1:]
            
            for species in species_list:
                # Get reference masses for this species
                if 'species' in reference_db.columns:
                    species_data = reference_db[reference_db['species'] == species]
                    if len(species_data) > 0:
                        ref_masses = species_data.iloc[:, 2:].values.flatten()  # Skip first columns (species, maybe ID)
                        ref_masses = ref_masses[~pd.isna(ref_masses)]  # Remove NaN values
                    else:
                        continue
                else:
                    # Alternative format
                    ref_masses = reference_db[reference_db.iloc[:, 0] == species].iloc[:, 2:].values.flatten()
                    ref_masses = ref_masses[~pd.isna(ref_masses)]
                
                # Calculate correlation
                correlation = self._calculate_mass_correlation(sample_masses, ref_masses)
                
                correlations.append({
                    'species': species,
                    'correlation': correlation,
                    'matched_peaks': len(self._find_matching_peaks(sample_masses, ref_masses, tolerance=0.5))
                })
            
            # Convert to DataFrame and sort by correlation
            result_df = pd.DataFrame(correlations)
            result_df = result_df.sort_values('correlation', ascending=False)
            
            return result_df
            
        except Exception as e:
            raise ValueError(f"Error in correlation analysis: {str(e)}")
    
    def _calculate_mass_correlation(self, sample_masses: np.ndarray, 
                                 ref_masses: np.ndarray, tolerance: float = 0.5) -> float:
        """
        Calculate correlation between sample and reference masses
        
        Args:
            sample_masses: Sample mass values
            ref_masses: Reference mass values
            tolerance: Mass tolerance for matching
            
        Returns:
            Correlation coefficient
        """
        # Find matching peaks
        matches = self._find_matching_peaks(sample_masses, ref_masses, tolerance)
        
        # Calculate simple correlation based on matches
        if len(matches) == 0:
            return 0.0
        
        # Ratio of matches to total reference peaks
        match_ratio = len(matches) / len(ref_masses)
        
        # Weight by intensity if available (simplified version)
        return match_ratio
    
    def _find_matching_peaks(self, sample_masses: np.ndarray, 
                          ref_masses: np.ndarray, tolerance: float) -> List[Tuple[float, float]]:
        """
        Find matching peaks between sample and reference
        
        Args:
            sample_masses: Sample mass values
            ref_masses: Reference mass values
            tolerance: Mass tolerance in Da
            
        Returns:
            List of matching peak pairs
        """
        matches = []
        for ref_mass in ref_masses:
            # Find closest sample peak
            diffs = np.abs(sample_masses - ref_mass)
            min_diff_idx = np.argmin(diffs)
            
            if diffs[min_diff_idx] <= tolerance:
                matches.append((sample_masses[min_diff_idx], ref_mass))
        
        return matches
    
    def identify_species(self, sample_peaks_path: str, reference_db_path: str,
                        contaminants_path: str = None) -> Dict[str, Any]:
        """
        Identify species from sample peaks
        
        Args:
            sample_peaks_path: Path to sample peaks CSV
            reference_db_path: Path to reference database
            contaminants_path: Path to contaminants database (optional)
            
        Returns:
            Dictionary with identification results
        """
        try:
            # Load data
            sample_peaks = self.load_peak_csv(sample_peaks_path)
            reference_db = self.load_reference_database(reference_db_path)
            
            if contaminants_path:
                contaminants_db = self.load_contaminants_database(contaminants_path)
            else:
                contaminants_db = None
            
            # Perform correlation analysis
            correlations = self.correlate_with_database(sample_peaks, reference_db)
            
            # Check for contaminants
            contaminant_results = None
            if contaminants_db is not None:
                contaminant_results = self.correlate_with_database(sample_peaks, contaminants_db)
            
            # Get top matches
            top_matches = correlations.head(5)
            
            return {
                'top_matches': top_matches.to_dict('records'),
                'all_correlations': correlations.to_dict('records'),
                'contaminant_matches': contaminant_results.to_dict('records') if contaminant_results is not None else None,
                'sample_file': os.path.basename(sample_peaks_path),
                'reference_database': os.path.basename(reference_db_path),
                'total_reference_species': len(correlations)
            }
            
        except Exception as e:
            raise ValueError(f"Error in species identification: {str(e)}")
    
    def batch_process_directory(self, csv_directory: str, reference_db_path: str,
                            output_directory: str = None) -> Dict[str, Any]:
        """
        Process all CSV files in a directory
        
        Args:
            csv_directory: Directory containing peak CSV files
            reference_db_path: Path to reference database
            output_directory: Directory for results (optional)
            
        Returns:
            Dictionary with batch results
        """
        try:
            csv_files = glob.glob(os.path.join(csv_directory, "*.csv"))
            
            if not csv_files:
                raise ValueError(f"No CSV files found in {csv_directory}")
            
            results = {}
            
            for csv_file in csv_files:
                filename = os.path.basename(csv_file)
                try:
                    result = self.identify_species(csv_file, reference_db_path)
                    results[filename] = result
                except Exception as e:
                    results[filename] = {'error': str(e)}
            
            # Save results if output directory specified
            if output_directory:
                os.makedirs(output_directory, exist_ok=True)
                
                # Create summary results
                summary_data = []
                for filename, result in results.items():
                    if 'error' not in result and result['top_matches']:
                        top_match = result['top_matches'][0]
                        summary_data.append({
                            'filename': filename,
                            'species': top_match['species'],
                            'correlation': top_match['correlation'],
                            'matched_peaks': top_match['matched_peaks']
                        })
                
                summary_df = pd.DataFrame(summary_data)
                summary_path = os.path.join(output_directory, 'species_identification_summary.csv')
                summary_df.to_csv(summary_path, index=False)
            
            return {
                'processed_files': len(csv_files),
                'successful_identifications': len([r for r in results.values() if 'error' not in r]),
                'results': results
            }
            
        except Exception as e:
            raise ValueError(f"Error in batch processing: {str(e)}")
    
    def create_results_report(self, results: Dict[str, Any], output_path: str):
        """
        Create detailed results report
        
        Args:
            results: Results from identification or batch processing
            output_path: Path for output report
        """
        try:
            if 'processed_files' in results:
                # Batch processing report
                report_lines = [
                    "SpecieScan Species Identification Report",
                    "=" * 50,
                    f"Processed Files: {results['processed_files']}",
                    f"Successful Identifications: {results['successful_identifications']}",
                    f"Success Rate: {results['successful_identifications']/results['processed_files']*100:.1f}%",
                    "",
                    "Sample Results:",
                    "-" * 20
                ]
                
                for filename, result in results['results'].items():
                    if 'error' not in result:
                        top_match = result['top_matches'][0] if result['top_matches'] else None
                        if top_match:
                            report_lines.append(f"{filename}: {top_match['species']} ({top_match['correlation']:.3f})")
                        else:
                            report_lines.append(f"{filename}: No matches found")
                    else:
                        report_lines.append(f"{filename}: ERROR - {result['error']}")
            
            else:
                # Single sample report
                report_lines = [
                    "SpecieScan Species Identification Report",
                    "=" * 50,
                    f"Sample File: {results.get('sample_file', 'Unknown')}",
                    f"Reference Database: {results.get('reference_database', 'Unknown')}",
                    f"Total Reference Species: {results.get('total_reference_species', 0)}",
                    "",
                    "Top 5 Matches:",
                    "-" * 15
                ]
                
                for i, match in enumerate(results['top_matches'][:5], 1):
                    report_lines.append(
                        f"{i}. {match['species']}: {match['correlation']:.3f} ({match['matched_peaks']} peaks)"
                    )
                
                if results.get('contaminant_matches'):
                    report_lines.extend([
                        "",
                        "Potential Contaminants:",
                        "-" * 25
                    ])
                    for contaminant in results['contaminant_matches'][:3]:
                        report_lines.append(f"- {contaminant['species']}: {contaminant['correlation']:.3f}")
            
            # Write report
            with open(output_path, 'w') as f:
                f.write('\n'.join(report_lines))
                
        except Exception as e:
            raise ValueError(f"Error creating report: {str(e)}")

# Global Python analysis instance
_python_analysis = None

def get_python_analysis():
    """Get or create Python analysis instance"""
    global _python_analysis
    if _python_analysis is None:
        _python_analysis = SpecieScanPython()
    return _python_analysis