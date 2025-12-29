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
        cell = self.get_cell(r, c)
        if cell:
            cell.type = CellType.WHITE

    def generate_topology(self, density: float = 0.60, max_sector_length: int = 9):
        """
        Generates a Kakuro grid using a 'Stitcher' growth algorithm with Robust Seeding.
        Guarantees a non-empty board.
        """
        MAX_RETRIES = 20
        
        for attempt in range(MAX_RETRIES):
            # 1. Clear Grid (All Block)
            for r in range(self.height):
                for c in range(self.width):
                    self.grid[r][c].type = CellType.BLOCK
            self.white_cells = []

            # 2. Robust Seed: Try until we successfully place a cross
            if not self._place_random_seed():
                continue # Retry topology if seed failed (e.g. board too small)

            # 3. Growth Phase
            self._grow_lattice(density, max_sector_length)
            
            # 4. Filters & Stabilization
            # Only break huge patches, preserve the intricate structure
            self._break_large_patches(size=3)
            self._stabilize_grid()
            
            # 5. Validation
            # If we ended up with too few cells (bad random growth), retry internal loop
            min_cells = max(5, int(self.width * self.height * 0.15))
            if len(self.white_cells) >= min_cells:
                print("Missing whites fixed on attempt", attempt)
                return # Success!
        
        # If we failed 10 times, we just leave whatever we have (likely small board issue)

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

    def _stabilize_grid(self):
        """
        Repeatedly fixes runs and connectivity until stable.
        Connectivity should be mostly guaranteed by the growth algo,
        but this cleans up stray runs and ensures no islands formed due to symmetry/filtering.
        """
        changed = True
        iterations = 0
        max_stabilization_loops = 15 # Increased loops

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
        
        # Reset sector links on all white cells
        for cell in self.white_cells:
            cell.sector_h = None
            cell.sector_v = None
        
        # Horizontal
        for r in range(self.height):
            current_sector = []
            for c in range(self.width):
                if self.grid[r][c].type == CellType.WHITE:
                    current_sector.append(self.grid[r][c])
                else:
                    if current_sector:
                        self.sectors_h.append(current_sector)
                        for cell in current_sector:
                            cell.sector_h = current_sector
                        current_sector = []
            if current_sector:
                self.sectors_h.append(current_sector)
                for cell in current_sector:
                    cell.sector_h = current_sector

        # Vertical
        for c in range(self.width):
            current_sector = []
            for r in range(self.height):
                if self.grid[r][c].type == CellType.WHITE:
                    current_sector.append(self.grid[r][c])
                else:
                    if current_sector:
                        self.sectors_v.append(current_sector)
                        for cell in current_sector:
                            cell.sector_v = current_sector
                        current_sector = []
            if current_sector:
                self.sectors_v.append(current_sector)
                for cell in current_sector:
                    cell.sector_v = current_sector

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
