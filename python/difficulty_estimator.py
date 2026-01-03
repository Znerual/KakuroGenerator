import itertools
from typing import List, Set, Dict, Tuple
from collections import defaultdict
from python.kakuro import KakuroBoard, Cell, CellType # Adjust import

class KakuroDifficultyEstimator:
    def __init__(self, board: KakuroBoard):
        self.board = board
       
    def estimate_difficulty(self) -> float:
        """
        Simulates a human solving the puzzle logically.
        Returns (Rating, NumericScore).
        
        Score roughly correlates to:
        - < 1.0: Trivial (Unique sums only)
        - 1.0 - 3.0: Very Easy (Single pass constraint propagation)
        - 3.0 - 6.0: Easy/Medium (Multiple passes, interaction between rows/cols)
        - 6.0 - 15.0: Hard (Requires complex chain logic)
        - > 15.0: Very Hard (Requires trial & error / bifurcation)
        """
        
        # 1. Initialize Candidates: Every cell starts with {1..9}
        candidates: Dict[Tuple[int, int], Set[int]] = {}
        for cell in self.board.white_cells:
            candidates[(cell.r, cell.c)] = set(range(1, 10))

        # 2. Logic Loop
        passes = 0
        solved_cells = 0
        total_cells = len(self.board.white_cells)
        
        # We track how much the candidates "shrink" per pass
        while solved_cells < total_cells:
            passes += 1
            changes = False
            
            # --- Technique A: Sum Combinations (Sector Logic) ---
            # For every run (e.g., "Sum 10 in 3 cells"), filter candidates 
            # based on valid permutations.
            for sector in self.board.sectors_h + self.board.sectors_v:
                if self._apply_sum_constraints(sector, candidates):
                    changes = True

            # --- Technique B: Naked Singles ---
            # If a cell has only 1 candidate left, it is "solved".
            # (Implicitly handled by _apply_sum_constraints reducing sets to size 1)
            
            # Check progress
            current_solved = sum(1 for cs in candidates.values() if len(cs) == 1)
            if current_solved > solved_cells:
                # If we solved new cells, we consider this a productive pass
                solved_cells = current_solved
            elif not changes:
                # STUCK!
                # If logic stops making progress but board isn't full, 
                # it means the puzzle requires "Look-Ahead" (Guessing).
                # This drastically increases difficulty score.
                remaining = total_cells - solved_cells
                penalty = remaining * 2.0 # Heavy penalty for unsolved cells
                return float(passes) + penalty

            # Loop safety cap
            if passes > 20:
                return 99.0

        # Calculate final score based on passes needed
        # Base score is the number of logic passes
        score = passes
        
        return score

    def _apply_sum_constraints(self, sector: List[Cell], candidates: Dict[Tuple[int, int], Set[int]]) -> bool:
        """
        Filters candidates for a sector (row or col) based on its Clue Sum.
        Returns True if any candidates were removed.
        """
        # 1. Get Clue
        is_horz = (sector == sector[0].sector_h)
        if is_horz:
            clue = self.board.grid[sector[0].r][sector[0].c - 1].clue_h
        else:
            clue = self.board.grid[sector[0].r - 1][sector[0].c].clue_v
            
        if clue is None: return False

        # 2. Identify fixed values and open variables
        # Some cells in this sector might already be solved (len(candidates)==1)
        
        sector_coords = [(c.r, c.c) for c in sector]
        current_possible_values = [candidates[coord] for coord in sector_coords]
        
        # Optimization: If all cells have {1..9}, total permutations is huge.
        # But we only need to check valid partitions of 'clue' into 'len(sector)' parts.
        
        # 3. Generate Valid Permutations
        # A valid permutation is a list of numbers [n1, n2, n3] such that:
        #   - sum(n) == clue
        #   - all distinct
        #   - n[i] is in current_possible_values[i]
        
        valid_sets = []
        
        # We can optimize this by generating partitions first, then permutations
        # But for Kakuro (max length 9), itertools is okay if constrained early.
        
        # optimization: Pre-filter logic
        # e.g., if Clue is 3 in 2 cells, valid sets are {1,2}. 
        # If one cell only has {2,4,8}, then that cell MUST be 2.
        
        # Generate all valid partitions of sum `clue` with length `len(sector)`
        partitions = self._get_partitions(clue, len(sector))
        
        valid_permutation_exists = False
        
        # We want to find the UNION of allowed values for each slot across all valid permutations
        allowed_values_per_slot = [set() for _ in range(len(sector))]
        
        for p in partitions:
            # p is a set {a, b, c}. We need to see if these numbers can fit into the slots
            # respecting the current candidate restrictions.
            # This is a bipartite matching problem, but simpler: checks permutations.
            for perm in itertools.permutations(p):
                # Check if this permutation fits current candidates
                fits = True
                for i, val in enumerate(perm):
                    if val not in current_possible_values[i]:
                        fits = False
                        break
                
                if fits:
                    valid_permutation_exists = True
                    for i, val in enumerate(perm):
                        allowed_values_per_slot[i].add(val)

        # 4. Prune Candidates
        changed = False
        if valid_permutation_exists:
            for i, coord in enumerate(sector_coords):
                current_set = candidates[coord]
                allowed_set = allowed_values_per_slot[i]
                
                # Intersection
                new_set = current_set.intersection(allowed_set)
                
                if len(new_set) < len(current_set):
                    candidates[coord] = new_set
                    changed = True
                    # If reduced to 0, puzzle is broken (shouldn't happen with valid input)
        
        return changed

    def _get_partitions(self, total: int, count: int) -> List[Tuple[int, ...]]:
        """Returns list of unique tuples summing to total (e.g. 4 in 2 -> [(1,3)])"""
        # This can be cached class-level for performance
        return [
            p for p in itertools.combinations(range(1, 10), count) 
            if sum(p) == total
        ]