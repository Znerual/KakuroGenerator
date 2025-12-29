import unittest
from python.kakuro import KakuroBoard, CellType
from python.solver import CSPSolver
import sys

class TestKakuro(unittest.TestCase):
    def test_topology(self):
        board = KakuroBoard(10, 10)
        board.generate_topology()
        self.assertTrue(len(board.white_cells) > 0)
        
    def test_solver(self):
        board = KakuroBoard(5, 5)
        board.generate_topology(density=0.2)
        solver = CSPSolver(board)
        success = solver.solve_fill()
        self.assertTrue(success)
        
        solver.calculate_clues()
        clues = 0
        for r in range(5):
            for c in range(5):
                cell = board.get_cell(r, c)
                if cell.type == CellType.BLOCK:
                    if cell.clue_h or cell.clue_v:
                        clues += 1
        self.assertTrue(clues > 0)

if __name__ == '__main__':
    with open('test_result.txt', 'w') as f:
        runner = unittest.TextTestRunner(stream=f)
        unittest.main(testRunner=runner, exit=False)
