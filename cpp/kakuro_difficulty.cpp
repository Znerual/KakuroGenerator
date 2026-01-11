#include "kakuro_cpp.h"

namespace kakuro {

KakuroDifficultyEstimator::KakuroDifficultyEstimator(
    std::shared_ptr<KakuroBoard> b)
    : board(b) {
  auto get_clue_internal = [&](const std::vector<Cell *> &s,
                               bool is_h) -> std::optional<int> {
    if (s.empty())
      return std::nullopt;
    int r = is_h ? s[0]->r : s[0]->r - 1;
    int c = is_h ? s[0]->c - 1 : s[0]->c;
    if (r < 0 || c < 0 || r >= board->height || c >= board->width)
      return std::nullopt;
    return is_h ? board->grid[r][c].clue_h : board->grid[r][c].clue_v;
  };

  for (auto &s : board->sectors_h) {
    auto clue = get_clue_internal(*s, true);
    if (clue) {
      all_sectors.push_back({*s, *clue, true});
      for (Cell *c : *s) {
        cell_to_h[c] = {*clue, (int)s->size()};
      }
    }
  }
  for (auto &s : board->sectors_v) {
    auto clue = get_clue_internal(*s, false);
    if (clue) {
      all_sectors.push_back({*s, *clue, false});
      for (Cell *c : *s) {
        cell_to_v[c] = {*clue, (int)s->size()};
      }
    }
  }
}

DifficultyResult KakuroDifficultyEstimator::estimate_difficulty_detailed() {
  solve_log.clear();
  found_solutions.clear();
  partition_cache.clear();
  logged_singles.clear();

  // Reset limits
  nodes_explored = 0;
  search_aborted = false;
  start_time = std::chrono::steady_clock::now();

  if (board->white_cells.empty() || all_sectors.empty())
    return DifficultyResult();

  CandidateMap logic_state;
  for (Cell *c : board->white_cells) {
    logic_state[c] = ALL_CANDIDATES;
  }

#if KAKURO_ENABLE_LOGGING
  if (board->logger->is_enabled()) {
    board->logger->log_step(
        GenerationLogger::STAGE_DIFFICULTY, GenerationLogger::SUBSTAGE_START,
        "Starting detailed difficulty analysis", board->get_grid_state());
  }
#endif

  run_solve_loop(logic_state, false);

  // Now check solutions. Use 1-9 mask for search, NOT logic_state.
  CandidateMap search_start;
  for (Cell *c : board->white_cells)
    search_start[c] = ALL_CANDIDATES;
  discover_solutions(search_start, 3);

  DifficultyResult res;
  TechniqueTier highest_tier = TechniqueTier::VERY_EASY;
  float cumulative_effort = 0;

  for (const auto &step : solve_log) {
    // Map technique names to Tiers and Weights
    TechniqueTier current_tier;
    float weight;

    if (step.technique == "unique_intersection" ||
        step.technique == "elimination_singles") {
      current_tier = TechniqueTier::VERY_EASY;
      weight = 1.0f;
    } else if (step.technique == "simple_partition") {
      current_tier = TechniqueTier::EASY;
      weight = 2.5f;
    } else if (step.technique == "hidden_singles" ||
               step.technique == "constraint_propagation") {
      current_tier = TechniqueTier::MEDIUM;
      weight = 5.0f;
    } else if (step.technique == "complex_intersection") {
      current_tier = TechniqueTier::HARD;
      weight = 12.0f;
    } else { // trial_and_error
      current_tier = TechniqueTier::EXTREME;
      weight = 50.0f;
    }

    if ((int)current_tier > (int)highest_tier)
      highest_tier = current_tier;

    // Scalar Score Calculation: Weight * Number of cells/sectors affected
    cumulative_effort += (weight * step.cells_affected);
  }

  switch (highest_tier) {
  case TechniqueTier::VERY_EASY:
    res.rating = "Very Easy";
    break;
  case TechniqueTier::EASY:
    res.rating = "Easy";
    break;
  case TechniqueTier::MEDIUM:
    res.rating = "Medium";
    break;
  case TechniqueTier::HARD:
    res.rating = "Hard";
    break;
  case TechniqueTier::EXTREME:
    res.rating = "Extreme";
    break;
  }

  res.score = cumulative_effort;
  res.max_tier = highest_tier;
  res.solve_path = solve_log;

  res.total_steps = (int)solve_log.size();
  res.solution_count = (int)found_solutions.size();
  res.uniqueness = (res.solution_count == 1)
                       ? "Unique"
                       : (res.solution_count > 1 ? "Multiple" : "No Solution");

  if (search_aborted) {
    res.rating = "Extreme / Unsolvable";
    res.uniqueness = "Inconclusive (Timeout)";
  }

#if KAKURO_ENABLE_LOGGING
  if (board->logger && board->logger->is_enabled()) {
    board->logger->log_difficulty(res, board->get_grid_state());
  }
#endif

  for (const auto &sol : found_solutions)
    res.solutions.push_back(render_solution(sol));
  return res;
}

void KakuroDifficultyEstimator::run_solve_loop(CandidateMap &candidates,
                                               bool silent) {
  bool changed = true;
  int iterations = 0;
  while (changed && iterations < 100) {
    if (is_limit_exceeded())
      return;
    changed = apply_logic_pass(candidates, silent, ++iterations);
  }

  // Only if logic is stuck, try one level of bifurcation
  bool solved = true;
  for (auto *c : board->white_cells)
    if (count_set_bits(candidates[c]) > 1)
      solved = false;

  if (!solved && !silent && !is_limit_exceeded()) {
    solve_log.emplace_back("trial_and_error", 20.0f, 0);
    try_bifurcation(candidates);
  }
}

bool KakuroDifficultyEstimator::apply_logic_pass(CandidateMap &candidates,
                                                 bool silent, int iteration) {
  // Tier 1: Very Easy
  if (find_unique_intersections(candidates, silent))
    return true;
  if (find_naked_singles(candidates, silent, iteration))
    return true;

  if (apply_constraint_propagation(candidates, silent))
    return true;

  // Tier 2: Easy
  if (apply_simple_partitions(candidates, silent))
    return true;

  // Tier 3: Medium
  if (find_hidden_singles(candidates, silent))
    return true;

  // Tier 4: Hard
  if (iteration > 2 && analyze_complex_intersections(candidates, silent))
    return true;

  // Tier 5: Extreme
  return false;
}

bool KakuroDifficultyEstimator::find_hidden_singles(CandidateMap &candidates,
                                                    bool silent) {
  int affected = 0;
  for (auto &sec : all_sectors) {
    for (int v = 1; v <= 9; ++v) {
      Cell *target = nullptr;
      int count = 0;
      for (auto *c : sec.cells) {
        if (candidates.at(c) & (1 << v)) {
          count++;
          target = c;
        }
      }
      if (count == 1 && count_set_bits(candidates.at(target)) > 1) {
        candidates[target] = (1 << v);
        affected++;
      }
    }
  }
  if (affected > 0) {
    if (!silent) {
      solve_log.emplace_back("hidden_singles", 5.0f, affected);
#if KAKURO_ENABLE_LOGGING
      if (board->logger->is_enabled()) {
        std::unordered_map<Cell *, int> viz_map;
        for (auto &[c, m] : candidates) {
          if (count_set_bits(m) == 1)
            viz_map[c] = mask_to_digit(m);
        }
        board->logger->log_step(
            GenerationLogger::STAGE_DIFFICULTY,
            GenerationLogger::SUBSTAGE_LOGIC_STEP,
            "Applied hidden_singles: " + std::to_string(affected) +
                " cells affected",
            board->get_grid_state(&viz_map));
      }
#endif
    }
    return true;
  }
  return false;
}

bool KakuroDifficultyEstimator::find_naked_singles(CandidateMap &candidates,
                                                   bool silent, int iteration) {
  if (!silent && iteration == 1)
    logged_singles.clear();

  int newly_solved = 0;
  for (auto *c : board->white_cells) {
    if (count_set_bits(candidates.at(c)) == 1 &&
        logged_singles.find(c) == logged_singles.end()) {
      if (!silent)
        logged_singles.insert(c);
      newly_solved++;
    }
  }
  if (newly_solved > 0 && !silent) {
    solve_log.emplace_back("elimination_singles", 2.0f, newly_solved);
#if KAKURO_ENABLE_LOGGING
    if (board->logger->is_enabled()) {
      std::unordered_map<Cell *, int> viz_map;
      for (auto &[c, m] : candidates) {
        if (count_set_bits(m) == 1)
          viz_map[c] = mask_to_digit(m);
      }
      board->logger->log_step(
          GenerationLogger::STAGE_DIFFICULTY,
          GenerationLogger::SUBSTAGE_LOGIC_STEP,
          "Applied elimination_singles: " + std::to_string(newly_solved) +
              " cells solved",
          board->get_grid_state(&viz_map));
    }
#endif
    return true;
  }
  return false;
}

bool KakuroDifficultyEstimator::apply_sector_constraints(
    const SectorInfo &sec, CandidateMap &candidates) {
  if (search_aborted)
    return false;

  bool changed = false;
  int n = (int)sec.cells.size();

  // STEP 1: Bitmask Filter (Instant)
  // Eliminate digits that don't exist in ANY mathematical partition for this
  // clue/length.
  uint16_t sector_allowed_mask = get_partition_bits(sec.clue, n);
  for (auto *c : sec.cells) {
    uint16_t old = candidates[c];
    candidates[c] &= sector_allowed_mask;
    if (candidates[c] != old)
      changed = true;
  }

  // STEP 2: Reachability Math (O(N))
  // For each cell, check if its current values can actually reach the clue sum
  // given the min/max possibilities of the other cells in the sector.
  if (n > 1) {
    // We pre-calculate the min and max for all cells to avoid redundant loops
    std::vector<int> c_mins(n), c_maxs(n);
    int total_min = 0, total_max = 0;

    for (int i = 0; i < n; ++i) {
      int mi = 10, ma = 0;
      uint16_t mask = candidates[sec.cells[i]];
      for (int v = 1; v <= 9; ++v) {
        if (mask & (1 << v)) {
          if (v < mi)
            mi = v;
          if (v > ma)
            ma = v;
        }
      }
      c_mins[i] = mi;
      c_maxs[i] = ma;
      total_min += mi;
      total_max += ma;
    }

    for (int i = 0; i < n; ++i) {
      uint16_t mask = candidates[sec.cells[i]];
      uint16_t new_mask = mask;

      // The "others" are the sum of everything except the current cell
      int others_min = total_min - c_mins[i];
      int others_max = total_max - c_maxs[i];

      for (int v = 1; v <= 9; ++v) {
        if (mask & (1 << v)) {
          // If I pick value 'v', can the rest of the cells fill the gap?
          // Gap required = Clue - v
          if (v + others_min > sec.clue || v + others_max < sec.clue) {
            new_mask &= ~(1 << v);
          }
        }
      }

      if (new_mask != mask) {
        candidates[sec.cells[i]] = new_mask;
        changed = true;
        // If we pruned a value, we should update the total_min/max
        // for the next cell in this loop, but even without doing that,
        // the next logic pass will catch it.
      }
    }
  }

  // STEP 3: Unique Value Check (Sudoku style)
  // If a value is already "solved" in one cell, no other cell in the sector can
  // have it.
  uint16_t solved_mask = 0;
  for (auto *c : sec.cells) {
    if (count_set_bits(candidates[c]) == 1)
      solved_mask |= candidates[c];
  }
  for (auto *c : sec.cells) {
    if (count_set_bits(candidates[c]) > 1) {
      uint16_t old = candidates[c];
      candidates[c] &= ~solved_mask;
      if (candidates[c] != old)
        changed = true;
    }
  }

  return changed;
}

int KakuroDifficultyEstimator::mask_to_digit(uint16_t mask) const {
  for (int v = 1; v <= 9; ++v) {
    if (mask == (1 << v))
      return v;
  }
  return 0;
}

void KakuroDifficultyEstimator::discover_solutions(CandidateMap candidates,
                                                   int limit) {
  if (found_solutions.size() >= limit || is_limit_exceeded())
    return;
  for (int i = 0; i < 3; ++i) {
    bool progress = false;
    for (auto &sec : all_sectors)
      if (apply_sector_constraints(sec, candidates))
        progress = true;
    if (!progress)
      break;
  }
  for (auto *c : board->white_cells)
    if (candidates.at(c) == 0)
      return;
  Cell *mrv = nullptr;
  int min_b = 10;
  for (auto *c : board->white_cells) {
    int b = count_set_bits(candidates.at(c));
    if (b > 1 && b < min_b) {
      min_b = b;
      mrv = c;
    }
  }
  if (!mrv) {
    std::unordered_map<Cell *, int> sol;
    for (auto *c : board->white_cells) {
      int digit = mask_to_digit(candidates.at(c));
      if (digit == 0)
        return; // Should not happen if count_set_bits was 1
      sol[c] = digit;
    }
    if (verify_math(sol)) {
      // Check for duplicates before adding
      bool exists = false;
      for (auto &existing : found_solutions) {
        bool match = true;
        for (auto *cell : board->white_cells)
          if (existing[cell] != sol[cell]) {
            match = false;
            break;
          }
        if (match) {
          exists = true;
          break;
        }
      }
      if (!exists)
        found_solutions.push_back(sol);
    }
    return;
  }
  uint16_t mask = candidates.at(mrv);
  for (int v = 1; v <= 9; ++v) {
    if (mask & (1 << v)) {
      if (search_aborted)
        break;
      CandidateMap branch = candidates;
      branch[mrv] = (1 << v);
      discover_solutions(branch, limit);
      if (found_solutions.size() >= limit)
        break;
    }
  }
}

bool KakuroDifficultyEstimator::find_unique_intersections(
    CandidateMap &candidates, bool silent) {
  bool changed = false;
  int affected = 0;

  for (auto *cell : board->white_cells) {
    if (count_set_bits(candidates[cell]) <= 1)
      continue;

    // O(1) Lookup: No more looping through all_sectors!
    SectorMetadata &h = cell_to_h[cell];
    SectorMetadata &v = cell_to_v[cell];

    uint16_t h_mask = get_partition_bits(h.clue, h.length);
    uint16_t v_mask = get_partition_bits(v.clue, v.length);

    uint16_t combined_constraint = h_mask & v_mask;
    uint16_t new_candidates = candidates[cell] & combined_constraint;

    if (new_candidates != candidates[cell]) {
      candidates[cell] = new_candidates;
      changed = true;
      if (count_set_bits(new_candidates) == 1)
        affected++;
    }
  }
  if (affected > 0 && !silent) {
    solve_log.emplace_back("unique_intersection", 0.5f, affected);
#if KAKURO_ENABLE_LOGGING
    if (board->logger->is_enabled()) {
      std::unordered_map<Cell *, int> viz_map;
      for (auto &[c, m] : candidates) {
        if (count_set_bits(m) == 1)
          viz_map[c] = mask_to_digit(m);
      }
      board->logger->log_step(GenerationLogger::STAGE_DIFFICULTY,
                              GenerationLogger::SUBSTAGE_LOGIC_STEP,
                              "Applied unique_intersection: " +
                                  std::to_string(affected) + " cells affected",
                              board->get_grid_state(&viz_map));
    }
#endif
  }
  return changed;
}

bool KakuroDifficultyEstimator::apply_simple_partitions(
    CandidateMap &candidates, bool silent) {
  bool ch = false;
  int aff = 0;
  for (auto &sec : all_sectors) {
    auto ps = get_partitions(sec.clue, (int)sec.cells.size());
    if (ps.size() == 1) {
      uint16_t m = 0;
      for (int v : ps[0])
        m |= (1 << v);
      for (auto *c : sec.cells) {
        uint16_t old = candidates.at(c);
        candidates[c] &= m;
        if (candidates.at(c) != old) {
          ch = true;
          aff++;
        }
      }
    }
  }
  if (aff > 0 && !silent) {
    solve_log.emplace_back("simple_partition", 1.0f, aff);
#if KAKURO_ENABLE_LOGGING
    if (board->logger->is_enabled()) {
      std::unordered_map<Cell *, int> viz_map;
      for (auto &[c, m] : candidates) {
        if (count_set_bits(m) == 1)
          viz_map[c] = mask_to_digit(m);
      }
      board->logger->log_step(GenerationLogger::STAGE_DIFFICULTY,
                              GenerationLogger::SUBSTAGE_LOGIC_STEP,
                              "Applied simple_partition: " +
                                  std::to_string(aff) + " cells affected",
                              board->get_grid_state(&viz_map));
    }
#endif
  }
  return ch;
}

bool KakuroDifficultyEstimator::apply_constraint_propagation(
    CandidateMap &candidates, bool silent) {
  bool changed = false;
  int affected_cells = 0;
  for (auto &sec : all_sectors) {
    if (apply_sector_constraints(sec, candidates)) {
      changed = true;
      affected_cells += (int)sec.cells.size();
    }
  }
  if (changed && !silent) {
    // High scalar weight because this requires checking sums repeatedly
    solve_log.emplace_back("constraint_propagation", 4.0f, affected_cells);
#if KAKURO_ENABLE_LOGGING
    if (board->logger->is_enabled()) {
      std::unordered_map<Cell *, int> viz_map;
      for (auto &[c, m] : candidates) {
        if (count_set_bits(m) == 1)
          viz_map[c] = mask_to_digit(m);
      }
      board->logger->log_step(
          GenerationLogger::STAGE_DIFFICULTY,
          GenerationLogger::SUBSTAGE_LOGIC_STEP,
          "Applied constraint_propagation: " + std::to_string(affected_cells) +
              " cells affected",
          board->get_grid_state(&viz_map));
    }
#endif
  }
  return changed;
}

bool KakuroDifficultyEstimator::analyze_complex_intersections(
    CandidateMap &candidates, bool silent) {
  bool ch = false;
  for (auto *cell : board->white_cells) {
    if (count_set_bits(candidates.at(cell)) <= 1)
      continue;
    uint16_t mask = candidates.at(cell), valid = 0;
    for (int v = 1; v <= 9; ++v) {
      if (!(mask & (1 << v)))
        continue;
      bool ok = true;
      for (auto &sec : all_sectors) {
        bool in = false;
        for (auto *sc : sec.cells)
          if (sc == cell)
            in = true;
        if (!in)
          continue;
        bool p_ok = false;
        for (auto &p : get_partitions(sec.clue, (int)sec.cells.size())) {
          if (std::find(p.begin(), p.end(), v) != p.end()) {
            p_ok = true;
            break;
          }
        }
        if (!p_ok) {
          ok = false;
          break;
        }
      }
      if (ok)
        valid |= (1 << v);
    }
    if (valid != 0 && valid != mask) {
      candidates[cell] = valid;
      ch = true;
    }
  }
  if (ch && !silent) {
    solve_log.emplace_back("complex_intersection", 6.0f, 1);
#if KAKURO_ENABLE_LOGGING
    if (board->logger->is_enabled()) {
      std::unordered_map<Cell *, int> viz_map;
      for (auto &[c, m] : candidates) {
        if (count_set_bits(m) == 1)
          viz_map[c] = mask_to_digit(m);
      }
      board->logger->log_step(GenerationLogger::STAGE_DIFFICULTY,
                              GenerationLogger::SUBSTAGE_LOGIC_STEP,
                              "Applied complex_intersection",
                              board->get_grid_state(&viz_map));
    }
#endif
  }
  return ch;
}

bool KakuroDifficultyEstimator::try_bifurcation(CandidateMap &candidates) {
  if (is_limit_exceeded())
    return false;

  Cell *target = nullptr;
  int min_b = 10;
  for (auto *c : board->white_cells) {
    int b = count_set_bits(candidates.at(c));
    if (b > 1 && b < min_b) {
      min_b = b;
      target = c;
    }
  }
  if (!target)
    return true;
  uint16_t mask = candidates.at(target);
  for (int v = 1; v <= 9; ++v) {
    if (mask & (1 << v)) {
      if (is_limit_exceeded())
        return false;
      CandidateMap test = candidates;
      test[target] = (1 << v);
      run_solve_loop(test, true);
      bool ok = true;
      for (auto *c : board->white_cells)
        if (count_set_bits(test.at(c)) != 1) {
          ok = false;
          break;
        }
      if (ok) {
        candidates = test;
        return true;
      }
    }
  }
  return false;
}

std::vector<std::vector<int>>
KakuroDifficultyEstimator::get_partitions(int sum, int len) {
  if (partition_cache.count({sum, len}))
    return partition_cache[{sum, len}];
  std::vector<std::vector<int>> res;
  std::vector<int> cur;
  std::function<void(int, int, int)> bt = [&](int t, int k, int s) {
    if (k == 0) {
      if (t == 0)
        res.push_back(cur);
      return;
    }
    for (int i = s; i <= 9; ++i) {
      if (i > t)
        break;
      cur.push_back(i);
      bt(t - i, k - 1, i + 1);
      cur.pop_back();
    }
  };
  bt(sum, len, 1);
  return partition_cache[{sum, len}] = res;
}

uint16_t KakuroDifficultyEstimator::get_partition_bits(int sum, int len) {
  uint32_t key = (sum << 8) | len;
  if (partition_mask_cache.count(key))
    return partition_mask_cache[key];

  uint16_t mask = 0;
  auto partitions = get_partitions(sum, len); // Use your existing logic once
  for (const auto &p : partitions) {
    for (int v : p)
      mask |= (1 << v);
  }
  return partition_mask_cache[key] = mask;
}

bool KakuroDifficultyEstimator::verify_math(
    const std::unordered_map<Cell *, int> &sol) const {
  for (auto &sec : all_sectors) {
    int sum = 0;
    std::bitset<10> seen;
    for (auto *c : sec.cells) {
      if (sol.find(c) == sol.end())
        return false;
      int v = sol.at(c);
      sum += v;
      seen.set(v);
    }
    if (sum != sec.clue || (int)seen.count() != (int)sec.cells.size())
      return false;
  }
  return true;
}

std::vector<std::vector<std::optional<int>>>
KakuroDifficultyEstimator::render_solution(
    const std::unordered_map<Cell *, int> &sol) const {
  std::vector<std::vector<std::optional<int>>> res(
      board->height,
      std::vector<std::optional<int>>(board->width, std::nullopt));
  for (int r = 0; r < board->height; ++r) {
    for (int c = 0; c < board->width; ++c) {
      if (board->grid[r][c].type == CellType::WHITE) {
        auto it = sol.find(const_cast<Cell *>(&board->grid[r][c]));
        if (it != sol.end())
          res[r][c] = it->second;
      }
    }
  }
  return res;
}

int KakuroDifficultyEstimator::count_set_bits(uint16_t n) const {
  return (int)std::bitset<16>(n).count();
}
float KakuroDifficultyEstimator::estimate_difficulty() {
  return estimate_difficulty_detailed().score;
}

} // namespace kakuro