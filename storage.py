import os
import json
import uuid
from typing import List, Dict, Optional

STORAGE_DIR = "saved_puzzles"

def ensure_storage_dir():
    if not os.path.exists(STORAGE_DIR):
        os.makedirs(STORAGE_DIR)

def save_puzzle(puzzle_id: str, data: Dict):
    ensure_storage_dir()
    filepath = os.path.join(STORAGE_DIR, f"{puzzle_id}.json")
    with open(filepath, "w") as f:
        json.dump(data, f, indent=4)

def load_puzzle(puzzle_id: str) -> Optional[Dict]:
    filepath = os.path.join(STORAGE_DIR, f"{puzzle_id}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r") as f:
        return json.load(f)

def list_puzzles() -> List[Dict]:
    ensure_storage_dir()
    puzzles = []
    for filename in os.listdir(STORAGE_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(STORAGE_DIR, filename)
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                    # Return metadata
                    puzzles.append({
                        "id": data.get("id"),
                        "difficulty": data.get("difficulty"),
                        "width": data.get("width"),
                        "height": data.get("height"),
                        "status": data.get("status", "started"),
                        "timestamp": data.get("timestamp")
                    })
            except Exception as e:
                print(f"Error reading {filename}: {e}")
    return puzzles

def delete_puzzle(puzzle_id: str) -> bool:
    filepath = os.path.join(STORAGE_DIR, f"{puzzle_id}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
        return True
    return False
