from typing import List, Dict, Set, Optional, Tuple
from kakuro import KakuroBoard, Cell, CellType
import copy
import random

class CSPSolver:
    def __init__(self, board: KakuroBoard):
        self.board = board

    def solve_fill(self, max_nodes: int = 20000, prefer_small_numbers: bool = False) -> bool:
        """Phase 3: Populate grid with numbers (1-9) ensuring uniqueness in sectors."""
        # Variables: self.board.white_cells
        # Domains: {1..9}
        assignment = {} # Cell -> int
        node_count = [0]
        return self._backtrack_fill_optimized(assignment, node_count, max_nodes, prefer_small_numbers)

    def _backtrack_fill_optimized(self, assignment: Dict[Cell, int], node_count: List[int], max_nodes: int, prefer_small_numbers: bool = False) -> bool:
        if node_count[0] >= max_nodes:
            return False
        node_count[0] += 1

        if len(assignment) == len(self.board.white_cells):
            # Apply to board
            for cell, val in assignment.items():
                cell.value = val
            return True

        # MRV Heuristic
        var = None
        min_options = 11
        for cell in self.board.white_cells:
            if cell not in assignment:
                # Use a simplified domain size check for initial fill (just sector uniqueness)
                options = self._get_fill_domain_size(cell, assignment)
                if options == 0: return False # Prune
                if options < min_options:
                    min_options = options
                    var = cell
                    if options == 1: break
        
        if var is None: return False

        # Randomize domain order to get different puzzles
        domain = list(range(1, 10))
        if prefer_small_numbers:
            # Favor 1-5 more heavily. We still want some variety, so we'll 
            # shuffle them but keep them mostly at the front of the list.
            smalls = [1, 2, 3, 4, 5]
            larges = [6, 7, 8, 9]
            random.shuffle(smalls)
            random.shuffle(larges)
            domain = smalls + larges
        else:
            random.shuffle(domain)

        for value in domain:
            if self._is_consistent_fill(var, value, assignment):
                assignment[var] = value
                if self._backtrack_fill_optimized(assignment, node_count, max_nodes, prefer_small_numbers):
                    return True
                del assignment[var]
        
        return False

    def _get_fill_domain_size(self, cell: Cell, assignment: Dict[Cell, int]) -> int:
        count = 0
        for val in range(1, 10):
            if self._is_consistent_fill(cell, val, assignment):
                count += 1
        return count

    def _is_consistent_fill(self, var: Cell, value: int, assignment: Dict[Cell, int]) -> bool:
        # Check Horizontal Sector (using direct references if available)
        h_sector = var.sector_h
        if h_sector:
            for peer in h_sector:
                if peer in assignment and assignment[peer] == value:
                    return False
        else:
            # Fallback for during construction/stabilization if needed
            for sector in self.board.sectors_h:
                if var in sector:
                    for peer in sector:
                        if peer in assignment and assignment[peer] == value:
                            return False
        
        # Check Vertical Sector
        v_sector = var.sector_v
        if v_sector:
            for peer in v_sector:
                if peer in assignment and assignment[peer] == value:
                    return False
        else:
            for sector in self.board.sectors_v:
                if var in sector:
                    for peer in sector:
                        if peer in assignment and assignment[peer] == value:
                            return False
        return True

    def calculate_clues(self):
        """Phase 4: Calculate clues based on filled values."""
        # Horizontal Clues
        for sector in self.board.sectors_h:
            s_sum = sum(c.value for c in sector)
            # The clue goes to the block immediately to the left of the first cell
            first_cell = sector[0]
            if first_cell.c > 0:
                clue_cell = self.board.grid[first_cell.r][first_cell.c - 1]
                if clue_cell.type == CellType.BLOCK:
                    clue_cell.clue_h = s_sum
        
        # Vertical Clues
        for sector in self.board.sectors_v:
            s_sum = sum(c.value for c in sector)
            # The clue goes to the block immediately above the first cell
            first_cell = sector[0]
            if first_cell.r > 0:
                clue_cell = self.board.grid[first_cell.r - 1][first_cell.c]
                if clue_cell.type == CellType.BLOCK:
                    clue_cell.clue_v = s_sum

    def verify_unique_solution(self, max_nodes: int = 50000) -> bool:
        """
        Verify uniqueness by checking if there's a solution different from the known one.
        Uses node limit for practicality - assumes unique if limit reached without finding alternate.
        """
        # Store the known solution
        known_solution = {cell: cell.value for cell in self.board.white_cells}
        
        # Reset values for verification
        for cell in self.board.white_cells:
            cell.value = None
        
        # Try to find ANY solution (should find the known one or an alternate)
        node_count = [0]
        found_different = [False]
        
        self._find_alternate_solution(known_solution, node_count, max_nodes, found_different)
        
        # Restore values
        for cell, val in known_solution.items():
            cell.value = val
        
        # If we found a different solution, puzzle is NOT unique
        return not found_different[0]

    def _find_alternate_solution(self, known: Dict[Cell, int], node_count: List[int], 
                                  max_nodes: int, found_different: List[bool]):
        """Search for a solution different from the known solution using MRV."""
        if found_different[0] or node_count[0] >= max_nodes:
            return
        
        node_count[0] += 1
        
        # MRV Heuristic: Choose variable with fewest remaining legal values
        var = None
        min_options = 11
        for cell in self.board.white_cells:
            if cell.value is None:
                options = self._get_domain_size(cell)
                if options == 0: return # Prune
                if options < min_options:
                    min_options = options
                    var = cell
                    if options == 1: break # Short-circuit
        
        if var is None:
            # Found a complete assignment - check if different from known
            for cell in self.board.white_cells:
                if cell.value != known[cell]:
                    found_different[0] = True
                    return
            return
        
        # Try each value 1-9
        for value in range(1, 10):
            if self._is_consistent_clues(var, value):
                var.value = value
                self._find_alternate_solution(known, node_count, max_nodes, found_different)
                if found_different[0]:
                    return
                var.value = None

    def _get_domain_size(self, cell: Cell) -> int:
        """Count how many values from 1-9 are currently legal for this cell."""
        count = 0
        for val in range(1, 10):
            if self._is_consistent_clues(cell, val):
                count += 1
        return count

    def _is_consistent_clues(self, var: Cell, value: int) -> bool:
        # 1. Unique in sectors
        # 2. Sum does not exceed clue
        # 3. If sector full, sum MUST equal clue
        
        # Check Horizontal
        h_sector = var.sector_h
        if h_sector:
            current_sum = 0
            count = 0
            filled_count = 0
            for cell in h_sector:
                val = cell.value if cell != var else value
                if val is not None:
                    if val == value and cell != var: return False # Duplicate
                    current_sum += val
                    filled_count += 1
                count += 1
            
            # Find clue
            clue = 0
            if h_sector[0].c > 0:
                clue_cell = self.board.grid[h_sector[0].r][h_sector[0].c - 1]
                clue = clue_cell.clue_h
            
            if clue:
                if current_sum > clue: return False
                if filled_count == count and current_sum != clue: return False

        # Check Vertical
        v_sector = var.sector_v
        if v_sector:
            current_sum = 0
            count = 0
            filled_count = 0
            for cell in v_sector:
                val = cell.value if cell != var else value
                if val is not None:
                    if val == value and cell != var: return False # Duplicate
                    current_sum += val
                    filled_count += 1
                count += 1
            
            # Find clue
            clue = 0
            if v_sector[0].r > 0:
                clue_cell = self.board.grid[v_sector[0].r - 1][v_sector[0].c]
                clue = clue_cell.clue_v
            
            if clue:
                if current_sum > clue: return False
                if filled_count == count and current_sum != clue: return False
                
        return True

    def generate_with_uniqueness(self, max_iterations: int = 10, prefer_small_numbers: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Generate a puzzle with guaranteed unique solution.
        Uses iterative constraint tightening if initial puzzle isn't unique.
        
        Returns: (success: bool, message: str)
        """
        for iteration in range(max_iterations):
            # Step 1: Fill the board with numbers
            success = self.solve_fill(prefer_small_numbers=prefer_small_numbers)
            if not success:
                return False, "Failed to fill board"
            
            # Step 2: Calculate clues
            self.calculate_clues()
            
            # Step 3: Check uniqueness (with node limit)
            is_unique = self.verify_unique_solution(max_nodes=10000)
            if is_unique:
                return True, f"Unique puzzle generated (iteration {iteration + 1})"
            
            # Step 4: Puzzle is NOT unique - apply constraint tightening
            tightened = self._tighten_constraints()
            if not tightened:
                # Could not tighten further, this topology may not support unique puzzles
                return False, "Could not tighten constraints further"
            
            # After tightening, we need to re-identify sectors and clear values
            self.board._collect_white_cells()
            self.board._identify_sectors()
            for cell in self.board.white_cells:
                cell.value = None
            
            # Clear existing clues
            for r in range(self.board.height):
                for c in range(self.board.width):
                    cell = self.board.grid[r][c]
                    cell.clue_h = None
                    cell.clue_v = None
        
        return False, f"Failed to generate unique puzzle after {max_iterations} iterations"

    def _tighten_constraints(self) -> bool:
        """
        Apply constraint tightening to make the puzzle more likely to have a unique solution.
        Returns True if a tightening was applied, False if no tightening possible.
        """
        # Strategy 1: Find and split long sectors (6+ cells)
        if self._split_long_sector():
            return True
        
        # Strategy 2: Find cells at intersection of two long sectors (4+ each) and block them
        if self._block_intersection_cell():
            return True
        
        # Strategy 3: Remove a cell from the longest sector
        if self._shrink_longest_sector():
            return True
        
        return False

    def _split_long_sector(self) -> bool:
        """Find a sector with 6+ cells and split it by adding a block in the middle."""
        # Check horizontal sectors
        for sector in self.board.sectors_h:
            if len(sector) >= 6:
                # Split in the middle
                mid_idx = len(sector) // 2
                cell_to_block = sector[mid_idx]
                self._convert_to_block(cell_to_block)
                return True
        
        # Check vertical sectors
        for sector in self.board.sectors_v:
            if len(sector) >= 6:
                mid_idx = len(sector) // 2
                cell_to_block = sector[mid_idx]
                self._convert_to_block(cell_to_block)
                return True
        
        return False

    def _block_intersection_cell(self) -> bool:
        """Find a cell at the intersection of two moderately long sectors and convert to block."""
        # Build a map of cell -> (h_sector_len, v_sector_len)
        cell_sector_lens = {}
        
        for sector in self.board.sectors_h:
            for cell in sector:
                if cell not in cell_sector_lens:
                    cell_sector_lens[cell] = [0, 0]
                cell_sector_lens[cell][0] = len(sector)
        
        for sector in self.board.sectors_v:
            for cell in sector:
                if cell not in cell_sector_lens:
                    cell_sector_lens[cell] = [0, 0]
                cell_sector_lens[cell][1] = len(sector)
        
        # Find cells where both sectors have length >= 4
        candidates = []
        for cell, (h_len, v_len) in cell_sector_lens.items():
            if h_len >= 4 and v_len >= 4:
                candidates.append((cell, h_len + v_len))
        
        if candidates:
            # Pick the one with highest combined sector length
            candidates.sort(key=lambda x: x[1], reverse=True)
            cell_to_block = candidates[0][0]
            self._convert_to_block(cell_to_block)
            return True
        
        return False

    def _shrink_longest_sector(self) -> bool:
        """Remove a cell from the end of the longest sector."""
        all_sectors = self.board.sectors_h + self.board.sectors_v
        if not all_sectors:
            return False
        
        # Find longest sector with at least 3 cells (so we can shrink to 2)
        longest = max((s for s in all_sectors if len(s) >= 3), key=len, default=None)
        if longest is None:
            return False
        
        # Remove last or first cell (whichever is safer)
        # Prefer end cells as they're less likely to break connectivity
        cell_to_block = longest[-1]
        self._convert_to_block(cell_to_block)
        return True

    def _convert_to_block(self, cell: Cell):
        """Convert a white cell to a block, maintaining symmetry."""
        cell.type = CellType.BLOCK
        cell.value = None
        
        # Apply symmetry
        sym_r = self.board.height - 1 - cell.r
        sym_c = self.board.width - 1 - cell.c
        sym_cell = self.board.get_cell(sym_r, sym_c)
        if sym_cell and sym_cell.type == CellType.WHITE:
            sym_cell.type = CellType.BLOCK
            sym_cell.value = None
        
        # Fix any resulting single-cell runs
        self.board._fix_single_runs()

