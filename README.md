# SpecieScan Web Application

A browser-based (web) application for **ZooMS** (Zooarchaeology by Mass Spectrometry) analysis based on the SpecieScan algorithm. It provides a guided, 9-step workflow that takes `.mzML` MALDI-ToF mass spectra from upload  to taxonomic identification, combining the preprocessing **MALDIquant** R preprocessing with the **Python** SpecieScan algorithm.

All spectra shown in the interface are the real data loaded from your files — there is no simulated/synthetic fallback.

For more information please read Végh, E. I. & Douka, K. (2024). SpecieScan: semi-automated taxonomic identification of bone collagen peptides from MALDI-ToF-MS. Bioinformatics 40(2), 1–12. DOI: 10.1093/bioinformatics/btae054

---

## Features

- 9-step workflow: upload → visualize → QC → preprocess → SNR → peak picking → distribution → averaging → identification/export.
- Real data only: spectra and peaks are loaded from `.mzML` through MALDIquant (via `rpy2`), never generated.
- Interactive Plotly.js visualisations (spectra, noise/SNR, peaks, peak-count histograms).
- Species identification against a reference database plus contaminant screening.
- CSV export of processed peak data.
- Terminal launcher that opens the app in your browser.

---

## Requirements

### Software
- **Python 3.10** (3.9+ should work; developed and tested on 3.10.9).
- **R 4.0 or newer** (tested on R 4.2.3). R is required — the application does not run in a "no-R" mode.

### Python packages
Installed from `requirements.txt`:

| Package | Tested version |
|---|---|
| Flask | 2.3.3 |
| Werkzeug | 2.3.7 |
| numpy | 1.23.5 |
| pandas | 2.3.3 |
| rpy2 | 3.5.15 |

### R packages
- `MALDIquant` — mass spectrometry processing
- `MALDIquantForeign` — file import (`.mzML`)
- `mzR` — low-level mzML reader (a dependency of MALDIquantForeign; from Bioconductor)

### Network
The web interface loads Plotly, Bootstrap and Font Awesome from public CDNs, so an internet connection is needed for styling and charts.

---

## Installation

1. **Get the code**

   Either clone the repository:
   ```bash
   git clone https://github.com/mesve/SpecieScan_webapplication.git
   cd SpecieScan_webapplication
   ```
   or download and unzip the release, then `cd` into the folder.

2. **Install Python dependencies** (a virtual environment is recommended)

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Install R and the R packages**

   Install R from <https://www.r-project.org/> (macOS users may prefer `brew install r`). Then, in an R console:

   ```r
   install.packages(c("MALDIquant", "MALDIquantForeign"))
   if (!requireNamespace("BiocManager", quietly = TRUE)) install.packages("BiocManager")
   BiocManager::install("mzR")
   ```

4. **Run the installer helper (optional)** — it checks Python/R and installs the R packages for you:

   ```bash
   bash install.sh
   ```

---

## Quick start

Launch the app with the CLI launcher (opens your browser automatically):

```bash
./specie_scan
```

Or run it directly:

```bash
python app.py
```

Then open <http://localhost:8080> if the browser does not open by itself.

Useful launcher options:

```bash
./specie_scan --port 5000     # use a different port
./specie_scan --no-browser    # don't open a browser
./specie_scan --debug         # debug mode
./specie_scan --check-only    # check dependencies and exit
```

> **Note:** on startup the app clears `static/uploads/`, so previously uploaded files are removed. Re-upload them each session.

---

## Sample data

A small example batch is included in [`sample_data/`](sample_data/) (Denisova Cave, batch 4):

```
sample_data/
├── DC15000_A1.mzML   DC15000_D1.mzML   DC15000_G1.mzML   # sample DC15000 (3 technical replicates)
└── DC15001_A3.mzML   DC15001_D3.mzML   DC15001_G3.mzML   # sample DC15001 (3 technical replicates)
```

Upload these in Step 1 to try the full workflow. Steps 8–9 will average the three replicates of each sample and produce two species-identification results.

---

## Workflow

| Step | What it does |
|---|---|
| 1. Upload | Select one or more `.mzML` files (batch upload supported). |
| 2. Visualise spectra | Plot real m/z vs intensity; browse files with Previous/Next. |
| 3. Quality control | Detect empty / irregular spectra and summarise lengths. |
| 4. Pre-processing | Savitzky–Golay smoothing, SNIP baseline removal, TIC normalisation. |
| 5. SNR analysis | Estimate noise per spectrum and adjust the SNR threshold interactively. |
| 6. Peak picking | SuperSmoother detection with configurable SNR, then monoisotopic deisotoping. |
| 7. Peak distribution | Histogram of peak counts with outlier filtering. |
| 8. Average replicates | Mean-average technical replicates into one spectrum per sample. |
| 9. Export & identify | Download peak CSV, then match peaks against the reference database and screen for contaminants. |

---

## Input data and reference databases

- **Input:** MALDI-ToF mass spectra in `.mzML` format.
- **Reference database:** `Mammals_reference_Eurasia_2024.csv` (species + ZooMS marker masses).
- **Contaminants:** `contaminants_list_2024.csv` (known contaminant masses).

These two CSV files ship at the repository root. The app locates them next to `app.py` or in a parent directory (see `find_data_file()` in `app.py`). If you move the app, keep the CSVs alongside it.

To analyse other regions/taxa, swap in a different reference CSV with the same column layout (first columns `Order, Family, Species, ZooMS_taxon`, followed by the marker-mass columns).

---

## Output

- **Peak CSV** exported from Step 9 (one row per detected peak: filename, mass, intensity).
- **Species identification** results in the browser: ranked matches with correlation scores.
- **Contaminant screening** results per sample.

---

## Project structure

```
SpecieScan_webapplication/
├── app.py                          # Main Flask application (routes + step processing)
├── specie_scan                      # CLI launcher
├── install.sh                       # Dependency/R-package installer
├── setup.py                         # Python packaging metadata
├── test_app.py                      # Smoke test (no .mzML needed)
├── requirements.txt                 # Python dependencies
├── R_integration/
│   └── r_interface.py              # rpy2 / MALDIquant integration layer
├── python_analysis/
│   └── species_identification.py   # Species matching + contaminant screening
├── static/
│   ├── css/specie_scan.css
│   ├── js/specie_scan.js           # Front-end logic and charts
│   └── uploads/                    # Runtime uploads (git-ignored)
├── downloads/                      # Runtime outputs (git-ignored)
├── templates/
│   ├── base.html
│   └── workflow.html
├── sample_data/                    # Example Denisova batch-4 .mzML files
├── Mammals_reference_Eurasia_2024.csv
└── contaminants_list_2024.csv
```

---

## Troubleshooting

- **R integration not available / "Conversion rules ... appear to be missing"**
  This is an `rpy2`/threading issue. It is already handled in this release (R is initialised on the main thread and the conversion context is seeded per thread). If it appears, make sure you are running the code in this repository and that R and the R packages above are installed.

- **"R packages loaded successfully" never printed**
  Check that `R` is on your `PATH`, then verify:
  ```
  python -c "import rpy2; print(rpy2.__version__)"
  R --slave -e "library(MALDIquant); library(MALDIquantForeign); library(mzR)"
  ```
  On macOS you may need to set `R_HOME`, e.g. `export R_HOME=$(R RHOME)`.

- **Browser shows "Could Not Load Spectrum"**
  The spectra contain ~200,000 points each. This release computes ranges iteratively so large arrays no longer overflow the JavaScript call stack. After updating the code, do a **hard refresh** (Cmd/Ctrl+Shift+R) to clear the cached `specie_scan.js`.

- **Port already in use**
  Start on another port: `./specie_scan --port 5000`.

- **Uploads disappear after restart**
  Expected: the app clears `static/uploads/` on startup. Re-upload your files, or comment out `reset_state_on_startup()` in `app.py`.

- **UI unstyled / charts missing**
  Plotly/Bootstrap load from CDNs; check your internet connection.

---

## Development

```bash
pip install -e ".[dev]"     # includes pytest, black, flake8
python test_app.py          # smoke test
```

---

## Citation

If you use SpecieScan in your research, please cite:

> Végh, E. I. & Douka, K. (2024). *SpecieScan: semi-automated taxonomic identification of bone collagen peptides from MALDI-ToF-MS.* Bioinformatics, 40(2), 1–12. DOI: [10.1093/bioinformatics/btae054](https://doi.org/10.1093/bioinformatics/btae054)

Please also cite the web application and the underlying algorithm code archive:

> Web application DOI: [10.5281/zenodo.23495280](https://doi.org/10.5281/zenodo.23495280)

> Algorithm DOI: [10.5281/zenodo.8055426](https://doi.org/10.5281/zenodo.8055426)

A machine-readable citation is provided in [`CITATION.cff`](CITATION.cff).

---

## License

MIT License — see [`LICENSE`](LICENSE). Copyright (c) 2026 Emese Végh.

---

## Contact

Dr Emese Végh — [mesve3@gmail.com](mailto:mesve3@gmail.com)

---

## Acknowledgments

- Much of the pre-processing steps of the code was adapted from Codlin MC, Douka K, Richter KK (2022). An application of zooms to identify archaeological avian fauna from Teotihuacan, Mexico. Journal of Archaeological Science;148:105692.
- The MALDIquant and MALDIquantForeign developers for the R mass-spectrometry packages.
- Plotly.js, Bootstrap and Font Awesome for the interactive interface.
