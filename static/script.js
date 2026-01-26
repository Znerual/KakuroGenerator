// Utility
function escapeHtml(text) {
    if (!text) return '';
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

const state = {
    puzzle: null,
    userGrid: [],
    selected: null,
    selectedCells: new Set(), // Set of "r,c" strings for multi-select
    rowNotes: [],    // Notes for each row (displayed on the left)
    colNotes: [],    // Notes for each column (displayed on top)
    cellNotes: {},   // Notes for cells: key = "r,c" or "r,c:r2,c2" for boundary notes
    editingNote: null, // { type: 'row'|'col'|'cell'|'boundary', key: string }
    showErrors: false,
    currentTab: 'started', // 'started' or 'solved'
    noteMode: false, // Toggle for note-taking mode
    gridBounds: null, // {minRow, maxRow, minCol, maxCol}
    notebook: '', // User's personal notes for this puzzle
    notebookOpen: false, // Whether notebook panel is visible
    rating: 0, // User's rating (0-5 stars)
    userComment: '', // User's comment about the puzzle
    theme: 'dark', // 'dark' or 'light'
    longPressTimer: null,
    isLongPressTriggered: false, // Tracks if timer finished
    isDragSelecting: false,      // Tracks if we are currently painting cells
    longPressDuration: 500,
    lastTouchedRC: null,        // To position numpad at the end
    lastTapTime: 0,
    lastTapRC: null,
    lastTouchTime: 0,
    touchStartX: 0,
    touchStartY: 0,
    // Auth state
    user: null, // Current logged in user
    accessToken: null,
    refreshToken: null,
    resendTimerInterval: null,
    resendCooldownSeconds: 60,
    // Analytics
    lastActionTime: Date.now(),
    puzzleQueue: [], // Queue of puzzles from the feed
    currentBatchDifficulty: null, // Track difficulty of current queue items
    leaderboardType: 'monthly', // 'monthly' or 'all-time'
    leaderboardData: [],
    info: { debug: false } // Application info from backend
};

const boardEl = document.getElementById('kakuro-board');
const btnGenerate = document.getElementById('btn-generate');
const btnCheck = document.getElementById('btn-check');
const btnSave = document.getElementById('btn-save');
const btnLibrary = document.getElementById('btn-library');
const libraryModal = document.getElementById('library-modal');
const closeModal = libraryModal.querySelector('.close');
const libraryList = document.getElementById('library-list');
const tabButtons = document.querySelectorAll('.tab-btn');

function init() {
    console.log('Init function called');
    const btnNoteMode = document.getElementById('btn-note-mode');
    const btnNotebook = document.getElementById('btn-notebook');
    const btnThemeToggle = document.getElementById('btn-theme-toggle');
    const btnMobileThemeToggle = document.getElementById('btn-mobile-theme-toggle');
    const btnDownloadBook = document.getElementById('btn-download-book');
    console.log('btnNoteMode:', btnNoteMode);

    btnGenerate.addEventListener('click', fetchPuzzle);
    btnCheck.addEventListener('click', checkPuzzle);
    btnSave.addEventListener('click', saveCurrentState);
    btnLibrary.addEventListener('click', openLibrary);

    // Bind Manual ID Lookup
    const btnFind = document.getElementById('btn-find-puzzle');
    const inputFind = document.getElementById('manual-puzzle-id');
    if (btnFind && inputFind) {
        btnFind.addEventListener('click', () => {
            const val = inputFind.value.trim();
            if (val) loadSolutionMode(val);
        });
    }

    // Bind PDF Modal
    const btnPdfConfirm = document.getElementById('btn-pdf-confirm');
    const btnMobileDownload = document.getElementById('btn-mobile-download-book');
    const pdfModal = document.getElementById('pdf-settings-modal');

    if (btnMobileDownload) {
        btnMobileDownload.addEventListener('click', () => {
            document.getElementById('mobile-settings-modal').style.display = 'none';
            openPdfSettings();
        });
    }

    if (btnDownloadBook) {
        btnDownloadBook.addEventListener('click', openPdfSettings);
    }

    if (btnPdfConfirm) {
        btnPdfConfirm.addEventListener('click', () => {
            if (pdfModal) pdfModal.style.display = 'none';
            downloadBook();
        });
    }

    if (btnNoteMode) {
        console.log('Adding event listener to note mode button');
        btnNoteMode.addEventListener('click', function () {
            console.log('Note mode button clicked!');
            toggleNoteMode();
        });
    } else {
        console.log('Note mode button not found!');
    }

    if (btnNotebook) {
        btnNotebook.addEventListener('click', toggleNotebook);
    }

    if (btnThemeToggle) {
        btnThemeToggle.addEventListener('click', toggleTheme);
    }
    if (btnMobileThemeToggle) {
        btnMobileThemeToggle.addEventListener('click', toggleTheme);
    }

    // Load theme from localStorage
    const savedTheme = localStorage.getItem('kakuro-theme');
    if (savedTheme) {
        state.theme = savedTheme;
        applyTheme(savedTheme);
    }
    closeModal.addEventListener('click', () => libraryModal.style.display = 'none');
    window.addEventListener('click', (e) => {
        if (e.target === libraryModal) libraryModal.style.display = 'none';
    });

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            tabButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.currentTab = btn.dataset.tab;
            renderLibrary();
        });
    });

    window.addEventListener('keydown', handleGlobalKey);

    setupMobile();

    // Initialize authentication
    initAuth();

    // Clear queue when difficulty changes (so next 'New Game' fetches correct difficulty)
    const diffSelect = document.getElementById('difficulty-select');
    if (diffSelect) {
        diffSelect.addEventListener('change', () => {
            state.puzzleQueue = [];
            state.currentBatchDifficulty = diffSelect.value;
            console.log("Difficulty changed, queue cleared");
        });
    }

    fetchPuzzle();


    window.addEventListener('contextmenu', (e) => {
        // If we are currently doing a long press action, block the menu
        if (state.isDragSelecting || state.isLongPressTriggered) {
            e.preventDefault();
            return false;
        }
    }, { capture: true }); // Capture phase ensures we catch it first

    // Check for solution_id in URL
    const urlParams = new URLSearchParams(window.location.search);
    const solutionId = urlParams.get('solution_id');
    if (solutionId) {
        // Clear params so refresh doesn't stick
        window.history.replaceState({}, document.title, "/");
        // We probably need to wait for auth to init first if we want to log it?
        // But for viewing solution, maybe we don't strictly need auth, but rating requires it?
        // Let's defer slightly
        setTimeout(() => loadSolutionMode(solutionId), 500);
        return; // Skip default fetchPuzzle
    }

    // Check if we should show the tutorial
    checkAndShowTutorial();

    // Leaderboard listeners
    const btnLeaderboard = document.getElementById('btn-leaderboard');
    if (btnLeaderboard) {
        btnLeaderboard.addEventListener('click', openLeaderboard);
    }
    const leaderboardClose = document.getElementById('leaderboard-close');
    if (leaderboardClose) {
        leaderboardClose.addEventListener('click', () => {
            document.getElementById('leaderboard-modal').style.display = 'none';
        });
    }
    const leaderboardTabs = document.querySelectorAll('[data-leaderboard]');
    leaderboardTabs.forEach(btn => {
        btn.addEventListener('click', () => {
            leaderboardTabs.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.leaderboardType = btn.dataset.leaderboard;
            fetchLeaderboardData();
        });
    });

    // Fetch app info (debug mode, etc.)
    fetchInfo();
}

async function fetchInfo() {
    try {
        const res = await fetch('/info');
        if (res.ok) {
            state.info = await res.json();
            console.log("App info loaded:", state.info);
        }
    } catch (e) {
        console.error("Failed to fetch app info:", e);
    }
}

function checkAndShowTutorial() {
    const lastVisit = localStorage.getItem('last_visit');
    const hasSeen = localStorage.getItem('has_seen_tutorial');
    const now = Date.now();
    const THIRTY_DAYS = 30 * 24 * 60 * 60 * 1000;

    // Show if never seen OR if not visited in 30 days
    if (!hasSeen || (lastVisit && (now - parseInt(lastVisit) > THIRTY_DAYS))) {
        // Delay slightly to let the UI settle
        setTimeout(() => {
            const modal = document.getElementById('tutorial-modal');
            if (modal) {
                modal.style.display = 'block';
            }
        }, 1000);
    }

    // Update last visit time
    localStorage.setItem('last_visit', now.toString());
}

function closeTutorial() {
    const modal = document.getElementById('tutorial-modal');
    if (modal) {
        modal.style.display = 'none';
        localStorage.setItem('has_seen_tutorial', 'true');
    }
}
window.closeTutorial = closeTutorial; // Make globally available


function getCellFromPoint(x, y) {
    const numpad = document.getElementById('mobile-numpad');
    let prevDisplay = '';

    if (numpad) {
        // Save current inline display style
        prevDisplay = numpad.style.display;
        // Force hide so elementFromPoint sees through it
        numpad.style.display = 'none';
    }

    const el = document.elementFromPoint(x, y);

    // Restore the display style immediately
    if (numpad) {
        numpad.style.display = prevDisplay;
    }

    // If we hit a child element, find the parent cell
    if (el) {
        return el.closest('.cell');
    }
    return null;
}

function toggleTheme() {
    state.theme = state.theme === 'dark' ? 'light' : 'dark';
    applyTheme(state.theme);
    localStorage.setItem('kakuro-theme', state.theme);
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    const btnThemeToggle = document.getElementById('btn-theme-toggle');
    const btnMobileThemeToggle = document.getElementById('btn-mobile-theme-toggle');

    const updateButton = (btn) => {
        if (btn) {
            const icon = btn.querySelector('.tool-icon');
            const label = btn.querySelector('.tool-label');
            if (theme === 'light') {
                if (icon) icon.textContent = '🌙';
                if (label) label.textContent = 'Dark Mode';
            } else {
                if (icon) icon.textContent = '☀️';
                if (label) label.textContent = 'Light Mode';
            }
        }
    };

    updateButton(btnThemeToggle);
    updateButton(btnMobileThemeToggle);
}

function toggleNotebook() {
    state.notebookOpen = !state.notebookOpen;
    const notebookPanel = document.getElementById('notebook-panel');
    const btnNotebook = document.getElementById('btn-notebook');

    if (notebookPanel) {
        if (state.notebookOpen) {
            notebookPanel.classList.add('open');
        } else {
            notebookPanel.classList.remove('open');
        }
    }
    if (btnNotebook) {
        btnNotebook.classList.toggle('active', state.notebookOpen);
    }
}

function toggleNoteMode(skipRender = false) {
    state.noteMode = !state.noteMode;
    console.log('toggleNoteMode called, current state:', state.noteMode);

    const board = document.getElementById('kakuro-board');
    if (state.noteMode) {
        board.classList.add('mode-notes');
    } else {
        board.classList.remove('mode-notes');
    }

    const btnNoteMode = document.getElementById('btn-note-mode');
    console.log('New note mode state:', state.noteMode);
    if (btnNoteMode) {
        btnNoteMode.classList.toggle('active', state.noteMode);
        const statusSpan = btnNoteMode.querySelector('.tool-status');
        if (statusSpan) {
            statusSpan.textContent = state.noteMode ? 'ON' : 'OFF';
        }
        console.log('Button status updated');
    }

    const noteHelp = document.getElementById('note-help');
    if (noteHelp) {
        if (state.noteMode) {
            // Set text based on device width
            if (window.innerWidth <= 768) {
                // Mobile Text
                noteHelp.innerHTML = `
                    📝 <strong>Note Mode Active</strong><br>
                    • Long-press & drag to select<br>
                    • Single tap to start new selection<br>
                    • Select 2 adjacent cells for boundary notes<br>
                    • Double-tap to exit
                `;
            } else {
                // Desktop Text
                noteHelp.innerHTML = `
                    📝 <strong>Note Mode</strong> (press <kbd>N</kbd> to toggle) • Click cells (Ctrl+click for multiple) • Type to add notes • Backspace to delete • Select 2 adjacent cells for boundary notes • <kbd>Esc</kbd> to exit
                `;
            }
            noteHelp.style.display = 'block';
        } else {
            noteHelp.style.display = 'none';
        }
    }

    const navTools = document.getElementById('nav-tools');
    if (navTools) {
        navTools.style.color = state.noteMode ? 'var(--success-color)' : '';
    }

    if (!state.noteMode) {
        state.selectedCells.clear();
    }

    // If entering note mode and we have a single selection but no 'selectedCells', 
    // add it so the user can type notes immediately.
    if (state.noteMode && state.selected && state.selectedCells.size === 0) {
        const key = `${state.selected.r},${state.selected.c}`;
        state.selectedCells.add(key);
    }

    if (!skipRender) {
        renderBoard();
    }
}

async function fetchPuzzle() {
    btnGenerate.textContent = "Loading...";
    btnGenerate.disabled = true;

    try {
        const difficultySelect = document.getElementById('difficulty-select');
        const difficulty = difficultySelect ? difficultySelect.value : 'medium';

        if (state.puzzle &&
            state.puzzle.difficulty === difficulty &&
            state.puzzle.status !== 'solved') {
            await skipCurrentPuzzle();
        }

        // Check if we need to invalidate the queue (user changed difficulty)
        if (state.currentBatchDifficulty !== difficulty) {
            state.puzzleQueue = [];
            state.currentBatchDifficulty = difficulty;
        }

        // If queue is empty, fetch more
        if (state.puzzleQueue.length === 0) {
            console.log("Queue empty, fetching feed for:", difficulty);
            const res = await fetch(`/feed?difficulty=${difficulty}&limit=5`, {
                headers: getAuthHeaders()
            });
            if (!res.ok) throw new Error("Failed to fetch feed");
            const newPuzzles = await res.json();

            if (newPuzzles.length === 0) {
                alert("No puzzles found in feed.");
                return;
            }
            state.puzzleQueue.push(...newPuzzles);
            console.log(`Added ${newPuzzles.length} puzzles to queue.`);
        }

        // Pop the next puzzle
        const nextPuzzle = state.puzzleQueue.shift();
        console.log("Loading puzzle from feed:", nextPuzzle);
        loadPuzzleIntoState(nextPuzzle);

    } catch (e) {
        console.error("Error in fetchPuzzle:", e);
        // Fallback to old single generate if feed fails? 
        // Or just show error. Let's show error for now as feed should work.
        alert("Error loading new puzzle: " + e.message);
    } finally {
        btnGenerate.textContent = "New Puzzle";
        btnGenerate.disabled = false;
    }
}

function loadPuzzleIntoState(data) {
    // 0. Normalization Pass: Backend might return values as strings, but we need numbers
    // This ensures that userValue (int) === value (int) comparison logic works.
    const normalizeCell = (cell) => {
        if (cell.value != null) cell.value = parseInt(cell.value);
        if (cell.userValue != null) cell.userValue = parseInt(cell.userValue);
        if (cell.clue_h != null) cell.clue_h = parseInt(cell.clue_h);
        if (cell.clue_v != null) cell.clue_v = parseInt(cell.clue_v);
    };
    if (data.grid) data.grid.forEach(row => row.forEach(normalizeCell));
    if (data.userGrid) data.userGrid.forEach(row => row.forEach(normalizeCell));

    state.puzzle = data;
    // If loading from storage, userGrid might already be present
    if (data.userGrid) {
        state.userGrid = data.userGrid;
    } else {
        state.userGrid = data.grid.map(row => row.map(cell => ({
            ...cell,
            userValue: cell.userValue || null
        })));
    }

    state.selected = null;
    state.selectedCells.clear();
    state.rowNotes = data.rowNotes || Array(data.height).fill('');
    state.colNotes = data.colNotes || Array(data.width).fill('');
    state.cellNotes = data.cellNotes || {};
    state.notebook = data.notebook || '';
    state.notebook = data.notebook || '';
    state.rating = data.rating || 0;
    state.difficultyVote = data.difficultyVote || 5;
    state.userComment = data.userComment || '';
    state.editingNote = null;
    state.showErrors = false;
    state.noteMode = false;
    state.lastActionTime = Date.now();

    const btnNoteMode = document.getElementById('btn-note-mode');
    if (btnNoteMode) {
        btnNoteMode.classList.remove('active');
        const statusSpan = btnNoteMode.querySelector('.tool-status');
        if (statusSpan) {
            statusSpan.textContent = 'OFF';
        }
    }

    // 2. Hide Help Text
    const noteHelp = document.getElementById('note-help');
    if (noteHelp) {
        noteHelp.style.display = 'none';
    }

    // Update notebook textarea if it exists
    const notebookTextarea = document.getElementById('notebook-textarea');
    if (notebookTextarea) {
        notebookTextarea.value = state.notebook;
    }

    const navNotes = document.getElementById('nav-notes');
    if (navNotes) {
        navNotes.style.color = '';
    }

    // Calculate grid bounds
    calculateGridBounds();

    // Update title in debug mode
    if (state.info && state.info.debug) {
        document.title = `Kakuro: ${data.id}`;
    } else {
        document.title = "Kakuro Generator";
    }

    console.log("State updated, rendering board...");
    renderBoard();
}

function getFillCount() {
    if (!state.puzzle) return 0;
    let count = 0;
    for (let r = 0; r < state.puzzle.height; r++) {
        for (let c = 0; c < state.puzzle.width; c++) {
            if (state.userGrid[r][c].type === 'WHITE' && state.userGrid[r][c].userValue) {
                count++;
            }
        }
    }
    return count;
}

function calculateGridBounds() {
    const { width, height, grid } = state.puzzle;
    let minRow = height, maxRow = -1, minCol = width, maxCol = -1;

    // Find all white cells
    for (let r = 0; r < height; r++) {
        for (let c = 0; c < width; c++) {
            if (grid[r][c].type === 'WHITE') {
                minRow = Math.min(minRow, r);
                maxRow = Math.max(maxRow, r);
                minCol = Math.min(minCol, c);
                maxCol = Math.max(maxCol, c);
            }
        }
    }

    // Expand by 1 to include clue cells
    minRow = Math.max(0, minRow - 1);
    minCol = Math.max(0, minCol - 1);
    maxRow = Math.min(height - 1, maxRow);
    maxCol = Math.min(width - 1, maxCol);

    state.gridBounds = { minRow, maxRow, minCol, maxCol };
}

/**
 * Checks if the board is completely filled and 100% correct.
 * Unlike checkPuzzle(), this does not modify UI state (showErrors)
 * unless the puzzle is actually solved.
 */
function checkIfSolved() {
    if (!state.puzzle) return false;

    // 1. Check if board is full first
    if (!isBoardFull()) return false;

    // 2. Check correctness
    for (let r = 0; r < state.puzzle.height; r++) {
        for (let c = 0; c < state.puzzle.width; c++) {
            const userCell = state.userGrid[r][c];
            // The solution value is stored in the original grid data
            // We need to look at state.puzzle.grid if userGrid doesn't have the 'value' prop directly,
            // but looking at your loadPuzzleIntoState, state.userGrid copies props from data.grid.
            // Assuming cell.value contains the solution.
            
            if (userCell.type === 'WHITE') {
                // Compare user input with solution (loose comparison for extra safety)
                if (userCell.userValue != userCell.value) {
                    return false; 
                }
            }
        }
    }

    return true;
}

async function logInteraction(actionType, data = {}) {
    // We only log if a puzzle is active. 
    // Authentication is handled by headers; backend ignores if not logged in.
    if (!state.puzzle) return;

    const now = Date.now();
    const duration = now - state.lastActionTime;
    state.lastActionTime = now;

    const deviceType = window.innerWidth <= 968 ? 'mobile' : 'desktop';
    const timestamp = new Date().toISOString();
    const fillCount = getFillCount();

    const createPayload = (itemData) => ({
        puzzle_id: state.puzzle.id,
        action_type: actionType,
        row: itemData.row ?? null,
        col: itemData.col ?? null,
        old_value: itemData.oldValue ? String(itemData.oldValue) : null,
        new_value: itemData.newValue ? String(itemData.newValue) : null,
        duration_ms: duration, // Batch shares the same think-time
        fill_count: fillCount,
        client_timestamp: timestamp,
        device_type: deviceType
    });

    try {
        // CHECK IF BATCH (Array) OR SINGLE
        if (Array.isArray(data)) {
            const batchPayload = data.map(createPayload);
            if (batchPayload.length === 0) return;

            fetch('/log/batch_interaction', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
                body: JSON.stringify(batchPayload)
            });
        } else {
            // Single Interaction
            const payload = createPayload(data || {});
            fetch('/log/interaction', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
                body: JSON.stringify(payload)
            });
        }
    } catch (e) {
        console.error("Logging failed", e);
    }
}

async function skipCurrentPuzzle() {
    if (!state.puzzle || !state.puzzle.template_id) return;

    // Only track skip if the puzzle isn't already marked as solved
    if (state.puzzle.status === 'solved') return;

    try {
        await fetch('/skip', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({ 
                template_id: state.puzzle.template_id,
                puzzle_id: state.puzzle.id 
            })
        });
        console.log("Puzzle skip tracked.");
    } catch (e) {
        console.error("Error tracking skip:", e);
    }
}

async function saveCurrentState(silent = false) {
    if (typeof silent !== 'boolean') silent = false;

    if (!state.puzzle) return;

    if (!state.user) {
        // If this was a manual click (not silent), prompt the user to login
        if (!silent) {
            showToast("Please log in to save progress.");
            openAuthModal('login');
        }
        // If it was an autosave (silent), just abort quietly
        return;
    }

    // Save current notebook content
    const notebookTextarea = document.getElementById('notebook-textarea');
    if (notebookTextarea) {
        state.notebook = notebookTextarea.value;
    }

    const data = {
        id: state.puzzle.id,
        template_id: state.puzzle.template_id,
        width: state.puzzle.width,
        height: state.puzzle.height,
        difficulty: state.puzzle.difficulty,
        grid: state.puzzle.grid,
        userGrid: state.userGrid,
        status: state.puzzle.status || "started",
        rowNotes: state.rowNotes,
        colNotes: state.colNotes,
        cellNotes: state.cellNotes,
        notebook: state.notebook,
        notebook: state.notebook,
        rating: state.rating,
        difficultyVote: state.difficultyVote,
        userComment: state.userComment
    };

    try {
        const res = await fetch('/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify(data)
        });
        if (res.ok) {
            if (!silent) showToast("Progress Saved!");
            
            // Log explicitly initiated saves
            if (!silent) {
                logInteraction('SAVE');
            }

            console.log("Autosave successful");
        } else {
            if (!silent) showToast("Failed to save progress.");
        }
    } catch (e) {
        console.error("Save error:", e);
        if (!silent) showToast("Error saving progress.");
    }
}

function openPdfSettings() {
    if (!state.user) {
        showToast("Please log in to download a PDF book.");
        openAuthModal('login');
        return;
    }

    const modal = document.getElementById('pdf-settings-modal');
    if (modal) {
        // Pre-fill with current game difficulty
        const desktopDiff = document.getElementById('difficulty-select');
        const pdfDiff = document.getElementById('pdf-difficulty-select');
        if (desktopDiff && pdfDiff) {
            pdfDiff.value = desktopDiff.value;
        }
        modal.style.display = 'block';
    }
}

async function downloadBook() {
    if (!state.user) {
        showToast("Please log in to download a PDF book.");
        openAuthModal('login');
        return;
    }

    const diffSelect = document.getElementById('pdf-difficulty-select');
    const countInput = document.getElementById('pdf-count-input');
    const layoutSelect = document.getElementById('pdf-layout-select');
    
    const difficulty = diffSelect ? diffSelect.value : 'medium';
    let numPuzzles = countInput ? parseInt(countInput.value) : 4;
    const layout = layoutSelect ? parseInt(layoutSelect.value) : 1;

    // Clamp to 1-5
    numPuzzles = Math.max(1, Math.min(5, numPuzzles));

    showToast("Generating your PDF book...");

    try {
        const res = await fetch('/api/generate-book', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({
                difficulty: difficulty,
                num_puzzles: numPuzzles,
                puzzles_per_page: layout
            })
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Failed to generate book");
        }

        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `kakuro_book_${difficulty}.pdf`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        showToast("Download started!");
    } catch (e) {
        console.error("Download error:", e);
        showToast("Error generating PDF: " + e.message);
    }
}

async function openLibrary() {
    if (!state.user) {
        showToast("Please log in to view your library.");
        openAuthModal('login');
        return;
    }

    libraryModal.style.display = 'block';
    renderLibrary();
}

async function renderLibrary() {
    libraryList.innerHTML = '<p>Loading puzzles...</p>';
    try {
        const res = await fetch('/list_saved', {
            headers: getAuthHeaders()
        });
        const puzzles = await res.json();

        const filtered = puzzles.filter(p => p.status === state.currentTab);

        if (filtered.length === 0) {
            libraryList.innerHTML = `<p>No ${state.currentTab} puzzles found.</p>`;
            return;
        }

        libraryList.innerHTML = '';
        filtered.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
            .forEach(p => {
                const card = document.createElement('div');
                card.className = 'puzzle-card';

                // Render thumbnail
                let thumbnailHtml = `<div class="puzzle-thumbnail" style="grid-template-columns: repeat(${p.width}, 1fr)">`;
                const gridToShow = p.userGrid || p.grid;
                if (gridToShow) {
                    gridToShow.forEach(row => {
                        row.forEach(cell => {
                            const typeClass = cell.type === 'BLOCK' ? 'block' : 'white';
                            const val = cell.userValue || '';
                            thumbnailHtml += `<div class="mini-cell ${typeClass}">${val}</div>`;
                        });
                    });
                }
                thumbnailHtml += `</div>`;

                card.innerHTML = `
                    ${thumbnailHtml}
                    <div class="puzzle-info">
                        <h3>${escapeHtml(p.difficulty.replace('_', ' ').toUpperCase())}</h3>
                        <p>${p.width}x${p.height}</p>
                        <p>${new Date(p.timestamp).toLocaleString()}</p>
                    </div>
                    <button class="delete-btn" onclick="deletePuzzle(event, '${escapeHtml(p.id)}')">&times;</button>
                `;
                card.addEventListener('click', () => loadSavedPuzzle(p.id));
                libraryList.appendChild(card);
            });
    } catch (e) {
        libraryList.innerHTML = '<p>Error loading library.</p>';
    }
}

function setupCellInteractions(element, r, c) {
    const handleStart = (e) => {
        // Only allow left click (0) or touch
        if (e.type === 'mousedown') {
            if (Date.now() - state.lastTouchTime < 800) return;
            // Also ignore non-left clicks
            if (e.button !== 0) return;
        }

        // Record Touch Time
        if (e.type === 'touchstart') {
            state.lastTouchTime = Date.now();
        }

        hideNumpad();

        state.isLongPressTriggered = false;
        state.isDragSelecting = false;
        state.lastTouchedRC = null;

        // ============================================
        // 1. DOUBLE TAP DETECTION
        // ============================================
        const now = Date.now();
        const currentRC = `${r},${c}`;

        // Check if same cell tapped within 300ms
        if (state.lastTapRC === currentRC && (now - state.lastTapTime) < 300) {

            // If in Note Mode, Exit it!
            if (state.noteMode) {
                toggleNoteMode();
                if (navigator.vibrate) navigator.vibrate([50, 50]); // Double buzz feedback
                showToast("Exited Note Mode");
            }

            // IMPORTANT: Return early to prevent Long Press timer from starting.
            // The browser will fire a 'click' event immediately after this.
            // That 'click' will call selectCell(), which will see that Note Mode 
            // is now OFF, and perform a standard exclusive selection.
            return;
        }

        // Save tap info for next time
        state.lastTapTime = now;
        state.lastTapRC = currentRC;
        // ============================================

        // Record Start Position (Critical for movement calculation)
        if (e.type === 'touchstart') {
            state.touchStartX = e.touches[0].clientX;
            state.touchStartY = e.touches[0].clientY;
        } else {
            state.touchStartX = e.clientX;
            state.touchStartY = e.clientY;
        }

        // Start the timer
        state.longPressTimer = setTimeout(() => {
            // TIMER FINISHED: Enter Drag/Note Mode
            state.isLongPressTriggered = true;
            state.isDragSelecting = true;

            // Store Origin
            const currentRC = `${r},${c}`;
            state.lastTouchedRC = currentRC;


            // 1. Enable Note Mode if off
            if (!state.noteMode) {
                // Pass true to skip renderBoard(), preventing DOM destruction
                toggleNoteMode(true);
                if (navigator.vibrate) navigator.vibrate(50);
            }

            // 2. Select Origin Cell
            state.selectedCells.clear();
            state.selectedCells.add(currentRC);
            state.selected = { r, c };

            const cell = document.querySelector(`.cell[data-rc="${currentRC}"]`);
            if (cell) {
                cell.classList.add('selected');
                // Ensure Note Mode styling is applied
                cell.classList.add('multi-selected');
                // Also ensure grid knows we are in note mode
                document.getElementById('kakuro-board').classList.add('mode-notes');
            }


        }, state.longPressDuration);
    };

    const handleMove = (e) => {
        // Get current coordinates
        let clientX, clientY;
        if (e.type === 'touchmove') {
            clientX = e.touches[0].clientX;
            clientY = e.touches[0].clientY;
        } else {
            clientX = e.clientX;
            clientY = e.clientY;
        }

        // SCENARIO 1: Timer is running (Waiting to see if it's a hold or a scroll)
        if (state.longPressTimer && !state.isDragSelecting) {
            const dx = clientX - state.touchStartX;
            const dy = clientY - state.touchStartY;
            const distance = Math.sqrt(dx * dx + dy * dy);

            // Tolerance: 10 pixels. 
            // If moved > 10px, user is trying to scroll/pan.
            if (distance > 10) {
                clearTimeout(state.longPressTimer);
                state.longPressTimer = null;
                // We return here and let the browser scroll naturally
                return;
            }
            // If distance < 10px, we DO NOTHING. We assume it's just a shaky finger.
        }

        // SCENARIO 2: Timer Finished (We are locked in Drag Mode)
        if (state.isDragSelecting) {
            // CRITICAL: Stop browser scrolling now that we are selecting
            if (e.cancelable) e.preventDefault();

            const targetCell = getCellFromPoint(clientX, clientY);

            if (targetCell && targetCell.classList.contains('white')) {
                const rc = targetCell.dataset.rc;
                if (rc) {
                    state.lastTouchedRC = rc;
                    if (!state.selectedCells.has(rc)) {
                        state.selectedCells.add(rc);
                        if (navigator.vibrate) navigator.vibrate(10);
                        renderBoard();
                    }
                }
            }
        }
    };

    const handleEnd = (e) => {
        // Clean up timer
        if (state.longPressTimer) {
            clearTimeout(state.longPressTimer);
            state.longPressTimer = null;
        }

        // If we were dragging, finish up
        if (state.isDragSelecting) {
            state.isDragSelecting = false;

            // Show numpad
            if (window.innerWidth <= 768 && state.lastTouchedRC) {
                const targetEl = document.querySelector(`.cell[data-rc="${state.lastTouchedRC}"]`);
                if (targetEl) {
                    showNumpad(targetEl);
                }
            }

            if (e.cancelable) e.preventDefault();
            e.stopImmediatePropagation();
        }
    };

    // --- Event Listeners ---

    // 1. Context Menu: Strictly Block It (Fixes the menu appearing)
    element.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        e.stopPropagation();
        return false;
    });

    // 2. Touch Events
    // passive: false is REQUIRED to use e.preventDefault() in touchmove
    element.addEventListener('touchstart', handleStart, { passive: true });
    element.addEventListener('touchmove', handleMove, { passive: false });
    element.addEventListener('touchend', handleEnd);

    // 3. Mouse Events (Desktop)
    element.addEventListener('mousedown', handleStart);
    element.addEventListener('mousemove', (e) => {
        if (e.buttons === 1) handleMove(e);
    });
    element.addEventListener('mouseup', handleEnd);

    // 4. Click (Short Press)
    element.addEventListener('click', (e) => {
        if (state.isLongPressTriggered) {
            e.stopImmediatePropagation();
            e.preventDefault();
            return;
        }
        selectCell(r, c, e);
    });
}

async function loadSavedPuzzle(id) {
    try {
        const res = await fetch(`/load/${id}`, {
            headers: getAuthHeaders()
        });
        if (!res.ok) throw new Error("Failed to load");
        const data = await res.json();
        loadPuzzleIntoState(data);
        if (libraryModal) libraryModal.style.display = 'none';
        showToast("Puzzle Loaded!");
    } catch (e) {
        alert("Error loading puzzle: " + e.message);
    }
}

async function loadSolutionMode(id) {
    try {
        showToast("Targeting solution...");
        const res = await fetch(`/load/${id}`, {
            headers: getAuthHeaders()
        });
        if (!res.ok) throw new Error("Puzzle not found");
        const data = await res.json();
        loadPuzzleIntoState(data);

        // Populate the grid with the solution
        state.userGrid.forEach(row => {
            row.forEach(cell => {
                if (cell.type === 'WHITE') {
                    cell.userValue = cell.value;
                }
            });
        });

        // Auto-show errors to reveal the solution (will show as green)
        state.showErrors = true;
        renderBoard();

        showToast("Solution Loaded!");
    } catch (e) {
        console.error("Load solution error:", e);
        showToast("Error: " + e.message);
    }
}

async function deletePuzzle(event, id) {
    event.stopPropagation();
    if (!confirm("Delete this puzzle?")) return;

    try {
        const res = await fetch(`/delete/${id}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        if (res.ok) {
            renderLibrary();
        }
    } catch (e) {
        alert("Error deleting puzzle.");
    }
}

function renderBoard() {
    if (!state.puzzle) return;

    // Clear the entire board container and rebuild
    const boardContainer = boardEl.parentElement;

    // Remove old wrapper if exists
    const oldWrapper = boardContainer.querySelector('.board-wrapper');
    if (oldWrapper) oldWrapper.remove();

    // Create wrapper for grid + margins
    const wrapper = document.createElement('div');
    wrapper.className = 'board-wrapper';

    const { minRow, maxRow, minCol, maxCol } = state.gridBounds;
    const visibleHeight = maxRow - minRow + 1;
    const visibleWidth = maxCol - minCol + 1;

    boardContainer.style.setProperty('--cols', visibleWidth);
    boardContainer.style.setProperty('--rows', visibleHeight);

    // Create column notes row (top margin)
    const colNotesRow = document.createElement('div');
    colNotesRow.className = 'col-notes-row';
    colNotesRow.style.gridTemplateColumns = `40px repeat(${visibleWidth}, 60px)`;

    // Empty corner cell
    const cornerCell = document.createElement('div');
    cornerCell.className = 'margin-corner';
    colNotesRow.appendChild(cornerCell);

    // Column note cells
    for (let c = minCol; c <= maxCol; c++) {
        const noteCell = createNoteCell('col', c, state.colNotes[c]);
        colNotesRow.appendChild(noteCell);
    }
    wrapper.appendChild(colNotesRow);

    // Create main content area with grid gaps for boundary notes
    const mainArea = document.createElement('div');
    mainArea.className = 'main-grid-area-with-gaps';
    // Use 60px for cells, 20px for gaps (note areas)
    const colTemplate = `40px repeat(${visibleWidth}, 60px)`;
    const rowTemplate = `repeat(${visibleHeight}, 60px)`;
    mainArea.style.gridTemplateColumns = colTemplate;
    mainArea.style.gridTemplateRows = rowTemplate;
    mainArea.style.gap = '1px';
    mainArea.style.position = 'relative';

    for (let r = minRow; r <= maxRow; r++) {
        // Row note cell
        const rowNoteCell = createNoteCell('row', r, state.rowNotes[r]);
        mainArea.appendChild(rowNoteCell);

        // Grid cells for this row
        for (let c = minCol; c <= maxCol; c++) {
            const cellData = state.userGrid[r][c];
            const el = createGridCell(cellData, r, c);
            mainArea.appendChild(el);
        }
    }

    // Add boundary notes as overlays
    addBoundaryNotesOverlay(mainArea, minRow, maxRow, minCol, maxCol);

    wrapper.appendChild(mainArea);

    boardContainer.insertBefore(wrapper, boardEl);

    // Keep the original grid hidden but maintain reference
    boardEl.style.display = 'none';
}

function addBoundaryNotesOverlay(container, minRow, maxRow, minCol, maxCol) {
    // Detect mobile layout matching CSS breakpoint
    const isMobile = window.innerWidth <= 968;

    // Desktop: 60px cell, 40px header
    // Mobile: 45px cell, 30px header
    const cellSize = isMobile ? 45 : 60;
    const headerSize = isMobile ? 30 : 40;
    const gap = 1;
    const cellStride = cellSize + gap;

    // Add all boundary notes as absolutely positioned elements
    for (let r = minRow; r <= maxRow; r++) {
        for (let c = minCol; c <= maxCol; c++) {
            // Right boundary (between this cell and next)
            if (c < maxCol) {
                const rightKey = `${r},${c}:${r},${c + 1}`;
                if (state.cellNotes[rightKey]) {
                    const note = document.createElement('div');
                    note.className = 'boundary-note-overlay boundary-vertical';
                    note.textContent = state.cellNotes[rightKey];

                    // Position between columns
                    const colIndex = c - minCol;
                    const rowIndex = r - minRow;

                    const left = headerSize + (colIndex + 1) * cellStride;
                    const top = rowIndex * cellStride + (cellSize / 2); // Center vertically in the cell

                    note.style.left = `${left}px`;
                    note.style.top = `${top}px`;
                    container.appendChild(note);
                }
            }

            // Bottom boundary (between this cell and below)
            if (r < maxRow) {
                const bottomKey = `${r},${c}:${r + 1},${c}`;
                if (state.cellNotes[bottomKey]) {
                    const note = document.createElement('div');
                    note.className = 'boundary-note-overlay boundary-horizontal';
                    note.textContent = state.cellNotes[bottomKey];

                    // Position between rows
                    const colIndex = c - minCol;
                    const rowIndex = r - minRow;

                    const left = headerSize + colIndex * cellStride + (cellSize / 2); // Center horizontally in the cell
                    const top = (rowIndex + 1) * cellStride; // Bottom edge of current cell

                    note.style.left = `${left}px`;
                    note.style.top = `${top}px`;
                    container.appendChild(note);
                }
            }
        }
    }
}

function createNoteCell(type, index, value) {
    const cell = document.createElement('div');
    cell.className = `margin-note margin-note-${type}`;

    const isEditing = state.editingNote &&
        state.editingNote.type === type &&
        state.editingNote.index === index;

    if (isEditing) {
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'note-input';
        input.value = value;
        input.maxLength = 10;

        // Update state immediately on input, but don't re-render (avoids focus loss)
        input.addEventListener('input', () => updateNoteState(type, index, input.value));

        input.addEventListener('blur', () => saveNote(type, index, input.value));
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                saveNote(type, index, input.value);
            } else if (e.key === 'Escape') {
                state.editingNote = null;
                renderBoard();
            }
            e.stopPropagation();
        });
        cell.appendChild(input);
        // Focus input after render
        setTimeout(() => input.focus(), 0);
    } else {
        cell.textContent = value || '';
        cell.addEventListener('click', (e) => {
            e.stopPropagation();
            state.editingNote = { type, index };
            renderBoard();
        });
    }

    return cell;
}

function updateNoteState(type, index, value) {
    if (type === 'row') {
        state.rowNotes[index] = value;
    } else if (type === 'col') {
        state.colNotes[index] = value;
    } else if (type === 'cell') {
        state.cellNotes[index] = value;
    }
    triggerAutosave();
}

function saveNote(type, index, value) {
    updateNoteState(type, index, value);
    state.editingNote = null;
    renderBoard();
}

function createGridCell(cellData, r, c) {
    const el = document.createElement('div');
    el.className = 'cell';
    el.dataset.rc = `${r},${c}`;

    const isSelected = state.selected && state.selected.r === r && state.selected.c === c;
    const isMultiSelected = state.selectedCells.has(`${r},${c}`);

    if (cellData.type === 'BLOCK') {
        el.classList.add('block');
        let content = `<div class="clue-container"><div class="diagonal-line"></div>`;
        if (cellData.clue_h !== null && cellData.clue_h !== undefined) {
            content += `<div class="clue-h">${cellData.clue_h}</div>`;
        }
        if (cellData.clue_v !== null && cellData.clue_v !== undefined) {
            content += `<div class="clue-v">${cellData.clue_v}</div>`;
        }
        content += `</div>`;
        el.innerHTML = content;
    } else {
        el.classList.add('white');
        if (isSelected) {
            el.classList.add('selected');
        }
        if (isMultiSelected) {
            el.classList.add('multi-selected');
        }

        // Create content wrapper
        const wrapper = document.createElement('div');
        wrapper.className = 'cell-content-wrapper';

        if (cellData.userValue) {
            const valueEl = document.createElement('div');
            valueEl.className = 'cell-value';
            valueEl.textContent = cellData.userValue;
            if (state.showErrors) {
                if (cellData.userValue == cellData.value) {
                    valueEl.classList.add('correct');
                } else {
                    valueEl.classList.add('incorrect');
                }
            }
            wrapper.appendChild(valueEl);
        } else if (state.showErrors) {
            // Highlight empty white cells as incorrect if checking
            el.classList.add('incorrect');
        }

        // Add cell notes
        addCellNotes(wrapper, r, c);

        el.appendChild(wrapper);
        setupCellInteractions(el, r, c);
    }

    return el;
}

function addCellNotes(wrapper, r, c) {
    const cellKey = `${r},${c}`;

    // Corner note (for single cell)
    if (state.cellNotes[cellKey]) {
        const cornerNote = document.createElement('div');
        cornerNote.className = 'cell-corner-note';
        cornerNote.textContent = state.cellNotes[cellKey];
        wrapper.appendChild(cornerNote);
    }

    // Boundary notes are now handled by addBoundaryNotesOverlay
}

function selectCell(r, c, event) {
    // Only allow selecting white cells via click
    if (state.userGrid[r][c].type === 'WHITE') {
        if (state.noteMode) {
            // Multi-select mode with Ctrl/Cmd key
            const key = `${r},${c}`;
            if (event && (event.ctrlKey || event.metaKey)) {
                // Add/remove from multi-selection
                if (state.selectedCells.has(key)) {
                    state.selectedCells.delete(key);
                } else {
                    state.selectedCells.add(key);
                }
            } else {
                // Single selection (clear previous)
                state.selectedCells.clear();
                state.selectedCells.add(key);
                state.selected = { r, c };
            }
        } else {
            // Normal selection mode
            state.selected = { r, c };
            state.selectedCells.clear();
        }
        renderBoard();
    }

    if (window.innerWidth <= 768) {
        // Find the cell using the data-rc attribute
        const targetEl = document.querySelector(`.cell[data-rc="${r},${c}"]`);

        if (targetEl) {
            showNumpad(targetEl);
        }
    }
}

function showNumpad(cellElement) {
    const numpad = document.getElementById('mobile-numpad');
    const rect = cellElement.getBoundingClientRect();
    const scrollY = window.scrollY;

    // Dimensions based on your CSS
    const numpadWidth = 300;
    const numpadHeight = 132; // (10px pad * 2) + (50px btn * 2) + 8px gap + borders
    const screenMargin = 10;  // Padding from screen edge
    const cellGap = 8;        // Gap between cell and numpad

    // 1. Horizontal Positioning (Clamped)
    // Start with the center of the cell
    let left = rect.left + (rect.width / 2);

    // Calculate bounds. Since CSS uses transform: translateX(-50%), 
    // the 'left' style coordinate represents the center of the numpad.
    // So 'left' must be at least (width/2 + margin) and at most (screenWidth - width/2 - margin)
    const minX = (numpadWidth / 2) + screenMargin;
    const maxX = window.innerWidth - (numpadWidth / 2) - screenMargin;

    // Clamp the value
    left = Math.max(minX, Math.min(left, maxX));

    // 2. Vertical Positioning (Smart Flip)
    // Default: Position BELOW the cell
    let top = rect.bottom + scrollY + cellGap;

    // Check available space in the viewport below the cell
    const spaceBelow = window.innerHeight - rect.bottom;

    // If there isn't enough space below, AND there is space above...
    if (spaceBelow < (numpadHeight + screenMargin) && rect.top > (numpadHeight + screenMargin)) {
        // ...Position ABOVE the cell
        // Calculation: Top of cell - Gap - Height of numpad
        top = rect.top + scrollY - cellGap - numpadHeight;
    }

    numpad.style.top = `${top}px`;
    numpad.style.left = `${left}px`; // CSS transform handles the centering offset

    numpad.style.display = '';
    numpad.classList.add('active');
}

function hideNumpad() {
    const numpad = document.getElementById('mobile-numpad');
    if (numpad) {
        numpad.classList.remove('active');
        // FORCE hide immediately to prevent any visual lag or ghost touches
        numpad.style.display = 'none';
    }
}

// 6. Update global click listener to hide numpad
window.addEventListener('click', (e) => {
    // If clicking outside board and outside numpad
    if (!e.target.closest('.mobile-numpad') && !e.target.closest('.cell')) {
        hideNumpad();
    }
});

function handleGlobalKey(e) {
    // Don't handle if typing in an input field
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    // Toggle note mode with 'n' key
    if (e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        toggleNoteMode();
        return;
    }

    const { minRow, maxRow, minCol, maxCol } = state.gridBounds;

    // Handle note mode typing
    if (state.noteMode && state.selectedCells.size > 0) {
        // Allow alphanumeric input for notes
        if (e.key.length === 1 && /[a-zA-Z0-9<>~]/.test(e.key)) {
            e.preventDefault();
            handleNoteInput(e.key);
            return;
        }

        // Backspace to delete notes
        if (e.key === 'Backspace' || e.key === 'Delete') {
            e.preventDefault();
            deleteSelectedNotes();
            return;
        }

        // Space to clear selection
        if (e.key === ' ') {
            e.preventDefault();
            state.selectedCells.clear();
            renderBoard();
            return;
        }

        // Escape to exit note mode
        if (e.key === 'Escape') {
            e.preventDefault();
            state.selectedCells.clear();
            state.noteMode = false;
            const btnNoteMode = document.getElementById('btn-note-mode');
            const noteHelp = document.getElementById('note-help');
            if (btnNoteMode) {
                btnNoteMode.classList.remove('active');
                const statusSpan = btnNoteMode.querySelector('.tool-status');
                if (statusSpan) {
                    statusSpan.textContent = 'OFF';
                }
            }
            if (noteHelp) {
                noteHelp.style.display = 'none';
            }
            renderBoard();
            return;
        }
    }

    // Normal mode - handle cell value input
    if (!state.noteMode && state.selected) {
        const { r, c } = state.selected;

        // Numbers 1-9
        if (e.key >= '1' && e.key <= '9') {
            handleInputNumber(e.key);
            return;
        }

        // Delete / Backspace
        if (e.key === 'Backspace' || e.key === 'Delete') {
            e.preventDefault(); // Prevent browser back navigation
            handleInputDelete();
            return;
        }

        // Arrows - navigate within visible bounds
        let nr = r, nc = c;
        if (e.key === 'ArrowUp') {
            nr = Math.max(minRow, r - 1);
        } else if (e.key === 'ArrowDown') {
            nr = Math.min(maxRow, r + 1);
        } else if (e.key === 'ArrowLeft') {
            nc = Math.max(minCol, c - 1);
        } else if (e.key === 'ArrowRight') {
            nc = Math.min(maxCol, c + 1);
        } else {
            return; // Not handled
        }

        e.preventDefault();
        state.selected = { r: nr, c: nc };
        renderBoard();
    }
}

function handleNoteInput(char) {
    if (state.selectedCells.size === 0) return;

    // If exactly 2 adjacent cells selected, create boundary note
    if (state.selectedCells.size === 2) {
        const cells = Array.from(state.selectedCells).map(k => {
            const [row, col] = k.split(',').map(Number);
            return { r: row, c: col };
        });

        const [c1, c2] = cells;
        const isAdjacent =
            (Math.abs(c1.r - c2.r) === 1 && c1.c === c2.c) ||
            (Math.abs(c1.c - c2.c) === 1 && c1.r === c2.r);

        if (isAdjacent) {
            const [first, second] = cells.sort((a, b) =>
                a.r !== b.r ? a.r - b.r : a.c - b.c
            );
            const boundaryKey = `${first.r},${first.c}:${second.r},${second.c}`;
            const oldValue = state.cellNotes[boundaryKey] || ''; // Define oldValue
            const newValue = oldValue + char;                  // Define newValue

            state.cellNotes[boundaryKey] = newValue;

            logInteraction('NOTE_BOUNDARY_ADD', {
                row: first.r,
                col: first.c,
                oldValue: oldValue,
                newValue: newValue
            });

            renderBoard();
            triggerAutosave();
            return;
        }
    }

    // Otherwise, add to corner notes of all selected cells
    const logs = [];
    state.selectedCells.forEach(key => {
        const [r, c] = key.split(',').map(Number);
        const oldValue = state.cellNotes[key] || '';
        const newValue = oldValue + char;

        state.cellNotes[key] = newValue;

        logs.push({
            row: r,
            col: c,
            oldValue: oldValue,
            newValue: newValue
        });
    });

    if (logs.length > 0) {
        logInteraction('NOTE_ADD', logs);
    }

    renderBoard();
    triggerAutosave();
}

function deleteSelectedNotes() {
    if (state.selectedCells.size === 0) return;

    // If exactly 2 adjacent cells, delete boundary note
    if (state.selectedCells.size === 2) {
        const cells = Array.from(state.selectedCells).map(k => {
            const [row, col] = k.split(',').map(Number);
            return { r: row, c: col };
        });

        const [c1, c2] = cells;
        const isAdjacent =
            (Math.abs(c1.r - c2.r) === 1 && c1.c === c2.c) ||
            (Math.abs(c1.c - c2.c) === 1 && c1.r === c2.r);

        if (isAdjacent) {
            const [first, second] = cells.sort((a, b) =>
                a.r !== b.r ? a.r - b.r : a.c - b.c
            );
            const boundaryKey = `${first.r},${first.c}:${second.r},${second.c}`;
            const oldValue = state.cellNotes[boundaryKey] || '';
            if (oldValue.length > 0) {
                const newValue = oldValue.slice(0, -1);
                if (newValue === '') {
                    delete state.cellNotes[boundaryKey];
                } else {
                    state.cellNotes[boundaryKey] = newValue;
                }
                logInteraction('NOTE_BOUNDARY_REMOVE', {
                    row: first.r,
                    col: first.c,
                    oldValue: oldValue,
                    newValue: newValue
                });
            }
            renderBoard();
            triggerAutosave();
            return;
        }
    }

    // Delete last character from corner notes
    const logs = [];
    state.selectedCells.forEach(key => {
        const [r, c] = key.split(',').map(Number);
        const oldValue = state.cellNotes[key] || '';
        if (oldValue.length > 0) {
            const newValue = oldValue.slice(0, -1);
            if (newValue === '') {
                delete state.cellNotes[key];
            } else {
                state.cellNotes[key] = newValue;
            }

            logs.push({
                row: r,
                col: c,
                oldValue: oldValue,
                newValue: newValue
            });
        }
    });

    if (logs.length > 0) {
        logInteraction('NOTE_REMOVE', logs);
    }
    renderBoard();
    triggerAutosave();
}

function checkPuzzle() {
    if (!state.puzzle) return;

    logInteraction('CHECK');

    state.showErrors = true;
    renderBoard();

    let allCorrect = true;
    let allFilled = true;

    for (let r = 0; r < state.puzzle.height; r++) {
        for (let c = 0; c < state.puzzle.width; c++) {
            const cell = state.userGrid[r][c];
            if (cell.type === 'WHITE') {
                if (!cell.userValue) {
                    allFilled = false;
                    allCorrect = false;
                } else if (cell.userValue != cell.value) {
                    allCorrect = false;
                }
            }
        }
    }

    if (allCorrect) {
        showToast("Perfect! Puzzle Solved!");
        state.puzzle.status = "solved";
        logInteraction('SOLVED');
        // Show rating modal
        showRatingModal();
    } else if (allFilled) {
        showToast("Almost there, but some numbers are wrong.");
    } else {
        showToast("Keep going! Some cells are missing or incorrect.");
    }
}

function showRatingModal() {
    const modal = document.getElementById('rating-modal');
    if (modal) {
        modal.style.display = 'block';
        modal.style.display = 'block';
        renderStars();
        renderDifficultySlider();
    }
}

function renderDifficultySlider() {
    const slider = document.getElementById('difficulty-slider');
    if (slider) {
        slider.value = state.difficultyVote || 5; // Default to 'Perfect' (5) if not set

        // Remove existing listener to avoid duplicates if re-rendering usually not needed as we just set value
        // But good practice if complex logic
        slider.oninput = (e) => {
            state.difficultyVote = parseInt(e.target.value);
        };
    }
}

function renderStars() {
    const starsContainer = document.getElementById('stars-container');
    if (!starsContainer) return;

    starsContainer.innerHTML = '';
    for (let i = 1; i <= 5; i++) {
        const star = document.createElement('span');
        star.className = 'star';
        star.textContent = '★';
        star.dataset.rating = i;
        if (i <= state.rating) {
            star.classList.add('active');
        }
        star.addEventListener('click', () => setRating(i));
        star.addEventListener('mouseenter', () => highlightStars(i));
        star.addEventListener('mouseleave', () => highlightStars(state.rating));
        starsContainer.appendChild(star);
    }
}

function setRating(rating) {
    state.rating = rating;
    renderStars();
}

function highlightStars(count) {
    const stars = document.querySelectorAll('.star');
    stars.forEach((star, index) => {
        if (index < count) {
            star.classList.add('active');
        } else {
            star.classList.remove('active');
        }
    });
}

function submitRating() {
    const commentTextarea = document.getElementById('rating-comment');
    if (commentTextarea) {
        state.userComment = commentTextarea.value;
    }

    // Capture slider value one last time (redundant but safe)
    const slider = document.getElementById('difficulty-slider');
    if (slider) {
        state.difficultyVote = parseInt(slider.value);
    }

    // Close modal
    const modal = document.getElementById('rating-modal');
    if (modal) {
        modal.style.display = 'none';
    }

    // Save with rating
    saveCurrentState();
    showToast("Thank you for your feedback!");

    setTimeout(() => {
        fetchPuzzle(); 
    }, 500);
}

function closeRatingModal() {
    const modal = document.getElementById('rating-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '1'; // Ensure it's visible
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.5s ease';
            setTimeout(() => toast.remove(), 500);
        }, 3000);
    }, 10);
}

// Wait for DOM to be fully loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

// =====================
// Authentication Module
// =====================


function initAuth() {
    // Load tokens from localStorage
    state.accessToken = localStorage.getItem('kakuro-access-token');
    state.refreshToken = localStorage.getItem('kakuro-refresh-token');

    // Check for tokens in URL (from OAuth callback)
    const urlParams = new URLSearchParams(window.location.search);
    const accessToken = urlParams.get('access_token');
    const refreshToken = urlParams.get('refresh_token');
    const resetToken = urlParams.get('reset_token');

    if (accessToken && refreshToken) {
        setTokens(accessToken, refreshToken);
        // Clear URL params
        window.history.replaceState({}, document.title, window.location.pathname);
    } else if (resetToken) {
        // Clear URL params
        window.history.replaceState({}, document.title, window.location.pathname);
        // Store token in global state if needed or just open modal
        state.resetToken = resetToken;
        openAuthModal('reset');
    }

    // Setup event listeners
    setupAuthEventListeners();

    // If we have tokens, fetch user profile
    if (state.accessToken) {
        fetchUserProfile();
    } else {
        updateAuthUI();
    }
}

function setupAuthEventListeners() {
    const btnLogin = document.getElementById('btn-login');
    const btnRegister = document.getElementById('btn-register');
    const authModal = document.getElementById('auth-modal');
    const authClose = document.getElementById('auth-close');
    const btnLoginSubmit = document.getElementById('btn-login-submit');
    const btnRegisterSubmit = document.getElementById('btn-register-submit');
    const btnVerifySubmit = document.getElementById('btn-verify-submit');
    const btnResendCode = document.getElementById('btn-resend-code');
    const btnSpamConfirm = document.getElementById('btn-spam-confirm');
    const btnSpamCancel = document.getElementById('btn-spam-cancel');
    const spamModal = document.getElementById('spam-check-modal');
    const backToRegister = document.getElementById('back-to-register');
    const switchToRegister = document.getElementById('switch-to-register');
    const switchToLogin = document.getElementById('switch-to-login');
    const btnUser = document.getElementById('btn-user');
    const btnLogout = document.getElementById('btn-logout');
    const userMenu = document.getElementById('user-menu');

    // New elements for forgot password
    const linkForgotPassword = document.getElementById('link-forgot-password');
    const btnForgotSubmit = document.getElementById('btn-forgot-submit');
    const btnResetSubmit = document.getElementById('btn-reset-submit');
    const backToLoginFromForgot = document.getElementById('back-to-login-from-forgot');
    const switchToLoginFromReset = document.getElementById('switch-to-login'); // Reusing or could be new

    if (btnLogin) {
        btnLogin.addEventListener('click', () => openAuthModal('login'));
    }
    if (btnRegister) {
        btnRegister.addEventListener('click', () => openAuthModal('register'));
    }
    if (authClose) {
        authClose.addEventListener('click', closeAuthModal);
    }
    if (authModal) {
        authModal.addEventListener('click', (e) => {
            if (e.target === authModal) closeAuthModal();
        });
    }
    if (btnLoginSubmit) {
        btnLoginSubmit.addEventListener('click', handleLogin);
    }
    if (btnRegisterSubmit) {
        btnRegisterSubmit.addEventListener('click', handleRegister);
    }
    if (btnVerifySubmit) {
        btnVerifySubmit.addEventListener('click', handleVerifyEmail);
    }
    if (btnResendCode) {
        btnResendCode.addEventListener('click', (e) => {
            e.preventDefault();

            // Check if link is disabled via class
            if (btnResendCode.classList.contains('disabled')) return;

            // Open the Spam Check Modal instead of sending immediately
            if (spamModal) {
                spamModal.style.display = 'block';
            }
        });
    }
    if (backToRegister) {
        backToRegister.addEventListener('click', (e) => {
            e.preventDefault();
            showAuthForm('register');
        });
    }
    if (btnSpamConfirm) {
        btnSpamConfirm.addEventListener('click', () => {
            // Close Spam Modal
            if (spamModal) spamModal.style.display = 'none';
            // Trigger actual API call
            handleResendCode();
        });
    }
    if (btnSpamCancel) {
        btnSpamCancel.addEventListener('click', () => {
            if (spamModal) spamModal.style.display = 'none';
        });
    }
    if (spamModal) {
        spamModal.addEventListener('click', (e) => {
            if (e.target === spamModal) spamModal.style.display = 'none';
        });
    }
    if (switchToRegister) {
        switchToRegister.addEventListener('click', (e) => {
            e.preventDefault();
            showAuthForm('register');
        });
    }
    if (switchToLogin) {
        switchToLogin.addEventListener('click', (e) => {
            e.preventDefault();
            showAuthForm('login');
        });
    }
    if (btnUser) {
        btnUser.addEventListener('click', (e) => {
            e.stopPropagation();
            userMenu.classList.toggle('open');
        });
    }
    if (btnLogout) {
        btnLogout.addEventListener('click', handleLogout);
    }

    // Close user dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (userMenu && !userMenu.contains(e.target)) {
            userMenu.classList.remove('open');
        }
    });

    // Setup OAuth buttons
    document.querySelectorAll('.btn-oauth').forEach(btn => {
        btn.addEventListener('click', () => {
            const provider = btn.dataset.provider;
            handleOAuth(provider);
        });
    });

    // Setup verification code inputs
    setupCodeInputs();

    // Handle Enter key in forms
    const loginEmail = document.getElementById('login-email');
    const loginPassword = document.getElementById('login-password');
    const registerUsername = document.getElementById('register-username');
    const registerEmail = document.getElementById('register-email');
    const registerPassword = document.getElementById('register-password');

    [loginEmail, loginPassword].forEach(input => {
        if (input) {
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') handleLogin();
            });
        }
    });

    [registerUsername, registerEmail, registerPassword].forEach(input => {
        if (input) {
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') handleRegister();
            });
        }
    });

    if (linkForgotPassword) {
        linkForgotPassword.addEventListener('click', (e) => {
            e.preventDefault();
            showAuthForm('forgot');
        });
    }

    if (btnForgotSubmit) {
        btnForgotSubmit.addEventListener('click', handleForgotPassword);
    }

    if (btnResetSubmit) {
        btnResetSubmit.addEventListener('click', handleResetPassword);
    }

    if (backToLoginFromForgot) {
        backToLoginFromForgot.addEventListener('click', (e) => {
            e.preventDefault();
            showAuthForm('login');
        });
    }

    checkResendTimerOnLoad();
}

function startResendTimer(remaining = RESEND_COOLDOWN_SEC) {
    const btnResend = document.getElementById('btn-resend-code');
    if (!btnResend) return;

    // 1. Set timestamp in localStorage if this is a fresh start
    if (remaining === RESEND_COOLDOWN_SEC) {
        const targetTime = Date.now() + (RESEND_COOLDOWN_SEC * 1000);
        localStorage.setItem('kakuro-resend-target', targetTime);
    }

    // 2. Disable Link UI
    btnResend.classList.add('disabled');

    // 3. Clear existing interval if any
    if (resendTimerInterval) clearInterval(resendTimerInterval);

    // 4. Update UI immediately
    updateResendUI(remaining);

    // 5. Start Interval
    resendTimerInterval = setInterval(() => {
        // Calculate real remaining time based on storage (prevents drift/refresh cheats)
        const targetTime = parseInt(localStorage.getItem('kakuro-resend-target') || '0');
        const now = Date.now();
        const secondsLeft = Math.ceil((targetTime - now) / 1000);

        if (secondsLeft <= 0) {
            stopResendTimer();
        } else {
            updateResendUI(secondsLeft);
        }
    }, 1000);
}

function stopResendTimer() {
    if (resendTimerInterval) {
        clearInterval(resendTimerInterval);
        resendTimerInterval = null;
    }

    localStorage.removeItem('kakuro-resend-target');

    const btnResend = document.getElementById('btn-resend-code');
    if (btnResend) {
        btnResend.classList.remove('disabled');
        btnResend.innerHTML = 'Resend code'; // Restore original text
    }
}

function updateResendUI(seconds) {
    const btnResend = document.getElementById('btn-resend-code');
    if (btnResend) {
        btnResend.innerHTML = `Resend in <span class="resend-timer-count">${seconds}s</span>`;
    }
}

function checkResendTimerOnLoad() {
    const targetTime = localStorage.getItem('kakuro-resend-target');
    if (targetTime) {
        const now = Date.now();
        const secondsLeft = Math.ceil((parseInt(targetTime) - now) / 1000);

        if (secondsLeft > 0) {
            startResendTimer(secondsLeft);
        } else {
            localStorage.removeItem('kakuro-resend-target');
        }
    }
}

function openAuthModal(form = 'login') {
    const authModal = document.getElementById('auth-modal');
    if (authModal) {
        authModal.style.display = 'block';
        showAuthForm(form);
    }
}

function closeAuthModal() {
    const authModal = document.getElementById('auth-modal');
    if (authModal) {
        authModal.style.display = 'none';
        clearAuthErrors();
    }
}

function showAuthForm(form) {
    console.log(`showAuthForm called with '${form}'`);
    const loginForm = document.getElementById('login-form');
    const registerForm = document.getElementById('register-form');
    const verificationForm = document.getElementById('verification-form');

    // Reset all
    document.querySelectorAll('.auth-form').forEach(f => f.style.display = 'none');

    if (form === 'login') {
        if (loginForm) loginForm.style.display = 'block';
    } else if (form === 'register') {
        if (registerForm) registerForm.style.display = 'block';
    } else if (form === 'verify' || form === 'verification') {
        if (verificationForm) {
            verificationForm.style.display = 'block';
            // Focus first code input
            setTimeout(() => {
                const code1 = document.getElementById('code-1');
                if (code1) code1.focus();
            }, 100);
        }
    } else if (form === 'forgot') {
        const forgotForm = document.getElementById('forgot-password-form');
        if (forgotForm) forgotForm.style.display = 'block';
    } else if (form === 'reset') {
        const resetForm = document.getElementById('reset-password-form');
        if (resetForm) resetForm.style.display = 'block';
    }
    clearAuthErrors();
}

function clearAuthErrors() {
    const loginError = document.getElementById('login-error');
    const registerError = document.getElementById('register-error');
    const verificationError = document.getElementById('verification-error');

    if (loginError) {
        loginError.textContent = '';
        loginError.classList.remove('show');
    }
    if (registerError) {
        registerError.textContent = '';
        registerError.classList.remove('show');
    }
    if (verificationError) {
        verificationError.textContent = '';
        verificationError.classList.remove('show');
    }

    const forgotError = document.getElementById('forgot-error');
    const forgotSuccess = document.getElementById('forgot-success');
    const resetError = document.getElementById('reset-error');

    if (forgotError) {
        forgotError.textContent = '';
        forgotError.classList.remove('show');
    }
    if (forgotSuccess) {
        forgotSuccess.textContent = '';
        forgotSuccess.style.display = 'none';
    }
    if (resetError) {
        resetError.textContent = '';
        resetError.classList.remove('show');
    }

    // Clear code inputs
    document.querySelectorAll('.code-input').forEach(input => {
        input.classList.remove('error');
    });
}

function showAuthError(form, message) {
    const errorEl = document.getElementById(`${form}-error`);
    if (errorEl) {
        errorEl.textContent = message;
        errorEl.classList.add('show');
    }

    // Shake code inputs on verification error
    if (form === 'verification' || form === 'verify') {
        document.querySelectorAll('.code-input').forEach(input => {
            input.classList.add('error');
        });
    }
}

function setupCodeInputs() {
    const inputs = document.querySelectorAll('.code-input');
    inputs.forEach((input, index) => {
        input.addEventListener('input', (e) => {
            if (e.target.value.length === 1 && index < inputs.length - 1) {
                inputs[index + 1].focus();
            }

            // Auto-submit if all 6 filled
            const digits = Array.from(inputs).map(i => i.value).join('');
            if (digits.length === 6) {
                setTimeout(() => handleVerifyEmail(), 100);
            }
        });

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Backspace' && !e.target.value && index > 0) {
                inputs[index - 1].focus();
            }
            // Auto-submit on Enter
            const digits = Array.from(inputs).map(i => i.value).join('');
            if (e.key === 'Enter') {
                if (digits.length === 6) {
                    handleVerifyEmail();
                }
            }
        });

        // Handle Paste
        input.addEventListener('paste', (e) => {
            e.preventDefault();
            const pasteData = (e.clipboardData || window.clipboardData).getData('text');
            const digits = pasteData.replace(/\D/g, '').split('').slice(0, 6);

            if (digits.length > 0) {
                digits.forEach((digit, i) => {
                    if (inputs[i]) {
                        inputs[i].value = digit;
                    }
                });

                // Focus the next empty input or the last digit
                const nextIndex = Math.min(digits.length, inputs.length - 1);
                inputs[nextIndex].focus();

                // Auto-submit if 6 digits pasted
                if (digits.length === 6) {
                    setTimeout(() => handleVerifyEmail(), 100);
                }
            }
        });
    });
}

async function handleVerifyEmail() {
    // Get code from inputs
    const codeInputs = document.querySelectorAll('.code-input');
    const code = Array.from(codeInputs).map(input => input.value).join('');

    if (code.length !== 6) {
        showAuthError('verification', 'Please enter the complete 6-digit code');
        return;
    }

    // Disable inputs during verification
    codeInputs.forEach(input => input.disabled = true);
    const btnVerify = document.getElementById('btn-verify-submit');
    if (btnVerify) {
        btnVerify.disabled = true;
        btnVerify.textContent = "Verifying...";
    }

    try {
        const res = await fetch('/auth/verify-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email: pendingVerificationEmail,
                code
            })
        });

        const data = await res.json();

        if (res.ok) {
            showToast('Email verified! You are now logged in.');

            // 1. Set tokens in localStorage and state
            setTokens(data.access_token, data.refresh_token);

            // 2. Set user data in state
            state.user = data.user;

            // 3. Update the UI buttons (Hide Login/Register, Show User Menu)
            updateAuthUI();

            // 4. Close the modal
            closeAuthModal();
        } else {
            codeInputs.forEach(input => input.disabled = false);
            showAuthError('verification', data.detail || 'Invalid verification code');

            // Clear inputs and focus first one
            codeInputs.forEach(input => input.value = '');
            codeInputs[0].focus();
        }
    } catch (e) {
        codeInputs.forEach(input => input.disabled = false);
        showAuthError('verification', 'Network error. Please try again.');
        console.error(e);
    } finally {
        if (btnVerify) {
            btnVerify.disabled = false;
            btnVerify.textContent = "Verify Email";
        }
    }
}

async function handleResendCode() {
    if (!pendingVerificationEmail) return;

    const btnResend = document.getElementById('btn-resend-code');
    if (btnResend) {
        btnResend.disabled = true;
        btnResend.textContent = 'Sending...';
    }

    try {
        const res = await fetch('/auth/resend-verification', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: pendingVerificationEmail })
        });

        const data = await res.json();

        if (res.ok) {
            showToast(data.message || 'Verification code resent!');
            // Clear inputs and focus first one
            const codeInputs = document.querySelectorAll('.code-input');
            codeInputs.forEach(input => input.value = '');
            if (codeInputs[0]) codeInputs[0].focus();

            startResendTimer();
        } else {
            showAuthError('verification', data.detail || 'Failed to resend code');
        }
    } catch (e) {
        showAuthError('verification', 'Network error. Please try again.');
    } finally {
        if (btnResend) {
            btnResend.disabled = false;
            btnResend.textContent = 'Send Again';
        }
    }
}

async function handleLogin() {
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;

    if (!email || !password) {
        showAuthError('login', 'Please enter email and password');
        return;
    }

    const btnLogin = document.getElementById('btn-login-submit');
    if (btnLogin) {
        btnLogin.disabled = true;
        btnLogin.textContent = 'Logging in...';
    }

    try {
        const res = await fetch('/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });

        if (res.status === 403) {
            console.log("Login: Unverified account detected. Switching to verification.");
            // Unverified account
            // Don't close modal, just switch view
            pendingVerificationEmail = email;

            // Update display text
            const displayEl = document.getElementById('verify-email-display');
            if (displayEl) displayEl.textContent = email;

            // Open verification
            if (typeof openAuthModal === 'function') {
                openAuthModal('verify');
            } else {
                showAuthForm('verify');
            }

            showAuthError('verify', "Your account is not verified. Please check your email for the code.");
            return;
        }

        const data = await res.json();

        if (res.ok) {
            setTokens(data.access_token, data.refresh_token);
            await fetchUserProfile();
            closeAuthModal();
            showToast('Welcome back!');
            // Assuming login-form exists and can be reset
            const loginForm = document.getElementById('login-form');
            if (loginForm) loginForm.reset();
        } else {
            let errorMsg = data.detail || 'Login failed';
            if (typeof errorMsg === 'object') {
                if (Array.isArray(errorMsg)) {
                    errorMsg = errorMsg.map(e => {
                        const msg = e.msg;
                        const colonIndex = msg.indexOf(':');
                        return colonIndex !== -1 ? msg.substring(colonIndex + 1).trim() : msg;
                    }).join(', ');
                } else {
                    errorMsg = JSON.stringify(errorMsg);
                }
            }
            showAuthError('login', errorMsg);
        }
    } catch (e) {
        showAuthError('login', 'Network error. Please try again.');
    } finally {
        if (btnLogin) {
            btnLogin.disabled = false;
            btnLogin.textContent = 'Login';
        }
    }
}

async function handleRegister() {
    const username = document.getElementById('register-username').value.trim();
    const email = document.getElementById('register-email').value.trim();
    const password = document.getElementById('register-password').value;

    if (!username || !email || !password) {
        showAuthError('register', 'Please fill in all fields');
        return;
    }

    if (password.length < 6) {
        showAuthError('register', 'Password must be at least 6 characters');
        return;
    }

    const btnRegister = document.getElementById('btn-register-submit');
    if (btnRegister) {
        btnRegister.disabled = true;
        btnRegister.textContent = 'Registering...';
    }

    try {
        const res = await fetch('/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, email, password })
        });

        if (res.status === 403) {
            console.log("Register: Account exists but unverified. Switching to verification.");
            // Account exists but unverified, or new registration requires verification
            pendingVerificationEmail = email;

            // Update display text
            const displayEl = document.getElementById('verify-email-display');
            if (displayEl) displayEl.textContent = email;

            // Open verification
            if (typeof openAuthModal === 'function') {
                openAuthModal('verify');
            } else {
                showAuthForm('verify');
            }

            showAuthError('verify', "Account created/exists but is unverified. Please enter the code sent to your email.");
            return;
        }

        const data = await res.json();

        if (res.ok) {
            // If registration immediately logs in and verifies
            if (data.access_token && data.refresh_token) {
                setTokens(data.access_token, data.refresh_token);
                await fetchUserProfile();
                closeAuthModal();
                showToast('Account created! Welcome!');
            } else {
                // If registration requires email verification
                closeAuthModal(); // Close register modal
                openAuthModal('verify'); // Open verify modal
                const verifyEmailInput = document.getElementById('verify-email');
                if (verifyEmailInput) verifyEmailInput.value = email;
                pendingVerificationEmail = email; // Store email for resend/verify
                showAuthError('verify', data.message || 'Registration successful! Please verify your email.');
            }
            // Assuming register-form exists and can be reset
            const registerForm = document.getElementById('register-form');
            if (registerForm) registerForm.reset();
        } else {
            showAuthError('register', data.detail || 'Registration failed');
        }
    } catch (e) {
        showAuthError('register', 'Network error. Please try again.');
    } finally {
        if (btnRegister) {
            btnRegister.disabled = false;
            btnRegister.textContent = 'Register';
        }
    }
}

async function handleForgotPassword() {
    const email = document.getElementById('forgot-email').value.trim();
    if (!email) {
        showAuthError('forgot', 'Please enter your email');
        return;
    }

    const btnSubmit = document.getElementById('btn-forgot-submit');
    const successEl = document.getElementById('forgot-success');

    if (btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.textContent = 'Sending...';
    }

    try {
        const res = await fetch('/auth/forgot-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        const data = await res.json();
        if (res.ok) {
            if (successEl) {
                successEl.textContent = data.message;
                successEl.style.display = 'block';
            }
            // Optional: Hide button or form
        } else {
            showAuthError('forgot', data.detail || 'Failed to send reset link');
        }
    } catch (e) {
        showAuthError('forgot', 'Network error. Please try again.');
    } finally {
        if (btnSubmit) {
            btnSubmit.disabled = false;
            btnSubmit.textContent = 'Send Reset Link';
        }
    }
}

async function handleResetPassword() {
    const newPassword = document.getElementById('reset-password-new').value;
    const confirmPassword = document.getElementById('reset-password-confirm').value;

    if (!newPassword || !confirmPassword) {
        showAuthError('reset', 'Please fill in all fields');
        return;
    }

    if (newPassword !== confirmPassword) {
        showAuthError('reset', 'Passwords do not match');
        return;
    }

    if (newPassword.length < 6) {
        showAuthError('reset', 'Password must be at least 6 characters');
        return;
    }

    const btnSubmit = document.getElementById('btn-reset-submit');
    if (btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.textContent = 'Resetting...';
    }

    try {
        const res = await fetch('/auth/reset-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                token: state.resetToken,
                new_password: newPassword
            })
        });
        const data = await res.json();
        if (res.ok) {
            showToast('Password reset successful! You can now log in.');
            // Clear form
            const newPasswordInput = document.getElementById('reset-password-new');
            const confirmPasswordInput = document.getElementById('reset-password-confirm');
            if (newPasswordInput) newPasswordInput.value = '';
            if (confirmPasswordInput) confirmPasswordInput.value = '';

            closeAuthModal();
            openAuthModal('login');
        } else {
            showAuthError('reset', data.detail || 'Failed to reset password');
        }
    } catch (e) {
        showAuthError('reset', 'Network error. Please try again.');
    } finally {
        if (btnSubmit) {
            btnSubmit.disabled = false;
            btnSubmit.textContent = 'Reset Password';
        }
    }
}

function handleLogout() {
    state.user = null;
    state.accessToken = null;
    state.refreshToken = null;
    localStorage.removeItem('kakuro-access-token');
    localStorage.removeItem('kakuro-refresh-token');
    updateAuthUI();
    showToast('Logged out');

    // Close user dropdown
    const userMenu = document.getElementById('user-menu');
    if (userMenu) userMenu.classList.remove('open');
}

window.logout = handleLogout;

function handleOAuth(provider) {
    // Redirect to OAuth endpoint
    window.location.href = `/auth/${provider}`;
}

function setTokens(accessToken, refreshToken) {
    state.accessToken = accessToken;
    state.refreshToken = refreshToken;
    localStorage.setItem('kakuro-access-token', accessToken);
    localStorage.setItem('kakuro-refresh-token', refreshToken);
}

async function fetchUserProfile() {
    if (!state.accessToken) return;

    try {
        const res = await fetch('/auth/me', {
            headers: getAuthHeaders()
        });

        if (res.ok) {
            state.user = await res.json();
            updateAuthUI();
        } else if (res.status === 401) {
            // Token expired, try to refresh
            const refreshed = await refreshAccessToken();
            if (refreshed) {
                await fetchUserProfile();
            } else {
                handleLogout();
            }
        }
    } catch (e) {
        console.error('Failed to fetch user profile:', e);
    }
}

async function refreshAccessToken() {
    if (!state.refreshToken) return false;

    try {
        const res = await fetch('/auth/refresh', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: state.refreshToken })
        });

        if (res.ok) {
            const data = await res.json();
            setTokens(data.access_token, data.refresh_token);
            return true;
        }
    } catch (e) {
        console.error('Token refresh failed:', e);
    }
    return false;
}

function getAuthHeaders() {
    const headers = {};
    if (state.accessToken) {
        headers['Authorization'] = `Bearer ${state.accessToken}`;
    }
    return headers;
}

function updateAuthUI() {
    const authButtons = document.getElementById('auth-buttons');
    const userMenu = document.getElementById('user-menu');
    const userName = document.getElementById('user-name');
    const userEmail = document.getElementById('user-email');
    const userSolved = document.getElementById('user-solved');
    const btnAdmin = document.getElementById('btn-admin-nav');

    if (state.user) {
        // Logged in
        if (authButtons) authButtons.style.display = 'none';
        if (userMenu) userMenu.style.display = 'block';
        if (userName) userName.textContent = state.user.username;
        if (userEmail) userEmail.textContent = state.user.email;
        if (userSolved) userSolved.textContent = `${state.user.kakuros_solved} puzzles solved`;
        const userScoreDisplay = document.getElementById('user-score-display');
        if (userScoreDisplay) userScoreDisplay.textContent = `${state.user.total_score || 0} pts`;

        // Admin button
        if (btnAdmin) {
            btnAdmin.style.display = state.user.is_admin ? 'inline-flex' : 'none';
        }
    } else {
        // Logged out
        if (authButtons) authButtons.style.display = 'flex';
        if (userMenu) userMenu.style.display = 'none';
        if (btnAdmin) btnAdmin.style.display = 'none';
    }
}

// End of consolidated auth module.


function setupMobile() {
    // 1. Generate Button in Mobile Modal
    const btnMobileGenerate = document.getElementById('btn-mobile-generate');
    const mobileDiffSelect = document.getElementById('mobile-difficulty-select');
    const desktopDiffSelect = document.getElementById('difficulty-select');
    const settingsModal = document.getElementById('mobile-settings-modal');

    const closeOtherModals = (exceptId) => {
        const modalIds = [
            'mobile-settings-modal',
            'mobile-notebook-modal',
            'library-modal',
            'auth-modal'
        ];

        modalIds.forEach(id => {
            if (id !== exceptId) {
                const el = document.getElementById(id);
                if (el) el.style.display = 'none';
            }
        });
    };

    if (btnMobileGenerate) {
        btnMobileGenerate.addEventListener('click', () => {
            // Sync value to desktop select (so fetchPuzzle uses it)
            if (desktopDiffSelect) desktopDiffSelect.value = mobileDiffSelect.value;

            // Close modal
            settingsModal.style.display = 'none';

            // Generate
            fetchPuzzle();
        });
    }

    // 2. Navigation Handlers
    const navPlay = document.getElementById('nav-play');
    if (navPlay && settingsModal) {
        navPlay.addEventListener('click', () => {
            if (settingsModal.style.display === 'block') {
                settingsModal.style.display = 'none';
            } else {
                closeOtherModals('mobile-settings-modal');
                settingsModal.style.display = 'block';
            }
        });
    }

    // 2. Notebook Button: Opens Notebook Modal
    const navNotebook = document.getElementById('nav-notebook');
    const notebookModal = document.getElementById('mobile-notebook-modal');
    const mobileTextarea = document.getElementById('mobile-notebook-textarea');
    const desktopTextarea = document.getElementById('notebook-textarea');

    if (navNotebook && notebookModal && mobileTextarea) {
        navNotebook.addEventListener('click', () => {
            if (notebookModal.style.display === 'block') {
                notebookModal.style.display = 'none';
            } else {
                closeOtherModals('mobile-notebook-modal');
                // Sync state -> mobile textarea
                mobileTextarea.value = state.notebook || '';
                notebookModal.style.display = 'block';
            }
        });

        // Save on input
        mobileTextarea.addEventListener('input', (e) => {
            state.notebook = e.target.value;
            // Sync back to desktop textarea if it exists (for seamless switching)
            if (desktopTextarea) desktopTextarea.value = state.notebook;
            triggerAutosave();
        });
    }

    // 3. Notes Button (Tools): Toggles Note Mode
    const navNotes = document.getElementById('nav-notes');
    if (navNotes) {
        navNotes.addEventListener('click', () => {
            toggleNoteMode();

            // Visual feedback
            const isActive = state.noteMode;
            navNotes.style.color = isActive ? 'var(--success-color)' : '';
            // Optional: Haptic feedback
            if (navigator.vibrate) navigator.vibrate(20);

            showToast(isActive ? "Note Mode ON" : "Note Mode OFF");
        });
    }

    const navCheck = document.getElementById('nav-check');
    if (navCheck) {
        navCheck.addEventListener('click', () => {
            checkPuzzle();
        });
    }



    const navLibrary = document.getElementById('nav-library');
    const libraryModal = document.getElementById('library-modal');

    if (navLibrary && libraryModal) {
        navLibrary.addEventListener('click', () => {
            if (libraryModal.style.display === 'block') {
                libraryModal.style.display = 'none';
            } else {
                closeOtherModals('library-modal');
                openLibrary();
            }
        });
    }

    const navProfile = document.getElementById('nav-profile');
    const authModal = document.getElementById('auth-modal');

    if (navProfile) {
        navProfile.addEventListener('click', () => {
            if (state.user) {
                // If logged in, we use confirm (native dialog, cannot toggle)
                if (confirm(`Logged in as ${state.user.username}. Logout?`)) {
                    handleLogout();
                }
            } else {
                // If logged out, toggle the Auth Modal
                if (authModal && authModal.style.display === 'block') {
                    closeAuthModal();
                } else {
                    closeOtherModals('auth-modal');
                    openAuthModal('login');
                }
            }
        });
    }


    setupNumpad();
}

function setupNumpad() {
    const numpad = document.getElementById('mobile-numpad');
    if (!numpad) return;

    numpad.style.display = 'none';
    numpad.style.pointerEvents = 'none';

    // Prevent clicking the numpad from closing it (propagation issue)
    numpad.addEventListener('click', (e) => e.stopPropagation());

    // Handle button clicks
    numpad.querySelectorAll('button').forEach(btn => {
        btn.style.pointerEvents = 'auto';

        btn.addEventListener('click', (e) => {
            e.stopPropagation(); // Don't deselect cell
            const val = btn.dataset.val;

            if (val === 'del') {
                handleInputDelete();
            } else {
                handleInputNumber(val);
            }
        });
    });

    // Hide numpad on scroll to prevent it floating awkwardly
    window.addEventListener('scroll', () => {
        if (window.innerWidth <= 768) hideNumpad();
    });
}

function isBoardFull() {
    if (!state.puzzle) return false;
    for (let r = 0; r < state.puzzle.height; r++) {
        for (let c = 0; c < state.puzzle.width; c++) {
            const cell = state.userGrid[r][c];
            // If it's a white cell and has no value (null), board is not full
            if (cell.type === 'WHITE' && !cell.userValue) {
                return false;
            }
        }
    }
    return true;
}

function handleInputNumber(numStr) {
    if (state.noteMode && state.selectedCells.size > 0) {
        handleNoteInput(numStr);
    } else if (!state.noteMode && state.selected) {
        const { r, c } = state.selected;
        if (state.userGrid[r][c].type === 'WHITE') {
            const oldValue = state.userGrid[r][c].userValue;
            state.userGrid[r][c].userValue = parseInt(numStr);
            state.showErrors = false;

            logInteraction('INPUT', {
                row: r,
                col: c,
                oldValue: oldValue,
                newValue: numStr
            });

            renderBoard();
            triggerAutosave();

            if (window.innerWidth <= 768) {
                hideNumpad();
            }

            // AUTO-CHECK LOGIC (Works on Desktop & Mobile)
            // If the board is full and correct, trigger the win immediately.
            if (checkIfSolved()) {
                state.puzzle.status = "solved";
                logInteraction('SOLVED');
                
                // Show visual feedback (Green cells)
                state.showErrors = true; 
                renderBoard();
                
                showToast("Perfect! Puzzle Solved!");
                
                // Slight delay before modal so user sees the green board
                setTimeout(() => {
                    showRatingModal();
                }, 500);
            }
        }
    }
}

function handleInputDelete() {
    if (state.noteMode && state.selectedCells.size > 0) {
        deleteSelectedNotes();
    } else if (!state.noteMode && state.selected) {
        const { r, c } = state.selected;
        if (state.userGrid[r][c].type === 'WHITE') {
            const oldValue = state.userGrid[r][c].userValue;
            state.userGrid[r][c].userValue = null;
            state.showErrors = false;

            logInteraction('DELETE', {
                row: r,
                col: c,
                oldValue: oldValue,
                newValue: null
            });

            renderBoard();
            triggerAutosave();
            if (window.innerWidth <= 768) hideNumpad();
        }
    }
}

let autosaveTimer = null;

function triggerAutosave() {
    // Clear existing timer
    if (autosaveTimer) clearTimeout(autosaveTimer);

    // Set new timer (save after 1 second of inactivity)
    autosaveTimer = setTimeout(() => {
        saveCurrentState(true); // true = silent mode
    }, 2000);
}

function initSidebarToggles() {
    const toggleLeft = document.getElementById('toggle-left');
    const toggleRight = document.getElementById('toggle-right');
    const sidebarLeft = document.querySelector('.sidebar-left');
    const sidebarRight = document.querySelector('.sidebar-right');
    const mainLayout = document.querySelector('.main-layout');

    if (toggleLeft && sidebarLeft) {
        toggleLeft.addEventListener('click', () => {
            sidebarLeft.classList.toggle('collapsed');
            toggleLeft.textContent = sidebarLeft.classList.contains('collapsed') ? '▶' : '◀';
            updateLayoutClasses();
        });
    }

    if (toggleRight && sidebarRight) {
        toggleRight.addEventListener('click', () => {
            sidebarRight.classList.toggle('collapsed');
            toggleRight.textContent = sidebarRight.classList.contains('collapsed') ? '◀' : '▶';
            updateLayoutClasses();
        });
    }

    function updateLayoutClasses() {
        const leftCollapsed = sidebarLeft.classList.contains('collapsed');
        const rightCollapsed = sidebarRight.classList.contains('collapsed');

        mainLayout.classList.remove('left-collapsed', 'right-collapsed', 'both-collapsed');

        if (leftCollapsed && rightCollapsed) {
            mainLayout.classList.add('both-collapsed');
        } else if (leftCollapsed) {
            mainLayout.classList.add('left-collapsed');
        } else if (rightCollapsed) {
            mainLayout.classList.add('right-collapsed');
        }
    }
}

async function openLeaderboard() {
    const modal = document.getElementById('leaderboard-modal');
    if (modal) {
        modal.style.display = 'block';
        fetchLeaderboardData();
    }
}

async function fetchLeaderboardData() {
    const body = document.getElementById('leaderboard-body');
    const loading = document.getElementById('leaderboard-loading');

    if (body) body.innerHTML = '';
    if (loading) loading.style.display = 'block';

    try {
        const endpoint = state.leaderboardType === 'monthly' ? '/leaderboard/monthly' : '/leaderboard/all-time';
        const res = await fetch(endpoint);
        if (!res.ok) throw new Error("Failed to fetch leaderboard");
        const data = await res.json();
        state.leaderboardData = data;
        renderLeaderboard();
    } catch (e) {
        console.error("Leaderboard error:", e);
        if (body) body.innerHTML = '<tr><td colspan="4" style="text-align:center">Error loading rankings</td></tr>';
    } finally {
        if (loading) loading.style.display = 'none';
    }
}

function renderLeaderboard() {
    const body = document.getElementById('leaderboard-body');
    if (!body) return;

    body.innerHTML = '';
    state.leaderboardData.forEach((entry, index) => {
        const tr = document.createElement('tr');
        if (state.user && entry.username === state.user.username) {
            tr.classList.add('current-user');
        }

        const avatar = entry.avatar ? `<img src="${entry.avatar}" class="leaderboard-avatar">` : `<span class="leaderboard-avatar">👤</span>`;

        tr.innerHTML = `
            <td class="rank-cell">#${index + 1}</td>
            <td class="user-cell">
                ${avatar}
                <span>${entry.username}</span>
            </td>
            <td>${entry.solved}</td>
            <td class="score-cell">${entry.score}</td>
        `;
        body.appendChild(tr);
    });

    if (state.leaderboardData.length === 0) {
        body.innerHTML = '<tr><td colspan="4" style="text-align:center">No rankings yet this month</td></tr>';
    }
}

// Call initSidebarToggles after the DOM is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSidebarToggles);
} else {
    initSidebarToggles();
}