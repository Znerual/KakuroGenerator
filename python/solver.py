from collections import deque
from typing import List, Dict, Set, Optional, Tuple
from python.kakuro import KakuroBoard, Cell, CellType
import copy
import random
import logging

logger = logging.getLogger("kakuro_solver")

class CSPSolver:
    def __init__(self, board: KakuroBoard):
        self.board = board

    def generate_puzzle(self, difficulty: str = "medium") -> bool:
        """
        Main Pipeline:
        1. Generate Topology
        2. Solve Fill (create numbers)
        3. Check Uniqueness
        4. If not unique, fix ambiguous area and repeat.
        """
        max_retries = 80
        
        for attempt in range(max_retries):
            # 1. Generate Topology 
            # We regenerate topology frequently if filling fails, 
            # because some intricate shapes are mathematically impossible to fill
            if attempt % 5 == 0: 
                d = 0.50 if difficulty == "very_easy" else (0.55 if difficulty == "easy" else 0.60)
                # For hard, we want more density (longer runs)
                if difficulty == "hard": d = 0.65
                
                self.board.generate_topology(density=d)
            
            # Safety check: Is board empty?
            if len(self.board.white_cells) < 4:
                continue

            # 2. Fill grid with numbers
            self.board.reset_values()

            if not self.solve_fill(difficulty=difficulty):
                continue # Bad topology, retry
            
            # 3. Calculate Clues based on the fill
            self.calculate_clues()
            
            # 4. Verify Uniqueness
            # Find an alternate solution
            unique, alt_solution = self.check_uniqueness()
            
            if unique:
                print(f"Success! Unique puzzle generated on attempt {attempt}.")
                return True
            
            # 5. Fix Uniqueness (Targeted Repair)
            # If we are here, we have Solution A (in board) and Solution B (in alt_solution)
            # Find a cell where they differ and block it.
            # 5. Fix Uniqueness (Targeted Repair)
            # Try to block a cell to remove ambiguity WITHOUT breaking the board
            repaired = self._repair_ambiguity_safely(alt_solution)
            
            if not repaired:
                # If we couldn't repair it safely (e.g. any block disconnects the graph),
                # we must regenerate the topology.
                # Force regeneration in next loop by manipulating loop counter or just continue
                # (The 'continue' will hit the solve_fill, fail or succeed, and eventually 
                # hit the 'attempt % 5' check to regen topology if we get stuck)
                d = 0.50 if difficulty == "very easy" else (0.55 if difficulty == "easy" else 0.60)
                # For hard, we want more density (longer runs)
                if difficulty == "hard": d = 0.65
                
                self.board.generate_topology(density=d)
                
            
        return False


    def solve_fill(self, difficulty: str = "medium", max_nodes: int = 30000) -> bool:
        """Backtracking to fill the grid with valid numbers 1-9."""
        assignment = {}
        node_count = [0]
        
        # Difficulty Weighting for numbers 1 through 9
        # format: [weight_for_1, weight_for_2, ..., weight_for_9]
        
        if difficulty == "very_easy":
            # Extreme bias towards 1, 2, 8, 9
            # Creates sums with unique partitions (e.g., 3, 4, 17)
            domain_weights = [20, 15, 5, 1, 1, 1, 5, 15, 20]
            
        elif difficulty == "easy":
            # Strong bias towards edges, but allows some variety
            domain_weights = [10, 8, 6, 2, 1, 2, 6, 8, 10]
            
        elif difficulty == "medium":
            # Flat distribution - Pure randomness
            # Creates a balanced mix of open and closed sums
            domain_weights = [5, 5, 5, 5, 5, 5, 5, 5, 5]
            
        elif difficulty == "hard":
            # Bias towards the middle (4, 5, 6)
            # Creates sums with maximum freedom (e.g., 12, 13, 14, 15)
            # These are the hardest to deduce logically
            domain_weights = [1, 2, 5, 10, 10, 10, 5, 2, 1]
            
        else:
            # Fallback to medium
            domain_weights = [5, 5, 5, 5, 5, 5, 5, 5, 5]
            
        return self._backtrack_fill(assignment, node_count, max_nodes, domain_weights)
    
    def _backtrack_fill(self, assignment: Dict[Cell, int], node_count: List[int], max_nodes: int, weights: List[int]) -> bool:
        if node_count[0] > max_nodes: 
            return False
        node_count[0] += 1

        # MRV Heuristic
        unassigned = [c for c in self.board.white_cells if c not in assignment]
        if not unassigned:
            # Apply assignment to board
            for cell, val in assignment.items():
                cell.value = val
            return True
            
        # Sort by most constrained (approximate by sector neighbors filled)
        var = max(unassigned, key=lambda c: self._count_neighbors_filled(c, assignment))
        
        # Domain selection
        nums = [1, 2, 3, 4, 5, 6, 7, 8, 9]
        # Weighted shuffle based on difficulty
        # python's random.choices returns with replacement, so we use it to sort
        weighted_pairs = list(zip(nums, weights))
        random.shuffle(weighted_pairs)
        # Sort based on weight + random noise
        weighted_pairs.sort(key=lambda x: x[1] * random.random(), reverse=True)
        ordered_domain = [x[0] for x in weighted_pairs]

        for val in ordered_domain:
            if self._is_consistent_number(var, val, assignment):
                assignment[var] = val
                if self._backtrack_fill(assignment, node_count, max_nodes, weights):
                    return True
                del assignment[var]
        
        return False

    def _count_neighbors_filled(self, cell: Cell, assignment: Dict[Cell, int]) -> int:
        count = 0
        if cell.sector_h:
            for n in cell.sector_h:
                if n in assignment: count += 1
        if cell.sector_v:
            for n in cell.sector_v:
                if n in assignment: count += 1
        return count

    def _is_consistent_number(self, var: Cell, value: int, assignment: Dict[Cell, int]) -> bool:
        # Check Row
        if var.sector_h:
            for cell in var.sector_h:
                if cell in assignment and assignment[cell] == value: return False
        # Check Col
        if var.sector_v:
            for cell in var.sector_v:
                if cell in assignment and assignment[cell] == value: return False
        return True

    def calculate_clues(self):
        """Calculates clues based on current filled values."""
        for sector in self.board.sectors_h:
            s_sum = sum(c.value for c in sector if c.value)
            first = sector[0]
            if first.c > 0:
                self.board.grid[first.r][first.c - 1].clue_h = s_sum
        
        for sector in self.board.sectors_v:
            s_sum = sum(c.value for c in sector if c.value)
            first = sector[0]
            if first.r > 0:
                self.board.grid[first.r - 1][first.c].clue_v = s_sum


    def check_uniqueness(self, max_nodes: int = 10000) -> Tuple[bool, Optional[Dict[Tuple[int, int], int]]]:
        """
        Returns (True, None) if unique.
        Returns (False, Alternative_Assignment) if not unique.
        """
        current_solution = { (c.r, c.c): c.value for c in self.board.white_cells }
        
        # Clear board to prepare for solving
        for c in self.board.white_cells:
            c.value = None
            
        found_solutions = []
        self._solve_for_uniqueness(found_solutions, current_solution, [0], max_nodes)
        
        # Restore original solution
        for c in self.board.white_cells:
            c.value = current_solution[(c.r, c.c)]
            
        if not found_solutions:
            # This shouldn't happen if the puzzle was valid, but acts as a fallback
            return True, None 
            
        # found_solutions contains the ALTERNATIVE solution
        return False, found_solutions[0]

    def _solve_for_uniqueness(self, found_solutions: List[Dict], avoid_sol: Dict, node_count: List[int], max_nodes: int):
        if found_solutions: return # Found an alternative, stop
        if node_count[0] > max_nodes: return
        node_count[0] += 1
        
        # Find unassigned
        unassigned = [c for c in self.board.white_cells if c.value is None]
        if not unassigned:
            # Check if this solution is different from the original
            is_diff = False
            current_sol = {}
            for c in self.board.white_cells:
                current_sol[(c.r, c.c)] = c.value
                if avoid_sol[(c.r, c.c)] != c.value:
                    is_diff = True
            
            if is_diff:
                found_solutions.append(current_sol)
            return

        # MRV
        var = min(unassigned, key=lambda c: self._get_domain_size(c))
        
        for val in range(1, 10):
            if self._is_valid_move(var, val):
                var.value = val
                self._solve_for_uniqueness(found_solutions, avoid_sol, node_count, max_nodes)
                if found_solutions: return
                var.value = None

    def _get_domain_size(self, cell: Cell) -> int:
        c = 0
        for v in range(1, 10):
            if self._is_valid_move(cell, v): c += 1
        return c

    def _is_valid_move(self, cell: Cell, val: int) -> bool:
        # 1. Unique in row/col
        # 2. Sum constraint not violated
        
        # Horizontal
        if cell.sector_h:
            curr_sum = val
            filled = 1
            for peer in cell.sector_h:
                if peer.value is not None:
                    if peer.value == val: return False
                    curr_sum += peer.value
                    filled += 1
            
            clue = self.board.grid[cell.sector_h[0].r][cell.sector_h[0].c - 1].clue_h
            if curr_sum > clue: return False
            if filled == len(cell.sector_h) and curr_sum != clue: return False

        # Vertical
        if cell.sector_v:
            curr_sum = val
            filled = 1
            for peer in cell.sector_v:
                if peer.value is not None:
                    if peer.value == val: return False
                    curr_sum += peer.value
                    filled += 1
            
            clue = self.board.grid[cell.sector_v[0].r - 1][cell.sector_v[0].c].clue_v
            if curr_sum > clue: return False
            if filled == len(cell.sector_v) and curr_sum != clue: return False
            
        return True

    def _repair_ambiguity_safely(self, alt_sol: Dict[Tuple[int, int], int]) -> bool:
        """
        Finds difference between current board and alt_sol.
        Tries to place a block to break the ambiguity.
        CRITICAL: Checks if placing the block would disconnect the graph.
        Returns True if successful, False if no safe block could be placed.
        """
        diff_cells = []
        for c in self.board.white_cells:
            if c.value != alt_sol.get((c.r, c.c)):
                diff_cells.append(c)
        
        if not diff_cells: return False

        # Sort candidates to try middle first (usually best for breaking loops)
        # but if that fails, try others.
        diff_cells.sort(key=lambda c: abs(c.r - self.board.height//2) + abs(c.c - self.board.width//2))
        
        # Current set of white coordinates
        white_coords = set((c.r, c.c) for c in self.board.white_cells)
        
        for target in diff_cells:
            # Simulate: What happens if we remove 'target' and its symmetric partner?
            removed = {(target.r, target.c)}
            sym_r, sym_c = self.board.height - 1 - target.r, self.board.width - 1 - target.c
            if (sym_r, sym_c) in white_coords:
                removed.add((sym_r, sym_c))
            
            # Remaining white cells count
            remaining_coords = white_coords - removed
            
            # If we remove too much (shouldn't happen with 1 cell, but good to check)
            if len(remaining_coords) < 0.8 * len(white_coords): 
                continue

            # Connectivity Check on remaining_coords
            if self._is_connected(remaining_coords):
                # SUCCESS: We can block this cell safely
                self.board.set_block(target.r, target.c)
                self.board.set_block(sym_r, sym_c)
                
                # Re-stabilize to fix any run lengths (this might delete a few more cells, 
                # but we know the main graph is connected)
                self.board._stabilize_grid()
                return True

        return False # Could not find any safe cell to block

    def _is_connected(self, coords: Set[Tuple[int, int]]) -> bool:
        if not coords: return False
        start = next(iter(coords))
        q = deque([start])
        visited = {start}
        count = 0
        while q:
            r, c = q.popleft()
            count += 1
            for dr, dc in [(0,1), (0,-1), (1,0), (-1,0)]:
                nr, nc = r+dr, c+dc
                if (nr, nc) in coords and (nr, nc) not in visited:
                    visited.add((nr, nc))
                    q.append((nr, nc))
        return count == len(coords)