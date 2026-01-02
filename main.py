from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, select, desc
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
from python.models import User, Puzzle, PuzzleTemplate
from python.auth import get_current_user, get_required_user, get_current_user_and_session
from python.analytics import log_interaction
from routes.auth_routes import router as auth_router
from routes.admin_routes import router as admin_router
from python.generator_service import generator_service
import python.config as config
from python.performance import Timer, log_system_performance, record_metric
import python.performance as performance

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

# Trust proxy headers (e.g., X-Forwarded-Proto) from local proxy
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["127.0.0.1", "::1"])

# Include authentication routes
app.include_router(auth_router)
# Include admin routes
app.include_router(admin_router)

@app.middleware("http")
async def performance_middleware(request: Request, call_next):
    """
    Middleware to track request duration and active request count.
    """
    import time
    from python.database import SessionLocal
    
    # Increment active requests
    performance.ACTIVE_REQUESTS += 1
    
    start_time = time.perf_counter()
    try:
        response = await call_next(request)
        duration = (time.perf_counter() - start_time) * 1000 # ms
        
        # Log metric (we do this in a background-ish way or just quickly)
        # To avoid blocking the response, we could use BackgroundTasks, but here we'll just do it simply
        # or skip if it's too much overhead. For now, let's log everything.
        with SessionLocal() as db:
            record_metric(
                db, 
                "api_request_duration_ms", 
                duration, 
                "ms", 
                {
                    "path": request.url.path, 
                    "method": request.method,
                    "status_code": response.status_code
                }
            )
        
        return response
    finally:
        performance.ACTIVE_REQUESTS -= 1

def system_monitor_task():
    """Background task to log system metrics every 60 seconds."""
    from python.database import SessionLocal
    while True:
        try:
            log_system_performance(SessionLocal)
        except Exception as e:
            logger.error(f"Error in system monitor task: {e}")
        time.sleep(60)


@app.on_event("startup")
def startup_event():
    """Initialize database on startup."""
    init_db()
    
    # Manual migration: check if template_id exists in puzzles
    from sqlalchemy import inspect, text
    from python.database import engine
    
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    with engine.connect() as conn:
        if "puzzles" in table_names:
            columns = [c["name"] for c in inspector.get_columns("puzzles")]
            if "template_id" not in columns:
                logger.info("Migrating database: Adding template_id to puzzles table")
                conn.execute(text("ALTER TABLE puzzles ADD COLUMN template_id TEXT"))
        
        if "users" in table_names:
            columns = [c["name"] for c in inspector.get_columns("users")]
            if "is_admin" not in columns:
                logger.info("Migrating database: Adding is_admin to users table")
                conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0"))

        if "puzzle_interactions" in table_names:
            columns = [c["name"] for c in inspector.get_columns("puzzle_interactions")]
            if "fill_count" not in columns:
                logger.info("Migrating database: Adding fill_count to puzzle_interactions table")
                conn.execute(text("ALTER TABLE puzzle_interactions ADD COLUMN fill_count INTEGER"))

        if "users" in table_names:
            columns = [c["name"] for c in inspector.get_columns("users")]
            if "total_score" not in columns:
                logger.info("Migrating database: Adding total_score to users table")
                conn.execute(text("ALTER TABLE users ADD COLUMN total_score INTEGER DEFAULT 0"))
        
        # Create score_records table if it doesn't exist
        if "score_records" not in table_names:
            logger.info("Migrating database: Creating score_records table")
            conn.execute(text("""
                CREATE TABLE score_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    puzzle_id TEXT NOT NULL,
                    points INTEGER NOT NULL,
                    difficulty TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(puzzle_id) REFERENCES puzzles(id)
                )
            """))
            conn.execute(text("CREATE INDEX idx_score_records_user_id ON score_records(user_id)"))
            conn.execute(text("CREATE INDEX idx_score_records_created_at ON score_records(created_at)"))

    logger.info("Database initialized")
    
    # Start background generator
    generator_service.start()
    
    # Start system monitor
    threading.Thread(target=system_monitor_task, daemon=True).start()

@app.on_event("shutdown")
def shutdown_event():
    """Stop background services."""
    generator_service.stop()

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

DIFFICULTY_POINTS = {
    "very_easy": 10,
    "easy": 25,
    "medium": 100,
    "hard": 250
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
    template_id: Optional[str] = None

@app.post("/save")
def save_puzzle_endpoint(
    request: SaveRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Save a puzzle. If user is authenticated, associates with their account."""
    with Timer(db, "puzzle_save_duration_ms"):
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
                    # Award points
                    points = DIFFICULTY_POINTS.get(puzzle.difficulty, 0)
                    current_user.total_score += points
                    
                    # Create score record
                    from python.models import ScoreRecord
                    score_record = ScoreRecord(
                        user_id=current_user.id,
                        puzzle_id=puzzle.id,
                        points=points,
                        difficulty=puzzle.difficulty
                    )
                    db.add(score_record)
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
                    user_comment=request.userComment,
                    template_id=request.template_id
                )
                
                # If no template_id was provided (legacy/standalone gen), we should arguably create one
                # so this puzzle becomes shareable.
                if not request.template_id and request.status != 'started':
                    # Only "publish" if they've made progress or solved it, to avoid spamming templates with abandoned starts?
                    # For now, let's auto-create a template if missing, so it can be shared.
                    new_template = PuzzleTemplate(
                        width=request.width,
                        height=request.height,
                        difficulty=request.difficulty,
                        grid=request.grid,
                    )
                    db.add(new_template)
                    db.flush() # get id
                    puzzle.template_id = new_template.id
                
                db.add(puzzle)
                
                if request.status == "solved":
                    current_user.kakuros_solved += 1
                    # Award points
                    points = DIFFICULTY_POINTS.get(request.difficulty, 0)
                    current_user.total_score += points
                    
                    # Create score record
                    from python.models import ScoreRecord
                    score_record = ScoreRecord(
                        user_id=current_user.id,
                        puzzle_id=puzzle.id,
                        points=points,
                        difficulty=request.difficulty
                    )
                    db.add(score_record)
            
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

class InteractionLog(BaseModel):
    puzzle_id: str
    action_type: str
    row: Optional[int] = None
    col: Optional[int] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    duration_ms: Optional[int] = 0
    client_timestamp: str
    device_type: Optional[str] = "desktop"

@app.post("/log/interaction")
def log_user_interaction(
    log: InteractionLog,
    auth_data: tuple[Optional[User], Optional[str]] = Depends(get_current_user_and_session),
    db: Session = Depends(get_db)
):
    """
    Log a specific action taken by the user (move, note, delete, etc.).
    Uses the session ID from the token to link actions to a session.
    """
    user, session_id = auth_data
    if not user:
        # We generally only track logged-in users, but could expand this to anonymous if needed
        return {"status": "ignored"}

    with Timer(db, "interaction_log_duration_ms"):
        log_interaction(
            db=db,
            user_id=user.id,
            puzzle_id=log.puzzle_id,
            session_id=session_id,
            action_data=log.model_dump()
        )
    return {"status": "logged"}

@app.post("/log/batch_interaction")
def log_batch_interaction(
    logs: List[InteractionLog],
    auth_data: tuple[Optional[User], Optional[str]] = Depends(get_current_user_and_session),
    db: Session = Depends(get_db)
):
    """Log multiple actions in one request (e.g. multi-select notes)."""
    user, session_id = auth_data
    if not user:
        return {"status": "ignored"}

    # Process all logs in a single transaction
    for log in logs:
        log_interaction(
            db=db,
            user_id=user.id,
            puzzle_id=log.puzzle_id,
            session_id=session_id,
            action_data=log.model_dump()
        )
    
    return {"status": "batch_logged"}
    
@app.get("/feed")
def get_puzzle_feed(
    difficulty: str = "medium",
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """
    Returns a feed of puzzles from the pre-generated pool.
    """
    puzzles_to_return = []
    
    # query pool
    query = db.query(PuzzleTemplate).filter(
        PuzzleTemplate.difficulty == difficulty
    )

    if current_user:
        # Subquery to find template_ids that the user has already interacted with
        subquery = select(Puzzle.template_id).filter(
            Puzzle.user_id == current_user.id,
            Puzzle.template_id.isnot(None)
        )
        
        query = query.filter(~PuzzleTemplate.id.in_(subquery))
    
    # Fetch random templates from the pool
    # We fetch slightly more to handle potential race conditions or just providing variety
    existing_templates = query.order_by(func.random()).limit(limit).all()
    
    for tmpl in existing_templates:
        puzzles_to_return.append({
            "id": str(uuid.uuid4()), # New instance ID for the user to start
            "template_id": tmpl.id,
            "width": tmpl.width,
            "height": tmpl.height,
            "difficulty": tmpl.difficulty,
            "grid": tmpl.grid,
            "status": "started",
            "timestamp": datetime.datetime.now().isoformat(),
            "source": "pool"
        })
    
    # 2. GENERATE FALLBACK if pool is empty or user exhausted it
    needed = limit - len(puzzles_to_return)
    if needed > 0:
        logger.info(f"Feed pool exhausted for user (needed {needed}), generating fallback...")
        from python.kakuro_wrapper import KakuroBoard, CSPSolver
        
        # Size logic
        min_s, max_s = DIFFICULTY_SIZE_RANGES.get(difficulty, (10, 10))
        min_white = MIN_CELLS_MAP.get(difficulty, 12)
        
        for _ in range(needed):
            w = random.randint(min_s, max_s)
            h = random.randint(min_s, max_s)
            
            # Retry loop
            for attempt in range(10):
                board = KakuroBoard(w, h)
                solver = CSPSolver(board)
                if solver.generate_puzzle(difficulty=difficulty):
                    if len(board.white_cells) >= min_white:
                        # Success
                        grid_data = []
                        for r in range(h):
                            row_data = []
                            for c in range(w):
                                cell = board.get_cell(r, c)
                                row_data.append(cell.to_dict())
                            grid_data.append(row_data)
                        
                        # Create Template so it becomes part of the pool for others
                        tmpl = PuzzleTemplate(
                            width=w, 
                            height=h, 
                            difficulty=difficulty, 
                            grid=grid_data
                        )
                        db.add(tmpl)
                        db.commit() 
                        
                        puzzles_to_return.append({
                            "id": str(uuid.uuid4()),
                            "template_id": tmpl.id,
                            "width": w,
                            "height": h,
                            "difficulty": difficulty,
                            "grid": grid_data,
                            "status": "started",
                            "timestamp": datetime.datetime.now().isoformat(),
                            "source": "generated_fallback"
                        })
                        break

    return puzzles_to_return

@app.get("/leaderboard/all-time")
def get_all_time_leaderboard(db: Session = Depends(get_db)):
    """Fetch top 50 users by total score."""
    top_users = db.query(User).filter(User.username.isnot(None))\
        .order_by(User.total_score.desc()).limit(50).all()
    
    return [
        {
            "username": u.username,
            "score": u.total_score,
            "solved": u.kakuros_solved,
            "avatar": u.avatar_url
        } for u in top_users
    ]

@app.get("/leaderboard/monthly")
def get_monthly_leaderboard(db: Session = Depends(get_db)):
    """Fetch top users based on points earned in the current month."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    # Start of the current month
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    from sqlalchemy import func
    from python.models import ScoreRecord
    
    # Query to sum points per user for the current month
    monthly_scores = db.query(
        User.username,
        User.avatar_url,
        func.sum(ScoreRecord.points).label("monthly_points"),
        func.count(ScoreRecord.id).label("monthly_solved")
    ).join(ScoreRecord, User.id == ScoreRecord.user_id)\
     .filter(ScoreRecord.created_at >= start_of_month)\
     .group_by(User.id)\
     .order_by(desc("monthly_points"))\
     .limit(50).all()
    
    return [
        {
            "username": s.username,
            "score": int(s.monthly_points),
            "solved": s.monthly_solved,
            "avatar": s.avatar_url
        } for s in monthly_scores
    ]

def open_browser(url: str):
    """Wait for the server to start and then open the browser."""
    time.sleep(1.5)  # Give the server a moment to start
    webbrowser.open(url)

if __name__ == "__main__":
    host = "0.0.0.0" # "127.0.0.1"
    port = 8000
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
