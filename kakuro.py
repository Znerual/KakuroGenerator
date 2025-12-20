import random
from enum import Enum
from typing import List, Tuple, Optional, Set
from collections import deque

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

    def generate_topology(self, density: float = 0.25, max_sector_length: int = 5):
        """Phase 2: Topology Generation with optional sector length limiting for uniqueness."""
        # 1. Force top and left boundaries to be blocks for clues
        for c in range(self.width):
            self.set_block(0, c)
            self.set_block(self.height - 1, self.width - 1 - c) # Symmetry
        for r in range(self.height):
            self.set_block(r, 0)
            self.set_block(self.height - 1 - r, self.width - 1) # Symmetry

        # 2. Initialize & Symmetry
        # We'll iterate through the top-left half (including diagonal) and mirror changes
        for r in range(self.height):
            for c in range(self.width):
                # Skip already blocked boundary cells
                if r == 0 or c == 0 or r == self.height-1 or c == self.width-1:
                    continue
                    
                # Random blocking
                if random.random() < density:
                    self.set_block(r, c)
                    self.set_block(self.height - 1 - r, self.width - 1 - c)

        # Iterative stabilization
        changed = True
        loop_count = 0
        while changed and loop_count < 20: # Safety break
            changed = False
            
            # Fix single runs
            if self._fix_single_runs():
                changed = True
            
            # Ensure connectivity
            if self._ensure_connectivity():
                changed = True
            
            loop_count += 1
        
        self._collect_white_cells()
        self._identify_sectors()
        
        # Phase 2.6: Limit sector lengths for better uniqueness
        if max_sector_length > 0:
            if self._limit_sector_lengths(max_sector_length):
                # Re-run stabilization after limiting
                self._fix_single_runs()
                self._collect_white_cells()
                self._identify_sectors()

    def set_block(self, r: int, c: int):
        cell = self.get_cell(r, c)
        if cell:
            cell.type = CellType.BLOCK

    def _fix_single_runs(self) -> bool:
        """Phase 2.4: Ensure no horizontal or vertical white run is of length 1."""
        changed = True
        made_any_change = False
        while changed:
            changed = False
            # Check Horizontal
            for r in range(self.height):
                for c in range(self.width):
                    # Only check start of runs
                    is_start = (self.grid[r][c].type == CellType.WHITE) and \
                               (c == 0 or self.grid[r][c-1].type == CellType.BLOCK)
                    
                    if is_start:
                        # Calculate run length
                        length = 0
                        k = c
                        while k < self.width and self.grid[r][k].type == CellType.WHITE:
                            length += 1
                            k += 1
                        
                        if length == 1:
                            # Turn into block
                            self.set_block(r, c)
                            self.set_block(self.height - 1 - r, self.width - 1 - c)
                            changed = True
                            made_any_change = True
            
            # Check Vertical
            for c in range(self.width):
                for r in range(self.height):
                    # Only check start of runs
                    is_start = (self.grid[r][c].type == CellType.WHITE) and \
                               (r == 0 or self.grid[r-1][c].type == CellType.BLOCK)
                    
                    if is_start:
                        length = 0
                        k = r
                        while k < self.height and self.grid[k][c].type == CellType.WHITE:
                            length += 1
                            k += 1
                        
                        if length == 1:
                            self.set_block(r, c)
                            self.set_block(self.height - 1 - r, self.width - 1 - c)
                            changed = True
                            made_any_change = True
        return made_any_change

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

        if changed:
            # We made changes (deleted disconnected components)
            # The caller will handle re-running fix_single_runs
            return True
        return False

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
