try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    
import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from python.models import PerformanceMetric, AuthLog
from datetime import datetime, timezone
import os

logger = logging.getLogger("performance")

# Concurrent request tracker
ACTIVE_REQUESTS = 0

def record_metric(
    db: Session, 
    name: str, 
    value: float, 
    unit: Optional[str] = None, 
    metadata: Optional[Dict[str, Any]] = None
):
    """Saves a performance metric to the database."""
    try:
        metric = PerformanceMetric(
            metric_name=name,
            value=value,
            unit=unit,
            metadata_json=metadata
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
    def __init__(self, db: Session, name: str, unit: str = "ms", metadata: Optional[Dict[str, Any]] = None):
        self.db = db
        self.name = name
        self.unit = unit
        self.metadata = metadata or {}
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
            
        record_metric(self.db, self.name, val, self.unit, self.metadata)

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
