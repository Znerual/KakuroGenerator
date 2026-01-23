from collections import deque
from typing import List, Dict, Set, Optional, Tuple
from .kakuro import KakuroBoard, Cell, CellType
from .difficulty_estimator import KakuroDifficultyEstimator
import copy
import random
import logging

logger = logging.getLogger("kakuro_solver")

class CSPSolver:
    def __init__(self, board: KakuroBoard):
        self.board = board

    def generate_random_puzzle(self):
        """
        Generates a puzzle with randomized parameters and returns (Success, DifficultyResult).
        """
        import random
        w = random.randint(8, 18)
        h = random.randint(8, 16)
        self.board.width = w
        self.board.height = h
        self.board._reset_grid()
        self.board.grid = [[Cell(r, c) for c in range(w)] for r in range(h)]
        
        area = (w-2)*(h-2)
        
        density = random.uniform(0.55, 0.68)
        num_stamps = random.randint(8, 22) * area // 100
        
        all_stamps = [
            (1, 3), (3, 1), (2, 2), (1, 4), (4, 1), (2, 3), (3, 2),
            (1, 5), (5, 1), (2, 4), (4, 2), (3, 3), (1, 6), (6, 1),
            (2, 5), (5, 2), (3, 4), (1, 7), (7, 1), (1, 8), (8, 1)
        ]
        random.shuffle(all_stamps)
        n_stamps = random.randint(5, 12)
        stamps = all_stamps[:n_stamps]
        
        topo_params = {
            "density": density,
            "num_stamps": num_stamps,
            "stamps": stamps,
            "island_mode": True,
            "min_cells": int(area * random.uniform(0.18, 0.35)),
            "max_run_length": random.randint(6, 9),
            "max_patch_size": random.randint(2, 4)
        }
        
        pref = random.choice(["", "few", "unique"])
        
        for retry in range(5):
            success = self.board.generate_topology(**topo_params)
            if success:
                self.board._collect_white_cells()
                self.board._identify_sectors()
                
                # Try to fill
                fill_success = False
                for fill_attempt in range(5):
                    self.board.reset_values()
                    if self.solve_fill(partition_preference=pref, ignore_clues=True):
                        self.calculate_clues()
                        is_unique, _ = self.check_uniqueness()
                        if is_unique:
                            estimator = KakuroDifficultyEstimator(self.board)
                            return True, estimator.estimate_difficulty_detailed()
                
            # retry with higher density
            topo_params["density"] = min(0.75, topo_params["density"] + 0.05)
            topo_params["num_stamps"] = int(topo_params["num_stamps"] * 1.2)
            
        return False, None

    def generate_puzzle(self, difficulty: str = "medium") -> bool:
        """
        Main Pipeline:
        1. Generate Topology
        2. Solve Fill (create numbers)
        3. Check Uniqueness
        4. If not unique, fix ambiguous area and repeat.
        """
        MAX_TOPOLOGY_RETRIES = 20
        MAX_REPAIR_ATTEMPTS = 5 # How many times we try to fix a specific topology
        MAX_VALUE_RETRIES = 5   # How many times we try to fill values before giving up
        
        for topo_attempt in range(MAX_TOPOLOGY_RETRIES):
            # 1. Generate Topology
            d = 0.60
            if difficulty == "very_easy": d = 0.50
            elif difficulty == "easy": d = 0.55
            elif difficulty == "hard": d = 0.65
                
            self.board.generate_topology(density=d, difficulty=difficulty)
            
            # Safety check: Is board empty?
            if len(self.board.white_cells) < 12:
                logger.info(f"Topology led to empty board on attempt {topo_attempt}")
                continue

            # ---------------------------------------------------
            # STEP 2: Try to find a Unique Fill (Value Logic)
            # ---------------------------------------------------
            self.board._collect_white_cells()
            self.board._identify_sectors()
            
            repair_count = 0
            while repair_count < MAX_REPAIR_ATTEMPTS:
                # 2. Try to Fill Values
                # We try a few times with different seeds because sometimes 
                # a topology is valid but a specific random path gets stuck.
                fill_success = False
                last_ambiguity = None
                previous_solution_state = {} 
                
                for fill_attempt in range(MAX_VALUE_RETRIES):
                    constraints = {}
                    if fill_attempt > 1 and last_ambiguity:
                        constraints = self._generate_breaking_constraints(last_ambiguity)

                    self.board.reset_values()

                    success = self.solve_fill(difficulty=difficulty, initial_constraints=constraints, ignore_clues=True)
                    
                    if not success:
                        continue # Try next fill attempt

                    # Store this solution state for comparison / constraint generation
                    previous_solution_state = {(c.r, c.c): c.value for c in self.board.white_cells}
                    
                    # Calculate Clues based on this fill
                    self.calculate_clues()
                    
                    # Check Uniqueness using the clues
                    is_unique, alt_sol = self.check_uniqueness(random_seed=fill_attempt)
                    
                    if is_unique:
                        if self.check_uniqueness(random_seed=fill_attempt + 100)[0]:
                            logger.info(f"Success! Unique puzzle generated (Topo {topo_attempt}, Fill {fill_attempt})")
                          
                            return True
                    
                    last_ambiguity = alt_sol
                    
                if not fill_success:
                    # If we can't fill this topology (e.g. impossible geometry), 
                    # break inner loop and generate a NEW topology.
                    logger.debug(f"Topo {topo_attempt}: Could not fill values. Discarding.")
                    break 
                    
                # 3. Calculate Clues based on the fill
                self.calculate_clues()
                
                # Check Uniqueness
                is_unique, alt_sol = self.check_uniqueness(random_seed=fill_attempt)
                    
                if is_unique:
                    # Double check
                    is_unique_2, _ = self.check_uniqueness(random_seed=fill_attempt + 100)
                    if is_unique_2:
                        logger.info(f"Success! Unique puzzle generated (Topo {topo_attempt}, Fill {fill_attempt})")
                       
                        return True
                    
                # Not unique - record the ambiguity for the next 'Targeted Fill' attempt
                last_ambiguity = alt_sol
                logger.debug(f"Topo {topo_attempt} Fill {fill_attempt}: Not unique. Retrying values...")


                    
                # ---------------------------------------------------
                # STEP 3: Topology Repair (Last Resort)
                # ---------------------------------------------------
                # If we are here, we tried 10 different number combinations and ALL were ambiguous.
                # This implies the geometry itself is flawed (e.g., a symmetric loop).
                # Now we try to block a cell.
                
                logger.info(f"Values failed for Topo {topo_attempt}. Attempting topology repair...")
                
                if self._repair_topology_robust(last_ambiguity):
                    # SUCCESSFUL REPAIR
                    # The grid changed. The sectors changed.
                    self.board._collect_white_cells()  
                    self.board._identify_sectors()
                    
                    # CRITICAL: DO NOT return True yet.
                    # The current values are now garbage (sums are wrong for new blocks).
                    # We must LOOP BACK to the top of 'while' to RE-FILL the board.
                    repair_count += 1
                    continue 
                else:
                    # Repair failed (could not block without breaking connectivity).
                    # Break inner loop to try a fresh topology.
                    break
                
            
        return False

    def _repair_topology_robust(self, alt_sol: Dict[Tuple[int, int], int]) -> bool:
        """
        Surgically alters the board to resolve ambiguity.
        Returns True if a valid modification was made.
        """
        # 1. Identify differences
        diff_cells = []
        for c in self.board.white_cells:
            if c.value is not None and alt_sol.get((c.r, c.c)) != c.value:
                diff_cells.append(c)
        
        if not diff_cells: return False

        # 2. Sort by Connectivity Safety
        # Remove "Hubs" first (3-4 neighbors), check "Bridges" (1-2 neighbors) last.
        # This increases the chance that the graph stays connected.
        random.shuffle(diff_cells) # Add randomness so we don't always pick top-left
        diff_cells.sort(key=lambda c: self._count_white_neighbors(c), reverse=True)

        # Snapshot grid types for rollback
        original_types = [row[:] for row in [[c.type for c in r] for r in self.board.grid]]
        
        for target in diff_cells:
            # Transaction Start
            
            # 3. Apply Block + Symmetry
            targets = {(target.r, target.c)}
            sym_r, sym_c = self.board.height - 1 - target.r, self.board.width - 1 - target.c
            targets.add((sym_r, sym_c))
            
            for r, c in targets:
                self.board.set_block(r, c)
                
            # 4. CASCADE PRUNING
            # If blocking a cell creates a 1-length run neighbor, block that too.
            # This recursively cleans up the board.
            self.board._prune_singles()
            
            # 5. Validation
            valid = True
            
            # A. Check Size
            self.board._collect_white_cells()
            if len(self.board.white_cells) < 12:
                valid = False
                
            # B. Check Connectivity
            if valid and not self.board._check_connectivity():
                valid = False
                
            # C. Check Headers (Headless runs)
            if valid and not self.board._validate_clue_headers():
                valid = False

            if valid:
                return True # Commit Transaction
            
            # Rollback Transaction
            for r in range(self.board.height):
                for c in range(self.board.width):
                    self.board.grid[r][c].type = original_types[r][c]
            self.board._collect_white_cells()
            
        return False

    def solve_fill(self, difficulty: str = "medium", 
               max_nodes: int = 50000, 
               initial_constraints: Dict[Tuple[int, int], int] = None,
               ignore_clues: bool = False) -> bool:
        """Backtracking to fill the grid with valid numbers 1-9."""
        assignment = {}
        node_count = [0]

        # Apply initial constraints
        if initial_constraints:
            for (r, c), val in initial_constraints.items():
                cell = self.board.grid[r][c]
                if cell.type == CellType.WHITE:
                    # Verify consistency before assigning
                    if self._is_consistent_number(cell, val, assignment, ignore_clues):
                        assignment[cell] = val
                    else:
                        # Constraints were impossible
                        return False
        
        # Difficulty settings
        if difficulty == "very_easy":
            domain_weights = [20, 15, 5, 1, 1, 1, 5, 15, 20]
            partition_preference = "unique"  # NEW: Prefer unique partitions
            
        elif difficulty == "easy":
            domain_weights = [10, 8, 6, 2, 1, 2, 6, 8, 10]
            partition_preference = "few"  # NEW: Prefer few partitions (1-3)
            
        elif difficulty == "medium":
            domain_weights = [5, 5, 5, 5, 5, 5, 5, 5, 5]
            partition_preference = None  # No preference
            
        elif difficulty == "hard":
            domain_weights = [1, 2, 5, 10, 10, 10, 5, 2, 1]
            partition_preference = None
            
        else:
            domain_weights = [5, 5, 5, 5, 5, 5, 5, 5, 5]
            partition_preference = None
            
        return self._backtrack_fill(assignment, node_count, max_nodes, domain_weights, 
                                ignore_clues, partition_preference)


    
    def _backtrack_fill(self, assignment: Dict[Cell, int], node_count: List[int], 
                   max_nodes: int, weights: List[int], ignore_clues: bool = False,
                   partition_preference: str = None) -> bool:
        if node_count[0] > max_nodes: 
            return False
        node_count[0] += 1

        # MRV Heuristic
        unassigned = [c for c in self.board.white_cells if c not in assignment]
        if not unassigned:
            # FINAL VALIDATION for easy puzzles: Check if clues are actually easy
            if partition_preference and not ignore_clues:
                if not self._validate_partition_difficulty(assignment, partition_preference):
                    return False  # Reject this solution, backtrack
            
            # Apply assignment to board
            for cell, val in assignment.items():
                cell.value = val
            return True
            
        var = max(unassigned, key=lambda c: self._count_neighbors_filled(c, assignment))
        
        if partition_preference:
            ordered_domain = self._get_partition_aware_domain(var, assignment, partition_preference, weights)
        else:
            # Original approach
            nums = [1, 2, 3, 4, 5, 6, 7, 8, 9]
            weighted_pairs = list(zip(nums, weights))
            random.shuffle(weighted_pairs)
            weighted_pairs.sort(key=lambda x: x[1] * random.random(), reverse=True)
            ordered_domain = [x[0] for x in weighted_pairs]

        for val in ordered_domain:
            if self._is_consistent_number(var, val, assignment, ignore_clues):
                assignment[var] = val
                if self._backtrack_fill(assignment, node_count, max_nodes, weights, 
                                   ignore_clues, partition_preference):
                    return True
                del assignment[var]
        
        return False

    def _validate_partition_difficulty(self, assignment: Dict[Cell, int], 
                                    preference: str) -> bool:
        """
        Check if the filled puzzle has appropriate partition difficulty.
        For 'unique': At least 80% of clues should have <=2 partitions
        For 'few': At least 60% of clues should have <=4 partitions
        """
        easy_clue_count = 0
        total_clue_count = 0
        
        # Check horizontal sectors
        for sector in self.board.sectors_h:
            if not all(c in assignment for c in sector):
                continue
            total_clue_count += 1
            clue_sum = sum(assignment[c] for c in sector)
            num_partitions = self._count_partitions(clue_sum, len(sector))
            
            if preference == "unique" and num_partitions <= 2:
                easy_clue_count += 1
            elif preference == "few" and num_partitions <= 4:
                easy_clue_count += 1
        
        # Check vertical sectors
        for sector in self.board.sectors_v:
            if not all(c in assignment for c in sector):
                continue
            total_clue_count += 1
            clue_sum = sum(assignment[c] for c in sector)
            num_partitions = self._count_partitions(clue_sum, len(sector))
            
            if preference == "unique" and num_partitions <= 2:
                easy_clue_count += 1
            elif preference == "few" and num_partitions <= 4:
                easy_clue_count += 1
        
        if total_clue_count == 0:
            return True
        
        ratio = easy_clue_count / total_clue_count
        
        if preference == "unique":
            return ratio >= 0.80  # At least 60% easy clues
        elif preference == "few":
            return ratio >= 0.60  # At least 40% easy clues
        
        return True

    def _get_partition_aware_domain(self, cell: Cell, assignment: Dict[Cell, int], 
                                    preference: str, weights: List[int]) -> List[int]:
        """
        Returns an ordered domain that prefers values leading to easy partitions.
        
        Strategy:
        1. For each candidate value, calculate what the FINAL sum would be if we chose it
        2. Count partitions for that final sum
        3. Prioritize values that lead to sums with fewer partitions
        """
        candidates = []
        
        for val in range(1, 10):
            # Quick duplicate check
            if cell.sector_h:
                if any(assignment.get(c) == val for c in cell.sector_h):
                    continue
            if cell.sector_v:
                if any(assignment.get(c) == val for c in cell.sector_v):
                    continue
            
            # Calculate partition scores for both directions
            h_score = self._calculate_partition_score(cell, val, assignment, 'h', preference)
            v_score = self._calculate_partition_score(cell, val, assignment, 'v', preference)
            
            # Combined score: lower is better (fewer partitions = easier)
            # Weight by original difficulty weights too
            difficulty_weight = weights[val - 1]
            combined_score = (h_score + v_score) * (10.0 / max(difficulty_weight, 1))
            
            candidates.append((val, combined_score))
        
        # Sort by score (lower = better), with some randomness
        candidates.sort(key=lambda x: x[1] + random.random() * 2)
        
        return [val for val, _ in candidates]


    def _calculate_partition_score(self, cell: Cell, value: int, assignment: Dict[Cell, int],
                                direction: str, preference: str) -> float:
        """
        Calculate how "easy" this value would make the clue.
        Returns a score where LOWER is better (fewer partitions).
        """
        sector = cell.sector_h if direction == 'h' else cell.sector_v
        if not sector:
            return 0.0  # No constraint
        
        # Calculate current state of this sector
        current_sum = value
        filled_count = 1
        remaining_cells = []
        
        for c in sector:
            if c in assignment:
                current_sum += assignment[c]
                filled_count += 1
            elif c != cell:
                remaining_cells.append(c)
        
        sector_length = len(sector)
        
        # If this completes the sector, count actual partitions
        if filled_count == sector_length:
            num_partitions = self._count_partitions(current_sum, sector_length)
            
            if preference == "unique":
                # Strongly prefer 1-2 partitions, heavily penalize >3
                if num_partitions == 1:
                    return 0.0  # Perfect!
                elif num_partitions == 2:
                    return 1.0
                elif num_partitions <= 4:
                    return 5.0
                else:
                    return 20.0  # Very bad
                    
            elif preference == "few":
                # Prefer 1-4 partitions, penalize >6
                if num_partitions <= 2:
                    return 0.0
                elif num_partitions <= 4:
                    return 2.0
                elif num_partitions <= 6:
                    return 5.0
                else:
                    return 15.0
        
        else:
            # Sector not complete yet - estimate difficulty
            # Calculate what range of sums are possible
            remaining_count = len(remaining_cells)
            
            # Minimum possible final sum (use smallest available digits)
            used_digits = {assignment[c] for c in sector if c in assignment}
            used_digits.add(value)
            available = [d for d in range(1, 10) if d not in used_digits]
            
            if len(available) < remaining_count:
                return 100.0  # Impossible - will be pruned by consistency check
            
            min_remaining = sum(available[:remaining_count])
            max_remaining = sum(available[-remaining_count:]) if available else 0
            
            min_final_sum = current_sum + min_remaining
            max_final_sum = current_sum + max_remaining
            
            # Estimate average partition count in this range
            # For efficiency, sample a few sums in the range
            sample_sums = []
            if min_final_sum == max_final_sum:
                sample_sums = [min_final_sum]
            else:
                step = max(1, (max_final_sum - min_final_sum) // 3)
                sample_sums = list(range(min_final_sum, max_final_sum + 1, step))
            
            partition_counts = [self._count_partitions(s, sector_length) for s in sample_sums]
            avg_partitions = sum(partition_counts) / len(partition_counts) if partition_counts else 10
            
            # Return a "potential difficulty" score
            if preference == "unique":
                if avg_partitions <= 2:
                    return 1.0
                elif avg_partitions <= 4:
                    return 3.0
                else:
                    return 8.0
                    
            elif preference == "few":
                if avg_partitions <= 4:
                    return 1.0
                elif avg_partitions <= 6:
                    return 3.0
                else:
                    return 6.0
        
        return 5.0  # Default neutral score


    def _count_partitions(self, target_sum: int, length: int, cache: dict = None) -> int:
        """
        Count how many ways we can partition target_sum into 'length' distinct digits (1-9).
        Uses memoization for speed.
        """
        if cache is None:
            if not hasattr(self, '_partition_cache'):
                self._partition_cache = {}
            cache = self._partition_cache
        
        key = (target_sum, length)
        if key in cache:
            return cache[key]
        
        result = self._count_partitions_recursive(target_sum, length, 1, set())
        cache[key] = result
        return result



    def _count_partitions_recursive(self, remaining_sum: int, remaining_length: int, 
                                    min_digit: int, used: Set[int]) -> int:
        """Helper for counting partitions using backtracking with pruning."""
        if remaining_length == 0:
            return 1 if remaining_sum == 0 else 0
        
        if remaining_sum <= 0 or min_digit > 9:
            return 0
        
        # Quick feasibility check
        available = [d for d in range(min_digit, 10) if d not in used]
        if len(available) < remaining_length:
            return 0
        
        min_possible = sum(available[:remaining_length])
        max_possible = sum(available[-remaining_length:])
        
        if remaining_sum < min_possible or remaining_sum > max_possible:
            return 0
        
        count = 0
        for digit in available:
            used.add(digit)
            count += self._count_partitions_recursive(remaining_sum - digit, 
                                                    remaining_length - 1, 
                                                    digit + 1, used)
            used.remove(digit)
        
        return count


    def _generate_breaking_constraints(self, alt_sol: Dict[Tuple[int, int], int]) -> Dict[Tuple[int, int], int]:
        """
        Smart Value Repair:
        Compare current board values (Main Sol) vs Alt Sol.
        Pick a cell where they differ.
        Force that cell to be a THIRD value (randomly).
        
        This forces the solver to explore a completely different branch of the solution tree.
        """
        diffs = []
        for c in self.board.white_cells:
            if c.value is not None:
                if alt_sol.get((c.r, c.c)) != c.value:
                    diffs.append(c)
        
        if not diffs: return {}
        
        # Pick one difference to act as the pivot
        target = random.choice(diffs)
        
        val_a = target.value
        val_b = alt_sol.get((target.r, target.c))
        
        # Pick a value that is NEITHER A nor B
        domain = list(range(1, 10))
        if val_a in domain: domain.remove(val_a)
        if val_b in domain: domain.remove(val_b)
        
        if not domain: return {} # Should verify against neighbors, but let solver handle it
        
        new_val = random.choice(domain)
        
        # Return as constraint
        return {(target.r, target.c): new_val}

    def _count_white_neighbors(self, cell: Cell) -> int:
        n = 0
        for dr, dc in [(0,1), (0,-1), (1,0), (-1,0)]:
            nr, nc = cell.r + dr, cell.c + dc
            if self.board.get_cell(nr, nc) and self.board.get_cell(nr, nc).type == CellType.WHITE:
                n += 1
        return n

    def _count_neighbors_filled(self, cell: Cell, assignment: Dict[Cell, int]) -> int:
        count = 0
        if cell.sector_h:
            for n in cell.sector_h:
                if n in assignment: count += 1
        if cell.sector_v:
            for n in cell.sector_v:
                if n in assignment: count += 1
        return count

    def _is_consistent_number(self, var: Cell, value: int, assignment: Dict[Cell, int], ignore_clues: bool = False) -> bool:
        """
        Checks validity.
        If ignore_clues is True, ONLY checks for duplicate numbers in row/col.
        If ignore_clues is False, checks Sums match Clues.
        """
        # --- HORIZONTAL CHECK ---
        if var.sector_h:
            curr_sum = value
            filled_count = 1
            for cell in var.sector_h:
                if cell in assignment:
                    v = assignment[cell]
                    if v == value: return False # Duplicate check (ALWAYS ON)
                    curr_sum += v
                    filled_count += 1
            
            # Sum check (ONLY if not ignoring clues)
            if not ignore_clues:
                clue_cell = self.board.grid[var.sector_h[0].r][var.sector_h[0].c - 1]
                if clue_cell.clue_h is None: return False # Should not happen in solver mode
                
                if curr_sum > clue_cell.clue_h: return False
                if filled_count == len(var.sector_h) and curr_sum != clue_cell.clue_h: return False

        # --- VERTICAL CHECK ---
        if var.sector_v:
            curr_sum = value
            filled_count = 1
            for cell in var.sector_v:
                if cell in assignment:
                    v = assignment[cell]
                    if v == value: return False # Duplicate check
                    curr_sum += v
                    filled_count += 1
            
            if not ignore_clues:
                clue_cell = self.board.grid[var.sector_v[0].r - 1][var.sector_v[0].c]
                if clue_cell.clue_v is None: return False

                if curr_sum > clue_cell.clue_v: return False
                if filled_count == len(var.sector_v) and curr_sum != clue_cell.clue_v: return False
        
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


    def check_uniqueness(self, max_nodes: int = 10000, random_seed: int = 0) -> Tuple[bool, Optional[Dict[Tuple[int, int], int]]]:
        """
        Returns (True, None) if unique.
        Returns (False, Alternative_Assignment) if not unique.
        """
        current_solution = { (c.r, c.c): c.value for c in self.board.white_cells }
        
        # Clear board to prepare for solving
        for c in self.board.white_cells:
            c.value = None
            
        found_solutions = []
        self._solve_for_uniqueness(found_solutions, current_solution, [0], max_nodes, random_seed)
        
        # Restore original solution
        for c in self.board.white_cells:
            c.value = current_solution[(c.r, c.c)]
            
        if not found_solutions:
            # This shouldn't happen if the puzzle was valid, but acts as a fallback
            return True, None 
            
        # found_solutions contains the ALTERNATIVE solution
        return False, found_solutions[0]

    def _solve_for_uniqueness(self, found_solutions: List[Dict], avoid_sol: Dict, node_count: List[int], max_nodes: int, random_seed: int):
        if found_solutions or node_count[0] > max_nodes: return
        node_count[0] += 1
        unassigned = [c for c in self.board.white_cells if c.value is None]
        if not unassigned:
            for c in self.board.white_cells:
                if avoid_sol.get((c.r, c.c)) != c.value:
                    found_solutions.append({(cell.r, cell.c): cell.value for cell in self.board.white_cells})
                    return
            return
        
        # Helper to get domain size respecting CLUES
        def get_d_size(c):
            cnt = 0
            for v in range(1, 10):
                if self._is_consistent_number(c, v, {x: x.value for x in self.board.white_cells if x.value}, ignore_clues=False): cnt += 1
            return cnt

        var = min(unassigned, key=lambda c: get_d_size(c))
        values = list(range(1, 10))
        random.Random(random_seed + node_count[0]).shuffle(values)
        
        # Current partial assignment for validation
        current_assign = {x: x.value for x in self.board.white_cells if x.value is not None}
        
        for val in values:
            if self._is_consistent_number(var, val, current_assign, ignore_clues=False):
                var.value = val
                self._solve_for_uniqueness(found_solutions, avoid_sol, node_count, max_nodes, random_seed)
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