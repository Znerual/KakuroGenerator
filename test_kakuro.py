import unittest
from kakuro import KakuroBoard, CellType
from solver import CSPSolver

class TestKakuro(unittest.TestCase):
    def test_topology(self):
        board = KakuroBoard(10, 10)
        board.generate_topology()
        self.assertTrue(len(board.white_cells) > 0)
        # Check symmetry (roughly)
        # Check connectivity (should be connected)
        
    def test_solver(self):
        board = KakuroBoard(5, 5)
        # Force a simple grid for deterministic testing if needed, 
        # but let's trust the generator for now.
        board.generate_topology(density=0.2)
        
        solver = CSPSolver(board)
        success = solver.solve_fill()
        self.assertTrue(success, "Solver should find a valid fill")
        
        # Check constraints
        for sector in board.sectors_h:
            vals = [c.value for c in sector]
            self.assertEqual(len(vals), len(set(vals)), "Row sector must have unique values")
            
        for sector in board.sectors_v:
            vals = [c.value for c in sector]
            self.assertEqual(len(vals), len(set(vals)), "Col sector must have unique values")
            
        solver.calculate_clues()
        # Check if clues exist
        clues = 0
        for r in range(5):
            for c in range(5):
                cell = board.get_cell(r, c)
                if cell.type == CellType.BLOCK:
                    if cell.clue_h or cell.clue_v:
                        clues += 1
        self.assertTrue(clues > 0, "Should have generated clues")

if __name__ == '__main__':
    unittest.main()
