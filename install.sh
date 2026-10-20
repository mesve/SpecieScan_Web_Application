#!/bin/bash
# SpecieScan Installation Script

echo "🧬 SpecieScan Web Application Installer"
echo "========================================"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.7 or higher."
    exit 1
fi

echo "✓ Python 3 found"

# Check pip
if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
    echo "❌ pip is not installed. Please install pip."
    exit 1
fi

echo "✓ pip found"

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✓ Python dependencies installed successfully"
else
    echo "❌ Failed to install Python dependencies"
    exit 1
fi

# Check for R
if command -v R &> /dev/null; then
    echo "✓ R found"
    
    # Check R packages
    echo "📦 Checking R packages..."
    R --slave -e "
    if (!require('MALDIquant', quietly = TRUE)) {
        cat('MALDIquant not found. Installing...\n')
        install.packages('MALDIquant', repos='https://cran.r-project.org')
    }
    if (!require('MALDIquantForeign', quietly = TRUE)) {
        cat('MALDIquantForeign not found. Installing...\n')
        install.packages('MALDIquantForeign', repos='https://cran.r-project.org')
    }
    if (!require('mzR', quietly = TRUE)) {
        cat('mzR not found. Installing...\n')
        if (!requireNamespace('BiocManager', quietly = TRUE)) install.packages('BiocManager', repos='https://cran.r-project.org')
        BiocManager::install('mzR', ask = FALSE, update = FALSE)
    }
    cat('✓ R packages installed successfully\n')
    "
    
    if [ $? -eq 0 ]; then
        echo "✓ R packages are ready"
    else
        echo "⚠️  Warning: R packages may not be installed correctly"
        echo "   You can install them manually in R:"
        echo "   install.packages(c('MALDIquant', 'MALDIquantForeign'))"
    fi
else
    echo "⚠️  R not found. SpecieScan requires R for real spectra processing."
    echo "   Install R from: https://www.r-project.org/ then re-run this script."
fi

# Make CLI script executable
chmod +x specie_scan

echo ""
echo "🎉 Installation complete!"
echo ""
echo "🚀 To start the application:"
echo "   ./specie_scan"
echo ""
echo "📚 For more options:"
echo "   ./specie_scan --help"
echo ""
echo "🌐 The application will open in your default web browser"
echo "   or navigate to http://localhost:8080"