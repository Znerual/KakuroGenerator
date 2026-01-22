import threading
import time
import logging
import random
from sqlalchemy.orm import Session
from sqlalchemy import func
from .database import SessionLocal
from .models import PuzzleTemplate, DifficultyStat
from .kakuro_wrapper import KakuroBoard, CSPSolver, KakuroDifficultyEstimator, generate_kakuro

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
        self.difficulty_size_ranges = {}

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

    def start(self, difficulty_size_ranges: dict[str, tuple[int, int]]):
        """Start the background generation thread."""
        self.difficulty_size_ranges = difficulty_size_ranges
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

    def generate_single_puzzle(self, db: Session, target_diff: str, means: dict = None, height: int | None = None, width: int | None = None) -> PuzzleTemplate:
        """
        The core logic: Generate -> Score -> Push -> Update Stats -> Return Template.
        This is used for both background filling and on-demand fallback.
        """
        if means is None:
            means = self._get_all_means(db)

        # 1. Call C++ Generator
        if height is None or width is None:
            width, height = self._get_grid_size(target_diff)
        board = generate_kakuro(width=width, height=height, difficulty=target_diff, use_cpp=True)
        difficulty_estimator = KakuroDifficultyEstimator(board)
        diff = difficulty_estimator.estimate_difficulty_detailed()
        
        if not board or not diff:
            return None

        # 2. Package detailed information
        difficulty_info = {
            "rating": diff.rating,
            "score": round(diff.score, 2),
            "max_tier": int(diff.max_tier),
            "total_steps": diff.total_steps,
            "uniqueness": diff.uniqueness,
            "solution_count": diff.solution_count,
            "solve_path": [
                {"technique": s.technique, "weight": s.difficulty_weight, "cells": s.cells_affected} 
                for s in diff.solve_path
            ]
        }

        # 3. Difficulty Pushing Logic
        final_diff = target_diff
        idx = DIFFICULTY_LEVELS.index(target_diff)
        
        # Check Push UP (Is score > mean of higher level?)
        if idx < len(DIFFICULTY_LEVELS) - 1:
            higher = DIFFICULTY_LEVELS[idx + 1]
            if diff.score > means[higher]:
                final_diff = higher
        
        # Check Push DOWN (Is score < mean of lower level?)
        elif idx > 0:
            lower = DIFFICULTY_LEVELS[idx - 1]
            if diff.score < means[lower]:
                final_diff = lower

        # 4. Save Template
        tmpl = PuzzleTemplate(
            id=str(uuid.uuid4()),
            width=board.width,
            height=board.height,
            difficulty=final_diff,
            difficulty_score=diff.score,
            difficulty_data=difficulty_info,
            grid=board.to_dict()
        )
        db.add(tmpl)

        # 5. Update Statistics for the FINAL difficulty
        stat = db.query(DifficultyStat).filter_by(difficulty=final_diff).first()
        if not stat:
            stat = DifficultyStat(difficulty=final_diff)
            db.add(stat)
        stat.sum_scores += diff.score
        stat.count += 1
        
        return tmpl

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

    def _get_all_means(self, db: Session):
        """Retrieves a dict of difficulty -> mean_score."""
        stats = db.query(DifficultyStat).all()
        means = {s.difficulty: s.mean for s in stats}
        # Fill in defaults if stats table is empty
        defaults = {"very_easy": 10.0, "easy": 30.0, "medium": 60.0, "hard": 100.0}
        for d in DIFFICULTY_LEVELS:
            if d not in means or means[d] == 0:
                means[d] = defaults[d]
        return means

    def _update_stats(self, db: Session, difficulty: str, score: float):
        """Updates the running sum and count for a difficulty level."""
        stat = db.query(DifficultyStat).filter_by(difficulty=difficulty).first()
        if not stat:
            stat = DifficultyStat(difficulty=difficulty, sum_scores=0.0, count=0)
            db.add(stat)
        
        stat.sum_scores += score
        stat.count += 1
        # No commit here, part of the batch transaction

    def _determine_difficulty(self, score: float, requested_diff: str, means: dict) -> str:
        """
        Logic: Push up if score > mean of higher level.
        Push down if score < mean of lower level.
        """
        idx = DIFFICULTY_LEVELS.index(requested_diff)
        
        # Check Push Up
        if idx < len(DIFFICULTY_LEVELS) - 1:
            higher_diff = DIFFICULTY_LEVELS[idx + 1]
            if score > means[higher_diff]:
                logger.info(f"Pushing UP: {score} > mean({higher_diff})={means[higher_diff]:.2f}")
                return higher_diff
        
        # Check Push Down
        if idx > 0:
            lower_diff = DIFFICULTY_LEVELS[idx - 1]
            if score < means[lower_diff]:
                logger.info(f"Pushing DOWN: {score} < mean({lower_diff})={means[lower_diff]:.2f}")
                return lower_diff
                
        return requested_diff

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

    def _get_grid_size(self, difficulty: str) -> tuple[int, int]:
        """Get grid size based on difficulty level."""
        if difficulty not in self.difficulty_size_ranges:
            raise ValueError(f"Invalid difficulty level: {difficulty}")
        
        min_size, max_size = self.difficulty_size_ranges[difficulty]
        return random.randint(min_size, max_size), random.randint(min_size, max_size)
    

    def _check_and_refill_pools(self):
        """Check database for fresh puzzle counts and generate if needed."""
        with SessionLocal() as db:
            means = self._get_all_means(db)

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
                    logger.info(f"{difficulty} pool is low. Starting targeted generation batch...")
                    start_t = time.perf_counter()
                    self._generate_targeted_batch(db, difficulty, BATCH_SIZE, means)
                    duration_ms = (time.perf_counter() - start_t) * 1000
                
                    try:
                        from .performance import record_metric
                        record_metric(db, f"gen_{difficulty}_batch_time_ms", duration_ms, "ms")
                    except ImportError:
                        pass
            
                    
    def _generate_targeted_batch(self, db: Session, target_diff: str, count: int, means: dict, height: int | None = None, width: int | None = None):
        """Generates puzzles and adjusts their difficulty based on global means."""
        # Pre-fetch stats to avoid "flush-on-query" issues or duplicate "add" in batch
        stats_map = {s.difficulty: s for s in db.query(DifficultyStat).all()}

        generated = 0
        for _ in range(count):
            if self._stop_event.is_set(): break

            if height is None or width is None:
                width, height = self._get_grid_size(target_diff)
            board = generate_kakuro(width=width, height=height, difficulty=target_diff, use_cpp=True)
            difficulty_estimator = KakuroDifficultyEstimator(board)
            diff = difficulty_estimator.estimate_difficulty_detailed()

            if board and diff:
                raw_score = diff.score # Assuming C++ returns a float
              
                # Convert the C++ difficulty object to a dictionary
                difficulty_data = {
                    "rating": diff.rating,
                    "score": round(diff.score, 2),
                    "max_tier": int(diff.max_tier),
                    "total_steps": diff.total_steps,
                    "uniqueness": diff.uniqueness,
                    "solution_count": diff.solution_count,
                    "solve_path": [
                        {
                            "technique": step.technique,
                            "weight": step.difficulty_weight,
                            "cells": step.cells_affected
                        } for step in diff.solve_path
                    ]
                }
                # Apply the requested logic: Compare against means
                final_diff = self._determine_difficulty(raw_score, target_diff, means)
                
                tmpl = PuzzleTemplate(
                    width=board.width,
                    height=board.height,
                    difficulty=final_diff,
                    difficulty_score=raw_score,
                    difficulty_data=difficulty_data,
                    grid=board.to_dict(),
                    times_used=0
                )
                db.add(tmpl)
                
                # Update the running average for the FINAL difficulty
                if final_diff not in stats_map:
                    new_stat = DifficultyStat(difficulty=final_diff, sum_scores=0.0, count=0)
                    db.add(new_stat)
                    stats_map[final_diff] = new_stat
                
                stat = stats_map[final_diff]
                stat.sum_scores += raw_score
                stat.count += 1
                
                generated += 1
        
        if generated > 0:
            db.commit()
            logger.info(f"Saved {generated} puzzles initially targeted as {target_diff}")


# Singleton instance
generator_service = GeneratorService()
