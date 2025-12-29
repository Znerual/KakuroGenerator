#include "kakuro_cpp.h"
#include <algorithm>
#include <queue>
#include <iostream>

namespace kakuro {

CSPSolver::CSPSolver(std::shared_ptr<KakuroBoard> b) 
    : board(b), rng(std::random_device{}()) {}

bool CSPSolver::generate_puzzle(const std::string& difficulty) {
    const int max_retries = 80;
    
    LOG_DEBUG("Starting puzzle generation. Difficulty: " << difficulty);

    for (int attempt = 0; attempt < max_retries; attempt++) {
        // Regenerate topology periodically
        if (attempt % 5 == 0) {
            LOG_DEBUG("Attempt " << attempt << ": Regenerating topology");
            double d = 0.60;
            if (difficulty == "very_easy") d = 0.50;
            else if (difficulty == "easy") d = 0.55;
            else if (difficulty == "hard") d = 0.65;
            
            board->generate_topology(d);
        }
        
        // Safety check
        if (board->white_cells.size() < 4) {
            LOG_DEBUG("Attempt " << attempt << ": Too few white cells (" << board->white_cells.size() << ")");
            continue;
        }
        
        // Fill grid with numbers
        board->reset_values();
        
        if (!solve_fill(difficulty)) {
            if (attempt % 10 == 0) LOG_DEBUG("Attempt " << attempt << ": Failed to fill grid");
            continue;
        }
        
        // Calculate clues
        calculate_clues();
        
        // Check uniqueness
        LOG_DEBUG("Attempt " << attempt << ": Checking uniqueness...");
        auto [unique, alt_solution] = check_uniqueness();
        
        if (unique) {
            LOG_DEBUG("Success! Unique puzzle generated on attempt " << attempt);
            return true;
        }
        
        // Try to repair
        if (alt_solution.has_value()) {
            LOG_DEBUG("Attempt " << attempt << ": Ambiguous. Trying repair...");
            bool repaired = repair_ambiguity_safely(alt_solution.value());
            
            if (!repaired) {
                LOG_DEBUG("Attempt " << attempt << ": Repair failed. Forcing regen.");
                // Force regeneration
                double d = 0.60;
                if (difficulty == "very_easy") d = 0.50;
                else if (difficulty == "easy") d = 0.55;
                else if (difficulty == "hard") d = 0.65;
                
                board->generate_topology(d);
            } else {
                LOG_DEBUG("Attempt " << attempt << ": Repair successful!");
                // You might want to re-check uniqueness here or return true depending on logic
                // For now assuming repair makes it unique or we retry loop
            }
        }
    }
    
    LOG_DEBUG("Failed to generate puzzle after max retries");
    return false;
}

bool CSPSolver::solve_fill(const std::string& difficulty, int max_nodes) {
    std::unordered_map<Cell*, int> assignment;
    int node_count = 0;
    
    // Difficulty weights for numbers 1-9
    std::vector<int> domain_weights;
    
    if (difficulty == "very_easy") {
        domain_weights = {20, 15, 5, 1, 1, 1, 5, 15, 20};
    } else if (difficulty == "easy") {
        domain_weights = {10, 8, 6, 2, 1, 2, 6, 8, 10};
    } else if (difficulty == "medium") {
        domain_weights = {5, 5, 5, 5, 5, 5, 5, 5, 5};
    } else if (difficulty == "hard") {
        domain_weights = {1, 2, 5, 10, 10, 10, 5, 2, 1};
    } else {
        domain_weights = {5, 5, 5, 5, 5, 5, 5, 5, 5};
    }
    
    return backtrack_fill(assignment, node_count, max_nodes, domain_weights);
}

bool CSPSolver::backtrack_fill(std::unordered_map<Cell*, int>& assignment,
                                int& node_count, int max_nodes,
                                const std::vector<int>& weights) {
    if (node_count > max_nodes) {
        return false;
    }
    node_count++;
    
    // Find unassigned cells
    std::vector<Cell*> unassigned;
    unassigned.reserve(board->white_cells.size());
    for (Cell* c : board->white_cells) {
        if (assignment.find(c) == assignment.end()) {
            unassigned.push_back(c);
        }
    }
    
    if (unassigned.empty()) {
        // Apply assignment to board
        for (auto& [cell, val] : assignment) {
            cell->value = val;
        }
        return true;
    }
    
    // MRV: Select most constrained variable
    Cell* var = nullptr;
    int max_neighbors = -1;
    
    for (Cell* c : unassigned) {
        int n = count_neighbors_filled(c, assignment);
        if (n > max_neighbors) {
            max_neighbors = n;
            var = c;
        }
    }
    
    // Pre-calculate random scores so they don't change during sort
    std::vector<std::pair<int, double>> domain;
    domain.reserve(9);
    
    std::uniform_real_distribution<> dist(0.01, 1.0);
    
    for (int i = 0; i < 9; i++) {
        // weights[i] is int, multiply by random double
        double score = static_cast<double>(weights[i]) * dist(rng);
        domain.push_back({i + 1, score});
    }
    
    // Sort descending by score (Safe: score is constant for this call)
    std::sort(domain.begin(), domain.end(),
        [](const std::pair<int, double>& a, const std::pair<int, double>& b) {
            return a.second > b.second;
        });
    
    for (const auto& pair : domain) {
        int val = pair.first;
        if (is_consistent_number(var, val, assignment)) {
            assignment[var] = val;
            if (backtrack_fill(assignment, node_count, max_nodes, weights)) {
                return true;
            }
            assignment.erase(var);
        }
    }
    
    return false;
}

int CSPSolver::count_neighbors_filled(Cell* cell, 
                                      const std::unordered_map<Cell*, int>& assignment) {
    int count = 0;
    
    if (cell->sector_h && !cell->sector_h->empty()) {
        for (Cell* n : *(cell->sector_h)) {
            if (assignment.find(n) != assignment.end()) {
                count++;
            }
        }
    }
    
    if (cell->sector_v && !cell->sector_v->empty()) {
        for (Cell* n : *(cell->sector_v)) {
            if (assignment.find(n) != assignment.end()) {
                count++;
            }
        }
    }
    
    return count;
}

bool CSPSolver::is_consistent_number(Cell* var, int value,
                                     const std::unordered_map<Cell*, int>& assignment) {
    // Check horizontal sector
    if (var->sector_h && !var->sector_h->empty()) {
        for (Cell* cell : *(var->sector_h)) {
            auto it = assignment.find(cell);
            if (it != assignment.end() && it->second == value) {
                return false;
            }
        }
    }
    
    // Check vertical sector
    if (var->sector_v && !var->sector_v->empty()) {
        for (Cell* cell : *(var->sector_v)) {
            auto it = assignment.find(cell);
            if (it != assignment.end() && it->second == value) {
                return false;
            }
        }
    }
    
    return true;
}

void CSPSolver::calculate_clues() {
    // Horizontal sectors
    for (auto& sector : board->sectors_h) {
        int sum = 0;
        for (Cell* c : sector) {
            if (c->value.has_value()) {
                sum += c->value.value();
            }
        }
        
        Cell* first = sector[0];
        if (first->c > 0) {
            board->grid[first->r][first->c - 1].clue_h = sum;
        }
    }
    
    // Vertical sectors
    for (auto& sector : board->sectors_v) {
        int sum = 0;
        for (Cell* c : sector) {
            if (c->value.has_value()) {
                sum += c->value.value();
            }
        }
        
        Cell* first = sector[0];
        if (first->r > 0) {
            board->grid[first->r - 1][first->c].clue_v = sum;
        }
    }
}

std::pair<bool, std::optional<std::unordered_map<std::pair<int, int>, int, PairHash>>> 
CSPSolver::check_uniqueness(int max_nodes) {
    // Save current solution
    std::unordered_map<std::pair<int, int>, int, PairHash> current_solution;
    for (Cell* c : board->white_cells) {
        if (c->value.has_value()) {
            current_solution[{c->r, c->c}] = c->value.value();
        }
    }
    
    // Clear board
    for (Cell* c : board->white_cells) {
        c->value = std::nullopt;
    }
    
    // Search for alternative solution
    std::vector<std::unordered_map<std::pair<int, int>, int, PairHash>> found_solutions;
    int node_count = 0;
    solve_for_uniqueness(found_solutions, current_solution, node_count, max_nodes);
    
    // Restore original solution
    for (Cell* c : board->white_cells) {
        c->value = current_solution[{c->r, c->c}];
    }
    
    if (found_solutions.empty()) {
        return {true, std::nullopt};
    }
    
    return {false, found_solutions[0]};
}

void CSPSolver::solve_for_uniqueness(
    std::vector<std::unordered_map<std::pair<int, int>, int, PairHash>>& found_solutions,
    const std::unordered_map<std::pair<int, int>, int, PairHash>& avoid_sol,
    int& node_count, int max_nodes) {
    
    if (!found_solutions.empty()) return;
    if (node_count > max_nodes) return;
    node_count++;
    
    // Find unassigned
    std::vector<Cell*> unassigned;
    for (Cell* c : board->white_cells) {
        if (!c->value.has_value()) {
            unassigned.push_back(c);
        }
    }
    
    if (unassigned.empty()) {
        // Check if different from original
        bool is_diff = false;
        std::unordered_map<std::pair<int, int>, int, PairHash> current_sol;
        
        for (Cell* c : board->white_cells) {
            current_sol[{c->r, c->c}] = c->value.value();
            if (avoid_sol.at({c->r, c->c}) != c->value.value()) {
                is_diff = true;
            }
        }
        
        if (is_diff) {
            found_solutions.push_back(current_sol);
        }
        return;
    }
    
    // MRV
    Cell* var = *std::min_element(unassigned.begin(), unassigned.end(),
        [this](Cell* a, Cell* b) {
            return get_domain_size(a) < get_domain_size(b);
        });
    
    for (int val = 1; val <= 9; val++) {
        if (is_valid_move(var, val)) {
            var->value = val;
            solve_for_uniqueness(found_solutions, avoid_sol, node_count, max_nodes);
            if (!found_solutions.empty()) return;
            var->value = std::nullopt;
        }
    }
}

int CSPSolver::get_domain_size(Cell* cell) {
    int count = 0;
    for (int v = 1; v <= 9; v++) {
        if (is_valid_move(cell, v)) {
            count++;
        }
    }
    return count;
}

bool CSPSolver::is_valid_move(Cell* cell, int val) {
    // Check horizontal sector
    if (cell->sector_h && !cell->sector_h->empty()) {
        int curr_sum = val;
        int filled = 1;
        
        for (Cell* peer : *(cell->sector_h)) {
            if (peer->value.has_value()) {
                if (peer->value.value() == val) return false;
                curr_sum += peer->value.value();
                filled++;
            }
        }
        
        Cell* first = (*(cell->sector_h))[0];
        if (first->c > 0) {
            auto clue = board->grid[first->r][first->c - 1].clue_h;
            if (clue.has_value()) {
                if (curr_sum > clue.value()) return false;
                if (filled == (int)cell->sector_h->size() && 
                    curr_sum != clue.value()) return false;
            }
        }
    }
    
    // Check vertical sector
    if (cell->sector_v && !cell->sector_v->empty()) {
        int curr_sum = val;
        int filled = 1;
        
        for (Cell* peer : *(cell->sector_v)) {
            if (peer->value.has_value()) {
                if (peer->value.value() == val) return false;
                curr_sum += peer->value.value();
                filled++;
            }
        }
        
        Cell* first = (*(cell->sector_v))[0];
        if (first->r > 0) {
            auto clue = board->grid[first->r - 1][first->c].clue_v;
            if (clue.has_value()) {
                if (curr_sum > clue.value()) return false;
                if (filled == (int)cell->sector_v->size() && 
                    curr_sum != clue.value()) return false;
            }
        }
    }
    
    return true;
}

bool CSPSolver::repair_ambiguity_safely(
    const std::unordered_map<std::pair<int, int>, int, PairHash>& alt_sol) {
    
    // Find different cells
    std::vector<Cell*> diff_cells;
    for (Cell* c : board->white_cells) {
        if (c->value.has_value()) {
            auto it = alt_sol.find({c->r, c->c});
            if (it != alt_sol.end() && it->second != c->value.value()) {
                diff_cells.push_back(c);
            }
        }
    }
    
    if (diff_cells.empty()) return false;
    
    // Sort by distance from center
    std::sort(diff_cells.begin(), diff_cells.end(),
        [this](Cell* a, Cell* b) {
            int dist_a = std::abs(a->r - board->height/2) + 
                        std::abs(a->c - board->width/2);
            int dist_b = std::abs(b->r - board->height/2) + 
                        std::abs(b->c - board->width/2);
            return dist_a < dist_b;
        });
    
    // Current white coordinates
    std::unordered_set<std::pair<int, int>, PairHash> white_coords;
    for (Cell* c : board->white_cells) {
        white_coords.insert({c->r, c->c});
    }
    
    for (Cell* target : diff_cells) {
        // Simulate removal
        std::unordered_set<std::pair<int, int>, PairHash> removed;
        removed.insert({target->r, target->c});
        
        int sym_r = board->height - 1 - target->r;
        int sym_c = board->width - 1 - target->c;
        if (white_coords.count({sym_r, sym_c})) {
            removed.insert({sym_r, sym_c});
        }
        
        std::unordered_set<std::pair<int, int>, PairHash> remaining_coords;
        for (auto coord : white_coords) {
            if (!removed.count(coord)) {
                remaining_coords.insert(coord);
            }
        }
        
        if (remaining_coords.size() < 0.8 * white_coords.size()) {
            continue;
        }
        
        // Check connectivity
        if (is_connected(remaining_coords)) {
            board->set_block(target->r, target->c);
            board->set_block(sym_r, sym_c);
            board->stabilize_grid();
            return true;
        }
    }
    
    return false;
}

bool CSPSolver::is_connected(
    const std::unordered_set<std::pair<int, int>, PairHash>& coords) {
    
    if (coords.empty()) return false;
    
    auto start = *coords.begin();
    std::queue<std::pair<int, int>> q;
    q.push(start);
    
    std::unordered_set<std::pair<int, int>, PairHash> visited;
    visited.insert(start);
    
    int count = 0;
    std::vector<std::pair<int, int>> dirs = {{0,1}, {0,-1}, {1,0}, {-1,0}};
    
    while (!q.empty()) {
        auto [r, c] = q.front();
        q.pop();
        count++;
        
        for (auto [dr, dc] : dirs) {
            std::pair<int, int> next = {r + dr, c + dc};
            if (coords.count(next) && !visited.count(next)) {
                visited.insert(next);
                q.push(next);
            }
        }
    }
    
    return count == (int)coords.size();
}

} // namespace kakuro