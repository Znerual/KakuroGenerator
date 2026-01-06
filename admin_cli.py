import argparse
import sys
import uuid
from sqlalchemy.orm import Session
from kakuro.models import User, PuzzleTemplate, PuzzleInteraction, ScoreRecord, UserSession, Puzzle
from kakuro.database import SessionLocal
from kakuro.auth import hash_password
from datetime import datetime, timezone

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_user(username, email, password, is_admin=False):
    db = SessionLocal()
    try:
        # Check if exists
        existing = db.query(User).filter((User.username == username) | (User.email == email)).first()
        if existing:
            print(f"Error: User with username '{username}' or email '{email}' already exists.")
            return

        hashed_password = hash_password(password)
        new_user = User(
            id=str(uuid.uuid4()),
            username=username,
            email=email,
            hashed_password=hashed_password,
            is_admin=is_admin,
            email_verified=True # CLI created users are verified by default
        )
        db.add(new_user)
        db.commit()
        print(f"User '{username}' created successfully (Admin: {is_admin}).")
    finally:
        db.close()

def reset_puzzles():
    """Clears all puzzle-related data while keeping User accounts."""
    db = SessionLocal()
    print("!!! WARNING !!!")
    print("This will delete ALL Puzzle Templates, User Progress, Interactions, and Scores.")
    print("User accounts will be kept, but their stats (solved count/score) will be reset to 0.")
    
    confirm = input("\nType 'RESET' to confirm this action: ")
    if confirm != "RESET":
        print("Reset aborted.")
        return

    try:
        print("Cleaning up database...")
        
        # 1. Delete dependent records first (Foreign Key constraints)
        db.query(PuzzleInteraction).delete()
        db.query(ScoreRecord).delete()
        
        # 2. Delete user puzzle instances
        db.query(Puzzle).delete()
        
        # 3. Delete master templates
        db.query(PuzzleTemplate).delete()
        
        # 4. Reset User statistics so leaderboards are fresh
        db.query(User).update({
            User.kakuros_solved: 0,
            User.total_score: 0
        })
        
        db.commit()
        print("Successfully reset the system. Puzzles cleared and user stats zeroed.")
    except Exception as e:
        db.rollback()
        print(f"Error during reset: {e}")
    finally:
        db.close()

def list_users():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        print(f"{'ID':<40} | {'Username':<20} | {'Email':<30} | {'Admin':<5} | {'Verified':<8}")
        print("-" * 110)
        for u in users:
            print(f"{u.id:<40} | {u.username:<20} | {u.email:<30} | {str(u.is_admin):<5} | {str(u.email_verified):<8}")
    finally:
        db.close()

def promote_user(id_or_username):
    db = SessionLocal()
    try:
        user = db.query(User).filter((User.id == id_or_username) | (User.username == id_or_username)).first()
        if not user:
            print(f"Error: User '{id_or_username}' not found.")
            return
        
        user.is_admin = True
        db.commit()
        print(f"User '{user.username}' promoted to Admin.")
    finally:
        db.close()

def edit_user(id_or_username, password=None, email=None):
    db = SessionLocal()
    try:
        user = db.query(User).filter((User.id == id_or_username) | (User.username == id_or_username)).first()
        if not user:
            print(f"Error: User '{id_or_username}' not found.")
            return
        
        if password:
            user.hashed_password = hash_password(password)
            print(f"Password updated for '{user.username}'.")
        if email:
            user.email = email
            print(f"Email updated to '{email}' for '{user.username}'.")
            
        db.commit()
    finally:
        db.close()

def delete_user(id_or_username):
    db = SessionLocal()
    try:
        user = db.query(User).filter((User.id == id_or_username) | (User.username == id_or_username)).first()
        if not user:
            print(f"Error: User '{id_or_username}' not found.")
            return
        
        username = user.username # Save name for print
        db.delete(user)
        db.commit()
        print(f"User '{username}' (ID: {user.id}) deleted successfully.")
    except Exception as e:
        print(f"Error deleting user: {e}")
        db.rollback()
    finally:
        db.close()

def main():
    parser = argparse.ArgumentParser(description="Kakuro Admin CLI")
    subparsers = parser.add_subparsers(dest="command")

    # Create
    create_parser = subparsers.add_parser("create", help="Create a new user")
    create_parser.add_argument("username")
    create_parser.add_argument("email")
    create_parser.add_argument("password")
    create_parser.add_argument("--admin", action="store_true", help="Set as admin")

    # List
    subparsers.add_parser("list", help="List all users")

    # Promote
    promote_parser = subparsers.add_parser("promote", help="Promote a user to admin")
    promote_parser.add_argument("user", help="ID or Username")

    # Edit
    edit_parser = subparsers.add_parser("edit", help="Edit a user")
    edit_parser.add_argument("user", help="ID or Username")
    edit_parser.add_argument("--password", help="New password")
    edit_parser.add_argument("--email", help="New email")

    # Delete
    delete_parser = subparsers.add_parser("delete", help="Delete a user")
    delete_parser.add_argument("user", help="ID or Username")

    # Reset System
    subparsers.add_parser("reset-system", help="Clear all puzzles, templates, and scores (Keep users)")

    args = parser.parse_args()

    if args.command == "create":
        create_user(args.username, args.email, args.password, args.admin)
    elif args.command == "list":
        list_users()
    elif args.command == "promote":
        promote_user(args.user)
    elif args.command == "edit":
        edit_user(args.user, args.password, args.email)
    elif args.command == "delete":
        delete_user(args.user)
    elif args.command == "reset-system":
        reset_puzzles()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
