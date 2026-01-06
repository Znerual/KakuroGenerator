try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    
import logging
from typing import Optional, Dict, Any, Union
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Float
from .models import PerformanceMetric, AuthLog, PuzzleTemplate
from datetime import datetime, timezone
import time
import os

logger = logging.getLogger("performance")

# Concurrent request tracker
ACTIVE_REQUESTS = 0

def record_metric(
    db: Session, 
    name: str, 
    value: float, 
    unit: Optional[str] = None, 
    metadata: Optional[Dict[str, Any]] = None,
    user: Optional[Any] = None
):
    """Saves a performance metric to the database."""
    try:
        final_metadata = metadata or {}

        if user:
            # Check if user is authenticated (assuming user object from models.py)
            final_metadata["user_type"] = "authenticated"
            final_metadata["user_id"] = getattr(user, "id", None)
        else:
            final_metadata["user_type"] = "anonymous"

        metric = PerformanceMetric(
            metric_name=name,
            value=value,
            unit=unit,
            metadata_json=final_metadata
        )
        db.add(metric)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to record metric {name}: {e}")
        db.rollback()

def log_auth_attempt(
    db: Session,
    email: str,
    action: str,
    status: str,
    request: Any,
    user_id: Optional[str] = None,
    reason: Optional[str] = None
):
    """Logs an authentication attempt (login, register, etc.)."""
    try:
        ip_address = request.client.host if request.client else "Unknown"
        user_agent = request.headers.get("user-agent", "Unknown")
        
        log = AuthLog(
            user_id=user_id,
            email=email,
            action=action,
            status=status,
            ip_address=ip_address,
            user_agent=user_agent,
            reason=reason
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log auth attempt for {email}: {e}")
        db.rollback()

class Timer:
    """Context manager for timing code blocks."""
    def __init__(
        self, 
        db: Session, 
        name: str, 
        unit: str = "ms", 
        metadata: Optional[Dict[str, Any]] = None,
        user: Optional[Any] = None
    ):
        self.db = db
        self.name = name
        self.unit = unit
        self.metadata = metadata or {}
        self.user = user
        self.start_time = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = time.perf_counter()
        duration = (end_time - self.start_time)
        
        if self.unit == "ms":
            val = duration * 1000
        else:
            val = duration
            
        record_metric(self.db, self.name, val, self.unit, self.metadata, user=self.user)

def get_system_metrics() -> Dict[str, Any]:
    """Collects current CPU and Memory usage."""
    if not PSUTIL_AVAILABLE:
        # Fallback or empty metrics if psutil is missing
        import multiprocessing
        return {
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "cpu_count": multiprocessing.cpu_count(),
            "note": "psutil not installed"
        }

    try:
        cpu_percent = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        process = psutil.Process(os.getpid())
        process_memory = process.memory_info().rss
        
        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_used_bytes": memory.used,
            "process_memory_bytes": process_memory,
            "cpu_count": psutil.cpu_count(logical=True),
            "physical_cpu_count": psutil.cpu_count(logical=False)
        }
    except Exception as e:
        logger.error(f"Failed to collect system metrics: {e}")
        return {}

def log_puzzle_quality_metrics(db: Session):
    """Calculates and logs aggregate skip rates and puzzle quality."""
    try:
        # Calculate overall skip rate across all templates
        stats = db.query(
            func.sum(PuzzleTemplate.times_used).label("total_uses"),
            func.sum(PuzzleTemplate.times_skipped).label("total_skips")
        ).first()

        if stats and stats.total_uses and stats.total_uses > 0:
            skip_rate = (stats.total_skips / stats.total_uses) * 100
            record_metric(db, "aggregate_skip_rate", skip_rate, "%")
            record_metric(db, "total_puzzle_uses", float(stats.total_uses), "count")

        # Log skip rate per difficulty
        diff_stats = db.query(
            PuzzleTemplate.difficulty,
            func.sum(PuzzleTemplate.times_used),
            func.sum(PuzzleTemplate.times_skipped)
        ).group_by(PuzzleTemplate.difficulty).all()

        for diff, uses, skips in diff_stats:
            if uses > 0:
                rate = (skips / uses) * 100
                record_metric(db, f"skip_rate_{diff}", rate, "%", {"difficulty": diff})

    except Exception as e:
        logger.error(f"Error logging quality metrics: {e}")

def log_generator_status(db: Session):
    """Logs the state of the background generator service."""
    try:
        from .generator_service import generator_service
        # 1. Fill Level & Thresholds (from generator_service)
        # Using the .status property which returns {difficulty: count}
        current_counts = generator_service.status 
        target = generator_service.settings.get("target_count", 50)
        threshold = generator_service.settings.get("threshold", 10)

        
        for difficulty, count in current_counts.items():
            fill_percentage = (count / target) * 100 if target > 0 else 0
            record_metric(db, f"gen_fill_{difficulty}", fill_percentage, "%", {
                "count": count,
                "target": target,
                "threshold": threshold,
                "is_low": count <= threshold
            })

        # 2. Pool Freshness (Average usage of templates in DB)
        # Low average = Fresh pool; High average = Stale pool (users seeing repeats)
        avg_uses = db.query(func.avg(PuzzleTemplate.times_used)).scalar() or 0
        record_metric(db, "pool_freshness_index", float(avg_uses), "avg_uses")

    except Exception as e:
        logger.warning(f"Could not log generator status: {e}")

def log_system_performance(db_session_factory):
    """Utility to be run in a background task to log system performance periodically."""
    metrics = get_system_metrics()
    if not metrics:
        return

    with db_session_factory() as db:
        if "cpu_percent" in metrics:
            record_metric(db, "system_cpu_percent", metrics["cpu_percent"], "%")
        if "memory_percent" in metrics:
            record_metric(db, "system_memory_percent", metrics["memory_percent"], "%")
        if "process_memory_bytes" in metrics:
            record_metric(db, "process_memory_bytes", metrics["process_memory_bytes"], "bytes")
        
        # Log active requests as a proxy for load
        global ACTIVE_REQUESTS
        record_metric(db, "active_requests_count", float(ACTIVE_REQUESTS), "count")

        # 3. New: Quality & Skip Metrics
        log_puzzle_quality_metrics(db)

        # 4. New: Generator State Metrics
        log_generator_status(db)