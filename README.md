# Kakuro Puzzle Generator & Solver

A robust, full-stack Kakuro puzzle platform featuring a sophisticated procedural generation engine and an interactive web-based interface. This tool provides puzzles of varying difficulties, guaranteed uniqueness (optional), and a local library for saving progress.

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.8+**
- **pip** (Python package manager)

### Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/your-username/KakuroGenerator.git
    cd KakuroGenerator/backend
    ```

2.  **Create a virtual environment (optional but recommended)**:
    ```bash
    python -m venv .venv
    # On Windows:
    .venv\Scripts\activate
    # On macOS/Linux:
    source .venv/bin/activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

### Running the Tool

#### 1. As an Executable (Recommended for users)
If you have a pre-built executable:
- Simply run `KakuroGenerator.exe`.
- The application will be available at `http://localhost:8000`.

#### 2. From Source (Development)
1.  **Start the Backend Server**:
    From the `backend` directory, run:
    ```bash
    python main.py
    ```
    The server will start on `http://localhost:8008`.

2.  **Access the Application**:
    Open your web browser and navigate to `http://localhost:8008`.

---

## Recompile Extensions

if you want to recompile the extensions, run:
```bash
uv run python setup.py build_ext --inplace
```

## 📦 Packaging (Build your own executable)

If you want to create a standalone `.exe` for distribution:

1.  **Ensure you are in the `backend` directory**.
2.  **Run the packaging script**:
    ```bash
    python package_app.py
    ```
    This script will:
    - Install `PyInstaller` if it's missing.
    - Bundle the `static` folder and the Python backend into a single file.
    - Generate the executable in the `dist` directory.

> [!NOTE]
> The generated executable will store puzzles in a `saved_puzzles` folder located in the same directory as the `.exe`.

---

## 🧩 Features

- **Procedural Generation**: Every puzzle is unique, generated using a combination of topological randomization and constraint satisfaction.
- **Variable Difficulty**: Choose from `Very Easy`, `Easy`, `Medium`, and `Hard`, affecting grid size and clue complexity.
- **Interactive Board**: Number input, arrow key navigation, and real-time error checking.
- **Check Functionality**: Validate your solution against the generated answer key.
- **Puzzle Library**: Save your progress locally and resume later. Includes a thumbnail preview of saved puzzles.
- **Marginal Notes**: Specialized fields for row and column annotations to help solve complex puzzles.

---

## 🛠️ How it Works

The tool utilizes a multi-phase generation pipeline to ensure high-quality, solvable Kakuro puzzles.

### 1. Topology Generation
The "skeleton" of the puzzle is created with several constraints:
- **Rotational Symmetry**: The board is generated with 180° rotational symmetry for a classic aesthetic.
- **Connectivity**: A Breadth-First Search (BFS) ensures that all white cells form a single connected component.
- **Stabilization**: An iterative process fixes "single runs" (runs of length 1) to ensure every sector is at least 2 cells long.
- **Sector Limiting**: To aid solvability and uniqueness, the generator can limit the maximum length of any row or column sector.

### 2. Constraint Satisfaction Problem (CSP) Solver
Once the topology is set, the grid is filled using a custom CSP solver:
- **Backtracking Search**: An optimized recursion fills cells with numbers 1-9.
- **MRV Heuristic**: The "Minimum Remaining Values" heuristic is used to select the next cell to fill, significantly pruning the search space.
- **Consistency Checks**:
    - **Uniqueness**: Each number must be unique within its horizontal and vertical sector.
    - **Arithmetic Summary**: Once a sector is fully filled, the sum must match the pre-calculated clue.

### 3. Iterative Uniqueness Refinement (Advanced)
If the "Guarantee Uniqueness" option is used, the generator performs a secondary verification:
- It attempts to find a *different* solution to the generated clues.
- If an alternate solution is found, the tool **tightens constraints** by splitting long sectors or adding strategically placed blocks at intersections.
- The process repeats until a unique solution is guaranteed or the retry limit is reached.

---

## 📂 Project Structure

- `backend/main.py`: FastAPI application and API endpoints.
- `backend/kakuro.py`: Core logic for `KakuroBoard` and topology generation.
- `backend/solver.py`: CSP Solver and uniqueness verification logic.
- `backend/storage.py`: Local file-based storage for puzzles.
- `backend/static/`: Frontend assets (HTML, CSS, JS).

---

## 📝 License

This project is open-source and available under the MIT License.
