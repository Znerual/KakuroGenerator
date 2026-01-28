import sys
import os
import argparse
from sqlalchemy import func, desc
from datetime import datetime

# Ensure we can import from the python package
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from python.database import SessionLocal
from python.models import Puzzle, User

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def print_header(title):
    print(f"\n{'='*100}")
    print(f" {title}")
    print(f"{'='*100}")

def list_puzzles(db, limit=20, status_filter=None, show_all=False):
    query = db.query(Puzzle).join(User, Puzzle.user_id == User.id)
    
    if status_filter:
        query = query.filter(Puzzle.status == status_filter)
        print_header(f"PUZZLES (Status: {status_filter})")
    else:
        print_header("ALL PUZZLES")

    # Order by creation date descending
    query = query.order_by(desc(Puzzle.created_at))
    
    if not show_all:
        query = query.limit(limit)

    puzzles = query.all()
    
    if not puzzles:
        print("No puzzles found.")
        return

    # Table Header
    # ID | User | Status | Diff | Rating | Created At
    print(f"{'ID':<8} | {'User':<15} | {'Status':<10} | {'Diff':<10} | {'Rating':<6} | {'Created At':<20} | {'Hidden?'}")
    print("-" * 100)
    
    for p in puzzles:
        pid = p.id[:8] + "..."
        user = p.user.username if p.user and p.user.username else (p.user.email if p.user else "Unknown")
        user = user[:15]
        
        # Check if it would be hidden from dashboard (Rating > 0 check)
        is_hidden = "HIDDEN" if (p.rating is None or p.rating == 0) else "VISIBLE"
        
        created = p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else "Unknown"
        rating = str(p.rating) if p.rating is not None else "0"
        
        print(f"{pid:<8} | {user:<15} | {p.status:<10} | {p.difficulty:<10} | {rating:<6} | {created:<20} | {is_hidden}")

def inspect_puzzle_details(db, puzzle_id):
    puzzle = db.query(Puzzle).filter(Puzzle.id.like(f"{puzzle_id}%")).first()
    
    if not puzzle:
        print(f"Puzzle with ID starting with '{puzzle_id}' not found.")
        return

    print_header(f"DETAILS FOR PUZZLE: {puzzle.id}")
    print(f"User:           {puzzle.user.username if puzzle.user else 'Unknown'} ({puzzle.user_id})")
    print(f"Status:         {puzzle.status}")
    print(f"Difficulty:     {puzzle.difficulty}")
    print(f"Rating:         {puzzle.rating}")
    print(f"User Comment:   {puzzle.user_comment}")
    print(f"Created At:     {puzzle.created_at}")
    print(f"Updated At:     {puzzle.updated_at}")
    print(f"Template ID:    {puzzle.template_id}")
    print(f"Interactive:    {len(puzzle.interactions)} interactions recorded")
    
    print("\n--- Notes ---")
    print(f"Notebook: {puzzle.notebook[:100]}..." if puzzle.notebook else "No notebook entries.")

def main():
    parser = argparse.ArgumentParser(description="Inspect Kakuro Puzzles")
    parser.add_argument("command", choices=["list", "details"], help="Command to run")
    parser.add_argument("--id", type=str, help="Puzzle ID (partial ok) for details")
    parser.add_argument("--limit", type=int, default=20, help="Number of rows to list")
    parser.add_argument("--status", type=str, help="Filter by status (e.g., 'started', 'solved')")
    parser.add_argument("--all", action="store_true", help="Show all (no limit)")
    
    args = parser.parse_args()
    
    db = next(get_db())
    
    try:
        if args.command == "list":
            list_puzzles(db, limit=args.limit, status_filter=args.status, show_all=args.all)
        elif args.command == "details":
            if not args.id:
                print("Error: --id is required for details command.")
                return
            inspect_puzzle_details(db, args.id)
    except Exception as e:
        print(f"Error accessing database: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
