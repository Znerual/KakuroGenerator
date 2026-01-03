#ifndef KAKURO_CPP_H
#define KAKURO_CPP_H

#include <vector>
#include <string>
#include <iostream>
#include <memory>
#include <optional>
#include <unordered_set>
#include <unordered_map>
#include <random>
#include <deque>
#include <utility>
#include <algorithm>
#include <bitset>

namespace kakuro {

#define LOG_DEBUG(msg) do {} while(0) // do { std::cerr << "[CPP] " << msg << std::endl; std::cerr.flush(); } while(0)

enum class CellType {
    BLOCK,
    WHITE
};

struct Cell {
    int r;
    int c;
    CellType type;
    std::optional<int> value;
    std::optional<int> clue_h;  // Sum of the row to the right
    std::optional<int> clue_v;  // Sum of the col below
    
    // Pointers to sectors (for fast access during solving)
    std::vector<Cell*>* sector_h;
    std::vector<Cell*>* sector_v;
    
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

class KakuroBoard {
public:
    int width;
    int height;
    std::vector<std::vector<Cell>> grid;
    std::vector<Cell*> white_cells;
    std::deque<std::vector<Cell*>> sectors_h;  // Use deque to prevent pointer invalidation
    std::deque<std::vector<Cell*>> sectors_v;  // Use deque to prevent pointer invalidation
    
    // Random number generator
    std::mt19937 rng;
    
    KakuroBoard(int w, int h);
    
    Cell* get_cell(int r, int c);
    void reset_values();
    void set_block(int r, int c);
    void set_white(int r, int c);
    
    // Topology generation
    void generate_topology(double density = 0.60, int max_sector_length = 9, std::string difficulty = "medium");
    bool generate_stamps(const std::vector<std::pair<int, int>>& shapes, int iterations);
    
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
    
    // Export to Python-friendly format
    std::vector<std::vector<std::unordered_map<std::string, std::string>>> to_dict() const;
    
private:
    bool place_random_seed();
    void grow_lattice(double density, int max_sector_length);
    void break_large_patches(int size = 3);
    bool fix_invalid_runs();
    bool fix_invalid_runs_gentle();
    void apply_slice(int fixed_idx, int start, int length, bool is_horz);
    void block_sym(Cell* cell);
    bool ensure_connectivity();
    // bool limit_sector_lengths(int max_length);
    // int count_neighbors_filled(Cell* cell, const std::unordered_map<Cell*, int>& assignment);
    // bool is_connected(const std::unordered_set<std::pair<int, int>, 
    //                   std::hash<std::pair<int, int>>>& coords);
};

class CSPSolver {
public:
    std::shared_ptr<KakuroBoard> board;
    std::mt19937 rng;
    
    CSPSolver(std::shared_ptr<KakuroBoard> b);
    
    bool generate_puzzle(const std::string& difficulty = "medium");
    bool solve_fill(const std::string& difficulty = "medium", int max_nodes = 30000, const std::unordered_map<Cell*, int>& initial_constraints = {}, bool ignore_clues = false);
    void calculate_clues();
    std::pair<bool, std::optional<std::unordered_map<std::pair<int, int>, int, PairHash>>> 
    check_uniqueness(int max_nodes = 10000, int seed_offset = 0);
    
private:
    bool backtrack_fill(std::unordered_map<Cell*, int>& assignment, 
                       int& node_count, int max_nodes, 
                       const std::vector<int>& weights,
                       bool ignore_clues);
    
    int count_neighbors_filled(Cell* cell, const std::unordered_map<Cell*, int>& assignment);
    bool is_consistent_number(Cell* var, int value, const std::unordered_map<Cell*, int>& assignment, bool ignore_clues);
    
    void solve_for_uniqueness(
        std::vector<std::unordered_map<std::pair<int, int>, int, PairHash>>& found_solutions,
        const std::unordered_map<std::pair<int, int>, int, PairHash>& avoid_sol,
        int& node_count, int max_nodes, int seed);

    int get_domain_size(Cell* cell);
    bool is_valid_move(Cell* cell, int val);
    bool repair_topology_robust(const std::unordered_map<std::pair<int, int>, int, PairHash>& alt_sol);
    std::unordered_map<Cell*, int> generate_breaking_constraints(
        const std::unordered_map<std::pair<int, int>, int, PairHash>& alt_sol,
        const std::unordered_map<std::pair<int, int>, int, PairHash>& prev_sol);
        
    bool is_connected(const std::unordered_set<std::pair<int, int>, PairHash>& coords);
};

class KakuroDifficultyEstimator {
public:
    std::shared_ptr<KakuroBoard> board;
    
    KakuroDifficultyEstimator(std::shared_ptr<KakuroBoard> b);
    
    float estimate_difficulty();

private:
    // 0x3FE = binary ...1111111110 (bits 1-9 set)
    static const uint16_t ALL_CANDIDATES = 0x3FE; 
    
    std::vector<std::vector<uint16_t>> candidates;
    
    bool apply_sum_constraints(const std::vector<Cell*>& sector);
    
    void find_valid_permutations(
        const std::vector<Cell*>& sector,
        int index,
        int current_sum,
        int target_sum,
        uint16_t used_numbers_mask,
        std::vector<int>& path,
        std::vector<uint16_t>& allowed_values_per_slot
    );
    
    int count_set_bits(uint16_t n);
};

} // namespace kakuro


#endif // KAKURO_CPP_H