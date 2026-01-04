#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <sstream>
#include <iomanip>
#include "kakuro_cpp.h"

namespace py = pybind11;

PYBIND11_MODULE(kakuro_cpp, m) {
    m.doc() = "Kakuro puzzle generator and solver in C++";

    // Bind CellType enum
    py::enum_<kakuro::CellType>(m, "CellType")
        .value("BLOCK", kakuro::CellType::BLOCK)
        .value("WHITE", kakuro::CellType::WHITE)
        .export_values();

    // Bind Cell class
    py::class_<kakuro::Cell>(m, "Cell")
        .def(py::init<int, int, kakuro::CellType>(),
             py::arg("r"), py::arg("c"), py::arg("type") = kakuro::CellType::WHITE)
        .def_readwrite("r", &kakuro::Cell::r)
        .def_readwrite("c", &kakuro::Cell::c)
        .def_readwrite("type", &kakuro::Cell::type)
        .def_property("value",
            [](const kakuro::Cell& c) -> py::object {
                if (c.value.has_value()) {
                    return py::cast(c.value.value());
                }
                return py::none();
            },
            [](kakuro::Cell& c, py::object val) {
                if (val.is_none()) {
                    c.value = std::nullopt;
                } else {
                    c.value = val.cast<int>();
                }
            })
        .def_property("clue_h",
            [](const kakuro::Cell& c) -> py::object {
                if (c.clue_h.has_value()) {
                    return py::cast(c.clue_h.value());
                }
                return py::none();
            },
            [](kakuro::Cell& c, py::object val) {
                if (val.is_none()) {
                    c.clue_h = std::nullopt;
                } else {
                    c.clue_h = val.cast<int>();
                }
            })
        .def_property("clue_v",
            [](const kakuro::Cell& c) -> py::object {
                if (c.clue_v.has_value()) {
                    return py::cast(c.clue_v.value());
                }
                return py::none();
            },
            [](kakuro::Cell& c, py::object val) {
                if (val.is_none()) {
                    c.clue_v = std::nullopt;
                } else {
                    c.clue_v = val.cast<int>();
                }
            })
        .def("to_dict", [](const kakuro::Cell& c) {
            py::dict d;
            d["r"] = c.r;
            d["c"] = c.c;
            d["type"] = (c.type == kakuro::CellType::BLOCK) ? "BLOCK" : "WHITE";
            
            if (c.value.has_value()) d["value"] = c.value.value();
            else d["value"] = py::none();
            
            if (c.clue_h.has_value()) d["clue_h"] = c.clue_h.value();
            else d["clue_h"] = py::none();
            
            if (c.clue_v.has_value()) d["clue_v"] = c.clue_v.value();
            else d["clue_v"] = py::none();
            
            return d;
        })
        .def("__repr__", [](const kakuro::Cell& c) {
            return "Cell(" + std::to_string(c.r) + "," + std::to_string(c.c) + ")";
        });

    // Bind KakuroBoard class
    py::class_<kakuro::KakuroBoard, std::shared_ptr<kakuro::KakuroBoard>>(m, "KakuroBoard")
        .def(py::init<int, int>())
        .def_readwrite("width", &kakuro::KakuroBoard::width)
        .def_readwrite("height", &kakuro::KakuroBoard::height)
        .def("get_cell", &kakuro::KakuroBoard::get_cell,
             py::return_value_policy::reference)
        .def("reset_values", &kakuro::KakuroBoard::reset_values)
        .def("set_block", &kakuro::KakuroBoard::set_block)
        .def("set_white", &kakuro::KakuroBoard::set_white)
        
        // FIX: Added difficulty argument
        .def("generate_topology", &kakuro::KakuroBoard::generate_topology,
             py::arg("density") = 0.60,
             py::arg("max_sector_length") = 9,
             py::arg("difficulty") = "medium") 
             
        .def("collect_white_cells", &kakuro::KakuroBoard::collect_white_cells)
        .def("identify_sectors", &kakuro::KakuroBoard::identify_sectors)
        .def("to_dict", &kakuro::KakuroBoard::to_dict)
        .def_property_readonly("white_cells",
            [](const kakuro::KakuroBoard& b) {
                return b.white_cells;
            })
        .def_property_readonly("sectors_h", [](const kakuro::KakuroBoard& b) {
                // Convert vector<shared_ptr<vector<Cell*>>> 
                // to vector<vector<Cell*>> for Python
                std::vector<std::vector<kakuro::Cell*>> result;
                for (const auto& sector_ptr : b.sectors_h) {
                    if (sector_ptr) {
                        result.push_back(*sector_ptr); // Dereference shared_ptr to copy vector
                    }
                }
                return result; // Pybind11 converts this to list of lists of Cells automatically
            })
        .def_property_readonly("sectors_v", [](const kakuro::KakuroBoard& b) {
                // Convert vector<shared_ptr<vector<Cell*>>> 
                // to vector<vector<Cell*>> for Python
                std::vector<std::vector<kakuro::Cell*>> result;
                for (const auto& sector_ptr : b.sectors_v) {
                    if (sector_ptr) {
                        result.push_back(*sector_ptr); // Dereference shared_ptr to copy vector
                    }
                }
                return result; // Pybind11 converts this to list of lists of Cells automatically
            })
        .def("get_grid", [](const kakuro::KakuroBoard& b) {
            py::list result;
            for (int r = 0; r < b.height; r++) {
                py::list row;
                for (int c = 0; c < b.width; c++) {
                    row.append(py::cast(&b.grid[r][c], py::return_value_policy::reference));
                }
                result.append(row);
            }
            return result;
        });

    py::class_<kakuro::CSPSolver::ValueConstraint>(m, "ValueConstraint")
        .def(py::init<>())
        .def_readwrite("cell", &kakuro::CSPSolver::ValueConstraint::cell)
        .def_readwrite("values", &kakuro::CSPSolver::ValueConstraint::values);

    // Bind CSPSolver class
    py::class_<kakuro::CSPSolver>(m, "CSPSolver")
        .def(py::init<std::shared_ptr<kakuro::KakuroBoard>>())
        .def("generate_puzzle", &kakuro::CSPSolver::generate_puzzle,
             py::arg("difficulty") = "medium")
             
        .def("solve_fill", &kakuro::CSPSolver::solve_fill,
             py::arg("difficulty") = "medium",
             py::arg("max_nodes") = 30000,
             py::arg("forced_assignments") = std::unordered_map<kakuro::Cell*, int>(),
             py::arg("forbidden_constraints") = std::vector<kakuro::CSPSolver::ValueConstraint>(),
             py::arg("ignore_clues") = false)
             
        .def("calculate_clues", &kakuro::CSPSolver::calculate_clues)
        
        .def("check_uniqueness", &kakuro::CSPSolver::check_uniqueness,
             py::arg("max_nodes") = 10000,
             py::arg("seed_offset") = 0);

    py::class_<kakuro::SolveStep>(m, "SolveStep")
        .def_readwrite("technique", &kakuro::SolveStep::technique)
        .def_readwrite("difficulty_weight", &kakuro::SolveStep::difficulty_weight)
        .def_readwrite("cells_affected", &kakuro::SolveStep::cells_affected);

    py::class_<kakuro::DifficultyResult>(m, "DifficultyResult")
        .def_readwrite("score", &kakuro::DifficultyResult::score)
        .def_readwrite("rating", &kakuro::DifficultyResult::rating)
        .def_readwrite("uniqueness", &kakuro::DifficultyResult::uniqueness)
        .def_readwrite("solution_count", &kakuro::DifficultyResult::solution_count)
        .def_readwrite("solve_path", &kakuro::DifficultyResult::solve_path)
        .def_readwrite("techniques_used", &kakuro::DifficultyResult::techniques_used)
        .def_readwrite("solutions", &kakuro::DifficultyResult::solutions)
        .def("__repr__", [](const kakuro::DifficultyResult &r) {
            std::ostringstream oss;
            oss << "<DifficultyResult rating='" << r.rating << "', "
                << "score=" << std::fixed << std::setprecision(1) << r.score << ", "
                << "uniqueness='" << r.uniqueness << "', "
                << "solutions=" << r.solution_count << ">";
            return oss.str();
        });

    py::class_<kakuro::KakuroDifficultyEstimator>(m, "KakuroDifficultyEstimator")
        .def(py::init<std::shared_ptr<kakuro::KakuroBoard>>())
        .def("estimate_difficulty", &kakuro::KakuroDifficultyEstimator::estimate_difficulty)
        .def("estimate_difficulty_detailed", &kakuro::KakuroDifficultyEstimator::estimate_difficulty_detailed);
   
}