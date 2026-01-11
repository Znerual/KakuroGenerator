#include "kakuro_cpp.h"
#include <algorithm>
#include <iostream>
#include <map>
#include <numeric>
#include <queue>

namespace kakuro {

CSPSolver::CSPSolver(std::shared_ptr<KakuroBoard> b)
    : board(b), rng(std::random_device{}()) {}

bool CSPSolver::check_timeout() {
  auto now = std::chrono::steady_clock::now();
  std::chrono::duration<double> elapsed = now - start_time_;
  if (elapsed.count() > time_limit_sec_) {
    LOG_ERROR("=== TIMEOUT: Generation exceeded "
              << time_limit_sec_ << " seconds. Terminating. ===");
#if KAKURO_ENABLE_LOGGING
    if (board->logger->is_enabled()) {
      board->logger->log_step(
          GenerationLogger::STAGE_FILLING, GenerationLogger::SUBSTAGE_FAILED,
          "Timeout exceeded " + std::to_string(time_limit_sec_) + "s",
          board->get_grid_state());
      board->logger->close();
    }
#endif
    return true;
  }
  return false;
}

bool CSPSolver::generate_puzzle(const std::string &difficulty) {
  FillParams fill_params;
  fill_params.difficulty = difficulty;

  TopologyParams topo_params;
  topo_params.difficulty = difficulty;
  board->apply_topology_defaults(topo_params);

  return generate_puzzle(fill_params, topo_params);
}

bool CSPSolver::generate_puzzle(const FillParams &params,
                                const TopologyParams &topo_params) {
  // Reset Timer at start of generation
  start_time_ = std::chrono::steady_clock::now();

  const int MAX_TOPOLOGY_RETRIES = 50;
  LOG_DEBUG("Starting puzzle generation. Difficulty: " << params.difficulty);

  for (int topo_attempt = 0; topo_attempt < MAX_TOPOLOGY_RETRIES;
       topo_attempt++) {
    if (check_timeout())
      return false;
    if (!prepare_new_topology(topo_params))
      continue;

    if (attempt_fill_and_validate(params)) {
#if KAKURO_ENABLE_LOGGING
      board->logger->log_step(
          GenerationLogger::STAGE_FILLING, GenerationLogger::SUBSTAGE_COMPLETE,
          "Puzzle generation successful", board->get_grid_state());
      board->logger->close();
#endif
      return true;
    }
  }

  LOG_ERROR("=== FAILURE: Maximum topology retries ("
            << MAX_TOPOLOGY_RETRIES << ") exceeded for difficulty "
            << params.difficulty << " ===");
#if KAKURO_ENABLE_LOGGING
  board->logger->log_step(
      GenerationLogger::STAGE_FILLING, GenerationLogger::SUBSTAGE_FAILED,
      "Puzzle generation failed after max retries", board->get_grid_state());
  board->logger->close();
#endif
  return false;
}

GeneratedPuzzle CSPSolver::generate_random_puzzle() {
  std::uniform_int_distribution<int> dist_w(8, 18);
  std::uniform_int_distribution<int> dist_h(8, 16);
  std::uniform_real_distribution<double> dist_density(0.55, 0.68);
  std::uniform_int_distribution<int> dist_num_stamps(
      8, 20); // Normalized by area in board
  std::uniform_int_distribution<int> dist_pref(0, 2);

  int w = dist_w(rng);
  int h = dist_h(rng);
  board = std::make_shared<KakuroBoard>(w, h);
  int area = (w - 2) * (h - 2);

  TopologyParams topo;
  topo.density = dist_density(rng);
  topo.num_stamps = dist_num_stamps(rng) * area / 100;
  topo.max_sector_length = 9;
  topo.island_mode = true;
  topo.min_cells =
      (int)(area * std::uniform_real_distribution<double>(0.18, 0.35)(rng));
  topo.max_run_len = std::uniform_int_distribution<>(6, 9)(rng);
  topo.max_patch_size = std::uniform_int_distribution<>(2, 4)(rng);

  // Random stamps subset
  std::vector<std::pair<int, int>> all_stamps = {
      {1, 3}, {3, 1}, {2, 2}, {1, 4}, {4, 1}, {2, 3}, {3, 2},
      {1, 5}, {5, 1}, {2, 4}, {4, 2}, {3, 3}, {1, 6}, {6, 1},
      {2, 5}, {5, 2}, {3, 4}, {1, 7}, {7, 1}, {1, 8}, {8, 1}};
  std::shuffle(all_stamps.begin(), all_stamps.end(), rng);
  int n_stamps = std::uniform_int_distribution<>(5, 12)(rng);
  topo.stamps = std::vector<std::pair<int, int>>(
      all_stamps.begin(),
      all_stamps.begin() + std::min(n_stamps, (int)all_stamps.size()));

  FillParams fill;
  int pref = dist_pref(rng);
  if (pref == 0)
    fill.partition_preference = "";
  else if (pref == 1)
    fill.partition_preference = "few";
  else
    fill.partition_preference = "unique";

  for (int retry = 0; retry < 5; retry++) {
    if (generate_puzzle(fill, topo)) {
      KakuroDifficultyEstimator estimator(board);
      GeneratedPuzzle res;
      res.difficulty = estimator.estimate_difficulty_detailed();
      res.width = board->width;
      res.height = board->height;

      res.grid.resize(h, std::vector<PuzzleCell>(w));
      for (int r = 0; r < h; r++) {
        for (int c = 0; c < w; c++) {
          auto &src = board->grid[r][c];
          auto &dst = res.grid[r][c];
          dst.type = src.type;
          dst.clue_h = src.clue_h;
          dst.clue_v = src.clue_v;
          dst.solution = src.value;
        }
      }
      return res;
    }
    // retry with more density
    topo.density = std::min(0.75, *topo.density + 0.05);
    topo.num_stamps = (int)(*topo.num_stamps * 1.2);
  }

  return GeneratedPuzzle();
}

bool CSPSolver::prepare_new_topology(const TopologyParams &topo_params) {
  bool success = board->generate_topology(topo_params);
  if (!success || board->white_cells.size() < 12) {
    return false;
  }
  board->collect_white_cells();
  board->identify_sectors();
  return true;
}

bool CSPSolver::attempt_fill_and_validate(const FillParams &params) {
  const int MAX_FILL_ATTEMPTS = 100;
  const int MAX_REPAIR_ATTEMPTS = 5;
  int consecutive_repair_failures = 0;
  int fills_for_this_topology = 0;

  std::vector<ValueConstraint> cumulative_constraints;

  for (int fill_attempt = 0;
       fill_attempt < MAX_FILL_ATTEMPTS * MAX_REPAIR_ATTEMPTS; fill_attempt++) {

    // Check timeout inside fill loop
    if (check_timeout())
      return false;

    board->reset_values();

    // 1. Fill the board with values
    // NEW: Pass the cumulative_constraints to the solver
    if (!solve_fill(params, {}, cumulative_constraints, true)) {
      // If filling failed completely with these constraints, we might have
      // over-constrained it. Clear constraints to allow a fresh start on this
      // topology.
      if (!cumulative_constraints.empty()) {
        LOG_DEBUG(
            "  Fill failed with constraints. Clearing learned constraints.");
        cumulative_constraints.clear();
        continue;
      }
      // If it failed without constraints, this topology might be bad.
      continue;
    }

    // 2. Sync clues to the filled values
    calculate_clues();

    if (has_high_global_ambiguity()) {
      LOG_DEBUG("  Rejecting fill: high global ambiguity detected");
      continue;
    }

    // 3. Robust Uniqueness Check (The "Multi-Check")
    auto [result, alt_sol_opt] = perform_robust_uniqueness_check();

    if (result == UniquenessResult::UNIQUE) {
      // Final check with Estimator to ensure it meets difficulty targets
      KakuroDifficultyEstimator estimator(board);
      DifficultyResult diff = estimator.estimate_difficulty_detailed();

      if (diff.solution_count == 1) {
        LOG_DEBUG("=== SUCCESS! Unique " << diff.rating << " puzzle ===");
        return true;
      }
      result = UniquenessResult::MULTIPLE;
    }

    // Check timeout after uniqueness check (expensive operation)
    if (check_timeout())
      return false;

    // 4. Handle Repairs
    if (result == UniquenessResult::MULTIPLE) {
      fills_for_this_topology++;

      // --- NEW: LEARN FROM FAILURE ---
      // If we have an alternative solution, we know that the current fill
      // (Solution A) allowed an ambiguity (Solution B). To avoid generating
      // Solution A again, we pick a cell where they differ and forbid Solution
      // A's value there in the next pass.
      if (alt_sol_opt) {
        std::vector<Cell *> diff_cells;
        for (Cell *c : board->white_cells) {
          if (c->value && alt_sol_opt->count({c->r, c->c})) {
            if (*c->value != alt_sol_opt->at({c->r, c->c})) {
              diff_cells.push_back(c);
            }
          }
        }

        if (!diff_cells.empty()) {
          // Heuristic: Pick the cell with the most neighbors (highest degree),
          // as fixing it has the most impact on the board.
          std::sort(diff_cells.begin(), diff_cells.end(),
                    [this](Cell *a, Cell *b) {
                      return board->count_white_neighbors(a) >
                             board->count_white_neighbors(b);
                    });

          // Add a constraint: "In the next fill, this cell cannot be what it is
          // now."
          Cell *target = diff_cells[0];
          int bad_val = *target->value;
          cumulative_constraints.push_back({target, {bad_val}});

          LOG_DEBUG("  Learning: Forbidding val "
                    << bad_val << " at (" << target->r << "," << target->c
                    << ") for next attempt.");
        }
      }

      if (fills_for_this_topology < MAX_FILL_ATTEMPTS) {
        LOG_DEBUG("  Non-unique solution. Retrying fill for current topology ("
                  << fills_for_this_topology << "/" << MAX_FILL_ATTEMPTS
                  << ")");
        continue;
      }

      // Re-identify sectors just to be safe before repair
      board->collect_white_cells();
      board->identify_sectors();

#if KAKURO_ENABLE_LOGGING
      if (alt_sol_opt) {
        std::vector<std::pair<int, int>> highlights;
        for (Cell *c : board->white_cells) {
          if (c->value && alt_sol_opt->count({c->r, c->c}) &&
              alt_sol_opt->at({c->r, c->c}) != *c->value) {
            highlights.push_back({c->r, c->c});
          }
        }

        // 2. Prepare the alternative grid state
        std::unordered_map<Cell *, int> alt_sol_cells;
        for (auto &pair : *alt_sol_opt) {
          Cell *c = board->get_cell(pair.first.first, pair.first.second);
          if (c)
            alt_sol_cells[c] = pair.second;
        }
        auto alt_grid_state = board->get_grid_state(&alt_sol_cells);

        board->logger->log_step_with_highlights(
            GenerationLogger::STAGE_FILLING, "uniqueness_conflict",
            "Uniqueness conflict: multiple solutions found. Overlay available.",
            board->get_grid_state(), highlights, alt_grid_state);
      }
#endif

      if (alt_sol_opt && repair_topology_robust(*alt_sol_opt)) {
        // SUCCESS: The board has changed and is still valid.
        LOG_DEBUG(
            "  Repair successful. Restarting fill loop on modified topology.");
        fills_for_this_topology = 0;
        cumulative_constraints.clear();
        // Reset loop to start fresh on this modified board
        continue;
      } else {
        // FAILURE: Could not find a valid repair that maintained
        // connectivity/rules.
        LOG_DEBUG("  Repair failed or board invalid. Discarding topology.");
        return false; // This exits to generate_puzzle() which calls
                      // prepare_new_topology()
      }
    }
  }
  LOG_DEBUG("=== FAILURE: Maximum fill attempts ("
            << MAX_FILL_ATTEMPTS
            << ") reached without a unique solution for difficulty "
            << params.difficulty << " ===");
  return false;
}

std::pair<UniquenessResult,
          std::optional<std::unordered_map<std::pair<int, int>, int, PairHash>>>
CSPSolver::perform_robust_uniqueness_check() {
  // We check 3 times with different search seeds.
  // This catches "symmetric" solutions that a single search might miss.
  for (int i = 0; i < 3; i++) {
    // Check timeout after uniqueness check (expensive operation)
    if (check_timeout())
      return {UniquenessResult::INCONCLUSIVE, std::nullopt};

    auto [status, alt_sol] = check_uniqueness(150000, 42 + (i * 100));

    if (status == UniquenessResult::MULTIPLE)
      return {UniquenessResult::MULTIPLE, alt_sol};
    if (status == UniquenessResult::INCONCLUSIVE)
      return {UniquenessResult::INCONCLUSIVE, std::nullopt};
  }
  return {UniquenessResult::UNIQUE, std::nullopt};
}

bool CSPSolver::solve_fill(
    const std::string &difficulty, int max_nodes,
    const std::unordered_map<Cell *, int> &forced_assignments,
    const std::vector<ValueConstraint> &forbidden_constraints,
    bool ignore_clues) {
  FillParams params;
  params.difficulty = difficulty;
  params.max_nodes = max_nodes;
  return solve_fill(params, forced_assignments, forbidden_constraints,
                    ignore_clues);
}

bool CSPSolver::solve_fill(
    const FillParams &params,
    const std::unordered_map<Cell *, int> &forced_assignments,
    const std::vector<ValueConstraint> &forbidden_constraints,
    bool ignore_clues) {
  int max_nodes = params.max_nodes.value_or(30000);
  LOG_DEBUG("      solve_fill: difficulty="
            << params.difficulty << ", max_nodes=" << max_nodes
            << ", ignore_clues=" << ignore_clues);
  std::unordered_map<Cell *, int> assignment;
  int node_count = 0;

#if KAKURO_ENABLE_LOGGING
  if (!ignore_clues) { // Only log the main filling pass, not the helper ones
                       // usually
    board->logger->log_step(
        GenerationLogger::STAGE_FILLING, GenerationLogger::SUBSTAGE_START,
        "Starting fill solve. Max nodes: " + std::to_string(max_nodes),
        board->get_grid_state());
  }
#endif

  // Apply constraints
  for (auto &[cell, val] : forced_assignments) {
    if (cell->type == CellType::WHITE) {
      for (const auto &f : forbidden_constraints) {
        if (f.cell == cell) {
          for (int f_val : f.values) {
            if (val == f_val)
              return false; // Impossible constraints
          }
        }
      }

      if (is_consistent_number(cell, val, assignment, ignore_clues)) {
        assignment[cell] = val;
      } else {
        LOG_DEBUG("      solve_fill: Inconsistent number");
        return false;
      }
    }
  }

  std::vector<int> weights;
  std::string partition_preference = "";

  std::string difficulty = params.difficulty;
  if (difficulty == "very_easy") {
    weights = {20, 15, 5, 1, 1, 1, 5, 15, 20};
    partition_preference = "unique";
  } else if (difficulty == "easy") {
    weights = {10, 8, 6, 2, 1, 2, 6, 8, 10};
    partition_preference = "few";
  } else if (difficulty == "hard") {
    weights = {1, 2, 5, 10, 10, 10, 5, 2, 1};
    partition_preference = "";
  } else if (difficulty == "medium") {
    weights = {5, 5, 5, 5, 5, 5, 5, 5, 5};
    partition_preference = "few";
  } else {
    weights = {5, 5, 5, 5, 5, 5, 5, 5, 5};
    partition_preference = "";
  }

  // Overrides
  if (params.weights.has_value())
    weights = *params.weights;
  if (params.partition_preference.has_value())
    partition_preference = *params.partition_preference;

  bool result =
      backtrack_fill(assignment, node_count, max_nodes, weights, ignore_clues,
                     partition_preference, forbidden_constraints);
  LOG_DEBUG("      solve_fill result: " << (result ? "SUCCESS" : "FAIL")
                                        << ", nodes explored: " << node_count);
  return result;
}

bool CSPSolver::backtrack_fill(
    std::unordered_map<Cell *, int> &assignment, int &node_count, int max_nodes,
    const std::vector<int> &weights, bool ignore_clues,
    const std::string &partition_preference,
    const std::vector<ValueConstraint> &forbidden_constraints) {
  if (node_count > max_nodes) {
    LOG_DEBUG("        Max nodes exceeded (" << node_count << " > " << max_nodes
                                             << ")");
    return false;
  }
  node_count++;

  if (node_count % 1000 == 0) {
    // Check timeout after uniqueness check (expensive operation)
    if (check_timeout())
      return false;

    LOG_DEBUG("        Backtrack progress: "
              << node_count << " nodes, " << assignment.size() << "/"
              << board->white_cells.size() << " assigned");
  }

  std::vector<Cell *> unassigned;
  for (Cell *c : board->white_cells) {
    if (assignment.find(c) == assignment.end()) {
      unassigned.push_back(c);
    }
  }

  if (unassigned.empty()) {
    LOG_DEBUG("        All cells assigned!");

    // FINAL VALIDATION for easy puzzles
    if (!partition_preference.empty() && !ignore_clues) {
      LOG_DEBUG("        Validating partition difficulty for: "
                << partition_preference);
      if (!validate_partition_difficulty(assignment, partition_preference)) {
        LOG_DEBUG("        Partition difficulty validation FAILED");
        return false; // Reject this solution, backtrack
      }
      LOG_DEBUG("        Partition difficulty validation PASSED");
    }

    for (auto &[cell, val] : assignment) {
      cell->value = val;
    }
    return true;
  }

  // MRV
  Cell *var = nullptr;
  int min_domain = 10;

  for (Cell *c : board->white_cells) {
    if (assignment.find(c) == assignment.end()) {
      // Use the assignment map for filling phase
      int d_size = get_domain_size(c, &assignment, ignore_clues);

      if (d_size == 0)
        return false; // Dead end

      if (d_size < min_domain) {
        min_domain = d_size;
        var = c;
      }
      if (min_domain == 1)
        break;
    }
  }

  if (!var)
    return true;

  std::vector<int> domain;

  if (!partition_preference.empty()) {
    domain = get_partition_aware_domain(var, assignment, partition_preference,
                                        weights);
    if (node_count % 500 == 0) {
      LOG_DEBUG("        Partition-aware domain for ("
                << var->r << "," << var->c << "): size=" << domain.size());
    }
  } else {
    // Original approach
    last_scored_cell = var;
    last_candidate_scores.clear();

    std::vector<std::pair<int, double>> weighted_domain;
    std::uniform_real_distribution<> dist(0.01, 1.0);
    for (int i = 0; i < 9; i++) {
      int val = i + 1;
      double score = (double)weights[i] * dist(rng);
      weighted_domain.push_back({val, score});

      // Shadow calculations for visual logging (even if not used for sorting)
      double h_score =
          calculate_partition_score(var, val, assignment, 'h', "few");
      double v_score =
          calculate_partition_score(var, val, assignment, 'v', "few");
      double entropy = estimate_intersection_entropy(var, val, assignment);

      last_candidate_scores.push_back(
          {val, h_score, v_score, entropy, (double)weights[i], score});
    }
    std::sort(weighted_domain.begin(), weighted_domain.end(),
              [](const auto &a, const auto &b) { return a.second > b.second; });

    for (auto &p : weighted_domain) {
      domain.push_back(p.first);
    }
  }

  for (int val : domain) {
    // Check forbidden values from constraints
    bool forbidden = false;
    for (const auto &cons : forbidden_constraints) {
      if (cons.cell == var) {
        for (int f_val : cons.values) {
          if (val == f_val) {
            forbidden = true;
            break;
          }
        }
      }
      if (forbidden)
        break;
    }
    if (forbidden)
      continue;

    if (is_consistent_number(var, val, assignment, ignore_clues)) {
      assignment[var] = val;

      if (backtrack_fill(assignment, node_count, max_nodes, weights,
                         ignore_clues, partition_preference,
                         forbidden_constraints)) {
        return true;
      }
      assignment.erase(var);
    }
  }
  return false;
}

double CSPSolver::estimate_intersection_entropy(
    Cell *cell, int value, const std::unordered_map<Cell *, int> &assignment) {
  int h = estimate_future_domain_size(cell, value, 'h', assignment);
  int v = estimate_future_domain_size(cell, value, 'v', assignment);

  if (h == 0 || v == 0)
    return 100.0; // dead move

  int intersection = std::min(h, v);

  // log-scaled entropy
  return std::log2(1.0 + intersection);
}

int CSPSolver::estimate_future_domain_size(
    Cell *cell, int value, char direction,
    const std::unordered_map<Cell *, int> &assignment) {
  auto sector = (direction == 'h') ? cell->sector_h : cell->sector_v;
  if (!sector || sector->empty())
    return 0;

  int current_sum = value;
  uint16_t used_mask = (1 << value);
  int filled = 1;

  for (Cell *c : *sector) {
    if (c == cell)
      continue;
    if (assignment.count(c)) {
      int v = assignment.at(c);
      current_sum += v;
      used_mask |= (1 << v);
      filled++;
    }
  }

  int remaining = (int)sector->size() - filled;
  if (remaining <= 0)
    return 1; // forced completion

  // Determine clue
  Cell *first = (*sector)[0];
  int clue_r = (direction == 'h') ? first->r : first->r - 1;
  int clue_c = (direction == 'h') ? first->c - 1 : first->c;

  auto &clue_cell = board->grid[clue_r][clue_c];
  std::optional<int> clue_opt =
      (direction == 'h') ? clue_cell.clue_h : clue_cell.clue_v;

  if (!clue_opt.has_value())
    return 9; // unconstrained (should not happen in practice)

  int target = *clue_opt;
  int remaining_sum = target - current_sum;
  if (remaining_sum <= 0)
    return 0;

  int count = 0;

  for (int d = 1; d <= 9; d++) {
    if (used_mask & (1 << d))
      continue;

    // feasibility check
    int min_possible = d;
    int max_possible = d;

    int slots = remaining - 1;
    for (int i = 1; i <= 9 && slots > 0; i++) {
      if (!(used_mask & (1 << i)) && i != d) {
        min_possible += i;
        slots--;
      }
    }

    slots = remaining - 1;
    for (int i = 9; i >= 1 && slots > 0; i--) {
      if (!(used_mask & (1 << i)) && i != d) {
        max_possible += i;
        slots--;
      }
    }

    if (min_possible <= remaining_sum && max_possible >= remaining_sum) {
      count++;
    }
  }

  return count;
}

bool CSPSolver::has_high_global_ambiguity() {
  int bad_cells = 0;

  for (Cell *c : board->white_cells) {
    int domain = get_domain_size(c, nullptr, false);
    if (domain >= 4) {
      bad_cells++;
      LOG_DEBUG("    Ambiguity check: cell(" << c->r << "," << c->c
                                             << ") has domain size " << domain);
    }
    if (bad_cells >= 3) {
      LOG_DEBUG("    High global ambiguity detected: " << bad_cells
                                                       << " bad cells found.");
#if KAKURO_ENABLE_LOGGING
      if (board->logger->is_enabled()) {
        std::vector<std::pair<int, int>> highlights;
        std::ostringstream extra;
        extra << "{\"bc\": [";
        int b_count = 0;
        for (Cell *bc : board->white_cells) {
          int d = get_domain_size(bc, nullptr, false);
          if (d >= 4) {
            highlights.push_back({bc->r, bc->c});
            if (b_count > 0)
              extra << ",";
            extra << "{\"r\":" << bc->r << ",\"c\":" << bc->c << ",\"d\":" << d
                  << "}";
            b_count++;
          }
        }
        extra << "]}";
        board->logger->log_step_with_highlights(
            GenerationLogger::STAGE_FILLING, "ambiguity_rejection",
            "Rejecting fill: high global ambiguity detected (" +
                std::to_string(bad_cells) + " cells)",
            board->get_grid_state(), highlights, {});
        // Note: we can't easily pass 'extra' to log_step_with_highlights
        // without overloading it, but we can just use log_step if we want.
        // Actually, log_step_with_highlights uses extra_data internally
        // if we change the signature or just use the base log_step.
        // Let's stick to log_step for simplicity if we want extra data.
      }
#endif
      return true;
    }
  }
  if (bad_cells > 0) {
    LOG_DEBUG("    Ambiguity check: " << bad_cells
                                      << " bad cells found (threshold: 3).");
  }
  return false;
}

std::vector<int> CSPSolver::get_partition_aware_domain(
    Cell *cell, const std::unordered_map<Cell *, int> &assignment,
    const std::string &preference, const std::vector<int> &weights) {

  last_scored_cell = cell;
  last_candidate_scores.clear();
  std::vector<std::pair<int, double>> candidates;

  for (int val = 1; val <= 9; val++) {
    // Quick duplicate check
    bool duplicate = false;

    if (cell->sector_h && !cell->sector_h->empty()) {
      for (Cell *c : *(cell->sector_h)) {
        if (assignment.count(c) && assignment.at(c) == val) {
          duplicate = true;
          break;
        }
      }
    }

    if (!duplicate && cell->sector_v && !cell->sector_v->empty()) {
      for (Cell *c : *(cell->sector_v)) {
        if (assignment.count(c) && assignment.at(c) == val) {
          duplicate = true;
          break;
        }
      }
    }

    if (duplicate)
      continue;

    // Calculate partition scores for both directions
    double h_score =
        calculate_partition_score(cell, val, assignment, 'h', preference);
    double v_score =
        calculate_partition_score(cell, val, assignment, 'v', preference);

    double entropy_penalty =
        estimate_intersection_entropy(cell, val, assignment);

    // Combined score: lower is better (fewer partitions = easier)
    double difficulty_weight = (double)weights[val - 1];
    double combined_score =
        (h_score + v_score) +
        3.0 * entropy_penalty * (10.0 / std::max(difficulty_weight, 1.0));

    last_candidate_scores.push_back({val, h_score, v_score, entropy_penalty,
                                     difficulty_weight, combined_score});

    candidates.push_back({val, combined_score});
  }

  if (candidates.empty()) {
    LOG_DEBUG("          WARNING: No valid candidates for cell("
              << cell->r << "," << cell->c << ")");
    // Fallback: return all values 1-9 if no valid candidates found
    std::vector<int> result;
    for (int i = 1; i <= 9; i++)
      result.push_back(i);
    return result;
  }

  // Sort by score (lower = better), with some randomness
  std::uniform_real_distribution<> dist(0.0, 2.0);
  for (auto &cand : candidates) {
    cand.second += dist(rng);
  }

  // 2. Sort based on the now-static scores (Strict Weak Ordering satisfied)
  std::sort(candidates.begin(), candidates.end(),
            [](const auto &a, const auto &b) { return a.second < b.second; });

  std::vector<int> result;
  for (auto &[val, score] : candidates) {
    result.push_back(val);
  }
  return result;
}

double CSPSolver::calculate_partition_score(
    Cell *cell, int value, const std::unordered_map<Cell *, int> &assignment,
    char direction, const std::string &preference) {

  auto sector = (direction == 'h') ? cell->sector_h : cell->sector_v;

  // Safety check
  if (!sector || sector->empty())
    return 0.0;

  // Calculate current state of this sector
  int current_sum = value;
  int filled_count = 1;
  std::vector<Cell *> remaining_cells;

  for (Cell *c : *sector) {
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
      if (num_partitions == 1)
        return 0.0;
      else if (num_partitions == 2)
        return 1.0;
      else if (num_partitions <= 4)
        return 5.0;
      else
        return 20.0;
    } else if (preference == "few") {
      if (num_partitions <= 2)
        return 0.0;
      else if (num_partitions <= 4)
        return 2.0;
      else if (num_partitions <= 6)
        return 5.0;
      else
        return 15.0;
    }
  } else {
    // Sector not complete yet - estimate difficulty
    int remaining_count = (int)remaining_cells.size();

    // Get used digits
    std::unordered_set<int> used_digits;
    for (Cell *c : *sector) {
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

    if ((int)available.size() < remaining_count)
      return 100.0;

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

    if (sample_sums.empty())
      return 5.0; // Safety fallback

    double avg_partitions = 0;
    for (int s : sample_sums) {
      avg_partitions += count_partitions(s, sector_length);
    }
    avg_partitions /= sample_sums.size();

    if (preference == "unique") {
      if (avg_partitions <= 2)
        return 1.0;
      else if (avg_partitions <= 4)
        return 3.0;
      else
        return 8.0;
    } else if (preference == "few") {
      if (avg_partitions <= 4)
        return 1.0;
      else if (avg_partitions <= 6)
        return 3.0;
      else
        return 6.0;
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
    LOG_DEBUG("          Partition count: sum=" << target_sum
                                                << ", len=" << length << " -> "
                                                << result << " partitions");
  }

  return result;
}

int CSPSolver::count_partitions_recursive(int remaining_sum,
                                          int remaining_length, int min_digit,
                                          std::unordered_set<int> &used) {

  if (remaining_length == 0) {
    return (remaining_sum == 0) ? 1 : 0;
  }

  if (remaining_sum <= 0 || min_digit > 9)
    return 0;

  // Get available digits
  std::vector<int> available;
  for (int d = min_digit; d <= 9; d++) {
    if (used.find(d) == used.end()) {
      available.push_back(d);
    }
  }

  if ((int)available.size() < remaining_length)
    return 0;

  // Feasibility check
  int min_possible = 0;
  for (int i = 0; i < remaining_length && i < (int)available.size(); i++) {
    min_possible += available[i];
  }

  int max_possible = 0;
  int start = (int)available.size() - remaining_length;
  if (start < 0)
    start = 0;
  for (int i = start; i < (int)available.size(); i++) {
    max_possible += available[i];
  }

  if (remaining_sum < min_possible || remaining_sum > max_possible)
    return 0;

  int count = 0;
  for (int digit : available) {
    used.insert(digit);
    count += count_partitions_recursive(remaining_sum - digit,
                                        remaining_length - 1, digit + 1, used);
    used.erase(digit);
  }

  return count;
}

bool CSPSolver::validate_partition_difficulty(
    const std::unordered_map<Cell *, int> &assignment,
    const std::string &preference) {

  LOG_DEBUG("          Validating partition difficulty...");

  int easy_clue_count = 0;
  int total_clue_count = 0;

  // Check horizontal sectors
  for (const auto &sector : board->sectors_h) {
    if (sector->empty())
      continue;

    bool all_assigned = true;
    for (Cell *c : *(sector)) {
      if (assignment.find(c) == assignment.end()) {
        all_assigned = false;
        break;
      }
    }
    if (!all_assigned)
      continue;

    total_clue_count++;
    int clue_sum = 0;
    for (Cell *c : *(sector)) {
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
  for (const auto &sector : board->sectors_v) {
    if (sector->empty())
      continue;

    bool all_assigned = true;
    for (Cell *c : *(sector)) {
      if (assignment.find(c) == assignment.end()) {
        all_assigned = false;
        break;
      }
    }
    if (!all_assigned)
      continue;

    total_clue_count++;
    int clue_sum = 0;
    for (Cell *c : *(sector)) {
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

  LOG_DEBUG("          Easy clues: "
            << easy_clue_count << "/" << total_clue_count << " = "
            << (ratio * 100) << "% (required: " << (required_ratio * 100)
            << "%)");

  if (preference == "unique") {
    return ratio >= 0.80;
  } else if (preference == "few") {
    return ratio >= 0.60;
  }

  return true;
}

int CSPSolver::count_neighbors_filled(
    Cell *cell, const std::unordered_map<Cell *, int> &assignment) {
  int count = 0;

  if (cell->sector_h && !cell->sector_h->empty()) {
    for (Cell *n : *(cell->sector_h)) {
      if (assignment.find(n) != assignment.end()) {
        count++;
      }
    }
  }

  if (cell->sector_v && !cell->sector_v->empty()) {
    for (Cell *n : *(cell->sector_v)) {
      if (assignment.find(n) != assignment.end()) {
        count++;
      }
    }
  }

  return count;
}

bool CSPSolver::is_consistent_number(
    Cell *var, int value, const std::unordered_map<Cell *, int> &assignment,
    bool ignore_clues) {
  if (ignore_clues) {
    // Simple duplicate check for the filling phase
    auto has_dupe = [&](std::shared_ptr<std::vector<Cell *>> sector) {
      if (!sector)
        return false;
      for (Cell *p : *sector) {
        if (p == var)
          continue;
        if (assignment.count(p) && assignment.at(p) == value)
          return true;
        if (p->value.has_value() && *p->value == value)
          return true;
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
  for (auto &sector : board->sectors_h) {
    int sum = 0;
    for (Cell *c : *sector)
      sum += c->value.value_or(0);
    Cell *first = (*sector)[0];
    board->grid[first->r][first->c - 1].clue_h = sum;
  }
  for (auto &sector : board->sectors_v) {
    int sum = 0;
    for (Cell *c : *sector)
      sum += c->value.value_or(0);
    Cell *first = (*sector)[0];
    board->grid[first->r - 1][first->c].clue_v = sum;
  }
}

std::pair<UniquenessResult,
          std::optional<std::unordered_map<std::pair<int, int>, int, PairHash>>>
CSPSolver::check_uniqueness(int max_nodes, int seed_offset) {
  LOG_DEBUG("  Checking uniqueness using Logical Estimator...");

  // 1. Back up current solution
  std::unordered_map<Cell *, int> original_sol;
  std::unordered_map<std::pair<int, int>, int, PairHash> original_sol_coords;
  for (Cell *c : board->white_cells) {
    if (c->value) {
      original_sol[c] = *c->value;
      original_sol_coords[{c->r, c->c}] = *c->value;
    }
    c->value = std::nullopt; // Clear for solving
  }

  std::vector<std::unordered_map<std::pair<int, int>, int, PairHash>> found;
  int node_count = 0;
  bool timed_out = false;

  solve_for_uniqueness(found, original_sol_coords, node_count, max_nodes,
                       seed_offset, timed_out);

  for (Cell *c : board->white_cells) {
    if (original_sol.count(c))
      c->value = original_sol[c];
    else
      c->value = std::nullopt;
  }

  if (!found.empty()) {
    return {UniquenessResult::MULTIPLE, found[0]};
  }
  if (timed_out)
    return {UniquenessResult::INCONCLUSIVE, std::nullopt};
  return {UniquenessResult::UNIQUE, std::nullopt};
}

void CSPSolver::solve_for_uniqueness(
    std::vector<std::unordered_map<std::pair<int, int>, int, PairHash>>
        &found_solutions,
    const std::unordered_map<std::pair<int, int>, int, PairHash> &avoid_sol,
    int &node_count, int max_nodes, int seed, bool &timed_out) {

  if (!found_solutions.empty())
    return;
  if (node_count > max_nodes) {
    timed_out = true;
    return;
  }
  node_count++;

  if (node_count % 1000 == 0) {
    if (check_timeout()) {
      timed_out = true;
      return;
    }
  }

  Cell *var = nullptr;
  int min_domain = 10;

  // MRV Selection
  for (Cell *c : board->white_cells) {
    if (!c->value.has_value()) {
      int d_size = get_domain_size(c, nullptr, false);
      if (d_size == 0)
        return;
      if (d_size < min_domain) {
        min_domain = d_size;
        var = c;
      }
      if (min_domain == 1)
        break;
    }
  }

  if (!var) {
    // Found A solution. Is it different?
    std::unordered_map<std::pair<int, int>, int, PairHash> sol;
    bool is_different = false;
    for (Cell *c : board->white_cells) {
      int val = c->value.value_or(0);
      sol[{c->r, c->c}] = val;
      if (val != avoid_sol.at({c->r, c->c}))
        is_different = true;
    }
    if (is_different) {
      found_solutions.push_back(sol);
#if KAKURO_ENABLE_LOGGING
      // Log the alternative solution
      std::vector<std::pair<int, int>> highlights;

      // Construct alt grid state relative to avoid_sol for the highlighting
      for (const auto &[coords, val] : sol) {
        if (val != avoid_sol.at(coords)) {
          highlights.push_back(coords);
        }
      }

      std::unordered_map<Cell *, int> original_assignment;
      for (Cell *c : board->white_cells) {
        if (avoid_sol.count({c->r, c->c})) {
          original_assignment[c] = avoid_sol.at({c->r, c->c});
        }
      }
      auto original_grid_state = board->get_grid_state(&original_assignment);

      // 3. The current board state holds the "Alternative" solution
      auto alternative_grid_state = board->get_grid_state();

      board->logger->log_step_with_highlights(
          GenerationLogger::STAGE_UNIQUENESS,
          GenerationLogger::SUBSTAGE_ALTERNATIVE_FOUND,
          "Found component-wise alternative solution (" +
              std::to_string(found_solutions.size()) + ")",
          original_grid_state, highlights, alternative_grid_state);
#endif
    }

    return;
  }

  // Check limit - if we found enough, stop recursing
  if (found_solutions.size() >= 3)
    return;

  std::vector<int> vals = {1, 2, 3, 4, 5, 6, 7, 8, 9};
  int target_val = avoid_sol.at({var->r, var->c});

  std::shuffle(vals.begin(), vals.end(),
               std::default_random_engine(seed + node_count));

  // Move the 'avoid' value to the end of the list
  std::partition(vals.begin(), vals.end(),
                 [&](int v) { return v != target_val; });

  for (int v : vals) {
    if (is_valid_move(var, v, nullptr, false)) {
      var->value = v;
      solve_for_uniqueness(found_solutions, avoid_sol, node_count, max_nodes,
                           seed, timed_out);
      var->value = std::nullopt;
      if (!found_solutions.empty() || timed_out)
        return;
    }
  }
}

int CSPSolver::get_domain_size(
    Cell *cell, const std::unordered_map<Cell *, int> *assignment,
    bool ignore_clues) {
  int count = 0;
  for (int v = 1; v <= 9; v++) {
    if (is_valid_move(cell, v, assignment, ignore_clues)) {
      count++;
    }
  }
  return count;
}

bool CSPSolver::is_valid_move(Cell *cell, int val,
                              const std::unordered_map<Cell *, int> *assignment,
                              bool ignore_clues) {
  auto check_sector = [&](std::shared_ptr<std::vector<Cell *>> sector,
                          bool is_horz) {
    if (!sector || sector->empty())
      return true;

    int sum = val;
    int filled_count = 1;
    uint16_t used_mask = (1 << val);

    for (Cell *p : *sector) {
      if (p == cell)
        continue;
      int v = 0;
      if (assignment && assignment->count(p))
        v = assignment->at(p);
      else if (p->value.has_value())
        v = *p->value;

      if (v > 0) {
        if (v == val)
          return false;
        sum += v;
        used_mask |= (1 << v);
        filled_count++;
      }
    }

    // If we are ignoring clues (Filling Phase), we stop here after the
    // duplicate check
    if (ignore_clues)
      return true;

    // FIND THE CLUE (Robust Indexing)
    Cell *first = (*sector)[0];
    int clue_r = is_horz ? first->r : first->r - 1;
    int clue_c = is_horz ? first->c - 1 : first->c;

    // Safety bounds check
    if (clue_r < 0 || clue_c < 0)
      return false;

    auto &clue_cell = board->grid[clue_r][clue_c];
    std::optional<int> clue_opt = is_horz ? clue_cell.clue_h : clue_cell.clue_v;

    // CRITICAL: If no clue is found, this move is INVALID (not "anything goes")
    if (!clue_opt.has_value())
      return false;

    int target = *clue_opt;
    int remaining_cells = (int)sector->size() - filled_count;

    if (sum > target)
      return false;
    if (remaining_cells > 0) {
      int min_rem = 0, max_rem = 0, f_min = 0, f_max = 0;
      for (int i = 1; i <= 9 && f_min < remaining_cells; ++i) {
        if (!(used_mask & (1 << i))) {
          min_rem += i;
          f_min++;
        }
      }
      for (int i = 9; i >= 1 && f_max < remaining_cells; --i) {
        if (!(used_mask & (1 << i))) {
          max_rem += i;
          f_max++;
        }
      }
      if (sum + min_rem > target || sum + max_rem < target)
        return false;
    } else if (sum != target)
      return false;

    return true;
  };

  return check_sector(cell->sector_h, true) &&
         check_sector(cell->sector_v, false);
}

bool CSPSolver::repair_topology_robust(
    const std::unordered_map<std::pair<int, int>, int, PairHash> &alt_sol) {

  LOG_DEBUG("  Attempting topology repair");

  // Find cells where solutions differ
  std::vector<Cell *> diffs;
  for (Cell *c : board->white_cells) {
    if (c->value && alt_sol.count({c->r, c->c}) &&
        alt_sol.at({c->r, c->c}) != *c->value) {
      diffs.push_back(c);
    }
  }

  LOG_DEBUG("  Found " << diffs.size() << " differing cells");
  if (diffs.empty())
    return false;

  // Sort by neighbor count (prefer blocking high-connectivity cells)
  std::shuffle(diffs.begin(), diffs.end(), rng);

  // 2. Snapshot the grid state
  struct GridSnapshot {
    std::vector<std::vector<CellType>> types;
  } backup;
  backup.types.resize(board->height, std::vector<CellType>(board->width));
  for (int r = 0; r < board->height; r++) {
    for (int c = 0; c < board->width; c++) {
      backup.types[r][c] = board->grid[r][c].type;
    }
  }

  // 3. Try multiple repair candidates
  // We try more than before to increase the chance of success
  int max_candidates_to_test = std::min(15, (int)diffs.size());

  for (int i = 0; i < max_candidates_to_test; i++) {
    Cell *target = diffs[i];

    // Restore to clean snapshot before each attempt
    for (int r = 0; r < board->height; r++) {
      for (int c = 0; c < board->width; c++) {
        board->grid[r][c].type = backup.types[r][c];
      }
    }

    // Try the smart removal
    if (board->try_remove_and_reconnect(target->r, target->c)) {
      // Run full stabilization to ensure the new "bridge" didn't create new
      // issues
      board->stabilize_grid(false);
    } else {
      continue;
    }

    // CHECK IF IT ACTUALLY CHANGED
    bool changed = false;
    for (int r = 0; r < board->height; r++) {
      for (int c = 0; c < board->width; c++) {
        if (board->grid[r][c].type != backup.types[r][c]) {
          changed = true;
          break;
        }
      }
      if (changed)
        break;
    }

    if (!changed) {
#if KAKURO_ENABLE_LOGGING
      board->logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                              GenerationLogger::SUBSTAGE_REPAIR_ATTEMPT,
                              "Topology repair did not change the board",
                              board->get_grid_state());
#endif
      continue;
    }

    board->identify_sectors();
    if (!board->validate_topology_structure()) {
#if KAKURO_ENABLE_LOGGING
      board->logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                              GenerationLogger::SUBSTAGE_REPAIR_ATTEMPT,
                              "Topology repair failed to create a valid board",
                              board->get_grid_state());
#endif
      continue;
    }

    if (board->white_cells.size() <= 12) {
#if KAKURO_ENABLE_LOGGING
      board->logger->log_step(
          GenerationLogger::STAGE_TOPOLOGY,
          GenerationLogger::SUBSTAGE_REPAIR_ATTEMPT,
          "Topology repair failed to create a valid board (too small)",
          board->get_grid_state());
#endif
      continue;
    }

    // If we got here, the board is valid and DIFFERENT
#if KAKURO_ENABLE_LOGGING
    board->logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                            GenerationLogger::SUBSTAGE_REPAIR_ATTEMPT,
                            "Topology repaired successfully",
                            board->get_grid_state());
#endif
    return true;
  }

  LOG_DEBUG("  All repair attempts failed");
  return false;
}

std::unordered_map<Cell *, int> CSPSolver::generate_breaking_constraints(
    const std::unordered_map<std::pair<int, int>, int, PairHash> &alt_sol,
    const std::unordered_map<std::pair<int, int>, int, PairHash> &prev_sol) {

  std::unordered_map<Cell *, int> constraints;
  std::vector<Cell *> diffs;

  for (Cell *c : board->white_cells) {
    if (alt_sol.count({c->r, c->c}) && prev_sol.count({c->r, c->c})) {
      if (alt_sol.at({c->r, c->c}) != prev_sol.at({c->r, c->c})) {
        diffs.push_back(c);
      }
    }
  }

  if (!diffs.empty()) {
    Cell *target =
        diffs[std::uniform_int_distribution<>(0, (int)diffs.size() - 1)(rng)];
    auto it_prev = prev_sol.find({target->r, target->c});
    auto it_alt = alt_sol.find({target->r, target->c});

    if (it_prev != prev_sol.end() && it_alt != alt_sol.end()) {
      int val_a = it_prev->second;
      int val_b = it_alt->second;

      std::vector<int> domain;
      for (int i = 1; i <= 9; i++)
        if (i != val_a && i != val_b)
          domain.push_back(i);

      if (!domain.empty()) {
        int new_val = domain[std::uniform_int_distribution<>(
            0, (int)domain.size() - 1)(rng)];
        constraints[target] = new_val;
      }
    }
  }
  return constraints;
}

bool CSPSolver::is_connected(
    const std::unordered_set<std::pair<int, int>, PairHash> &coords) {

  if (coords.empty())
    return false;

  auto start = *coords.begin();
  std::queue<std::pair<int, int>> q;
  q.push(start);

  std::unordered_set<std::pair<int, int>, PairHash> visited;
  visited.insert(start);

  int count = 0;
  std::vector<std::pair<int, int>> dirs = {{0, 1}, {0, -1}, {1, 0}, {-1, 0}};

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