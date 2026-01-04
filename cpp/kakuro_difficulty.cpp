#include "kakuro_cpp.h"
#include <vector>
#include <numeric>
#include <cmath>
#include <algorithm>

namespace kakuro {

KakuroDifficultyEstimator::KakuroDifficultyEstimator(std::shared_ptr<KakuroBoard> b) 
    : board(b) {}

int KakuroDifficultyEstimator::count_set_bits(uint16_t n) {
    int count = 0;
    while (n > 0) {
        n &= (n - 1);
        count++;
    }
    return count;
}

float KakuroDifficultyEstimator::estimate_difficulty() {
    candidates.assign(board->height, std::vector<uint16_t>(board->width, 0));
    
    int total_white_cells = 0;
    for (Cell* c : board->white_cells) {
        candidates[c->r][c->c] = ALL_CANDIDATES;
        total_white_cells++;
    }

    int passes = 0;
    int solved_cells = 0;
    
    while (solved_cells < total_white_cells) {
        passes++;
        bool changes = false;
        
        // FIX: Collect the vectors inside the shared_ptrs
        for (auto& s_ptr : board->sectors_h) {
            if (apply_sum_constraints(*s_ptr)) changes = true;
        }
        for (auto& s_ptr : board->sectors_v) {
            if (apply_sum_constraints(*s_ptr)) changes = true;
        }
        
        int current_solved = 0;
        for (Cell* c : board->white_cells) {
            if (count_set_bits(candidates[c->r][c->c]) == 1) {
                current_solved++;
            }
        }
        
        if (current_solved > solved_cells) {
            solved_cells = current_solved;
        } else if (!changes) {
            float remaining = (float)(total_white_cells - solved_cells);
            return (float)passes + (remaining * 2.0f);
        }
        
        if (passes > 20) return 99.0f;
    }
    
    return (float)passes;
}

bool KakuroDifficultyEstimator::apply_sum_constraints(const std::vector<Cell*>& sector) {
    if (sector.empty()) return false;
    
    // FIX: Use .get() to compare shared_ptr contents to the raw address of 'sector'
    bool is_horz = (sector[0]->sector_h.get() == &sector);
                   
    int clue = 0;
    if (is_horz) {
        auto val = board->grid[sector[0]->r][sector[0]->c - 1].clue_h;
        if (!val.has_value()) return false;
        clue = *val;
    } else {
        auto val = board->grid[sector[0]->r - 1][sector[0]->c].clue_v;
        if (!val.has_value()) return false;
        clue = *val;
    }
    
    std::vector<uint16_t> allowed_values_per_slot(sector.size(), 0);
    std::vector<int> current_path(sector.size(), 0);
    
    find_valid_permutations(sector, 0, 0, clue, 0, current_path, allowed_values_per_slot);
    
    bool changed = false;
    for (size_t i = 0; i < sector.size(); ++i) {
        Cell* c = sector[i];
        uint16_t current_mask = candidates[c->r][c->c];
        uint16_t allowed_mask = allowed_values_per_slot[i];
        uint16_t new_mask = current_mask & allowed_mask;
        
        if (new_mask != current_mask) {
            candidates[c->r][c->c] = new_mask;
            changed = true;
        }
    }
    return changed;
}

void KakuroDifficultyEstimator::find_valid_permutations(
    const std::vector<Cell*>& sector,
    int index,
    int current_sum,
    int target_sum,
    uint16_t used_numbers_mask,
    std::vector<int>& path,
    std::vector<uint16_t>& allowed_values_per_slot
) {
    if (index == (int)sector.size()) {
        if (current_sum == target_sum) {
            for (size_t i = 0; i < sector.size(); ++i) {
                allowed_values_per_slot[i] |= (1 << path[i]);
            }
        }
        return;
    }
    
    if (current_sum >= target_sum) return;
    
    // Optimization: check if remaining sum is even possible
    int remaining_cells = (int)sector.size() - index;
    // Min possible remaining sum: 1+2+...
    // Max possible remaining sum: 9+8+... 
    // (Simplified check for speed)
    if (current_sum + remaining_cells > target_sum) return;

    Cell* current_cell = sector[index];
    uint16_t cell_candidates = candidates[current_cell->r][current_cell->c];
    
    for (int num = 1; num <= 9; ++num) {
        uint16_t num_bit = (1 << num);
        if ((cell_candidates & num_bit) && !(used_numbers_mask & num_bit)) {
            path[index] = num;
            find_valid_permutations(sector, index + 1, current_sum + num, target_sum,
                                    used_numbers_mask | num_bit, path, allowed_values_per_slot);
        }
    }
}

} // namespace