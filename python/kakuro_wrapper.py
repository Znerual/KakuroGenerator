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
    import kakuro.kakuro_cpp as kakuro_cpp
    
    # Map C++ classes to local names
    _KakuroBoard = kakuro_cpp.KakuroBoard
    _CSPSolver = kakuro_cpp.CSPSolver
    _KakuroDifficultyEstimator = kakuro_cpp.KakuroDifficultyEstimator
    CPP_AVAILABLE = True
    print("✓ C++ acceleration loaded successfully")
except ImportError as e:
    try:
        import kakuro_cpp as kakuro_cpp
        # Map C++ classes to local names
        _KakuroBoard = kakuro_cpp.KakuroBoard
        _CSPSolver = kakuro_cpp.CSPSolver
        _KakuroDifficultyEstimator = kakuro_cpp.KakuroDifficultyEstimator
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
        else:
            # Fallback to pure Python implementation
            try:
                from .kakuro import KakuroBoard as PyKakuroBoard
                self._board = PyKakuroBoard(width, height)
            except ImportError:
                # Alternative import path
                from kakuro import KakuroBoard as PyKakuroBoard
                self._board = PyKakuroBoard(width, height)
    
    def generate_topology(self, density: float = 0.60, max_sector_length: int = 9, difficulty: str = "medium"):
        """Generate the board topology."""
        # Note: Added difficulty argument to match updated C++ API
        self._board.generate_topology(density, max_sector_length, difficulty)
    
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
                from .solver import CSPSolver as PyCSPSolver
                self._solver = PyCSPSolver(board._board)
            except ImportError:
                from solver import CSPSolver as PyCSPSolver
                self._solver = PyCSPSolver(board._board)
    
    def generate_puzzle(self, difficulty: str = "medium") -> bool:
        """
        Generate a complete, unique Kakuro puzzle.
        """
        return self._solver.generate_puzzle(difficulty)
    
    def solve_fill(self, difficulty: str = "medium", max_nodes: int = 30000) -> bool:
        """Fill the board with valid numbers."""
        return self._solver.solve_fill(difficulty, max_nodes)
    
    def calculate_clues(self):
        """Calculate clues based on current board state."""
        self._solver.calculate_clues()


class KakuroDifficultyEstimator:
    """Python wrapper for Difficulty Estimator."""
    
    def __init__(self, board: KakuroBoard):
        self.board = board
        
        if board.use_cpp:
            self._estimator = _KakuroDifficultyEstimator(board._board)
        else:
            try:
                from .difficulty_estimator import KakuroDifficultyEstimator as PyEst
                self._estimator = PyEst(board._board)
            except ImportError:
                from difficulty_estimator import KakuroDifficultyEstimator as PyEst
                self._estimator = PyEst(board._board)
               

    def estimate_difficulty(self) -> float:
        """Returns the difficulty score."""
        if self.board.use_cpp:
            return self._estimator.estimate_difficulty()
        else:
            return self._estimator.estimate_difficulty()


def generate_kakuro(width: int, height: int, difficulty: str = "medium", 
                   use_cpp: bool = True) -> KakuroBoard:
    """
    Convenience function to generate a complete Kakuro puzzle.
    """
    #print(f"Generating {width}x{height} {difficulty} puzzle (C++={use_cpp})...")
    
    # Try up to 20 times to get a valid puzzle
    for i in range(20):
        board = KakuroBoard(width, height, use_cpp=use_cpp)
        solver = CSPSolver(board)
        
        success = solver.generate_puzzle(difficulty)
        
        if success:
            # Estimate actual difficulty
            estimator = KakuroDifficultyEstimator(board)
            score = estimator.estimate_difficulty()
            
            #print(f"✓ Generated puzzle successfully. Score: {score} ({type(score)})")
            return board
    
    print(f"⚠ Failed to generate puzzle with difficulty {difficulty}")
    return board


def export_to_json(board: KakuroBoard) -> dict:
    """
    Export board to JSON-serializable format.
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
            
            if "value" in cell_dict and cell_dict["value"] is not None:
                cell_data["value"] = int(cell_dict["value"])
            if "clue_h" in cell_dict and cell_dict["clue_h"] is not None:
                cell_data["clue_h"] = int(cell_dict["clue_h"])
            if "clue_v" in cell_dict and cell_dict["clue_v"] is not None:
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
        board = generate_kakuro(10, 10, difficulty="very_easy", use_cpp=True)
        
        print(f"Generated board with {len(board.white_cells)} white cells")
        
        # Test difficulty estimator explicitly
        est = KakuroDifficultyEstimator(board)
        print(f"Difficulty Score: {est.estimate_difficulty()}")
        
    else:
        print("\n⚠ C++ module not available")
        print("\nTo build the C++ module:")
        print("  1. Make sure you have CMake installed")
        print("  2. Run: pip install pybind11")
        print("  3. Run: python setup.py build_ext --inplace")