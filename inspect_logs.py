import sys
import os
import argparse
from sqlalchemy import func, text
from sqlalchemy.orm import Session

# Ensure we can import from the python package
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from python.database import SessionLocal
from python.models import PuzzleInteraction, Puzzle

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def print_header(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def inspect_summary(db: Session):
    print_header("DATABASE SUMMARY")
    
    total_interactions = db.query(PuzzleInteraction).count()
    total_puzzles = db.query(Puzzle).count()
    
    print(f"Total Puzzles in DB:      {total_puzzles}")
    print(f"Total Interactions Logged: {total_interactions}")
    
    if total_interactions == 0:
        print("\n[!] WARNING: No interactions found. Database write failed or table is empty.")
        return

    # Breakdown by action type
    print("\n--- Breakdown by Action Type ---")
    actions = db.query(
        PuzzleInteraction.action_type, 
        func.count(PuzzleInteraction.id)
    ).group_by(PuzzleInteraction.action_type).all()
    
    for action, count in actions:
        print(f"{action:<15} : {count}")

def diagnose_dashboard(db: Session):
    print_header("DASHBOARD DIAGNOSTIC (Move Speed vs Fill State)")
    
    # 1. Check INPUTs
    inputs = db.query(PuzzleInteraction).filter(PuzzleInteraction.action_type == "INPUT").count()
    print(f"1. Total 'INPUT' actions: {inputs}")
    
    if inputs == 0:
        print("   -> STOP: The dashboard only looks at 'INPUT' actions. None found.")
        return

    # 2. Check Duration
    has_duration = db.query(PuzzleInteraction).filter(
        PuzzleInteraction.action_type == "INPUT",
        PuzzleInteraction.duration_ms > 0
    ).count()
    print(f"2. Inputs with duration_ms > 0: {has_duration}")
    
    if has_duration == 0:
        print("   -> [!] ISSUE FOUND: 'duration_ms' is 0 or NULL.")
        print("      The dashboard ignores 0ms durations.")
        
    # 3. Check Fill Count
    has_fill = db.query(PuzzleInteraction).filter(
        PuzzleInteraction.action_type == "INPUT",
        PuzzleInteraction.fill_count.isnot(None)
    ).count()
    print(f"3. Inputs with fill_count set:  {has_fill}")

    if has_fill == 0:
        print("   -> [!] ISSUE FOUND: 'fill_count' is NULL.")
        print("      The dashboard needs this to group data into buckets.")

    # 4. Check Valid Data (The actual dashboard query criteria)
    valid_data = db.query(PuzzleInteraction).filter(
        PuzzleInteraction.action_type == "INPUT",
        PuzzleInteraction.duration_ms > 0,
        PuzzleInteraction.fill_count.isnot(None)
    ).count()
    
    print(f"\n>>> Total valid rows for Dashboard: {valid_data} <<<")
    
    if valid_data > 0:
        print("\nSample Valid Row:")
        row = db.query(PuzzleInteraction).filter(
            PuzzleInteraction.action_type == "INPUT",
            PuzzleInteraction.duration_ms > 0,
            PuzzleInteraction.fill_count.isnot(None)
        ).first()
        print(f"  ID: {row.id} | Dur: {row.duration_ms}ms | Fill: {row.fill_count} | Time: {row.client_timestamp}")
    else:
        print("\n[!] Dashboard is empty because no rows meet all 3 criteria above.")

def list_latest(db: Session, limit=10):
    print_header(f"LATEST {limit} INTERACTIONS")
    
    rows = db.query(PuzzleInteraction).order_by(PuzzleInteraction.id.desc()).limit(limit).all()
    
    if not rows:
        print("No logs found.")
        return

    # Simple table formatting
    print(f"{'ID':<6} | {'Type':<10} | {'Dur(ms)':<8} | {'Fill':<5} | {'PuzzleID':<10}")
    print("-" * 60)
    
    for r in rows:
        dur = str(r.duration_ms) if r.duration_ms is not None else "NULL"
        fill = str(r.fill_count) if r.fill_count is not None else "NULL"
        pid = str(r.puzzle_id)[:8] + "..." if r.puzzle_id else "NULL"
        
        print(f"{r.id:<6} | {r.action_type:<10} | {dur:<8} | {fill:<5} | {pid:<10}")

def main():
    parser = argparse.ArgumentParser(description="Inspect Kakuro Interaction Logs")
    parser.add_argument("command", choices=["summary", "diagnose", "list"], help="Command to run")
    parser.add_argument("--limit", type=int, default=20, help="Number of rows to list")
    
    args = parser.parse_args()
    
    db = next(get_db())
    
    try:
        if args.command == "summary":
            inspect_summary(db)
        elif args.command == "diagnose":
            diagnose_dashboard(db)
        elif args.command == "list":
            list_latest(db, args.limit)
    except Exception as e:
        print(f"Error accessing database: {e}")
        # Debug connection info
        print(f"DB URL: {os.getenv('DATABASE_URL', 'sqlite:///./kakuro.db')}")
    finally:
        db.close()

if __name__ == "__main__":
    main()