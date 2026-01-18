#include "kakuro_cpp.h"


namespace kakuro {

// Implementation of HybridUniquenessChecker
// (Class declaration should be in kakuro_cpp.h)
std::pair<UniquenessResult, 
          std::optional<std::unordered_map<std::pair<int, int>, int, PairHash>>>
HybridUniquenessChecker::check_uniqueness_hybrid(int max_nodes, int seed_offset) {
    PROFILE_FUNCTION(board_->logger);
    LOG_DEBUG("  Checking uniqueness using Hybrid Logic+Search approach...");
    
    // 1. Backup current solution
    std::unordered_map<Cell*, int> original_sol;
    std::unordered_map<std::pair<int, int>, int, PairHash> original_sol_coords;
    
    {
        PROFILE_SCOPE("Uniqueness_Backup", board_->logger);
        for (Cell* c : board_->white_cells) {
            if (c->value) {
                original_sol[c] = *c->value;
                original_sol_coords[{c->r, c->c}] = *c->value;
            }
            c->value = std::nullopt; // Clear for solving
        }
    }
    
    // 2. Initialize candidates with full domain
    CandidateMap candidates;
    for (Cell* c : board_->white_cells) {
        candidates[c] = ALL_CANDIDATES;
    }
    
    // 3. Initialize candidates properly by removing impossible values
    {
        PROFILE_SCOPE("Uniqueness_CandidateInit", board_->logger);
        
        // Remove values that are already used in each sector
        // We only care about values that are currently set on the board (which are none for white cells
        // at this stage, but this loop is kept for correctness if partial solving is added later).
        for (Cell* cell : board_->white_cells) {
            uint16_t valid_mask = ALL_CANDIDATES;
            
            // Check horizontal sector for used values
            if (cell->sector_h) {
                for (Cell* neighbor : *(cell->sector_h)) {
                    if (neighbor != cell && neighbor->value.has_value()) {
                        valid_mask &= ~(1 << *neighbor->value);
                    }
                }
            }
            
            // Check vertical sector for used values
            if (cell->sector_v) {
                for (Cell* neighbor : *(cell->sector_v)) {
                    if (neighbor != cell && neighbor->value.has_value()) {
                        valid_mask &= ~(1 << *neighbor->value);
                    }
                }
            }
            
            candidates[cell] = valid_mask;
        }
        
        // Basic sum constraint filtering
        auto init_sector_constraints = [&](const std::vector<std::shared_ptr<std::vector<Cell*>>>& sectors, bool is_horz) {
            for (const auto& sector : sectors) {
                if (sector->empty()) continue;
                
                // Get the clue
                Cell* first = (*sector)[0];
                std::optional<int> clue_opt;
                
                if (is_horz && first->c > 0) {
                    clue_opt = board_->grid[first->r][first->c - 1].clue_h;
                } else if (!is_horz && first->r > 0) {
                    clue_opt = board_->grid[first->r - 1][first->c].clue_v;
                }
                
                if (!clue_opt.has_value()) continue;
                int target = *clue_opt;
                int length = sector->size();
                
                // Calculate min and max possible sums for this sector
                int min_sum = 0, max_sum = 0;
                for (int i = 1; i <= 9 && i <= length; i++) {
                    min_sum += i;
                }
                for (int i = 9; i > 0 && (9 - i) < length; i--) {
                    max_sum += i;
                }
                
                // If the target is impossible for this sector length, something is wrong
                if (target < min_sum || target > max_sum) continue;
                
                // Remove values that are clearly too large or too small
                for (Cell* cell : *sector) {
                    uint16_t new_mask = 0;
                    
                    for (int d = 1; d <= 9; d++) {
                        if (!(candidates[cell] & (1 << d))) continue;
                        
                        // Very basic check: would this value leave room for others?
                        int remaining = target - d;
                        int slots = length - 1;
                        
                        if (slots == 0) {
                            // This cell must complete the sum
                            if (remaining == 0) {
                                new_mask |= (1 << d);
                            }
                        } else {
                            // Check if remaining sum is achievable
                            // Min: 1+2+...+slots
                            // Max: 9+8+...+(9-slots+1)
                            int min_others = (slots * (slots + 1)) / 2;
                            int max_others = (slots * (18 - slots + 1)) / 2;
                            
                            if (remaining >= min_others && remaining <= max_others) {
                                new_mask |= (1 << d);
                            }
                        }
                    }
                    
                    if (new_mask != 0) {
                        candidates[cell] &= new_mask;
                    } else {
                        // FIX: If new_mask is 0, it means NO value works. 
                        // We must set candidates to 0 to signal contradiction.
                        candidates[cell] = 0;
                    }
                }
            }
        };
        
        init_sector_constraints(board_->sectors_h, true);
        init_sector_constraints(board_->sectors_v, false);
    }

    // 5. Count how many cells are logically determined
    int determined_cells = 0;
    for (auto& [cell, mask] : candidates) {
        if (popcount9(mask) == 1) {
            determined_cells++;
        }
    }
    
    // 4. Apply logical deduction to reduce search space
    bool reduced = false;
    bool logic_consistent = true;
    CandidateMap candidates_backup = candidates; // Shallow copy of map (integers)

    std::vector<std::pair<Cell*, std::optional<int>>> value_backup;
    for(auto c : board_->white_cells) {
        value_backup.push_back({c, c->value});
    }
    
    {
        PROFILE_SCOPE("Uniqueness_LogicalReduction", board_->logger);
        reduced = apply_logical_reduction(candidates, original_sol_coords);
        
        // Validation: Check for empty candidates (Contradiction)
        for (auto& [c, m] : candidates) {
            if (m == 0) {
                logic_consistent = false;
                break;
            }
        }
    }
    
    if (!logic_consistent) {
        LOG_DEBUG("    Logical reduction caused contradiction! Reverting to full search.");
        candidates = candidates_backup; // Restore
        // FIX: Restore values
        for(auto& p : value_backup) {
            p.first->value = p.second;
        }

        determined_cells = 0; 
#if KAKURO_ENABLE_LOGGING
        if (board_->logger && board_->logger->is_enabled()) {
            board_->logger->log_step(
                GenerationLogger::STAGE_UNIQUENESS,
                GenerationLogger::SUBSTAGE_LOGIC_STEP,
                "Logical reduction caused contradiction: reverting",
                board_->get_grid_state());
        }
#endif
    } else {
        LOG_DEBUG("    Logical reduction: " << (reduced ? "SUCCESS" : "NONE") 
                  << " (reduced search space)");
      
        for (Cell* c : board_->white_cells) {
            uint16_t m = candidates[c];
            if (popcount9(m) == 1) {
                for (int d = 1; d <= 9; d++) {
                    if (m & (1 << d)) {
                        c->value = d;
                        break;
                    }
                }
            }
        }
    

    }
    
    
    LOG_DEBUG("    Cells logically determined: " << determined_cells 
              << "/" << board_->white_cells.size());


#if KAKURO_ENABLE_LOGGING
    if (board_->logger && board_->logger->is_enabled()) {
        std::unordered_map<Cell *, int> viz_map;
        for (auto &[c, m] : candidates) {
            if (popcount9(m) == 1) {
                auto vals = mask_to_values(m);
                if (!vals.empty()) viz_map[c] = vals[0];
            }
        }
        board_->logger->log_step(
            GenerationLogger::STAGE_UNIQUENESS,
            GenerationLogger::SUBSTAGE_LOGIC_STEP,
            "Logical reduction complete: " + std::to_string(determined_cells) + " cells determined",
            board_->get_grid_state(&viz_map));
    }
#endif
    
    // 6. Hybrid search
    std::vector<std::unordered_map<std::pair<int, int>, int, PairHash>> found;
    int node_count = 0;
    bool timed_out = false;
    
    {
        PROFILE_SCOPE("Uniqueness_HybridSearch", board_->logger);
        hybrid_search(found, original_sol_coords, candidates, 
                     node_count, max_nodes, seed_offset, timed_out);
    }
    
    // 7. Restore original solution
    {
        PROFILE_SCOPE("Uniqueness_Restore", board_->logger);
        for (Cell* c : board_->white_cells) {
            if (original_sol.count(c))
                c->value = original_sol[c];
            else
                c->value = std::nullopt;
        }
    }
    
    LOG_DEBUG("    Hybrid search explored " << node_count << " nodes");

#if KAKURO_ENABLE_LOGGING
    if (board_->logger && board_->logger->is_enabled()) {
        std::string search_status = "Hybrid search finished: " + std::to_string(node_count) + " nodes.";
        if (timed_out) {
            search_status += " Timed out.";
        } else if (!found.empty()) {
            search_status += " Found alternative solution.";
        } else {
            search_status += " No alternative found.";
        }
        
        board_->logger->log_step(
            GenerationLogger::STAGE_UNIQUENESS,
            "hybrid_result",
            search_status,
            board_->get_grid_state() // Original solution is restored above
        );
    }
#endif
    
    if (!found.empty()) {
        return {UniquenessResult::MULTIPLE, found[0]};
    }
    if (timed_out)
        return {UniquenessResult::INCONCLUSIVE, std::nullopt};
    return {UniquenessResult::UNIQUE, std::nullopt};
}

// Helper to check if a partition can be assigned to a sector
// with cell at cell_idx assigned to val
bool HybridUniquenessChecker::can_assign_partition_to_sector(
    const std::vector<int>& partition,
    const std::vector<Cell*>& sector,
    const CandidateMap& candidates,
    int fixed_cell_idx,
    int fixed_val) {
    
    int n = sector.size();
    std::vector<int> partition_copy = partition;
    
    // Remove fixed_val from partition
    auto it = std::find(partition_copy.begin(), partition_copy.end(), fixed_val);
    if (it == partition_copy.end()) return false; // fixed_val not in partition
    partition_copy.erase(it);
    
    // Try to assign remaining partition values to remaining cells
    // Use backtracking to check if a valid assignment exists
    return can_match_values_to_cells(partition_copy, sector, candidates, fixed_cell_idx);
}

bool HybridUniquenessChecker::can_match_values_to_cells(
    std::vector<int> values,
    const std::vector<Cell*>& sector,
    const CandidateMap& candidates,
    int skip_cell_idx) {
    
    if (values.empty()) return true; // All values assigned
    
    // Try to assign first value to any compatible cell
    int val = values[0];
    std::vector<int> remaining_values(values.begin() + 1, values.end());
    
    for (int i = 0; i < sector.size(); i++) {
        if (i == skip_cell_idx) continue; // Skip the fixed cell
        
        Cell* cell = sector[i];
        if (cell->value.has_value() && *cell->value != val) {
            continue;
        }
        uint16_t mask = candidates.at(cell);
        
        // Can this cell take this value?
        if (mask & (1 << val)) {
            // Try assigning it and recurse
            // Need to prevent reusing this cell for other values
            std::unordered_set<int> used = {i};
            if (can_match_values_to_cells_recursive(remaining_values, sector, candidates, skip_cell_idx, used)) {
                return true;
            }
        }
    }
    
    return false;
}

bool HybridUniquenessChecker::can_match_values_to_cells_recursive(
    const std::vector<int>& values,
    const std::vector<Cell*>& sector,
    const CandidateMap& candidates,
    int skip_cell_idx,
    const std::unordered_set<int>& used_cell_indices) {
    
    if (values.empty()) return true; // All values successfully assigned
    
    // Try to assign first value to any compatible unused cell
    int val = values[0];
    std::vector<int> remaining_values(values.begin() + 1, values.end());
    
    for (int i = 0; i < sector.size(); i++) {
        // Skip the fixed cell and already-used cells
        if (i == skip_cell_idx || used_cell_indices.count(i)) continue;
        
        Cell* cell = sector[i];
        if (cell->value.has_value() && *cell->value != val) {
            continue;
        }

        uint16_t mask = candidates.at(cell);
        
        // Can this cell take this value?
        if (mask & (1 << val)) {
            // Mark this cell as used and recurse
            std::unordered_set<int> new_used = used_cell_indices;
            new_used.insert(i);
            
            if (can_match_values_to_cells_recursive(remaining_values, sector, candidates, skip_cell_idx, new_used)) {
                return true;
            }
        }
    }
    
    return false; // Couldn't assign all values
}

bool HybridUniquenessChecker::apply_logical_reduction(
    CandidateMap& candidates,
    const std::unordered_map<std::pair<int, int>, int, PairHash>& avoid_sol) {
    
    // Backup Cell values in case we need to revert due to contradiction
    std::vector<std::pair<Cell*, std::optional<int>>> local_val_backup;
    for(auto c : board_->white_cells) local_val_backup.push_back({c, c->value});

    // Partition Cache
    static std::map<std::pair<int, int>, std::vector<std::vector<int>>> partition_cache;

    // Mutex removed to avoid dependency issues in single-threaded env
    
    auto get_partitions = [&](int sum, int len) -> const std::vector<std::vector<int>>& {
        static std::vector<std::vector<int>> empty; 
        if(len > 9 || len < 1) return empty;
        
        if (partition_cache.count({sum, len})) return partition_cache[{sum, len}];
        
        std::vector<std::vector<int>> res;
        std::vector<int> cur;
        std::function<void(int, int, int)> bt = [&](int t, int k, int s) {
            if (k == 0) {
                if (t == 0) res.push_back(cur);
                return;
            }
            for (int i = s; i <= 9; ++i) {
                if (i > t) break;
                cur.push_back(i);
                bt(t - i, k - 1, i + 1);
                cur.pop_back();
            }
        };
        bt(sum, len, 1);
        partition_cache[{sum, len}] = res;
        return partition_cache[{sum, len}];
    };
    
    // ... apply_partition_pruning defined below ...
    // (We need to jump to the loop to insert the call)


    auto apply_partition_pruning = [&](const std::vector<std::shared_ptr<std::vector<Cell*>>>& sectors, bool is_horz) {
        bool local_change = false;
        for (const auto& sector : sectors) {
            if (sector->empty()) continue;
            
            // Get Clue
            Cell* first = (*sector)[0];
            std::optional<int> clue_opt;
            if (is_horz && first->c > 0) clue_opt = board_->grid[first->r][first->c - 1].clue_h;
            else if (!is_horz && first->r > 0) clue_opt = board_->grid[first->r - 1][first->c].clue_v;
            
            if (!clue_opt) continue;
            int target = *clue_opt;
            int len = sector->size();
            
            // FIX: Use SOUND partition generation (theoretical), not union-based
            const auto& valid_partitions = get_partitions(target, len);
            
            if (valid_partitions.empty()) {
                for(Cell* c : *sector) candidates[c] = 0;
                return false; 
            }
            
            for (int cell_idx = 0; cell_idx < len; cell_idx++) {
                Cell* c = (*sector)[cell_idx];
                uint16_t old_mask = candidates[c];
                uint16_t new_mask = 0;
                
                // For each candidate value of this cell
                for (int val = 1; val <= 9; val++) {
                    if (!(old_mask & (1 << val))) continue;
                    
                    // Check if there exists a valid partition where this cell can be 'val'
                    bool found_valid_assignment = false;
                    
                    for (const auto& partition : valid_partitions) {
                        // Does this partition contain val?
                        bool has_val = false;
                        for (int pv : partition) {
                            if (pv == val) {
                                has_val = true;
                                break;
                            }
                        }
                        if (!has_val) continue;
                        
                        // Can we assign the REST of the partition to the REST of the sector?
                        if (can_assign_partition_to_sector(partition, *sector, candidates, cell_idx, val)) {
                            found_valid_assignment = true;
                            break;
                        }
                    }
                    
                    if (found_valid_assignment) {
                        new_mask |= (1 << val);
                    }
                }
                
                if (new_mask != old_mask) {
                    candidates[c] = new_mask;
                    local_change = true;
                    if (new_mask == 0) return false; // Contradiction
                }
            }
        }
        return local_change; 
    };



    bool any_change = false;
    int iterations = 0;
    const int MAX_QUICK_ITERATIONS = 10; // Increased slightly
    
    while (iterations++ < MAX_QUICK_ITERATIONS) {
        bool changed = false;

        // 1. Naked singles propagation - FIXED VERSION
        // Use a queue to process newly-determined cells
        std::queue<Cell*> to_process;
        std::unordered_set<Cell*> processed;
        
        // Find all currently determined cells
        for (Cell* cell : board_->white_cells) {
            uint16_t mask = candidates[cell];
            if (popcount9(mask) == 1) {
                to_process.push(cell);
            }
        }
        
        // Process each determined cell and propagate
        while (!to_process.empty()) {
            Cell* cell = to_process.front();
            to_process.pop();
            
            if (processed.count(cell)) continue;
            processed.insert(cell);
            
            uint16_t mask = candidates[cell];
            if (popcount9(mask) != 1) continue; // Cell is no longer determined

            for(int d=1; d<=9; d++) {
                if(mask & (1<<d)) { cell->value = d; break; }
            }
            
            auto propagate_to_neighbors = [&](const std::shared_ptr<std::vector<Cell*>>& sec) {
                if (!sec) return true;
                for (Cell* neighbor : *sec) {
                    if (neighbor != cell && (candidates[neighbor] & mask)) {
                        uint16_t old_mask = candidates[neighbor];
                        candidates[neighbor] &= ~mask;
                        changed = true;
                        
                        if (candidates[neighbor] == 0) return false; // Contradiction
                        
                        if (popcount9(old_mask) > 1 && popcount9(candidates[neighbor]) == 1) {
                            to_process.push(neighbor);
                        }
                    }
                }
                return true;
            };

            if (!propagate_to_neighbors(cell->sector_h)) goto contradiction;
            if (!propagate_to_neighbors(cell->sector_v)) goto contradiction;
        
        }
        
        // 2. Hidden singles (one pass)
        auto check_hidden_singles_once = [&]() {
            bool found = false;
            auto process_sectors = [&](const std::vector<std::shared_ptr<std::vector<Cell*>>>& sectors) {
                    for (const auto& sector : sectors) {
                        if (sector->empty()) continue;
                        std::array<int, 10> digit_count = {0};
                        std::array<Cell*, 10> digit_cell = {nullptr};
                        for (Cell* cell : *sector) {
                            uint16_t mask = candidates[cell];
                            for (int d = 1; d <= 9; d++) {
                                if (mask & (1 << d)) {
                                    digit_count[d]++;
                                    digit_cell[d] = cell;
                                }
                            }
                        }
                        for (int d = 1; d <= 9; d++) {
                            if (digit_count[d] == 1 && digit_cell[d]) {
                                Cell* cell = digit_cell[d];
                                if (popcount9(candidates[cell]) > 1) {
                                    candidates[cell] = (1 << d);
                                    found = true;
                                    changed = true; // Mark global change
                                    // Sync value
                                    cell->value = d;
                                }
                            }
                        }
                    }
                };
                process_sectors(board_->sectors_h);
                process_sectors(board_->sectors_v);
                return found;
            };
            
            if (check_hidden_singles_once()) {
                changed = true;
            }

            // 3. Partition Pruning (Moved to end of loop as requested)
            // Check returned false if contradiction occurred inside
            if (apply_partition_pruning(board_->sectors_h, true)) changed = true;
            else {
                // Check for actual contradiction (empty mask)
                for(auto c : board_->white_cells) if(candidates[c] == 0) goto contradiction;
            }

            if (apply_partition_pruning(board_->sectors_v, false)) changed = true;
            else {
                for(auto c : board_->white_cells) if(candidates[c] == 0) goto contradiction;
            }

            if (!changed) break; 
            any_change = true;
        }
        
        return any_change;

contradiction:
    // Restore logic state values on contradiction
    for(auto& p : local_val_backup) p.first->value = p.second;
    return false; // Actually implies failure/contradiction in this context
}

void HybridUniquenessChecker::hybrid_search(
    std::vector<std::unordered_map<std::pair<int, int>, int, PairHash>>& found_solutions,
    const std::unordered_map<std::pair<int, int>, int, PairHash>& avoid_sol,
    CandidateMap& candidates,
    int& node_count,
    int max_nodes,
    int seed,
    bool& timed_out) {
    
    if (!found_solutions.empty()) return;
    if (node_count > max_nodes) {
        timed_out = true;
        return;
    }
    node_count++;

#if KAKURO_ENABLE_LOGGING
    if (node_count % 1000 == 0 && board_->logger && board_->logger->is_enabled()) {
        std::unordered_map<Cell *, int> viz_map;
        int determined = 0;
        for (auto &[c, m] : candidates) {
            if (popcount9(m) == 1) {
                determined++;
                int val = 0;
                for(int d=1; d<=9; d++) { if(m & (1<<d)) { val=d; break; } }
                if(val) viz_map[c] = val;
            }
        }
        board_->logger->log_step(
            GenerationLogger::STAGE_UNIQUENESS,
            "search_step",
            "Hybrid search: " + std::to_string(node_count) + " nodes, " + std::to_string(determined) + " cells determined",
            board_->get_grid_state(&viz_map));
    }
#endif
    
    // **FIX 1: First, assign all logically determined values to cell->value**
    // This ensures constraint checking sees them
    for (Cell* c : board_->white_cells) {
        uint16_t mask = candidates[c];
        if (popcount9(mask) == 1 && !c->value.has_value()) {
            // Extract the single value
            for (int d = 1; d <= 9; d++) {
                if (mask & (1 << d)) {
                    c->value = d;
                    break;
                }
            }
        }
    }

    // Find first cell that needs assignment (has multiple candidates)
    Cell* var = nullptr;
    int min_candidates = 10;
    for (Cell* c : board_->white_cells) {
        int candidate_count = popcount9(candidates[c]);
        if (candidate_count == 0) return; // Contradiction
        if (candidate_count > 1 && candidate_count < min_candidates) {
            min_candidates = candidate_count;
            var = c;
        }
    }
    
    // All cells are determined (have exactly 1 candidate) - we have a complete solution
    if (!var) {
        // Build the solution from candidate masks (NOT cell->value)
        std::unordered_map<std::pair<int, int>, int, PairHash> sol;
        bool is_different = false;
        
        for (Cell* c : board_->white_cells) {
            if (!c->value.has_value()) {
                // This shouldn't happen if all_determined is true
                return;
            }
            int val = *c->value;
            sol[{c->r, c->c}] = val;
            if (avoid_sol.count({c->r, c->c}) && val != avoid_sol.at({c->r, c->c})) {
                is_different = true;
            }
        }
        
        if (is_different) {
            found_solutions.push_back(sol);
#if KAKURO_ENABLE_LOGGING
            if (board_->logger && board_->logger->is_enabled()) {
                std::unordered_map<Cell*, int> alt_map;
                std::unordered_map<Cell*, int> orig_map;
                std::vector<std::pair<int, int>> highlights;
                
                // Populate maps
                for(Cell* c : board_->white_cells) {
                    // Alternative solution
                    if (sol.count({c->r, c->c})) {
                        alt_map[c] = sol.at({c->r, c->c});
                    }
                    
                    // Original solution (avoid_sol)
                    if (avoid_sol.count({c->r, c->c})) {
                        orig_map[c] = avoid_sol.at({c->r, c->c});
                    }
                    
                    // Highlight differences
                    if (alt_map.count(c) && orig_map.count(c) && alt_map[c] != orig_map[c]) {
                        highlights.push_back({c->r, c->c});
                    }
                }
                
                auto main_grid = board_->get_grid_state(&orig_map);
                auto alt_grid = board_->get_grid_state(&alt_map);
                
                board_->logger->log_step_with_highlights(
                    GenerationLogger::STAGE_UNIQUENESS,
                    "alternative_found",
                    "Non-unique solution found! (Overlay shows alternative)",
                    main_grid,
                    highlights, 
                    alt_grid);
            }
#endif
        }
        return;
    }
    
    // Try values from candidate set
    std::vector<int> values = mask_to_values(candidates[var]);
    
    // Deprioritize the value from the original solution
    int avoid_val = avoid_sol.at({var->r, var->c});
    std::partition(values.begin(), values.end(), 
                   [avoid_val](int v) { return v != avoid_val; });
    
    for (int val : values) {
        // Save the original candidate mask for var
        uint16_t var_orig_mask = candidates[var];
        std::optional<int> var_orig_value = var->value;

        candidates[var] = (1 << val);
        var->value = val;
        
        std::vector<std::pair<Cell*, uint16_t>> saved_candidates;
        std::vector<std::pair<Cell*, std::optional<int>>> saved_values;

        saved_candidates.reserve(20);
        saved_values.reserve(20);
        
        bool conflict = false;

        // Propagate assignment (simple forward checking)
        auto propagate = [&](const std::shared_ptr<std::vector<Cell*>>& sec) {
            if (!sec) return true;
            for (Cell* n : *sec) {
                if (n == var) continue;
                if (n->value.has_value() && *n->value == val) return false;
                
                uint16_t old_mask = candidates[n];
                if (old_mask & (1 << val)) {
                    uint16_t new_mask = old_mask & ~(1 << val);
                    if (new_mask == 0) return false;
                    
                    saved_candidates.push_back({n, old_mask});
                    candidates[n] = new_mask;
                    
                    if (popcount9(new_mask) == 1 && !n->value.has_value()) {
                        for(int d=1; d<=9; d++) if(new_mask & (1<<d)) {
                            saved_values.push_back({n, n->value});
                            n->value = d;
                            break;
                        }
                    }
                }
            }
            return true;
        };

        if (!propagate(var->sector_h)) conflict = true;
        if (!conflict && !propagate(var->sector_v)) conflict = true;
        
        if (!conflict) {
             hybrid_search(found_solutions, avoid_sol, candidates,
                         node_count, max_nodes, seed, timed_out);
        }
        
        // **FIX 6: Restore BOTH candidates and cell values**
        candidates[var] = var_orig_mask;
        var->value = var_orig_value;
        
        for (auto& [cell, old_mask] : saved_candidates) {
            candidates[cell] = old_mask;
        }
        
        for (auto& [cell, old_value] : saved_values) {
            cell->value = old_value;
        }
        
        if (!found_solutions.empty() || timed_out) return;
    }
}

std::vector<int> HybridUniquenessChecker::mask_to_values(uint16_t mask) const {
    std::vector<int> result;
    for (int d = 1; d <= 9; d++) {
        if (mask & (1 << d)) {
            result.push_back(d);
        }
    }
    return result;
}


bool HybridUniquenessChecker::is_valid_with_candidates(
    Cell* cell, int val, const CandidateMap& candidates) {
    
    // Check if val is in the candidate set
    if (!(candidates.at(cell) & (1 << val))) {
        return false;
    }
    
    // Check horizontal sector
    if (cell->sector_h) {
        for (Cell* n : *(cell->sector_h)) {
            if (n->value.has_value() && *n->value == val) {
                return false;
            }
        }
    }
    
    // Check vertical sector
    if (cell->sector_v) {
        for (Cell* n : *(cell->sector_v)) {
            if (n->value.has_value() && *n->value == val) {
                return false;
            }
        }
    }
    
    return true;
}

} // namespace kakuro