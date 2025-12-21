
import sys
import os
import random
import traceback

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("kakuro_debug.log"),
        logging.StreamHandler()
    ]
)

from kakuro import KakuroBoard
from solver import CSPSolver
from main import DIFFICULTY_MAP, validate_board, MIN_WHITE_CELLS

def run_repro():
    width, height = 10, 10
    difficulty = "hard"
    verify_unique = True
    density = DIFFICULTY_MAP.get(difficulty, 0.15)
    
    print(f"Starting repro with width={width}, height={height}, difficulty={difficulty}")
    
    for i in range(100):
        print(f"--- Attempt {i} ---")
        try:
            board = KakuroBoard(width, height)
            max_sector = 4 if (verify_unique) else 9
            if difficulty == "hard": max_sector = 4
            
            board.generate_topology(density=density, max_sector_length=max_sector)
            
            if len(board.white_cells) < 10:
                print("Too few white cells, skipping...")
                continue
                
            solver = CSPSolver(board)
            success, msg = solver.generate_with_uniqueness(max_iterations=5)
            print(f"Result: {success}, {msg}")
            
            if not success and "iterations" in msg:
                print("Failed to generate unique puzzle after max iterations")
                
        except Exception as e:
            print(f"CRASHED: {e}")
            traceback.print_exc()
            break

if __name__ == "__main__":
    run_repro()
