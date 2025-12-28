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
    userComment: '' // User's comment about the puzzle
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
    console.log('btnNoteMode:', btnNoteMode);
    
    btnGenerate.addEventListener('click', fetchPuzzle);
    btnCheck.addEventListener('click', checkPuzzle);
    btnSave.addEventListener('click', saveCurrentState);
    btnLibrary.addEventListener('click', openLibrary);
    
    if (btnNoteMode) {
        console.log('Adding event listener to note mode button');
        btnNoteMode.addEventListener('click', function() {
            console.log('Note mode button clicked!');
            toggleNoteMode();
        });
    } else {
        console.log('Note mode button not found!');
    }
    
    if (btnNotebook) {
        btnNotebook.addEventListener('click', toggleNotebook);
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
    fetchPuzzle();
}

function toggleNotebook() {
    state.notebookOpen = !state.notebookOpen;
    const notebookPanel = document.getElementById('notebook-panel');
    const btnNotebook = document.getElementById('btn-notebook');
    
    if (notebookPanel) {
        notebookPanel.classList.toggle('open', state.notebookOpen);
    }
    if (btnNotebook) {
        btnNotebook.classList.toggle('active', state.notebookOpen);
    }
}

function toggleNoteMode() {
    console.log('toggleNoteMode called, current state:', state.noteMode);
    const btnNoteMode = document.getElementById('btn-note-mode');
    const noteHelp = document.getElementById('note-help');
    state.noteMode = !state.noteMode;
    console.log('New note mode state:', state.noteMode);
    if (btnNoteMode) {
        btnNoteMode.classList.toggle('active', state.noteMode);
        btnNoteMode.textContent = state.noteMode ? 'Note Mode: ON' : 'Note Mode: OFF';
        console.log('Button text updated to:', btnNoteMode.textContent);
    }
    if (noteHelp) {
        noteHelp.style.display = state.noteMode ? 'block' : 'none';
    }
    if (!state.noteMode) {
        state.selectedCells.clear();
    }
    renderBoard();
}

async function fetchPuzzle() {
    btnGenerate.textContent = "Generating...";
    btnGenerate.disabled = true;
    try {
        const difficultySelect = document.getElementById('difficulty-select');
        const difficulty = difficultySelect ? difficultySelect.value : 'medium';

        const res = await fetch(`/generate?difficulty=${difficulty}`);
        if (!res.ok) throw new Error("Failed to fetch");
        const data = await res.json();
        console.log("Received data:", data);

        loadPuzzleIntoState(data);
    } catch (e) {
        console.error("Error in fetchPuzzle:", e);
        alert("Error generating puzzle: " + e.message);
    } finally {
        btnGenerate.textContent = "New Puzzle";
        btnGenerate.disabled = false;
    }
}

function loadPuzzleIntoState(data) {
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
    state.rating = data.rating || 0;
    state.userComment = data.userComment || '';
    state.editingNote = null;
    state.showErrors = false;
    state.noteMode = false;
    const btnNoteMode = document.getElementById('btn-note-mode');
    if (btnNoteMode) {
        btnNoteMode.classList.remove('active');
        btnNoteMode.textContent = 'Note Mode: OFF';
    }

    // Update notebook textarea if it exists
    const notebookTextarea = document.getElementById('notebook-textarea');
    if (notebookTextarea) {
        notebookTextarea.value = state.notebook;
    }

    // Calculate grid bounds
    calculateGridBounds();

    console.log("State updated, rendering board...");
    renderBoard();
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

async function saveCurrentState() {
    if (!state.puzzle) return;

    // Save current notebook content
    const notebookTextarea = document.getElementById('notebook-textarea');
    if (notebookTextarea) {
        state.notebook = notebookTextarea.value;
    }

    const data = {
        id: state.puzzle.id,
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
        rating: state.rating,
        userComment: state.userComment
    };

    try {
        const res = await fetch('/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (res.ok) {
            showToast("Progress Saved!");
        } else {
            showToast("Failed to save progress.");
        }
    } catch (e) {
        console.error("Save error:", e);
        showToast("Error saving progress.");
    }
}

async function openLibrary() {
    libraryModal.style.display = 'block';
    renderLibrary();
}

async function renderLibrary() {
    libraryList.innerHTML = '<p>Loading puzzles...</p>';
    try {
        const res = await fetch('/list_saved');
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
                        <h3>${p.difficulty.replace('_', ' ').toUpperCase()}</h3>
                        <p>${p.width}x${p.height}</p>
                        <p>${new Date(p.timestamp).toLocaleString()}</p>
                    </div>
                    <button class="delete-btn" onclick="deletePuzzle(event, '${p.id}')">&times;</button>
                `;
                card.addEventListener('click', () => loadSavedPuzzle(p.id));
                libraryList.appendChild(card);
            });
    } catch (e) {
        libraryList.innerHTML = '<p>Error loading library.</p>';
    }
}

async function loadSavedPuzzle(id) {
    try {
        const res = await fetch(`/load/${id}`);
        if (!res.ok) throw new Error("Failed to load");
        const data = await res.json();
        loadPuzzleIntoState(data);
        libraryModal.style.display = 'none';
        showToast("Puzzle Loaded!");
    } catch (e) {
        alert("Error loading puzzle: " + e.message);
    }
}

async function deletePuzzle(event, id) {
    event.stopPropagation();
    if (!confirm("Delete this puzzle?")) return;

    try {
        const res = await fetch(`/delete/${id}`, { method: 'DELETE' });
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
    // Add all boundary notes as absolutely positioned elements
    for (let r = minRow; r <= maxRow; r++) {
        for (let c = minCol; c <= maxCol; c++) {
            // Right boundary (between this cell and next)
            if (c < maxCol) {
                const rightKey = `${r},${c}:${r},${c+1}`;
                if (state.cellNotes[rightKey]) {
                    const note = document.createElement('div');
                    note.className = 'boundary-note-overlay boundary-vertical';
                    note.textContent = state.cellNotes[rightKey];
                    
                    // Position between columns
                    const colIndex = c - minCol;
                    const rowIndex = r - minRow;
                    // 40px for row labels, then colIndex * 60px to get to the cell, +60px to get to right edge
                    const left = 40 + (colIndex + 1) * 60;
                    const top = rowIndex * 60 + 30; // Center vertically in the cell
                    
                    note.style.left = `${left}px`;
                    note.style.top = `${top}px`;
                    container.appendChild(note);
                }
            }
            
            // Bottom boundary (between this cell and below)
            if (r < maxRow) {
                const bottomKey = `${r},${c}:${r+1},${c}`;
                if (state.cellNotes[bottomKey]) {
                    const note = document.createElement('div');
                    note.className = 'boundary-note-overlay boundary-horizontal';
                    note.textContent = state.cellNotes[bottomKey];
                    
                    // Position between rows
                    const colIndex = c - minCol;
                    const rowIndex = r - minRow;
                    // 40px for row labels, then colIndex * 60px, +30px to center horizontally
                    const left = 40 + colIndex * 60 + 30;
                    const top = (rowIndex + 1) * 60; // Bottom edge of current cell
                    
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

function saveNote(type, index, value) {
    if (type === 'row') {
        state.rowNotes[index] = value;
    } else if (type === 'col') {
        state.colNotes[index] = value;
    } else if (type === 'cell') {
        state.cellNotes[index] = value;
    }
    state.editingNote = null;
    renderBoard();
}

function createGridCell(cellData, r, c) {
    const el = document.createElement('div');
    el.className = 'cell';

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
                if (cellData.userValue === cellData.value) {
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
        el.addEventListener('click', (e) => selectCell(r, c, e));
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
            renderBoard();
        } else {
            // Normal selection mode
            state.selected = { r, c };
            state.selectedCells.clear();
            renderBoard();
        }
    }
}

function handleGlobalKey(e) {
    // Don't handle if typing in an input field
    if (e.target.tagName === 'INPUT') return;

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
        if (e.key.length === 1 && /[a-zA-Z0-9]/.test(e.key)) {
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
                btnNoteMode.textContent = 'Note Mode: OFF';
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
            if (state.userGrid[r][c].type === 'WHITE') {
                state.userGrid[r][c].userValue = parseInt(e.key);
                state.showErrors = false;
                renderBoard();
            }
            return;
        }

        // Delete / Backspace
        if (e.key === 'Backspace' || e.key === 'Delete') {
            if (state.userGrid[r][c].type === 'WHITE') {
                state.userGrid[r][c].userValue = null;
                state.showErrors = false;
                renderBoard();
            }
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
            const currentValue = state.cellNotes[boundaryKey] || '';
            state.cellNotes[boundaryKey] = currentValue + char;
            renderBoard();
            return;
        }
    }
    
    // Otherwise, add to corner notes of all selected cells
    state.selectedCells.forEach(key => {
        const currentValue = state.cellNotes[key] || '';
        state.cellNotes[key] = currentValue + char;
    });
    renderBoard();
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
            const currentValue = state.cellNotes[boundaryKey] || '';
            if (currentValue.length > 0) {
                state.cellNotes[boundaryKey] = currentValue.slice(0, -1);
                if (state.cellNotes[boundaryKey] === '') {
                    delete state.cellNotes[boundaryKey];
                }
            }
            renderBoard();
            return;
        }
    }
    
    // Delete last character from corner notes
    state.selectedCells.forEach(key => {
        const currentValue = state.cellNotes[key] || '';
        if (currentValue.length > 0) {
            state.cellNotes[key] = currentValue.slice(0, -1);
            if (state.cellNotes[key] === '') {
                delete state.cellNotes[key];
            }
        }
    });
    renderBoard();
}

function checkPuzzle() {
    if (!state.puzzle) return;

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
                } else if (cell.userValue !== cell.value) {
                    allCorrect = false;
                }
            }
        }
    }

    if (allCorrect) {
        showToast("Perfect! Puzzle Solved!");
        state.puzzle.status = "solved";
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
        renderStars();
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
            star.classList.add('filled');
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
            star.classList.add('filled');
        } else {
            star.classList.remove('filled');
        }
    });
}

function submitRating() {
    const commentTextarea = document.getElementById('rating-comment');
    if (commentTextarea) {
        state.userComment = commentTextarea.value;
    }
    
    // Close modal
    const modal = document.getElementById('rating-modal');
    if (modal) {
        modal.style.display = 'none';
    }
    
    // Save with rating
    saveCurrentState();
    showToast("Thank you for your feedback!");
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