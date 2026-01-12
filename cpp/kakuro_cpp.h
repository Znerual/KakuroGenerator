#ifndef KAKURO_CPP_H
#define KAKURO_CPP_H

#include <algorithm>
#include <bitset>
#include <chrono>
#include <cmath>
#include <deque>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <random>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace kakuro {

// ============================================================================
// LOGGING CONFIGURATION
// Set to 1 to enable detailed generation logging, 0 to disable
// ============================================================================
#define KAKURO_ENABLE_LOGGING 1

#define LOG_DEBUG(msg)                                                         \
  do {                                                                         \
  } while (0) // { if (KAKURO_ENABLE_LOGGING) { std::cerr << "[DEBUG] " << msg
              // << std::endl; } } while (0)
#define LOG_INFO(msg)                                                          \
  do {                                                                         \
  } while (0) // { if (KAKURO_ENABLE_LOGGING) { std::cerr << "[INFO] " << msg <<
              // std::endl; } } while (0)
#define LOG_ERROR(msg)                                                         \
  do {                                                                         \
  } while (0) // { std::cerr << "[ERROR] " << msg << std::endl; }

// ============================================================================
// GENERATION LOGGER - Structured JSON logging for visualization
// ============================================================================

struct TopologyParams {
  std::string difficulty = "medium";
  std::optional<double> density;
  std::optional<int> max_sector_length;
  std::optional<int> num_stamps;
  std::optional<float> min_cells;
  std::optional<int> max_run_len;
  std::optional<int> max_run_len_soft;
  std::optional<double> max_run_len_soft_prob;
  std::optional<int> max_patch_size;
  std::optional<bool> island_mode;
  std::optional<std::vector<std::pair<int, int>>> stamps;
};

struct FillParams {
  std::string difficulty = "medium";
  std::optional<std::vector<int>> weights;
  std::optional<std::string> partition_preference;
  std::optional<int> max_nodes;
};

enum class TechniqueTier {
  VERY_EASY = 1, // Intersection of two masks, naked singles
  EASY = 2,      // Simple partitions (only 1 valid combination)
  MEDIUM = 3,    // Hidden singles, basic constraint propagation
  HARD = 4,      // Complex intersections, multi-sector lookahead
  EXTREME = 5    // Trial and Error / Bifurcation
};

struct SolveStep {
  std::string technique;
  float difficulty_weight;
  int cells_affected;
  SolveStep(std::string t, float w, int c)
      : technique(t), difficulty_weight(w), cells_affected(c) {}
};

struct DifficultyResult {
  float score = 0;    // Factor 2: Persistence (Sum of effort)
  std::string rating; // Factor 1: Capability (Hardest technique)
  TechniqueTier max_tier = TechniqueTier::VERY_EASY;

  int total_steps = 0;
  int solution_count = 0;
  std::string uniqueness;
  std::vector<SolveStep> solve_path;
  std::vector<std::vector<std::vector<std::optional<int>>>> solutions;
};

class GenerationLogger {
public:
  // Stages (Aliases for efficiency)
  static constexpr const char *STAGE_TOPOLOGY = "tc";   // topology_creation
  static constexpr const char *STAGE_FILLING = "f";     // filling
  static constexpr const char *STAGE_UNIQUENESS = "uv"; // uniqueness_validation
  static constexpr const char *STAGE_DIFFICULTY = "de"; // difficulty_estimation
  static constexpr const char *STAGE_PROFILE = "p";     // profile

  // Substages - Topology
  static constexpr const char *SUBSTAGE_START = "s"; // start
  static constexpr const char *SUBSTAGE_STAMP_PLACEMENT =
      "sp"; // stamp_placement
  static constexpr const char *SUBSTAGE_LATTICE_GROWTH = "lg"; // lattice_growth
  static constexpr const char *SUBSTAGE_PATCH_BREAKING = "pb"; // patch_breaking
  static constexpr const char *SUBSTAGE_VALIDATION_FAILED =
      "vf"; // validation_failed
  static constexpr const char *SUBSTAGE_CONNECTIVITY_CHECK =
      "cc";                                             // connectivity_check
  static constexpr const char *SUBSTAGE_COMPLETE = "c"; // complete
  static constexpr const char *SUBSTAGE_FAILED = "f";   // failed

  // Substages - Topology Extended
  static constexpr const char *SUBSTAGE_SEED_PLACEMENT =
      "sep";                                                  // seed_placement
  static constexpr const char *SUBSTAGE_SLICE_RUNS = "sr";    // slice_runs
  static constexpr const char *SUBSTAGE_BREAK_PATCHES = "bp"; // break_patches
  static constexpr const char *SUBSTAGE_PRUNE_SINGLES = "ps"; // prune_singles
  static constexpr const char *SUBSTAGE_BREAK_SINGLE_RUNS =
      "bsr"; // break_single_runs
  static constexpr const char *SUBSTAGE_STABILIZE_GRID = "sg"; // stabilize_grid
  static constexpr const char *SUBSTAGE_FIX_INVALID_RUNS =
      "fir"; // fix_invalid_runs

  // Substages - Filling
  static constexpr const char *SUBSTAGE_NUMBER_PLACEMENT =
      "np";                                               // number_placement
  static constexpr const char *SUBSTAGE_BACKTRACK = "bt"; // backtrack
  static constexpr const char *SUBSTAGE_CONSISTENCY_FAILED =
      "cf"; // consistency_check_failed

  // Substages - Uniqueness
  static constexpr const char *SUBSTAGE_ALTERNATIVE_FOUND =
      "af"; // alternative_found
  static constexpr const char *SUBSTAGE_REPAIR_ATTEMPT = "ra"; // repair_attempt

  // Substages - Difficulty
  static constexpr const char *SUBSTAGE_LOGIC_STEP = "ls"; // logic_step
  static constexpr const char *SUBSTAGE_TIMING = "tm";     // timing

private:
  std::ofstream log_file_;
  std::ofstream prof_file_;
  int step_id_ = 0;
  bool enabled_ = false;
  std::string current_kakuro_id_;
  std::chrono::steady_clock::time_point last_step_time_;

  static std::string escape_json(const std::string &s) {
    std::ostringstream oss;
    for (char c : s) {
      if (c == '"')
        oss << "\\\"";
      else if (c == '\\')
        oss << "\\\\";
      else if (c == '\n')
        oss << "\\n";
      else if (c == '\r')
        oss << "\\r";
      else if (c == '\t')
        oss << "\\t";
      else
        oss << c;
    }
    return oss.str();
  }

public:
  GenerationLogger() = default;

  ~GenerationLogger() { close(); }

  bool is_enabled() const { return enabled_; }

  void start_new_kakuro(const std::string &log_dir = "kakuro_logs") {
#if KAKURO_ENABLE_LOGGING
    if (log_file_.is_open())
      return; // Continue in the same file if already open

    std::error_code ec;
    std::filesystem::create_directories(log_dir, ec);
    if (ec) {
      LOG_ERROR("Failed to create log directory: " + ec.message());
      return;
    }
    auto now = std::chrono::system_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                  now.time_since_epoch())
                  .count();
    current_kakuro_id_ = "kakuro_" + std::to_string(ms);

    std::string filepath = log_dir + "/" + current_kakuro_id_ + ".jsonl";
    std::string prof_filepath = log_dir + "/_" + current_kakuro_id_ + ".jsonl";
    log_file_.open(filepath);
    prof_file_.open(prof_filepath);

    if (log_file_.is_open() && prof_file_.is_open()) {
      enabled_ = true;
      step_id_ = 0;
      last_step_time_ = std::chrono::steady_clock::now();
      // JSONL: No opening bracket
    }
#endif
  }

  void close() {
    if (log_file_.is_open()) {
      log_file_.flush();
      log_file_.close();
    }
    if (prof_file_.is_open()) {
      prof_file_.flush();
      prof_file_.close();
    }
    enabled_ = false;
  }

  std::string get_kakuro_id() const { return current_kakuro_id_; }

  void log_step(
      const std::string &stage, const std::string &substage,
      const std::string &message,
      const std::vector<std::vector<std::pair<std::string, int>>> &grid_state,
      const std::string &extra_data = "") {
#if KAKURO_ENABLE_LOGGING
    if (!enabled_ || !log_file_.is_open())
      return;

    auto now = std::chrono::steady_clock::now();
    double duration_ms = std::chrono::duration<double, std::milli>(now - last_step_time_).count();
    last_step_time_ = now;

    // JSONL: Each entry is a single-line JSON object
    log_file_ << "{\"id\":" << step_id_++
              << ",\"dur\":" << std::fixed << std::setprecision(2) << duration_ms
              << ",\"s\":\"" << stage << "\""
              << ",\"ss\":\"" << substage << "\""
              << ",\"m\":\"" << escape_json(message) << "\"";

    if (!grid_state.empty()) {
      log_file_ << ",\"wh\":[" << grid_state[0].size() << "," << grid_state.size() << "]"
                << ",\"g\":[";
      bool first_cell = true;
      for (size_t r = 0; r < grid_state.size(); r++) {
        for (size_t c = 0; c < grid_state[r].size(); c++) {
          const auto &[type, value] = grid_state[r][c];
          if (type == "WHITE") {
            if (!first_cell) log_file_ << ",";
            log_file_ << "[" << r << "," << c << "," << value << "]";
            first_cell = false;
          }
        }
      }
      log_file_ << "]";
    } else {
      log_file_ << ",\"g\":[]";
    }

    if (!extra_data.empty()) {
      log_file_ << ",\"d\":" << extra_data;
    }
    log_file_ << "}\n"; // End of line for JSONL
    log_file_.flush();
#endif
  }

  void log_step_with_highlights(
      const std::string &stage, const std::string &substage,
      const std::string &message,
      const std::vector<std::vector<std::pair<std::string, int>>> &grid_state,
      const std::vector<std::pair<int, int>> &highlighted_cells,
      const std::vector<std::vector<std::pair<std::string, int>>> &alt_grid =
          {}) {
#if KAKURO_ENABLE_LOGGING
    if (!enabled_ || !log_file_.is_open())
      return;

    std::ostringstream data;
    data << "{\"hc\": ["; // highlighted_cells
    for (size_t i = 0; i < highlighted_cells.size(); i++) {
      data << "[" << highlighted_cells[i].first << ","
           << highlighted_cells[i].second << "]";
      if (i < highlighted_cells.size() - 1)
        data << ",";
    }
    data << "]";

    // Serialize Alternative Grid if present
    if (!alt_grid.empty()) {
      data << ", \"ag\": ["; // alternative_grid
      bool first_val = true;
      for (size_t r = 0; r < alt_grid.size(); r++) {
        for (size_t c = 0; c < alt_grid[r].size(); c++) {
          const auto &[type, value] = alt_grid[r][c];
          // We only log WHITE cells to save space, matching the main grid
          // format
          if (type == "WHITE") {
            if (!first_val)
              data << ",";
            data << "[" << r << "," << c << "," << value << "]";
            first_val = false;
          }
        }
      }
      data << "]";
    }
    data << "}";

    log_step(stage, substage, message, grid_state, data.str());
#endif
  }

  void log_params(const FillParams &fill_p, const TopologyParams &topo_p) {
#if KAKURO_ENABLE_LOGGING
    if (!enabled_ || !log_file_.is_open())
      return;

    log_file_ << "{\"id\":" << step_id_++ << ",\"s\":\"params\",\"ss\":\"init\",\"m\":\"Generation Parameters\"";

    // Serialize FillParams
    log_file_ << ",\"fill\":{";
    log_file_ << "\"difficulty\":\"" << fill_p.difficulty << "\"";
    if (fill_p.max_nodes)
      log_file_ << ",\"max_nodes\":" << *fill_p.max_nodes;
    if (fill_p.partition_preference)
      log_file_ << ",\"partition_preference\":\"" << *fill_p.partition_preference << "\"";
    if (fill_p.weights) {
      log_file_ << ",\"weights\":[";
      for (size_t i = 0; i < fill_p.weights->size(); ++i) {
        log_file_ << (*fill_p.weights)[i] << (i < fill_p.weights->size() - 1 ? "," : "");
      }
      log_file_ << "]";
    }
    log_file_ << "}";

    // Serialize TopologyParams
    log_file_ << ",\"topo\":{";
    log_file_ << "\"difficulty\":\"" << topo_p.difficulty << "\"";
    if (topo_p.density) log_file_ << ",\"density\":" << *topo_p.density;
    if (topo_p.max_sector_length) log_file_ << ",\"max_sector_length\":" << *topo_p.max_sector_length;
    if (topo_p.num_stamps) log_file_ << ",\"num_stamps\":" << *topo_p.num_stamps;
    if (topo_p.min_cells) log_file_ << ",\"min_cells\":" << *topo_p.min_cells;
    if (topo_p.max_run_len) log_file_ << ",\"max_run_len\":" << *topo_p.max_run_len;
    if (topo_p.max_run_len_soft) log_file_ << ",\"max_run_len_soft\":" << *topo_p.max_run_len_soft;
    if (topo_p.max_run_len_soft_prob) log_file_ << ",\"max_run_len_soft_prob\":" << *topo_p.max_run_len_soft_prob;
    if (topo_p.max_patch_size) log_file_ << ",\"max_patch_size\":" << *topo_p.max_patch_size;
    if (topo_p.island_mode) log_file_ << ",\"island_mode\":" << (*topo_p.island_mode ? "true" : "false");
    if (topo_p.stamps) {
      log_file_ << ",\"stamps\":[";
      for (size_t i = 0; i < topo_p.stamps->size(); ++i) {
        log_file_ << "[" << (*topo_p.stamps)[i].first << "," << (*topo_p.stamps)[i].second << "]"
                  << (i < topo_p.stamps->size() - 1 ? "," : "");
      }
      log_file_ << "]";
    }
    log_file_ << "}}\n"; // Close object and end line
    log_file_.flush();
#endif
  }

  void log_difficulty(
      const DifficultyResult &diff,
      const std::vector<std::vector<std::pair<std::string, int>>> &grid_state) {
#if KAKURO_ENABLE_LOGGING
    if (!enabled_ || !log_file_.is_open())
      return;

    log_file_ << "{\"id\":" << step_id_++ 
              << ",\"s\":\"" << STAGE_DIFFICULTY << "\""
              << ",\"ss\":\"" << SUBSTAGE_COMPLETE << "\""
              << ",\"m\":\"Difficulty estimation complete: " << escape_json(diff.rating) << "\""
              << ",\"difficulty\":{"
              << "\"rating\":\"" << escape_json(diff.rating) << "\""
              << ",\"score\":" << diff.score
              << ",\"max_tier\":" << (int)diff.max_tier
              << ",\"solution_count\":" << diff.solution_count
              << ",\"uniqueness\":\"" << escape_json(diff.uniqueness) << "\"}";

    if (!grid_state.empty()) {
      log_file_ << ",\"wh\":[" << grid_state[0].size() << "," << grid_state.size() << "]"
                << ",\"g\":[";
      bool first_cell = true;
      for (size_t r = 0; r < grid_state.size(); r++) {
        for (size_t c = 0; c < grid_state[r].size(); c++) {
          const auto &[type, value] = grid_state[r][c];
          if (type == "WHITE") {
            if (!first_cell) log_file_ << ",";
            log_file_ << "[" << r << "," << c << "," << value << "]";
            first_cell = false;
          }
        }
      }
      log_file_ << "]}";
    } else {
      log_file_ << ",\"g\":[]}";
    }
    log_file_ << "\n";
    log_file_.flush();
#endif
  }

  void log_profile(const std::string &name, double duration_ms) {
#if KAKURO_ENABLE_LOGGING
    if (!enabled_ || !prof_file_.is_open())
      return;

    prof_file_ << "{\"id\":" << step_id_++ 
               << ",\"s\":\"" << STAGE_PROFILE << "\""
               << ",\"ss\":\"" << SUBSTAGE_TIMING << "\""
               << ",\"m\":\"Profile: " << escape_json(name) << "\""
               << ",\"dur\":" << std::fixed << std::setprecision(3) << duration_ms << "}\n";
    prof_file_.flush();
#endif
  }
};

// ============================================================================
// PROFILING TOOLS
// ============================================================================

class ScopedTimer {
public:
  ScopedTimer(const std::string &name, std::shared_ptr<GenerationLogger> logger)
      : name_(name), logger_(logger),
        start_(std::chrono::steady_clock::now()) {}

  ~ScopedTimer() {
    auto end = std::chrono::steady_clock::now();
    double duration =
        std::chrono::duration<double, std::milli>(end - start_).count();
    if (logger_ && logger_->is_enabled()) {
      logger_->log_profile(name_, duration);
    }
  }

private:
  std::string name_;
  std::shared_ptr<GenerationLogger> logger_;
  std::chrono::steady_clock::time_point start_;
};

#define PROFILE_SCOPE(name, logger)                                            \
  kakuro::ScopedTimer timer##__LINE__(name, logger)
#define PROFILE_FUNCTION(logger) PROFILE_SCOPE(__func__, logger)

enum class CellType { BLOCK, WHITE };

enum class UniquenessResult { UNIQUE, MULTIPLE, INCONCLUSIVE };

struct Cell {
  int r;
  int c;
  CellType type;
  std::optional<int> value;
  std::optional<int> clue_h; // Sum of the row to the right
  std::optional<int> clue_v; // Sum of the col below

  // Pointers to sectors (for fast access during solving)
  std::shared_ptr<std::vector<Cell *>> sector_h;
  std::shared_ptr<std::vector<Cell *>> sector_v;

  Cell(int row, int col, CellType t = CellType::WHITE)
      : r(row), c(col), type(t), value(std::nullopt), clue_h(std::nullopt),
        clue_v(std::nullopt), sector_h(nullptr), sector_v(nullptr) {}
};

struct PairHash {
  template <class T1, class T2>
  std::size_t operator()(const std::pair<T1, T2> &p) const {
    auto h1 = std::hash<T1>{}(p.first);
    auto h2 = std::hash<T2>{}(p.second);
    return h1 ^ (h2 << 1);
  }
};

class KakuroBoard {
public:
  int width;
  int height;
  std::vector<std::vector<Cell>> grid;
  std::vector<Cell *> white_cells;
  std::vector<std::shared_ptr<std::vector<Cell *>>> sectors_h;
  std::vector<std::shared_ptr<std::vector<Cell *>>> sectors_v;

  std::shared_ptr<GenerationLogger> logger;

  // Random number generator
  std::mt19937 rng;

  KakuroBoard(int w, int h);

  Cell *get_cell(int r, int c);
  void reset_values();
  void set_block(int r, int c);
  void set_white(int r, int c);

  // Topology generation
  bool generate_topology(const TopologyParams &params = TopologyParams());
  bool generate_topology(double density = 0.60, int max_sector_length = 9,
                         std::string difficulty = "medium"); // Legacy
  void apply_topology_defaults(TopologyParams &params);
  bool generate_stamps(const std::vector<std::pair<int, int>> &shapes,
                       int iterations);
  bool validate_topology_structure();
  // Helper methods
  void collect_white_cells();
  void identify_sectors();
  bool stabilize_grid(bool gentle = false);
  void stamp_rect(int r, int c, int h, int w);
  bool slice_long_runs(int max_len);
  bool slice_soft_runs(int soft_len, double prob);
  bool prune_singles();
  bool break_single_runs();
  bool validate_clue_headers();
  bool check_connectivity();
  int count_white_neighbors(Cell *cell);
  bool try_remove_and_reconnect(int r, int c);
  std::vector<std::vector<std::pair<int, int>>> find_components();

  bool place_random_seed();
  void grow_lattice(double density, int max_sector_length);
  bool break_large_patches(int size = 3);
  bool fix_invalid_runs();
  bool fix_invalid_runs_gentle();
  void apply_slice(int fixed_idx, int start, int length, bool is_horz);
  void block_sym(Cell *cell);
  bool ensure_connectivity();

  // Export to Python-friendly format
  std::vector<std::vector<std::unordered_map<std::string, std::string>>>
  to_dict() const;

  std::vector<std::vector<std::pair<std::string, int>>> get_grid_state(
      const std::unordered_map<Cell *, int> *assignment = nullptr) const;

private:
  // bool limit_sector_lengths(int max_length);
  // int count_neighbors_filled(Cell* cell, const std::unordered_map<Cell*,
  // int>& assignment); bool is_connected(const
  // std::unordered_set<std::pair<int, int>,
  //                   std::hash<std::pair<int, int>>>& coords);
};

struct PuzzleCell {
  CellType type;
  std::optional<int> clue_h;
  std::optional<int> clue_v;
  std::optional<int> solution;
};

struct GeneratedPuzzle {
  DifficultyResult difficulty;
  int width;
  int height;
  std::vector<std::vector<PuzzleCell>> grid;
};

class CSPSolver {
public:
  std::shared_ptr<KakuroBoard> board;
  std::mt19937 rng;

  CSPSolver(std::shared_ptr<KakuroBoard> b);
  void apply_fill_defaults(FillParams &params);

  void set_time_limit(double seconds) { time_limit_sec_ = seconds; }

  struct ScoreInfo {
    int value;
    double h_score;
    double v_score;
    double entropy;
    double weight;
    double combined;
  };

  struct ValueConstraint {
    Cell *cell;
    std::vector<int> values;
  };

  bool generate_puzzle(const FillParams &params = FillParams(),
                       const TopologyParams &topo_params = TopologyParams());
  bool generate_puzzle(const std::string &difficulty = "medium"); // Legacy
  GeneratedPuzzle generate_random_puzzle();
  bool
  solve_fill(const FillParams &params,
             const std::unordered_map<Cell *, int> &forced_assignments = {},
             const std::vector<ValueConstraint> &forbidden_constraints = {},
             bool ignore_clues = false);
  bool
  solve_fill(const std::string &difficulty, int max_nodes,
             const std::unordered_map<Cell *, int> &forced_assignments = {},
             const std::vector<ValueConstraint> &forbidden_constraints = {},
             bool ignore_clues = false); // Legacy
  void calculate_clues();
  std::pair<
      UniquenessResult,
      std::optional<std::unordered_map<std::pair<int, int>, int, PairHash>>>
  check_uniqueness(int max_nodes = 10000, int seed_offset = 0);

private:
  // --- Time Limit Members ---
  std::chrono::steady_clock::time_point start_time_;
  double time_limit_sec_ = 30.0; // Default 30 seconds
  bool check_timeout(); // Returns true if timed out and handles logging/closing

  bool
  backtrack_fill(std::unordered_map<Cell *, int> &assignment, int &node_count,
                 int max_nodes, const std::vector<int> &weights,
                 bool ignore_clues, const std::string &partition_preference,
                 const std::vector<ValueConstraint> &forbidden_constraints);
  bool attempt_fill_and_validate(const FillParams &params);
  bool prepare_new_topology(const TopologyParams &topo_params);
  std::pair<
      UniquenessResult,
      std::optional<std::unordered_map<std::pair<int, int>, int, PairHash>>>
  perform_robust_uniqueness_check();
  int count_neighbors_filled(Cell *cell,
                             const std::unordered_map<Cell *, int> &assignment);
  bool is_consistent_number(Cell *var, int value,
                            const std::unordered_map<Cell *, int> &assignment,
                            bool ignore_clues);
  int estimate_future_domain_size(
      Cell *cell, int value, char direction,
      const std::unordered_map<Cell *, int> &assignment);
  double estimate_intersection_entropy(
      Cell *cell, int value, const std::unordered_map<Cell *, int> &assignment);
  bool has_high_global_ambiguity();
  void solve_for_uniqueness(
      std::vector<std::unordered_map<std::pair<int, int>, int, PairHash>>
          &found_solutions,
      const std::unordered_map<std::pair<int, int>, int, PairHash> &avoid_sol,
      int &node_count, int max_nodes, int seed, bool &timed_out);

  int get_domain_size(
      Cell *cell, const std::unordered_map<Cell *, int> *assignment = nullptr,
      bool ignore_clues = false);
  bool
  is_valid_move(Cell *cell, int val,
                const std::unordered_map<Cell *, int> *assignment = nullptr,
                bool ignore_clues = false);
  bool repair_topology_robust(
      const std::unordered_map<std::pair<int, int>, int, PairHash> &alt_sol);
  std::unordered_map<Cell *, int> generate_breaking_constraints(
      const std::unordered_map<std::pair<int, int>, int, PairHash> &alt_sol,
      const std::unordered_map<std::pair<int, int>, int, PairHash> &prev_sol);

  bool
  is_connected(const std::unordered_set<std::pair<int, int>, PairHash> &coords);
  std::vector<int> get_partition_aware_domain(
      Cell *cell, const std::unordered_map<Cell *, int> &assignment,
      const std::string &preference, const std::vector<int> &weights);

  double
  calculate_partition_score(Cell *cell, int value,
                            const std::unordered_map<Cell *, int> &assignment,
                            char direction, const std::string &preference);

  int count_partitions(int target_sum, int length);

  int count_partitions_recursive(int remaining_sum, int remaining_length,
                                 int min_digit, std::unordered_set<int> &used);

  bool validate_partition_difficulty(
      const std::unordered_map<Cell *, int> &assignment,
      const std::string &preference);

  // Cache for partition counts
  std::unordered_map<std::pair<int, int>, int, PairHash> partition_cache;

  // Track scores for the current cell being filled (for logging)
  Cell *last_scored_cell = nullptr;
  std::vector<ScoreInfo> last_candidate_scores;
};

class KakuroDifficultyEstimator {
public:
  explicit KakuroDifficultyEstimator(std::shared_ptr<KakuroBoard> b);
  DifficultyResult estimate_difficulty_detailed();
  float estimate_difficulty();

private:
  struct SectorInfo {
    std::vector<Cell *> cells;
    int clue;
    bool is_horz;
  };

  struct SectorMetadata {
    int clue;
    int length;
  };

  std::unordered_map<Cell *, SectorMetadata> cell_to_h;
  std::unordered_map<Cell *, SectorMetadata> cell_to_v;

  std::shared_ptr<KakuroBoard> board;
  std::vector<SolveStep> solve_log;
  std::vector<std::unordered_map<Cell *, int>> found_solutions;
  std::vector<SectorInfo> all_sectors;
  std::unordered_set<Cell *> logged_singles;

  // Using bitmasks (1 << value) for performance. 0x3FE = digits 1-9.
  typedef std::unordered_map<Cell *, uint16_t> CandidateMap;
  static constexpr uint16_t ALL_CANDIDATES = 0x3FE;

  int mask_to_digit(uint16_t mask) const;

  // Internal Logic Engine
  void run_solve_loop(CandidateMap &candidates, bool silent);
  bool apply_logic_pass(CandidateMap &candidates, bool silent, int iteration);

  // Techniques
  bool find_unique_intersections(CandidateMap &candidates, bool silent);
  bool apply_simple_partitions(CandidateMap &candidates, bool silent);
  bool apply_constraint_propagation(CandidateMap &candidates, bool silent);
  bool find_hidden_singles(CandidateMap &candidates, bool silent);
  bool find_naked_singles(CandidateMap &candidates, bool silent, int iteration);

  // --- Complex Strategies ---
  bool analyze_complex_intersections(CandidateMap &candidates, bool silent);
  bool analyze_sector_pairs(CandidateMap &candidates);
  bool test_value_propagation(Cell *target, int val,
                              const CandidateMap &current_candidates);
  std::vector<std::shared_ptr<std::vector<Cell *>>>
  find_highly_constrained_sectors(const CandidateMap &candidates);

  // Infrastructure
  bool apply_sector_constraints(const SectorInfo &sec,
                                CandidateMap &candidates);
  void discover_solutions(CandidateMap candidates, int limit);
  bool try_bifurcation(CandidateMap &candidates);

  // Helpers
  std::optional<int> get_clue(const std::vector<Cell *> &sector, bool is_horz);
  std::vector<std::vector<int>> get_partitions(int sum, int len);
  uint16_t get_partition_bits(int sum, int len);
  int count_set_bits(uint16_t n) const;
  bool verify_math(const std::unordered_map<Cell *, int> &sol) const;
  std::vector<std::vector<std::optional<int>>>
  render_solution(const std::unordered_map<Cell *, int> &sol) const;

  // Avoid getting stuck
  long long nodes_explored = 0;
  const long long MAX_NODES = 50000000; // Adjust based on desired effort
  std::chrono::steady_clock::time_point start_time;
  const double TIME_LIMIT_SEC = 5.0;
  bool search_aborted = false;

  bool is_limit_exceeded() {
    if (search_aborted)
      return true;
    if (++nodes_explored > MAX_NODES) {
      search_aborted = true;
      return true;
    }
    if (nodes_explored % 500 == 0) {
      auto now = std::chrono::steady_clock::now();
      std::chrono::duration<double> elapsed = now - start_time;
      if (elapsed.count() > TIME_LIMIT_SEC) { // 2.5 second timeout
        search_aborted = true;
        return true;
      }
    }
    return false;
  }

  std::map<std::pair<int, int>, std::vector<std::vector<int>>> partition_cache;
  std::unordered_map<uint32_t, uint16_t> partition_mask_cache;
};

} // namespace kakuro

#endif // KAKURO_CPP_H