# SpecieScan — Terminal Quick Start (macOS)

This is the command-line installation for **macOS**. If you prefer not to use the terminal, follow [START_HERE.md](START_HERE.md) instead.

You will install Python 3.10 and R 4.2.3 once, then run four short command blocks. Nothing is uploaded to a server: the app runs on your Mac and your spectra stay local.

**Time:** about 20–30 minutes, mostly downloading.
**Disk:** about 2 GB.
**Internet:** needed for installation and for the page's chart/styling libraries.

---

## 1. Install the two prerequisites

### Python 3.10.11
Download and install the **macOS 64-bit universal2 installer**:

<https://www.python.org/downloads/release/python-31011/>

### R 4.2.3
Check **Apple menu → About This Mac → Chip**:

- **Apple M1/M2/M3/M4 (Apple Silicon):**
  <https://cran.r-project.org/bin/macosx/big-sur-arm64/base/R-4.2.3-arm64.pkg>
- **Intel:**
  <https://cran.r-project.org/bin/macosx/base/R-4.2.3.pkg>

Open each `.pkg` and click **Continue → Continue → Agree → Install**.

> Apple Silicon note: the repository includes a prebuilt `rpy2` package, so you do **not** need Xcode Command Line Tools.

---

## 2. Download the project

1. Open <https://github.com/mesve/SpecieScan_Web_Application>.
2. Click the green **Code** button → **Download ZIP**.
3. Double-click the ZIP in **Downloads** to unpack it. It is usually named `SpecieScan_Web_Application-main`.

> The repository must be public, or you must be signed in with access. If it is private, ask the owner to make it public or to send you the ZIP.

---

## 3. Open Terminal

Open **Terminal** from **Applications → Utilities → Terminal**.

Change into the project folder. Type `cd ` (with a space), then **drag the unzipped folder into the Terminal window** and press Return:

```bash
cd ~/Downloads/SpecieScan_Web_Application-main
```

If you cloned with Git instead, use `cd SpecieScan_Web_Application`.

---

## 4. Create the private Python environment

Run this block exactly as written (it uses the full Python 3.10 path installed by python.org):

```bash
/Library/Frameworks/Python.framework/Versions/3.10/bin/python3.10 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
```

### Apple Silicon only — install the included `rpy2` wheel

```bash
if [ "$(uname -m)" = "arm64" ]; then
  .venv/bin/python -m pip install vendor/rpy2-3.5.15-cp310-cp310-macosx_11_0_arm64.whl
fi
```

This avoids compiling `rpy2`. On Intel Macs the `if` does nothing, and the next step downloads the normal Python wheel.

### Install the Python packages

```bash
.venv/bin/python -m pip install -r requirements.txt
```

> If you see an error mentioning `clang`, `xcode-select`, or “command failed”, run:
> ```bash
> xcode-select --install
> ```
> Click **Install** in the dialog, wait for it to finish, then repeat the `pip install -r requirements.txt` line.

---

## 5. Install the R packages (one time)

These commands install into your own user library, so no administrator password is needed:

```bash
export R_LIBS_USER="$(R --slave -e 'cat(Sys.getenv("R_LIBS_USER"))')"
if [ -n "$R_LIBS_USER" ]; then mkdir -p "$R_LIBS_USER"; fi

R --slave -e 'install.packages(c("MALDIquant","MALDIquantForeign"), repos="https://cloud.r-project.org", lib=Sys.getenv("R_LIBS_USER"))'

R --slave -e 'if (!requireNamespace("BiocManager", quietly=TRUE)) install.packages("BiocManager", repos="https://cloud.r-project.org", lib=Sys.getenv("R_LIBS_USER")); BiocManager::install("mzR", ask=FALSE, update=FALSE, lib=Sys.getenv("R_LIBS_USER"))'
```

This downloads `MALDIquant`, `MALDIquantForeign`, and `mzR`. It can take a few minutes.

---

## 6. Start SpecieScan

```bash
export R_LIBS_USER="$(R --slave -e 'cat(Sys.getenv("R_LIBS_USER"))')"
export R_HOME="$(R RHOME)"
.venv/bin/python app.py
```

The browser opens automatically at **http://localhost:8080**.

Keep the Terminal window open while you use the app. To stop it, press **Control + C** or close the Terminal window.

Uploaded files are cleared every time the app starts, so download your CSV results before closing.

---

## Running it again later

Open Terminal and run only this:

```bash
cd ~/Downloads/SpecieScan_Web_Application-main
export R_LIBS_USER="$(R --slave -e 'cat(Sys.getenv("R_LIBS_USER"))')"
export R_HOME="$(R RHOME)"
.venv/bin/python app.py
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `python3.10: command not found` | Use the full path shown in Step 4. Make sure Python 3.10.11 is installed from python.org. |
| `R: command not found` | Install R 4.2.3, then open a **new** Terminal window. |
| `ModuleNotFoundError` | You are using the system Python. Always run `.venv/bin/python`, not `python3`. |
| `clang` / build error during `pip install` | Run `xcode-select --install`, click **Install**, wait, then repeat the `pip` line. |
| `Port 8080 is in use` | Start on another port: `PORT=5001 .venv/bin/python app.py` and open `http://localhost:5001`. |
| Page is unstyled or charts are empty | Check your internet connection; Bootstrap/Plotly are loaded from CDNs. |
| `R packages loaded successfully` never appears | Run the Step 5 R commands again, then restart. |
| Wrong Python or R architecture | On Apple Silicon install the **arm64** R package; on Intel install the **x86_64** package. |
| Old page after an update | In the browser press **Command + Shift + R**. |

---

## Notes

- **Data privacy:** everything runs locally. Your `.mzML` files stay on your Mac.
- **Sample data:** the `sample_data` folder contains six example `.mzML` files for testing.
- **No terminal?** Use [START_HERE.md](START_HERE.md) and the two `*.command` files instead.
- **Citation:** Végh, E. I. & Douka, K. (2024). *Bioinformatics*, 40(2), 1–12. <https://doi.org/10.1093/bioinformatics/btae054>
