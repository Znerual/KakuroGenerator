#include "kakuro_cpp.h"

namespace kakuro {

KakuroDifficultyEstimator::KakuroDifficultyEstimator(std::shared_ptr<KakuroBoard> b) : board(b) {
    auto get_clue_internal = [&](const std::vector<Cell*>& s, bool is_h) -> std::optional<int> {
        if (s.empty()) return std::nullopt;
        int r = is_h ? s[0]->r : s[0]->r - 1;
        int c = is_h ? s[0]->c - 1 : s[0]->c;
        if (r < 0 || c < 0 || r >= board->height || c >= board->width) return std::nullopt;
        return is_h ? board->grid[r][c].clue_h : board->grid[r][c].clue_v;
    };

    for (auto& s : board->sectors_h) {
        auto clue = get_clue_internal(*s, true);
        if (clue) all_sectors.push_back({*s, *clue, true});
    }
    for (auto& s : board->sectors_v) {
        auto clue = get_clue_internal(*s, false);
        if (clue) all_sectors.push_back({*s, *clue, false});
    }
}

DifficultyResult KakuroDifficultyEstimator::estimate_difficulty_detailed() {
    solve_log.clear();
    found_solutions.clear();
    partition_cache.clear();
    logged_singles.clear();

    if (board->white_cells.empty() || all_sectors.empty()) return DifficultyResult();

    CandidateMap initial_candidates;
    for (Cell* c : board->white_cells) initial_candidates[c] = ALL_CANDIDATES;

    CandidateMap logic_state = initial_candidates;
    run_solve_loop(logic_state, false);

    discover_solutions(initial_candidates, 3);

    DifficultyResult res;
    for (const auto& step : solve_log) {
        res.score += step.difficulty_weight;
        res.techniques_used[step.technique]++;
    }
    res.solve_path = solve_log;
    res.total_steps = (int)solve_log.size();
    res.solution_count = (int)found_solutions.size();
    res.uniqueness = (res.solution_count == 1) ? "Unique" : (res.solution_count > 1 ? "Multiple" : "No Solution");
    
    if (res.score < 15) res.rating = "Easy";
    else if (res.score < 30) res.rating = "Medium";
    else if (res.score < 60) res.rating = "Hard";
    else res.rating = "Expert";

    for (const auto& sol : found_solutions) res.solutions.push_back(render_solution(sol));
    return res;
}

void KakuroDifficultyEstimator::run_solve_loop(CandidateMap& candidates, bool silent) {
    for (int it = 1; it <= 50; ++it) {
        if (!apply_logic_pass(candidates, silent, it)) {
            if (!silent) {
                bool solved = true;
                for (auto* c : board->white_cells) if (count_set_bits(candidates.at(c)) > 1) solved = false;
                if (!solved) {
                    solve_log.emplace_back("trial_and_error", 20.0f, 0);
                    if (!try_bifurcation(candidates)) break;
                } else break;
            } else break;
        }
        bool solved = true;
        for (auto* c : board->white_cells) if (count_set_bits(candidates.at(c)) != 1) solved = false;
        if (solved) return;
    }
}

bool KakuroDifficultyEstimator::apply_logic_pass(CandidateMap& candidates, bool silent, int iteration) {
    if (find_unique_intersections(candidates, silent)) return true;
    if (apply_simple_partitions(candidates, silent)) return true;
    if (apply_constraint_propagation(candidates, silent)) return true;
    if (find_naked_singles(candidates, silent, iteration)) return true;
    if (find_hidden_singles(candidates, silent)) return true;
    if (iteration > 3 && analyze_complex_intersections(candidates, silent)) return true;
    return false;
}

bool KakuroDifficultyEstimator::find_hidden_singles(CandidateMap& candidates, bool silent) {
    bool changed = false; int affected = 0;
    for (auto& sec : all_sectors) {
        for (int v = 1; v <= 9; ++v) {
            Cell* target = nullptr; int count = 0;
            for (auto* c : sec.cells) if (candidates.at(c) & (1 << v)) { count++; target = c; }
            if (count == 1 && count_set_bits(candidates.at(target)) > 1) {
                candidates[target] = (1 << v);
                changed = true; affected++;
            }
        }
    }
    if (affected > 0 && !silent) solve_log.emplace_back("hidden_singles", 3.0f, affected);
    return changed;
}

bool KakuroDifficultyEstimator::find_naked_singles(CandidateMap& candidates, bool silent, int iteration) {
    if (!silent && iteration == 1) logged_singles.clear(); 

    int newly_solved = 0;
    for (auto* c : board->white_cells) {
        if (count_set_bits(candidates.at(c)) == 1 && logged_singles.find(c) == logged_singles.end()) {
            if (!silent) logged_singles.insert(c);
            newly_solved++;
        }
    }
    if (newly_solved > 0 && !silent) {
        solve_log.emplace_back("elimination_singles", 2.0f, newly_solved);
        return true; 
    }
    return false; 
}

bool KakuroDifficultyEstimator::apply_sector_constraints(const SectorInfo& sec, CandidateMap& candidates) {
    std::vector<uint16_t> allowed(sec.cells.size(), 0);
    auto partitions = get_partitions(sec.clue, (int)sec.cells.size());
    bool found = false;
    for (auto p : partitions) {
        std::sort(p.begin(), p.end());
        do {
            bool ok = true;
            for (size_t i = 0; i < sec.cells.size(); ++i) {
                if (!(candidates.at(sec.cells[i]) & (1 << p[i]))) { ok = false; break; }
            }
            if (ok) {
                found = true;
                for (size_t i = 0; i < sec.cells.size(); ++i) allowed[i] |= (1 << p[i]);
            }
        } while (std::next_permutation(p.begin(), p.end()));
    }
    if (!found) { for (auto* c : sec.cells) candidates[c] = 0; return false; }
    bool changed = false;
    for (size_t i = 0; i < sec.cells.size(); ++i) {
        uint16_t old = candidates.at(sec.cells[i]);
        candidates[sec.cells[i]] &= allowed[i];
        if (candidates.at(sec.cells[i]) != old) changed = true;
    }
    return changed;
}

void KakuroDifficultyEstimator::discover_solutions(CandidateMap candidates, int limit) {
    if (found_solutions.size() >= limit) return;
    for (int i = 0; i < 3; ++i) {
        bool progress = false;
        for (auto& sec : all_sectors) if (apply_sector_constraints(sec, candidates)) progress = true;
        if (!progress) break;
    }
    for (auto* c : board->white_cells) if (candidates.at(c) == 0) return;
    Cell* mrv = nullptr; int min_b = 10;
    for (auto* c : board->white_cells) {
        int b = count_set_bits(candidates.at(c));
        if (b > 1 && b < min_b) { min_b = b; mrv = c; }
    }
    if (!mrv) {
        std::unordered_map<Cell*, int> sol;
        for (auto* c : board->white_cells) sol[c] = (int)std::log2(candidates.at(c));
        if (verify_math(sol)) found_solutions.push_back(sol);
        return;
    }
    uint16_t mask = candidates.at(mrv);
    for (int v = 1; v <= 9; ++v) {
        if (mask & (1 << v)) {
            CandidateMap branch = candidates;
            branch[mrv] = (1 << v);
            discover_solutions(branch, limit);
            if (found_solutions.size() >= limit) break;
        }
    }
}

bool KakuroDifficultyEstimator::find_unique_intersections(CandidateMap& candidates, bool silent) {
    bool ch = false; int sol = 0;
    for (auto* c : board->white_cells) {
        if (count_set_bits(candidates.at(c)) <= 1) continue;
        uint16_t rm = 0, cm = 0; bool h = false, v = false;
        for (auto& sec : all_sectors) {
            bool in = false; for (auto* sc : sec.cells) if (sc == c) in = true;
            if (in) {
                uint16_t m = 0;
                for (auto& p : get_partitions(sec.clue, (int)sec.cells.size())) for (int val : p) m |= (1 << val);
                if (sec.is_horz) { rm = m; h = true; } else { cm = m; v = true; }
            }
        }
        if (h && v) {
            uint16_t inter = rm & cm & candidates.at(c);
            if (inter != 0 && inter != candidates.at(c)) {
                candidates[c] = inter; ch = true;
                if (count_set_bits(inter) == 1) sol++;
            }
        }
    }
    if (sol > 0 && !silent) solve_log.emplace_back("unique_intersection", 0.5f, sol);
    return ch;
}

bool KakuroDifficultyEstimator::apply_simple_partitions(CandidateMap& candidates, bool silent) {
    bool ch = false; int aff = 0;
    for (auto& sec : all_sectors) {
        auto ps = get_partitions(sec.clue, (int)sec.cells.size());
        if (ps.size() == 1) {
            uint16_t m = 0; for (int v : ps[0]) m |= (1 << v);
            for (auto* c : sec.cells) {
                uint16_t old = candidates.at(c);
                candidates[c] &= m;
                if (candidates.at(c) != old) { ch = true; aff++; }
            }
        }
    }
    if (aff > 0 && !silent) solve_log.emplace_back("simple_partition", 1.0f, aff);
    return ch;
}

bool KakuroDifficultyEstimator::apply_constraint_propagation(CandidateMap& candidates, bool silent) {
    bool ch = false; int aff = 0;
    for (auto& sec : all_sectors) if (apply_sector_constraints(sec, candidates)) { ch = true; aff++; }
    if (ch && !silent) solve_log.emplace_back("constraint_propagation", 4.0f, aff);
    return ch;
}

bool KakuroDifficultyEstimator::analyze_complex_intersections(CandidateMap& candidates, bool silent) {
    bool ch = false;
    for (auto* cell : board->white_cells) {
        if (count_set_bits(candidates.at(cell)) <= 1) continue;
        uint16_t mask = candidates.at(cell), valid = 0;
        for (int v = 1; v <= 9; ++v) {
            if (!(mask & (1 << v))) continue;
            bool ok = true;
            for (auto& sec : all_sectors) {
                bool in = false; for (auto* sc : sec.cells) if (sc == cell) in = true;
                if (!in) continue;
                bool p_ok = false;
                for (auto& p : get_partitions(sec.clue, (int)sec.cells.size())) {
                    if (std::find(p.begin(), p.end(), v) != p.end()) { p_ok = true; break; }
                }
                if (!p_ok) { ok = false; break; }
            }
            if (ok) valid |= (1 << v);
        }
        if (valid != 0 && valid != mask) { candidates[cell] = valid; ch = true; }
    }
    if (ch && !silent) solve_log.emplace_back("complex_intersection", 6.0f, 1);
    return ch;
}

bool KakuroDifficultyEstimator::try_bifurcation(CandidateMap& candidates) {
    Cell* target = nullptr; int min_b = 10;
    for (auto* c : board->white_cells) {
        int b = count_set_bits(candidates.at(c));
        if (b > 1 && b < min_b) { min_b = b; target = c; }
    }
    if (!target) return true;
    uint16_t mask = candidates.at(target);
    for (int v = 1; v <= 9; ++v) {
        if (mask & (1 << v)) {
            CandidateMap test = candidates; test[target] = (1 << v);
            run_solve_loop(test, true);
            bool ok = true;
            for (auto* c : board->white_cells) if (count_set_bits(test.at(c)) != 1) { ok = false; break; }
            if (ok) { candidates = test; return true; }
        }
    }
    return false;
}

std::vector<std::vector<int>> KakuroDifficultyEstimator::get_partitions(int sum, int len) {
    if (partition_cache.count({sum, len})) return partition_cache[{sum, len}];
    std::vector<std::vector<int>> res; std::vector<int> cur;
    std::function<void(int, int, int)> bt = [&](int t, int k, int s) {
        if (k == 0) { if (t == 0) res.push_back(cur); return; }
        for (int i = s; i <= 9; ++i) { if (i > t) break; cur.push_back(i); bt(t-i, k-1, i+1); cur.pop_back(); }
    };
    bt(sum, len, 1);
    return partition_cache[{sum, len}] = res;
}

bool KakuroDifficultyEstimator::verify_math(const std::unordered_map<Cell*, int>& sol) const {
    for (auto& sec : all_sectors) {
        int sum = 0; std::bitset<10> seen;
        for (auto* c : sec.cells) {
            if (sol.find(c) == sol.end()) return false;
            int v = sol.at(c); sum += v; seen.set(v); 
        }
        if (sum != sec.clue || (int)seen.count() != (int)sec.cells.size()) return false;
    }
    return true;
}

std::vector<std::vector<std::optional<int>>> KakuroDifficultyEstimator::render_solution(const std::unordered_map<Cell*, int>& sol) const {
    std::vector<std::vector<std::optional<int>>> res(board->height, std::vector<std::optional<int>>(board->width, std::nullopt));
    for (int r = 0; r < board->height; ++r) {
        for (int c = 0; c < board->width; ++c) {
            if (board->grid[r][c].type == CellType::WHITE) {
                auto it = sol.find(const_cast<Cell*>(&board->grid[r][c]));
                if (it != sol.end()) res[r][c] = it->second;
            }
        }
    }
    return res;
}

int KakuroDifficultyEstimator::count_set_bits(uint16_t n) const { return (int)std::bitset<16>(n).count(); }
float KakuroDifficultyEstimator::estimate_difficulty() { return estimate_difficulty_detailed().score; }

} // namespace kakuro