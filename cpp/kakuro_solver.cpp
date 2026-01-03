#include "kakuro_cpp.h"
#include <algorithm>
#include <queue>
#include <iostream>
#include <map>
#include <numeric>

namespace kakuro {

CSPSolver::CSPSolver(std::shared_ptr<KakuroBoard> b) 
    : board(b), rng(std::random_device{}()) {}

bool CSPSolver::generate_puzzle(const std::string& difficulty) {
    const int MAX_TOPOLOGY_RETRIES = 20;
    const int MAX_REPAIR_ATTEMPTS = 5;
    const int MAX_VALUE_RETRIES = 5;

    
    LOG_DEBUG("Starting puzzle generation. Difficulty: " << difficulty);

    for (int topo_attempt = 0; topo_attempt < MAX_TOPOLOGY_RETRIES; topo_attempt++) {
        board->generate_topology(0.60, 9, difficulty);

        if (board->white_cells.size() < 12) continue;
        
        // Force synchronization
        board->collect_white_cells();
        board->identify_sectors();

        
        int repair_count = 0;
        while (repair_count < MAX_REPAIR_ATTEMPTS) {
            bool fill_success = false;
            std::unordered_map<std::pair<int, int>, int, PairHash> last_ambiguity;
            std::unordered_map<std::pair<int, int>, int, PairHash> previous_solution_state;
            bool has_last_ambiguity = false;
            bool has_previous_state = false;

            for (int fill_attempt = 0; fill_attempt < MAX_VALUE_RETRIES; fill_attempt++) {
                
                // Logic Fix 1: Generate constraints BEFORE reset
                std::unordered_map<Cell*, int> constraints;
                if (fill_attempt > 1 && has_last_ambiguity && has_previous_state) {
                    auto constraint_map = generate_breaking_constraints(last_ambiguity, previous_solution_state);
                    for(auto& [c, val] : constraint_map) {
                        constraints[c] = val;
                    }
                }

                board->reset_values();

                // Logic Fix 2: Pass ignore_clues=true
                bool success = solve_fill(difficulty, 50000, constraints, true);

                if (success) {
                    fill_success = true;
                    // Store state
                    previous_solution_state.clear();
                    for(Cell* c : board->white_cells) {
                        if(c->value) previous_solution_state[{c->r, c->c}] = *c->value;
                    }
                    has_previous_state = true;
                    break;
                }
            }

            if (!fill_success) break; // discard topology

            calculate_clues();

            // Check Uniqueness (seed logic can be handled by offset)
            auto [unique, alt_sol] = check_uniqueness(10000, 0);
            
            if (unique) {
                // Double check
                auto [unique2, _] = check_uniqueness(10000, 100);
                if (unique2) return true;
            }

            if (alt_sol.has_value()) {
                last_ambiguity = alt_sol.value();
                has_last_ambiguity = true;
                
                // Repair
                if (repair_topology_robust(last_ambiguity)) {
                    // Force complete re-sync
                    board->collect_white_cells();
                    board->identify_sectors();
                    repair_count++;
                    continue; // Loop back to refill
                } else {
                    break; // Repair failed
                }
            } else {
                // Should be unique if alt_sol is empty, but double check logic might have failed
                break; 
            }
        }
    }
    return false;
}

bool CSPSolver::solve_fill(const std::string& difficulty, 
                           int max_nodes,
                           const std::unordered_map<Cell*, int>& initial_constraints,
                           bool ignore_clues) {
    std::unordered_map<Cell*, int> assignment;
    int node_count = 0;
    
    // Apply constraints
    for(auto& [cell, val] : initial_constraints) {
        if(cell->type == CellType::WHITE) {
            if(is_consistent_number(cell, val, assignment, ignore_clues)) {
                assignment[cell] = val;
            } else {
                return false;
            }
        }
    }

    std::vector<int> weights;
    if (difficulty == "very_easy") weights = {20, 15, 5, 1, 1, 1, 5, 15, 20};
    else if (difficulty == "easy") weights = {10, 8, 6, 2, 1, 2, 6, 8, 10};
    else if (difficulty == "hard") weights = {1, 2, 5, 10, 10, 10, 5, 2, 1};
    else weights = {5, 5, 5, 5, 5, 5, 5, 5, 5};
    
    return backtrack_fill(assignment, node_count, max_nodes, weights, ignore_clues);
}


bool CSPSolver::backtrack_fill(std::unordered_map<Cell*, int>& assignment,
                               int& node_count, int max_nodes,
                               const std::vector<int>& weights,
                               bool ignore_clues) {
    if (node_count > max_nodes) return false;
    node_count++;
    
    std::vector<Cell*> unassigned;
    for (Cell* c : board->white_cells) {
        if (assignment.find(c) == assignment.end()) unassigned.push_back(c);
    }
    
    if (unassigned.empty()) {
        for (auto& [cell, val] : assignment) cell->value = val;
        return true;
    }
    
    // MRV
    Cell* var = *std::max_element(unassigned.begin(), unassigned.end(),
        [this, &assignment](Cell* a, Cell* b) {
            return count_neighbors_filled(a, assignment) < count_neighbors_filled(b, assignment);
        });
    
    std::vector<std::pair<int, double>> domain;
    std::uniform_real_distribution<> dist(0.01, 1.0);
    for (int i = 0; i < 9; i++) {
        domain.push_back({i + 1, (double)weights[i] * dist(rng)});
    }
    std::sort(domain.begin(), domain.end(), [](const auto& a, const auto& b){ return a.second > b.second; });
    
    for (auto& p : domain) {
        int val = p.first;
        if (is_consistent_number(var, val, assignment, ignore_clues)) {
            assignment[var] = val;
            if (backtrack_fill(assignment, node_count, max_nodes, weights, ignore_clues)) return true;
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
                                     const std::unordered_map<Cell*, int>& assignment, 
                                     bool ignore_clues) {
    // Horizontal
    if (var->sector_h) {
        int curr_sum = value;
        int filled = 1;
        for (Cell* peer : *var->sector_h) {
            if (assignment.count(peer)) {
                int v = assignment.at(peer);
                if (v == value) return false; // Duplicate check always on
                curr_sum += v;
                filled++;
            }
        }
        if (!ignore_clues) {
            Cell* start = (*var->sector_h)[0];
            if (start->c > 0) {
                auto clue = board->grid[start->r][start->c-1].clue_h;
                if (clue) {
                    if (curr_sum > *clue) return false;
                    if (filled == (int)var->sector_h->size() && curr_sum != *clue) return false;
                }
            }
        }
    }
    // Vertical
    if (var->sector_v) {
        int curr_sum = value;
        int filled = 1;
        for (Cell* peer : *var->sector_v) {
            if (assignment.count(peer)) {
                int v = assignment.at(peer);
                if (v == value) return false; 
                curr_sum += v;
                filled++;
            }
        }
        if (!ignore_clues) {
            Cell* start = (*var->sector_v)[0];
            if (start->r > 0) {
                auto clue = board->grid[start->r-1][start->c].clue_v;
                if (clue) {
                    if (curr_sum > *clue) return false;
                    if (filled == (int)var->sector_v->size() && curr_sum != *clue) return false;
                }
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
CSPSolver::check_uniqueness(int max_nodes, int seed_offset) {
    std::unordered_map<std::pair<int, int>, int, PairHash> current_sol;
    for (Cell* c : board->white_cells) if(c->value) current_sol[{c->r, c->c}] = *c->value;
    
    for (Cell* c : board->white_cells) c->value = std::nullopt;
    
    std::vector<std::unordered_map<std::pair<int, int>, int, PairHash>> found;
    int node_count = 0;
    solve_for_uniqueness(found, current_sol, node_count, max_nodes, seed_offset);
    
    for (Cell* c : board->white_cells) c->value = current_sol[{c->r, c->c}];
    
    if (found.empty()) return {true, std::nullopt};
    return {false, found[0]};
}

void CSPSolver::solve_for_uniqueness(
    std::vector<std::unordered_map<std::pair<int, int>, int, PairHash>>& found_solutions,
    const std::unordered_map<std::pair<int, int>, int, PairHash>& avoid_sol,
    int& node_count, int max_nodes, int seed) {
    
    if (!found_solutions.empty() || node_count > max_nodes) return;
    node_count++;
    
    std::vector<Cell*> unassigned;
    for(Cell* c : board->white_cells) if(!c->value) unassigned.push_back(c);
    
    if(unassigned.empty()) {
        bool diff = false;
        std::unordered_map<std::pair<int, int>, int, PairHash> sol;
        for(Cell* c : board->white_cells) {
            sol[{c->r, c->c}] = *c->value;
            if(avoid_sol.at({c->r, c->c}) != *c->value) diff = true;
        }
        if(diff) found_solutions.push_back(sol);
        return;
    }
    
    Cell* var = *std::min_element(unassigned.begin(), unassigned.end(),
        [this](Cell* a, Cell* b){ return get_domain_size(a) < get_domain_size(b); });
    
    std::vector<int> vals(9);
    std::iota(vals.begin(), vals.end(), 1);
    std::shuffle(vals.begin(), vals.end(), std::default_random_engine(seed + node_count));
    
    for(int v : vals) {
        // false = DO NOT ignore clues (we are checking uniqueness against clues)
        if(is_valid_move(var, v)) {
            var->value = v;
            solve_for_uniqueness(found_solutions, avoid_sol, node_count, max_nodes, seed);
            if(!found_solutions.empty()) return;
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
    // Horizontal
    if(cell->sector_h) {
        int sum = val; int filled = 1;
        for(Cell* p : *cell->sector_h) {
            if(p->value) {
                if(*p->value == val) return false;
                sum += *p->value;
                filled++;
            }
        }
        if((*cell->sector_h)[0]->c > 0) {
            auto clue = board->grid[(*cell->sector_h)[0]->r][(*cell->sector_h)[0]->c-1].clue_h;
            if(clue && (sum > *clue || (filled == (int)cell->sector_h->size() && sum != *clue))) return false;
        }
    }
    // Vertical
    if(cell->sector_v) {
        int sum = val; int filled = 1;
        for(Cell* p : *cell->sector_v) {
            if(p->value) {
                if(*p->value == val) return false;
                sum += *p->value;
                filled++;
            }
        }
        if((*cell->sector_v)[0]->r > 0) {
            auto clue = board->grid[(*cell->sector_v)[0]->r-1][(*cell->sector_v)[0]->c].clue_v;
            if(clue && (sum > *clue || (filled == (int)cell->sector_v->size() && sum != *clue))) return false;
        }
    }
    return true;
}

bool CSPSolver::repair_topology_robust(const std::unordered_map<std::pair<int, int>, int, PairHash>& alt_sol) {
    std::vector<Cell*> diffs;
    for(Cell* c : board->white_cells) {
        if(c->value && alt_sol.count({c->r, c->c}) && alt_sol.at({c->r, c->c}) != *c->value) {
            diffs.push_back(c);
        }
    }
    if(diffs.empty()) return false;
    
    std::shuffle(diffs.begin(), diffs.end(), rng);
    std::sort(diffs.begin(), diffs.end(), [this](Cell* a, Cell* b){
        return board->count_white_neighbors(a) > board->count_white_neighbors(b);
    });
    
    // Snapshot types
    std::vector<std::vector<CellType>> snapshot(board->height, std::vector<CellType>(board->width));
    for(int r=0; r<board->height; r++)
        for(int c=0; c<board->width; c++) snapshot[r][c] = board->grid[r][c].type;

    for(Cell* target : diffs) {
        board->set_block(target->r, target->c);
        board->set_block(board->height - 1 - target->r, board->width - 1 - target->c);
        
        board->prune_singles(); // Cascading prune
        
        // Validate
        board->collect_white_cells();
        bool valid = true;
        if(board->white_cells.size() < 12) valid = false;
        if(valid && !board->check_connectivity()) valid = false;
        if(valid && !board->validate_clue_headers()) valid = false;
        
        if(valid) return true;
        
        // Rollback
        for(int r=0; r<board->height; r++)
            for(int c=0; c<board->width; c++) board->grid[r][c].type = snapshot[r][c];
        board->collect_white_cells();
    }
    return false;
}

std::unordered_map<Cell*, int> CSPSolver::generate_breaking_constraints(
    const std::unordered_map<std::pair<int, int>, int, PairHash>& alt_sol,
    const std::unordered_map<std::pair<int, int>, int, PairHash>& prev_sol) {
    
    std::unordered_map<Cell*, int> constraints;
    std::vector<Cell*> diffs;
    
    for(Cell* c : board->white_cells) {
        if(alt_sol.count({c->r, c->c}) && prev_sol.count({c->r, c->c})) {
            if(alt_sol.at({c->r, c->c}) != prev_sol.at({c->r, c->c})) {
                diffs.push_back(c);
            }
        }
    }
    
    if(!diffs.empty()) {
        Cell* target = diffs[std::uniform_int_distribution<>(0, (int)diffs.size()-1)(rng)];
        int val_a = prev_sol.at({target->r, target->c});
        int val_b = alt_sol.at({target->r, target->c});
        
        std::vector<int> domain;
        for(int i=1; i<=9; i++) if(i != val_a && i != val_b) domain.push_back(i);
        
        if(!domain.empty()) {
            int new_val = domain[std::uniform_int_distribution<>(0, (int)domain.size()-1)(rng)];
            constraints[target] = new_val;
        }
    }
    return constraints;
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