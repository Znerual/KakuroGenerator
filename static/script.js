const state = {
    puzzle: null,
    userGrid: [],
    selected: null,
    rowNotes: [],    // Notes for each row (displayed on the left)
    colNotes: [],    // Notes for each column (displayed on top)
    editingNote: null, // { type: 'row'|'col', index: number }
    showErrors: false,
    currentTab: 'started' // 'started' or 'solved'
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
    btnGenerate.addEventListener('click', fetchPuzzle);
    btnCheck.addEventListener('click', checkPuzzle);
    btnSave.addEventListener('click', saveCurrentState);
    btnLibrary.addEventListener('click', openLibrary);
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

async function fetchPuzzle() {
    btnGenerate.textContent = "Generating...";
    btnGenerate.disabled = true;
    try {
        const difficultySelect = document.getElementById('difficulty-select');
        const difficulty = difficultySelect ? difficultySelect.value : 'medium';

        let width = 10, height = 10;
        if (difficulty === 'very_easy') {
            width = 7;
            height = 7;
        } else if (difficulty === 'easy') {
            width = 8;
            height = 8;
        }

        const res = await fetch(`/generate?difficulty=${difficulty}&width=${width}&height=${height}`);
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
    state.rowNotes = data.rowNotes || Array(data.height).fill('');
    state.colNotes = data.colNotes || Array(data.width).fill('');
    state.editingNote = null;
    state.showErrors = false;

    console.log("State updated, rendering board...");
    renderBoard();
}

async function saveCurrentState() {
    if (!state.puzzle) return;

    const data = {
        id: state.puzzle.id,
        width: state.puzzle.width,
        height: state.puzzle.height,
        difficulty: state.puzzle.difficulty,
        grid: state.puzzle.grid,
        userGrid: state.userGrid,
        status: state.puzzle.status || "started",
        rowNotes: state.rowNotes,
        colNotes: state.colNotes
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

    const { width, height } = state.puzzle;

    // Create column notes row (top margin)
    const colNotesRow = document.createElement('div');
    colNotesRow.className = 'col-notes-row';
    colNotesRow.style.gridTemplateColumns = `40px repeat(${width}, 60px)`;

    // Empty corner cell
    const cornerCell = document.createElement('div');
    cornerCell.className = 'margin-corner';
    colNotesRow.appendChild(cornerCell);

    // Column note cells
    for (let c = 0; c < width; c++) {
        const noteCell = createNoteCell('col', c, state.colNotes[c]);
        colNotesRow.appendChild(noteCell);
    }
    wrapper.appendChild(colNotesRow);

    // Create main content area (row notes + grid)
    const mainArea = document.createElement('div');
    mainArea.className = 'main-grid-area';
    mainArea.style.gridTemplateColumns = `40px repeat(${width}, 60px)`;
    mainArea.style.gridTemplateRows = `repeat(${height}, 60px)`;

    for (let r = 0; r < height; r++) {
        // Row note cell
        const rowNoteCell = createNoteCell('row', r, state.rowNotes[r]);
        mainArea.appendChild(rowNoteCell);

        // Grid cells for this row
        for (let c = 0; c < width; c++) {
            const cellData = state.userGrid[r][c];
            const el = createGridCell(cellData, r, c);
            mainArea.appendChild(el);
        }
    }
    wrapper.appendChild(mainArea);

    boardContainer.insertBefore(wrapper, boardEl);

    // Keep the original grid hidden but maintain reference
    boardEl.style.display = 'none';
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
    } else {
        state.colNotes[index] = value;
    }
    state.editingNote = null;
    renderBoard();
}

function createGridCell(cellData, r, c) {
    const el = document.createElement('div');
    el.className = 'cell';

    const isSelected = state.selected && state.selected.r === r && state.selected.c === c;

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

        if (cellData.userValue) {
            el.textContent = cellData.userValue;
            if (state.showErrors) {
                if (cellData.userValue === cellData.value) {
                    el.classList.add('correct');
                } else {
                    el.classList.add('incorrect');
                }
            }
        } else if (state.showErrors) {
            // Highlight empty white cells as incorrect if checking
            el.classList.add('incorrect');
        }

        el.addEventListener('click', () => selectCell(r, c));
    }

    return el;

}

function selectCell(r, c) {
    // Only allow selecting white cells via click
    if (state.userGrid[r][c].type === 'WHITE') {
        state.selected = { r, c };
        renderBoard();
    }
}

function handleGlobalKey(e) {
    if (!state.selected) return;

    const { r, c } = state.selected;
    const { width, height } = state.puzzle;

    // Numbers 1-9
    if (e.key >= '1' && e.key <= '9') {
        // Only if current cell is white
        if (state.userGrid[r][c].type === 'WHITE') {
            state.userGrid[r][c].userValue = parseInt(e.key);
            state.showErrors = false; // Hide errors when user types
            renderBoard();
        }
        return;
    }

    // Delete / Backspace
    if (e.key === 'Backspace' || e.key === 'Delete') {
        if (state.userGrid[r][c].type === 'WHITE') {
            state.userGrid[r][c].userValue = null;
            state.showErrors = false; // Hide errors when user deletes
            renderBoard();
        }
        return;
    }

    // Arrows
    let nr = r, nc = c;
    if (e.key === 'ArrowUp') nr = Math.max(0, r - 1);
    else if (e.key === 'ArrowDown') nr = Math.min(height - 1, r + 1);
    else if (e.key === 'ArrowLeft') nc = Math.max(0, c - 1);
    else if (e.key === 'ArrowRight') nc = Math.min(width - 1, c + 1);
    else return; // Not handled

    e.preventDefault();
    state.selected = { r: nr, c: nc };
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
        saveCurrentState();
    } else if (allFilled) {
        showToast("Almost there, but some numbers are wrong.");
    } else {
        showToast("Keep going! Some cells are missing or incorrect.");
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

init();
