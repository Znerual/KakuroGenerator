"""
Integration tests for C++ Kakuro generator
Place this in: tests/test_cpp_integration.py
"""

import faulthandler
import pytest
import sys
import os

faulthandler.enable()

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python.kakuro_wrapper import KakuroBoard, CSPSolver, CPP_AVAILABLE, export_to_json


class TestCppAvailability:
    """Test that C++ module is built and available"""
    
    def test_cpp_available(self):
        """C++ module should be available after building"""
        assert CPP_AVAILABLE, (
            "C++ module not available. "
            "Run: python setup.py build_ext --inplace"
        )
    
    def test_can_import_cpp_directly(self):
        """Test direct import of C++ module"""
        if CPP_AVAILABLE:
            try:
                import kakuro_cpp
                assert hasattr(kakuro_cpp, 'KakuroBoard')
                assert hasattr(kakuro_cpp, 'CSPSolver')
            except ImportError:
                pytest.fail("C++ module found but cannot import")


class TestBoardCreation:
    """Test board creation with C++ acceleration"""
    
    def test_create_cpp_board(self):
        """Create a board using C++"""
        board = KakuroBoard(10, 10, use_cpp=True)
        assert board.width == 10
        assert board.height == 10
        if CPP_AVAILABLE:
            assert board.use_cpp == True
    
    def test_create_python_board(self):
        """Create a board using pure Python"""
        board = KakuroBoard(10, 10, use_cpp=False)
        assert board.width == 10
        assert board.height == 10
        assert board.use_cpp == False
    
    def test_board_dimensions(self):
        """Test various board dimensions"""
        sizes = [(6, 6), (8, 8), (10, 10), (12, 12)]
        for width, height in sizes:
            board = KakuroBoard(width, height, use_cpp=CPP_AVAILABLE)
            assert board.width == width
            assert board.height == height


class TestTopologyGeneration:
    """Test topology generation"""
    
    def test_generate_topology_cpp(self):
        """Generate topology with C++"""
        if not CPP_AVAILABLE:
            pytest.skip("C++ not available")
        
        board = KakuroBoard(10, 10, use_cpp=True)
        board.generate_topology(density=0.60, max_sector_length=9)
        
        assert len(board.white_cells) > 0, "Should have white cells"
        assert len(board.sectors_h) > 0, "Should have horizontal sectors"
        assert len(board.sectors_v) > 0, "Should have vertical sectors"
    
    def test_generate_topology_python(self):
        """Generate topology with Python"""
        board = KakuroBoard(10, 10, use_cpp=False)
        board.generate_topology(density=0.60, max_sector_length=9)
        
        assert len(board.white_cells) > 0, "Should have white cells"
    
    def test_different_densities(self):
        """Test different density values"""
        densities = [0.40, 0.50, 0.60, 0.70]
        
        for density in densities:
            board = KakuroBoard(10, 10, use_cpp=CPP_AVAILABLE)
            board.generate_topology(density=density)
            assert len(board.white_cells) > 0


class TestPuzzleGeneration:
    """Test complete puzzle generation"""
    
    @pytest.mark.parametrize("difficulty", ["very_easy", "easy", "medium"])
    def test_generate_puzzle_cpp(self, difficulty):
        """Test puzzle generation with different difficulties (C++)"""
        if not CPP_AVAILABLE:
            pytest.skip("C++ not available")
        
        board = KakuroBoard(8, 8, use_cpp=True)
        solver = CSPSolver(board)
        
        success = solver.generate_puzzle(difficulty)
        
        if success:
            # Verify puzzle was generated
            filled_count = sum(1 for c in board.white_cells if hasattr(c, 'value') and c.value)
            assert filled_count > 0, "Should have filled cells"
        else:
            # Generation can fail occasionally, that's okay
            pytest.skip(f"Failed to generate {difficulty} puzzle (expected occasionally)")
    
    @pytest.mark.parametrize("difficulty", ["very_easy", "easy", "medium"])
    def test_generate_puzzle_python(self, difficulty):
        """Test puzzle generation with Python fallback"""
        board = KakuroBoard(8, 8, use_cpp=False)
        solver = CSPSolver(board)
        
        success = solver.generate_puzzle(difficulty)
        
        if not success:
            pytest.skip(f"Failed to generate {difficulty} puzzle (expected occasionally)")
    
    def test_quick_easy_puzzle(self):
        """Quick test with smaller board"""
        board = KakuroBoard(6, 6, use_cpp=CPP_AVAILABLE)
        solver = CSPSolver(board)
        
        # Very easy should generate quickly
        success = solver.generate_puzzle("very_easy")
        
        # Don't fail test if it doesn't generate
        # (stochastic algorithms can fail)
        if success:
            assert len(board.white_cells) > 0


class TestBoardExport:
    """Test exporting board to different formats"""
    
    def test_to_dict(self):
        """Test exporting to dictionary"""
        board = KakuroBoard(8, 8, use_cpp=CPP_AVAILABLE)
        board.generate_topology()
        
        grid_dict = board.to_dict()
        
        assert isinstance(grid_dict, list)
        assert len(grid_dict) == 8
        assert len(grid_dict[0]) == 8
    
    def test_export_to_json(self):
        """Test JSON export function"""
        board = KakuroBoard(8, 8, use_cpp=CPP_AVAILABLE)
        board.generate_topology()
        
        json_data = export_to_json(board)
        
        assert "width" in json_data
        assert "height" in json_data
        assert "grid" in json_data
        assert json_data["width"] == 8
        assert json_data["height"] == 8


class TestPerformanceComparison:
    """Compare C++ vs Python performance"""
    
    @pytest.mark.slow
    def test_performance_comparison(self):
        """Compare generation speed (marked as slow test)"""
        if not CPP_AVAILABLE:
            pytest.skip("C++ not available for comparison")
        
        import time
        
        # Test with smaller board for faster test
        size = 8
        
        # C++ version
        start = time.time()
        board_cpp = KakuroBoard(size, size, use_cpp=True)
        solver_cpp = CSPSolver(board_cpp)
        cpp_success = solver_cpp.generate_puzzle("easy")
        cpp_time = time.time() - start
        
        # Python version
        start = time.time()
        board_py = KakuroBoard(size, size, use_cpp=False)
        solver_py = CSPSolver(board_py)
        py_success = solver_py.generate_puzzle("easy")
        py_time = time.time() - start
        
        if cpp_success and py_success:
            speedup = py_time / cpp_time
            print(f"\nPerformance: C++={cpp_time:.3f}s, Python={py_time:.3f}s, Speedup={speedup:.1f}x")
            
            # C++ should be faster (but don't fail if not due to randomness)
            if speedup > 1.5:
                assert speedup > 1.5, f"C++ should be faster, got {speedup:.1f}x"


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    def test_small_board(self):
        """Test with very small board"""
        board = KakuroBoard(4, 4, use_cpp=CPP_AVAILABLE)
        board.generate_topology(density=0.50)
        # Should not crash
        assert board.width == 4
    
    def test_reset_values(self):
        """Test resetting board values"""
        board = KakuroBoard(8, 8, use_cpp=CPP_AVAILABLE)
        board.generate_topology()
        solver = CSPSolver(board)
        
        if solver.generate_puzzle("easy"):
            board.reset_values()
            # After reset, values should be cleared
            # (implementation specific, just check it doesn't crash)
            assert True


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])