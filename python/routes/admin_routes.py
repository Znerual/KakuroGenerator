from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, cast, Float
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone

from kakuro.database import get_db
from kakuro.models import User, Puzzle, PuzzleTemplate, PuzzleInteraction, PerformanceMetric, AuthLog
from kakuro.auth import get_admin_user
import kakuro.performance as performance
from kakuro.generator_service import generator_service
import os

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/stats/overview")
async def get_overview_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """General overview statistics for the admin dashboard."""
    user_count = db.query(User).count()
    puzzle_count = db.query(Puzzle).count()
    template_count = db.query(PuzzleTemplate).count()
    
    # Active sessions (last 15 minutes)
    fifteen_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=15)
    active_sessions = db.query(func.count(User.id)).filter(User.last_login >= fifteen_mins_ago).scalar()
    
    # System info
    sys_metrics = performance.get_system_metrics()

    quality_stats = db.query(
        func.sum(PuzzleTemplate.times_used).label("total_uses"),
        func.sum(PuzzleTemplate.times_skipped).label("total_skips"),
        func.avg(PuzzleTemplate.times_used).label("avg_uses")
    ).first()

    global_skip_rate = 0
    if quality_stats and quality_stats.total_uses:
        global_skip_rate = (quality_stats.total_skips / quality_stats.total_uses) * 100
    
    return {
        "counts": {
            "users": user_count,
            "puzzles_played": puzzle_count,
            "puzzle_templates": template_count,
            "active_users_15m": active_sessions
        },
        "quality": {
            "global_skip_rate": global_skip_rate,
            "pool_freshness": float(quality_stats.avg_uses or 0)
        },
        "system": sys_metrics,
        "active_requests": performance.ACTIVE_REQUESTS
    }

@router.get("/stats/performance")
async def get_performance_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
    hours: int = 24
):
    """Detailed performance metrics for the last X hours."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    # Average request duration per path
    req_stats = db.query(
        PerformanceMetric.metadata_json["path"].label("path"),
        PerformanceMetric.metadata_json["auth_status"].label("auth_status"),
        func.avg(PerformanceMetric.value).label("avg_ms"),
        func.count(PerformanceMetric.id).label("count")
    ).filter(
        PerformanceMetric.metric_name == "api_request_duration_ms",
        PerformanceMetric.timestamp >= since
    ).group_by("path", "auth_status").all()
    
    # System load trends (simplified)
    cpu_load = db.query(
        PerformanceMetric.timestamp,
        PerformanceMetric.value
    ).filter(
        PerformanceMetric.metric_name == "system_cpu_percent",
        PerformanceMetric.timestamp >= since
    ).order_by(PerformanceMetric.timestamp).all()

    mem_load = db.query(
        PerformanceMetric.timestamp,
        PerformanceMetric.value
    ).filter(
        PerformanceMetric.metric_name == "system_memory_percent",
        PerformanceMetric.timestamp >= since
    ).order_by(PerformanceMetric.timestamp).all()
    
    return {
        "requests": [{"path": r.path, "auth_status": r.auth_status, "avg_ms": r.avg_ms, "count": r.count} for r in req_stats],
        "cpu_trend": [{"time": c.timestamp.isoformat(), "value": c.value} for c in cpu_load],
        "memory_trend": [{"time": m.timestamp.isoformat(), "value": m.value} for m in mem_load]
    }

@router.get("/stats/generator")
async def get_generator_stats(
    admin: User = Depends(get_admin_user)
):
    """Real-time status of the background puzzle generator."""
    current_counts = generator_service.status
    settings = generator_service.settings
    target = settings.get("target_count", 50)
    threshold = settings.get("threshold", 10)

    res = {}
    for diff, count in current_counts.items():
        res[diff] = {
            "count": count,
            "target": target,
            "threshold": threshold,
            "fill_percent": (count / target) * 100 if target > 0 else 0,
            "is_low": count <= threshold
        }
    return {"difficulties": res}

@router.get("/user/{identifier}/journey")
async def get_user_journey(
    identifier: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Follow a specific user's behavior timeline."""
    user = db.query(User).filter(
        (User.id == identifier) | (User.username == identifier)
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    interactions = db.query(PuzzleInteraction).filter(
        PuzzleInteraction.user_id == user.id
    ).order_by(PuzzleInteraction.timestamp.desc()).limit(100).all()

    return {
        "user": user.to_dict(),
        "interactions": [
            {
                "timestamp": i.timestamp.isoformat(),
                "action_type": i.action_type,
                "puzzle_id": i.puzzle_id,
                "details": f"Cell [{i.row},{i.col}] -> {i.new_value}" if i.row is not None else ""
            } for i in interactions
        ]
    }

@router.get("/stats/solving")
async def get_solving_behavior(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Analyzes solving times and user behavior."""
    # Average solve time per difficulty
    # This requires looking at PuzzleInteraction or Puzzle status changes
    # Simple version: Puzzle.updated_at - Puzzle.created_at for solved puzzles
    
    solve_times = db.query(
        Puzzle.difficulty,
        func.avg(
            (func.strftime('%s', Puzzle.updated_at) - func.strftime('%s', Puzzle.created_at))
        ).label("avg_solve_seconds")
    ).filter(Puzzle.status == "solved").group_by(Puzzle.difficulty).all()
    
    # Move speed (duration_ms between interactions)
    # Filter for INPUT actions
    move_speeds = db.query(
        Puzzle.difficulty,
        func.avg(PuzzleInteraction.duration_ms).label("avg_move_ms")
    ).join(PuzzleInteraction, Puzzle.id == PuzzleInteraction.puzzle_id).filter(
        PuzzleInteraction.action_type == "INPUT",
        PuzzleInteraction.duration_ms > 0
    ).group_by(Puzzle.difficulty).all()
    
    # Move speed per fill state (e.g. 0-25%, 25-50%, etc.)
    # We can group by fill_count relative to total white cells.
    # For now, let's just group by absolute fill_count buckets.
    progress_speed = db.query(
        (PuzzleInteraction.fill_count / 10).label("bucket"),
        func.avg(PuzzleInteraction.duration_ms).label("avg_ms")
    ).filter(
        PuzzleInteraction.action_type == "INPUT",
        PuzzleInteraction.duration_ms > 0,
        PuzzleInteraction.fill_count != None
    ).group_by("bucket").all()
    
    # Calculate "start options" for templates
    # Simple metric: sum of (1 / number of combinations per clue) - actually clues are hard.
    # Let's just count templates by complexity (width * height * clues)
    
    return {
        "avg_solve_times": [{"difficulty": s.difficulty, "seconds": s.avg_solve_seconds} for s in solve_times],
        "avg_move_speeds": [{"difficulty": m.difficulty, "ms": m.avg_move_ms} for m in move_speeds],
        "speed_by_progress": [{"fill_bucket": p.bucket * 10, "ms": p.avg_ms} for p in progress_speed]
    }


@router.get("/stats/puzzles")
async def get_puzzle_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Puzzle ratings and comments analysis."""
    puzzles = db.query(
        Puzzle.id,
        Puzzle.difficulty,
        Puzzle.rating,
        Puzzle.user_comment,
        Puzzle.created_at,
        User.username
    ).join(User, Puzzle.user_id == User.id).filter(
        Puzzle.rating > 0
    ).order_by(desc(Puzzle.rating), desc(Puzzle.created_at)).limit(100).all()
    
    return [
        {
            "id": p.id,
            "difficulty": p.difficulty,
            "rating": p.rating,
            "comment": p.user_comment,
            "date": p.created_at.isoformat(),
            "user": p.username
        } for p in puzzles
    ]

@router.get("/logs/auth")
async def get_auth_logs(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
    limit: int = 100
):
    """Recent authentication logs."""
    logs = db.query(AuthLog).order_by(desc(AuthLog.timestamp)).limit(limit).all()
    return [log.to_dict() for log in logs]

@router.get("/logs/errors")
async def get_error_logs(
    admin: User = Depends(get_admin_user),
    lines: int = 100
):
    """Reads the last X lines of the debug log."""
    log_file = "kakuro_debug.log"
    if not os.path.exists(log_file):
        return {"error": "Log file not found"}
    
    try:
        with open(log_file, "r") as f:
            # Simple way to get last N lines
            all_lines = f.readlines()
            return {"logs": all_lines[-lines:]}
    except Exception as e:
        return {"error": str(e)}
