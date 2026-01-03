import random
from enum import Enum
from typing import List, Tuple, Optional, Set
from collections import deque
import logging

logger = logging.getLogger("kakuro_board")

class CellType(str, Enum):
    BLOCK = "BLOCK"
    WHITE = "WHITE"

class Cell:
    def __init__(self, r: int, c: int, type: CellType = CellType.WHITE):
        self.r = r
        self.c = c
        self.type = type
        self.value: Optional[int] = None
        self.clue_h: Optional[int] = None # Sum of the row to the right
        self.clue_v: Optional[int] = None # Sum of the col below
        self.sector_h: Optional[List['Cell']] = None # Direct reference for speed
        self.sector_v: Optional[List['Cell']] = None # Direct reference for speed

    def to_dict(self):
        return {
            "r": self.r,
            "c": self.c,
            "type": self.type.value,
            "value": self.value,
            "clue_h": self.clue_h,
            "clue_v": self.clue_v
        }
    
    def __repr__(self):
        return f"({self.r},{self.c})"


class KakuroBoard:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.grid: List[List[Cell]] = [[Cell(r, c) for c in range(width)] for r in range(height)]
        self.white_cells: List[Cell] = []
        self.sectors_h: List[List[Cell]] = []
        self.sectors_v: List[List[Cell]] = []

    def get_cell(self, r: int, c: int) -> Optional[Cell]:
        if 0 <= r < self.height and 0 <= c < self.width:
            return self.grid[r][c]
        return None
    
    def reset_values(self):
        """Clears all filled numbers and clues."""
        for r in range(self.height):
            for c in range(self.width):
                self.grid[r][c].value = None
                self.grid[r][c].clue_h = None
                self.grid[r][c].clue_v = None

    def set_block(self, r: int, c: int):
        cell = self.get_cell(r, c)
        if cell and cell.type != CellType.BLOCK:
            logger.debug(f"Blocking cell ({r}, {c})")
            cell.type = CellType.BLOCK
            cell.value = None

    def set_white(self, r: int, c: int):
        # CRITICAL FIX: Prevent White cells on the border.
        # White cells are only allowed from index 1 to Size-2.
        # This guarantees every run has a Block at index-1 to hold the clue.
        if 1 <= r < self.height - 1 and 1 <= c < self.width - 1:
            self.grid[r][c].type = CellType.WHITE

    def _reset_grid(self):
        """Resets grid and CLEARS SECTOR DATA to prevent stale references."""
        for r in range(self.height):
            for c in range(self.width):
                cell = self.grid[r][c]
                cell.type = CellType.BLOCK
                cell.value = None
                cell.sector_h = None
                cell.sector_v = None
                cell.clue_h = None
                cell.clue_v = None
        self.white_cells = []
        self.sectors_h = []
        self.sectors_v = []

    def generate_topology(self, density: float = 0.60, max_sector_length: int = 9, difficulty: str = "medium"):
        """
        Generates a Kakuro grid using a 'Stitcher' growth algorithm with Robust Seeding.
        Guarantees a non-empty board.

        Easy: Jigged topology with small rectangular clusters connected by short paths
        Medium: Balanced mix of structures
        Hard: Dense regions with longer runs and more complex patterns
        """
        MAX_RETRIES = 60

        # Adjust parameters based on difficulty
        if difficulty == "very_easy":
            # 2x2, 2x3, 3x2, and 3x3 stamps
            stamps = [
                (1, 3), (3, 1), # Short lines
                (1, 4), (4, 1), # Medium lines
                (2, 2)          # Hub/Corner (less frequent)
            ]
            num_stamps = random.randint(6, 12) 
            min_cells = 16 
            max_run_length = 5
        elif difficulty == "easy":
            stamps = [
                (1, 3), (3, 1), 
                (1, 4), (4, 1), 
                (1, 5), (5, 1),
                (2, 3), (3, 2),
                (2, 4), (4, 2),
                (3, 3), 
            ]
            num_stamps = random.randint(8, 15)
            min_cells = 22
            max_run_length = 6
        elif difficulty == "medium":
            island_mode = False
            max_sector_length = 7
            min_cells = 22
        elif difficulty == "hard":
            island_mode = False
            min_cells = 25
            max_sector_length = 9  # Allow longest runs
            density = min(0.70, density + 0.05)  # Denser
        
        
        for attempt in range(MAX_RETRIES):
            # 1. Clear Grid (All Block)
            self._reset_grid()
           
            # 2. Generate based on difficulty
            success = False
            if difficulty in ["very_easy", "easy"]:
                success = self._generate_stamps(stamps, num_stamps)
            else:
                if self._place_random_seed():
                    self._grow_lattice(density, max_sector_length)
                    success = len(self.white_cells) > 0
                print(f"Original growth algorithm: {success}")

            if not success:
                continue
          
            # 3. Filters & Stabilization
            if difficulty in ["hard"]:
                self._break_large_patches(size=4)
                self._stabilize_grid(gentle=False)
            elif difficulty in ["medium"]:
                self._break_large_patches(size=3)
                self._stabilize_grid(gentle=False)
            elif difficulty in ["very_easy", "easy"]:
                self._slice_long_runs(max_run_length)
                self._prune_singles()
                self._break_single_runs()
            
            self._collect_white_cells()
            
            # 4. Final Count Check
            if len(self.white_cells) < min_cells:
                continue

            # 5. Connectivity Check (Critical final gate)
            if not self._check_connectivity():
                logger.info("Topology failed connectivity check")
                continue

            if not self._validate_clue_headers():
                logger.info("Topology failed clue header check")
                continue
            
            self._identify_sectors()
            logger.info(f"Topology generated on attempt {attempt} ({difficulty})")
            return
        
        # If we failed 10 times, we just leave whatever we have (likely small board issue)
        logger.info("Topology failed after maximum retries")

    def _break_single_runs(self):
        """
        Removes runs of white cells that are exactly 1 cell long in any direction.
        This prevents trivial clues (e.g., a clue of '5' for a single cell).
        """
        changed = True
        while changed:
            changed = False
            for r in range(1, self.height - 1):
                for c in range(1, self.width - 1):
                    cell = self.grid[r][c]
                    if cell.type == CellType.WHITE:
                        # Check horizontal run length
                        h_len = 0
                        if self.grid[r][c-1].type == CellType.WHITE: h_len += 1
                        if self.grid[r][c+1].type == CellType.WHITE: h_len += 1
                        
                        # Check vertical run length
                        v_len = 0
                        if self.grid[r-1][c].type == CellType.WHITE: v_len += 1
                        if self.grid[r+1][c].type == CellType.WHITE: v_len += 1
                        
                        # If it has NO neighbors in EITHER direction (is a 1x1 island)
                        # OR if it's part of a horizontal run of length 1 AND vertical run of length 1
                        # then break it.
                        # A cell is a "single run" if it has at most 1 neighbor in *each* direction.
                        
                        # More simply: if a cell has only 1 neighbor TOTAL (e.g., EITHER left OR top)
                        # This is not quite right.
                        # The real condition is: does this cell START a sector of length 1?
                        
                        # Let's re-evaluate: A clue cell (block) should NEVER have a sector of length 1 adjacent to it.
                        # And a white cell should not be *isolated* such that it forms a sector of length 1.

                        # Correct approach: Check if this cell is part of a run of length 1.
                        # A run of length 1 means cell[r][c] is WHITE, BUT
                        # cell[r][c-1] is BLOCK AND cell[r][c+1] is BLOCK AND
                        # cell[r-1][c] is BLOCK AND cell[r+1][c] is BLOCK.
                        # That means it has ZERO white neighbors.
                        
                        is_isolated = True
                        for dr, dc in [(0,1), (0,-1), (1,0), (-1,0)]:
                            nr, nc = r + dr, c + dc
                            if self.grid[nr][nc].type == CellType.WHITE:
                                is_isolated = False
                                break
                        
                        if is_isolated:
                            self.set_block(r, c)
                            self.set_block(self.height - 1 - r, self.width - 1 - c)
                            changed = True
            # After potentially blocking cells, the sectors might become invalid (length 1).
            # The loop will re-run _prune_singles and then _break_single_runs again.
        
    def _generate_stamps(self, shapes: List[Tuple[int, int]], iterations: int) -> bool:
        """
        Starts from center, stamps rectangles outward.
        Guarantees symmetry and connectivity.
        """
        # Start in the center (guaranteed safe zone)
        center_r, center_c = self.height // 2, self.width // 2
        
        # Initial Seed (2x2)
        self._stamp_rect(center_r, center_c, 2, 2)
        
        current_iter = 0
        failures = 0
        
        while current_iter < iterations and failures < 20:
            self._collect_white_cells()
            if not self.white_cells: return False
            
            # Pick a random existing cell to extend from
            anchor = random.choice(self.white_cells)
            h, w = random.choice(shapes)
            
            # Try to place the new shape such that it OVERLAPS the anchor
            # This guarantees connectivity without thin paths
            offset_r = random.randint(-(h-1), 0)
            offset_c = random.randint(-(w-1), 0)
            
            top_r = anchor.r + offset_r
            left_c = anchor.c + offset_c
            
            # BOUNDS CHECKING
            # Ensure the stamp stays within [1, Height-2]
            # This ensures Row 0 and Row H-1 remain BLOCKS for clues.
            if (top_r >= 1 and 
                left_c >= 1 and 
                top_r + h < self.height - 1 and 
                left_c + w < self.width - 1):
                
                self._stamp_rect(top_r, left_c, h, w)
                current_iter += 1
            else:
                failures += 1
                
        return len(self.white_cells) > 0

    def _stamp_rect(self, r: int, c: int, h: int, w: int):
        """Stamps a rectangle at (r,c) and its rotational symmetric partner."""
        for i in range(h):
            for j in range(w):
                # Apply strict set_white which handles bounds check again
                self.set_white(r + i, c + j)
                
                # Symmetric Stamp
                sym_r = self.height - 1 - (r + i)
                sym_c = self.width - 1 - (c + j)
                self.set_white(sym_r, sym_c)

    def _slice_long_runs(self, max_len: int):
        """
        Detects runs longer than max_len and places a block in the middle.
        This keeps the math easy for beginners.
        """
        # Determine split points first to avoid modifying grid while iterating
        split_points = []

        # Horizontal Scans
        for r in range(1, self.height - 1):
            run_start = -1
            length = 0
            for c in range(1, self.width): # Scan up to width (exclusive of border)
                cell = self.grid[r][c]
                if cell.type == CellType.WHITE:
                    if run_start == -1: run_start = c
                    length += 1
                else:
                    if length > max_len:
                        mid = run_start + length // 2
                        split_points.append((r, mid))
                    run_start = -1
                    length = 0
            # End of row check
            if length > max_len:
                mid = run_start + length // 2
                split_points.append((r, mid))

        # Vertical Scans
        for c in range(1, self.width - 1):
            run_start = -1
            length = 0
            for r in range(1, self.height):
                cell = self.grid[r][c]
                if cell.type == CellType.WHITE:
                    if run_start == -1: run_start = r
                    length += 1
                else:
                    if length > max_len:
                        mid = run_start + length // 2
                        split_points.append((mid, c))
                    run_start = -1
                    length = 0
            if length > max_len:
                mid = run_start + length // 2
                split_points.append((mid, c))

        # Apply Splits (Symmetrically)
        for r, c in split_points:
            self.set_block(r, c)
            self.set_block(self.height - 1 - r, self.width - 1 - c)

    def _prune_singles(self):
        """Remove 1x1 isolated white cells (orphans)."""
        changed = True
        while changed:
            changed = False
            for r in range(1, self.height - 1):
                for c in range(1, self.width - 1):
                    if self.grid[r][c].type == CellType.WHITE:
                        # Check neighbors
                        h_neighbors = 0
                        if self.grid[r][c-1].type == CellType.WHITE: h_neighbors += 1
                        if self.grid[r][c+1].type == CellType.WHITE: h_neighbors += 1
                        
                        v_neighbors = 0
                        if self.grid[r-1][c].type == CellType.WHITE: v_neighbors += 1
                        if self.grid[r+1][c].type == CellType.WHITE: v_neighbors += 1
                        
                        # If isolated in BOTH directions (length 1 run horizontally AND vertically)
                        # Then it's a 1x1 island. Remove it.
                        if h_neighbors == 0 and v_neighbors == 0:
                            self.set_block(r, c)
                            self.set_block(self.height - 1 - r, self.width - 1 - c)
                            changed = True

    def _validate_clue_headers(self) -> bool:
        """
        CRITICAL: Ensures every white cell is part of a run that has a valid 
        BLOCK immediately preceding it to hold the clue.
        """
        for r in range(self.height):
            for c in range(self.width):
                if self.grid[r][c].type == CellType.WHITE:
                    
                    # 1. Check Horizontal Header
                    # If this is the start of a run (cell to left is not white)
                    if c > 0 and self.grid[r][c-1].type != CellType.WHITE:
                        # The cell to the left MUST be a BLOCK
                        if self.grid[r][c-1].type != CellType.BLOCK:
                            return False 
                    elif c == 0:
                        # A white cell at c=0 is impossible given our bounds check, 
                        # but if it happened, it's a headless run.
                        return False

                    # 2. Check Vertical Header
                    if r > 0 and self.grid[r-1][c].type != CellType.WHITE:
                        if self.grid[r-1][c].type != CellType.BLOCK:
                            return False
                    elif r == 0:
                        return False

        return True

    def _check_connectivity(self) -> bool:
        self._collect_white_cells()
        if not self.white_cells: return False
        
        start = self.white_cells[0]
        q = deque([(start.r, start.c)])
        seen = {(start.r, start.c)}
        
        count = 0
        while q:
            r, c = q.popleft()
            count += 1
            
            for dr, dc in [(0,1), (0,-1), (1,0), (-1,0)]:
                nr, nc = r+dr, c+dc
                if 0 <= nr < self.height and 0 <= nc < self.width:
                    if self.grid[nr][nc].type == CellType.WHITE and (nr,nc) not in seen:
                        seen.add((nr,nc))
                        q.append((nr,nc))
                        
        return count == len(self.white_cells)

    def _collect_white_cells(self):
        self.white_cells = [c for row in self.grid for c in row if c.type == CellType.WHITE]

    def _place_random_seed(self) -> bool:
        """
        Attempts to place a starting 'Cross' or 'T' shape in the center area.
        Returns True if successful.
        """
        margin_x = max(1, self.width // 4)
        margin_y = max(1, self.height // 4)
        
        # Define the box where we can start
        min_r, max_r = margin_y, self.height - 1 - margin_y
        min_c, max_c = margin_x, self.width - 1 - margin_x
        
        if min_r >= max_r: min_r, max_r = 1, self.height - 2
        if min_c >= max_c: min_c, max_c = 1, self.width - 2
        
        for _ in range(20): # Try 20 times to place a seed
            r = random.randint(min_r, max_r)
            c = random.randint(min_c, max_c)
            
            # Try to place a horizontal run of 3 and vertical run of 3 crossing at r,c
            # Check bounds
            if r-1 > 0 and r+1 < self.height-1 and c-1 > 0 and c+1 < self.width-1:
                # Place Cross
                coords = [(r, c), (r, c-1), (r, c+1), (r-1, c), (r+1, c)]
                for cr, cc in coords:
                    self.set_white(cr, cc)
                    self.set_white(self.height - 1 - cr, self.width - 1 - cc) # Symmetry
                
                self._collect_white_cells()
                return True
                
        return False

    def _grow_lattice(self, density: float, max_sector_length: int):
        target_white = int((self.width - 2) * (self.height - 2) * density)
        current_white = len(self.white_cells)
        
        attempts = 0
        max_attempts = 2000 # Give it enough tries
        
        while current_white < target_white and attempts < max_attempts:
            if not self.white_cells: break
            
            # Pick a random existing white cell to grow FROM
            source = random.choice(self.white_cells)
            r, c = source.r, source.c
            
            # Determine orientation (Perpendicular to existing neighbors)
            has_h = (self.get_cell(r, c-1) and self.get_cell(r, c-1).type == CellType.WHITE) or \
                    (self.get_cell(r, c+1) and self.get_cell(r, c+1).type == CellType.WHITE)
            has_v = (self.get_cell(r-1, c) and self.get_cell(r-1, c).type == CellType.WHITE) or \
                    (self.get_cell(r+1, c) and self.get_cell(r+1, c).type == CellType.WHITE)
            
            if has_h and has_v: grow_vert = random.choice([True, False])
            elif has_h: grow_vert = True
            elif has_v: grow_vert = False
            else: grow_vert = random.choice([True, False]) # Single cell (seed center?), random
            
            new_len = random.randint(2, max_sector_length)
            
            # Try to stitch a line through (r,c)
            # We shuffle shifts to avoid bias
            shifts = list(range(new_len))
            random.shuffle(shifts)
            
            placed = False
            for shift in shifts:
                cells_indices = []
                possible = True
                
                for k in range(new_len):
                    idx = k - shift
                    nr, nc = (r + idx, c) if grow_vert else (r, c + idx)
                    
                    # Strict Margins
                    if nr < 1 or nr >= self.height - 1 or nc < 1 or nc >= self.width - 1:
                        possible = False; break
                    cells_indices.append((nr, nc))
                
                if possible:
                    # Apply
                    added_new = False
                    for cr, cc in cells_indices:
                        if self.grid[cr][cc].type == CellType.BLOCK:
                            self.set_white(cr, cc)
                            self.set_white(self.height - 1 - cr, self.width - 1 - cc)
                            added_new = True
                    
                    if added_new:
                        placed = True
                        break # Move to next growth step
            
            if placed:
                self._collect_white_cells()
                current_white = len(self.white_cells)
                attempts = 0
            else:
                attempts += 1

    def _break_large_patches(self, size: int = 3):
        """Breaks 3x3 (or larger) patches of white cells by adding blocks at valid spots."""
        # We limit the number of breaks to avoid destroying the grid
        for _ in range(50): 
            found = False
            for r in range(1, self.height - size):
                for c in range(1, self.width - size):
                    # Check for size x size white patch
                    is_patch = True
                    patch_cells = []
                    for ir in range(size):
                        for ic in range(size):
                            cell = self.grid[r+ir][c+ic]
                            patch_cells.append(cell)
                            if cell.type != CellType.WHITE:
                                is_patch = False
                                break
                        if not is_patch: break
                    
                    if is_patch:
                        found = True
                        # Pick a cell to block that is touching a block (to avoid islands)
                        candidates = []
                        for cell in patch_cells:
                            has_block_neighbor = False
                            for dr, dc in [(0,1),(0,-1),(1,0),(-1,0)]:
                                n = self.get_cell(cell.r+dr, cell.c+dc)
                                if n and n.type == CellType.BLOCK:
                                    has_block_neighbor = True; break
                            if has_block_neighbor: candidates.append(cell)
                        
                        target = random.choice(candidates) if candidates else random.choice(patch_cells)
                        self.set_block(target.r, target.c)
                        self.set_block(self.height-1-target.r, self.width-1-target.c)
                        break # Break inner loops to restart scan
                if found: break 
            if not found: break # No patches left

    def _stabilize_grid(self, gentle: bool = False):
        """
        Repeatedly fixes runs and connectivity until stable.
        Connectivity should be mostly guaranteed by the growth algo,
        but this cleans up stray runs and ensures no islands formed due to symmetry/filtering.
        """
        changed = True
        iterations = 0
        max_stabilization_loops = 10 if gentle else 15

        while changed and iterations < max_stabilization_loops:
            changed = False
            
            # Fix invalid runs (length 1 or >9)
            if self._fix_invalid_runs():
                changed = True

            # Ensure connectivity - crucial after filtering/symmetry changes
            if self._ensure_connectivity():
                changed = True
                
            iterations += 1
            
        self._collect_white_cells()
        self._identify_sectors()

    def _stabilize_islands(self):
        """
        Special stabilization for island topologies.
        Only fixes critical issues without destroying the island structure.
        """
        changed = True
        iterations = 0
        max_iterations = 5  # Very limited iterations
        
        while changed and iterations < max_iterations:
            changed = False
            
            # Only fix runs that are REALLY broken (length 1) and not part of paths
            if self._fix_invalid_runs_gentle():
                changed = True
            
            # Ensure connectivity (this is critical)
            if self._ensure_connectivity():
                changed = True
            
            iterations += 1
        
        self._collect_white_cells()
        self._identify_sectors()
    
    def _fix_invalid_runs_gentle(self) -> bool:
        """
        Gentler version that only removes truly isolated single cells,
        not single cells that are part of connecting paths.
        """
        changed = False
        
        # Only remove cells that have NO neighbors in BOTH directions
        for r in range(self.height):
            for c in range(self.width):
                if self.grid[r][c].type != CellType.WHITE:
                    continue
                
                # Check horizontal neighbors
                h_before = (c > 0 and self.grid[r][c-1].type == CellType.WHITE)
                h_after = (c < self.width - 1 and self.grid[r][c+1].type == CellType.WHITE)
                has_h_neighbor = h_before or h_after
                
                # Check vertical neighbors
                v_before = (r > 0 and self.grid[r-1][c].type == CellType.WHITE)
                v_after = (r < self.height - 1 and self.grid[r+1][c].type == CellType.WHITE)
                has_v_neighbor = v_before or v_after
                
                # Only block if it's truly isolated (no neighbors in any direction)
                if not has_h_neighbor and not has_v_neighbor:
                    self.set_block(r, c)
                    self.set_block(self.height - 1 - r, self.width - 1 - c)
                    changed = True
        
        # Still need to handle very long runs (>9)
        # Horizontal
        for r in range(self.height):
            c = 0
            while c < self.width:
                if self.grid[r][c].type == CellType.WHITE:
                    start = c
                    length = 0
                    while c < self.width and self.grid[r][c].type == CellType.WHITE:
                        length += 1
                        c += 1
                    
                    if length > 9:
                        mid = start + length // 2
                        self.set_block(r, mid)
                        self.set_block(self.height-1-r, self.width-1-mid)
                        changed = True
                else:
                    c += 1
        
        # Vertical
        for c in range(self.width):
            r = 0
            while r < self.height:
                if self.grid[r][c].type == CellType.WHITE:
                    start = r
                    length = 0
                    while r < self.height and self.grid[r][c].type == CellType.WHITE:
                        length += 1
                        r += 1
                    
                    if length > 9:
                        mid = start + length // 2
                        self.set_block(mid, c)
                        self.set_block(self.height-1-mid, self.width-1-c)
                        changed = True
                else:
                    r += 1
        
        return changed
        

    def _fix_invalid_runs(self) -> bool:
        """
        Scans for runs of length 1 or >9.
        Length 1 -> Block it (It's a stray).
        Length >9 -> Split it (Add block in middle).
        """
        changed = False
        
        # Horizontal
        for r in range(self.height):
            c = 0
            while c < self.width:
                if self.grid[r][c].type == CellType.WHITE:
                    start = c
                    length = 0
                    while c < self.width and self.grid[r][c].type == CellType.WHITE:
                        length += 1
                        c += 1
                    
                    # Check Run
                    if length == 1:
                        self.set_block(r, start)
                        self.set_block(self.height-1-r, self.width-1-start)
                        changed = True
                    elif length > 9:
                        mid = start + length // 2
                        self.set_block(r, mid)
                        self.set_block(self.height-1-r, self.width-1-mid)
                        changed = True
                else:
                    c += 1
                    
        # Vertical
        for c in range(self.width):
            r = 0
            while r < self.height:
                if self.grid[r][c].type == CellType.WHITE:
                    start = r
                    length = 0
                    while r < self.height and self.grid[r][c].type == CellType.WHITE:
                        length += 1
                        r += 1
                    
                    if length == 1:
                        self.set_block(start, c)
                        self.set_block(self.height-1-start, self.width-1-c)
                        changed = True
                    elif length > 9:
                        mid = start + length // 2
                        self.set_block(mid, c)
                        self.set_block(self.height-1-mid, self.width-1-c)
                        changed = True
                else:
                    r += 1
                    
        return changed

    def _block_sym(self, cell):
        self.set_block(cell.r, cell.c)
        self.set_block(self.height-1-cell.r, self.width-1-cell.c)


    def _ensure_connectivity(self):
        """Phase 2.5: Ensure all white cells form a single connected component."""
        # Find all white cells
        white_cells = []
        for r in range(self.height):
            for c in range(self.width):
                if self.grid[r][c].type == CellType.WHITE:
                    white_cells.append((r, c))
        
        
        if not white_cells:
            return False

        white_set = set(white_cells)
        components = []
        visited = set()

        for start_node in white_cells:
            if start_node in visited:
                continue
            
            # BFS for this component
            component = []
            q = deque([start_node])
            visited.add(start_node)
            while q:
                curr = q.popleft()
                component.append(curr)
                r, c = curr
                for dr, dc in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                    nr, nc = r + dr, c + dc
                    if (nr, nc) in white_set and (nr, nc) not in visited:
                        visited.add((nr, nc))
                        q.append((nr, nc))
            components.append(component)
        
        if not components:
            return False

        # Keep the largest component
        largest_component = max(components, key=len)
        largest_component_set = set(largest_component)
        
        changed = False
        # Turn all other white cells to blocks
        for r, c in white_cells:
            if (r, c) not in largest_component_set:
                self.set_block(r, c)
                self.set_block(self.height - 1 - r, self.width - 1 - c)
                changed = True

        return changed

    def _collect_white_cells(self):
        self.white_cells = []
        for r in range(self.height):
            for c in range(self.width):
                if self.grid[r][c].type == CellType.WHITE:
                    self.white_cells.append(self.grid[r][c])

    def _identify_sectors(self):
        self.sectors_h = []
        self.sectors_v = []
        
        # Horizontal
        for r in range(self.height):
            current_sector = []
            for c in range(self.width):
                cell = self.grid[r][c]
                if cell.type == CellType.WHITE:
                    current_sector.append(cell)
                else:
                    if current_sector:
                        self.sectors_h.append(current_sector)
                        for s_cell in current_sector:
                            s_cell.sector_h = current_sector
                        current_sector = []
            if current_sector:
                self.sectors_h.append(current_sector)
                for s_cell in current_sector:
                    s_cell.sector_h = current_sector

        # Vertical
        for c in range(self.width):
            current_sector = []
            for r in range(self.height):
                cell = self.grid[r][c]
                if cell.type == CellType.WHITE:
                    current_sector.append(cell)
                else:
                    if current_sector:
                        self.sectors_v.append(current_sector)
                        for s_cell in current_sector:
                            s_cell.sector_v = current_sector
                        current_sector = []
            if current_sector:
                self.sectors_v.append(current_sector)
                for s_cell in current_sector:
                    s_cell.sector_v = current_sector

    def _limit_sector_lengths(self, max_length: int) -> bool:
        """Split sectors that exceed max_length by adding blocks."""
        changed = False
        
        # Process horizontal sectors
        for sector in list(self.sectors_h):  # Copy list as we'll modify
            if len(sector) > max_length:
                # Split in middle
                mid_idx = len(sector) // 2
                cell = sector[mid_idx]
                self.set_block(cell.r, cell.c)
                self.set_block(self.height - 1 - cell.r, self.width - 1 - cell.c)
                changed = True
        
        # Process vertical sectors
        for sector in list(self.sectors_v):
            if len(sector) > max_length:
                mid_idx = len(sector) // 2
                cell = sector[mid_idx]
                self.set_block(cell.r, cell.c)
                self.set_block(self.height - 1 - cell.r, self.width - 1 - cell.c)
                changed = True
        
        return changed

    def to_json(self):
        return [row[:] for row in self.grid] # List of lists of Cells (which are objects, but we'll serialize them later)
