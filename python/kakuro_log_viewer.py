#!/usr/bin/env python3
"""
Kakuro Generation Log Viewer
An interactive terminal-based tool for stepping through kakuro generation logs.

Usage:
    python kakuro_log_viewer.py [log_directory]
    
Controls:
    n / → / Space : Next step
    p / ← / b     : Previous step
    j <n>         : Jump to step number n
    s <stage>     : Skip to stage (topology, filling, uniqueness)
    l             : List available log files
    o <n>         : Open log file number n
    g             : Show grid only (toggle)
    q / Ctrl+C    : Quit
"""

import json
import os
import sys
import glob
from typing import List, Dict, Any, Optional

# ANSI color codes
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    # Foreground colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Background colors
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'
    
    # Bright colors
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'


def clear_screen():
    """Clear the terminal screen."""
    os.system('clear' if os.name != 'nt' else 'cls')


def get_stage_color(stage: str) -> str:
    """Get color for a stage."""
    colors = {
        'topology_creation': Colors.CYAN,
        'filling': Colors.GREEN,
        'uniqueness_validation': Colors.YELLOW,
    }
    return colors.get(stage, Colors.WHITE)


def get_substage_icon(substage: str) -> str:
    """Get icon for a substage."""
    icons = {
        'start': '🚀',
        'stamp_placement': '✚',
        'lattice_growth': '🌱',
        'patch_breaking': '💥',
        'validation_failed': '❌',
        'connectivity_check': '🔗',
        'complete': '✅',
        'number_placement': '🔢',
        'backtrack': '↩️',
        'consistency_check_failed': '⚠️',
        'alternative_found': '🔀',
        'repair_attempt': '🔧',
    }
    return icons.get(substage, '•')


class LogViewer:
    def __init__(self, log_directory: str = 'kakuro_logs'):
        self.log_directory = log_directory
        self.log_files: List[str] = []
        self.current_file_index = 0
        self.steps: List[Dict[str, Any]] = []
        self.current_step_index = 0
        self.show_grid_only = False
        self.highlighted_cells: List[List[int]] = []
        self.alternative_grid: List[List[Dict]] = []
        
        self.refresh_log_files()
    
    def refresh_log_files(self):
        """Refresh the list of available log files."""
        pattern = os.path.join(self.log_directory, 'kakuro_*.json')
        self.log_files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    
    def load_log_file(self, index: int = 0):
        """Load a log file by index."""
        if not self.log_files:
            print(f"{Colors.RED}No log files found in {self.log_directory}{Colors.RESET}")
            return False
        
        if index < 0 or index >= len(self.log_files):
            print(f"{Colors.RED}Invalid file index: {index}{Colors.RESET}")
            return False
        
        self.current_file_index = index
        filepath = self.log_files[index]
        
        try:
            with open(filepath, 'r') as f:
                self.steps = json.load(f)
            self.current_step_index = 0
            self.highlighted_cells = []
            self.alternative_grid = []
            return True
        except json.JSONDecodeError as e:
            print(f"{Colors.RED}Error parsing JSON: {e}{Colors.RESET}")
            return False
        except Exception as e:
            print(f"{Colors.RED}Error loading file: {e}{Colors.RESET}")
            return False
    
    def get_current_step(self) -> Optional[Dict[str, Any]]:
        """Get the current step data."""
        if not self.steps or self.current_step_index < 0 or self.current_step_index >= len(self.steps):
            return None
        return self.steps[self.current_step_index]
    
    def render_grid(self, grid: List[List[Dict]], highlighted: Optional[List[List[int]]] = None):
        """Render the kakuro grid with colors."""
        if not grid:
            return "No grid data"
        
        highlighted_set = set()
        if highlighted:
            highlighted_set = {(r, c) for r, c in highlighted}
        
        lines = []
        height = len(grid)
        width = len(grid[0]) if grid else 0
        
        # Column headers
        header = "    " + " ".join(f"{c:2}" for c in range(width))
        lines.append(f"{Colors.DIM}{header}{Colors.RESET}")
        lines.append("   +" + "---" * width + "+")
        
        for r, row in enumerate(grid):
            line_parts = [f"{Colors.DIM}{r:2}{Colors.RESET} |"]
            for c, cell in enumerate(row):
                cell_type = cell.get('type', 'WHITE')
                value = cell.get('value', 0)
                
                is_highlighted = (r, c) in highlighted_set
                
                if cell_type == 'BLOCK':
                    char = f"{Colors.BG_BLACK}{Colors.BRIGHT_BLACK} ██{Colors.RESET}"
                elif value > 0:
                    if is_highlighted:
                        char = f"{Colors.BG_YELLOW}{Colors.BLACK} {value:2}{Colors.RESET}"
                    else:
                        char = f"{Colors.GREEN} {value:2}{Colors.RESET}"
                else:
                    if is_highlighted:
                        char = f"{Colors.BG_YELLOW}{Colors.BLACK}  ·{Colors.RESET}"
                    else:
                        char = f"{Colors.DIM}  ·{Colors.RESET}"
                
                line_parts.append(char)
            
            line_parts.append("|")
            lines.append("".join(line_parts))
        
        lines.append("   +" + "---" * width + "+")
        return "\n".join(lines)
    
    def render_step_info(self, step: Dict[str, Any]) -> str:
        """Render step metadata."""
        stage = step.get('stage', 'unknown')
        substage = step.get('substage', 'unknown')
        step_id = step.get('step_id', '?')
        message = step.get('message', '')
        timestamp = step.get('timestamp', '')
        
        stage_color = get_stage_color(stage)
        icon = get_substage_icon(substage)
        
        lines = []
        lines.append(f"{Colors.BOLD}═══════════════════════════════════════════════════════════════{Colors.RESET}")
        lines.append(f"{Colors.BOLD}Step {step_id}/{len(self.steps) - 1}{Colors.RESET}")
        lines.append(f"{Colors.DIM}Time: {timestamp}{Colors.RESET}")
        lines.append("")
        lines.append(f"{stage_color}[{stage.upper().replace('_', ' ')}]{Colors.RESET} {icon} {substage.replace('_', ' ')}")
        lines.append("")
        lines.append(f"{Colors.WHITE}{message}{Colors.RESET}")
        lines.append(f"{Colors.BOLD}═══════════════════════════════════════════════════════════════{Colors.RESET}")
        
        return "\n".join(lines)
    
    def render_current_step(self):
        """Render the current step to the terminal."""
        clear_screen()
        
        step = self.get_current_step()
        if not step:
            print(f"{Colors.RED}No step data available{Colors.RESET}")
            return
        
        # File info
        current_file = os.path.basename(self.log_files[self.current_file_index]) if self.log_files else "N/A"
        print(f"{Colors.DIM}File: {current_file} ({self.current_file_index + 1}/{len(self.log_files)}){Colors.RESET}")
        print()
        
        # Step info
        if not self.show_grid_only:
            print(self.render_step_info(step))
            print()
        
        # Grid
        grid = step.get('grid', [])
        highlighted = step.get('data', {}).get('highlighted_cells', []) if isinstance(step.get('data'), dict) else []
        print(self.render_grid(grid, highlighted))
        
        # Alternative grid if present
        if isinstance(step.get('data'), dict):
            alt_grid = step['data'].get('alternative_grid', [])
            if alt_grid:
                print()
                print(f"{Colors.CYAN}Alternative Solution:{Colors.RESET}")
                print(self.render_grid(alt_grid, highlighted))
        
        # Controls
        print()
        print(f"{Colors.DIM}Controls: [n]ext [p]rev [j]ump [s]kip [l]ist [o]pen [g]rid [q]uit{Colors.RESET}")
    
    def next_step(self):
        """Go to next step."""
        if self.current_step_index < len(self.steps) - 1:
            self.current_step_index += 1
    
    def prev_step(self):
        """Go to previous step."""
        if self.current_step_index > 0:
            self.current_step_index -= 1
    
    def jump_to_step(self, step_num: int):
        """Jump to a specific step number."""
        if 0 <= step_num < len(self.steps):
            self.current_step_index = step_num
    
    def skip_to_stage(self, stage_prefix: str):
        """Skip to next occurrence of a stage."""
        stage_map = {
            'topology': 'topology_creation',
            'filling': 'filling',
            'uniqueness': 'uniqueness_validation',
        }
        
        target_stage = stage_map.get(stage_prefix.lower())
        if not target_stage:
            print(f"{Colors.RED}Unknown stage: {stage_prefix}{Colors.RESET}")
            return
        
        # Search from current position
        for i in range(self.current_step_index + 1, len(self.steps)):
            if self.steps[i].get('stage') == target_stage:
                self.current_step_index = i
                return
        
        # Wrap around
        for i in range(0, self.current_step_index):
            if self.steps[i].get('stage') == target_stage:
                self.current_step_index = i
                return
        
        print(f"{Colors.YELLOW}No steps found for stage: {target_stage}{Colors.RESET}")
    
    def list_files(self):
        """List available log files."""
        self.refresh_log_files()
        clear_screen()
        print(f"{Colors.BOLD}Available Log Files:{Colors.RESET}")
        print()
        for i, filepath in enumerate(self.log_files):
            filename = os.path.basename(filepath)
            marker = f"{Colors.GREEN}→{Colors.RESET}" if i == self.current_file_index else " "
            print(f"  {marker} [{i}] {filename}")
        print()
        print(f"{Colors.DIM}Use 'o <number>' to open a file{Colors.RESET}")
        input("\nPress Enter to continue...")
    
    def run(self):
        """Run the interactive viewer."""
        if not self.log_files:
            print(f"{Colors.RED}No log files found in {self.log_directory}{Colors.RESET}")
            print(f"{Colors.DIM}Generate some kakuros first to create log files.{Colors.RESET}")
            return
        
        # Load the most recent log file
        if not self.load_log_file(0):
            return
        
        while True:
            self.render_current_step()
            
            try:
                cmd = input(f"\n{Colors.CYAN}>{Colors.RESET} ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break
            
            if cmd in ('q', 'quit', 'exit'):
                print("Goodbye!")
                break
            elif cmd in ('n', '', ' '):
                self.next_step()
            elif cmd in ('p', 'b'):
                self.prev_step()
            elif cmd == 'g':
                self.show_grid_only = not self.show_grid_only
            elif cmd == 'l':
                self.list_files()
            elif cmd.startswith('j'):
                try:
                    step_num = int(cmd.split()[1])
                    self.jump_to_step(step_num)
                except (IndexError, ValueError):
                    print(f"{Colors.RED}Usage: j <step_number>{Colors.RESET}")
                    input("Press Enter...")
            elif cmd.startswith('s'):
                try:
                    stage = cmd.split()[1]
                    self.skip_to_stage(stage)
                except IndexError:
                    print(f"{Colors.RED}Usage: s <topology|filling|uniqueness>{Colors.RESET}")
                    input("Press Enter...")
            elif cmd.startswith('o'):
                try:
                    file_index = int(cmd.split()[1])
                    if self.load_log_file(file_index):
                        pass  # Loaded successfully
                    else:
                        input("Press Enter...")
                except (IndexError, ValueError):
                    print(f"{Colors.RED}Usage: o <file_number>{Colors.RESET}")
                    input("Press Enter...")


def main():
    log_dir = sys.argv[1] if len(sys.argv) > 1 else 'kakuro_logs'
    
    if not os.path.isdir(log_dir):
        print(f"{Colors.RED}Directory not found: {log_dir}{Colors.RESET}")
        print(f"{Colors.DIM}Create log files by running kakuro generation with logging enabled.{Colors.RESET}")
        sys.exit(1)
    
    viewer = LogViewer(log_dir)
    viewer.run()


if __name__ == '__main__':
    main()
