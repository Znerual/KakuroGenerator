from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from kakuro import KakuroBoard
from solver import CSPSolver
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

DIFFICULTY_MAP = {
    "easy": 0.08,
    "medium": 0.15,
    "hard": 0.22
}

MIN_WHITE_CELLS = 15  # Minimum white cells for a valid puzzle
MAX_RETRIES = 20  # More retries for reliability

def validate_board(board, min_white_cells: int) -> bool:
    """Check if the board has enough white cells."""
    return len(board.white_cells) >= min_white_cells

@app.get("/generate")
def generate_puzzle(width: int = 10, height: int = 10, difficulty: str = "medium", verify_unique: bool = False):
    density = DIFFICULTY_MAP.get(difficulty, 0.15)
    
    for attempt in range(MAX_RETRIES):
        # 1. Topology (with smaller sectors when uniqueness is requested)
        board = KakuroBoard(width, height)
        # Even stricter sector limiting for higher difficulties to aid uniqueness
        max_sector = 4 if verify_unique else 9
        if difficulty == "hard": max_sector = min(max_sector, 5)
        
        board.generate_topology(density=density, max_sector_length=max_sector)
        
        # Validate board has enough white cells
        if not validate_board(board, MIN_WHITE_CELLS):
            continue  # Retry
        
        # 2. Fill and ensure uniqueness (using iterative refinement)
        solver = CSPSolver(board)
        
        if verify_unique:
            # New smart generation with iterative tightening
            success, msg = solver.generate_with_uniqueness(max_iterations=5)
            if not success:
                continue  # Full retry with new topology
        else:
            # Standard fill without uniqueness check (with node limit for safety)
            success = solver.solve_fill(max_nodes=10000)
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

        return {
            "width": width,
            "height": height,
            "difficulty": difficulty,
            "grid": grid_data
        }
    
    # All retries failed
    raise HTTPException(status_code=500, detail="Failed to generate valid puzzle after multiple attempts. Try a different difficulty or size.")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
