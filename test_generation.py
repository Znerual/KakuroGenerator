from kakuro import KakuroBoard, CellType
import sys

try:
    board = KakuroBoard(10, 10)
    board.generate_topology()

    white_count = 0
    block_count = 0
    
    with open('generation_result.txt', 'w') as f:
        for r in range(10):
            row_str = ""
            for c in range(10):
                if board.grid[r][c].type == CellType.WHITE:
                    white_count += 1
                    row_str += "."
                else:
                    block_count += 1
                    row_str += "#"
            f.write(row_str + "\n")
        
        f.write(f"\nWhites: {white_count}\n")
        f.write(f"Blocks: {block_count}\n")
        
        if white_count == 0:
            f.write("FAIL: Board is empty\n")
        else:
            f.write("SUCCESS: Board has white cells\n")

    print(f"Done. Whites: {white_count}")

except Exception as e:
    with open('generation_result.txt', 'w') as f:
        f.write(f"ERROR: {e}")
    print(e)
