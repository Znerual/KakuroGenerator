
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from python.kakuro import KakuroBoard, CellType
from python.solver import CSPSolver
import random

def test_repro():
    print("Testing for non-unique puzzles...")
    non_unique_found = 0
    total = 20
    
    for i in range(total):
        # Generate a puzzle WITHOUT uniqueness check (like currently done by default)
        width, height = 8, 8
        board = KakuroBoard(width, height)
        board.generate_topology(density=0.15, max_sector_length=9)
        
        solver = CSPSolver(board)
        # Generate WITH uniqueness check
        success, msg = solver.generate_with_uniqueness(max_iterations=10)
        if success:
            # Verify uniqueness again with a higher node limit to be sure
            is_unique = solver.verify_unique_solution(max_nodes=100000)
            if not is_unique:
                non_unique_found += 1
                print(f"Puzzle {i+1}: NOT UNIQUE!")
            else:
                print(f"Puzzle {i+1}: Unique.")
        else:
            print(f"Puzzle {i+1}: Generation failed (fill).")

    print(f"\nResult: Found {non_unique_found} / {total} non-unique puzzles.")

if __name__ == "__main__":
    test_repro()
