import itertools
import copy
from typing import List, Set, Dict, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass

from .kakuro import KakuroBoard, Cell, CellType

@dataclass
class SolveStep:
    """Records a single logical deduction"""
    technique: str
    difficulty_weight: float
    cells_affected: int

class KakuroDifficultyEstimator:
    # Technique difficulty weights
    WEIGHTS = {
        'unique_intersection': 0.5,      # Two clues intersect → unique value
        'simple_partition': 1.0,          # Only one partition possible
        'elimination_singles': 2.0,       # Narrow to 1 by elimination
        'hidden_singles': 3.0,            # Value must go in specific cell
        'constraint_propagation': 4.0,    # Multiple passes needed
        'complex_intersection': 6.0,      # 3+ clues interact
        'trial_and_error': 20.0,          # Guessing required
        'deep_bifurcation': 50.0          # Multiple guess levels
    }
    
    def __init__(self, board):
        self.board = board
        self.solve_log: List[SolveStep] = []
        self._partition_cache = {}
        self.found_solutions: List[Dict[Tuple[int, int], int]] = []
        
    def estimate_difficulty(self) -> Dict:
        """
        Returns detailed difficulty analysis and checks for uniqueness.
        """
        self.solve_log = []
        self.found_solutions = []
        
        # 1. Initialize
        initial_candidates = self._initialize_candidates()
        
        # 2. Estimate Difficulty (Logic Pass)
        # We work on a copy to record steps without affecting uniqueness search
        logic_candidates = copy.deepcopy(initial_candidates)
        self._run_solve_loop(logic_candidates, silent=False)
        
        # 3. Check Uniqueness (Exhaustive Search)
        # We look for up to 3 solutions to report non-uniqueness clearly
        search_candidates = copy.deepcopy(initial_candidates)
        self._discover_all_solutions(search_candidates, limit=3)
        
        return self._compile_results()

    def _run_solve_loop(self, candidates: Dict, silent: bool):
        """Main logical solving engine."""
        iteration = 0
        max_iterations = 50
        
        while not self._is_solved(candidates) and iteration < max_iterations:
            iteration += 1
            progress = False
            
            if self._find_unique_intersections(candidates, silent): progress = True
            if self._apply_simple_partitions(candidates, silent): progress = True
            if self._apply_constraint_propagation(candidates, silent): progress = True
            if self._find_naked_singles(candidates, silent): progress = True
            if self._find_hidden_singles(candidates, silent): progress = True
            
            # Complex techniques only used if basic ones fail
            if iteration > 3 and not progress:
                if self._analyze_complex_intersections(candidates, silent): 
                    progress = True
            
            if not progress:
                # If human logic is stuck, we need trial and error
                remaining = sum(1 for cs in candidates.values() if len(cs) > 1)
                if remaining > 0 and not silent:
                    self.solve_log.append(SolveStep('trial_and_error', self.WEIGHTS['trial_and_error'], remaining))
                    # Try to advance one step with bifurcation
                    if not self._try_bifurcation(candidates):
                        self.solve_log.append(SolveStep('deep_bifurcation', self.WEIGHTS['deep_bifurcation'], remaining))
                break

    def _discover_all_solutions(self, candidates: Dict, limit: int):
        """Pure recursive backtracking to find all solutions."""
        if len(self.found_solutions) >= limit:
            return

        # Lightweight logic to prune the search tree
        self._apply_constraint_propagation(candidates, silent=True)
        
        # Check for contradictions
        if any(len(cands) == 0 for cands in candidates.values()):
            return

        # Check if solved
        if all(len(cands) == 1 for cands in candidates.values()):
            sol = {coord: list(vals)[0] for coord, vals in candidates.items()}
            if sol not in self.found_solutions and self._verify_math(sol):
                self.found_solutions.append(sol)
            return

        # Pick cell with fewest candidates
        unsolved = [c for c, v in candidates.items() if len(v) > 1]
        if not unsolved: return
        target = min(unsolved, key=lambda c: len(candidates[c]))
        
        for val in sorted(list(candidates[target])):
            branch = copy.deepcopy(candidates)
            branch[target] = {val}
            self._discover_all_solutions(branch, limit)
            if len(self.found_solutions) >= limit:
                break

    def _verify_math(self, sol: Dict) -> bool:
        """Final sanity check that the solution respects all Kakuro rules."""
        for sector in self.board.sectors_h + self.board.sectors_v:
            clue = self._get_sector_clue(sector, sector in self.board.sectors_h)
            if clue is None: continue
            vals = [sol[(c.r, c.c)] for c in sector]
            if sum(vals) != clue or len(set(vals)) != len(vals):
                return False
        return True

    # --- Logical Techniques ---

    def _find_unique_intersections(self, candidates: Dict, silent: bool) -> bool:
        changed = False
        cells_solved = 0
        for cell in self.board.white_cells:
            coord = (cell.r, cell.c)
            if len(candidates[coord]) == 1: continue
            
            row_p = self._get_partitions_for_sector(cell.sector_h, True)
            col_p = self._get_partitions_for_sector(cell.sector_v, False)
            if not row_p or not col_p: continue
            
            row_vals = set().union(*row_p)
            col_vals = set().union(*col_p)
            intersect = row_vals & col_vals & candidates[coord]
            
            if 0 < len(intersect) < len(candidates[coord]):
                candidates[coord] = intersect
                if len(intersect) == 1: cells_solved += 1
                changed = True
        
        if cells_solved > 0 and not silent:
            self.solve_log.append(SolveStep('unique_intersection', self.WEIGHTS['unique_intersection'], cells_solved))
        return changed

    def _apply_simple_partitions(self, candidates: Dict, silent: bool) -> bool:
        changed = False
        cells_affected = 0
        for sector in self.board.sectors_h + self.board.sectors_v:
            partitions = self._get_partitions_for_sector(sector, sector in self.board.sectors_h)
            if partitions and len(partitions) == 1:
                p_set = set(partitions[0])
                for cell in sector:
                    coord = (cell.r, cell.c)
                    if not candidates[coord].issubset(p_set):
                        candidates[coord] &= p_set
                        cells_affected += 1
                        changed = True
        if cells_affected > 0 and not silent:
            self.solve_log.append(SolveStep('simple_partition', self.WEIGHTS['simple_partition'], cells_affected))
        return changed

    def _apply_constraint_propagation(self, candidates: Dict, silent: bool) -> bool:
        changed = False
        cells_affected = 0
        for sector in self.board.sectors_h + self.board.sectors_v:
            if self._apply_sector_constraints(sector, candidates):
                cells_affected += len(sector)
                changed = True
        if cells_affected > 0 and not silent:
            self.solve_log.append(SolveStep('constraint_propagation', self.WEIGHTS['constraint_propagation'], cells_affected))
        return changed

    def _apply_sector_constraints(self, sector: List, candidates: Dict) -> bool:
        is_horz = (sector in self.board.sectors_h)
        clue = self._get_sector_clue(sector, is_horz)
        if clue is None: return False
        
        coords = [(c.r, c.c) for c in sector]
        current_domains = [candidates[coord] for coord in coords]
        partitions = self._get_partitions(clue, len(sector))
        
        allowed_per_slot = [set() for _ in range(len(sector))]
        found_any = False
        
        for p in partitions:
            # Check if this partition is even theoretically possible with current candidates
            if all(any(v in domain for v in p) for domain in current_domains):
                for perm in itertools.permutations(p):
                    if all(perm[i] in current_domains[i] for i in range(len(sector))):
                        found_any = True
                        for i, val in enumerate(perm):
                            allowed_per_slot[i].add(val)
        
        changed = False
        if found_any:
            for i, coord in enumerate(coords):
                new_set = candidates[coord] & allowed_per_slot[i]
                if len(new_set) < len(candidates[coord]):
                    candidates[coord] = new_set
                    changed = True
        return changed

    def _find_naked_singles(self, candidates: Dict, silent: bool) -> bool:
        changed = False
        count = 0
        # Check for cells newly solved to 1 candidate
        for cands in candidates.values():
            if len(cands) == 1:
                # Progress is usually flagged by the tech that caused the single
                pass
        return False

    def _find_hidden_singles(self, candidates: Dict, silent: bool) -> bool:
        changed = False
        cells_affected = 0
        for sector in self.board.sectors_h + self.board.sectors_v:
            coords = [(c.r, c.c) for c in sector]
            for val in range(1, 10):
                possible_positions = [c for c in coords if val in candidates[c]]
                if len(possible_positions) == 1:
                    target = possible_positions[0]
                    if len(candidates[target]) > 1:
                        candidates[target] = {val}
                        cells_affected += 1
                        changed = True
        if cells_affected > 0 and not silent:
            self.solve_log.append(SolveStep('hidden_singles', self.WEIGHTS['hidden_singles'], cells_affected))
        return changed

    # --- Complex Strategies (Strategies 1, 2, 3) ---

    def _analyze_complex_intersections(self, candidates: Dict, silent: bool) -> bool:
        changed = False
        cells_affected = 0
        
        # 1. Graph and Propagation Test
        highly_constrained = self._find_highly_constrained_sectors(candidates)
        if highly_constrained:
            critical_cells = self._find_critical_intersection_cells(highly_constrained, candidates)
            for coord in critical_cells:
                if len(candidates[coord]) <= 1: continue
                valid_values = set()
                for test_val in candidates[coord]:
                    if self._test_value_propagation(coord, test_val, candidates):
                        valid_values.add(test_val)
                
                if valid_values and len(valid_values) < len(candidates[coord]):
                    candidates[coord] = valid_values
                    cells_affected += 1
                    changed = True
        
        # 2. Sector Pair Analysis
        if self._analyze_sector_pairs(candidates):
            cells_affected += 1
            changed = True
        
        if cells_affected > 0 and not silent:
            self.solve_log.append(SolveStep('complex_intersection', self.WEIGHTS['complex_intersection'], cells_affected))
        return changed

    def _build_intersection_graph(self, candidates: Dict) -> Dict:
        graph = defaultdict(set)
        for sector in self.board.sectors_h + self.board.sectors_v:
            coords = [(c.r, c.c) for c in sector]
            for i, c1 in enumerate(coords):
                for c2 in coords[i+1:]:
                    graph[c1].add(c2)
                    graph[c2].add(c1)
        return graph

    def _find_highly_constrained_sectors(self, candidates: Dict) -> List:
        constrained = []
        for sector in self.board.sectors_h + self.board.sectors_v:
            clue = self._get_sector_clue(sector, sector in self.board.sectors_h)
            if clue is None: continue
            
            perms_count = 0
            possible_domains = [candidates[(c.r, c.c)] for c in sector]
            for p in self._get_partitions(clue, len(sector)):
                for perm in itertools.permutations(p):
                    if all(perm[i] in possible_domains[i] for i in range(len(sector))):
                        perms_count += 1
                        if perms_count > 10: break
                if perms_count > 10: break
            
            if 1 <= perms_count <= 10:
                constrained.append(sector)
        return constrained

    def _find_critical_intersection_cells(self, sectors, candidates) -> Set:
        counts = defaultdict(int)
        for s in sectors:
            for cell in s:
                if len(candidates[(cell.r, cell.c)]) > 1:
                    counts[(cell.r, cell.c)] += 1
        return {coord for coord, count in counts.items() if count >= 2}

    def _test_value_propagation(self, coord, val, candidates) -> bool:
        # Lightweight look-ahead
        test_c = {k: v.copy() for k, v in candidates.items()}
        test_c[coord] = {val}
        # Try a few logic passes
        for _ in range(2):
            self._apply_sector_constraints(next(c.sector_h for c in self.board.white_cells if (c.r, c.c) == coord), test_c)
            self._apply_sector_constraints(next(c.sector_v for c in self.board.white_cells if (c.r, c.c) == coord), test_c)
            if any(len(v) == 0 for v in test_c.values()): return False
        return True

    def _analyze_sector_pairs(self, candidates: Dict) -> bool:
        changed = False
        for s1 in self.board.sectors_h:
            for s2 in self.board.sectors_v:
                coords1 = {(c.r, c.c) for c in s1}
                coords2 = {(c.r, c.c) for c in s2}
                intersect = coords1 & coords2
                if len(intersect) == 1:
                    coord = next(iter(intersect))
                    clue1 = self._get_sector_clue(s1, True)
                    clue2 = self._get_sector_clue(s2, False)
                    if clue1 and clue2:
                        v1 = {assign[list(coords1).index(coord)] for assign in self._get_valid_sector_assignments(s1, clue1, candidates)}
                        v2 = {assign[list(coords2).index(coord)] for assign in self._get_valid_sector_assignments(s2, clue2, candidates)}
                        final = v1 & v2
                        if 0 < len(final) < len(candidates[coord]):
                            candidates[coord] &= final
                            changed = True
        return changed

    def _get_valid_sector_assignments(self, sector, clue, candidates):
        coords = [(c.r, c.c) for c in sector]
        domains = [candidates[c] for c in coords]
        valid = []
        for p in self._get_partitions(clue, len(sector)):
            for perm in itertools.permutations(p):
                if all(perm[i] in domains[i] for i in range(len(sector))):
                    valid.append(perm)
        return valid

    # --- Helpers ---

    def _try_bifurcation(self, candidates: Dict) -> bool:
        unsolved = [c for c, v in candidates.items() if len(v) > 1]
        if not unsolved: return True
        target = min(unsolved, key=lambda c: len(candidates[c]))
        for val in sorted(list(candidates[target])):
            test_c = copy.deepcopy(candidates)
            test_c[target] = {val}
            self._run_solve_loop(test_c, silent=True)
            if self._is_solved(test_c):
                candidates.update(test_c)
                return True
        return False

    def _get_sector_clue(self, sector: List, is_horz: bool) -> Optional[int]:
        if not sector: return None
        first = sector[0]
        # Defensively find clue cell based on orientation
        r, c = (first.r, first.c - 1) if is_horz else (first.r - 1, first.c)
        if 0 <= r < len(self.board.grid) and 0 <= c < len(self.board.grid[0]):
            clue_cell = self.board.grid[r][c]
            return getattr(clue_cell, 'clue_h' if is_horz else 'clue_v', None)
        return None

    def _get_partitions(self, total: int, count: int) -> List[Tuple[int, ...]]:
        key = (total, count)
        if key not in self._partition_cache:
            self._partition_cache[key] = [p for p in itertools.combinations(range(1, 10), count) if sum(p) == total]
        return self._partition_cache[key]

    def _get_partitions_for_sector(self, sector, is_horz):
        clue = self._get_sector_clue(sector, is_horz)
        return self._get_partitions(clue, len(sector)) if clue else None

    def _initialize_candidates(self) -> Dict:
        return {(c.r, c.c): set(range(1, 10)) for c in self.board.white_cells}

    def _is_solved(self, candidates: Dict) -> bool:
        return all(len(cs) == 1 for cs in candidates.values())

    def _compile_results(self) -> Dict:
        score = sum(step.difficulty_weight for step in self.solve_log)
        techniques = defaultdict(int)
        for step in self.solve_log: techniques[step.technique] += 1
        
        rating = "Trivial"
        if score > 100: rating = "Expert"
        elif score > 60: rating = "Very Hard"
        elif score > 30: rating = "Hard"
        elif score > 15: rating = "Medium"
        elif score > 5: rating = "Easy"

        return {
            'score': score,
            'rating': rating,
            'techniques_used': dict(techniques),
            'solve_path': self.solve_log,
            'uniqueness': "Unique" if len(self.found_solutions) == 1 else "Multiple Solutions" if len(self.found_solutions) > 1 else "No Solution",
            'solution_count': len(self.found_solutions),
            'solutions': [self._render_grid(s) for s in self.found_solutions]
        }

    def _render_grid(self, sol_dict: Dict) -> List[List[str]]:
        grid = [["#" for _ in range(self.board.width)] for _ in range(self.board.height)]
        for (r, c), val in sol_dict.items():
            grid[r][c] = str(val)
        return grid