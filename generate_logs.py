import kakuro

from python.kakuro_wrapper import KakuroBoard, CSPSolver

print("Generating Kakuro...")
board = kakuro.KakuroBoard(10, 10, use_cpp=True)
solver = kakuro.CSPSolver(board)
# Generate puzzle (this will trigger logging)
if solver.generate_puzzle("medium"):
    print("SUCCESS: Puzzle generated")
else:
    print("FAILURE: Could not generate puzzle")
