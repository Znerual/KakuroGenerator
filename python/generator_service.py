import threading
import time
import logging
import random
from sqlalchemy.orm import Session
from python.database import SessionLocal
from python.models import PuzzleTemplate
from python.kakuro_wrapper import KakuroBoard, CSPSolver

logger = logging.getLogger("kakuro_generator")

# Configuration
DIFFICULTY_LEVELS = ["very_easy", "easy", "medium", "hard"]
POOL_TARGET_SIZE = 50  # Keep at least 50 puzzles per difficulty
BATCH_SIZE = 5         # Generate 5 at a time to yield lock frequently
CHECK_INTERVAL_SECONDS = 10

class GeneratorService:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None
        self.running = False

    def start(self):
        """Start the background generation thread."""
        if self.running:
            return
        
        logger.info("Starting Generator Service...")
        self._stop_event.clear()
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the background generation thread."""
        logger.info("Stopping Generator Service...")
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.running = False

    def _run_loop(self):
        """Main loop that checks pool sizes and triggers generation."""
        logger.info("Generator Service Loop Started")
        
        while not self._stop_event.is_set():
            try:
                self._check_and_refill_pools()
            except Exception as e:
                logger.error(f"Error in Generator Service loop: {e}", exc_info=True)
            
            # Sleep in small chunks to allow faster shutdown
            for _ in range(CHECK_INTERVAL_SECONDS * 2):
                if self._stop_event.is_set():
                    break
                time.sleep(0.5)

    def _check_and_refill_pools(self):
        """Check database for puzzle counts and generate if needed."""
        with SessionLocal() as db:
            for difficulty in DIFFICULTY_LEVELS:
                if self._stop_event.is_set():
                    return

                # Check current count
                count = db.query(PuzzleTemplate).filter(
                    PuzzleTemplate.difficulty == difficulty
                ).count()

                if count < POOL_TARGET_SIZE:
                    needed = POOL_TARGET_SIZE - count
                    logger.info(f"Pool '{difficulty}' low ({count}/{POOL_TARGET_SIZE}). Generating batch...")
                    
                    # Generate a small batch
                    generate_count = min(needed, BATCH_SIZE)
                    self._generate_batch(db, difficulty, generate_count)

    def _generate_batch(self, db: Session, difficulty: str, count: int):
        from main import MIN_CELLS_MAP, DIFFICULTY_SIZE_RANGES

        generated = 0
        min_white = MIN_CELLS_MAP.get(difficulty, 12)
        min_s, max_s = DIFFICULTY_SIZE_RANGES.get(difficulty, (10, 10))

        for _ in range(count):
            if self._stop_event.is_set():
                break

            w = random.randint(min_s, max_s)
            h = random.randint(min_s, max_s)

            # Retry logic for a single puzzle
            for attempt in range(20):
                board = KakuroBoard(w, h)
                solver = CSPSolver(board)
                
                if solver.generate_puzzle(difficulty=difficulty):
                    if len(board.white_cells) >= min_white:
                        # Success - Convert to Dict
                        grid_data = []
                        for r in range(h):
                            row_data = []
                            for c in range(w):
                                cell = board.get_cell(r, c)
                                row_data.append(cell.to_dict())
                            grid_data.append(row_data)

                        # Save to DB
                        tmpl = PuzzleTemplate(
                            width=w,
                            height=h,
                            difficulty=difficulty,
                            grid=grid_data
                        )
                        db.add(tmpl)
                        generated += 1
                        break # Break inner retry loop
        
        if generated > 0:
            db.commit()
            logger.info(f"Generated {generated} puzzles for '{difficulty}'")

# Singleton instance
generator_service = GeneratorService()
