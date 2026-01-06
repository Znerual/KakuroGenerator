import sys
import os
import kakuro
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A5
from reportlab.lib import colors
from reportlab.lib.units import mm


# --- CONFIGURATION ---
PDF_FILENAME = "kakuro_book_design.pdf"
PAGE_WIDTH, PAGE_HEIGHT = A5
MARGIN_X = 10 * mm
MARGIN_Y = 10 * mm

# Layout Constants
DIVIDER_Y = 55 * mm  # Height of the solution footer area
SOLUTION_OFFSET = 2
DIFFICULTY = "medium"

# Fonts - "Classic Book" style
FONT_TITLE = "Times-Bold"      # For "Puzzle #1"
FONT_SERIF = "Times-Roman"     # For general text
FONT_ITALIC = "Times-Italic"   # For "Difficulty" label
FONT_SANS = "Helvetica-Bold"   # For grid numbers (Clarity)
FONT_HAND = "Helvetica"        # For solution numbers

def draw_diamond(c, x, y, size, filled=True):
    """Draws a diamond shape centered at x,y."""
    half = size / 2
    p = c.beginPath()
    p.moveTo(x, y + half)      # Top
    p.lineTo(x + half, y)      # Right
    p.lineTo(x, y - half)      # Bottom
    p.lineTo(x - half, y)      # Left
    p.close()
    
    c.setLineWidth(0.5)
    c.setStrokeColor(colors.black)
    if filled:
        c.setFillColor(colors.black)
        c.drawPath(p, fill=1, stroke=0)
    else:
        c.setFillColor(colors.white)
        c.drawPath(p, fill=0, stroke=1)

def draw_difficulty_badge(c, right_x, top_y, difficulty_name, difficulty_score):
    """
    Draws a styled difficulty indicator at the top right.
    Layout:
       Difficulty      (Small, Italic)
        MEDIUM         (Bold, Uppercase)
       ♦ ♦ ♢           (Visual Meter)
    """
    # 1. Map difficulty to a 1-4 scale
    levels = {"very_easy": 1, "easy": 2, "medium": 3, "hard": 4}
    level_num = levels.get(difficulty_name.lower(), 2) # Default to 2
    
    # 2. Draw "Difficulty" Label
    c.setFillColor(colors.black)
    c.setFont(FONT_ITALIC, 9)
    # y coordinates: top_y is the baseline for the top text
    c.drawRightString(right_x, top_y, f"Difficulty Level: {difficulty_score}")
    
    # 3. Draw Level Name (MEDIUM)
    c.setFont(FONT_TITLE, 14)
    # Move down by 14pts
    c.drawRightString(right_x, top_y - 14, difficulty_name.upper())
    
    # 4. Draw Visual Diamonds
    # Start drawing form right to left or left to right? 
    # Let's align them to the right to match text
    diamond_size = 4 * mm
    spacing = 1 * mm
    total_width = (3 * diamond_size) + (2 * spacing) # Assuming max 3 or 4 stars
    
    start_x = right_x - total_width + (diamond_size/2)
    diamond_y = top_y - 22 # Below the text
    
    # Draw 3 indicators (Standard scale)
    for i in range(1, 4):
        cx = start_x + ((i-1) * (diamond_size + spacing))
        is_filled = i <= level_num
        draw_diamond(c, cx, diamond_y, diamond_size, filled=is_filled)

def draw_clue_cell(c, x, y, size, down_val, right_val):
    """Draws a Kakuro clue cell with a slightly darker grey and sharp lines."""
    # 1. Background (Mid-Grey for better contrast)
    c.setFillColor(colors.Color(0.85, 0.85, 0.85)) # slightly darker than lightgrey
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)
    c.rect(x, y, size, size, fill=1, stroke=1)
    
    # 2. Diagonal
    c.setLineWidth(0.5)
    c.line(x, y + size, x + size, y)
    
    # 3. Text
    c.setFillColor(colors.black)
    c.setFont(FONT_SANS, size / 3.8) # Slightly smaller, bolder font
    
    if down_val and down_val != 0:
        # Shifted slightly for optical centering
        c.drawCentredString(x + (size * 0.28), y + (size * 0.12), str(down_val))
        
    if right_val and right_val != 0:
        c.drawCentredString(x + (size * 0.72), y + (size * 0.62), str(right_val))

def draw_input_cell(c, x, y, size, value=None, is_solution=False):
    """Draws a crisp white input cell."""
    c.setFillColor(colors.grey)
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)
    c.rect(x, y, size, size, fill=1, stroke=1)
    
    if is_solution and value:
        c.setFillColor(colors.black)
        # Use a simpler font for the 'handwritten' number look
        c.setFont(FONT_HAND, size / 1.6)
        c.drawCentredString(x + (size / 2), y + (size * 0.22), str(value))

def draw_thick_border(c, start_x, top_y, width, height):
    """Draws a thick border around the entire active grid area."""
    c.setStrokeColor(colors.black)
    c.setLineWidth(2.0) # Thick border
    c.setFillColor(colors.transparent)
    # y is bottom-left, so we calculate from top
    c.rect(start_x, top_y - height, width, height, stroke=1, fill=0)

def get_active_board_bounds(board_json, cell_size):
    """
    Calculates the bounding box of the ACTUAL drawn cells (excluding whitespace/skipped cells).
    This allows us to draw a nice border around the puzzle or center it perfectly.
    Returns: (min_col, max_col, min_row, max_row) indices
    """
    grid = board_json['grid']
    min_r, max_r = len(grid), -1
    min_c, max_c = len(grid[0]), -1
    
    found_any = False
    
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            clue_h = cell.get('clue_h', 0)
            clue_v = cell.get('clue_v', 0)
            ctype = str(cell.get('type', 'white')).upper()
            
            # If it's a visible cell
            if ctype in ["WHITE", "INPUT"] or clue_h > 0 or clue_v > 0:
                min_r = min(min_r, r)
                max_r = max(max_r, r)
                min_c = min(min_c, c)
                max_c = max(max_c, c)
                found_any = True
                
    if not found_any:
        return 0, 0, 0, 0
        
    return min_c, max_c, min_r, max_r

def draw_board(c, board_json, start_x, top_y, cell_size, show_solution=False):
    """Draws the board and returns the actual width/height drawn."""
    grid = board_json['grid']
    
    # Draw cells
    for r, row_data in enumerate(grid):
        for col, cell in enumerate(row_data):
            pos_x = start_x + (col * cell_size)
            pos_y = top_y - ((r + 1) * cell_size)
            
            clue_h = cell.get('clue_h', 0)
            clue_v = cell.get('clue_v', 0)
            val = cell.get('value', None)
            cell_type = str(cell.get('type', 'white')).upper()

            if cell_type in ["WHITE", "INPUT"]:
                draw_input_cell(c, pos_x, pos_y, cell_size, val, show_solution)
            elif clue_h > 0 or clue_v > 0:
                draw_clue_cell(c, pos_x, pos_y, cell_size, clue_v, clue_h)
            # Skip empty fillers

    # Draw Thick Outer Border around the active puzzle shape? 
    # Usually Kakuros are irregular, so a square border around the whole bounds 
    # looks professional.
    min_c, max_c, min_r, max_r = get_active_board_bounds(board_json, cell_size)
    
    # To draw a border around the *content*, we need relative coordinates
    # But usually, keeping the grid structure visible (even empty corners) 
    # is confusing. Let's just rely on the cell borders, but maybe 
    # draw a thick border around the *bounding box* of the grid if desired.
    # For now, we leave the irregular shape as is, which is standard for Kakuro.
    pass

def calculate_optimal_cell_size(board_json, max_width, max_height):
    rows = len(board_json['grid'])
    cols = len(board_json['grid'][0])
    if rows == 0 or cols == 0: return 10
    return min(max_width / cols, max_height / rows)

def generate_pdf(num_puzzles=4, width=10, height=12):
    c = canvas.Canvas(PDF_FILENAME, pagesize=A5)
    c.setTitle("Kakuro Puzzle Book")
    
    print(f"Generating {num_puzzles} puzzles...")
    puzzles = []

    # 1. Generate Data
    for i in range(num_puzzles):
       
        board_obj = kakuro.generate_kakuro(width, height, difficulty=DIFFICULTY.lower(), use_cpp=True)
        difficulty_score = kakuro.KakuroDifficultyEstimator(board_obj).estimate_difficulty_detailed()
        print(f"Puzzle {i+1}: Difficulty: {difficulty_score} Techniques: {difficulty_score.solve_path}")
        board_data = kakuro.export_to_json(board_obj)
        puzzles.append((board_data, difficulty_score))
      

    total_pages = num_puzzles + SOLUTION_OFFSET
    
    for page_idx in range(total_pages):
        puzzle_idx = page_idx
        solution_idx = page_idx - SOLUTION_OFFSET
        
        has_puzzle = 0 <= puzzle_idx < len(puzzles)
        has_solution = 0 <= solution_idx < len(puzzles)

        if not has_puzzle and not has_solution:
            break

        # ==========================================
        # 1. HEADER DESIGN
        # ==========================================
        if has_puzzle:
            current_puzzle, difficulty_score = puzzles[puzzle_idx]
            # Draw the new Fancy Difficulty Badge
            draw_difficulty_badge(c, PAGE_WIDTH - 2 * MARGIN_X, PAGE_HEIGHT - MARGIN_Y, DIFFICULTY, f"{difficulty_score}" )
            
            # Main Title (Black Pill Box)
            title_text = f"PUZZLE  {puzzle_idx + 1}"
            c.setFont(FONT_TITLE, 22)
            title_w = c.stringWidth(title_text, FONT_TITLE, 22)
            
            box_w = title_w + 20 * mm
            box_h = 14 * mm
            box_x = (PAGE_WIDTH - box_w) / 2
            
            # Align top of box with the Difficulty text baseline roughly
            box_y = PAGE_HEIGHT - MARGIN_Y - box_h - 2 * mm 
            
            c.setFillColor(colors.black)
            c.rect(box_x, box_y, box_w, box_h, fill=1, stroke=0)
            
            c.setFillColor(colors.white)
            c.drawCentredString(PAGE_WIDTH / 2, box_y + 4 * mm, title_text)

            # ==========================================
            # 2. MAIN PUZZLE
            # ==========================================
            # Define area below header, above footer
            area_top_y = box_y - 10 * mm
            area_bottom_y = DIVIDER_Y + 5 * mm
            area_w = PAGE_WIDTH - (2 * MARGIN_X)
            area_h = area_top_y - area_bottom_y
            
            
            # Calculate Layout
            cell_size = calculate_optimal_cell_size(current_puzzle, area_w, area_h)
            
            # Get actual pixel size of the grid
            grid_cols = len(current_puzzle['grid'][0])
            grid_rows = len(current_puzzle['grid'])
            board_w = grid_cols * cell_size
            board_h = grid_rows * cell_size
            
            # Center positions
            x_offset = MARGIN_X + (area_w - board_w) / 2
            y_offset = area_bottom_y + (area_h - board_h) / 2 + board_h
            
            draw_board(c, current_puzzle, x_offset, y_offset, cell_size, show_solution=False)

        # ==========================================
        # 3. SOLUTION FOOTER DESIGN
        # ==========================================
        if has_solution:
            # Draw Light Grey Background for the Footer
            c.setFillColor(colors.Color(0.95, 0.95, 0.95)) # Very light grey (whitesmoke)
            c.setStrokeColor(colors.transparent)
            # Rectangle covers bottom part of page
            c.rect(0, 0, PAGE_WIDTH, DIVIDER_Y, fill=1, stroke=0)
            
            # Add a thin top border to the footer
            c.setStrokeColor(colors.black)
            c.setLineWidth(1)
            c.line(0, DIVIDER_Y, PAGE_WIDTH, DIVIDER_Y)
            
            # --- Solution Content ---
            sol_puzzle, difficulty_score = puzzles[solution_idx]
            
            # Left Side: Text Label
            c.setFillColor(colors.black)
            c.setFont(FONT_TITLE, 14)
            
            # Vertically center text in footer
            text_y_center = DIVIDER_Y / 2
            
            c.drawString(MARGIN_X + 5*mm, text_y_center + 5, "SOLUTION")
            c.setFont(FONT_SERIF, 12)
            c.drawString(MARGIN_X + 5*mm, text_y_center - 10, f"Puzzle #{solution_idx + 1}")
            
            # Right Side: Mini Grid
            # Available space for grid
            grid_area_w = PAGE_WIDTH - 60*mm # Reserve 60mm for text
            grid_area_h = DIVIDER_Y - 10*mm # Padding
            
            # Calculate size
            cell_size = calculate_optimal_cell_size(sol_puzzle, grid_area_w, grid_area_h)
            
            # Get dimensions
            grid_cols = len(sol_puzzle['grid'][0])
            grid_rows = len(sol_puzzle['grid'])
            board_w = grid_cols * cell_size
            board_h = grid_rows * cell_size
            
            # Position: Right aligned with margin, centered vertically
            board_x = PAGE_WIDTH - MARGIN_X - board_w
            board_y = (DIVIDER_Y - board_h) / 2 + board_h
            
            draw_board(c, sol_puzzle, board_x, board_y, cell_size, show_solution=True)

        elif not has_puzzle:
             # End of book Page
            c.setFillColor(colors.black)
            c.setFont(FONT_TITLE, 16)
            c.drawCentredString(PAGE_WIDTH/2, PAGE_HEIGHT/2, "CONGRATULATIONS!")
            c.setFont(FONT_SERIF, 12)
            c.drawCentredString(PAGE_WIDTH/2, PAGE_HEIGHT/2 - 20, "You have completed all puzzles.")

        # ==========================================
        # 4. FOOTER (Page Number)
        # ==========================================
        # Standard book placement: Bottom Center
        c.setFillColor(colors.black)
        c.setFont(FONT_SERIF, 9)
        # We place it very low, inside the solution box if it exists, or just at bottom
        c.drawCentredString(PAGE_WIDTH / 2, 5 * mm, str(page_idx + 1))

        c.showPage()

    c.save()
    print(f"✓ PDF saved to {PDF_FILENAME}")

if __name__ == "__main__":
    generate_pdf(num_puzzles=6, width=10, height=12)