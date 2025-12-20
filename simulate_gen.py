from kakuro import KakuroBoard
from solver import CSPSolver

def validate_board(board, min_white_cells: int) -> bool:
    count = 0
    for r in range(board.height):
        for c in range(board.width):
            if board.grid[r][c].type.value == "WHITE":
                count += 1
    return count >= min_white_cells

def test_gen(difficulty, verify_unique):
    density_map = {"easy": 0.15, "medium": 0.25, "hard": 0.35}
    density = density_map[difficulty]
    width, height = 10, 10
    min_white = 10
    
    board = KakuroBoard(width, height)
    max_sector = 5 if verify_unique else 9
    board.generate_topology(density=density, max_sector_length=max_sector)
    
    white_cells = len(board.white_cells)
    if not validate_board(board, min_white):
        return f"FAIL_TOPOLOGY({white_cells})"
    
    solver = CSPSolver(board)
    if verify_unique:
        success, msg = solver.generate_with_uniqueness(max_iterations=5)
        if not success:
            return "FAIL_UNIQUENESS"
    else:
        success = solver.solve_fill()
        if not success:
            return "FAIL_FILL"
    return "SUCCESS"

n = 10
for diff in ["easy", "medium", "hard"]:
    print(f"Testing {diff}...")
    results = {}
    for _ in range(n):
        res = test_gen(diff, True)
        results[res] = results.get(res, 0) + 1
    print(f"{diff}: {results}")
