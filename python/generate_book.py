import sys
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A5
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
import io


# --- CONFIGURATION ---
PDF_FILENAME = "kakuro_book_design.pdf"
PAGE_WIDTH, PAGE_HEIGHT = A5
MARGIN_X = 10 * mm
MARGIN_Y = 10 * mm

# Layout Constants
DIVIDER_Y = 55 * mm  # Height of the solution footer area
SOLUTION_OFFSET = 0
DIFFICULTY = "medium"

# Fonts - "Classic Book" style
FONT_TITLE = "Times-Bold"      # For "Puzzle #1"
FONT_SERIF = "Times-Roman"     # For general text
FONT_ITALIC = "Times-Italic"   # For "Difficulty" label
FONT_SANS = "Helvetica-Bold"   # For grid numbers (Clarity)
FONT_HAND = "Helvetica"        # For solution numbers

def draw_qr_code(c, x, y, size, data):
    """Draws a QR code at the specified location."""
    qr_code = qr.QrCodeWidget(data)
    qr_code.barWidth = size
    qr_code.barHeight = size
    qr_code.qrVersion = 1  # Adjust version if data requires it, 1 is smallest
    
    # Create a drawing to hold the QR code
    d = Drawing(size, size)
    d.add(qr_code)
    
    # Draw it on the canvas
    renderPDF.draw(d, c, x, y)

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
       [●] MEDIUM      (Bold, Uppercase with colored circle)
       ♦ ♦ ♢           (Visual Meter)
    """
    # 1. Map difficulty to data
    levels = {
        "very_easy": {"num": 1, "label": "VERY EASY", "color": colors.Color(0.2, 0.8, 0.2)}, # Light Green
        "easy": {"num": 2, "label": "EASY", "color": colors.Color(0.1, 0.6, 0.1)},       # Green
        "medium": {"num": 3, "label": "MEDIUM", "color": colors.Color(0.9, 0.7, 0.1)},     # Yellow/Orange
        "hard": {"num": 4, "label": "HARD", "color": colors.Color(0.8, 0.1, 0.1)}          # Red
    }
    
    config = levels.get(difficulty_name.lower(), levels["medium"])
    level_num = config["num"]
    display_name = config["label"]
    badge_color = config["color"]
    
    # 2. Draw "Difficulty Level" Label
    c.setFillColor(colors.black)
    c.setFont(FONT_ITALIC, 8)
    try:
        score_val = float(difficulty_score)
        score_text = f"Rating: {score_val:.1f}"
    except:
        score_text = ""
        
    c.drawRightString(right_x, top_y, score_text)
    
    # 3. Draw Level Name (MEDIUM) and Colored Badge
    c.setFont(FONT_TITLE, 14)
    # Move down by 14pts
    
    name_w = c.stringWidth(display_name, FONT_TITLE, 14)
    
    # Draw Badge Circle
    circle_radius = 2.5 * mm
    circle_x = right_x - name_w - 4 * mm - circle_radius
    circle_y = top_y - 14 + 4 # Center with text height roughly
    
    c.setFillColor(badge_color)
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.5)
    c.circle(circle_x, circle_y, circle_radius, fill=1, stroke=1)
    
    # Draw the Text
    c.setFillColor(colors.black)
    c.drawRightString(right_x, top_y - 14, display_name)
    
    # 4. Draw Visual Diamonds
    diamond_size = 4 * mm
    spacing = 1 * mm
    total_width = (4 * diamond_size) + (3 * spacing) 
    
    start_x = right_x - total_width + (diamond_size/2)
    diamond_y = top_y - 24 # Below the text
    
    # Draw 4 indicators
    for i in range(1, 5):
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
            clue_h = int(cell.get('clue_h', 0))
            clue_v = int(cell.get('clue_v', 0))
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
            
            clue_h = int(cell.get('clue_h', 0))
            clue_v = int(cell.get('clue_v', 0))
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

def draw_puzzle_on_page(c, p_data, difficulty_score, puzzle_num, base_url, page_width=A5[0], page_height=A5[1]):
    """Draws a single puzzle and its solution footer on a canvas of given size."""
    # --- 1. HEADER ---
    diff_name = p_data.get('difficulty', 'medium')
    # Draw difficulty badge
    draw_difficulty_badge(c, page_width - 2 * MARGIN_X, page_height - MARGIN_Y, diff_name, f"{difficulty_score}")
    
    # Title
    title_text = f"PUZZLE  {puzzle_num}"
    c.setFont(FONT_TITLE, 22)
    title_w = c.stringWidth(title_text, FONT_TITLE, 22)
    box_w = title_w + 10 * mm
    box_h = 14 * mm
    box_x = MARGIN_X
    box_y = page_height - MARGIN_Y - box_h - 2 * mm
    
    c.setFillColor(colors.black)
    c.rect(box_x, box_y, box_w, box_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.drawCentredString(box_x + box_w / 2, box_y + 4 * mm, title_text)

    # --- 2. MAIN PUZZLE ---
    area_top_y = box_y - 10 * mm
    area_bottom_y = DIVIDER_Y + 5 * mm
    area_w = page_width - (2 * MARGIN_X)
    area_h = area_top_y - area_bottom_y
    
    cell_size = calculate_optimal_cell_size(p_data, area_w, area_h)
    grid_cols = len(p_data['grid'][0])
    grid_rows = len(p_data['grid'])
    board_w = grid_cols * cell_size
    board_h = grid_rows * cell_size
    
    px_offset = MARGIN_X + (area_w - board_w) / 2
    py_offset = area_bottom_y + (area_h - board_h) / 2 + board_h
    
    draw_board(c, p_data, px_offset, py_offset, cell_size, show_solution=False)

    # --- 3. SOLUTION FOOTER ---
    footer_h = DIVIDER_Y
    footer_y = 0
    
    c.setFillColor(colors.Color(0.95, 0.95, 0.95))
    c.rect(0, footer_y, page_width, footer_h, fill=1, stroke=0)
    
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(0, footer_y + footer_h, page_width, footer_y + footer_h)
    
    # Text
    c.setFillColor(colors.black)
    c.setFont(FONT_TITLE, 14)
    text_y_center = footer_y + (footer_h / 2)
    
    c.drawString(MARGIN_X + 5*mm, text_y_center + 10, "SOLUTION")
    c.setFont(FONT_SERIF, 11)
    c.drawString(MARGIN_X + 5*mm, text_y_center - 5, f"Puzzle #{puzzle_num}")
    
    c.setFont("Courier-Bold", 10)
    pid = str(p_data.get('id', 'N/A'))
    short_id = p_data.get('short_id', pid[:8] if len(pid) > 8 else pid)
    c.drawString(MARGIN_X + 5*mm, text_y_center - 28, f"CODE: {short_id}")

    # QR Code
    qr_size = 35 * mm
    qr_x = (page_width - qr_size) / 2
    qr_y = footer_y + (footer_h - qr_size) / 2 + 5 * mm
    solution_url = f"{base_url}/?solution_id={short_id}"
    draw_qr_code(c, qr_x, qr_y, qr_size, solution_url)
    
    c.setFillColor(colors.black)
    c.setFont(FONT_SANS, 8)
    c.drawCentredString(page_width / 2, qr_y - 4*mm, "Scan to verify & rate")
    c.setFont(FONT_SANS, 6)
    c.drawCentredString(page_width / 2, qr_y - 7*mm, f"Or visit: {base_url}/?solution_id={short_id}")

    # Page/Puzzle Number
    c.setFillColor(colors.black)
    c.setFont(FONT_SERIF, 9)
    c.drawCentredString(page_width / 2, 5 * mm, str(puzzle_num))


def generate_pdf(puzzles, file_obj=None, base_url="http://localhost:8000", puzzles_per_page=1):
    """
    Generates a PDF book from a list of puzzle dictionaries.
    """
    from reportlab.lib.pagesizes import A4, A5
    
    output_dest = file_obj if file_obj else PDF_FILENAME
    
    if puzzles_per_page == 2:
        effective_page_size = A4
    else:
        effective_page_size = A5
        
    c = canvas.Canvas(output_dest, pagesize=effective_page_size)
    c.setTitle("Kakuro Puzzle Book")
    
    PAGE_W, PAGE_H = effective_page_size
    A5_W, A5_H = A5
    
    processed_puzzles = []
    for p in puzzles:
        score = p.get('difficulty_score', p.get('difficulty', 'Unknown'))
        if 'id' not in p or not p['id']:
             p['id'] = "MISSING_ID"
        processed_puzzles.append((p, score))

    num_puzzles = len(processed_puzzles)
    
    if puzzles_per_page == 1:
        for i, (p_data, score) in enumerate(processed_puzzles):
            draw_puzzle_on_page(c, p_data, score, i + 1, base_url, A5_W, A5_H)
            c.showPage()
    else:
        # 2 puzzles per page (A4 Portrait)
        # Each A5 Portrait is rotated 90 degrees to fill the A4 page.
        # Top puzzle fills top half (210 wide x 148.5 high).
        # Bottom puzzle fills bottom half (210 wide x 148.5 high).
        
        for i in range(0, num_puzzles, 2):
            # Top Puzzle
            p1_data, s1 = processed_puzzles[i]
            c.saveState()
            c.translate(0, PAGE_H) # Move to top-left
            c.rotate(-90)           # Rotate 90 deg clockwise
            # Now X is DOWN (A4 height), Y is RIGHT (A4 width)
            # Area is width: 148.5 (half A4 height), height: 210 (A4 width)
            draw_puzzle_on_page(c, p1_data, s1, i + 1, base_url, PAGE_H / 2, PAGE_W)
            c.restoreState()
            
            # Bottom Puzzle
            if i + 1 < num_puzzles:
                p2_data, s2 = processed_puzzles[i+1]
                c.saveState()
                c.translate(0, PAGE_H / 2) # Move to middle-left
                c.rotate(-90)
                draw_puzzle_on_page(c, p2_data, s2, i + 2, base_url, PAGE_H / 2, PAGE_W)
                c.restoreState()
            
            c.showPage()


    c.save()
    if not file_obj:
        print(f"✓ PDF saved to {PDF_FILENAME}")
    
    return puzzles

    return puzzles

if __name__ == "__main__":
    print("This module is intended to be imported. Run backend/generate_book.py to test.")