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

    // DEBUG: Verify that original_sol is actually valid for this topology
    {
        PROFILE_SCOPE("Uniqueness_IntegrityCheck", board_->logger);
        bool integrity_fail = false;
        
        auto check_integrity = [&](const std::vector<std::shared_ptr<std::vector<Cell*>>>& sectors, bool is_horz) {
            for (const auto& sec : sectors) {
                if (sec->empty()) continue;
                Cell* first = (*sec)[0];
                std::optional<int> clue_opt;
                if (is_horz && first->c > 0) clue_opt = board_->grid[first->r][first->c - 1].clue_h;
                else if (!is_horz && first->r > 0) clue_opt = board_->grid[first->r - 1][first->c].clue_v;
                
                if (!clue_opt) {
                    LOG_ERROR("[INTEGRITY ERROR] Sector at (" << first->r << "," << first->c << ") has no clue!");
                    integrity_fail = true;
                    continue;
                }
                
                int target = *clue_opt;
                int sum = 0;
                uint16_t used_mask = 0;
                std::vector<int> vals;
                
                for (Cell* c : *sec) {
                    if (original_sol.count(c)) {
                        int v = original_sol.at(c);
                        if (used_mask & (1 << v)) {
                            LOG_ERROR("[INTEGRITY ERROR] Duplicate value " << v << " in sector at (" << first->r << "," << first->c << ")");
                            integrity_fail = true;
                        }
                        used_mask |= (1 << v);
                        sum += v;
                        vals.push_back(v);
                    } else {
                        LOG_ERROR("[INTEGRITY ERROR] White cell (" << c->r << "," << c->c << ") missing from original_sol!");
                        integrity_fail = true;
                    }
                }
                
                if (sum != target) {
                    std::string val_str;
                    for(int v : vals) val_str += std::to_string(v) + " ";
                    LOG_ERROR("[INTEGRITY ERROR] Sector sum mismatch! Clue: " << target << " Actual: " << sum << " Values: " << val_str << " (is_horz=" << is_horz << ")");
                    integrity_fail = true;
                }
            }
        };
        
        check_integrity(board_->sectors_h, true);
        check_integrity(board_->sectors_v, false);
        
        if (integrity_fail) {
            LOG_ERROR("ABORTING UNIQUENESS CHECK: Topology/Solution integrity failed!");
            // return {UniquenessResult::INCONCLUSIVE, std::nullopt}; // Don't abort yet, let's see how search fails
        }
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
                
                // FIX: Use proper partition-based filtering instead of loose bounds
                // Generate all valid partitions for this clue/length
                std::vector<std::vector<int>> valid_partitions;
                {
                    std::vector<int> cur;
                    std::function<void(int, int, int)> gen_partitions = [&](int remaining, int slots, int start) {
                        if (slots == 0) {
                            if (remaining == 0) valid_partitions.push_back(cur);
                            return;
                        }
                        for (int d = start; d <= 9; d++) {
                            if (d > remaining) break;
                            cur.push_back(d);
                            gen_partitions(remaining - d, slots - 1, d + 1);
                            cur.pop_back();
                        }
                    };
                    gen_partitions(target, length, 1);
                }
                
                if (valid_partitions.empty()) continue; // No valid partitions exist
                
                // Build a mask of all digits that appear in ANY valid partition
                uint16_t valid_digits_mask = 0;
                for (const auto& partition : valid_partitions) {
                    for (int d : partition) {
                        valid_digits_mask |= (1 << d);
                    }
                }
                
                // Apply this mask to all cells in the sector
                for (Cell* cell : *sector) {
                    candidates[cell] &= valid_digits_mask;
                }
            }
        };
        
        init_sector_constraints(board_->sectors_h, true);
        init_sector_constraints(board_->sectors_v, false);
        
        // DEBUG: Validate that original solution values are still in candidates
        bool init_valid = true;
        for (Cell* c : board_->white_cells) {
            if (original_sol.count(c)) {
                int sol_val = original_sol[c];
                if (!(candidates[c] & (1 << sol_val))) {
                    init_valid = false;
                    LOG_ERROR("INIT VALIDATION FAILED: Cell (" << c->r << "," << c->c << ") original value " << sol_val << " is not in candidates after init! Candidates mask: " << candidates[c]);
                    
                    // Log sector info for debugging
                    if (c->sector_h) {
                        Cell* first_h = (*c->sector_h)[0];
                        std::optional<int> clue_h;
                        if (first_h->c > 0) clue_h = board_->grid[first_h->r][first_h->c - 1].clue_h;
                        LOG_ERROR("  H-sector: length=" << c->sector_h->size() << ", clue=" << (clue_h ? std::to_string(*clue_h) : "NONE"));
                    }
                    if (c->sector_v) {
                        Cell* first_v = (*c->sector_v)[0];
                        std::optional<int> clue_v;
                        if (first_v->r > 0) clue_v = board_->grid[first_v->r - 1][first_v->c].clue_v;
                        LOG_ERROR("  V-sector: length=" << c->sector_v->size() << ", clue=" << (clue_v ? std::to_string(*clue_v) : "NONE"));
                    }
                }
            }
        }
        if (!init_valid) {
            LOG_ERROR("Initial constraint filtering eliminated valid solution values!");
        }
    }

    // 5. Count how many cells are logically determined
    int determined_cells = 0;
    int total_candidates_start = 0;
    for (auto& [cell, mask] : candidates) {
        if (popcount9(mask) == 1) {
            determined_cells++;
        }
        total_candidates_start += popcount9(mask);
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
        ReductionResult result = apply_logical_reduction(candidates, original_sol_coords);
        
        if (result == ReductionResult::CHANGED) reduced = true;
        
        // Validation: Check for empty candidates (Contradiction)
        if (result == ReductionResult::CONTRADICTION) {
            logic_consistent = false;
        } else {
             for (auto& [c, m] : candidates) {
                if (m == 0) {
                    logic_consistent = false;
                    break;
                }
            }
        }
    }
    
    int total_candidates_end = 0;
    
    if (!logic_consistent) {
        LOG_DEBUG("    Logical reduction caused contradiction! Reverting to full search.");
        candidates = candidates_backup; // Restore
        // FIX: Restore values
        for(auto& p : value_backup) {
            p.first->value = p.second;
        }

        determined_cells = 0; 
        total_candidates_end = total_candidates_start; // Reverted, so no change
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
    
        // FIX: Count determined cells AFTER logical reduction succeeds
        determined_cells = 0;
        for (auto& [cell, mask] : candidates) {
            if (popcount9(mask) == 1) {
                determined_cells++;
            }
            total_candidates_end += popcount9(mask);
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
        std::string log_msg = "Logical reduction complete: " + std::to_string(determined_cells) + " cells determined";
        if (total_candidates_start > 0) {
             int removed = total_candidates_start - total_candidates_end;
             double pct = 100.0 * removed / total_candidates_start;
             log_msg += ", reduced candidates: " + std::to_string(total_candidates_start) + " -> " + std::to_string(total_candidates_end) + " (-" + std::to_string((int)pct) + "%)";
        }
        board_->logger->log_step(
            GenerationLogger::STAGE_UNIQUENESS,
            GenerationLogger::SUBSTAGE_LOGIC_STEP,
            log_msg,
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
        
        // Prepare visualization map for alternative solution
        std::unordered_map<Cell*, int> viz_map;
        bool show_alt = false;

        if (timed_out) {
            search_status += " Timed out. Assuming UNIQUE.";

            board_->logger->log_step(
                GenerationLogger::STAGE_UNIQUENESS,
                "hybrid_result",
                search_status,
                board_->get_grid_state()
            );

        } else if (!found.empty()) {
            search_status += " Found alternative solution.";
            show_alt = true;
            
            // Map the found solution (coords -> value) back to Cell* -> value
            const auto& alt_sol = found[0];
            
            std::vector<std::pair<int, int>> highlights;
            for (Cell* c : board_->white_cells) {
                if (alt_sol.count({c->r, c->c})) {
                    viz_map[c] = alt_sol.at({c->r, c->c});
                }
                
                // Compare alternative with original (original_sol_coords)
                if (viz_map.count(c) && original_sol_coords.count({c->r, c->c})) {
                    if (viz_map[c] != original_sol_coords.at({c->r, c->c})) {
                        highlights.push_back({c->r, c->c});
                    }
                }
            }


            board_->logger->log_step_with_highlights(
                GenerationLogger::STAGE_UNIQUENESS,
                "hybrid_result",
                search_status,
                board_->get_grid_state(),
                highlights,
                board_->get_grid_state(&viz_map)
            );
        } else {
            search_status += " No alternative found.";

            board_->logger->log_step(
                GenerationLogger::STAGE_UNIQUENESS,
                "hybrid_result",
                search_status,
                board_->get_grid_state()
            );
        }
        
        
    }
#endif
    
    if (!found.empty()) {
        return {UniquenessResult::MULTIPLE, found[0]};
    }
    if (timed_out) {
        LOG_INFO("Hybrid search timed out (" << node_count << " nodes). Assuming UNIQUE.");
    }
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
    
    // Use bitmask for used cells (sector size <= 9)
    // fixed_cell_idx is already 'used'
    int used_mask = (1 << fixed_cell_idx);
    
    return can_match_values_to_cells(partition_copy, sector, candidates, used_mask);
}

bool HybridUniquenessChecker::can_match_values_to_cells(
    const std::vector<int>& values,
    const std::vector<Cell*>& sector,
    const CandidateMap& candidates,
    int used_mask) {
    
    if (values.empty()) return true; // All values assigned
    
    int val = values[0];
    
    // We pass slice of values by index/pointer to avoid copying vector every time? 
    // Actually, vector copy for size < 9 is very fast (simd). Keeping it simple.
    std::vector<int> remaining_values(values.begin() + 1, values.end());
    
    for (int i = 0; i < sector.size(); i++) {
        if (used_mask & (1 << i)) continue; // Skip used cells
        
        Cell* cell = sector[i];
        
        // Strict check: if cell has a value, it MUST match 'val'. 
        // If it matches 'val', we are good. If it has a DIFFERENT value, we can't use this cell for 'val'.
        if (cell->value.has_value() && *cell->value != val) {
            continue;
        }
        
        uint16_t mask = candidates.at(cell);
        
        // standard candidate check
        if (mask & (1 << val)) {
            if (can_match_values_to_cells(remaining_values, sector, candidates, used_mask | (1 << i))) {
                return true;
            }
        }
    }
    
    return false;
}



HybridUniquenessChecker::ReductionResult HybridUniquenessChecker::apply_logical_reduction(
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



    auto apply_partition_pruning = [&](const std::vector<std::shared_ptr<std::vector<Cell*>>>& sectors, bool is_horz, const CandidateMap& reference_candidates) -> ReductionResult {
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
                return ReductionResult::CONTRADICTION; 
            }
            
            for (int cell_idx = 0; cell_idx < len; cell_idx++) {
                Cell* c = (*sector)[cell_idx];
                // FIX: Read old_mask from REFERENCE (snapshot) candidates, not mutating candidates
                // This ensures we use consistent state when checking partition assignments
                uint16_t old_mask = reference_candidates.at(c);
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
                        
                        // FIX: Use reference_candidates (snapshot) for checking, not mutating candidates
                        // This prevents cascading incorrect eliminations
                        if (can_assign_partition_to_sector(partition, *sector, reference_candidates, cell_idx, val)) {
                            found_valid_assignment = true;
                            break;
                        }
                    }
                    
                    if (found_valid_assignment) {
                        new_mask |= (1 << val);
                    }
                }
                
                if (new_mask != old_mask) {
                    // Soundness check: Did we just eliminate the correct value?
                    if (avoid_sol.count({c->r, c->c})) {
                        int correct_val = avoid_sol.at({c->r, c->c});
                        if ((old_mask & (1 << correct_val)) && !(new_mask & (1 << correct_val))) {
                            LOG_ERROR("[SOUNDNESS BUG] Partition pruning eliminated correct value " << correct_val << " for cell (" << c->r << "," << c->c << ")!");
                            LOG_ERROR("  Sector: " << (is_horz ? "H" : "V") << " Target: " << target << " Len: " << len);
                        }
                    }

                    candidates[c] = new_mask;
                    local_change = true;
                    if (new_mask == 0) {
                        // DEBUG: Log detailed contradiction info
                        LOG_ERROR("CONTRADICTION in partition pruning: Cell (" << c->r << "," << c->c << ") has no valid candidates for any partition");
                        LOG_ERROR("  Target sum: " << target << ", Sector length: " << len);
                        LOG_ERROR("  Old mask (before pruning): " << old_mask);
                        LOG_ERROR("  Valid partitions for this sector:");
                        for (const auto& p : valid_partitions) {
                            std::string pstr = "{";
                            for (size_t pidx = 0; pidx < p.size(); pidx++) {
                                if (pidx > 0) pstr += ",";
                                pstr += std::to_string(p[pidx]);
                            }
                            pstr += "}";
                            LOG_ERROR("    " << pstr);
                        }
                        LOG_ERROR("  Reference candidates for other cells in sector:");
                        for (int idx = 0; idx < len; idx++) {
                            Cell* sc = (*sector)[idx];
                            LOG_ERROR("    Cell (" << sc->r << "," << sc->c << "): mask=" << reference_candidates.at(sc));
                        }
#if KAKURO_ENABLE_LOGGING
                        if (board_->logger && board_->logger->is_enabled()) {
                            board_->logger->log_step(
                                GenerationLogger::STAGE_UNIQUENESS,
                                "contradiction_debug",
                                "Partition pruning contradiction: Cell (" + std::to_string(c->r) + "," + std::to_string(c->c) + ") has no valid values for target=" + std::to_string(target) + " len=" + std::to_string(len),
                                board_->get_grid_state());
                        }
#endif
                        return ReductionResult::CONTRADICTION; // Contradiction
                    }
                }
            }
        }

        return local_change ? ReductionResult::CHANGED : ReductionResult::NO_CHANGE; 
    };


    bool any_change = false;
    int iterations = 0;
    const int MAX_QUICK_ITERATIONS = 10; // Increased slightly
    
    while (iterations++ < MAX_QUICK_ITERATIONS) {
        bool changed = false;
        
        // FIX: Take a snapshot of candidates at the start of each iteration
        // This prevents cascading incorrect eliminations in partition pruning
        CandidateMap candidates_snapshot = candidates;

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
            
            auto propagate_to_neighbors = [&](const std::shared_ptr<std::vector<Cell*>>& sec, const char* sec_name) {
                if (!sec) return true;
                for (Cell* neighbor : *sec) {
                    if (neighbor != cell && (candidates[neighbor] & mask)) {
                        uint16_t old_mask = candidates[neighbor];
                        candidates[neighbor] &= ~mask;
                        changed = true;
                        
                        if (candidates[neighbor] == 0) {
                            // DEBUG: Log contradiction source
                            LOG_ERROR("CONTRADICTION in naked singles propagation: Cell (" << neighbor->r << "," << neighbor->c << ") became empty after removing value from cell (" << cell->r << "," << cell->c << ") via " << sec_name << " sector");
#if KAKURO_ENABLE_LOGGING
                            if (board_->logger && board_->logger->is_enabled()) {
                                board_->logger->log_step(
                                    GenerationLogger::STAGE_UNIQUENESS,
                                    "contradiction_debug",
                                    "Naked singles contradiction: Cell (" + std::to_string(neighbor->r) + "," + std::to_string(neighbor->c) + ") candidates=0 after removing value from (" + std::to_string(cell->r) + "," + std::to_string(cell->c) + ")",
                                    board_->get_grid_state());
                            }
#endif
                            return false; // Contradiction
                        }
                        
                        if (popcount9(old_mask) > 1 && popcount9(candidates[neighbor]) == 1) {
                            to_process.push(neighbor);
                        }
                    }
                }
                return true;
            };

            if (!propagate_to_neighbors(cell->sector_h, "horizontal")) goto contradiction;
            if (!propagate_to_neighbors(cell->sector_v, "vertical")) goto contradiction;
        
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
            
            /* 
            // HIDDEN SINGLES - DISABLED
            // This heuristic is incorrect for Kakuro because a sector doesn't contain all digits.
            // Just because a digit D fits in only one cell doesn't mean D must be used!
            if (check_hidden_singles_once()) {
                changed = true;
            }
            */

            // 3. Partition Pruning (Moved to end of loop as requested)
            // Check returned false if contradiction occurred inside
            // 3. Partition Pruning (Moved to end of loop as requested)
            // Check returned false if contradiction occurred inside
            // 3. Partition Pruning (Restored)
            ReductionResult h_res = apply_partition_pruning(board_->sectors_h, true, candidates_snapshot);
            if (h_res == ReductionResult::CONTRADICTION) goto contradiction;
            if (h_res == ReductionResult::CHANGED) changed = true;
            else {
                // Check for actual contradiction (empty mask)
                 for(auto c : board_->white_cells) if(candidates[c] == 0) goto contradiction;
            }

            ReductionResult v_res = apply_partition_pruning(board_->sectors_v, false, candidates_snapshot);
            if (v_res == ReductionResult::CONTRADICTION) goto contradiction;
            if (v_res == ReductionResult::CHANGED) changed = true;
            else {
                for(auto c : board_->white_cells) if(candidates[c] == 0) goto contradiction;
            }

            if (!changed) break; 

            // Soundness check after each iteration
            for (Cell* c : board_->white_cells) {
                if (avoid_sol.count({c->r, c->c})) {
                    int correct_val = avoid_sol.at({c->r, c->c});
                    if (!(candidates[c] & (1 << correct_val))) {
                        LOG_ERROR("[SOUNDNESS BUG] Logical reduction incorrectly eliminated correct value " << correct_val << " for cell (" << c->r << "," << c->c << ")!");
                    }
                    if (c->value.has_value() && *c->value != correct_val) {
                        LOG_ERROR("[SOUNDNESS BUG] Logical reduction incorrectly assigned value " << *c->value << " to cell (" << c->r << "," << c->c << "). Should be " << correct_val << "!");
                    }
                }
            }
            any_change = true;
        }
        
        return any_change ? ReductionResult::CHANGED : ReductionResult::NO_CHANGE;

contradiction:
    // Restore logic state values on contradiction
    for(auto& p : local_val_backup) p.first->value = p.second;
    return ReductionResult::CONTRADICTION;
}

void HybridUniquenessChecker::hybrid_search(
    std::vector<std::unordered_map<std::pair<int, int>, int, PairHash>>& found_solutions,
    const std::unordered_map<std::pair<int, int>, int, PairHash>& avoid_sol,
    CandidateMap& candidates,
    int& node_count,
    int max_nodes,
    int seed,
    bool& timed_out,
    bool is_on_avoid_path) {
    
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
    
    // RAII helper to restore values of determined cells upon return
    // This prevents "leakage" of temporary values to sibling search branches (Soundness fix)
    struct DeterminedValueRestorer {
        std::vector<Cell*> cells;
        ~DeterminedValueRestorer() {
             for (Cell* c : cells) c->value = std::nullopt;
        }
    };
    DeterminedValueRestorer determined_updates;

    // **FIX 1: First, assign all logically determined values to cell->value**
    // This ensures constraint checking sees them
    for (Cell* c : board_->white_cells) {
        uint16_t mask = candidates[c];
        if (popcount9(mask) == 1 && !c->value.has_value()) {
            // Extract the single value
            for (int d = 1; d <= 9; d++) {
                if (mask & (1 << d)) {
                    c->value = d;
                    determined_updates.cells.push_back(c);
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
        
        // Populate solution map
        for (Cell* c : board_->white_cells) {
             if (!c->value.has_value()) {
                 // Fallback to extraction from mask if value not set (shouldn't happen with FIX 1 logic, but safer)
                uint16_t mask = candidates[c];
                int val = 0;
                for(int d=1; d<=9; d++) if(mask & (1<<d)) { val=d; break; }
                if (val == 0) return; // Should not happen
                sol[{c->r, c->c}] = val;
             } else {
                 sol[{c->r, c->c}] = *c->value;
             }
        }

        // FIX: Verify that the solution satisfies ALL sum constraints
        // The propagation only checked "all different", not sums!
        for (const auto& sector : board_->sectors_h) {
            if (sector->empty()) continue;
            Cell* first = (*sector)[0];
            if (first->c == 0) continue; // Should have header
            auto clue = board_->grid[first->r][first->c - 1].clue_h;
            if (!clue) continue;
            
            int sum = 0;
            for (Cell* c : *sector) {
                sum += sol[{c->r, c->c}];
            }
            if (sum != *clue) {
                LOG_ERROR("Invalid sum for sector " << first->r << ", " << first->c << ": " << sum << " != " << *clue);
                return; // Invalid sum
            }
        }
        for (const auto& sector : board_->sectors_v) {
            if (sector->empty()) continue;
            Cell* first = (*sector)[0];
            if (first->r == 0) continue; // Should have header
            auto clue = board_->grid[first->r - 1][first->c].clue_v;
            if (!clue) continue;
            
            int sum = 0;
            for (Cell* c : *sector) {
                sum += sol[{c->r, c->c}];
            }
            if (sum != *clue) {
                LOG_ERROR("Invalid sum for sector " << first->r << ", " << first->c << ": " << sum << " != " << *clue);
                return; // Invalid sum
            }
        }

        // Check difference from original solution
        for (const auto& [coords, val] : sol) {
            if (avoid_sol.count(coords) && val != avoid_sol.at(coords)) {
                is_different = true;
                break;
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
        bool is_correct_val = (val == avoid_val);
        bool next_on_avoid_path = (is_on_avoid_path && is_correct_val);

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

        // Propagate assignment (simple forward checking + sum reasoning)
        auto propagate = [&](const std::shared_ptr<std::vector<Cell*>>& sec, bool is_horizontal) {
            if (!sec) return true;
            
            Cell* first = (*sec)[0];
            int target = 0;
            if (is_horizontal) {
                // Horizontal sector: clue is to the left
                 if (first->c > 0 && board_->grid[first->r][first->c-1].clue_h)
                    target = *board_->grid[first->r][first->c-1].clue_h;
            } else {
                // Vertical sector: clue is above
                 if (first->r > 0 && board_->grid[first->r-1][first->c].clue_v)
                    target = *board_->grid[first->r-1][first->c].clue_v;
            }
            if (target == 0) return true; // Should not happen for valid sectors

            int current_sum = 0;
            int unknown_count = 0;
            int min_remaining = 0;
            int max_remaining = 0;

            for (Cell* n : *sec) {
                if (n->value.has_value()) {
                    // Check duplicate
                    if (n != var && *n->value == val) {
                        // Soundness check: Only if we are on the correct path and val is the correct one for var
                        if (next_on_avoid_path) {
                            if (avoid_sol.count({n->r, n->c}) && avoid_sol.at({n->r, n->c}) == *n->value) {
                                LOG_ERROR("[SOUNDNESS BUG] Pruning duplicate value " << val << " in sector that should contain it according to avoid_sol!");
                            }
                        }
                        return false;
                    }
                    current_sum += *n->value;
                } else {
                    unknown_count++;
                    // Estimate bounds for remaining cells
                    uint16_t mask = candidates[n];
                    // If n == var, we shouldn't be here since var has value, but just in case
                    if (n == var) { current_sum += val; continue; }
                    
                    // Simple update: remove 'val' from candidates of neighbors
                    if (mask & (1 << val)) {
                         uint16_t old_mask = mask;
                         uint16_t new_mask = old_mask & ~(1 << val);
                         if (new_mask == 0) {
                             if (next_on_avoid_path && avoid_sol.count({n->r, n->c}) && avoid_sol.at({n->r, n->c}) == val) {
                                 LOG_ERROR("[SOUNDNESS BUG] Domain empty for cell (" << n->r << "," << n->c << ") because " << val << " was removed, but it's the correct value!");
                             }
                             return false; 
                         }
                         
                         // Temporarily update mask for bound calculation (commit to map)
                         if (candidates[n] != new_mask) {
                             saved_candidates.push_back({n, old_mask});
                             candidates[n] = new_mask;
                             mask = new_mask;
                             
                             // Soundness check
                             if (next_on_avoid_path && avoid_sol.count({n->r, n->c})) {
                                 int correct_val = avoid_sol.at({n->r, n->c});
                                 if (!(new_mask & (1 << correct_val))) {
                                     LOG_ERROR("[SOUNDNESS BUG] Removed correct value " << correct_val << " from cell (" << n->r << "," << n->c << ") candidates!");
                                 }
                             }
                         }
                    }
                    
                    // Add min/max candidates to bounds
                    int local_min = 10, local_max = 0;
                    for(int d=1; d<=9; d++) {
                        if (mask & (1<<d)) {
                            if (d < local_min) local_min = d;
                            if (d > local_max) local_max = d;
                        }
                    }
                    min_remaining += local_min;
                    max_remaining += local_max;
                }
            }
            
            // Check sum feasibility
            auto check_soundness_on_failure = [&](const std::string& reason) {
                if (!next_on_avoid_path) return;
                // Check if the original solution satisfies this sector
                int sol_sum = 0;
                bool sol_possible = true;
                std::string debug_vals = "";
                for (Cell* n : *sec) {
                    if (!avoid_sol.count({n->r, n->c})) { sol_possible = false; break; }
                    int val_in_sol = avoid_sol.at({n->r, n->c});
                    sol_sum += val_in_sol;
                    
                    debug_vals += "(" + std::to_string(n->r) + "," + std::to_string(n->c) + "):";
                    if (n->value.has_value()) debug_vals += "v=" + std::to_string(*n->value);
                    else debug_vals += "cmask=" + std::to_string(candidates[n]);
                    debug_vals += "[sol=" + std::to_string(val_in_sol) + "] ";
                }
                if (sol_possible && sol_sum == target) {
                    LOG_ERROR("[SOUNDNESS BUG] Pruning valid path. Reason: " << reason << " Target: " << target << " Sum: " << current_sum << " Var: (" << var->r << "," << var->c << ")=" << val);
                    LOG_ERROR("  Sector details: " << debug_vals);
                }
            };

            if (current_sum > target) {
                 check_soundness_on_failure("Sum exceeded target " + std::to_string(target) + " current=" + std::to_string(current_sum));
                 return false;
            }
            // If filled, check exact match
            if (unknown_count == 0) {
                if (current_sum != target) {
                    check_soundness_on_failure("Sector full but sum " + std::to_string(current_sum) + " != target " + std::to_string(target));
                    return false;
                }
            } else {
                // Check if target is reachable
                if (current_sum + min_remaining > target) {
                    check_soundness_on_failure("Target " + std::to_string(target) + " unreachable (min possible " + std::to_string(current_sum + min_remaining) + ")");
                    return false;
                }
                if (current_sum + max_remaining < target) {
                    check_soundness_on_failure("Target " + std::to_string(target) + " unreachable (max possible " + std::to_string(current_sum + max_remaining) + ")");
                    return false;
                }
            }

            return true;
        };

        if (!propagate(var->sector_h, true)) conflict = true;
        if (!conflict && !propagate(var->sector_v, false)) conflict = true;
        
        if (!conflict) {
             hybrid_search(found_solutions, avoid_sol, candidates,
                         node_count, max_nodes, seed, timed_out, next_on_avoid_path);
        }
        
        // **FIX 6: Restore BOTH candidates and cell values**
        candidates[var] = var_orig_mask;
        var->value = var_orig_value;
        
        // **IMPORTANT: Restore candidates in REVERSE order to handle multiple updates to same cell**
        for (int i = (int)saved_candidates.size() - 1; i >= 0; i--) {
            candidates[saved_candidates[i].first] = saved_candidates[i].second;
        }
        
        for (int i = (int)saved_values.size() - 1; i >= 0; i--) {
            saved_values[i].first->value = saved_values[i].second;
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