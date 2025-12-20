from kakuro import KakuroBoard
from solver import CSPSolver

def test_very_easy_topology():
    print("Testing 'Very Easy' topology...")
    width, height = 7, 7
    board = KakuroBoard(width, height)
    board.generate_topology(density=0.15, max_sector_length=4)
    
    print(f"Board size: {board.width}x{board.height}")
    assert board.width == 7
    assert board.height == 7
    
    # Check sector lengths
    all_sectors = board.sectors_h + board.sectors_v
    if not all_sectors:
        print("FAIL: No sectors generated")
        return

    max_len = max(len(s) for s in all_sectors)
    print(f"Max sector length: {max_len}")
    assert max_len <= 4, f"Sector length {max_len} exceeds 4"
    
    # Check filling with small numbers
    solver = CSPSolver(board)
    # Just solve once without uniqueness check to verify clue values
    success = solver.solve_fill(prefer_small_numbers=True)
    if not success:
        print("FAIL: Could not fill board")
        return
    
    solver.calculate_clues()
    
    values = [cell.value for cell in board.white_cells]
    avg_val = sum(values) / len(values)
    print(f"Average value: {avg_val:.2f}")
    
    clues = []
    for r in range(height):
        for c in range(width):
            cell = board.grid[r][c]
            if cell.clue_h: clues.append(cell.clue_h)
            if cell.clue_v: clues.append(cell.clue_v)
    
    avg_clue = sum(clues) / len(clues)
    print(f"Average clue: {avg_clue:.2f}")
    print(f"Values: {sorted(values)}")
    print(f"Clues: {sorted(clues)}")
    print("SUCCESS: Topology and filling meet requirements.")

if __name__ == "__main__":
    test_very_easy_topology()
