# SpecieScan Web Application

A browser-based (web) application for **ZooMS** (Zooarchaeology by Mass Spectrometry) analysis based on the SpecieScan algorithm. It provides an optional Bruker-to-`.mzML` conversion step followed by a guided, 9-step workflow that takes `.mzML` MALDI-ToF mass spectra from upload to taxonomic identification, combining **MALDIquant** R pre-processing with the **Python** SpecieScan algorithm.

All spectra shown in the interface are the real data loaded from your files — there is no simulated/synthetic fallback.

For more information please read Végh, E. I. & Douka, K. (2024). SpecieScan: semi-automated taxonomic identification of bone collagen peptides from MALDI-ToF-MS. Bioinformatics 40(2), 1–12. DOI: 10.1093/bioinformatics/btae054

> **New to Python, R, or the terminal?** Follow **[START_HERE.md](START_HERE.md)** for a click-by-click macOS setup — no commands to type.
>
> **Prefer the terminal?** Follow **[TERMINAL_GUIDE.md](TERMINAL_GUIDE.md)** for a copy-paste macOS install.

---

## Features

- Optional **Step 0**: convert raw Bruker Flex data to `.mzML` (ZIP upload, conversion in R, ZIP download).
- 9-step workflow: upload → visualise → QC → pre-process → SNR → peak picking → distribution → averaging → identification/export.
- Real data only: spectra and peaks are loaded from `.mzML` through MALDIquant (via `rpy2`), never generated.
- Interactive Plotly.js visualisations (mirror spectra, noise/SNR, peaks, peak-count histograms).
- Step 2 mirror view: two spectra stacked around a shared m/z axis, with the bottom spectrum mirrored and independently navigable.
- Step 5 overlays the real spectrum with the estimated noise and SNR threshold curves, with mass-range, Y-max and threshold zoom controls for inspecting noise in detail.
- Step 9 ships seven SpecieScan reference databases (Eurasia, African and New World mammals, birds, fish, amphibians, reptiles; last updated 2024) and also accepts a custom reference CSV.
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

For Apple Silicon + Python 3.10, `vendor/` contains a prebuilt `rpy2` wheel so no compiler is required; the installers use it automatically. Other platforms install `rpy2` from PyPI.

### R packages
- `MALDIquant` — mass spectrometry processing
- `MALDIquantForeign` — `.mzML` import/export and Bruker Flex import (used by optional Step 0)
- `mzR` — low-level mzML reader (a dependency of MALDIquantForeign; from Bioconductor)

### Network
The web interface loads Plotly, Bootstrap and Font Awesome from public CDNs, so an internet connection is needed for styling and charts.

---

## Installation

1. **Get the code**

   Either clone the repository:
   ```bash
   git clone https://github.com/mesve/SpecieScan_Web_Application.git
   cd SpecieScan_Web_Application
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

## Optional Step 0: convert Bruker data to .mzML

If your spectra come straight from a Bruker MALDI instrument, the app can convert them before the main workflow. This step is optional — skip it if your files are already `.mzML`.

1. Compress your Bruker MALDI folder into a `.zip` (on macOS: right-click the folder → **Compress**).
2. On **Step 0**, upload the ZIP with **Upload Bruker Files**. The archive is extracted safely on your computer; nothing is uploaded to the internet.
3. Click **Convert to mzML**. R (`MALDIquantForeign`) imports the Bruker Flex spectra and exports one `.mzML` file per spectrum.
4. Click **Download .mzML Files (.zip)** and unzip the result.

Renaming is **not** automatic, because Step 1 and Step 8 rely on your sample names. Rename the converted files to `Samplenumber_spotnumber` (for example `DC15000_A1.mzML`, `DC15000_D1.mzML`, `DC15000_G1.mzML`) before uploading them in Step 1. Replicates of the same sample must share the same identifier so that Step 8 can average them.

The ZIP upload limit is 500 MB and the extracted size limit is 2 GB.

---

## Workflow

| Step | What it does |
|---|---|
| 0. Convert (optional) | Upload a Bruker Flex `.zip`, convert to `.mzML` in R, download the converted files. |
| 1. Upload | Select one or more `.mzML` files (batch upload supported). |
| 2. Visualise spectra | Plot two real spectra in a mirror view around a shared m/z axis. Each side has its own Previous/Next controls and filename label; zooming one side updates both. |
| 3. Quality control | Detect empty / irregular spectra and summarise lengths. |
| 4. Pre-processing | Savitzky–Golay smoothing, SNIP baseline removal, TIC normalisation. |
| 5. SNR analysis | Estimate noise per spectrum, overlay the spectrum with the noise/SNR curves, and zoom to a mass window or to the threshold. |
| 6. Peak picking | SuperSmoother detection with configurable SNR, then monoisotopic deisotoping. |
| 7. Peak distribution | Histogram of peak counts with outlier filtering. |
| 8. Average replicates | Mean-average technical replicates into one spectrum per sample. |
| 9. Export & identify | Download peak CSV, then match peaks against a built-in SpecieScan 2024 database or your own uploaded reference CSV, and screen for contaminants. |

---

## Input data and reference databases

- **Input:** MALDI-ToF mass spectra in `.mzML` format.
- **Built-in reference databases (2024):** seven SpecieScan databases in `reference_databases/`:
  - Eurasia Mammals (121 species)
  - African Mammals (65 species)
  - New World Mammals (97 species)
  - Birds (21 species)
  - Fish (141 species)
  - Amphibians (11 species)
  - Reptiles (8 species)
- **Custom reference database:** upload a `.csv` in Step 9. It must use the columns `Order, Family, Species, ZooMS_taxon`, followed by one or more marker-mass columns. Marker cells can contain one mass or alternatives separated by `/`, `•`, or whitespace.
- **Contaminants:** `contaminants_list_2024.csv` (known contaminant masses).

The built-in databases live in `reference_databases/` and are loaded from there. Custom uploads are stored outside `static/` and removed when the workflow is reset. The built-in files come from the SpecieScan algorithm and were last updated in 2024; see `reference_databases/README.md` for provenance and counts.

---

## Output

- **Converted `.mzML` files** from optional Step 0, downloaded as a ZIP.
- **Peak CSV** exported from Step 9 (one row per detected peak: filename, mass, intensity).
- **Species identification** results in the browser: ranked matches with correlation scores.
- **Contaminant screening** results per sample.

---

## Project structure

```
SpecieScan_Web_Application/
├── START_HERE.md                    # Beginner guide (no terminal knowledge needed)
├── TERMINAL_GUIDE.md                # Copy-paste terminal install for macOS
├── 1-Install-SpecieScan.command     # Double-click: one-time macOS setup
├── 2-Start-SpecieScan.command       # Double-click: launch and open the browser
├── vendor/                          # Prebuilt rpy2 wheel for Apple Silicon + Python 3.10
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
├── reference_databases/            # Seven built-in SpecieScan 2024 databases
├── Mammals_reference_Eurasia_2024.csv  # Legacy copy (the app uses reference_databases/)
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


> Algorithm DOI: [10.5281/zenodo.8055426](https://doi.org/10.5281/zenodo.8055426)

A machine-readable citation is provided in [`CITATION.cff`](CITATION.cff).

---

## Licence

MIT Licence — see [`LICENSE`](LICENSE). Copyright (c) 2026 Emese Végh.

---

## Contact

Dr Emese Végh — [mesve3@gmail.com](mailto:mesve3@gmail.com)

---

## Acknowledgements

- Much of the pre-processing steps of the code was adapted from Codlin MC, Douka K, Richter KK (2022). An application of zooms to identify archaeological avian fauna from Teotihuacan, Mexico. Journal of Archaeological Science;148:105692. 
- The MALDIquant and MALDIquantForeign developers for the R mass-spectrometry packages.
- Plotly.js, Bootstrap and Font Awesome for the interactive interface.
