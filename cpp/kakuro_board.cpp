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
            grid[r].emplace_back(r, c, CellType::BLOCK);
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
    if (r >= 1 && r < height - 1 && c >= 1 && c < width - 1) {
        grid[r][c].type = CellType::WHITE;
    }
}

bool KakuroBoard::generate_topology(double density, int max_sector_length, std::string difficulty) {
    const int MAX_RETRIES = 60;

    // Config based on difficulty
    std::vector<std::pair<int, int>> stamps;
    int num_stamps = 0;
    int max_run_len = 9;
    int min_cells = 12;
    bool island_mode = false;

    if (difficulty == "very_easy") {
        stamps = {{1, 3}, {3, 1}, {1, 4}, {4, 1}, {2, 2}};
        num_stamps = std::uniform_int_distribution<>(6, 12)(rng);
        min_cells = 16;
        max_run_len = 5;
        island_mode = true;
    } else if (difficulty == "easy") {
        stamps = {{1, 3}, {3, 1}, {1, 4}, {4, 1}, {1, 5}, {5, 1}, {1, 6}, {6, 1}, {2,2}, {3, 3}};
        num_stamps = std::uniform_int_distribution<>(8, 15)(rng);
        min_cells = 22;
        max_run_len = 6;
        island_mode = true;
    } else if (difficulty == "medium") {
        island_mode = false;
        max_sector_length = 7;
        min_cells = (int)(width * height * 0.15);
    } else { // Hard
        island_mode = false;
        max_sector_length = 9;
        density = std::min(0.70, density + 0.05);
        min_cells = (int)(width * height * 0.15);
    }
    
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

        bool success = false;
        if (island_mode) {
            success = generate_stamps(stamps, num_stamps);
        } else {
            if (place_random_seed()) {
                grow_lattice(density, max_sector_length);
                collect_white_cells();
                success = !white_cells.empty();
            }
        }
        
        if (!success) continue;

        // Filters & Stabilization
        if (!island_mode) {
            break_large_patches(difficulty == "medium" ? 3 : 4);
            stabilize_grid(false);
        } else {
            slice_long_runs(max_run_len);
            prune_singles();
            break_single_runs();
        }

        collect_white_cells();
        
        // Final Validation
        if ((int)white_cells.size() < min_cells) continue;
        if (!check_connectivity()) continue;
        if (!validate_clue_headers()) continue;
        
        identify_sectors();
        return true;
    }
    LOG_DEBUG("Failed to generate topology after retries");
    return false;
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
    int current_white = (int)white_cells.size();
    
    int attempts = 0;
    const int max_attempts = 2000;
    
    std::uniform_int_distribution<> len_dist(2, max_sector_length);
    std::uniform_int_distribution<> bool_dist(0, 1);
    
    while (current_white < target_white && attempts < max_attempts) {
        if (white_cells.empty()) break;
        
        // Pick random white cell
        std::uniform_int_distribution<> cell_dist(0, (int)white_cells.size() - 1);
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
            current_white = (int)white_cells.size();
            attempts = 0;
        } else {
            attempts++;
        }
    }
}

bool KakuroBoard::generate_stamps(const std::vector<std::pair<int, int>>& shapes, int iterations) {
    int center_r = height / 2;
    int center_c = width / 2;
    
    stamp_rect(center_r, center_c, 2, 2);
    
    int current_iter = 0;
    int failures = 0;
    
    while (current_iter < iterations && failures < 20) {
        collect_white_cells();
        if (white_cells.empty()) return false;
        
        std::uniform_int_distribution<> dist(0, (int)white_cells.size() - 1);
        Cell* anchor = white_cells[dist(rng)];
        
        std::uniform_int_distribution<> shape_dist(0, (int)shapes.size() - 1);
        auto [h, w] = shapes[shape_dist(rng)];
        
        std::uniform_int_distribution<> offset_r_dist(-(h-1), 0);
        std::uniform_int_distribution<> offset_c_dist(-(w-1), 0);
        
        int top_r = anchor->r + offset_r_dist(rng);
        int left_c = anchor->c + offset_c_dist(rng);
        
        // Bounds Check (Strict 1-cell border)
        if (top_r >= 1 && left_c >= 1 && 
            top_r + h < height - 1 && left_c + w < width - 1) {
            
            stamp_rect(top_r, left_c, h, w);
            current_iter++;
        } else {
            failures++;
        }
    }
    collect_white_cells();
    return !white_cells.empty();
}

void KakuroBoard::stamp_rect(int r, int c, int h, int w) {
    for (int i = 0; i < h; i++) {
        for (int j = 0; j < w; j++) {
            set_white(r + i, c + j);
            set_white(height - 1 - (r + i), width - 1 - (c + j));
        }
    }
}

void KakuroBoard::slice_long_runs(int max_len) {
    // Horizontal
    for (int r = 1; r < height - 1; r++) {
        int length = 0;
        int run_start = -1;
        for (int c = 1; c < width; c++) {
            if (grid[r][c].type == CellType::WHITE) {
                if (run_start == -1) run_start = c;
                length++;
            } else {
                if (length > max_len) apply_slice(r, run_start, length, true);
                length = 0;
                run_start = -1;
            }
        }
        if (length > max_len) apply_slice(r, run_start, length, true);
    }
    
    // Vertical
    for (int c = 1; c < width - 1; c++) {
        int length = 0;
        int run_start = -1;
        for (int r = 1; r < height; r++) {
            if (grid[r][c].type == CellType::WHITE) {
                if (run_start == -1) run_start = r;
                length++;
            } else {
                if (length > max_len) apply_slice(c, run_start, length, false);
                length = 0;
                run_start = -1;
            }
        }
        if (length > max_len) apply_slice(c, run_start, length, false);
    }
}

void KakuroBoard::apply_slice(int fixed_idx, int start, int length, bool is_horz) {
    int mid_offset = length / 2;
    int r = is_horz ? fixed_idx : start + mid_offset;
    int c = is_horz ? start + mid_offset : fixed_idx;
    set_block(r, c);
    set_block(height - 1 - r, width - 1 - c);
}

void KakuroBoard::prune_singles() {
    bool changed = true;
    while (changed) {
        changed = false;
        for (int r = 1; r < height - 1; r++) {
            for (int c = 1; c < width - 1; c++) {
                if (grid[r][c].type == CellType::WHITE) {
                    int h_nbs = 0;
                    if (grid[r][c-1].type == CellType::WHITE) h_nbs++;
                    if (grid[r][c+1].type == CellType::WHITE) h_nbs++;
                    
                    int v_nbs = 0;
                    if (grid[r-1][c].type == CellType::WHITE) v_nbs++;
                    if (grid[r+1][c].type == CellType::WHITE) v_nbs++;
                    
                    if (h_nbs == 0 && v_nbs == 0) {
                        set_block(r, c);
                        set_block(height - 1 - r, width - 1 - c);
                        changed = true;
                    }
                }
            }
        }
    }
}

void KakuroBoard::break_single_runs() {
    bool changed = true;
    bool any_change = false;
    while (changed) {
        changed = false;
        for (int r = 1; r < height - 1; r++) {
            for (int c = 1; c < width - 1; c++) {
                if (grid[r][c].type == CellType::WHITE) {
                    // Count horizontal run length (including this cell)
                    int h_len = 1;
                    // Look left
                    int check_c = c - 1;
                    while (check_c >= 0 && grid[r][check_c].type == CellType::WHITE) {
                        h_len++;
                        check_c--;
                    }
                    // Look right
                    check_c = c + 1;
                    while (check_c < width && grid[r][check_c].type == CellType::WHITE) {
                        h_len++;
                        check_c++;
                    }
                    
                    // Count vertical run length (including this cell)
                    int v_len = 1;
                    // Look up
                    int check_r = r - 1;
                    while (check_r >= 0 && grid[check_r][c].type == CellType::WHITE) {
                        v_len++;
                        check_r--;
                    }
                    // Look down
                    check_r = r + 1;
                    while (check_r < height && grid[check_r][c].type == CellType::WHITE) {
                        v_len++;
                        check_r++;
                    }
                    
                    // If this cell is part of a length-1 run in EITHER direction, remove it
                    if (h_len == 1 || v_len == 1) {
                        set_block(r, c);
                        set_block(height - 1 - r, width - 1 - c);
                        changed = true;
                        any_change = true;
                    }
                }
            }
        }
    }
    if (any_change) {
        collect_white_cells();
        identify_sectors();
    }
}
bool KakuroBoard::validate_clue_headers() {
    for (int r = 0; r < height; r++) {
        for (int c = 0; c < width; c++) {
            if (grid[r][c].type == CellType::WHITE) {
                // Horizontal: If first in row or cell to left is NOT white, it must be a block
                if (c == 0 || grid[r][c-1].type != CellType::WHITE) {
                    if (c == 0 || grid[r][c-1].type != CellType::BLOCK) return false;
                }
                // Vertical: If first in col or cell above is NOT white, it must be a block
                if (r == 0 || grid[r-1][c].type != CellType::WHITE) {
                    if (r == 0 || grid[r-1][c].type != CellType::BLOCK) return false;
                }
            }
        }
    }
    return true;
}

bool KakuroBoard::check_connectivity() {
    collect_white_cells();
    if (white_cells.empty()) return false;
    
    std::unordered_set<std::pair<int, int>, PairHash> visited;
    std::queue<Cell*> q;
    
    q.push(white_cells[0]);
    visited.insert({white_cells[0]->r, white_cells[0]->c});
    
    int count = 0;
    while (!q.empty()) {
        Cell* curr = q.front();
        q.pop();
        count++;
        
        int dr[] = {0, 0, 1, -1};
        int dc[] = {1, -1, 0, 0};
        
        for (int i = 0; i < 4; i++) {
            Cell* n = get_cell(curr->r + dr[i], curr->c + dc[i]);
            if (n && n->type == CellType::WHITE) {
                if (visited.find({n->r, n->c}) == visited.end()) {
                    visited.insert({n->r, n->c});
                    q.push(n);
                }
            }
        }
    }
    return count == (int)white_cells.size();
}

int KakuroBoard::count_white_neighbors(Cell* cell) {
    int n = 0;
    int dr[] = {0, 0, 1, -1};
    int dc[] = {1, -1, 0, 0};
    for(int i=0; i<4; ++i) {
        Cell* neighbor = get_cell(cell->r + dr[i], cell->c + dc[i]);
        if(neighbor && neighbor->type == CellType::WHITE) n++;
    }
    return n;
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
                        std::uniform_int_distribution<> dist(0, (int)candidates.size() - 1);
                        target = candidates[dist(rng)];
                    } else {
                        std::uniform_int_distribution<> dist(0, (int)patch_cells.size() - 1);
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

void KakuroBoard::stabilize_grid(bool gentle) {
    bool changed = true;
    int iterations = 0;
    const int max_loops = 15;
    while (changed && iterations < max_loops) {
        changed = false;
        if (gentle) { if(fix_invalid_runs_gentle()) changed = true; }
        else { if(fix_invalid_runs()) changed = true; }
        if (ensure_connectivity()) changed = true;

        break_single_runs(); 
        
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

bool KakuroBoard::fix_invalid_runs_gentle() {
    bool changed = false;
    for (int r = 0; r < height; r++) {
        for (int c = 0; c < width; c++) {
            if (grid[r][c].type != CellType::WHITE) continue;
            bool h_nb = (c>0 && grid[r][c-1].type==CellType::WHITE) || (c<width-1 && grid[r][c+1].type==CellType::WHITE);
            bool v_nb = (r>0 && grid[r-1][c].type==CellType::WHITE) || (r<height-1 && grid[r+1][c].type==CellType::WHITE);
            if (!h_nb && !v_nb) {
                set_block(r, c);
                set_block(height-1-r, width-1-c);
                changed = true;
            }
        }
    }
    // Also split long runs
    if(fix_invalid_runs()) changed = true; // reusing existing logic for long splits
    return changed;
}

void KakuroBoard::block_sym(Cell* cell) {
    set_block(cell->r, cell->c);
    set_block(height - 1 - cell->r, width - 1 - cell->c);
}

bool KakuroBoard::ensure_connectivity() {
    collect_white_cells();
    if(white_cells.empty()) return false;
    std::unordered_set<std::pair<int, int>, PairHash> white_set;
    for(auto c : white_cells) white_set.insert({c->r, c->c});
    
    std::vector<std::vector<std::pair<int, int>>> components;
    std::unordered_set<std::pair<int, int>, PairHash> visited;
    
    for(auto c : white_cells) {
        if(visited.count({c->r, c->c})) continue;
        std::vector<std::pair<int, int>> comp;
        std::queue<std::pair<int, int>> q;
        q.push({c->r, c->c});
        visited.insert({c->r, c->c});
        while(!q.empty()) {
            auto [r, col] = q.front(); q.pop();
            comp.push_back({r, col});
            int dr[] = {0, 0, 1, -1};
            int dc[] = {1, -1, 0, 0};
            for(int i=0; i<4; i++) {
                std::pair<int, int> next = {r+dr[i], col+dc[i]};
                if(white_set.count(next) && !visited.count(next)) {
                    visited.insert(next);
                    q.push(next);
                }
            }
        }
        components.push_back(comp);
    }
    if(components.empty()) return false;
    
    auto largest = *std::max_element(components.begin(), components.end(), 
        [](const auto& a, const auto& b){ return (int)a.size() < (int)b.size(); });
    std::unordered_set<std::pair<int, int>, PairHash> largest_set(largest.begin(), largest.end());
    
    bool changed = false;
    for(auto c : white_cells) {
        if(!largest_set.count({c->r, c->c})) {
            set_block(c->r, c->c);
            set_block(height-1-c->r, width-1-c->c);
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
    // Clear existing shared_ptr lists
    sectors_h.clear(); 
    sectors_v.clear();
    for(auto c : white_cells) { c->sector_h = nullptr; c->sector_v = nullptr; }
    
    // Horizontal
    for(int r = 0; r < height; r++) {
        auto current_sec = std::make_shared<std::vector<Cell*>>();
        for(int c = 0; c < width; c++) {
            if(grid[r][c].type == CellType::WHITE) {
                current_sec->push_back(&grid[r][c]);
            } else {
                if(!current_sec->empty()) {
                    sectors_h.push_back(current_sec);
                    for(auto sc : *current_sec) sc->sector_h = current_sec;
                    current_sec = std::make_shared<std::vector<Cell*>>();
                }
            }
        }
        if(!current_sec->empty()) {
            sectors_h.push_back(current_sec);
            for(auto sc : *current_sec) sc->sector_h = current_sec;
        }
    }
    
    // Vertical (Same logic for sectors_v...)
    for(int c = 0; c < width; c++) {
        auto current_sec = std::make_shared<std::vector<Cell*>>();
        for(int r = 0; r < height; r++) {
            if(grid[r][c].type == CellType::WHITE) {
                current_sec->push_back(&grid[r][c]);
            } else {
                if(!current_sec->empty()) {
                    sectors_v.push_back(current_sec);
                    for(auto sc : *current_sec) sc->sector_v = current_sec;
                    current_sec = std::make_shared<std::vector<Cell*>>();
                }
            }
        }
        if(!current_sec->empty()) {
            sectors_v.push_back(current_sec);
            for(auto sc : *current_sec) sc->sector_v = current_sec;
        }
    }
}

std::vector<std::vector<std::unordered_map<std::string, std::string>>> KakuroBoard::to_dict() const {
    std::vector<std::vector<std::unordered_map<std::string, std::string>>> result;
    for (int r = 0; r < height; r++) {
        std::vector<std::unordered_map<std::string, std::string>> row;
        for (int c = 0; c < width; c++) {
            const Cell& cell = grid[r][c];
            std::unordered_map<std::string, std::string> d;
            d["r"] = std::to_string(cell.r);
            d["c"] = std::to_string(cell.c);
            d["type"] = (cell.type == CellType::BLOCK) ? "BLOCK" : "WHITE";
            if(cell.value) d["value"] = std::to_string(*cell.value);
            if(cell.clue_h) d["clue_h"] = std::to_string(*cell.clue_h);
            if(cell.clue_v) d["clue_v"] = std::to_string(*cell.clue_v);
            row.push_back(d);
        }
        result.push_back(row);
    }
    return result;
}

} // namespace kakuro