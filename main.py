from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import sys
import webbrowser
import threading
import time
from kakuro import KakuroBoard
from solver import CSPSolver
import uvicorn
import uuid
import datetime
import storage
from pydantic import BaseModel
from typing import List, Optional, Dict

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_base_path():
    if getattr(sys, 'frozen', False):
        # We are running in a bundle (e.g., PyInstaller)
        return sys._MEIPASS
    else:
        # We are running in a normal Python environment
        return os.path.dirname(os.path.abspath(__file__))

BASE_PATH = get_base_path()
STATIC_PATH = os.path.join(BASE_PATH, "static")

app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(STATIC_PATH, "index.html"))

DIFFICULTY_MAP = {
    "very_easy": 0.15,
    "easy": 0.08,
    "medium": 0.15,
    "hard": 0.22
}

DIFFICULTY_SIZE_RANGES = {
    "very_easy": (6, 8),
    "easy": (8, 10),
    "medium": (10, 12),
    "hard": (12, 14)
}

MIN_WHITE_CELLS = 15  # Minimum white cells for a valid puzzle
MAX_RETRIES = 20  # More retries for reliability

def validate_board(board, min_white_cells: int) -> bool:
    """Check if the board has enough white cells."""
    return len(board.white_cells) >= min_white_cells

import random

@app.get("/generate")
def generate_puzzle(width: Optional[int] = None, height: Optional[int] = None, difficulty: str = "medium", verify_unique: bool = False):
    density = DIFFICULTY_MAP.get(difficulty, 0.15)
    
    # Randomize size if not specified
    if width is None or height is None:
        min_s, max_s = DIFFICULTY_SIZE_RANGES.get(difficulty, (10, 10))
        if width is None:
            width = random.randint(min_s, max_s)
        if height is None:
            height = random.randint(min_s, max_s)

    # Adjust minimum white cells and sector length for very easy
    min_white = MIN_WHITE_CELLS
    if difficulty == "very_easy" or width < 8 or height < 8:
        min_white = 8  # Allow smaller puzzles for very easy
    
    for attempt in range(MAX_RETRIES):
        # 1. Topology (with smaller sectors when uniqueness is requested)
        board = KakuroBoard(width, height)
        # Even stricter sector limiting for higher difficulties to aid uniqueness
        max_sector = 4 if (verify_unique or difficulty == "very_easy") else 9
        if difficulty == "hard": max_sector = min(max_sector, 5)
        
        board.generate_topology(density=density, max_sector_length=max_sector)
        
        # Validate board has enough white cells
        if not validate_board(board, min_white):
            continue  # Retry
        
        # 2. Fill and ensure uniqueness (using iterative refinement)
        solver = CSPSolver(board)
        
        if verify_unique:
            # New smart generation with iterative tightening
            success, msg = solver.generate_with_uniqueness(
                max_iterations=5, 
                prefer_small_numbers=(difficulty == "very_easy")
            )
            if not success:
                continue  # Full retry with new topology
        else:
            # Standard fill without uniqueness check (with node limit for safety)
            success = solver.solve_fill(
                max_nodes=10000, 
                prefer_small_numbers=(difficulty == "very_easy")
            )
            if not success:
                continue  # Retry
            solver.calculate_clues()
        
        # Serialize
        grid_data = []
        for r in range(height):
            row_data = []
            for c in range(width):
                cell = board.get_cell(r, c)
                row_data.append(cell.to_dict())
            grid_data.append(row_data)

        puzzle_id = str(uuid.uuid4())
        return {
            "id": puzzle_id,
            "width": width,
            "height": height,
            "difficulty": difficulty,
            "grid": grid_data,
            "status": "started",
            "timestamp": datetime.datetime.now().isoformat()
        }
    
    # All retries failed
    raise HTTPException(status_code=500, detail="Failed to generate valid puzzle after multiple attempts. Try a different difficulty or size.")

class SaveRequest(BaseModel):
    id: str
    width: int
    height: int
    difficulty: str
    grid: List[List[Dict]]
    userGrid: Optional[List[List[Dict]]] = None
    status: str
    rowNotes: List[str]
    colNotes: List[str]
    timestamp: Optional[str] = None

@app.post("/save")
def save_puzzle_endpoint(request: SaveRequest):
    data = request.dict()
    if not data.get("timestamp"):
        data["timestamp"] = datetime.datetime.now().isoformat()
    storage.save_puzzle(request.id, data)
    return {"status": "success"}

@app.get("/list_saved")
def list_saved_puzzles():
    return storage.list_puzzles()

@app.get("/load/{puzzle_id}")
def load_puzzle_endpoint(puzzle_id: str):
    data = storage.load_puzzle(puzzle_id)
    if not data:
        raise HTTPException(status_code=404, detail="Puzzle not found")
    return data

@app.delete("/delete/{puzzle_id}")
def delete_puzzle_endpoint(puzzle_id: str):
    if storage.delete_puzzle(puzzle_id):
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Puzzle not found")

def open_browser(url: str):
    """Wait for the server to start and then open the browser."""
    time.sleep(1.5)  # Give the server a moment to start
    webbrowser.open(url)

if __name__ == "__main__":
    host = "127.0.0.1"
    port = 8008
    url = f"http://{host}:{port}"
    
    try:
        # Check if we're running as a bundle to disable reload
        is_frozen = getattr(sys, 'frozen', False)
        
        # Open browser in a separate thread
        threading.Thread(target=open_browser, args=(url,), daemon=True).start()
        
        if is_frozen:
            # Pass app object directly to avoid import issues in frozen environment
            uvicorn.run(app, host=host, port=port, reload=False)
        else:
            uvicorn.run("main:app", host=host, port=port, reload=True)
            
    except Exception as e:
        # Log error to file if startup fails in frozen mode
        if getattr(sys, 'frozen', False):
            with open("startup_error.log", "w") as f:
                import traceback
                f.write(traceback.format_exc())
        raise e
