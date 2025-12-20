from kakuro import KakuroBoard, CellType
from solver import CSPSolver
import statistics

def test_very_easy():
    print("Testing 'Very Easy' generation...")
    width, height = 7, 7
    board = KakuroBoard(width, height)
    board.generate_topology(density=0.15, max_sector_length=4)
    
    solver = CSPSolver(board)
    success, msg = solver.generate_with_uniqueness(max_iterations=10, prefer_small_numbers=True)
    
    if not success:
        print(f"FAILED: {msg}")
        return

    print(f"SUCCESS: {msg}")
    
    # Check sector lengths
    all_sectors = board.sectors_h + board.sectors_v
    max_len = max(len(s) for s in all_sectors)
    print(f"Max sector length: {max_len}")
    assert max_len <= 4, f"Sector length {max_len} exceeds 4"
    
    # Check if numbers are generally small
    values = [cell.value for cell in board.white_cells if cell.value is not None]
    avg_val = statistics.mean(values)
    print(f"Average value: {avg_val:.2f}")
    print(f"Values: {sorted(values)}")
    
    # Check clues
    clues = []
    for r in range(height):
        for c in range(width):
            cell = board.grid[r][c]
            if cell.type == CellType.BLOCK:
                if cell.clue_h: clues.append(cell.clue_h)
                if cell.clue_v: clues.append(cell.clue_v)
    
    avg_clue = statistics.mean(clues)
    print(f"Average clue: {avg_clue:.2f}")
    print(f"Clues: {sorted(clues)}")

if __name__ == "__main__":
    test_very_easy()
