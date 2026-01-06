import threading
import time
import logging
import random
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import PuzzleTemplate
from .kakuro_wrapper import KakuroBoard, CSPSolver, generate_random_kakuro

logger = logging.getLogger("kakuro_generator")

# Configuration
DIFFICULTY_LEVELS = ["very_easy", "easy", "medium", "hard"]
POOL_TARGET_SIZE = 50  # Keep at least 50 fresh puzzles per difficulty
BATCH_SIZE = 5         # Generate 5 at a time to yield lock frequently
CHECK_INTERVAL_SECONDS = 10
FRESHNESS_BUFFER = 20  # Buffer above max user completions for freshness threshold

class GeneratorService:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None
        self.running = False
        self._current_counts = {diff: 0 for diff in DIFFICULTY_LEVELS}

    @property
    def status(self) -> dict:
        """Returns current pool counts for the Admin Dashboard."""
        return self._current_counts

    @property
    def settings(self) -> dict:
        """Returns config for the Admin Dashboard."""
        return {
            "target_count": POOL_TARGET_SIZE,
            "threshold": 10, # Fixed threshold for UI or calculate dynamically
            "batch_size": BATCH_SIZE
        }

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

    def _get_freshness_threshold(self, db: Session, difficulty: str) -> int:
        """
        Calculate dynamic threshold based on user completion stats.
        A template is 'fresh' if times_used < threshold.
        
        Logic: threshold = max(user completions for difficulty) + buffer
        This ensures power users always have novel content.
        """
        from sqlalchemy import func
        from .models import Puzzle
        
        # Find max completions per user for this difficulty
        max_completions = db.query(func.count(Puzzle.id))\
            .filter(Puzzle.difficulty == difficulty, Puzzle.status == "solved")\
            .group_by(Puzzle.user_id)\
            .order_by(func.count(Puzzle.id).desc())\
            .limit(1).scalar()
        
        # Default to 1 if no completions, add buffer
        return (max_completions or 0) + FRESHNESS_BUFFER

    def _check_and_refill_pools(self):
        """Check database for fresh puzzle counts and generate if needed."""
        with SessionLocal() as db:
            any_low = False
            for difficulty in DIFFICULTY_LEVELS:
                if self._stop_event.is_set():
                    return

                # Get dynamic freshness threshold
                threshold = self._get_freshness_threshold(db, difficulty)
                
                # Count 'fresh' templates (times_used below threshold)
                fresh_count = db.query(PuzzleTemplate).filter(
                    PuzzleTemplate.difficulty == difficulty,
                    PuzzleTemplate.times_used < threshold
                ).count()

                self._current_counts[difficulty] = fresh_count
                if fresh_count < POOL_TARGET_SIZE:
                    any_low = True

            if any_low:
                logger.info("Some pools are low. Starting randomized generation batch...")
                start_t = time.perf_counter()
                self._generate_random_batch(db, BATCH_SIZE)
                duration_ms = (time.perf_counter() - start_t) * 1000
                
                try:
                    from .performance import record_metric
                    record_metric(db, "gen_random_batch_time_ms", duration_ms, "ms")
                except ImportError:
                    pass
                    
    def _generate_random_batch(self, db: Session, count: int):
        """Generates random puzzles and categorizes them by estimated difficulty."""
        generated = 0
        
        # Mapping from Estimator Rating (C++) to DB Difficulty
        RATING_MAP = {
            "Very Easy": "very_easy",
            "Easy": "easy",
            "Medium": "medium",
            "Hard": "hard",
            "Extreme": "hard" # Or maybe we support extreme later
        }

        for _ in range(count):
            if self._stop_event.is_set():
                break

            # Use C++ implementation for speed and better difficulty metrics
            board, diff_info = generate_random_kakuro(use_cpp=True)
            
            if board and diff_info:
                # Success - Map Rating
                rating_str = diff_info.rating
                internal_diff = RATING_MAP.get(rating_str, "medium")
                
                # Export board to Dict
                grid_data = board.to_dict()

                # Save to DB
                tmpl = PuzzleTemplate(
                    width=board.width,
                    height=board.height,
                    difficulty=internal_diff,
                    grid=grid_data
                )
                db.add(tmpl)
                generated += 1
                logger.info(f"Generated {rating_str} puzzle ({board.width}x{board.height})")
        
        if generated > 0:
            db.commit()
            logger.info(f"Batch completed: {generated} random puzzles saved.")

# Singleton instance
generator_service = GeneratorService()
