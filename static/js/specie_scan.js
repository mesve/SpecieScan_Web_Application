/**
 * SpecieScan Web Application JavaScript
 * Handles workflow navigation, API communication, and real-time updates
 */

// Iterative min/max: Math.min(...arr) throws "Maximum call stack size
// exceeded" on the ~200k-point mass/intensity arrays returned by the API.
function arrayMin(arr) {
    let m = Infinity;
    for (let i = 0; i < arr.length; i++) {
        if (arr[i] < m) m = arr[i];
    }
    return m;
}

function arrayMax(arr) {
    let m = -Infinity;
    for (let i = 0; i < arr.length; i++) {
        if (arr[i] > m) m = arr[i];
    }
    return m;
}

// Chart palette: light cream panels with dark-green ink, matching the UI.
const THEME = {
    bg: '#F4F9F1',
    text: '#164A41',
    grid: '#C9DEC1',
    line: '#4D774E',
    accent: '#164A41',
    highlight: '#9DC88D',
    threshold: '#B7791F',
    danger: '#9B3B3B',
    success: '#2F7D5E',
    muted: '#8AAE7E',
    legendBg: 'rgba(244, 249, 241, 0.9)'
};

class SpecieScanApp {
    constructor() {
        this.currentStep = 1;
        this.totalSteps = 9;
        this.state = {
            uploadedFiles: [],
            processingData: {},
            sessionId: null
        };
        this.spectraData = null;
        this.currentSpectrumIndex = 0;
        this.currentPeakIndex = 0;
        this.currentSNRSpectrumIndex = 0;  // For Step 5 navigation
        this.currentPeaksSpectrumIndex = 0;  // For Step 6 navigation
        this.stateLoaded = false;
        this.loadingTimeout = null;
        this.step2Promise = null;
        
        this.initializeApp();
    }

    async initializeApp() {
        console.log('Initializing SpecieScan Web Application...');
        
        // Wait for state to load before binding events
        await this.loadState();
        this.stateLoaded = true;
        
        // Now bind events
        this.bindEvents();
        
        // Set initial step
        this.showStep(this.currentStep);
        this.updateProgress();
        this.updateNavigation();
        
        console.log('App initialized successfully');
        console.log('Current state:', this.state);
    }

    bindEvents() {
        // Navigation buttons
        const nextBtn = document.getElementById('next-btn');
        const prevBtn = document.getElementById('previous-btn');
        const resetBtn = document.getElementById('reset-btn');
        
        if (nextBtn) nextBtn.addEventListener('click', () => this.nextStep());
        if (prevBtn) prevBtn.addEventListener('click', () => this.previousStep());
        if (resetBtn) resetBtn.addEventListener('click', () => this.resetWorkflow());
        
        // File upload
        const uploadForm = document.getElementById('upload-form');
        if (uploadForm) {
            uploadForm.addEventListener('submit', (e) => this.handleFileUpload(e));
        }
        
        // Spectrum navigation (Step 2)
        const prevSpectrumBtn = document.getElementById('prev-spectrum');
        const nextSpectrumBtn = document.getElementById('next-spectrum');
        
        if (prevSpectrumBtn) prevSpectrumBtn.addEventListener('click', () => this.previousSpectrum());
        if (nextSpectrumBtn) nextSpectrumBtn.addEventListener('click', () => this.nextSpectrum());
        
        // SNR spectrum navigation (Step 5)
        const prevSNRSpectrumBtn = document.getElementById('prev-snr-spectrum');
        const nextSNRSpectrumBtn = document.getElementById('next-snr-spectrum');
        
        if (prevSNRSpectrumBtn) prevSNRSpectrumBtn.addEventListener('click', () => this.previousSNRSpectrum());
        if (nextSNRSpectrumBtn) nextSNRSpectrumBtn.addEventListener('click', () => this.nextSNRSpectrum());
        
        // Peak spectrum navigation (Step 6) - navigate through different spectra showing their peaks
        const prevPeaksSpectrumBtn = document.getElementById('prev-peaks-spectrum');
        const nextPeaksSpectrumBtn = document.getElementById('next-peaks-spectrum');
        
        if (prevPeaksSpectrumBtn) prevPeaksSpectrumBtn.addEventListener('click', () => this.previousPeaksSpectrum());
        if (nextPeaksSpectrumBtn) nextPeaksSpectrumBtn.addEventListener('click', () => this.nextPeaksSpectrum());
        
        // Parameter controls
        const snrValue = document.getElementById('snr-value');
        const minPeaks = document.getElementById('min-peaks');
        const maxPeaks = document.getElementById('max-peaks');
        
        if (snrValue) snrValue.addEventListener('change', () => this.updateSNRPlot());
        if (minPeaks) minPeaks.addEventListener('input', (e) => {
            const display = document.getElementById('min-peaks-value');
            if (display) display.textContent = e.target.value;
        });
        if (maxPeaks) maxPeaks.addEventListener('input', (e) => {
            const display = document.getElementById('max-peaks-value');
            if (display) display.textContent = e.target.value;
        });
    }

    async loadState() {
        try {
            const response = await fetch('/api/state');
            const state = await response.json();
            
            console.log('Loaded state from server:', state);
            
            // Merge server state with local defaults to ensure all properties exist
            this.state = {
                ...this.state,
                ...state,
                processingData: state.processing_data || {},
                uploadedFiles: state.uploaded_files || []
            };
            
            this.currentStep = state.current_step || 1;
            
            this.showStep(this.currentStep);
            this.updateProgress();
        } catch (error) {
            console.error('Error loading state:', error);
            // Start fresh if state loading fails
            this.currentStep = 1;
            this.state = {
                uploadedFiles: [],
                processingData: {},
                sessionId: null
            };
        }
    }

    showStep(stepNumber) {
        // Hide all steps
        for (let i = 1; i <= this.totalSteps; i++) {
            const stepElement = document.getElementById(`step${i}`);
            if (stepElement) {
                stepElement.style.display = 'none';
            }
        }
        
        // Show current step
        const currentStepElement = document.getElementById(`step${stepNumber}`);
        if (currentStepElement) {
            currentStepElement.style.display = 'block';
        }
        
        // Update title
        const titleElement = document.getElementById('current-step-title');
        if (titleElement && window.stepTitles[stepNumber]) {
            titleElement.textContent = `Step ${stepNumber}: ${window.stepTitles[stepNumber]}`;
        }
        
        // Update sidebar
        this.updateSidebar(stepNumber);
        
        // Step-specific initialization
        if (stepNumber === 2) {
            // Process spectra on entry and show the real data
            setTimeout(() => this.enterStep2(), 100);
        } else if (stepNumber === 5) {
            // Load SNR plot for first spectrum when entering step 5
            this.currentSNRSpectrumIndex = 0;
            setTimeout(() => {
                this.updateSNRPlot();
                this.updateSNRCounter();
            }, 100);
        } else if (stepNumber === 6) {
            // Load peaks for first spectrum when entering step 6
            this.currentPeaksSpectrumIndex = 0;
            setTimeout(() => {
                if (this.state.processingData?.step_6_data?.status === 'completed') {
                    this.loadPeaksForSpectrum(0);
                } else {
                    this.showPeaksPrompt();
                }
            }, 100);
        } else if (stepNumber === 7) {
            // Load histogram when entering step 7
            setTimeout(() => this.updateHistogram(), 100);
        }
    }

    async enterStep2() {
        const files = this.state.uploadedFiles || [];

        if (files.length === 0) {
            this.showSpectrumError(
                'No Files Uploaded',
                'Please upload at least one .mzML file in Step 1 first.'
            );
            return;
        }

        const step2Data = this.state.processingData?.step_2_data;
        if (step2Data && step2Data.status === 'completed') {
            await this.loadSpectrumData(this.currentSpectrumIndex || 0);
            return;
        }
        if (step2Data && step2Data.status === 'error') {
            this.showSpectrumError('Could Not Load Spectra', step2Data.message || 'Unknown error', true);
            return;
        }

        await this.ensureStep2Processed();
    }

    async ensureStep2Processed() {
        if (this.step2Promise) {
            return this.step2Promise;
        }

        this.step2Promise = (async () => {
            try {
                await this.processCurrentStep();
                const step2Data = this.state.processingData?.step_2_data;
                if (step2Data && step2Data.status === 'completed') {
                    this.currentSpectrumIndex = 0;
                    await this.loadSpectrumData(0);
                } else {
                    this.showSpectrumError(
                        'Could Not Load Spectra',
                        step2Data?.message || 'The spectra could not be loaded from R.',
                        true
                    );
                }
            } catch (error) {
                console.error('Step 2 processing failed:', error);
                this.showSpectrumError('Could Not Load Spectra', error.message, true);
            } finally {
                this.step2Promise = null;
            }
        })();

        return this.step2Promise;
    }

    showSpectrumError(title, message, showRetry = false) {
        const plotDiv = document.getElementById('spectrum-plot');
        const dataSourceDiv = document.getElementById('spectrum-data-source');
        const counterDiv = document.getElementById('spectrum-counter');

        if (dataSourceDiv) {
            dataSourceDiv.className = 'badge bg-danger';
            dataSourceDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error';
        }
        if (counterDiv) {
            counterDiv.textContent = `${this.state.uploadedFiles?.length || 0} files uploaded`;
        }

        if (plotDiv) {
            plotDiv.innerHTML = `
                <div class="d-flex flex-column align-items-center justify-content-center" style="height: 500px;">
                    <div class="alert alert-danger text-center" style="max-width: 650px;">
                        <h5><i class="fas fa-exclamation-triangle"></i> ${title}</h5>
                        <p class="mb-3">${message}</p>
                        ${showRetry ? '<button class="btn btn-danger" onclick="window.app.retryStep2()"><i class="fas fa-redo"></i> Retry</button>' : ''}
                    </div>
                </div>
            `;
        }
    }

    retryStep2() {
        if (this.state.processingData) {
            delete this.state.processingData.step_2_data;
            delete this.state.processingData.step_2_status;
        }
        this.ensureStep2Processed();
    }

    showPeaksPrompt() {
        const plotDiv = document.getElementById('peaks-plot');
        if (!plotDiv) return;
        plotDiv.innerHTML = `
            <div class="d-flex flex-column align-items-center justify-content-center" style="height: 500px;">
                <div class="alert alert-info text-center" style="max-width: 600px;">
                    <h5><i class="fas fa-info-circle"></i> Peaks Not Detected Yet</h5>
                    <p class="mb-0">Click <strong>"Detect Peaks"</strong> to run peak picking on the pre-processed spectra.</p>
                </div>
            </div>
        `;
    }

    showPeakError(message) {
        const plotDiv = document.getElementById('peaks-plot');
        if (!plotDiv) return;
        plotDiv.innerHTML = `
            <div class="d-flex flex-column align-items-center justify-content-center" style="height: 500px;">
                <div class="alert alert-danger text-center" style="max-width: 600px;">
                    <h5><i class="fas fa-exclamation-triangle"></i> Could Not Load Peaks</h5>
                    <p class="mb-0">${message}</p>
                </div>
            </div>
        `;
    }

    updateSidebar(currentStep) {
        document.querySelectorAll('.step-link').forEach((link, index) => {
            const step = index + 1;
            const badge = link.querySelector('.step-number');
            
            if (badge) {
                badge.className = 'step-number badge';
            }
            
            link.classList.toggle('active', step === currentStep);
        });
    }

    updateProgress() {
        const progressBar = document.querySelector('.progress-bar');
        const progressPercent = (this.currentStep / this.totalSteps) * 100;
        
        if (progressBar) {
            progressBar.style.width = `${progressPercent}%`;
            progressBar.setAttribute('aria-valuenow', this.currentStep);
            progressBar.textContent = `Step ${this.currentStep} of ${this.totalSteps}`;
        }
    }

    updateNavigation() {
        const prevBtn = document.getElementById('previous-btn');
        const nextBtn = document.getElementById('next-btn');
        
        if (prevBtn) {
            prevBtn.disabled = this.currentStep === 1;
        }
        
        if (nextBtn) {
            nextBtn.disabled = this.currentStep === this.totalSteps;
        }
    }

    async nextStep() {
        if (!this.stateLoaded) {
            console.warn('State not yet loaded, please wait...');
            this.showMessage('Please wait for the application to fully load...', 'warning');
            return;
        }
        
        if (this.currentStep < this.totalSteps) {
            // Validate before proceeding to next step
            const canProceed = await this.validateCurrentStep();
            if (!canProceed) {
                return;
            }
            
            // Step 1 upload is handled separately. Steps that were already
            // processed explicitly (e.g. via a button) are not re-run.
            if (this.currentStep !== 1) {
                const stepKey = `step_${this.currentStep}_data`;
                const alreadyDone = this.state.processingData?.[stepKey]?.status === 'completed';
                if (!alreadyDone) {
                    try {
                        if (this.currentStep === 2) {
                            // Shares the in-flight promise so spectra are not
                            // loaded twice if the user clicks Next quickly.
                            await this.ensureStep2Processed();
                            const step2Data = this.state.processingData?.step_2_data;
                            if (!step2Data || step2Data.status !== 'completed') {
                                return;
                            }
                        } else {
                            await this.processCurrentStep();
                        }
                    } catch (error) {
                        // Stop navigation if processing failed
                        console.error('Step processing failed:', error);
                        this.showMessage(`Step ${this.currentStep} failed: ${error.message}. Check console for details.`, 'danger');
                        return;
                    }
                }
            }
            
            this.currentStep++;
            this.showStep(this.currentStep);
            this.updateProgress();
            this.updateNavigation();
        }
    }

    async previousStep() {
        if (this.currentStep > 1) {
            this.currentStep--;
            this.showStep(this.currentStep);
            this.updateProgress();
            this.updateNavigation();
        }
    }
    
    async validateCurrentStep() {
        // Validate that we have files before proceeding past step 1
        if (this.currentStep === 1) {
            if (!this.state.uploadedFiles || this.state.uploadedFiles.length === 0) {
                this.showMessage('Please upload at least one .mzML file before proceeding', 'warning');
                return false;
            }
        }
        
        return true;
    }

    async processCurrentStep() {
        // Clear any existing loading timeout
        if (this.loadingTimeout) {
            clearTimeout(this.loadingTimeout);
        }
        
        try {
            // Ensure processingData exists
            if (!this.state.processingData) {
                this.state.processingData = {};
            }
            
            console.log(`Processing step ${this.currentStep}`);
            
            this.showLoading(`Processing Step ${this.currentStep}...`);
            
            // Loading 8 mzML files can take a while - only warn, never hide early
            this.loadingTimeout = setTimeout(() => {
                this.showMessage('Still processing ... this can take a moment for large mzML files.', 'info');
            }, 180000);
            
            const response = await fetch(`/api/step/${this.currentStep}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            // Check if response is ok
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Server error: ${response.status} - ${errorText}`);
            }
            
            const result = await response.json();
            console.log('Step result:', result);
            
            if (result.error) {
                throw new Error(result.error);
            }
            
            // Store result
            this.state.processingData[`step_${this.currentStep}_data`] = result;
            
            // Show success message
            if (result.status === 'completed') {
                this.showMessage(result.message || `Step ${this.currentStep} completed successfully`, 'success');
            }
            
        } catch (error) {
            console.error(`Error processing step ${this.currentStep}:`, error);
            this.showMessage(`Error in step ${this.currentStep}: ${error.message}`, 'danger');
            throw error;
        } finally {
            // Clear the timeout
            if (this.loadingTimeout) {
                clearTimeout(this.loadingTimeout);
                this.loadingTimeout = null;
            }
            this.hideLoading();
        }
    }

    async handleFileUpload(event) {
        event.preventDefault();
        
        const formData = new FormData();
        const fileInput = document.getElementById('file-input');
        const files = fileInput.files;
        
        if (files.length === 0) {
            this.showMessage('Please select files to upload', 'warning');
            return;
        }
        
        // Add files to form data
        for (let file of files) {
            formData.append('files', file);
        }
        
        try {
            this.showLoading('Uploading files...');
            
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });
            
            // Check if response is ok
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Upload failed: ${response.status} - ${errorText}`);
            }
            
            const result = await response.json();
            
            if (result.error) {
                throw new Error(result.error);
            }
            
            this.state.uploadedFiles = result.files;
            if (!this.state.processingData) {
                this.state.processingData = {};
            }
            this.updateFileList(result.files);
            this.showMessage(`Successfully uploaded ${result.count} files`, 'success');
            
        } catch (error) {
            console.error('Upload error:', error);
            this.showMessage(`Upload failed: ${error.message}`, 'danger');
        } finally {
            this.hideLoading();
        }
    }

    updateFileList(files) {
        const fileList = document.getElementById('file-list');
        if (!fileList) return;
        
        if (files.length === 0) {
            fileList.innerHTML = '<p class="text-muted" id="no-files-message">No files uploaded yet.</p>';
            return;
        }
        
        fileList.innerHTML = files.map(file => `
            <div class="file-item alert alert-success">
                <i class="fas fa-file"></i> ${file.name}
                <span class="text-muted">(${(file.size / 1024 / 1024).toFixed(2)} MB)</span>
            </div>
        `).join('');
        
        // Add clear button if not present
        const cardHeader = fileList.closest('.card')?.querySelector('.card-header');
        if (cardHeader && !cardHeader.querySelector('.btn-outline-danger')) {
            const clearBtn = document.createElement('button');
            clearBtn.className = 'btn btn-sm btn-outline-danger';
            clearBtn.innerHTML = '<i class="fas fa-trash"></i> Clear All';
            clearBtn.onclick = () => window.clearFiles();
            cardHeader.appendChild(clearBtn);
        }
    }

    showLoading(message = 'Processing...') {
        const modal = document.getElementById('loadingModal');
        const messageElement = document.getElementById('loading-message');
        
        if (messageElement) {
            messageElement.textContent = message;
        }
        
        if (modal) {
            // Remove any existing modal backdrops first
            const existingBackdrops = document.querySelectorAll('.modal-backdrop');
            existingBackdrops.forEach(backdrop => backdrop.remove());
            
            // Show modal
            modal.style.display = 'block';
            modal.classList.add('show');
            document.body.classList.add('modal-open');
            
            // Add backdrop manually if not present
            if (!document.querySelector('.modal-backdrop')) {
                const backdrop = document.createElement('div');
                backdrop.className = 'modal-backdrop fade show';
                document.body.appendChild(backdrop);
            }
        }
    }

    hideLoading() {
        const modal = document.getElementById('loadingModal');
        if (modal) {
            modal.style.display = 'none';
            modal.classList.remove('show');
            document.body.classList.remove('modal-open');
            
            // Remove backdrop
            const backdrops = document.querySelectorAll('.modal-backdrop');
            backdrops.forEach(backdrop => backdrop.remove());
        }
    }

    showMessage(message, type = 'info') {
        const container = document.getElementById('status-container');
        if (!container) return;
        
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show status-message`;
        alertDiv.style.marginTop = '10px';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        container.appendChild(alertDiv);
        
        // Auto-remove after 8 seconds
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 8000);
    }

    async resetWorkflow() {
        if (!confirm('Are you sure you want to reset the entire workflow? All data will be lost.')) {
            return;
        }
        
        try {
            this.showLoading('Resetting workflow...');
            
            const response = await fetch('/reset', { method: 'POST' });
            
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Reset failed: ${response.status}`);
            }
            
            const result = await response.json();
            
            if (result.success) {
                this.currentStep = 1;
                this.state = result.state;
                this.spectraData = null;
                this.currentSpectrumIndex = 0;
                this.currentPeakIndex = 0;
                
                this.showStep(1);
                this.updateProgress();
                this.updateNavigation();
                this.showMessage('Workflow reset successfully', 'success');
                
                // Reload page after a short delay
                setTimeout(() => location.reload(), 1500);
            }
        } catch (error) {
            console.error('Reset error:', error);
            this.showMessage('Error resetting workflow: ' + error.message, 'danger');
        } finally {
            this.hideLoading();
        }
    }

    // Spectrum data loading and visualization
    async loadSpectrumData(index) {
        try {
            this.showLoading('Loading spectrum data...');
            
            const response = await fetch(`/api/spectra/${index}`);
            
            if (!response.ok) {
                throw new Error(`Failed to load spectrum: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.error) {
                console.error('API Error:', data.error);
                if (data.hint) {
                    console.error('Hint:', data.hint);
                }
                throw new Error(data.error);
            }
            
            // Debug logging
            if (data.success && data.mass && data.mass.length > 0) {
                const sourceIcon = data.source === 'R' ? '✓' : '⚠';
                const sourceText = data.source === 'R' ? 'REAL R data' : `${data.source} data`;
                console.log(`${sourceIcon} Received ${sourceText} from API: ${data.metadata?.filename || 'Unknown'}`);
                console.log(`  Mass range: ${arrayMin(data.mass).toFixed(1)} - ${arrayMax(data.mass).toFixed(1)}, ${data.mass.length} points`);
            } else {
                console.warn(`⚠ Received unexpected data format:`, data);
            }
            
            this.spectraData = data;
            this.currentSpectrumIndex = index;
            this.plotSpectrum();
            
        } catch (error) {
            console.error('Error loading spectrum:', error);
            this.showSpectrumError('Could Not Load Spectrum', error.message, false);
        } finally {
            this.hideLoading();
        }
    }
    
    async loadPeakData(index) {
        try {
            this.showLoading('Loading peak data...');
            
            const response = await fetch(`/api/peaks/${index}`);
            
            if (!response.ok) {
                throw new Error(`Failed to load peaks: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }
            
            this.peaksData = data;
            this.currentPeakIndex = index;
            this.plotPeaksForSpectrum(data, index);
            
        } catch (error) {
            console.error('Error loading peaks:', error);
            this.showPeakError(error.message);
        } finally {
            this.hideLoading();
        }
    }

    // Spectrum navigation methods
    previousSpectrum() {
        const totalFiles = this.state.uploadedFiles?.length || (this.spectraData?.total || 1);
        if (this.currentSpectrumIndex > 0) {
            this.currentSpectrumIndex--;
            this.loadSpectrumData(this.currentSpectrumIndex);
        }
    }

    nextSpectrum() {
        const totalFiles = this.state.uploadedFiles?.length || (this.spectraData?.total || 1);
        if (this.currentSpectrumIndex < totalFiles - 1) {
            this.currentSpectrumIndex++;
            this.loadSpectrumData(this.currentSpectrumIndex);
        }
    }

    previousPeaks() {
        const totalFiles = this.state.uploadedFiles?.length || (this.peakData?.total || 1);
        if (this.currentPeakIndex > 0) {
            this.currentPeakIndex--;
            this.loadPeakData(this.currentPeakIndex);
        }
    }

    nextPeaks() {
        const totalFiles = this.state.uploadedFiles?.length || (this.peakData?.total || 1);
        if (this.currentPeakIndex < totalFiles - 1) {
            this.currentPeakIndex++;
            this.loadPeakData(this.currentPeakIndex);
        }
    }

    // SNR Spectrum navigation methods (Step 5)
    previousSNRSpectrum() {
        const totalFiles = this.state.uploadedFiles?.length || 1;
        if (this.currentSNRSpectrumIndex > 0) {
            this.currentSNRSpectrumIndex--;
            this.updateSNRPlot();
            this.updateSNRCounter();
        }
    }

    nextSNRSpectrum() {
        const totalFiles = this.state.uploadedFiles?.length || 1;
        if (this.currentSNRSpectrumIndex < totalFiles - 1) {
            this.currentSNRSpectrumIndex++;
            this.updateSNRPlot();
            this.updateSNRCounter();
        }
    }

    updateSNRCounter() {
        const counterDiv = document.getElementById('snr-spectrum-counter');
        const filenameDiv = document.getElementById('snr-spectrum-filename');
        const totalFiles = this.state.uploadedFiles?.length || 1;
        
        if (counterDiv) {
            counterDiv.textContent = `Spectrum ${this.currentSNRSpectrumIndex + 1} of ${totalFiles}`;
        }
        
        if (filenameDiv && this.state.uploadedFiles[this.currentSNRSpectrumIndex]) {
            const filename = this.state.uploadedFiles[this.currentSNRSpectrumIndex].name;
            filenameDiv.innerHTML = `<small>Viewing SNR for: <strong>${filename}</strong></small>`;
        }
    }

    // Peaks Spectrum navigation methods (Step 6) - navigate through different spectra
    previousPeaksSpectrum() {
        const totalFiles = this.state.uploadedFiles?.length || 1;
        if (this.currentPeaksSpectrumIndex > 0) {
            this.currentPeaksSpectrumIndex--;
            this.loadPeaksForSpectrum(this.currentPeaksSpectrumIndex);
        }
    }

    nextPeaksSpectrum() {
        const totalFiles = this.state.uploadedFiles?.length || 1;
        if (this.currentPeaksSpectrumIndex < totalFiles - 1) {
            this.currentPeaksSpectrumIndex++;
            this.loadPeaksForSpectrum(this.currentPeaksSpectrumIndex);
        }
    }

    async loadPeaksForSpectrum(index) {
        this.showLoading(`Loading peaks for spectrum ${index + 1}...`);
        
        try {
            const response = await fetch(`/api/peaks/${index}`);
            
            if (!response.ok) {
                throw new Error(`Failed to load peaks: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.error) {
                this.showPeakError(data.error);
                return;
            }
            
            this.peaksData = data;
            this.currentPeaksSpectrumIndex = index;
            this.plotPeaksForSpectrum(data, index);
            
        } catch (error) {
            console.error('Error loading peaks:', error);
            this.showPeakError(error.message);
        } finally {
            this.hideLoading();
        }
    }

    plotPeaksForSpectrum(data, index) {
        const plotDiv = document.getElementById('peaks-plot');
        const counterDiv = document.getElementById('peaks-spectrum-counter');
        const filenameDiv = document.getElementById('peaks-spectrum-filename');
        
        if (!plotDiv) return;
        
        if (!data || !data.peak_mass) {
            this.showPeakError('No peak data available for this spectrum.');
            return;
        }
        
        const totalFiles = this.state.uploadedFiles?.length || 1;
        const filename = this.state.uploadedFiles[index]?.name || `Spectrum ${index + 1}`;
        
        if (counterDiv) {
            counterDiv.textContent = `Spectrum ${index + 1} of ${totalFiles}`;
        }
        
        if (filenameDiv) {
            filenameDiv.innerHTML = `<small>Viewing peaks for: <strong>${filename}</strong></small>`;
        }
        
        const peakMass = data.peak_mass;
        const peakIntensity = data.peak_intensity;
        const mass = data.spectrum_mass;
        const intensity = data.spectrum_intensity;
        
        const spectrumTrace = {
            x: mass,
            y: intensity,
            mode: 'lines',
            type: 'scatter',
            name: 'Spectrum',
            line: { color: THEME.line, width: 1 }
        };
        
        const peaksTrace = {
            x: peakMass,
            y: peakIntensity,
            mode: 'markers',
            type: 'scatter',
            name: 'Peaks',
            marker: { color: THEME.accent, size: 8, symbol: 'diamond' }
        };
        
        const layout = {
            title: `${filename} - Detected Peaks`,
            xaxis: { title: 'Mass (m/z)', showgrid: true, gridcolor: THEME.grid },
            yaxis: { title: 'Intensity', showgrid: true, gridcolor: THEME.grid },
            plot_bgcolor: THEME.bg,
            paper_bgcolor: THEME.bg,
            font: { color: THEME.text },
            showlegend: true,
            margin: { t: 40, r: 20, b: 40, l: 60 }
        };
        
        Plotly.newPlot('peaks-plot', [spectrumTrace, peaksTrace], layout, {responsive: true});
    }

    // Plotting methods
    plotSpectrum() {
        const plotDiv = document.getElementById('spectrum-plot');
        const counterDiv = document.getElementById('spectrum-counter');
        const filenameDiv = document.getElementById('spectrum-filename');
        const dataSourceDiv = document.getElementById('spectrum-data-source');
        
        if (!plotDiv) return;
        
        if (!this.spectraData || !this.spectraData.mass || !this.spectraData.intensity) {
            this.showSpectrumError('No Spectrum Data', 'The spectrum could not be displayed.');
            return;
        }
        
        const mass = this.spectraData.mass;
        const intensity = this.spectraData.intensity;
        const filename = this.spectraData.metadata?.filename || `Spectrum ${this.currentSpectrumIndex + 1}`;
        
        if (counterDiv) {
            counterDiv.textContent = `Spectrum ${this.spectraData.index + 1} of ${this.spectraData.total}`;
        }
        
        if (filenameDiv) {
            filenameDiv.innerHTML = `<i class="fas fa-file"></i> ${filename}`;
        }
        
        if (dataSourceDiv) {
            dataSourceDiv.className = 'badge bg-success';
            dataSourceDiv.innerHTML = '<i class="fas fa-check-circle"></i> R Data';
        }
        
        console.log(`✓ Plotting REAL R data: ${filename} (${mass.length} mass points)`);
        
        const trace = {
            x: mass,
            y: intensity,
            mode: 'lines',
            type: 'scatter',
            line: {
                color: THEME.line,
                width: 1
            },
            name: 'Intensity'
        };
        
        const layout = {
            title: filename,
            xaxis: {
                title: 'Mass (m/z)',
                showgrid: true,
                gridcolor: THEME.grid
            },
            yaxis: {
                title: 'Intensity',
                showgrid: true,
                gridcolor: THEME.grid
            },
            plot_bgcolor: THEME.bg,
            paper_bgcolor: THEME.bg,
            font: { color: THEME.text },
            margin: { t: 40, r: 20, b: 40, l: 60 }
        };
        
        Plotly.newPlot('spectrum-plot', [trace], layout, {responsive: true});
    }

    async updateSNRPlot() {
        const plotDiv = document.getElementById('snr-plot');
        if (!plotDiv) return;
        
        const snrValue = parseFloat(document.getElementById('snr-value')?.value) || 3.5;
        const index = this.currentSNRSpectrumIndex || 0;
        
        try {
            const response = await fetch(`/api/noise/${index}`);
            if (!response.ok) {
                throw new Error(`Failed to load noise data: ${response.status}`);
            }
            
            const data = await response.json();
            if (data.error) {
                throw new Error(data.error);
            }
            
            const mass = data.noise_mass;
            const noise = data.noise_intensity;
            
            const noiseTrace = {
                x: mass,
                y: noise,
                mode: 'lines',
                name: 'Estimated Noise',
                line: { color: THEME.muted, width: 2 }
            };
            
            const snr3Trace = {
                x: mass,
                y: noise.map(v => v * 3),
                mode: 'lines',
                name: 'SNR = 3',
                line: { color: THEME.threshold, width: 1.5, dash: 'dash' }
            };
            
            const snr5Trace = {
                x: mass,
                y: noise.map(v => v * 5),
                mode: 'lines',
                name: 'SNR = 5',
                line: { color: THEME.danger, width: 1.5, dash: 'dash' }
            };
            
            const thresholdTrace = {
                x: mass,
                y: noise.map(v => v * snrValue),
                mode: 'lines',
                name: `Current Threshold (SNR = ${snrValue})`,
                line: { color: THEME.accent, width: 3 }
            };
            
            const maxNoise = noise.length ? arrayMax(noise) : 0;
            const filename = data.filename || `Spectrum ${index + 1}`;
            
            const layout = {
                title: `Noise estimation - ${filename} (SNR = ${snrValue})`,
                xaxis: {
                    title: 'Mass (m/z)',
                    showgrid: true,
                    gridcolor: THEME.grid
                },
                yaxis: {
                    title: 'Intensity',
                    showgrid: true,
                    gridcolor: THEME.grid,
                    rangemode: 'tozero'
                },
                plot_bgcolor: THEME.bg,
                paper_bgcolor: THEME.bg,
            font: { color: THEME.text },
                showlegend: true,
                legend: {
                    x: 0.02,
                    y: 0.98,
                    bgcolor: THEME.legendBg
                },
                margin: { t: 40, r: 20, b: 40, l: 60 }
            };
            
            Plotly.newPlot('snr-plot', [noiseTrace, snr3Trace, snr5Trace, thresholdTrace], layout, {responsive: true});
            
        } catch (error) {
            console.error('Error loading noise data:', error);
            plotDiv.innerHTML = `
                <div class="d-flex align-items-center justify-content-center" style="height: 500px;">
                    <div class="alert alert-danger text-center" style="max-width: 600px;">
                        <h5><i class="fas fa-exclamation-triangle"></i> Could Not Load Noise Data</h5>
                        <p class="mb-0">${error.message}</p>
                    </div>
                </div>
            `;
        }
    }
    
    updateHistogram() {
        const plotDiv = document.getElementById('histogram-plot');
        if (!plotDiv) return;
        
        // Get peak counts from step 6 or step 7 data
        const step6Data = this.state.processingData?.step_6_data;
        const step7Data = this.state.processingData?.step_7_data;
        
        let peakCounts = [];
        let histogramTitle = 'Distribution of Peak Counts Across Spectra';
        
        if (step7Data && step7Data.peak_counts) {
            peakCounts = step7Data.peak_counts;
        } else if (step6Data && step6Data.peak_count) {
            peakCounts = step6Data.peak_count;
            histogramTitle += ' (From Step 6)';
        }
        
        if (!peakCounts || peakCounts.length === 0) {
            plotDiv.innerHTML = `
                <div class="d-flex align-items-center justify-content-center" style="height: 500px;">
                    <div class="alert alert-info text-center" style="max-width: 600px;">
                        <h5><i class="fas fa-info-circle"></i> No Peak Data Yet</h5>
                        <p class="mb-0">Run <strong>Step 6 (Peak Picking)</strong> first to analyse the peak distribution.</p>
                    </div>
                </div>
            `;
            return;
        }
        
        // Use 30 breaks like the R code: hist(x, breaks = 30)
        const numBins = Math.min(30, Math.max(10, Math.ceil(peakCounts.length / 2)));
        
        const trace = {
            x: peakCounts,
            type: 'histogram',
            nbinsx: numBins,
            marker: {
                color: THEME.line,
                line: {
                    color: THEME.accent,
                    width: 1
                }
            },
            name: 'Peak Count Distribution',
            opacity: 0.75
        };
        
        const layout = {
            title: histogramTitle,
            xaxis: {
                title: 'Number of Peaks',
                showgrid: true,
                gridcolor: THEME.grid,
                zeroline: false
            },
            yaxis: {
                title: 'Number of Spectra',
                showgrid: true,
                gridcolor: THEME.grid,
                zeroline: false
            },
            plot_bgcolor: THEME.bg,
            paper_bgcolor: THEME.bg,
            font: { color: THEME.text },
            margin: { t: 40, r: 20, b: 40, l: 60 },
            bargap: 0.1
        };
        
        Plotly.newPlot('histogram-plot', [trace], layout, {responsive: true});
        
        // Display stats
        const statsDiv = document.createElement('div');
        statsDiv.className = 'alert alert-info mt-3';
        statsDiv.innerHTML = `
            <strong>Statistics:</strong><br>
            Mean: ${(peakCounts.reduce((a, b) => a + b, 0) / peakCounts.length).toFixed(1)} | 
            Min: ${Math.min(...peakCounts)} | 
            Max: ${Math.max(...peakCounts)} | 
            Total Spectra: ${peakCounts.length}
        `;
        
        // Remove old stats if any
        const oldStats = plotDiv.parentElement.querySelector('.alert-info');
        if (oldStats) oldStats.remove();
        
        plotDiv.parentElement.appendChild(statsDiv);
    }
}

// Global function for clearing files
window.clearFiles = async function() {
    if (!confirm('Are you sure you want to clear all uploaded files?')) {
        return;
    }
    
    try {
        window.app.showLoading('Clearing files...');
        
        const response = await fetch('/clear-files', { method: 'POST' });
        
        if (!response.ok) {
            throw new Error(`Failed to clear files: ${response.status}`);
        }
        
        const result = await response.json();
        
        if (result.success) {
            window.app.state.uploadedFiles = [];
            window.app.spectraData = null;
            window.app.currentSpectrumIndex = 0;
            
            const fileList = document.getElementById('file-list');
            if (fileList) {
                fileList.innerHTML = '<p class="text-muted" id="no-files-message">No files uploaded yet.</p>';
            }
            
            const cardHeader = document.querySelector('#step1 .card-header');
            const clearBtn = cardHeader?.querySelector('.btn-outline-danger');
            if (clearBtn) clearBtn.remove();
            
            window.app.showMessage(`Cleared ${result.files_removed} files successfully`, 'success');
        }
    } catch (error) {
        console.error('Error clearing files:', error);
        window.app.showMessage('Error clearing files: ' + error.message, 'danger');
    } finally {
        window.app.hideLoading();
    }
};

// Global functions called from HTML
window.runQualityControl = async function() {
    console.log('Running quality control...');
    window.app.showLoading('Running quality control checks...');
    
    try {
        const response = await fetch('/api/step/3', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }
        
        const result = await response.json();
        
        if (result.error) {
            throw new Error(result.error);
        }
        
        window.app.hideLoading();
        window.app.showMessage(result.message || 'Quality control completed', 'success');
        window.app.state.processingData.step_3_data = result;
        
        let resultsHtml = `
            <div class="alert alert-${result.results?.qc_passed ? 'success' : 'warning'}">
                <h6><i class="fas fa-${result.results?.qc_passed ? 'check-circle' : 'exclamation-triangle'}"></i> Quality Control Results</h6>
                <p><strong>Status:</strong> ${result.results?.qc_passed ? 'PASSED' : 'CHECK REQUIRED'}</p>
                <p><strong>Empty Spectra:</strong> ${result.results?.has_empty ? 'Yes' : 'None detected'}</p>
                <p><strong>Regular Spectra:</strong> ${result.results?.all_regular ? 'All regular' : 'Some irregular'}</p>
                <p><strong>Spectra Count:</strong> ${result.results?.shape?.count || 'N/A'}</p>
                <p><strong>Avg Length:</strong> ${Math.round(result.results?.shape?.avg_length || 0)} points</p>
            </div>
        `;
        
        document.getElementById('qc-results').innerHTML = resultsHtml;
        
    } catch (error) {
        window.app.hideLoading();
        console.error('QC error:', error);
        window.app.showMessage(`QC error: ${error.message}`, 'danger');
        
        document.getElementById('qc-results').innerHTML = `
            <div class="alert alert-danger">
                <h6><i class="fas fa-exclamation-triangle"></i> Quality Control Failed</h6>
                <p class="mb-0">Could not complete quality control. Error: ${error.message}</p>
            </div>
        `;
    }
};

window.runPreprocessing = async function() {
    console.log('Running preprocessing...');
    window.app.showLoading('Applying preprocessing steps...');
    
    try {
        const response = await fetch('/api/step/4', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }
        
        const result = await response.json();
        
        if (result.error) {
            throw new Error(result.error);
        }
        
        window.app.hideLoading();
        window.app.showMessage(result.message || 'Preprocessing completed', 'success');
        window.app.state.processingData.step_4_data = result;
        
    } catch (error) {
        window.app.hideLoading();
        console.error('Preprocessing error:', error);
        window.app.showMessage(`Preprocessing error: ${error.message}`, 'danger');
    }
};

window.updateSNR = function() {
    console.log('Updating SNR...');
    window.app.updateSNRPlot();
};

window.runPeakPicking = async function() {
    console.log('Running peak picking...');
    window.app.showLoading('Detecting and deisotoping peaks...');
    
    const params = {
        snr: parseFloat(document.getElementById('peak-snr')?.value) || 3.5,
        min_cor: parseFloat(document.getElementById('min-cor')?.value) || 0.95,
        tolerance: parseFloat(document.getElementById('tolerance')?.value) || 1e-4,
        distance: parseFloat(document.getElementById('distance')?.value) || 1.00235,
        size_range: document.getElementById('size')?.value || '2:10'
    };
    
    try {
        const response = await fetch('/api/step/6', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });
        
        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }
        
        const result = await response.json();
        
        if (result.error) {
            throw new Error(result.error);
        }
        
        window.app.showMessage(result.message || 'Peak picking completed', 'success');
        window.app.state.processingData.step_6_data = result;
        
        // Update peak display with the real detected peaks
        window.app.currentPeaksSpectrumIndex = 0;
        await window.app.loadPeaksForSpectrum(0);
        
    } catch (error) {
        console.error('Peak picking error:', error);
        window.app.showMessage(`Peak picking error: ${error.message}`, 'danger');
        window.app.showPeakError(error.message);
    } finally {
        window.app.hideLoading();
    }
};

window.applyFilters = async function() {
    console.log('Applying filters...');
    window.app.showLoading('Removing outlier spectra...');
    
    const minPeaks = parseInt(document.getElementById('min-peaks')?.value) || 45;
    const maxPeaks = parseInt(document.getElementById('max-peaks')?.value) || 105;
    
    try {
        // Get current peak counts from step 6 or 7 data
        const step6Data = window.app.state.processingData?.step_6_data;
        const step7Data = window.app.state.processingData?.step_7_data;
        
        let originalCounts = [];
        if (step7Data && step7Data.peak_counts) {
            originalCounts = step7Data.peak_counts;
        } else if (step6Data && step6Data.peak_count) {
            originalCounts = step6Data.peak_count;
        }
        
        if (!originalCounts || originalCounts.length === 0) {
            window.app.hideLoading();
            window.app.showMessage('No peak data available. Please run Step 6 (Peak Picking) first.', 'warning');
            return;
        }
        
        // Filter spectra within the min-max range
        const filteredCounts = originalCounts.filter(count => count >= minPeaks && count <= maxPeaks);
        const removedCount = originalCounts.length - filteredCounts.length;
        
        // Store filtered data in state
        if (!window.app.state.processingData) {
            window.app.state.processingData = {};
        }
        window.app.state.processingData.step_7_filtered = {
            original_counts: originalCounts,
            filtered_counts: filteredCounts,
            min_peaks: minPeaks,
            max_peaks: maxPeaks,
            removed: removedCount
        };
        
        window.app.hideLoading();
        
        if (removedCount > 0) {
            window.app.showMessage(`Removed ${removedCount} outlier spectra. ${filteredCounts.length} spectra remaining.`, 'success');
        } else {
            window.app.showMessage(`No spectra removed. All ${filteredCounts.length} spectra are within range ${minPeaks}-${maxPeaks}.`, 'info');
        }
        
        // Update histogram with filtered data
        updateHistogramWithFilteredData(filteredCounts, minPeaks, maxPeaks, removedCount);
        
    } catch (error) {
        window.app.hideLoading();
        console.error('Filter error:', error);
        window.app.showMessage(`Error applying filters: ${error.message}`, 'danger');
    }
};

function updateHistogramWithFilteredData(filteredCounts, minPeaks, maxPeaks, removedCount) {
    const plotDiv = document.getElementById('histogram-plot');
    if (!plotDiv) return;
    
    // Use 30 breaks like the R code
    const numBins = Math.min(30, Math.max(10, Math.ceil(filteredCounts.length / 2)));
    
    const trace = {
        x: filteredCounts,
        type: 'histogram',
        nbinsx: numBins,
        marker: {
            color: THEME.success, // Green for filtered data
            line: {
                color: THEME.accent,
                width: 1
            }
        },
        name: 'Filtered Peak Count Distribution',
        opacity: 0.75
    };
    
    // Add vertical lines for min and max thresholds
    const shapes = [
        {
            type: 'line',
            x0: minPeaks,
            x1: minPeaks,
            y0: 0,
            y1: 1,
            yref: 'paper',
            line: {
                color: THEME.danger,
                width: 2,
                dash: 'dash'
            }
        },
        {
            type: 'line',
            x0: maxPeaks,
            x1: maxPeaks,
            y0: 0,
            y1: 1,
            yref: 'paper',
            line: {
                color: THEME.danger,
                width: 2,
                dash: 'dash'
            }
        }
    ];
    
    const layout = {
        title: `Filtered Distribution: ${filteredCounts.length} spectra (Range: ${minPeaks}-${maxPeaks})`,
        xaxis: {
            title: 'Number of Peaks',
            showgrid: true,
            gridcolor: THEME.grid,
            zeroline: false
        },
        yaxis: {
            title: 'Number of Spectra',
            showgrid: true,
            gridcolor: THEME.grid,
            zeroline: false
        },
        plot_bgcolor: THEME.bg,
        paper_bgcolor: THEME.bg,
            font: { color: THEME.text },
        margin: { t: 40, r: 20, b: 40, l: 60 },
        bargap: 0.1,
        shapes: shapes,
        annotations: [
            {
                x: minPeaks,
                y: 1.05,
                yref: 'paper',
                text: `Min: ${minPeaks}`,
                showarrow: false,
                font: { color: THEME.danger, size: 12 }
            },
            {
                x: maxPeaks,
                y: 1.05,
                yref: 'paper',
                text: `Max: ${maxPeaks}`,
                showarrow: false,
                font: { color: THEME.danger, size: 12 }
            }
        ]
    };
    
    Plotly.newPlot('histogram-plot', [trace], layout, {responsive: true});
    
    // Display stats
    const statsDiv = document.createElement('div');
    statsDiv.className = 'alert alert-success mt-3';
    statsDiv.innerHTML = `
        <strong>Filter Results:</strong><br>
        Spectra Remaining: ${filteredCounts.length} | 
        Spectra Removed: ${removedCount} | 
        Range: ${minPeaks} - ${maxPeaks} peaks<br>
        Mean: ${(filteredCounts.reduce((a, b) => a + b, 0) / filteredCounts.length).toFixed(1)} | 
        Min: ${Math.min(...filteredCounts)} | 
        Max: ${Math.max(...filteredCounts)}
    `;
    
    // Remove old stats if any
    const oldStats = plotDiv.parentElement.querySelector('.alert-info, .alert-success');
    if (oldStats) oldStats.remove();
    
    plotDiv.parentElement.appendChild(statsDiv);
}

window.averageReplicates = async function() {
    console.log('Averaging replicates...');
    window.app.showLoading('Averaging technical replicates...');
    
    try {
        const response = await fetch('/api/step/8', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }
        
        const result = await response.json();
        
        if (result.error) {
            throw new Error(result.error);
        }
        
        window.app.hideLoading();
        window.app.showMessage(result.message || 'Averaging completed', 'success');
        window.app.state.processingData.step_8_data = result;
        
        const resultsDiv = document.getElementById('averaging-results');
        if (resultsDiv) {
            // Build sample groups display
            let groupsHtml = '';
            if (result.sample_groups && Object.keys(result.sample_groups).length > 0) {
                groupsHtml = '<div class="mt-3"><strong>Sample Groups:</strong><ul class="list-group mt-2">';
                for (const [sample, files] of Object.entries(result.sample_groups)) {
                    groupsHtml += `
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            <span><strong>${sample}</strong></span>
                            <span class="badge bg-primary rounded-pill">${files.length} replicates</span>
                        </li>
                        <li class="list-group-item bg-light">
                            <small class="text-muted">${files.join(', ')}</small>
                        </li>
                    `;
                }
                groupsHtml += '</ul></div>';
            } else if (result.groups_summary) {
                groupsHtml = '<div class="mt-3"><strong>Sample Groups:</strong><ul class="list-group mt-2">';
                result.groups_summary.forEach(group => {
                    groupsHtml += `<li class="list-group-item">${group}</li>`;
                });
                groupsHtml += '</ul></div>';
            }
            
            resultsDiv.innerHTML = `
                <div class="alert alert-success">
                    <h6><i class="fas fa-check-circle"></i> Averaging Results</h6>
                    <p><strong>${result.averaged_count || 0} unique samples</strong> created from ${result.original_count || 0} spectra</p>
                    <p class="mb-2">Files with the same name prefix (before '_') are technical replicates and have been averaged together.</p>
                    ${groupsHtml}
                </div>
            `;
        }
        
    } catch (error) {
        window.app.hideLoading();
        console.error('Averaging error:', error);
        window.app.showMessage(`Averaging error: ${error.message}`, 'danger');
    }
};

window.exportResults = function() {
    console.log('Exporting peak data...');
    window.app.showLoading('Generating peak data CSV...');
    
    // Download the real detected peaks generated by the backend
    fetch('/api/export/peaks')
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => {
                    throw new Error(err.error || `Export failed: ${response.status}`);
                }).catch(() => {
                    throw new Error(`Export failed: ${response.status}`);
                });
            }
            return response.blob();
        })
        .then(blob => {
            const link = document.createElement('a');
            const url = URL.createObjectURL(blob);
            link.setAttribute('href', url);
            link.setAttribute('download', `SpecieScan_Peaks_${new Date().toISOString().split('T')[0]}.csv`);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
            
            window.app.showMessage('Peak data exported successfully', 'success');
            
            const exportDiv = document.getElementById('export-status');
            if (exportDiv) {
                exportDiv.innerHTML = `
                    <div class="alert alert-success">
                        <i class="fas fa-check-circle"></i> Peak data exported successfully
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Export error:', error);
            window.app.showMessage(`Export error: ${error.message}`, 'danger');
            const exportDiv = document.getElementById('export-status');
            if (exportDiv) {
                exportDiv.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-exclamation-triangle"></i> ${error.message}
                    </div>
                `;
            }
        })
        .finally(() => {
            window.app.hideLoading();
        });
};

window.runPythonAnalysis = async function() {
    console.log('Running Python analysis...');
    window.app.showLoading('Running species identification for all samples...');
    
    const dbSelect = document.getElementById('reference-db');
    const selectedDb = dbSelect?.options[dbSelect.selectedIndex]?.text || 'Eurasia Mammals';
    
    try {
        // Call API to get species identification results for all samples
        const response = await fetch('/api/step/9', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }
        
        const result = await response.json();
        
        if (result.error) {
            throw new Error(result.error);
        }
        
        window.app.hideLoading();
        window.app.showMessage(result.message || 'Species identification completed', 'success');
        window.app.state.processingData.step_9_data = result;
        
        const resultsDiv = document.getElementById('python-results');
        if (resultsDiv) {
            displayAllSampleResults(result, selectedDb, resultsDiv);
        }
        
    } catch (error) {
        window.app.hideLoading();
        console.error('Species identification error:', error);
        window.app.showMessage(`Error: ${error.message}`, 'danger');
    }
};

function displayAllSampleResults(result, databaseName, resultsDiv) {
    const sampleResults = result.sample_results || {};
    const totalSamples = result.total_samples || Object.keys(sampleResults).length;
    
    let html = `
        <div class="alert alert-success mb-4">
            <h5><i class="fas fa-dna"></i> Species Identification Completed</h5>
            <p><strong>Reference Database:</strong> ${result.reference_database || databaseName}</p>
            <p><strong>Total Samples Analyzed:</strong> ${totalSamples}</p>
        </div>
        
        <div class="d-flex justify-content-between align-items-center mb-3">
            <h5>Results by Sample</h5>
            <button class="btn btn-success" onclick="exportResultsToCSV()">
                <i class="fas fa-file-csv"></i> Export All Results to CSV
            </button>
        </div>
    `;
    
    // Display each sample's results
    for (const [sampleName, sampleData] of Object.entries(sampleResults)) {
        const topMatches = sampleData.top_matches || [];
        const numReplicates = sampleData.num_replicates || sampleData.files?.length || 1;
        
        html += `
            <div class="card mb-3">
                <div class="card-header bg-primary text-white">
                    <h6 class="mb-0">
                        <i class="fas fa-flask"></i> Sample: ${sampleName}
                        <span class="badge bg-light text-primary ms-2">${numReplicates} replicates</span>
                    </h6>
                </div>
                <div class="card-body p-0">
                    <div class="table-responsive">
                        <table class="table table-striped table-hover mb-0">
                            <thead class="table-dark">
                                <tr>
                                    <th width="60">Rank</th>
                                    <th>ZooMS Taxon</th>
                                    <th>Species</th>
                                    <th>Family</th>
                                    <th>Order</th>
                                    <th>Match Score</th>
                                    <th>Matched / Total Peaks</th>
                                </tr>
                            </thead>
                            <tbody>
        `;
        
        topMatches.forEach((match, index) => {
            const correlationPercent = (match.correlation * 100).toFixed(1);
            const rowClass = index === 0 ? 'table-success' : '';
            const totalRef = match.total_reference_peaks || (match.reference_peaks ? match.reference_peaks.length : '');
            
            html += `
                <tr class="${rowClass}">
                    <td><strong>${match.rank}</strong></td>
                    <td><code>${match.ZooMS_taxon}</code></td>
                    <td><em>${match.species}</em></td>
                    <td>${match.family}</td>
                    <td>${match.order}</td>
                    <td>
                        <div class="progress" style="height: 20px;">
                            <div class="progress-bar ${index === 0 ? 'bg-success' : 'bg-info'}" 
                                 role="progressbar" 
                                 style="width: ${correlationPercent}%">
                                ${correlationPercent}%
                            </div>
                        </div>
                    </td>
                    <td>${match.matched_peaks} / ${totalRef}</td>
                </tr>
            `;
        });
        
        let contaminantsBlock = '';
        if (sampleData.contaminants && sampleData.contaminants.length > 0) {
            const items = sampleData.contaminants
                .map(c => `<li><strong>${c.contaminant}</strong> (${c.count} peak${c.count > 1 ? 's' : ''})</li>`)
                .join('');
            contaminantsBlock = `
                <div class="p-2 border-top">
                    <div class="alert alert-warning mb-0 py-2">
                        <strong><i class="fas fa-biohazard"></i> Potential contaminants detected:</strong>
                        <ul class="mb-0">${items}</ul>
                    </div>
                </div>
            `;
        }
        
        html += `
                            </tbody>
                        </table>
                    </div>
                    ${contaminantsBlock}
                    <div class="p-2 bg-light border-top">
                        <small class="text-muted">
                            <strong>Files:</strong> ${sampleData.files?.join(', ') || 'N/A'}
                            | <strong>Marker peaks in range:</strong> ${sampleData.marker_count ?? 'N/A'}
                        </small>
                    </div>
                </div>
            </div>
        `;
    }
    
    // Store results globally for CSV export
    window.speciesIdentificationResults = result;
    
    resultsDiv.innerHTML = html;
}

window.exportResultsToCSV = function() {
    const result = window.speciesIdentificationResults || window.app.state.processingData?.step_9_data;
    
    if (!result || !result.sample_results) {
        alert('No results available to export. Please run species identification first.');
        return;
    }
    
    // Generate CSV content in long format
    let csvContent = 'Sample,ZooMS_taxon,Species,Common_Name,Family,Order,Correlation,Matched_Peaks,Reference_Peaks,Rank,Num_Replicates\n';
    
    for (const [sampleName, sampleData] of Object.entries(result.sample_results)) {
        const numReplicates = sampleData.num_replicates || sampleData.files?.length || 1;
        const topMatches = sampleData.top_matches || [];
        
        topMatches.forEach(match => {
            const referencePeaks = match.reference_peaks ? match.reference_peaks.join(';') : '';
            csvContent += `${sampleName},${match.ZooMS_taxon},"${match.species}",${match.common_name},${match.family},${match.order},${match.correlation},${match.matched_peaks},"${referencePeaks}",${match.rank},${numReplicates}\n`;
        });
    }
    
    // Create and download the CSV file
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    
    link.setAttribute('href', url);
    link.setAttribute('download', `SpecieScan_Results_${new Date().toISOString().split('T')[0]}.csv`);
    link.style.visibility = 'hidden';
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    window.app.showMessage('Results exported to CSV successfully', 'success');
};

// Initialize the application when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    window.app = new SpecieScanApp();
});
