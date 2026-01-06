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
    const int MAX_TOPOLOGY_RETRIES = 30;
    LOG_DEBUG("Starting puzzle generation. Difficulty: " << difficulty);

    for (int topo_attempt = 0; topo_attempt < MAX_TOPOLOGY_RETRIES; topo_attempt++) {
        if (!prepare_new_topology(difficulty)) continue;

        if (attempt_fill_and_validate(difficulty)) {
            return true;
        }
    }

    LOG_DEBUG("=== FAILURE: Maximum topology retries exceeded ===");
    return false;
}


bool CSPSolver::prepare_new_topology(const std::string& difficulty) {
    bool success = board->generate_topology(0.60, 9, difficulty);
    if (!success || board->white_cells.size() < 12) {
        return false;
    }
    board->collect_white_cells();
    board->identify_sectors();
    return true;
}

bool CSPSolver::attempt_fill_and_validate(const std::string& difficulty) {
    const int MAX_FILL_ATTEMPTS = 5;
    int consecutive_repair_failures = 0;

    for (int fill_attempt = 0; fill_attempt < MAX_FILL_ATTEMPTS; fill_attempt++) {
        board->reset_values();
        
        // 1. Fill the board with values
        if (!solve_fill(difficulty, 200000, {}, {}, true)) continue;
        
        // 2. Sync clues to the filled values
        calculate_clues();

        // 3. Robust Uniqueness Check (The "Multi-Check")
        UniquenessResult result = perform_robust_uniqueness_check();

        if (result == UniquenessResult::UNIQUE) {
            // Final check with Estimator to ensure it meets difficulty targets
            KakuroDifficultyEstimator estimator(board);
            DifficultyResult diff = estimator.estimate_difficulty_detailed();
            
            if (diff.solution_count == 1) {
                LOG_DEBUG("=== SUCCESS! Unique " << diff.rating << " puzzle ===");
                return true;
            }
            // If estimator finds multiple solutions but CSP didn't, CSP was inconclusive
            result = UniquenessResult::MULTIPLE; 
        }

        // 4. Handle Repairs
        if (result == UniquenessResult::MULTIPLE) {
            if (consecutive_repair_failures >= 3) break;
            
            // Try to find an alternative solution to guide repair
            auto [status, alt_sol] = check_uniqueness(100000, fill_attempt);
            if (alt_sol && repair_topology_robust(*alt_sol)) {
                board->collect_white_cells();
                board->identify_sectors();
                fill_attempt = -1; // Restart fill loop for new topology
                consecutive_repair_failures = 0;
            } else {
                consecutive_repair_failures++;
            }
        }
    }
    return false;
}

UniquenessResult CSPSolver::perform_robust_uniqueness_check() {
    // We check 3 times with different search seeds. 
    // This catches "symmetric" solutions that a single search might miss.
    for (int i = 0; i < 3; i++) {
        auto [status, alt_sol] = check_uniqueness(150000, 42 + (i * 100));
        
        if (status == UniquenessResult::MULTIPLE) return UniquenessResult::MULTIPLE;
        if (status == UniquenessResult::INCONCLUSIVE) return UniquenessResult::INCONCLUSIVE;
    }
    return UniquenessResult::UNIQUE;
}


bool CSPSolver::solve_fill(const std::string& difficulty, 
                   int max_nodes, 
                   const std::unordered_map<Cell*, int>& forced_assignments, 
                   const std::vector<ValueConstraint>& forbidden_constraints,
                   bool ignore_clues) {
    LOG_DEBUG("      solve_fill: difficulty=" << difficulty << ", max_nodes=" << max_nodes 
              << ", ignore_clues=" << ignore_clues);
    std::unordered_map<Cell*, int> assignment;
    int node_count = 0;
    
    // Apply constraints
    for(auto& [cell, val] : forced_assignments) {
        if(cell->type == CellType::WHITE) {
            for (const auto& f : forbidden_constraints) {
                if (f.cell == cell) {
                    for (int f_val : f.values) {
                        if (val == f_val) return false; // Impossible constraints
                    }
                }
            }

            if(is_consistent_number(cell, val, assignment, ignore_clues)) {
                assignment[cell] = val;
            } else {
                LOG_DEBUG("      solve_fill: Inconsistent number");
                return false;
            }
        }
    }

    std::vector<int> weights;
    std::string partition_preference = "";
    
    if (difficulty == "very_easy") {
        weights = {20, 15, 5, 1, 1, 1, 5, 15, 20};
        partition_preference = "unique";
    } else if (difficulty == "easy") {
        weights = {10, 8, 6, 2, 1, 2, 6, 8, 10};
        partition_preference = "few";
    } else if (difficulty == "hard") {
        weights = {1, 2, 5, 10, 10, 10, 5, 2, 1};
        partition_preference = "";
    } else {
        weights = {5, 5, 5, 5, 5, 5, 5, 5, 5};
        partition_preference = "";
    }
    
    bool result = backtrack_fill(assignment, node_count, max_nodes, weights, 
                          ignore_clues, partition_preference, forbidden_constraints);
    LOG_DEBUG("      solve_fill result: " << (result ? "SUCCESS" : "FAIL") << ", nodes explored: " << node_count);
    return result;
}


bool CSPSolver::backtrack_fill(std::unordered_map<Cell*, int>& assignment, 
                   int& node_count, int max_nodes, 
                   const std::vector<int>& weights,
                   bool ignore_clues,
                   const std::string& partition_preference,
                   const std::vector<ValueConstraint>& forbidden_constraints) {
    if (node_count > max_nodes) {
        LOG_DEBUG("        Max nodes exceeded (" << node_count << " > " << max_nodes << ")");
        return false;
    }
    node_count++;
    
    if (node_count % 1000 == 0) {
        LOG_DEBUG("        Backtrack progress: " << node_count << " nodes, " 
                  << assignment.size() << "/" << board->white_cells.size() << " assigned");
    }
    
    std::vector<Cell*> unassigned;
    for (Cell* c : board->white_cells) {
        if (assignment.find(c) == assignment.end()) {
            unassigned.push_back(c);
        }
    }
    
    if (unassigned.empty()) {
        LOG_DEBUG("        All cells assigned!");
        
        // FINAL VALIDATION for easy puzzles
        if (!partition_preference.empty() && !ignore_clues) {
            LOG_DEBUG("        Validating partition difficulty for: " << partition_preference);
            if (!validate_partition_difficulty(assignment, partition_preference)) {
                LOG_DEBUG("        Partition difficulty validation FAILED");
                return false;  // Reject this solution, backtrack
            }
            LOG_DEBUG("        Partition difficulty validation PASSED");
        }
        
        for (auto& [cell, val] : assignment) {
            cell->value = val;
        }
        return true;
    }
    
    // MRV
    Cell* var = nullptr;
    int min_domain = 10;

    for (Cell* c : board->white_cells) {
        if (assignment.find(c) == assignment.end()) {
            // Use the assignment map for filling phase
            int d_size = get_domain_size(c, &assignment, ignore_clues);
            
            if (d_size == 0) return false; // Dead end

            if (d_size < min_domain) {
                min_domain = d_size;
                var = c;
            }
            if (min_domain == 1) break;
        }
    }

    if (!var) return true;
    
    std::vector<int> domain;
    
    if (!partition_preference.empty()) {
        domain = get_partition_aware_domain(var, assignment, partition_preference, weights);
        if (node_count % 500 == 0) {
            LOG_DEBUG("        Partition-aware domain for (" << var->r << "," << var->c 
                      << "): size=" << domain.size());
        }
    } else {
        // Original approach
        std::vector<std::pair<int, double>> weighted_domain;
        std::uniform_real_distribution<> dist(0.01, 1.0);
        for (int i = 0; i < 9; i++) {
            weighted_domain.push_back({i + 1, (double)weights[i] * dist(rng)});
        }
        std::sort(weighted_domain.begin(), weighted_domain.end(), 
                 [](const auto& a, const auto& b){ return a.second > b.second; });
        
        for (auto& p : weighted_domain) {
            domain.push_back(p.first);
        }
    }
    
    for (int val : domain) {
        // Check forbidden values from constraints
        bool forbidden = false;
        for (const auto& cons : forbidden_constraints) {
            if (cons.cell == var) {
                for (int f_val : cons.values) {
                    if (val == f_val) { forbidden = true; break; }
                }
            }
            if (forbidden) break;
        }
        if (forbidden) continue;

        if (is_consistent_number(var, val, assignment, ignore_clues)) {
            assignment[var] = val;
            if (backtrack_fill(assignment, node_count, max_nodes, weights, 
                               ignore_clues, partition_preference, forbidden_constraints)) {
                return true;
            }
            assignment.erase(var);
        }
    }
    return false;
}

std::vector<int> CSPSolver::get_partition_aware_domain(
    Cell* cell, 
    const std::unordered_map<Cell*, int>& assignment,
    const std::string& preference,
    const std::vector<int>& weights) {
    
    std::vector<std::pair<int, double>> candidates;
    
    for (int val = 1; val <= 9; val++) {
        // Quick duplicate check
        bool duplicate = false;
        
        if (cell->sector_h && !cell->sector_h->empty()) {
            for (Cell* c : *(cell->sector_h)) {
                if (assignment.count(c) && assignment.at(c) == val) {
                    duplicate = true;
                    break;
                }
            }
        }
        
        if (!duplicate && cell->sector_v && !cell->sector_v->empty()) {
            for (Cell* c : *(cell->sector_v)) {
                if (assignment.count(c) && assignment.at(c) == val) {
                    duplicate = true;
                    break;
                }
            }
        }
        
        if (duplicate) continue;
        
        // Calculate partition scores for both directions
        double h_score = calculate_partition_score(cell, val, assignment, 'h', preference);
        double v_score = calculate_partition_score(cell, val, assignment, 'v', preference);
        
        // Combined score: lower is better (fewer partitions = easier)
        double difficulty_weight = (double)weights[val - 1];
        double combined_score = (h_score + v_score) * (10.0 / std::max(difficulty_weight, 1.0));
        
        candidates.push_back({val, combined_score});
    }
    
    if (candidates.empty()) {
        LOG_DEBUG("          WARNING: No valid candidates for cell(" << cell->r << "," << cell->c << ")");
        // Fallback: return all values 1-9 if no valid candidates found
        std::vector<int> result;
        for (int i = 1; i <= 9; i++) result.push_back(i);
        return result;
    }
    
    // Sort by score (lower = better), with some randomness
    std::uniform_real_distribution<> dist(0.0, 2.0);
    for (auto& cand : candidates) {
        cand.second += dist(rng);
    }

    // 2. Sort based on the now-static scores (Strict Weak Ordering satisfied)
    std::sort(candidates.begin(), candidates.end(), 
            [](const auto& a, const auto& b) {
                return a.second < b.second;
            });
    
    std::vector<int> result;
    for (auto& [val, score] : candidates) {
        result.push_back(val);
    }
    return result;
}


double CSPSolver::calculate_partition_score(
    Cell* cell,
    int value,
    const std::unordered_map<Cell*, int>& assignment,
    char direction,
    const std::string& preference) {
    
    auto sector = (direction == 'h') ? cell->sector_h : cell->sector_v;
    
    // Safety check
    if (!sector || sector->empty()) return 0.0;
    
    // Calculate current state of this sector
    int current_sum = value;
    int filled_count = 1;
    std::vector<Cell*> remaining_cells;
    
    for (Cell* c : *sector) {
        if (assignment.count(c)) {
            current_sum += assignment.at(c);
            filled_count++;
        } else if (c != cell) {
            remaining_cells.push_back(c);
        }
    }
    
    int sector_length = (int)sector->size();
    
    // If this completes the sector, count actual partitions
    if (filled_count == sector_length) {
        int num_partitions = count_partitions(current_sum, sector_length);
        
        if (preference == "unique") {
            if (num_partitions == 1) return 0.0;
            else if (num_partitions == 2) return 1.0;
            else if (num_partitions <= 4) return 5.0;
            else return 20.0;
        } else if (preference == "few") {
            if (num_partitions <= 2) return 0.0;
            else if (num_partitions <= 4) return 2.0;
            else if (num_partitions <= 6) return 5.0;
            else return 15.0;
        }
    } else {
        // Sector not complete yet - estimate difficulty
        int remaining_count = (int)remaining_cells.size();
        
        // Get used digits
        std::unordered_set<int> used_digits;
        for (Cell* c : *sector) {
            if (assignment.count(c)) {
                used_digits.insert(assignment.at(c));
            }
        }
        used_digits.insert(value);
        
        // Available digits
        std::vector<int> available;
        for (int d = 1; d <= 9; d++) {
            if (used_digits.find(d) == used_digits.end()) {
                available.push_back(d);
            }
        }
        
        if ((int)available.size() < remaining_count) return 100.0;
        
        int min_remaining = 0;
        for (int i = 0; i < remaining_count; i++) {
            min_remaining += available[i];
        }
        
        int max_remaining = 0;
        int start_idx = (int)available.size() - remaining_count;
        for (int i = start_idx; i < (int)available.size(); i++) {
            max_remaining += available[i];
        }
        
        int min_final_sum = current_sum + min_remaining;
        int max_final_sum = current_sum + max_remaining;
        
        // Sample a few sums in the range
        std::vector<int> sample_sums;
        if (min_final_sum == max_final_sum) {
            sample_sums.push_back(min_final_sum);
        } else {
            int step = std::max(1, (max_final_sum - min_final_sum) / 3);
            for (int s = min_final_sum; s <= max_final_sum; s += step) {
                sample_sums.push_back(s);
            }
        }
        
        if (sample_sums.empty()) return 5.0;  // Safety fallback
        
        double avg_partitions = 0;
        for (int s : sample_sums) {
            avg_partitions += count_partitions(s, sector_length);
        }
        avg_partitions /= sample_sums.size();
        
        if (preference == "unique") {
            if (avg_partitions <= 2) return 1.0;
            else if (avg_partitions <= 4) return 3.0;
            else return 8.0;
        } else if (preference == "few") {
            if (avg_partitions <= 4) return 1.0;
            else if (avg_partitions <= 6) return 3.0;
            else return 6.0;
        }
    }
    
    return 5.0;
}

int CSPSolver::count_partitions(int target_sum, int length) {
    // Add bounds check
    if (length <= 0 || length > 9 || target_sum <= 0 || target_sum > 45) {
        return 0;
    }
    
    std::pair<int, int> key = {target_sum, length};
    if (partition_cache.count(key)) {
        return partition_cache[key];
    }
    
    std::unordered_set<int> used;
    int result = count_partitions_recursive(target_sum, length, 1, used);
    partition_cache[key] = result;
    
    if (result == 0 || result > 20) {
        LOG_DEBUG("          Partition count: sum=" << target_sum << ", len=" << length 
                  << " -> " << result << " partitions");
    }
    
    return result;
}


int CSPSolver::count_partitions_recursive(
    int remaining_sum,
    int remaining_length,
    int min_digit,
    std::unordered_set<int>& used) {
    
    if (remaining_length == 0) {
        return (remaining_sum == 0) ? 1 : 0;
    }
    
    if (remaining_sum <= 0 || min_digit > 9) return 0;
    
    // Get available digits
    std::vector<int> available;
    for (int d = min_digit; d <= 9; d++) {
        if (used.find(d) == used.end()) {
            available.push_back(d);
        }
    }
    
    if ((int)available.size() < remaining_length) return 0;
    
    // Feasibility check
    int min_possible = 0;
    for (int i = 0; i < remaining_length && i < (int)available.size(); i++) {
        min_possible += available[i];
    }
    
    int max_possible = 0;
    int start = (int)available.size() - remaining_length;
    if (start < 0) start = 0;
    for (int i = start; i < (int)available.size(); i++) {
        max_possible += available[i];
    }
    
    if (remaining_sum < min_possible || remaining_sum > max_possible) return 0;
    
    int count = 0;
    for (int digit : available) {
        used.insert(digit);
        count += count_partitions_recursive(remaining_sum - digit, remaining_length - 1, 
                                           digit + 1, used);
        used.erase(digit);
    }
    
    return count;
}

bool CSPSolver::validate_partition_difficulty(
    const std::unordered_map<Cell*, int>& assignment,
    const std::string& preference) {
    
    LOG_DEBUG("          Validating partition difficulty...");
    
    int easy_clue_count = 0;
    int total_clue_count = 0;
    
    // Check horizontal sectors
    for (const auto& sector : board->sectors_h) {
        if (sector->empty()) continue;
        
        bool all_assigned = true;
        for (Cell* c : *(sector)) {
            if (assignment.find(c) == assignment.end()) {
                all_assigned = false;
                break;
            }
        }
        if (!all_assigned) continue;
        
        total_clue_count++;
        int clue_sum = 0;
        for (Cell* c : *(sector)) {
            clue_sum += assignment.at(c);
        }
        
        int num_partitions = count_partitions(clue_sum, (int)sector->size());
        
        if (preference == "unique" && num_partitions <= 2) {
            easy_clue_count++;
        } else if (preference == "few" && num_partitions <= 4) {
            easy_clue_count++;
        }
    }
    
    // Check vertical sectors
    for (const auto& sector : board->sectors_v) {
        if (sector->empty()) continue;
        
        bool all_assigned = true;
        for (Cell* c : *(sector)) {
            if (assignment.find(c) == assignment.end()) {
                all_assigned = false;
                break;
            }
        }
        if (!all_assigned) continue;
        
        total_clue_count++;
        int clue_sum = 0;
        for (Cell* c : *(sector)) {
            clue_sum += assignment.at(c);
        }
        
        int num_partitions = count_partitions(clue_sum, (int)sector->size());
        
        if (preference == "unique" && num_partitions <= 2) {
            easy_clue_count++;
        } else if (preference == "few" && num_partitions <= 4) {
            easy_clue_count++;
        }
    }
    
    if (total_clue_count == 0) {
        LOG_DEBUG("          No clues to validate");
        return true;
    }
    
    double ratio = (double)easy_clue_count / total_clue_count;
    double required_ratio = (preference == "unique") ? 0.80 : 0.60;
    
    LOG_DEBUG("          Easy clues: " << easy_clue_count << "/" << total_clue_count 
              << " = " << (ratio * 100) << "% (required: " << (required_ratio * 100) << "%)");
    
    if (preference == "unique") {
        return ratio >= 0.80;
    } else if (preference == "few") {
        return ratio >= 0.60;
    }
    
    return true;
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
    if (ignore_clues) {
        // Simple duplicate check for the filling phase
        auto has_dupe = [&](std::shared_ptr<std::vector<Cell*>> sector) {
            if (!sector) return false;
            for (Cell* p : *sector) {
                if (p == var) continue;
                if (assignment.count(p) && assignment.at(p) == value) return true;
                if (p->value.has_value() && *p->value == value) return true;
            }
            return false;
        };
        return !has_dupe(var->sector_h) && !has_dupe(var->sector_v);
    }

    // Comprehensive check for the uniqueness phase
    return is_valid_move(var, value, &assignment, ignore_clues);
}

void CSPSolver::calculate_clues() {
    // 1. Fully Clear
    for (int r = 0; r < board->height; r++) {
        for (int c = 0; c < board->width; c++) {
            board->grid[r][c].clue_h = std::nullopt;
            board->grid[r][c].clue_v = std::nullopt;
        }
    }

    // 2. Refresh sectors to ensure white_cells and sectors match the topology
    board->identify_sectors();

    // 3. Assign Clues
    for (auto& sector : board->sectors_h) {
        int sum = 0;
        for (Cell* c : *sector) sum += c->value.value_or(0);
        Cell* first = (*sector)[0];
        board->grid[first->r][first->c - 1].clue_h = sum;
    }
    for (auto& sector : board->sectors_v) {
        int sum = 0;
        for (Cell* c : *sector) sum += c->value.value_or(0);
        Cell* first = (*sector)[0];
        board->grid[first->r - 1][first->c].clue_v = sum;
    }
}

std::pair<UniquenessResult, std::optional<std::unordered_map<std::pair<int, int>, int, PairHash>>> 
CSPSolver::check_uniqueness(int max_nodes, int seed_offset) {
    LOG_DEBUG("  Checking uniqueness using Logical Estimator...");
    
    // 1. Back up current solution
    std::unordered_map<std::pair<int, int>, int, PairHash> original_sol;
    for (Cell* c : board->white_cells) {
        if(c->value) original_sol[{c->r, c->c}] = *c->value;
        c->value = std::nullopt; // Clear for solving
    }
    
    std::vector<std::unordered_map<std::pair<int, int>, int, PairHash>> found;
    int node_count = 0;
    bool timed_out = false;
    
    solve_for_uniqueness(found, original_sol, node_count, max_nodes, seed_offset, timed_out);
    
    for (Cell* c : board->white_cells) {
        c->value = original_sol[{c->r, c->c}];
    }
    
    if (!found.empty()) return {UniquenessResult::MULTIPLE, found[0]};
    if (timed_out) return {UniquenessResult::INCONCLUSIVE, std::nullopt};
    return {UniquenessResult::UNIQUE, std::nullopt};
}


void CSPSolver::solve_for_uniqueness(
    std::vector<std::unordered_map<std::pair<int, int>, int, PairHash>>& found_solutions,
    const std::unordered_map<std::pair<int, int>, int, PairHash>& avoid_sol,
    int& node_count, int max_nodes, int seed, bool& timed_out) {
    
    if (!found_solutions.empty()) return;
    if (node_count > max_nodes) {
        timed_out = true;
        return;
    }
    node_count++;
    
    Cell* var = nullptr;
    int min_domain = 10;

    // MRV Selection
    for (Cell* c : board->white_cells) {
        if (!c->value.has_value()) {
            int d_size = get_domain_size(c, nullptr, false);
            if (d_size == 0) return; 
            if (d_size < min_domain) {
                min_domain = d_size;
                var = c;
            }
            if (min_domain == 1) break; 
        }
    }

    if (!var) {
        // Found A solution. Is it different?
        std::unordered_map<std::pair<int, int>, int, PairHash> sol;
        bool is_different = false;
        for (Cell* c : board->white_cells) {
            int val = c->value.value_or(0);
            sol[{c->r, c->c}] = val;
            if (val != avoid_sol.at({c->r, c->c})) is_different = true;
        }
        if (is_different) found_solutions.push_back(sol);
        return;
    }
    
    std::vector<int> vals = {1,2,3,4,5,6,7,8,9};
    int target_val = avoid_sol.at({var->r, var->c});
    
    std::shuffle(vals.begin(), vals.end(), std::default_random_engine(seed + node_count));
    
    // Move the 'avoid' value to the end of the list
    std::partition(vals.begin(), vals.end(), [&](int v) { return v != target_val; });
    
    for(int v : vals) {
        if(is_valid_move(var, v, nullptr, false)) {
            var->value = v;
            solve_for_uniqueness(found_solutions, avoid_sol, node_count, max_nodes, seed, timed_out);
            var->value = std::nullopt;
            if(!found_solutions.empty() || timed_out) return;
        }
    }
}

int CSPSolver::get_domain_size(Cell* cell, const std::unordered_map<Cell*, int>* assignment, bool ignore_clues) {
    int count = 0;
    for (int v = 1; v <= 9; v++) {
        if (is_valid_move(cell, v, assignment, ignore_clues)) {
            count++;
        }
    }
    return count;
}

bool CSPSolver::is_valid_move(Cell* cell, int val, const std::unordered_map<Cell*, int>* assignment, bool ignore_clues) {
    auto check_sector = [&](std::shared_ptr<std::vector<Cell*>> sector, bool is_horz) {
        if (!sector || sector->empty()) return true;

        int sum = val;
        int filled_count = 1;
        uint16_t used_mask = (1 << val);

        for (Cell* p : *sector) {
            if (p == cell) continue;
            int v = 0;
            if (assignment && assignment->count(p)) v = assignment->at(p);
            else if (p->value.has_value()) v = *p->value;

            if (v > 0) {
                if (v == val) return false; 
                sum += v;
                used_mask |= (1 << v);
                filled_count++;
            }
        }

        // If we are ignoring clues (Filling Phase), we stop here after the duplicate check
        if (ignore_clues) return true;

        // FIND THE CLUE (Robust Indexing)
        Cell* first = (*sector)[0];
        int clue_r = is_horz ? first->r : first->r - 1;
        int clue_c = is_horz ? first->c - 1 : first->c;
        
        // Safety bounds check
        if (clue_r < 0 || clue_c < 0) return false; 
        
        auto& clue_cell = board->grid[clue_r][clue_c];
        std::optional<int> clue_opt = is_horz ? clue_cell.clue_h : clue_cell.clue_v;

        // CRITICAL: If no clue is found, this move is INVALID (not "anything goes")
        if (!clue_opt.has_value()) return false; 

        int target = *clue_opt;
        int remaining_cells = (int)sector->size() - filled_count;

        if (sum > target) return false; 
        if (remaining_cells > 0) {
            int min_rem = 0, max_rem = 0, f_min = 0, f_max = 0;
            for (int i = 1; i <= 9 && f_min < remaining_cells; ++i) {
                if (!(used_mask & (1 << i))) { min_rem += i; f_min++; }
            }
            for (int i = 9; i >= 1 && f_max < remaining_cells; --i) {
                if (!(used_mask & (1 << i))) { max_rem += i; f_max++; }
            }
            if (sum + min_rem > target || sum + max_rem < target) return false;
        } else if (sum != target) return false;
        
        return true;
    };

    return check_sector(cell->sector_h, true) && check_sector(cell->sector_v, false);
}

bool CSPSolver::repair_topology_robust(
    const std::unordered_map<std::pair<int, int>, int, PairHash>& alt_sol) {
    
    LOG_DEBUG("  Attempting topology repair");
    
    // Find cells where solutions differ
    std::vector<Cell*> diffs;
    for(Cell* c : board->white_cells) {
        if(c->value && alt_sol.count({c->r, c->c}) && 
           alt_sol.at({c->r, c->c}) != *c->value) {
            diffs.push_back(c);
        }
    }
    
    LOG_DEBUG("  Found " << diffs.size() << " differing cells");
    if(diffs.empty()) return false;
    
    // Sort by neighbor count (prefer blocking high-connectivity cells)
    std::shuffle(diffs.begin(), diffs.end(), rng);
    std::sort(diffs.begin(), diffs.end(), [this](Cell* a, Cell* b){
        return board->count_white_neighbors(a) > board->count_white_neighbors(b);
    });
    
    // Calculate minimum acceptable size
    int current_size = (int)board->white_cells.size();
    int min_required = std::max(12, current_size - (current_size / 4)); // Allow 25% reduction
    
    LOG_DEBUG("  Current size: " << current_size << ", min required: " << min_required);
    
    // Snapshot current state
    std::vector<std::vector<CellType>> snapshot(board->height, 
                                                 std::vector<CellType>(board->width));
    for(int r = 0; r < board->height; r++) {
        for(int c = 0; c < board->width; c++) {
            snapshot[r][c] = board->grid[r][c].type;
        }
    }
    
    // Try blocking each differing cell (limit attempts)
    int max_attempts = std::min(5, (int)diffs.size());
    
    for(int i = 0; i < max_attempts; i++) {
        Cell* target = diffs[i];
        LOG_DEBUG("    Trying cell(" << target->r << "," << target->c << ") [" 
                  << (i+1) << "/" << max_attempts << "]");
        
        // Restore snapshot
        for(int r = 0; r < board->height; r++) {
            for(int c = 0; c < board->width; c++) {
                board->grid[r][c].type = snapshot[r][c];
            }
        }
        
        // Block the target cell
        board->set_block(target->r, target->c);
        board->set_block(board->height - 1 - target->r, board->width - 1 - target->c);
        
        // Apply stabilization
        board->break_large_patches(3);
        board->prune_singles();
        board->break_single_runs();
        
        // Validate
        board->collect_white_cells();
        
        if((int)board->white_cells.size() < min_required) {
            LOG_DEBUG("    Failed: too few cells (" << board->white_cells.size() << ")");
            continue;
        }
        
        if(!board->check_connectivity()) {
            LOG_DEBUG("    Failed: connectivity check");
            continue;
        }
        
        if(!board->validate_clue_headers()) {
            LOG_DEBUG("    Failed: clue headers check");
            continue;
        }
        
        board->identify_sectors();
        
        // Additional check: make sure we still have enough sectors
        if(board->sectors_h.size() + board->sectors_v.size() < 6) {
            LOG_DEBUG("    Failed: too few sectors");
            continue;
        }
        
        LOG_DEBUG("    Repair successful!");
        return true;
    }
    
    // Restore original state if all repairs failed
    for(int r = 0; r < board->height; r++) {
        for(int c = 0; c < board->width; c++) {
            board->grid[r][c].type = snapshot[r][c];
        }
    }
    board->collect_white_cells();
    board->identify_sectors();
    
    LOG_DEBUG("  All repair attempts failed");
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
        auto it_prev = prev_sol.find({target->r, target->c});
        auto it_alt = alt_sol.find({target->r, target->c});
        
        if (it_prev != prev_sol.end() && it_alt != alt_sol.end()) {
            int val_a = it_prev->second;
            int val_b = it_alt->second;
        
            std::vector<int> domain;
            for(int i=1; i<=9; i++) if(i != val_a && i != val_b) domain.push_back(i);
            
            if(!domain.empty()) {
                int new_val = domain[std::uniform_int_distribution<>(0, (int)domain.size()-1)(rng)];
                constraints[target] = new_val;
            }
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