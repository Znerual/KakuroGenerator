#ifndef KAKURO_CPP_H
#define KAKURO_CPP_H

#include <vector>
#include <string>
#include <iostream>
#include <memory>
#include <optional>
#include <unordered_set>
#include <unordered_map>
#include <map>
#include <random>
#include <deque>
#include <utility>
#include <algorithm>
#include <cmath>
#include <bitset>
#include <functional>
#include <chrono>

namespace kakuro {

#define LOG_DEBUG(msg) do {} while(0) // do { std::cerr << "[DEBUG] " << msg << std::endl; } while(0)
#define LOG_INFO(msg)   do {} while(0) //do { std::cerr << "[INFO] " << msg << std::endl; } while(0)
#define LOG_ERROR(msg)  do {} while(0) //do { std::cerr << "[ERROR] " << msg << std::endl; } while(0)

enum class CellType {
    BLOCK,
    WHITE
};

enum class UniquenessResult {
    UNIQUE,
    MULTIPLE,
    INCONCLUSIVE
};

struct Cell {
    int r;
    int c;
    CellType type;
    std::optional<int> value;
    std::optional<int> clue_h;  // Sum of the row to the right
    std::optional<int> clue_v;  // Sum of the col below
    
    // Pointers to sectors (for fast access during solving)
    std::shared_ptr<std::vector<Cell*>> sector_h;
    std::shared_ptr<std::vector<Cell*>> sector_v;
    
    Cell(int row, int col, CellType t = CellType::WHITE)
        : r(row), c(col), type(t), value(std::nullopt), 
          clue_h(std::nullopt), clue_v(std::nullopt),
          sector_h(nullptr), sector_v(nullptr) {}
};

struct PairHash {
    template <class T1, class T2>
    std::size_t operator () (const std::pair<T1, T2>& p) const {
        auto h1 = std::hash<T1>{}(p.first);
        auto h2 = std::hash<T2>{}(p.second);
        return h1 ^ (h2 << 1);
    }
};

struct TopologyParams {
    std::string difficulty = "medium";
    std::optional<double> density;
    std::optional<int> max_sector_length;
    std::optional<int> num_stamps;
    std::optional<int> min_cells;
    std::optional<int> max_run_len;
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

class KakuroBoard {
public:
    int width;
    int height;
    std::vector<std::vector<Cell>> grid;
    std::vector<Cell*> white_cells;
    std::vector<std::shared_ptr<std::vector<Cell*>>> sectors_h;
    std::vector<std::shared_ptr<std::vector<Cell*>>> sectors_v;
    
    // Random number generator
    std::mt19937 rng;
    
    KakuroBoard(int w, int h);
    
    Cell* get_cell(int r, int c);
    void reset_values();
    void set_block(int r, int c);
    void set_white(int r, int c);
    
    // Topology generation
    bool generate_topology(const TopologyParams& params = TopologyParams());
    bool generate_topology(double density = 0.60, int max_sector_length = 9, std::string difficulty = "medium"); // Legacy
    void apply_topology_defaults(TopologyParams& params);
    bool generate_stamps(const std::vector<std::pair<int, int>>& shapes, int iterations);
    bool validate_topology_structure();
    // Helper methods
    void collect_white_cells();
    void identify_sectors();
    void stabilize_grid(bool gentle = false);
    void stamp_rect(int r, int c, int h, int w);
    void slice_long_runs(int max_len);
    void prune_singles();
    void break_single_runs();
    bool validate_clue_headers();
    bool check_connectivity();
    int count_white_neighbors(Cell* cell);
    
    bool place_random_seed();
    void grow_lattice(double density, int max_sector_length);
    void break_large_patches(int size = 3);
    bool fix_invalid_runs();
    bool fix_invalid_runs_gentle();
    void apply_slice(int fixed_idx, int start, int length, bool is_horz);
    void block_sym(Cell* cell);
    bool ensure_connectivity();
    
    // Export to Python-friendly format
    std::vector<std::vector<std::unordered_map<std::string, std::string>>> to_dict() const;
    
private:
    
    // bool limit_sector_lengths(int max_length);
    // int count_neighbors_filled(Cell* cell, const std::unordered_map<Cell*, int>& assignment);
    // bool is_connected(const std::unordered_set<std::pair<int, int>, 
    //                   std::hash<std::pair<int, int>>>& coords);
};

enum class TechniqueTier {
    VERY_EASY = 1,  // Intersection of two masks, naked singles
    EASY = 2,       // Simple partitions (only 1 valid combination)
    MEDIUM = 3,     // Hidden singles, basic constraint propagation
    HARD = 4,       // Complex intersections, multi-sector lookahead
    EXTREME = 5     // Trial and Error / Bifurcation
};

struct SolveStep {
    std::string technique;
    float difficulty_weight;
    int cells_affected;
    SolveStep(std::string t, float w, int c) : technique(t), difficulty_weight(w), cells_affected(c) {}
};

struct DifficultyResult {
    float score = 0;      // Factor 2: Persistence (Sum of effort)
    std::string rating;          // Factor 1: Capability (Hardest technique)
    TechniqueTier max_tier = TechniqueTier::VERY_EASY;
    
    int total_steps = 0;
    int solution_count = 0;
    std::string uniqueness;
    std::vector<SolveStep> solve_path;
    std::vector<std::vector<std::vector<std::optional<int>>>> solutions;
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

    struct ValueConstraint {
        Cell* cell;
        std::vector<int> values;
    };
    
    bool generate_puzzle(const FillParams& params = FillParams(), const TopologyParams& topo_params = TopologyParams());
    bool generate_puzzle(const std::string& difficulty = "medium"); // Legacy
    GeneratedPuzzle generate_random_puzzle();
    bool solve_fill(const FillParams& params,
                   const std::unordered_map<Cell*, int>& forced_assignments = {}, 
                    const std::vector<ValueConstraint>& forbidden_constraints = {},
                   bool ignore_clues = false);
    bool solve_fill(const std::string& difficulty, 
                   int max_nodes, 
                   const std::unordered_map<Cell*, int>& forced_assignments = {}, 
                    const std::vector<ValueConstraint>& forbidden_constraints = {},
                   bool ignore_clues = false); // Legacy
    void calculate_clues();
    std::pair<UniquenessResult, std::optional<std::unordered_map<std::pair<int, int>, int, PairHash>>> 
    check_uniqueness(int max_nodes = 10000, int seed_offset = 0);
    
private:
    bool backtrack_fill(std::unordered_map<Cell*, int>& assignment, 
                   int& node_count, int max_nodes, 
                   const std::vector<int>& weights,
                   bool ignore_clues,
                   const std::string& partition_preference,
                   const std::vector<ValueConstraint>& forbidden_constraints);
    bool attempt_fill_and_validate(const FillParams& params);
    bool prepare_new_topology(const TopologyParams& topo_params);
    UniquenessResult perform_robust_uniqueness_check();
    int count_neighbors_filled(Cell* cell, const std::unordered_map<Cell*, int>& assignment);
    bool is_consistent_number(Cell* var, int value, const std::unordered_map<Cell*, int>& assignment, bool ignore_clues);
    
    void solve_for_uniqueness(
        std::vector<std::unordered_map<std::pair<int, int>, int, PairHash>>& found_solutions,
        const std::unordered_map<std::pair<int, int>, int, PairHash>& avoid_sol,
        int& node_count, int max_nodes, int seed, bool& timed_out);

    int get_domain_size(Cell* cell, const std::unordered_map<Cell*, int>* assignment = nullptr, bool ignore_clues = false);
    bool is_valid_move(Cell* cell, int val, const std::unordered_map<Cell*, int>* assignment = nullptr, bool ignore_clues = false);
    bool repair_topology_robust(const std::unordered_map<std::pair<int, int>, int, PairHash>& alt_sol);
    std::unordered_map<Cell*, int> generate_breaking_constraints(
        const std::unordered_map<std::pair<int, int>, int, PairHash>& alt_sol,
        const std::unordered_map<std::pair<int, int>, int, PairHash>& prev_sol);
        
    bool is_connected(const std::unordered_set<std::pair<int, int>, PairHash>& coords);
    std::vector<int> get_partition_aware_domain(
        Cell* cell, 
        const std::unordered_map<Cell*, int>& assignment,
        const std::string& preference,
        const std::vector<int>& weights);
    
    double calculate_partition_score(
        Cell* cell,
        int value,
        const std::unordered_map<Cell*, int>& assignment,
        char direction,
        const std::string& preference);
    
    int count_partitions(int target_sum, int length);
    
    int count_partitions_recursive(
        int remaining_sum,
        int remaining_length,
        int min_digit,
        std::unordered_set<int>& used);
    
    bool validate_partition_difficulty(
        const std::unordered_map<Cell*, int>& assignment,
        const std::string& preference);
    
    // Cache for partition counts
    std::unordered_map<std::pair<int, int>, int, PairHash> partition_cache;
};

 



class KakuroDifficultyEstimator {
public:
    explicit KakuroDifficultyEstimator(std::shared_ptr<KakuroBoard> b);
    DifficultyResult estimate_difficulty_detailed();
    float estimate_difficulty();

private:
    struct SectorInfo {
        std::vector<Cell*> cells;
        int clue;
        bool is_horz;
    };

    struct SectorMetadata {
        int clue;
        int length;
    };

    
    std::unordered_map<Cell*, SectorMetadata> cell_to_h;
    std::unordered_map<Cell*, SectorMetadata> cell_to_v;
    
    std::shared_ptr<KakuroBoard> board;
    std::vector<SolveStep> solve_log;
    std::vector<std::unordered_map<Cell*, int>> found_solutions;
    std::vector<SectorInfo> all_sectors;
    std::unordered_set<Cell*> logged_singles;

    // Using bitmasks (1 << value) for performance. 0x3FE = digits 1-9.
    typedef std::unordered_map<Cell*, uint16_t> CandidateMap;
    static constexpr uint16_t ALL_CANDIDATES = 0x3FE;

    int mask_to_digit(uint16_t mask) const;
    
    // Internal Logic Engine
    void run_solve_loop(CandidateMap& candidates, bool silent);
    bool apply_logic_pass(CandidateMap& candidates, bool silent, int iteration);
    
    // Techniques
    bool find_unique_intersections(CandidateMap& candidates, bool silent);
    bool apply_simple_partitions(CandidateMap& candidates, bool silent);
    bool apply_constraint_propagation(CandidateMap& candidates, bool silent);
    bool find_hidden_singles(CandidateMap& candidates, bool silent);
    bool find_naked_singles(CandidateMap& candidates, bool silent, int iteration);

    // --- Complex Strategies ---
    bool analyze_complex_intersections(CandidateMap& candidates, bool silent);
    bool analyze_sector_pairs(CandidateMap& candidates);
    bool test_value_propagation(Cell* target, int val, const CandidateMap& current_candidates);
    std::vector<std::shared_ptr<std::vector<Cell*>>> find_highly_constrained_sectors(const CandidateMap& candidates);

    // Infrastructure
    bool apply_sector_constraints(const SectorInfo& sec, CandidateMap& candidates);
    void discover_solutions(CandidateMap candidates, int limit);
    bool try_bifurcation(CandidateMap& candidates);
    
    // Helpers
    std::optional<int> get_clue(const std::vector<Cell*>& sector, bool is_horz);
    std::vector<std::vector<int>> get_partitions(int sum, int len);
    uint16_t get_partition_bits(int sum, int len);
    int count_set_bits(uint16_t n) const;
    bool verify_math(const std::unordered_map<Cell*, int>& sol) const;
    std::vector<std::vector<std::optional<int>>> render_solution(const std::unordered_map<Cell*, int>& sol) const;
    
    // Avoid getting stuck
    long long nodes_explored = 0;
    const long long MAX_NODES = 50000000; // Adjust based on desired effort
    std::chrono::steady_clock::time_point start_time;
    const double TIME_LIMIT_SEC = 5.0; 
    bool search_aborted = false;

    bool is_limit_exceeded() {
        if (search_aborted) return true;
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