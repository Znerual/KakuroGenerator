#include "kakuro_cpp.h"
#include <algorithm>
#include <queue>
#include <iostream>
#include <ctime>

namespace kakuro {

KakuroBoard::KakuroBoard(int w, int h) 
    : width(w), height(h), rng(std::random_device{}()) {
    // Initialize grid
    grid.resize(height);
    for (int r = 0; r < height; r++) {
        grid[r].reserve(width);
        for (int c = 0; c < width; c++) {
            grid[r].emplace_back(r, c, CellType::WHITE);
        }
    }
}

Cell* KakuroBoard::get_cell(int r, int c) {
    if (r >= 0 && r < height && c >= 0 && c < width) {
        return &grid[r][c];
    }
    return nullptr;
}

void KakuroBoard::reset_values() {
    LOG_DEBUG("Resetting values");
    for (int r = 0; r < height; r++) {
        for (int c = 0; c < width; c++) {
            grid[r][c].value = std::nullopt;
            grid[r][c].clue_h = std::nullopt;
            grid[r][c].clue_v = std::nullopt;
        }
    }
    LOG_DEBUG("Values reset");
}

void KakuroBoard::set_block(int r, int c) {
    Cell* cell = get_cell(r, c);
    if (cell && cell->type != CellType::BLOCK) {
        cell->type = CellType::BLOCK;
        cell->value = std::nullopt;
    }
}

void KakuroBoard::set_white(int r, int c) {
    Cell* cell = get_cell(r, c);
    if (cell) {
        cell->type = CellType::WHITE;
    }
}

void KakuroBoard::generate_topology(double density, int max_sector_length) {
    const int MAX_RETRIES = 20;
    
    for (int attempt = 0; attempt < MAX_RETRIES; attempt++) {

        white_cells.clear();
        sectors_h.clear(); // Clear sectors explicitly to prevent pointer invalidation issues
        sectors_v.clear();

        // 1. Clear Grid (All Block)
        for (int r = 0; r < height; r++) {
            for (int c = 0; c < width; c++) {
                grid[r][c].type = CellType::BLOCK;
                grid[r][c].value = std::nullopt;
                grid[r][c].clue_h = std::nullopt;
                grid[r][c].clue_v = std::nullopt;
                grid[r][c].sector_h = nullptr;
                grid[r][c].sector_v = nullptr;
            }
        }
        
        // 2. Robust Seed
        if (!place_random_seed()) {
            continue;
        }
        
        // 3. Growth Phase
        grow_lattice(density, max_sector_length);
        
        // 4. Filters & Stabilization
        break_large_patches(3);
        stabilize_grid();
        
        // 5. Validation
        int min_cells = std::max(5, (int)(width * height * 0.15));
        if ((int)white_cells.size() >= min_cells) {
            LOG_DEBUG("Topology generated on attempt " << attempt);
            return;
        }
    }
    LOG_DEBUG("Failed to generate topology after retries");
}

bool KakuroBoard::place_random_seed() {
    int margin_x = std::max(1, width / 4);
    int margin_y = std::max(1, height / 4);
    
    int min_r = margin_y, max_r = height - 1 - margin_y;
    int min_c = margin_x, max_c = width - 1 - margin_x;
    
    if (min_r >= max_r) { min_r = 1; max_r = height - 2; }
    if (min_c >= max_c) { min_c = 1; max_c = width - 2; }
    
    std::uniform_int_distribution<> dist_r(min_r, max_r);
    std::uniform_int_distribution<> dist_c(min_c, max_c);
    
    for (int i = 0; i < 20; i++) {
        int r = dist_r(rng);
        int c = dist_c(rng);
        
        if (r - 1 > 0 && r + 1 < height - 1 && c - 1 > 0 && c + 1 < width - 1) {
            // Place Cross
            std::vector<std::pair<int, int>> coords = {
                {r, c}, {r, c-1}, {r, c+1}, {r-1, c}, {r+1, c}
            };
            
            for (auto [cr, cc] : coords) {
                set_white(cr, cc);
                set_white(height - 1 - cr, width - 1 - cc);
            }
            
            collect_white_cells();
            return true;
        }
    }
    
    return false;
}

void KakuroBoard::grow_lattice(double density, int max_sector_length) {
    int target_white = (int)((width - 2) * (height - 2) * density);
    int current_white = white_cells.size();
    
    int attempts = 0;
    const int max_attempts = 2000;
    
    std::uniform_int_distribution<> len_dist(2, max_sector_length);
    std::uniform_int_distribution<> bool_dist(0, 1);
    
    while (current_white < target_white && attempts < max_attempts) {
        if (white_cells.empty()) break;
        
        // Pick random white cell
        std::uniform_int_distribution<> cell_dist(0, white_cells.size() - 1);
        Cell* source = white_cells[cell_dist(rng)];
        int r = source->r;
        int c = source->c;
        
        // Determine orientation
        bool has_h = (get_cell(r, c-1) && get_cell(r, c-1)->type == CellType::WHITE) ||
                     (get_cell(r, c+1) && get_cell(r, c+1)->type == CellType::WHITE);
        bool has_v = (get_cell(r-1, c) && get_cell(r-1, c)->type == CellType::WHITE) ||
                     (get_cell(r+1, c) && get_cell(r+1, c)->type == CellType::WHITE);
        
        bool grow_vert;
        if (has_h && has_v) grow_vert = bool_dist(rng);
        else if (has_h) grow_vert = true;
        else if (has_v) grow_vert = false;
        else grow_vert = bool_dist(rng);
        
        int new_len = len_dist(rng);
        
        // Shuffle shifts
        std::vector<int> shifts(new_len);
        for (int i = 0; i < new_len; i++) shifts[i] = i;
        std::shuffle(shifts.begin(), shifts.end(), rng);
        
        bool placed = false;
        for (int shift : shifts) {
            std::vector<std::pair<int, int>> cells_indices;
            bool possible = true;
            
            for (int k = 0; k < new_len; k++) {
                int idx = k - shift;
                int nr = grow_vert ? r + idx : r;
                int nc = grow_vert ? c : c + idx;
                
                if (nr < 1 || nr >= height - 1 || nc < 1 || nc >= width - 1) {
                    possible = false;
                    break;
                }
                cells_indices.push_back({nr, nc});
            }
            
            if (possible) {
                bool added_new = false;
                for (auto [cr, cc] : cells_indices) {
                    if (grid[cr][cc].type == CellType::BLOCK) {
                        set_white(cr, cc);
                        set_white(height - 1 - cr, width - 1 - cc);
                        added_new = true;
                    }
                }
                
                if (added_new) {
                    placed = true;
                    break;
                }
            }
        }
        
        if (placed) {
            collect_white_cells();
            current_white = white_cells.size();
            attempts = 0;
        } else {
            attempts++;
        }
    }
}

void KakuroBoard::break_large_patches(int size) {
    std::uniform_int_distribution<> bool_dist(0, 1);
    
    for (int iteration = 0; iteration < 50; iteration++) {
        bool found = false;
        
        for (int r = 1; r < height - size && !found; r++) {
            for (int c = 1; c < width - size && !found; c++) {
                // Check for size x size white patch
                bool is_patch = true;
                std::vector<Cell*> patch_cells;
                
                for (int ir = 0; ir < size && is_patch; ir++) {
                    for (int ic = 0; ic < size && is_patch; ic++) {
                        Cell* cell = &grid[r + ir][c + ic];
                        patch_cells.push_back(cell);
                        if (cell->type != CellType::WHITE) {
                            is_patch = false;
                        }
                    }
                }
                
                if (is_patch) {
                    found = true;
                    
                    // Find candidates touching a block
                    std::vector<Cell*> candidates;
                    for (Cell* cell : patch_cells) {
                        bool has_block_neighbor = false;
                        std::vector<std::pair<int, int>> dirs = {{0,1}, {0,-1}, {1,0}, {-1,0}};
                        
                        for (auto [dr, dc] : dirs) {
                            Cell* n = get_cell(cell->r + dr, cell->c + dc);
                            if (n && n->type == CellType::BLOCK) {
                                has_block_neighbor = true;
                                break;
                            }
                        }
                        
                        if (has_block_neighbor) {
                            candidates.push_back(cell);
                        }
                    }
                    
                    Cell* target;
                    if (!candidates.empty()) {
                        std::uniform_int_distribution<> dist(0, candidates.size() - 1);
                        target = candidates[dist(rng)];
                    } else {
                        std::uniform_int_distribution<> dist(0, patch_cells.size() - 1);
                        target = patch_cells[dist(rng)];
                    }
                    
                    set_block(target->r, target->c);
                    set_block(height - 1 - target->r, width - 1 - target->c);
                }
            }
        }
        
        if (!found) break;
    }
}

void KakuroBoard::stabilize_grid() {
    bool changed = true;
    int iterations = 0;
    const int max_stabilization_loops = 15;
    
    while (changed && iterations < max_stabilization_loops) {
        changed = false;
        
        if (fix_invalid_runs()) {
            changed = true;
        }
        
        if (ensure_connectivity()) {
            changed = true;
        }
        
        iterations++;
    }
    
    collect_white_cells();
    identify_sectors();
}

bool KakuroBoard::fix_invalid_runs() {
    bool changed = false;
    
    // Horizontal
    for (int r = 0; r < height; r++) {
        int c = 0;
        while (c < width) {
            if (grid[r][c].type == CellType::WHITE) {
                int start = c;
                int length = 0;
                while (c < width && grid[r][c].type == CellType::WHITE) {
                    length++;
                    c++;
                }
                
                if (length == 1) {
                    set_block(r, start);
                    set_block(height - 1 - r, width - 1 - start);
                    changed = true;
                } else if (length > 9) {
                    int mid = start + length / 2;
                    set_block(r, mid);
                    set_block(height - 1 - r, width - 1 - mid);
                    changed = true;
                }
            } else {
                c++;
            }
        }
    }
    
    // Vertical
    for (int c = 0; c < width; c++) {
        int r = 0;
        while (r < height) {
            if (grid[r][c].type == CellType::WHITE) {
                int start = r;
                int length = 0;
                while (r < height && grid[r][c].type == CellType::WHITE) {
                    length++;
                    r++;
                }
                
                if (length == 1) {
                    set_block(start, c);
                    set_block(height - 1 - start, width - 1 - c);
                    changed = true;
                } else if (length > 9) {
                    int mid = start + length / 2;
                    set_block(mid, c);
                    set_block(height - 1 - mid, width - 1 - c);
                    changed = true;
                }
            } else {
                r++;
            }
        }
    }
    
    return changed;
}

void KakuroBoard::block_sym(Cell* cell) {
    set_block(cell->r, cell->c);
    set_block(height - 1 - cell->r, width - 1 - cell->c);
}

bool KakuroBoard::ensure_connectivity() {
    // Find all white cells
    std::vector<std::pair<int, int>> white_cells_coords;
    for (int r = 0; r < height; r++) {
        for (int c = 0; c < width; c++) {
            if (grid[r][c].type == CellType::WHITE) {
                white_cells_coords.push_back({r, c});
            }
        }
    }
    
    if (white_cells_coords.empty()) return false;
    
    std::unordered_set<std::pair<int, int>, PairHash> white_set(
        white_cells_coords.begin(), white_cells_coords.end());
    
    std::vector<std::vector<std::pair<int, int>>> components;
    std::unordered_set<std::pair<int, int>, PairHash> visited;
    
    for (auto start_node : white_cells_coords) {
        if (visited.count(start_node)) continue;
        
        std::vector<std::pair<int, int>> component;
        std::queue<std::pair<int, int>> q;
        q.push(start_node);
        visited.insert(start_node);
        
        while (!q.empty()) {
            auto [r, c] = q.front();
            q.pop();
            component.push_back({r, c});
            
            std::vector<std::pair<int, int>> dirs = {{0,1}, {1,0}, {0,-1}, {-1,0}};
            for (auto [dr, dc] : dirs) {
                std::pair<int, int> next = {r + dr, c + dc};
                if (white_set.count(next) && !visited.count(next)) {
                    visited.insert(next);
                    q.push(next);
                }
            }
        }
        
        components.push_back(component);
    }
    
    if (components.empty()) return false;
    
    // Keep largest component
    auto largest_component = *std::max_element(
        components.begin(), components.end(),
        [](const auto& a, const auto& b) { return a.size() < b.size(); }
    );
    
    std::unordered_set<std::pair<int, int>, PairHash> largest_set(
        largest_component.begin(), largest_component.end());
    
    bool changed = false;
    for (auto [r, c] : white_cells_coords) {
        if (!largest_set.count({r, c})) {
            set_block(r, c);
            set_block(height - 1 - r, width - 1 - c);
            changed = true;
        }
    }
    
    return changed;
}

void KakuroBoard::collect_white_cells() {
    white_cells.clear();
    for (int r = 0; r < height; r++) {
        for (int c = 0; c < width; c++) {
            if (grid[r][c].type == CellType::WHITE) {
                white_cells.push_back(&grid[r][c]);
            }
        }
    }
}

void KakuroBoard::identify_sectors() {
    // Clear old sectors
    sectors_h.clear();
    sectors_v.clear();
    
    // Reset sector links
    for (Cell* cell : white_cells) {
        cell->sector_h = nullptr;
        cell->sector_v = nullptr;
    }
    
    // Horizontal sectors
    for (int r = 0; r < height; r++) {
        std::vector<Cell*> current_sector;
        for (int c = 0; c < width; c++) {
            if (grid[r][c].type == CellType::WHITE) {
                current_sector.push_back(&grid[r][c]);
            } else {
                if (!current_sector.empty()) {
                    sectors_h.push_back(current_sector);
                    for (Cell* cell : current_sector) {
                        cell->sector_h = &sectors_h.back();
                    }
                    current_sector.clear();
                }
            }
        }
        if (!current_sector.empty()) {
            sectors_h.push_back(current_sector);
            for (Cell* cell : current_sector) {
                cell->sector_h = &sectors_h.back();
            }
        }
    }
    
    // Vertical sectors
    for (int c = 0; c < width; c++) {
        std::vector<Cell*> current_sector;
        for (int r = 0; r < height; r++) {
            if (grid[r][c].type == CellType::WHITE) {
                current_sector.push_back(&grid[r][c]);
            } else {
                if (!current_sector.empty()) {
                    sectors_v.push_back(current_sector);
                    for (Cell* cell : current_sector) {
                        cell->sector_v = &sectors_v.back();
                    }
                    current_sector.clear();
                }
            }
        }
        if (!current_sector.empty()) {
            sectors_v.push_back(current_sector);
            for (Cell* cell : current_sector) {
                cell->sector_v = &sectors_v.back();
            }
        }
    }
}

std::vector<std::vector<std::unordered_map<std::string, std::string>>> 
KakuroBoard::to_dict() const {
    std::vector<std::vector<std::unordered_map<std::string, std::string>>> result;
    
    for (int r = 0; r < height; r++) {
        std::vector<std::unordered_map<std::string, std::string>> row;
        for (int c = 0; c < width; c++) {
            const Cell& cell = grid[r][c];
            std::unordered_map<std::string, std::string> cell_dict;
            
            cell_dict["r"] = std::to_string(cell.r);
            cell_dict["c"] = std::to_string(cell.c);
            cell_dict["type"] = (cell.type == CellType::BLOCK) ? "BLOCK" : "WHITE";
            
            if (cell.value.has_value()) {
                cell_dict["value"] = std::to_string(cell.value.value());
            }
            if (cell.clue_h.has_value()) {
                cell_dict["clue_h"] = std::to_string(cell.clue_h.value());
            }
            if (cell.clue_v.has_value()) {
                cell_dict["clue_v"] = std::to_string(cell.clue_v.value());
            }
            
            row.push_back(cell_dict);
        }
        result.push_back(row);
    }
    
    return result;
}

} // namespace kakuro