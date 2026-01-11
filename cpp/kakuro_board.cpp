#include "kakuro_cpp.h"
#include <algorithm>
#include <ctime>
#include <iostream>
#include <queue>

namespace kakuro {

KakuroBoard::KakuroBoard(int w, int h)
    : width(w), height(h), rng(std::random_device{}()) {
  // Initialize grid
  grid.resize(height);
  for (int r = 0; r < height; r++) {
    grid[r].reserve(width);
    for (int c = 0; c < width; c++) {
      grid[r].emplace_back(r, c, CellType::BLOCK);
    }
  }
  logger = std::make_shared<GenerationLogger>();
}

Cell *KakuroBoard::get_cell(int r, int c) {
  if (r >= 0 && r < height && c >= 0 && c < width) {
    return &grid[r][c];
  }
  return nullptr;
}

// Helper for logging
std::vector<std::vector<std::pair<std::string, int>>>
KakuroBoard::get_grid_state(
    const std::unordered_map<Cell *, int> *assignment) const {
  std::vector<std::vector<std::pair<std::string, int>>> state;
  for (int r = 0; r < height; ++r) {
    std::vector<std::pair<std::string, int>> row_state;
    for (int c = 0; c < width; ++c) {
      std::string type =
          (grid[r][c].type == CellType::BLOCK) ? "BLOCK" : "WHITE";
      int val = grid[r][c].value.value_or(0);

      if (assignment) {
        // Look up in assignment map
        // Helper to find non-const pointer equivalent
        // We know the map keys are pointers to these cells
        auto it = assignment->find(const_cast<Cell *>(&grid[r][c]));
        if (it != assignment->end()) {
          val = it->second;
        }
      }
      row_state.push_back({type, val});
    }
    state.push_back(row_state);
  }
  return state;
}

void KakuroBoard::reset_values() {
  LOG_DEBUG("Resetting values");
  for (int r = 0; r < height; r++) {
    for (int c = 0; c < width; c++) {
      grid[r][c].value = std::nullopt;
      grid[r][c].clue_h = std::nullopt;
      grid[r][c].clue_v = std::nullopt;
    }
  }
  LOG_DEBUG("Values reset");
}

void KakuroBoard::set_block(int r, int c) {
  Cell *cell = get_cell(r, c);
  if (cell && cell->type != CellType::BLOCK) {
    cell->type = CellType::BLOCK;
    cell->value = std::nullopt;
  }
}

void KakuroBoard::set_white(int r, int c) {
  if (r >= 1 && r < height - 1 && c >= 1 && c < width - 1) {
    grid[r][c].type = CellType::WHITE;
  }
}

bool KakuroBoard::generate_topology(double density, int max_sector_length,
                                    std::string difficulty) {
  TopologyParams params;
  params.difficulty = difficulty;
  params.density = density;
  params.max_sector_length = max_sector_length;
  apply_topology_defaults(params);
  return generate_topology(params);
}

void KakuroBoard::apply_topology_defaults(TopologyParams &params) {
  int area = (width - 2) * (height - 2);
  std::string difficulty = params.difficulty;

  if (difficulty == "very_easy") {
    if (!params.stamps.has_value())
      params.stamps = {{2, 2}, {2, 3}, {3, 2}, {2, 4}, {4, 2}};
    if (!params.num_stamps.has_value())
      params.num_stamps =
          std::uniform_int_distribution<>(6, 8)(rng) * area / 100;
    if (!params.min_cells.has_value())
      params.min_cells = 16;
    if (!params.max_run_len.has_value())
      params.max_run_len = 5;
    if (!params.max_patch_size.has_value())
      params.max_patch_size = 3;
    if (!params.island_mode.has_value())
      params.island_mode = true;
    if (!params.max_sector_length.has_value())
      params.max_sector_length = 5;
    if (!params.max_run_len_soft.has_value())
      params.max_run_len_soft = 2;
    if (!params.max_run_len_soft_prob.has_value())
      params.max_run_len_soft_prob = 0.8;
  } else if (difficulty == "easy") {
    if (!params.stamps.has_value())
      params.stamps = {{2, 3}, {3, 2}, {2, 4}, {4, 2}};
    if (!params.num_stamps.has_value())
      params.num_stamps =
          std::uniform_int_distribution<>(8, 10)(rng) * area / 100;
    if (!params.min_cells.has_value())
      params.min_cells = 22;
    if (!params.max_run_len.has_value())
      params.max_run_len = 6;
    if (!params.max_run_len_soft.has_value())
      params.max_run_len_soft = 3;
    if (!params.max_run_len_soft_prob.has_value())
      params.max_run_len_soft_prob = 0.5;
    if (!params.max_patch_size.has_value())
      params.max_patch_size = 3;
    if (!params.island_mode.has_value())
      params.island_mode = true;
    if (!params.max_sector_length.has_value())
      params.max_sector_length = 6;
  } else if (difficulty == "medium") {
    if (!params.stamps.has_value())
      params.stamps = {{2, 3}, {3, 2}, {2, 5}, {5, 2},
                       {2, 6}, {6, 2}, {2, 2}, {3, 3}};
    if (!params.num_stamps.has_value())
      params.num_stamps =
          std::uniform_int_distribution<>(8, 12)(rng) * area / 100;
    if (!params.min_cells.has_value())
      params.min_cells = (int)(area * 0.25);
    if (!params.max_run_len.has_value())
      params.max_run_len = 8;
    if (!params.max_run_len_soft.has_value())
      params.max_run_len_soft = 4;
    if (!params.max_run_len_soft_prob.has_value())
      params.max_run_len_soft_prob = 0.4;
    if (!params.max_patch_size.has_value())
      params.max_patch_size = 3;
    if (!params.max_sector_length.has_value())
      params.max_sector_length = 8;
  } else if (difficulty == "hard") {
    if (!params.stamps.has_value())
      params.stamps = {{2, 3}, {3, 2}, {2, 5}, {5, 2}};
    if (!params.num_stamps.has_value())
      params.num_stamps =
          std::uniform_int_distribution<>(10, 12)(rng) * area / 100;
    if (!params.min_cells.has_value())
      params.min_cells = (int)(area * 0.25);
    if (!params.max_run_len.has_value())
      params.max_run_len = 9;
    if (!params.max_run_len_soft.has_value())
      params.max_run_len_soft = 5;
    if (!params.max_run_len_soft_prob.has_value())
      params.max_run_len_soft_prob = 0.3;
    if (!params.max_patch_size.has_value())
      params.max_patch_size = 3;
    if (!params.max_sector_length.has_value())
      params.max_sector_length = 9;
  } else if (difficulty == "very_hard") {
    if (!params.stamps.has_value())
      params.stamps = {{2, 3}, {3, 2}, {2, 4}, {4, 2}, {2, 5},
                       {5, 2}, {2, 6}, {6, 2}, {2, 2}, {3, 3}};
    if (!params.num_stamps.has_value())
      params.num_stamps =
          std::uniform_int_distribution<>(12, 16)(rng) * area / 100;
    if (!params.min_cells.has_value())
      params.min_cells = (int)(area * 0.25);
    if (!params.max_run_len.has_value())
      params.max_run_len = 9;
    if (!params.max_run_len_soft.has_value())
      params.max_run_len_soft = 6;
    if (!params.max_run_len_soft_prob.has_value())
      params.max_run_len_soft_prob = 0.25;
    if (!params.max_patch_size.has_value())
      params.max_patch_size = 4;
    if (!params.max_sector_length.has_value())
      params.max_sector_length = 9;
  } else if (difficulty == "extreme") {
    if (!params.stamps.has_value())
      params.stamps = {{2, 3}, {3, 2}, {2, 4}, {4, 2}, {2, 5},
                       {5, 2}, {2, 6}, {6, 2}, {2, 2}, {3, 3}};
    if (!params.num_stamps.has_value())
      params.num_stamps =
          std::uniform_int_distribution<>(14, 20)(rng) * area / 100;
    if (!params.min_cells.has_value())
      params.min_cells = (int)(area * 0.3);
    if (!params.max_run_len.has_value())
      params.max_run_len = 9;
    if (!params.max_run_len_soft.has_value())
      params.max_run_len_soft = 7;
    if (!params.max_run_len_soft_prob.has_value())
      params.max_run_len_soft_prob = 0.25;
    if (!params.max_patch_size.has_value())
      params.max_patch_size = 5;
    if (!params.max_sector_length.has_value())
      params.max_sector_length = 9;
  }
}

bool KakuroBoard::generate_topology(const TopologyParams &params) {
  const int MAX_RETRIES = 60;

  // Baseline Defaults (only if NOT in ANY difficulty block or provided in
  // params)
  std::vector<std::pair<int, int>> stamps = params.stamps.value_or(
      std::vector<std::pair<int, int>>{{1, 3}, {3, 1}, {2, 2}, {3, 3}});
  int num_stamps = params.num_stamps.value_or(20);
  int min_cells = params.min_cells.value_or(12);
  int max_run_len = params.max_run_len.value_or(9);
  int max_run_len_soft = params.max_run_len_soft.value_or(0);
  double max_run_len_soft_prob = params.max_run_len_soft_prob.value_or(0.0);
  int max_patch_size = params.max_patch_size.value_or(5);
  bool island_mode = params.island_mode.value_or(true);
  double density = params.density.value_or(0.60);
  int max_sector_length = params.max_sector_length.value_or(9);

  for (int attempt = 0; attempt < MAX_RETRIES; attempt++) {
    white_cells.clear();
    sectors_h.clear(); // Clear sectors explicitly to prevent pointer
                       // invalidation issues
    sectors_v.clear();

#if KAKURO_ENABLE_LOGGING
    logger->start_new_kakuro();
    logger->log_step(
        GenerationLogger::STAGE_TOPOLOGY, GenerationLogger::SUBSTAGE_START,
        "Starting topology generation attempt " + std::to_string(attempt + 1) +
            " with density=" + std::to_string(density),
        get_grid_state());
#endif

    // 1. Clear Grid (All Block)
    for (int r = 0; r < height; r++) {
      for (int c = 0; c < width; c++) {
        grid[r][c].type = CellType::BLOCK;
        grid[r][c].value = std::nullopt;
        grid[r][c].clue_h = std::nullopt;
        grid[r][c].clue_v = std::nullopt;
        grid[r][c].sector_h = nullptr;
        grid[r][c].sector_v = nullptr;
      }
    }

    bool success = false;
    if (island_mode) {
      // Place initial seed in center to guarantee core connectivity
      stamp_rect(height / 2 - 1, width / 2 - 1, 2, 2);
      success = generate_stamps(stamps, num_stamps);
#if KAKURO_ENABLE_LOGGING
      logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                       GenerationLogger::SUBSTAGE_STAMP_PLACEMENT,
                       "Generated stamps (island mode)", get_grid_state());
#endif
    } else {
      if (place_random_seed()) {
#if KAKURO_ENABLE_LOGGING
        logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                         GenerationLogger::SUBSTAGE_SEED_PLACEMENT,
                         "Placed random seed", get_grid_state());
#endif
        grow_lattice(density, max_sector_length);
#if KAKURO_ENABLE_LOGGING
        logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                         GenerationLogger::SUBSTAGE_LATTICE_GROWTH,
                         "Grew lattice", get_grid_state());
#endif
        collect_white_cells();
        success = !white_cells.empty();
      }
    }

    if (!success) {
#if KAKURO_ENABLE_LOGGING
      logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                       GenerationLogger::SUBSTAGE_VALIDATION_FAILED,
                       "Initial generation failed", get_grid_state());
#endif
      continue;
    }

    // Filters & Stabilization: Convergent Loop
    bool changed = true;
    int iterations = 0;
    const int MAX_TOPOLOGY_LOOPS = 20;

    while (changed && iterations < MAX_TOPOLOGY_LOOPS) {
      changed = false;
      iterations++;

      if (!island_mode) {
        changed |= break_large_patches(max_patch_size);
        changed |= stabilize_grid(false);
      } else {
        changed |= slice_long_runs(max_run_len);
        if (max_run_len_soft > 0 && max_run_len_soft_prob > 0) {
          changed |= slice_soft_runs(max_run_len_soft, max_run_len_soft_prob);
        }
        changed |= break_large_patches(max_patch_size);
        changed |= prune_singles();
        changed |= break_single_runs();
        changed |= ensure_connectivity();
      }
    }

    collect_white_cells();

    // Final Validation
    if ((int)white_cells.size() < min_cells) {
#if KAKURO_ENABLE_LOGGING
      logger->log_step(
          GenerationLogger::STAGE_TOPOLOGY,
          GenerationLogger::SUBSTAGE_VALIDATION_FAILED,
          "Too few white cells: " + std::to_string(white_cells.size()) + " < " +
              std::to_string(min_cells),
          get_grid_state());
#endif
      continue;
    }
    if (!check_connectivity()) {
#if KAKURO_ENABLE_LOGGING
      logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                       GenerationLogger::SUBSTAGE_VALIDATION_FAILED,
                       "Connectivity check failed", get_grid_state());
#endif
      continue;
    }
    if (!validate_clue_headers()) {
#if KAKURO_ENABLE_LOGGING
      logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                       GenerationLogger::SUBSTAGE_VALIDATION_FAILED,
                       "Clue header validation failed", get_grid_state());
#endif
      continue;
    }

    identify_sectors();

    if (!validate_topology_structure()) {
      LOG_DEBUG("Topology structure validation failed");
#if KAKURO_ENABLE_LOGGING
      logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                       GenerationLogger::SUBSTAGE_VALIDATION_FAILED,
                       "Topology structure validation failed",
                       get_grid_state());
#endif
      continue; // Try next attempt
    }

#if KAKURO_ENABLE_LOGGING
    logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                     GenerationLogger::SUBSTAGE_COMPLETE,
                     "Topology generation successful", get_grid_state());
#endif
    return true;
  }
  LOG_ERROR("Failed to generate topology after "
            << MAX_RETRIES << " retries. min_cells=" << min_cells
            << ", target_density=" << density);
#if KAKURO_ENABLE_LOGGING
  logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                   GenerationLogger::SUBSTAGE_FAILED,
                   "Failed to generate topology after " +
                       std::to_string(MAX_RETRIES) + " retries",
                   get_grid_state());
#endif
  return false;
}

bool KakuroBoard::validate_topology_structure() {
  auto fail = [&](int r, int c, const std::string &msg) {
    LOG_DEBUG("Topology Validation Failed at (" << r << "," << c
                                                << "): " << msg);
#if KAKURO_ENABLE_LOGGING
    if (logger && logger->is_enabled()) {
      logger->log_step_with_highlights(
          GenerationLogger::STAGE_TOPOLOGY,
          GenerationLogger::SUBSTAGE_VALIDATION_FAILED,
          "Structure Error: " + msg, get_grid_state(),
          {{r, c}} // Highlight the problematic cell
      );
    }
#endif
    return false;
  };

  // Check horizontal sectors
  for (const auto &sector : sectors_h) {
    if (sector->empty())
      continue;

    Cell *first = (*sector)[0];
    int clue_r = first->r;
    int clue_c = first->c - 1;

    if (clue_c < 0 || clue_c >= width)
      return fail(first->r, first->c,
                  "Horizontal sector starts at col 0 (no room for clue block) "
                  "or goes out too far");
    if (grid[clue_r][clue_c].type != CellType::BLOCK)
      return fail(clue_r, clue_c,
                  "Horizontal sector not preceded by a BLOCK cell");
  }

  // Check vertical sectors
  for (const auto &sector : sectors_v) {
    if (sector->empty())
      continue;

    Cell *first = (*sector)[0];
    int clue_r = first->r - 1;
    int clue_c = first->c;

    if (clue_r < 0 || clue_r >= height)
      return fail(first->r, first->c,
                  "Vertical sector starts at row 0 (no room for clue block) "
                  "or goes out too far");
    if (grid[clue_r][clue_c].type != CellType::BLOCK)
      return fail(clue_r, clue_c,
                  "Vertical sector not preceded by a BLOCK cell");
  }

  // Check that no block cell has orphaned clues
  for (int r = 0; r < height; r++) {
    for (int c = 0; c < width; c++) {
      if (grid[r][c].type != CellType::BLOCK)
        continue;

      // If this block has a horizontal clue, there must be white cells to the
      // right
      if (grid[r][c].clue_h.has_value()) {
        bool has_white = false;
        for (int cc = c + 1; cc < width; cc++) {
          if (grid[r][cc].type == CellType::WHITE) {
            has_white = true;
            break;
          }
          if (grid[r][cc].type == CellType::BLOCK)
            break;
        }
        if (!has_white) {
          LOG_DEBUG("Orphaned horizontal clue at (" << r << "," << c << ")");
          return fail(
              r, c,
              "Block has horizontal clue but no white cells to the right");
        }
      }

      // If this block has a vertical clue, there must be white cells below
      if (grid[r][c].clue_v.has_value()) {
        bool has_white = false;
        // A valid clue must have at least one white cell immediately below
        if (r + 1 < height && grid[r + 1][c].type == CellType::WHITE) {
          has_white = true;
        }
        if (!has_white) {
          return fail(r, c, "Block has vertical clue but no white cells below");
        }
      }
    }
  }

  return true;
}

bool KakuroBoard::place_random_seed() {
  int margin_x = std::max(1, width / 4);
  int margin_y = std::max(1, height / 4);

  int min_r = margin_y, max_r = height - 1 - margin_y;
  int min_c = margin_x, max_c = width - 1 - margin_x;

  if (min_r >= max_r) {
    min_r = 1;
    max_r = height - 2;
  }
  if (min_c >= max_c) {
    min_c = 1;
    max_c = width - 2;
  }

  std::uniform_int_distribution<> dist_r(min_r, max_r);
  std::uniform_int_distribution<> dist_c(min_c, max_c);

  for (int i = 0; i < 20; i++) {
    int r = dist_r(rng);
    int c = dist_c(rng);

    if (r - 1 > 0 && r + 1 < height - 1 && c - 1 > 0 && c + 1 < width - 1) {
      // Place Cross
      std::vector<std::pair<int, int>> coords = {
          {r, c}, {r, c - 1}, {r, c + 1}, {r - 1, c}, {r + 1, c}};

      for (auto [cr, cc] : coords) {
        set_white(cr, cc);
        set_white(height - 1 - cr, width - 1 - cc);
      }

      collect_white_cells();
      return true;
    }
  }

  return false;
}

void KakuroBoard::grow_lattice(double density, int max_sector_length) {
  int target_white = (int)((width - 2) * (height - 2) * density);
  int current_white = (int)white_cells.size();

  int attempts = 0;
  const int max_attempts = 2000;

  std::uniform_int_distribution<> len_dist(2, max_sector_length);
  std::uniform_int_distribution<> bool_dist(0, 1);

  while (current_white < target_white && attempts < max_attempts) {
    if (white_cells.empty())
      break;

    // Pick random white cell
    std::uniform_int_distribution<> cell_dist(0, (int)white_cells.size() - 1);
    Cell *source = white_cells[cell_dist(rng)];
    int r = source->r;
    int c = source->c;

    // Determine orientation
    bool has_h =
        (get_cell(r, c - 1) && get_cell(r, c - 1)->type == CellType::WHITE) ||
        (get_cell(r, c + 1) && get_cell(r, c + 1)->type == CellType::WHITE);
    bool has_v =
        (get_cell(r - 1, c) && get_cell(r - 1, c)->type == CellType::WHITE) ||
        (get_cell(r + 1, c) && get_cell(r + 1, c)->type == CellType::WHITE);

    bool grow_vert;
    if (has_h && has_v)
      grow_vert = bool_dist(rng);
    else if (has_h)
      grow_vert = true;
    else if (has_v)
      grow_vert = false;
    else
      grow_vert = bool_dist(rng);

    int new_len = len_dist(rng);

    // Shuffle shifts
    std::vector<int> shifts(new_len);
    for (int i = 0; i < new_len; i++)
      shifts[i] = i;
    std::shuffle(shifts.begin(), shifts.end(), rng);

    bool placed = false;
    for (int shift : shifts) {
      std::vector<std::pair<int, int>> cells_indices;
      bool possible = true;

      for (int k = 0; k < new_len; k++) {
        int idx = k - shift;
        int nr = grow_vert ? r + idx : r;
        int nc = grow_vert ? c : c + idx;

        if (nr < 1 || nr >= height - 1 || nc < 1 || nc >= width - 1) {
          possible = false;
          break;
        }
        cells_indices.push_back({nr, nc});
      }

      if (possible) {
        bool added_new = false;
        for (auto [cr, cc] : cells_indices) {
          if (grid[cr][cc].type == CellType::BLOCK) {
            set_white(cr, cc);
            set_white(height - 1 - cr, width - 1 - cc);
            added_new = true;
          }
        }

        if (added_new) {
          placed = true;
          break;
        }
      }
    }

    if (placed) {
      collect_white_cells();
      current_white = (int)white_cells.size();
      attempts = 0;
    } else {
      attempts++;
    }
  }
}

bool KakuroBoard::generate_stamps(
    const std::vector<std::pair<int, int>> &shapes, int iterations) {
  int current_iter = 0;
  int failures = 0;

  while (current_iter < iterations && failures < 20) {
    collect_white_cells();
    if (white_cells.empty())
      return false;

    std::uniform_int_distribution<> dist(0, (int)white_cells.size() - 1);
    Cell *anchor = white_cells[dist(rng)];

    std::uniform_int_distribution<> shape_dist(0, (int)shapes.size() - 1);
    auto [h, w] = shapes[shape_dist(rng)];

    std::uniform_int_distribution<> offset_r_dist(-(h - 1), 0);
    std::uniform_int_distribution<> offset_c_dist(-(w - 1), 0);

    int top_r = anchor->r + offset_r_dist(rng);
    int left_c = anchor->c + offset_c_dist(rng);

    // Bounds Check (Strict 1-cell border)
    if (top_r >= 1 && left_c >= 1 && top_r + h < height - 1 &&
        left_c + w < width - 1) {

      stamp_rect(top_r, left_c, h, w);
      current_iter++;
    } else {
      failures++;
    }
  }
  collect_white_cells();
  return !white_cells.empty();
}

void KakuroBoard::stamp_rect(int r, int c, int h, int w) {
  for (int i = 0; i < h; i++) {
    for (int j = 0; j < w; j++) {
      set_white(r + i, c + j);
      set_white(height - 1 - (r + i), width - 1 - (c + j));
    }
  }
}

bool KakuroBoard::slice_long_runs(int max_len) {
  bool changed = false;
  // Horizontal
  for (int r = 1; r < height - 1; r++) {
    int length = 0;
    int run_start = -1;
    for (int c = 1; c < width; c++) {
      if (grid[r][c].type == CellType::WHITE) {
        if (run_start == -1)
          run_start = c;
        length++;
      } else {
        if (length > max_len) {
          apply_slice(r, run_start, length, true);
          changed = true;
        }
        length = 0;
        run_start = -1;
      }
    }
    if (length > max_len) {
      apply_slice(r, run_start, length, true);
      changed = true;
    }
  }

  // Vertical
  for (int c = 1; c < width - 1; c++) {
    int length = 0;
    int run_start = -1;
    for (int r = 1; r < height; r++) {
      if (grid[r][c].type == CellType::WHITE) {
        if (run_start == -1)
          run_start = r;
        length++;
      } else {
        if (length > max_len) {
          apply_slice(c, run_start, length, false);
          changed = true;
        }
        length = 0;
        run_start = -1;
      }
    }
    if (length > max_len) {
      apply_slice(c, run_start, length, false);
      changed = true;
    }
  }
#if KAKURO_ENABLE_LOGGING
  if (changed) {
    logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                     GenerationLogger::SUBSTAGE_SLICE_RUNS, "Sliced long runs",
                     get_grid_state());
  }
#endif
  return changed;
}

bool KakuroBoard::slice_soft_runs(int soft_len, double prob) {
  bool changed = false;
  std::uniform_real_distribution<> dist(0.0, 1.0);

  // Horizontal
  for (int r = 1; r < height - 1; r++) {
    int length = 0;
    int run_start = -1;
    for (int c = 1; c < width; c++) {
      if (grid[r][c].type == CellType::WHITE) {
        if (run_start == -1)
          run_start = c;
        length++;
      } else {
        if (length > soft_len && dist(rng) < prob) {
          apply_slice(r, run_start, length, true);
          changed = true;
        }
        length = 0;
        run_start = -1;
      }
    }
    if (length > soft_len && dist(rng) < prob) {
      apply_slice(r, run_start, length, true);
      changed = true;
    }
  }

  // Vertical
  for (int c = 1; c < width - 1; c++) {
    int length = 0;
    int run_start = -1;
    for (int r = 1; r < height; r++) {
      if (grid[r][c].type == CellType::WHITE) {
        if (run_start == -1)
          run_start = r;
        length++;
      } else {
        if (length > soft_len && dist(rng) < prob) {
          apply_slice(c, run_start, length, false);
          changed = true;
        }
        length = 0;
        run_start = -1;
      }
    }
    if (length > soft_len && dist(rng) < prob) {
      apply_slice(c, run_start, length, false);
      changed = true;
    }
  }

#if KAKURO_ENABLE_LOGGING
  if (changed) {
    logger->log_step(
        GenerationLogger::STAGE_TOPOLOGY, GenerationLogger::SUBSTAGE_SLICE_RUNS,
        "Sliced soft runs (len > " + std::to_string(soft_len) + ")",
        get_grid_state());
  }
#endif
  return changed;
}

void KakuroBoard::apply_slice(int fixed_idx, int start, int length,
                              bool is_horz) {
  int mid_offset = length / 2;
  int r = is_horz ? fixed_idx : start + mid_offset;
  int c = is_horz ? start + mid_offset : fixed_idx;
  set_block(r, c);
  set_block(height - 1 - r, width - 1 - c);
}

std::vector<std::vector<std::pair<int, int>>> KakuroBoard::find_components() {
  collect_white_cells();
  std::vector<std::vector<std::pair<int, int>>> components;
  std::unordered_set<std::pair<int, int>, PairHash> visited;

  for (Cell *start_node : white_cells) {
    if (visited.count({start_node->r, start_node->c}))
      continue;

    std::vector<std::pair<int, int>> comp;
    std::queue<Cell *> q;
    q.push(start_node);
    visited.insert({start_node->r, start_node->c});

    while (!q.empty()) {
      Cell *curr = q.front();
      q.pop();
      comp.push_back({curr->r, curr->c});

      int dr[] = {0, 0, 1, -1};
      int dc[] = {1, -1, 0, 0};
      for (int i = 0; i < 4; i++) {
        Cell *n = get_cell(curr->r + dr[i], curr->c + dc[i]);
        if (n && n->type == CellType::WHITE && !visited.count({n->r, n->c})) {
          visited.insert({n->r, n->c});
          q.push(n);
        }
      }
    }
    components.push_back(comp);
  }
  return components;
}

bool KakuroBoard::try_remove_and_reconnect(int r, int c) {
  // 1. Store state for potential revert
  Cell *target = get_cell(r, c);
  if (!target || target->type != CellType::WHITE)
    return false;

  reset_values();

  // 3. Snapshot types for potential revert
  std::vector<std::vector<CellType>> backup(height,
                                            std::vector<CellType>(width));
  for (int i = 0; i < height; i++) {
    for (int j = 0; j < width; j++) {
      backup[i][j] = grid[i][j].type;
    }
  }

  int sym_r = height - 1 - r;
  int sym_c = width - 1 - c;
  Cell *sym_target = get_cell(sym_r, sym_c);

  // 2. Perform removal
  target->type = CellType::BLOCK;
  sym_target->type = CellType::BLOCK;

  auto components = find_components();

  // 3. If still connected or empty, we are done
  if (components.size() <= 1) {
#if KAKURO_ENABLE_LOGGING
    logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                     GenerationLogger::SUBSTAGE_PRUNE_SINGLES,
                     "Removed single cells without disconnecting",
                     get_grid_state());

#endif
    collect_white_cells();
    identify_sectors();
    return true;
  }

  // 4. Broken connectivity: Try to Reconnect elsewhere
  // Find potential bridge cells (BLOCK cells that touch at least 2 different
  // components)
  std::vector<std::pair<int, int>> bridge_candidates;

  for (int i = 1; i < height - 1; i++) {
    for (int j = 1; j < width - 1; j++) {
      if (grid[i][j].type == CellType::BLOCK) {
        // Don't use the cell we just removed or its symmetry
        if ((i == r && j == c) || (i == sym_r && j == sym_c))
          continue;

        std::unordered_set<int> touching_components;
        int dr[] = {0, 0, 1, -1};
        int dc[] = {1, -1, 0, 0};
        for (int k = 0; k < 4; k++) {
          int ni = i + dr[k], nj = j + dc[k];
          for (size_t comp_idx = 0; comp_idx < components.size(); comp_idx++) {
            for (auto &p : components[comp_idx]) {
              if (p.first == ni && p.second == nj) {
                touching_components.insert(comp_idx);
                break;
              }
            }
          }
        }

        if (touching_components.size() >= 2) {
          bridge_candidates.push_back({i, j});
        }
      }
    }
  }

  if (!bridge_candidates.empty()) {
    // Pick a random bridge
    std::uniform_int_distribution<> dist(0, (int)bridge_candidates.size() - 1);
    auto bridge = bridge_candidates[dist(rng)];

    set_white(bridge.first, bridge.second);
    set_white(height - 1 - bridge.first, width - 1 - bridge.second);

    // Final connectivity check
    if (check_connectivity())
#if KAKURO_ENABLE_LOGGING
      logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                       GenerationLogger::SUBSTAGE_PRUNE_SINGLES,
                       "Removed single cells with fixing disconnection",
                       get_grid_state());

#endif
    collect_white_cells();
    identify_sectors();

    return true;
  }

  for (int i = 0; i < height; i++) {
    for (int j = 0; j < width; j++)
      grid[i][j].type = backup[i][j];
  }
  collect_white_cells();
  identify_sectors();
  return false;
}

bool KakuroBoard::prune_singles() {
  bool any_change = false;
  bool changed = true;
  int limit = 10;

  while (changed && --limit > 0) {
    changed = false;
    collect_white_cells();

    for (size_t i = 0; i < white_cells.size(); i++) {
      Cell *c = white_cells[i];
      int h_nbs = 0;
      if (get_cell(c->r, c->c - 1)->type == CellType::WHITE)
        h_nbs++;
      if (get_cell(c->r, c->c + 1)->type == CellType::WHITE)
        h_nbs++;
      int v_nbs = 0;
      if (get_cell(c->r - 1, c->c)->type == CellType::WHITE)
        v_nbs++;
      if (get_cell(c->r + 1, c->c)->type == CellType::WHITE)
        v_nbs++;

      if (h_nbs == 0 || v_nbs == 0) {
        if (try_remove_and_reconnect(c->r, c->c)) {
          changed = true;
          any_change = true;
          collect_white_cells(); // List changed
          break;
        }
      }
    }
  }
  return any_change;
}

bool KakuroBoard::break_single_runs() {
  bool changed = true;
  bool any_change = false;
  while (changed) {
    changed = false;
    for (int r = 1; r < height - 1; r++) {
      for (int c = 1; c < width - 1; c++) {
        if (grid[r][c].type == CellType::WHITE) {
          // Count horizontal run length (including this cell)
          int h_len = 1;
          // Look left
          int check_c = c - 1;
          while (check_c >= 0 && grid[r][check_c].type == CellType::WHITE) {
            h_len++;
            check_c--;
          }
          // Look right
          check_c = c + 1;
          while (check_c < width && grid[r][check_c].type == CellType::WHITE) {
            h_len++;
            check_c++;
          }

          // Count vertical run length (including this cell)
          int v_len = 1;
          // Look up
          int check_r = r - 1;
          while (check_r >= 0 && grid[check_r][c].type == CellType::WHITE) {
            v_len++;
            check_r--;
          }
          // Look down
          check_r = r + 1;
          while (check_r < height && grid[check_r][c].type == CellType::WHITE) {
            v_len++;
            check_r++;
          }

          // If this cell is part of a length-1 run in EITHER direction, remove
          // it
          if (h_len == 1 || v_len == 1) {
            set_block(r, c);
            set_block(height - 1 - r, width - 1 - c);
            changed = true;
            any_change = true;
          }
        }
      }
    }
  }
  if (any_change) {
    collect_white_cells();
    identify_sectors();
#if KAKURO_ENABLE_LOGGING
    logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                     GenerationLogger::SUBSTAGE_BREAK_SINGLE_RUNS,
                     "Broke single-cell runs", get_grid_state());
#endif
  }
  return any_change;
}
bool KakuroBoard::validate_clue_headers() {
  for (int r = 0; r < height; r++) {
    for (int c = 0; c < width; c++) {
      if (grid[r][c].type == CellType::WHITE) {
        // Horizontal: If first in row or cell to left is NOT white, it must be
        // a block
        if (c == 0 || grid[r][c - 1].type != CellType::WHITE) {
          if (c == 0 || grid[r][c - 1].type != CellType::BLOCK)
            return false;
        }
        // Vertical: If first in col or cell above is NOT white, it must be a
        // block
        if (r == 0 || grid[r - 1][c].type != CellType::WHITE) {
          if (r == 0 || grid[r - 1][c].type != CellType::BLOCK)
            return false;
        }
      }
    }
  }
  return true;
}

bool KakuroBoard::check_connectivity() {
  collect_white_cells();
  if (white_cells.empty())
    return false;

  std::unordered_set<std::pair<int, int>, PairHash> visited;
  std::queue<Cell *> q;

  q.push(white_cells[0]);
  visited.insert({white_cells[0]->r, white_cells[0]->c});

  int count = 0;
  while (!q.empty()) {
    Cell *curr = q.front();
    q.pop();
    count++;

    int dr[] = {0, 0, 1, -1};
    int dc[] = {1, -1, 0, 0};

    for (int i = 0; i < 4; i++) {
      Cell *n = get_cell(curr->r + dr[i], curr->c + dc[i]);
      if (n && n->type == CellType::WHITE) {
        if (visited.find({n->r, n->c}) == visited.end()) {
          visited.insert({n->r, n->c});
          q.push(n);
        }
      }
    }
  }
  return count == (int)white_cells.size();
}

int KakuroBoard::count_white_neighbors(Cell *cell) {
  int n = 0;
  int dr[] = {0, 0, 1, -1};
  int dc[] = {1, -1, 0, 0};
  for (int i = 0; i < 4; ++i) {
    Cell *neighbor = get_cell(cell->r + dr[i], cell->c + dc[i]);
    if (neighbor && neighbor->type == CellType::WHITE)
      n++;
  }
  return n;
}

bool KakuroBoard::break_large_patches(int size) {
  bool changed_overall = false;
  // Standard Kakuro usually treats 0 and width-1 as borders.
  // We want to avoid creating 1-cell wide corridors at indices 1 and width-2.

  for (int iteration = 0; iteration < 50; iteration++) {
    bool found = false;

    for (int r = 1; r <= height - size && !found; r++) {
      for (int c = 1; c <= width - size && !found; c++) {

        // 1. Identify a large patch of WHITE cells
        bool is_patch = true;
        std::vector<Cell *> patch_cells;

        for (int ir = 0; ir < size && is_patch; ir++) {
          for (int ic = 0; ic < size && is_patch; ic++) {
            // Boundary safety check
            if (r + ir >= height || c + ic >= width) {
              is_patch = false;
              continue;
            }

            Cell *cell = &grid[r + ir][c + ic];
            patch_cells.push_back(cell);
            if (cell->type != CellType::WHITE) {
              is_patch = false;
            }
          }
        }

        if (is_patch && !patch_cells.empty()) {
          found = true;

          std::vector<Cell *> safe_candidates;
          std::vector<Cell *> priority_candidates;

          // 2. Filter candidates to prevent edge artifacts
          for (Cell *cell : patch_cells) {
            int cr = cell->r;
            int cc = cell->c;

            // Check if placing a block here creates a 1-wide gap at the edge
            bool creates_gap = false;

            // Top Edge: If at row 2, and row 1 is white -> Gap
            if (cr == 2 && grid[1][cc].type == CellType::WHITE)
              creates_gap = true;
            // Left Edge
            if (cc == 2 && grid[cr][1].type == CellType::WHITE)
              creates_gap = true;
            // Bottom Edge
            if (cr == height - 3 &&
                grid[height - 2][cc].type == CellType::WHITE)
              creates_gap = true;
            // Right Edge
            if (cc == width - 3 && grid[cr][width - 2].type == CellType::WHITE)
              creates_gap = true;

            // Check Symmetric counterpart for the same issues (Board must stay
            // symmetric)
            int sym_r = height - 1 - cr;
            int sym_c = width - 1 - cc;

            if (sym_r == 2 && grid[1][sym_c].type == CellType::WHITE)
              creates_gap = true;
            if (sym_c == 2 && grid[sym_r][1].type == CellType::WHITE)
              creates_gap = true;
            if (sym_r == height - 3 &&
                grid[height - 2][sym_c].type == CellType::WHITE)
              creates_gap = true;
            if (sym_c == width - 3 &&
                grid[sym_r][width - 2].type == CellType::WHITE)
              creates_gap = true;

            if (!creates_gap) {
              safe_candidates.push_back(cell);
            }
          }

          // 3. Find candidates that touch existing blocks (Connectivity
          // preference) We only look within 'safe_candidates' first.
          auto &source_list =
              safe_candidates.empty() ? patch_cells : safe_candidates;

          for (Cell *cell : source_list) {
            bool has_block_neighbor = false;
            std::vector<std::pair<int, int>> dirs = {
                {0, 1}, {0, -1}, {1, 0}, {-1, 0}};

            for (auto [dr, dc] : dirs) {
              Cell *n = get_cell(cell->r + dr, cell->c + dc);
              if (n && n->type == CellType::BLOCK) {
                has_block_neighbor = true;
                break;
              }
            }
            if (has_block_neighbor) {
              priority_candidates.push_back(cell);
            }
          }

          // 4. Select Target
          Cell *target = nullptr;

          if (!priority_candidates.empty()) {
            std::uniform_int_distribution<> dist(
                0, (int)priority_candidates.size() - 1);
            target = priority_candidates[dist(rng)];
          } else if (!safe_candidates.empty()) {
            std::uniform_int_distribution<> dist(
                0, (int)safe_candidates.size() - 1);
            target = safe_candidates[dist(rng)];
          } else {
            // Fallback: If absolutely necessary, pick any cell to break the
            // loop, preferably the center of the patch to minimize edge damage.
            target = patch_cells[patch_cells.size() / 2];
          }

          // 5. Apply Block and Symmetry
          if (target) {
            set_block(target->r, target->c);
            set_block(height - 1 - target->r, width - 1 - target->c);
            changed_overall = true;
          }
        }
      }
    }

    if (!found)
      break;
  }
#if KAKURO_ENABLE_LOGGING
  if (changed_overall) {
    logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                     GenerationLogger::SUBSTAGE_BREAK_PATCHES,
                     "Broke large patches", get_grid_state());
  }
#endif
  return changed_overall;
}

bool KakuroBoard::stabilize_grid(bool gentle) {
  bool changed = true;
  bool any_change = false;
  int iterations = 0;
  const int max_loops = 15;
  while (changed && iterations < max_loops) {
    changed = false;
    if (gentle) {
      if (fix_invalid_runs_gentle())
        changed = true;
    } else {
      if (fix_invalid_runs())
        changed = true;
    }
    if (prune_singles())
      changed = true;
    if (break_single_runs())
      changed = true;
    if (ensure_connectivity())
      changed = true;
    any_change |= changed;
    iterations++;
  }
#if KAKURO_ENABLE_LOGGING
  logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                   GenerationLogger::SUBSTAGE_STABILIZE_GRID,
                   "Grid stabilized after " + std::to_string(iterations) +
                       " iterations",
                   get_grid_state());
#endif
  collect_white_cells();
  identify_sectors();
  return any_change;
}

bool KakuroBoard::fix_invalid_runs() {
  bool changed = false;

  // Horizontal
  for (int r = 0; r < height; r++) {
    int c = 0;
    while (c < width) {
      if (grid[r][c].type == CellType::WHITE) {
        int start = c;
        int length = 0;
        while (c < width && grid[r][c].type == CellType::WHITE) {
          length++;
          c++;
        }

        if (length == 1) {
          set_block(r, start);
          set_block(height - 1 - r, width - 1 - start);
          changed = true;
        } else if (length > 9) {
          int mid = start + length / 2;
          set_block(r, mid);
          set_block(height - 1 - r, width - 1 - mid);
          changed = true;
        }
      } else {
        c++;
      }
    }
  }

  // Vertical
  for (int c = 0; c < width; c++) {
    int r = 0;
    while (r < height) {
      if (grid[r][c].type == CellType::WHITE) {
        int start = r;
        int length = 0;
        while (r < height && grid[r][c].type == CellType::WHITE) {
          length++;
          r++;
        }

        if (length == 1) {
          set_block(start, c);
          set_block(height - 1 - start, width - 1 - c);
          changed = true;
        } else if (length > 9) {
          int mid = start + length / 2;
          set_block(mid, c);
          set_block(height - 1 - mid, width - 1 - c);
          changed = true;
        }
      } else {
        r++;
      }
    }
  }

  if (changed && KAKURO_ENABLE_LOGGING) {
    logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                     GenerationLogger::SUBSTAGE_FIX_INVALID_RUNS,
                     "Fixed invalid runs (too short/long)", get_grid_state());
  }
  return changed;
}

bool KakuroBoard::fix_invalid_runs_gentle() {
  bool changed = false;
  for (int r = 0; r < height; r++) {
    for (int c = 0; c < width; c++) {
      if (grid[r][c].type != CellType::WHITE)
        continue;
      bool h_nb = (c > 0 && grid[r][c - 1].type == CellType::WHITE) ||
                  (c < width - 1 && grid[r][c + 1].type == CellType::WHITE);
      bool v_nb = (r > 0 && grid[r - 1][c].type == CellType::WHITE) ||
                  (r < height - 1 && grid[r + 1][c].type == CellType::WHITE);
      if (!h_nb && !v_nb) {
        set_block(r, c);
        set_block(height - 1 - r, width - 1 - c);
        changed = true;
      }
    }
  }
  // Also split long runs
  if (fix_invalid_runs())
    changed = true; // reusing existing logic for long splits
  return changed;
}

void KakuroBoard::block_sym(Cell *cell) {
  set_block(cell->r, cell->c);
  set_block(height - 1 - cell->r, width - 1 - cell->c);
}

bool KakuroBoard::ensure_connectivity() {
  collect_white_cells();
  if (white_cells.empty())
    return false;
  std::unordered_set<std::pair<int, int>, PairHash> white_set;
  for (auto c : white_cells)
    white_set.insert({c->r, c->c});

  std::vector<std::vector<std::pair<int, int>>> components;
  std::unordered_set<std::pair<int, int>, PairHash> visited;

  for (auto c : white_cells) {
    if (visited.count({c->r, c->c}))
      continue;
    std::vector<std::pair<int, int>> comp;
    std::queue<std::pair<int, int>> q;
    q.push({c->r, c->c});
    visited.insert({c->r, c->c});
    while (!q.empty()) {
      auto [r, col] = q.front();
      q.pop();
      comp.push_back({r, col});
      int dr[] = {0, 0, 1, -1};
      int dc[] = {1, -1, 0, 0};
      for (int i = 0; i < 4; i++) {
        std::pair<int, int> next = {r + dr[i], col + dc[i]};
        if (white_set.count(next) && !visited.count(next)) {
          visited.insert(next);
          q.push(next);
        }
      }
    }
    components.push_back(comp);
  }
  if (components.empty())
    return false;

  auto largest = *std::max_element(components.begin(), components.end(),
                                   [](const auto &a, const auto &b) {
                                     return (int)a.size() < (int)b.size();
                                   });
  std::unordered_set<std::pair<int, int>, PairHash> largest_set(largest.begin(),
                                                                largest.end());

  bool changed = false;
  int filled_count = 0;
  for (auto c : white_cells) {
    if (!largest_set.count({c->r, c->c})) {
      set_block(c->r, c->c);
      set_block(height - 1 - c->r, width - 1 - c->c);
      changed = true;
      filled_count++;
    }
  }

#if KAKURO_ENABLE_LOGGING
  if (filled_count > 0) {
    logger->log_step(GenerationLogger::STAGE_TOPOLOGY,
                     GenerationLogger::SUBSTAGE_CONNECTIVITY_CHECK,
                     "Removed disconnected components (" +
                         std::to_string(filled_count) + " cells)",
                     get_grid_state());
  }
#endif
  return changed;
}

void KakuroBoard::collect_white_cells() {
  white_cells.clear();
  for (int r = 0; r < height; r++) {
    for (int c = 0; c < width; c++) {
      if (grid[r][c].type == CellType::WHITE) {
        white_cells.push_back(&grid[r][c]);
      }
    }
  }
}

void KakuroBoard::identify_sectors() {
  // Clear existing shared_ptr lists
  sectors_h.clear();
  sectors_v.clear();
  for (auto c : white_cells) {
    c->sector_h = nullptr;
    c->sector_v = nullptr;
  }

  // Horizontal
  for (int r = 0; r < height; r++) {
    auto current_sec = std::make_shared<std::vector<Cell *>>();
    for (int c = 0; c < width; c++) {
      if (grid[r][c].type == CellType::WHITE) {
        current_sec->push_back(&grid[r][c]);
      } else {
        if (!current_sec->empty()) {
          sectors_h.push_back(current_sec);
          for (auto sc : *current_sec)
            sc->sector_h = current_sec;
          current_sec = std::make_shared<std::vector<Cell *>>();
        }
      }
    }
    if (!current_sec->empty()) {
      sectors_h.push_back(current_sec);
      for (auto sc : *current_sec)
        sc->sector_h = current_sec;
    }
  }

  // Vertical (Same logic for sectors_v...)
  for (int c = 0; c < width; c++) {
    auto current_sec = std::make_shared<std::vector<Cell *>>();
    for (int r = 0; r < height; r++) {
      if (grid[r][c].type == CellType::WHITE) {
        current_sec->push_back(&grid[r][c]);
      } else {
        if (!current_sec->empty()) {
          sectors_v.push_back(current_sec);
          for (auto sc : *current_sec)
            sc->sector_v = current_sec;
          current_sec = std::make_shared<std::vector<Cell *>>();
        }
      }
    }
    if (!current_sec->empty()) {
      sectors_v.push_back(current_sec);
      for (auto sc : *current_sec)
        sc->sector_v = current_sec;
    }
  }
}

std::vector<std::vector<std::unordered_map<std::string, std::string>>>
KakuroBoard::to_dict() const {
  std::vector<std::vector<std::unordered_map<std::string, std::string>>> result;
  for (int r = 0; r < height; r++) {
    std::vector<std::unordered_map<std::string, std::string>> row;
    for (int c = 0; c < width; c++) {
      const Cell &cell = grid[r][c];
      std::unordered_map<std::string, std::string> d;
      d["r"] = std::to_string(cell.r);
      d["c"] = std::to_string(cell.c);
      d["type"] = (cell.type == CellType::BLOCK) ? "BLOCK" : "WHITE";
      if (cell.value)
        d["value"] = std::to_string(*cell.value);
      if (cell.clue_h)
        d["clue_h"] = std::to_string(*cell.clue_h);
      if (cell.clue_v)
        d["clue_v"] = std::to_string(*cell.clue_v);
      row.push_back(d);
    }
    result.push_back(row);
  }
  return result;
}

} // namespace kakuro