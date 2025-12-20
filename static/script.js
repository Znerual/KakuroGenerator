const state = {
    puzzle: null,
    userGrid: [],
    selected: null,
    rowNotes: [],    // Notes for each row (displayed on the left)
    colNotes: [],    // Notes for each column (displayed on top)
    editingNote: null, // { type: 'row'|'col', index: number }
    showErrors: false
};

const boardEl = document.getElementById('kakuro-board');
const btnGenerate = document.getElementById('btn-generate');
const btnCheck = document.getElementById('btn-check');

function init() {
    btnGenerate.addEventListener('click', fetchPuzzle);
    btnCheck.addEventListener('click', checkPuzzle);
    window.addEventListener('keydown', handleGlobalKey);
    fetchPuzzle();
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

        if (!data || !data.grid) {
            throw new Error("Invalid data format received from server");
        }

        state.puzzle = data;
        state.userGrid = data.grid.map(row => row.map(cell => ({
            ...cell,
            userValue: null
        })));
        state.selected = null;
        state.rowNotes = Array(data.height).fill('');
        state.colNotes = Array(data.width).fill('');
        state.editingNote = null;
        state.showErrors = false;

        console.log("State updated, rendering board...");
        renderBoard();
    } catch (e) {
        console.error("Error in fetchPuzzle:", e);
        alert("Error generating puzzle: " + e.message);
    } finally {
        btnGenerate.textContent = "New Puzzle";
        btnGenerate.disabled = false;
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
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.5s ease';
        setTimeout(() => toast.remove(), 500);
    }, 3000);
}

init();
