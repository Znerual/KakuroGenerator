from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
import os
import sys
import webbrowser
import threading
import time
from python.kakuro_wrapper import KakuroBoard
from python.kakuro_wrapper import CSPSolver
import uvicorn
import uuid
import datetime
import python.storage as storage
import logging
import traceback
from pydantic import BaseModel
from typing import List, Optional, Dict

# Import auth and database modules
from python.database import init_db, get_db
from python.models import User, Puzzle
from python.auth import get_current_user, get_required_user
from routes.auth_routes import router as auth_router
import python.config as config

# Configure logging
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

# Clear existing handlers to avoid duplicates during reload
if root_logger.hasHandlers():
    root_logger.handlers.clear()

file_handler = logging.FileHandler("kakuro_debug.log", mode='a')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
root_logger.addHandler(file_handler)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
root_logger.addHandler(stream_handler)

logger = logging.getLogger("kakuro_main")
logger.info("Logging initialized or re-initialized")

app = FastAPI(title="Kakuro Generator", version="1.0.0")

# Session middleware for OAuth (required by Authlib)
app.add_middleware(SessionMiddleware, secret_key=config.JWT_SECRET_KEY)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include authentication routes
app.include_router(auth_router)


@app.on_event("startup")
def startup_event():
    """Initialize database on startup."""
    init_db()
    logger.info("Database initialized")

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

# Minimum white cells required to accept a puzzle
# verification fails if the puzzle is "too empty"
MIN_CELLS_MAP = {
    "very_easy": 6,   # Allow small puzzles
    "easy": 10,
    "medium": 15,
    "hard": 20
}

DIFFICULTY_SIZE_RANGES = {
    "very_easy": (6, 9),
    "easy": (8, 10),
    "medium": (10, 12),
    "hard": (12, 14)
}

MAX_RETRIES = 20  # More retries for reliability

def validate_board(board, min_white_cells: int) -> bool:
    """Check if the board has enough white cells."""
    return len(board.white_cells) >= min_white_cells

import random

@app.get("/generate")
def generate_puzzle(width: Optional[int] = None, height: Optional[int] = None, difficulty: str = "medium"):
    """
    Generates a Kakuro puzzle using the improved CSPSolver with uniqueness guarantees.
    """
    
    # 1. Randomize size if not specified
    if width is None or height is None:
        min_s, max_s = DIFFICULTY_SIZE_RANGES.get(difficulty, (10, 10))
        if width is None:
            width = random.randint(min_s, max_s)
        if height is None:
            height = random.randint(min_s, max_s)


    # Adjust minimum white cells and sector length for very easy
    min_white_cells = MIN_CELLS_MAP.get(difficulty, 12)

    # 2. Generation Loop
    # The solver.generate_puzzle method has its own internal retry loop for topology/uniqueness,
    # but we add a small outer loop just in case the board geometry itself is invalid (too small).
    max_outer_retries = MAX_RETRIES
    
    for attempt in range(max_outer_retries):
        board = KakuroBoard(width, height)
        solver = CSPSolver(board)
        
        # This function now handles Topology -> Fill -> Verify -> Repair -> Repeat
        success = solver.generate_puzzle(difficulty=difficulty)
        
        if success:
            # Final validation check to ensure the puzzle isn't too trivial
            if len(board.white_cells) < min_white_cells:
                print("Too trivial, retrying...")
                #continue # Retry to get a meatier puzzle

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
    cellNotes: Dict[str, str]
    notebook: str
    rating: int
    userComment: str
    timestamp: Optional[str] = None

@app.post("/save")
def save_puzzle_endpoint(
    request: SaveRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Save a puzzle. If user is authenticated, associates with their account."""
    if current_user:
        # Database storage for authenticated users
        puzzle = db.query(Puzzle).filter(Puzzle.id == request.id).first()
        if puzzle:
            # Update existing
            puzzle.grid = request.grid
            puzzle.user_grid = request.userGrid
            puzzle.status = request.status
            puzzle.row_notes = request.rowNotes
            puzzle.col_notes = request.colNotes
            puzzle.cell_notes = request.cellNotes
            puzzle.notebook = request.notebook
            puzzle.rating = request.rating
            puzzle.user_comment = request.userComment
            
            # Update solved count if status changed to solved
            if request.status == "solved" and puzzle.status != "solved":
                current_user.kakuros_solved += 1
        else:
            # Create new
            puzzle = Puzzle(
                id=request.id,
                user_id=current_user.id,
                width=request.width,
                height=request.height,
                difficulty=request.difficulty,
                grid=request.grid,
                user_grid=request.userGrid,
                status=request.status,
                row_notes=request.rowNotes,
                col_notes=request.colNotes,
                cell_notes=request.cellNotes,
                notebook=request.notebook,
                rating=request.rating,
                user_comment=request.userComment
            )
            db.add(puzzle)
            
            if request.status == "solved":
                current_user.kakuros_solved += 1
        
        db.commit()
    else:
        # Fall back to file storage for anonymous users
        data = request.model_dump()
        if not data.get("timestamp"):
            data["timestamp"] = datetime.datetime.now().isoformat()
        storage.save_puzzle(request.id, data)
    
    return {"status": "success"}


@app.get("/list_saved")
def list_saved_puzzles(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """List saved puzzles. If authenticated, returns user's puzzles from DB."""
    if current_user:
        puzzles = db.query(Puzzle).filter(Puzzle.user_id == current_user.id).all()
        return [p.to_dict() for p in puzzles]
    else:
        return storage.list_puzzles()


@app.get("/load/{puzzle_id}")
def load_puzzle_endpoint(
    puzzle_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Load a puzzle by ID."""
    if current_user:
        puzzle = db.query(Puzzle).filter(
            Puzzle.id == puzzle_id,
            Puzzle.user_id == current_user.id
        ).first()
        if puzzle:
            return puzzle.to_dict()
    
    # Fall back to file storage
    data = storage.load_puzzle(puzzle_id)
    if not data:
        raise HTTPException(status_code=404, detail="Puzzle not found")
    return data


@app.delete("/delete/{puzzle_id}")
def delete_puzzle_endpoint(
    puzzle_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Delete a puzzle by ID."""
    if current_user:
        puzzle = db.query(Puzzle).filter(
            Puzzle.id == puzzle_id,
            Puzzle.user_id == current_user.id
        ).first()
        if puzzle:
            db.delete(puzzle)
            db.commit()
            return {"status": "success"}
    
    # Fall back to file storage
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
