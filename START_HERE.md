# SpecieScan — Start Here (macOS)

This guide is for **macOS users who have nothing installed yet** and do **not** want to use the terminal. You will install two free programs (Python and R) with normal macOS installers, then double-click two files in the SpecieScan folder.

You do **not** need to type any commands. When a black **Terminal** window opens by itself, that is expected — just leave it open and wait.

**Time needed:** about 20–40 minutes, mostly waiting.
**Disk space needed:** about 2 GB.
**Internet:** required during installation and for the charts in the web page.

---

## Before you start

- Use a Mac with macOS 11 or newer.
- Keep the SpecieScan folder on your **Desktop** and do not rename or move it afterwards.
- Your spectra are processed **on your own Mac**. Nothing is uploaded to an external server.
- If you were given a ZIP file by the workshop organiser, skip to Step 2.

---

## Step 1 — Download SpecieScan

1. Open the project page in your browser:
   <https://github.com/mesve/SpecieScan_Web_Application>
2. Click the green **Code** button, then **Download ZIP**.
3. In your **Downloads** folder, double-click the ZIP file to unpack it.
4. Drag the unpacked folder to your **Desktop** and open it. You should see files named `1-Install-SpecieScan.command`, `2-Start-SpecieScan.command`, `app.py`, `sample_data`, and others.

> If the page says “Not Found”, the repository is private. Ask the organiser for access or for the ZIP file.

---

## Step 2 — Install Python 3.10.11

Python is the language the web application is written in.

1. Open: <https://www.python.org/downloads/release/python-31011/>
2. Scroll to the **Files** table and click **macOS 64-bit universal2 installer**.
3. Open the downloaded `.pkg` file.
4. Click **Continue → Continue → Agree → Install**.
5. If macOS asks for your password or Touch ID, provide it.
6. When it says the installation was successful, click **Close**.

> **Important:** install **3.10.11**, not the newest Python. Newer versions do not work with this release.

---

## Step 3 — Install R 4.2.3

R does the mass-spectrometry pre-processing.

First check your Mac type: open the **Apple menu → About This Mac** and look at **Chip**.
- If it says **Apple M1 / M2 / M3 / M4**, use the **Apple Silicon** link.
- If it says **Intel**, use the **Intel** link.

**Apple Silicon:**
<https://cran.r-project.org/bin/macosx/big-sur-arm64/base/R-4.2.3-arm64.pkg>

**Intel:**
<https://cran.r-project.org/bin/macosx/base/R-4.2.3.pkg>

1. Open the downloaded `.pkg` file.
2. Click **Continue → Continue → Agree → Install**.
3. Enter your password or Touch ID if asked.
4. Click **Close** when it finishes.

> Install **R 4.2.3**. Do not install a different R version unless the developer asks you to.

---

## Step 4 — Run the one-time setup (double-click)

1. Open the SpecieScan folder on your Desktop.
2. **Right-click** (or Control-click) `1-Install-SpecieScan.command`.
3. Choose **Open**.
4. A warning may appear that the file is from an unidentified developer. Click **Open** again.
5. A **Terminal** window opens and starts working by itself. **Do not type anything and do not close the window.**

What happens next:
- It creates a private Python environment inside the folder.
- It downloads the Python and R packages (this can take 5–30 minutes).
- It finishes with a dialog: **“Installation complete.”** Click **OK**.

If a dialog says Python or R is missing, install the missing program from Step 2 or 3, then double-click `1-Install-SpecieScan.command` again.

If something fails, the file `setup_log.txt` in the SpecieScan folder records what happened. Send it to the developer.

> **If double-clicking opens a text document instead of Terminal:** right-click the file → **Open With → Terminal**, or right-click → **Open** and confirm.

---

## Step 5 — Start SpecieScan

1. In the SpecieScan folder, **right-click** `2-Start-SpecieScan.command`.
2. Choose **Open** (and **Open** again if macOS warns).
3. A Terminal window opens and says `SpecieScan is starting`.
4. After a few seconds, your browser opens the application automatically.

If the browser does not open, open Safari/Chrome and go to:

**http://127.0.0.1:8080**

(If the Terminal window shows a different address such as `http://127.0.0.1:8081`, use that one.)

> **Keep the Terminal window open while you work.** Closing it stops SpecieScan. This is normal — the application runs on your Mac, not on a website.

---

## Step 6 — Use the application

1. **Step 0 (optional)** — if your data come straight from a Bruker MALDI instrument, compress the Bruker folder into a `.zip`, upload it in Step 0, click **Convert to mzML**, then download the converted files. Skip this step if your files are already `.mzML`.
2. Rename the converted files to `Samplenumber_spotnumber` (for example `DC15000_A1.mzML`) before continuing. Replicates of the same sample need the same identifier so they can be averaged in Step 8.
3. In **Step 1**, click the upload area and choose your `.mzML` files (or drag them in).
4. If you want to try it first, upload the files in the `sample_data` folder.
5. Click **Process Files**.
6. Follow the numbered steps in the left sidebar: visualise, quality control, pre-process, SNR, peak picking, distribution, averaging, and identification. In Step 2 the spectra are shown as a mirror view: use the separate Previous/Next buttons above and below the plot to choose the top and bottom spectrum.
7. In the final step, choose either **Upload my own reference database** (a `.csv` with the SpecieScan layout) or a **Default Reference Database (2024)** — Eurasia, African or New World mammals, birds, fish, amphibians, or reptiles — then run the identification. The built-in databases come from the SpecieScan algorithm and were last updated in 2024.
8. You can download the peak table and the identification results as CSV files.

The left sidebar always shows the documentation, the DOIs, and the citation for the method.

---

## Step 7 — Stop SpecieScan

- Close the Terminal window, **or**
- Click the Terminal window and press **Control + C**.

Your uploaded files are cleared when the application next starts. **Download any CSV results you need before closing.**

---

## Everyday use (after the first time)

You do **not** repeat Steps 2–4. Just:

1. Open the SpecieScan folder.
2. Double-click `2-Start-SpecieScan.command`.
3. Use the application in your browser.
4. Close the Terminal window when finished.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| “Cannot be opened because it is from an unidentified developer” | Right-click the file → **Open** → **Open**. You only need to do this once per file. |
| Double-clicking the `.command` file opens a text editor | Right-click → **Open With** → **Terminal**. |
| “Python 3.10 was not found” | Install Python 3.10.11 from Step 2, then run `1-Install-SpecieScan.command` again. Do not install Python 3.12/3.13. |
| “R was not found” | Install R 4.2.3 from Step 3, then run `1-Install-SpecieScan.command` again. |
| Setup seems stuck | It is usually compiling/downloading R packages. Wait up to 30 minutes. Keep the window open. |
| Setup fails | Open `setup_log.txt` in the SpecieScan folder and send it to the developer. |
| Browser does not open | Open your browser and type the address shown in the Terminal window, e.g. `http://127.0.0.1:8080`. |
| “Address already in use” / port 8080 busy | Close the other app using that port, or just restart with `2-Start-SpecieScan.command` — it automatically picks 8081, 8082, etc. |
| The page looks plain or charts are empty | Check your internet connection: the page loads chart and styling libraries from the internet. |
| I moved the folder and it stopped working | Move it back to the Desktop. If it still fails, run `1-Install-SpecieScan.command` again. |
| Old page still shows after an update | In the browser press **Command + Shift + R** to reload without the cache. |

---

## Frequently asked questions

**Are my files uploaded to the internet?**
No. The application runs locally on your Mac. Your `.mzML` files stay on your computer. Only the page styling/chart libraries are downloaded from the internet.

**Where are my uploaded files?**
In the `static/uploads` folder inside the SpecieScan folder. They are deleted every time the application starts, so export your results before closing.

**Do I need an internet connection?**
Yes during installation. While using the application, the interface loads Bootstrap, Plotly and Font Awesome from the internet, so charts and styling need a connection.

**Can I use Windows?**
This guide is macOS-only. Ask the developer for the Windows instructions.

**Can several people use one installation?**
Each person should have their own copy of the folder on their own Mac.

---

## Uninstalling

1. Quit SpecieScan (close the Terminal window).
2. Move the SpecieScan folder to the **Trash**.
3. Optional: uninstall Python and R with their own uninstallers if you no longer need them.

---

## Need help?

- Web application DOI: [10.5281/zenodo.23495280](https://doi.org/10.5281/zenodo.23495280)
- Underlying method: Végh, E. I. & Douka, K. (2024). *Bioinformatics*, 40(2), 1–12. <https://doi.org/10.1093/bioinformatics/btae054>
- Email: mesve3@gmail.com
