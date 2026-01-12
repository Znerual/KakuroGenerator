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
                    }
                }
            }
        };
        
        init_sector_constraints(board_->sectors_h, true);
        init_sector_constraints(board_->sectors_v, false);
    }
    
    // 4. Apply logical deduction to reduce search space
    bool reduced = false;
    {
        PROFILE_SCOPE("Uniqueness_LogicalReduction", board_->logger);
        reduced = apply_logical_reduction(candidates, original_sol_coords);
    }
    
    LOG_DEBUG("    Logical reduction: " << (reduced ? "SUCCESS" : "NONE") 
              << " (reduced search space)");
    
    // 5. Count how many cells are logically determined
    int determined_cells = 0;
    for (auto& [cell, mask] : candidates) {
        if (count_set_bits(mask) == 1) {
            determined_cells++;
        }
    }
    LOG_DEBUG("    Cells logically determined: " << determined_cells 
              << "/" << board_->white_cells.size());


#if KAKURO_ENABLE_LOGGING
    if (board_->logger && board_->logger->is_enabled()) {
        std::unordered_map<Cell *, int> viz_map;
        for (auto &[c, m] : candidates) {
            if (count_set_bits(m) == 1) {
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
    
    if (!found.empty()) {
        return {UniquenessResult::MULTIPLE, found[0]};
    }
    if (timed_out)
        return {UniquenessResult::INCONCLUSIVE, std::nullopt};
    return {UniquenessResult::UNIQUE, std::nullopt};
}

bool HybridUniquenessChecker::apply_logical_reduction(
    CandidateMap& candidates,
    const std::unordered_map<std::pair<int, int>, int, PairHash>& avoid_sol) {
    
    bool any_change = false;
    int iterations = 0;
    const int MAX_QUICK_ITERATIONS = 3; // Much lower limit for speed
    
    // Quick pass: only do the fastest techniques
    while (iterations++ < MAX_QUICK_ITERATIONS) {
        bool changed = false;
        
        // 1. FASTEST: Naked singles propagation only
        // When a cell is determined, remove its value from neighbors
        for (Cell* cell : board_->white_cells) {
            uint16_t mask = candidates[cell];
            if (count_set_bits(mask) != 1) continue;
            
            // Remove this value from horizontal neighbors
            if (cell->sector_h) {
                for (Cell* neighbor : *(cell->sector_h)) {
                    if (neighbor != cell && (candidates[neighbor] & mask)) {
                        candidates[neighbor] &= ~mask;
                        changed = true;
                        if (candidates[neighbor] == 0) {
                            return false; // Contradiction
                        }
                    }
                }
            }
            
            // Remove this value from vertical neighbors
            if (cell->sector_v) {
                for (Cell* neighbor : *(cell->sector_v)) {
                    if (neighbor != cell && (candidates[neighbor] & mask)) {
                        candidates[neighbor] &= ~mask;
                        changed = true;
                        if (candidates[neighbor] == 0) {
                            return false; // Contradiction
                        }
                    }
                }
            }
        }
        
        if (!changed) break; // No more naked singles, stop
        any_change = true;
    }
    
    // 2. FAST: One-pass hidden singles (no iteration)
    // Only check once to avoid slowdown
    auto check_hidden_singles_once = [&](const std::vector<std::shared_ptr<std::vector<Cell*>>>& sectors) {
        for (const auto& sector : sectors) {
            if (sector->empty()) continue;
            
            // Count where each digit can go
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
            
            // If a digit can only go in one place, put it there
            for (int d = 1; d <= 9; d++) {
                if (digit_count[d] == 1 && digit_cell[d]) {
                    Cell* cell = digit_cell[d];
                    if (count_set_bits(candidates[cell]) > 1) {
                        candidates[cell] = (1 << d);
                        any_change = true;
                    }
                }
            }
        }
    };
    
    check_hidden_singles_once(board_->sectors_h);
    check_hidden_singles_once(board_->sectors_v);
    
    // 3. SKIP expensive partition filtering entirely
    // The backtracking with candidate tracking will handle this efficiently
    
    return any_change;
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
    
    // Find first cell with candidates remaining
    // We use the candidate map, NOT cell->value, to determine what needs assignment
    Cell* var = nullptr;
    int min_candidates = 10;
    
    for (Cell* c : board_->white_cells) {
        int candidate_count = count_set_bits(candidates[c]);
        
        if (candidate_count == 0) {
            // This cell has been assigned (candidates pruned to 0)
            continue;
        }
        
        if (candidate_count < min_candidates) {
            min_candidates = candidate_count;
            var = c;
        }
        
        if (min_candidates == 1) break; // Can't do better
    }
    
    // All cells have 0 candidates remaining - we have a complete assignment
    if (!var) {
        // Build the solution from cell values
        std::unordered_map<std::pair<int, int>, int, PairHash> sol;
        bool is_different = false;
        
        for (Cell* c : board_->white_cells) {
            if (!c->value.has_value()) {
                // This shouldn't happen - all cells should be assigned
                return;
            }
            int val = *c->value;
            sol[{c->r, c->c}] = val;
            if (val != avoid_sol.at({c->r, c->c})) {
                is_different = true;
            }
        }
        
        if (is_different) {
            found_solutions.push_back(sol);
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
        // Make assignment to the actual cell
        var->value = val;
        
        // Save the original candidate mask for var
        uint16_t var_orig_mask = candidates[var];
        
        // OPTIMIZED: Use stack-based saved state
        std::vector<std::pair<Cell*, uint16_t>> saved_candidates;
        saved_candidates.reserve(20);
        
        uint16_t val_mask = (1 << val);
        candidates[var] = 0; // Mark as fully assigned (no candidates left)
        
        // Forward checking: Update neighbors and check for conflicts
        bool conflict = false;
        
        // Update horizontal neighbors
        if (!conflict && var->sector_h) {
            for (Cell* n : *(var->sector_h)) {
                if (n == var) continue;
                
                uint16_t old_mask = candidates[n];
                if (old_mask == 0) {
                // Already assigned - check for conflict
                    if (n->value.has_value() && *n->value == val) {
                        conflict = true;
                        break;
                    }
                    continue;
                }
                
                uint16_t new_mask = old_mask & ~val_mask;
                
                if (new_mask != old_mask) {
                    saved_candidates.push_back({n, old_mask});
                    candidates[n] = new_mask;
                    
                    // Conflict only if no candidates left and not yet assigned
                    if (new_mask == 0) {
                        conflict = true;
                        break;
                    }
                }
            }
        }
        
        // Update vertical neighbors
        if (!conflict && var->sector_v) {
            for (Cell* n : *(var->sector_v)) {
                if (n == var) continue;
                
                uint16_t old_mask = candidates[n];
                if (old_mask == 0) {
                    // Already assigned - check for conflict
                    if (n->value.has_value() && *n->value == val) {
                        conflict = true;
                        break;
                    }
                    continue;
                }
                
                uint16_t new_mask = old_mask & ~val_mask;
                
                if (new_mask != old_mask) {
                    saved_candidates.push_back({n, old_mask});
                    candidates[n] = new_mask;
                    
                    if (new_mask == 0) {
                        conflict = true;
                        break;
                    }
                }
            }
        }
        
        if (!conflict) {
            // Recurse
            hybrid_search(found_solutions, avoid_sol, candidates,
                         node_count, max_nodes, seed, timed_out);
        }
        
        // BACKTRACK: Restore state
        var->value = std::nullopt;
        candidates[var] = var_orig_mask;
        
        // Restore all neighbor candidates
        for (auto& [cell, old_mask] : saved_candidates) {
            candidates[cell] = old_mask;
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

int HybridUniquenessChecker::count_set_bits(uint16_t mask) const {
    int count = 0;
    while (mask) {
        count += mask & 1;
        mask >>= 1;
    }
    return count;
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