"""
Python wrapper for the C++ Kakuro generator.
Provides a Pythonic interface while leveraging C++ performance.
This version integrates with the existing FastAPI backend.
"""

import sys
import os

# Try to import the C++ module
try:
    # Look for the module in the python directory
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from kakuro_cpp import KakuroBoard as _KakuroBoard
    from kakuro_cpp import CSPSolver as _CSPSolver
    from kakuro_cpp import CellType
    CPP_AVAILABLE = True
    print("✓ C++ acceleration loaded successfully")
except ImportError as e:
    CPP_AVAILABLE = False
    print(f"⚠ C++ module not available: {e}")
    print("  Falling back to pure Python implementation")
    print("  To enable C++ acceleration, run: python setup.py build_ext --inplace")


class KakuroBoard:
    """Python wrapper for KakuroBoard that provides a familiar interface."""
    
    def __init__(self, width: int, height: int, use_cpp: bool = True):
        self.width = width
        self.height = height
        self.use_cpp = use_cpp and CPP_AVAILABLE
        
        if self.use_cpp:
            self._board = _KakuroBoard(width, height)
            print(f"Using C++ board ({width}x{height})")
        else:
            # Fallback to pure Python implementation
            # Import from your existing python/kakuro.py
            try:
                from python.kakuro import KakuroBoard as PyKakuroBoard
                self._board = PyKakuroBoard(width, height)
                print(f"Using Python board ({width}x{height})")
            except ImportError:
                # Alternative import path
                from kakuro import KakuroBoard as PyKakuroBoard
                self._board = PyKakuroBoard(width, height)
    
    def generate_topology(self, density: float = 0.60, max_sector_length: int = 9):
        """Generate the board topology."""
        self._board.generate_topology(density, max_sector_length)
    
    def reset_values(self):
        """Clear all values and clues."""
        self._board.reset_values()
    
    def get_cell(self, r: int, c: int):
        """Get cell at position (r, c)."""
        return self._board.get_cell(r, c)
    
    def to_dict(self):
        """Export board to dictionary format."""
        if self.use_cpp:
            return self._board.to_dict()
        else:
            # Convert Python board to dict
            result = []
            for row in self._board.grid:
                result.append([cell.to_dict() for cell in row])
            return result
    
    def get_grid(self):
        """Get the grid as a 2D list of cells."""
        if self.use_cpp:
            return self._board.get_grid()
        else:
            return self._board.grid
    
    @property
    def white_cells(self):
        """Get list of white cells."""
        return self._board.white_cells
    
    @property
    def sectors_h(self):
        """Get horizontal sectors."""
        return self._board.sectors_h
    
    @property
    def sectors_v(self):
        """Get vertical sectors."""
        return self._board.sectors_v


class CSPSolver:
    """Python wrapper for CSPSolver."""
    
    def __init__(self, board: KakuroBoard):
        self.board = board
        
        if board.use_cpp:
            self._solver = _CSPSolver(board._board)
        else:
            try:
                from python.solver import CSPSolver as PyCSPSolver
                self._solver = PyCSPSolver(board._board)
            except ImportError:
                from solver import CSPSolver as PyCSPSolver
                self._solver = PyCSPSolver(board._board)
    
    def generate_puzzle(self, difficulty: str = "medium") -> bool:
        """
        Generate a complete, unique Kakuro puzzle.
        
        Args:
            difficulty: One of "very_easy", "easy", "medium", "hard"
        
        Returns:
            True if successful, False otherwise
        """
        return self._solver.generate_puzzle(difficulty)
    
    def solve_fill(self, difficulty: str = "medium", max_nodes: int = 30000) -> bool:
        """Fill the board with valid numbers."""
        return self._solver.solve_fill(difficulty, max_nodes)
    
    def calculate_clues(self):
        """Calculate clues based on current board state."""
        self._solver.calculate_clues()


def generate_kakuro(width: int, height: int, difficulty: str = "medium", 
                   use_cpp: bool = True) -> KakuroBoard:
    """
    Convenience function to generate a complete Kakuro puzzle.
    
    Args:
        width: Board width
        height: Board height
        difficulty: Difficulty level ("very_easy", "easy", "medium", "hard")
        use_cpp: Whether to use C++ implementation (faster)
    
    Returns:
        KakuroBoard with generated puzzle
    """
    print(f"Generating {width}x{height} {difficulty} puzzle...")
    board = KakuroBoard(width, height, use_cpp=use_cpp)
    solver = CSPSolver(board)
    
    success = solver.generate_puzzle(difficulty)
    
    if not success:
        print(f"⚠ Failed to generate puzzle with difficulty {difficulty}")
    else:
        print(f"✓ Generated puzzle successfully")
    
    return board


def export_to_json(board: KakuroBoard) -> dict:
    """
    Export board to JSON-serializable format.
    
    Returns:
        Dictionary representing the board state
    """
    grid_dict = board.to_dict()
    
    # Convert to more JSON-friendly format
    result = {
        "width": board.width,
        "height": board.height,
        "grid": []
    }
    
    for row in grid_dict:
        result_row = []
        for cell_dict in row:
            # Convert string keys to proper types
            cell_data = {
                "r": int(cell_dict["r"]),
                "c": int(cell_dict["c"]),
                "type": cell_dict["type"],
            }
            
            if "value" in cell_dict:
                cell_data["value"] = int(cell_dict["value"])
            if "clue_h" in cell_dict:
                cell_data["clue_h"] = int(cell_dict["clue_h"])
            if "clue_v" in cell_dict:
                cell_data["clue_v"] = int(cell_dict["clue_v"])
            
            result_row.append(cell_data)
        result["grid"].append(result_row)
    
    return result


# Check if C++ module is available on import
if __name__ == "__main__":
    print(f"C++ module available: {CPP_AVAILABLE}")
    
    if CPP_AVAILABLE:
        print("\n✓ C++ acceleration is working!")
        print("\nGenerating test puzzle...")
        board = generate_kakuro(10, 10, difficulty="medium", use_cpp=True)
        
        print(f"Generated board with {len(board.white_cells)} white cells")
        print(f"Horizontal sectors: {len(board.sectors_h)}")
        print(f"Vertical sectors: {len(board.sectors_v)}")
    else:
        print("\n⚠ C++ module not available")
        print("\nTo build the C++ module:")
        print("  1. Make sure you have CMake installed")
        print("  2. Run: pip install pybind11")
        print("  3. Run: python setup.py build_ext --inplace")