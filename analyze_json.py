import json

try:
    with open('debug_response.json', 'r') as f:
        data = json.load(f)
    
    grid = data['grid']
    total_cells = 0
    blocks = 0
    whites = 0
    
    for row in grid:
        for cell in row:
            total_cells += 1
            if cell['type'] == 'BLOCK':
                blocks += 1
            elif cell['type'] == 'WHITE':
                whites += 1
            else:
                print(f"Unknown type: {cell['type']}")

    print(f"Total: {total_cells}")
    print(f"Blocks: {blocks}")
    print(f"Whites: {whites}")
    
except Exception as e:
    print(e)
