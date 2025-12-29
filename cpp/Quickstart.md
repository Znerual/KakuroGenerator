# Kakuro C++ Quick Start Guide

## For Python Users

### 1. Install Dependencies
```bash
pip install pybind11
```

### 2. Build the Module
```bash
# Option A: Using the build script (Linux/Mac)
./build.sh python

# Option B: Using setup.py directly
python setup.py install

# Option C: Development mode (editable install)
pip install -e .
```

### 3. Test the Installation
```python
from kakuro_wrapper import generate_kakuro

# Generate a puzzle
board = generate_kakuro(10, 10, difficulty="medium")
print(f"Generated {len(board.white_cells)} white cells")
```

### 4. Use in Your Code
```python
from kakuro_wrapper import KakuroBoard, CSPSolver, export_to_json
import json

# Create and generate
board = KakuroBoard(12, 12, use_cpp=True)
solver = CSPSolver(board)

if solver.generate_puzzle("hard"):
    # Export to JSON
    data = export_to_json(board)
    with open("puzzle.json", "w") as f:
        json.dump(data, f)
    print("Puzzle saved!")
```

## For Android Developers

### 1. Add Files to Your Project
Copy these files to your Android project:
```
app/src/main/cpp/
├── kakuro_cpp.h
├── kakuro_board.cpp
├── kakuro_solver.cpp
├── kakuro_jni.h
└── kakuro_jni.cpp

app/src/main/java/com/kakuro/
├── KakuroBoard.java
└── CSPSolver.java
```

### 2. Configure CMakeLists.txt
Create or update `app/src/main/cpp/CMakeLists.txt`:
```cmake
cmake_minimum_required(VERSION 3.18.1)
project("kakuro")

add_library(kakuro_jni SHARED
    kakuro_board.cpp
    kakuro_solver.cpp
    kakuro_jni.cpp
)

target_include_directories(kakuro_jni PRIVATE .)
target_link_libraries(kakuro_jni log)
```

### 3. Configure build.gradle
Update `app/build.gradle`:
```gradle
android {
    defaultConfig {
        externalNativeBuild {
            cmake {
                cppFlags "-std=c++17"
            }
        }
    }
    
    externalNativeBuild {
        cmake {
            path "src/main/cpp/CMakeLists.txt"
        }
    }
}
```

### 4. Use in Kotlin
```kotlin
class MainActivity : AppCompatActivity() {
    private fun generatePuzzle() {
        lifecycleScope.launch(Dispatchers.Default) {
            val board = KakuroBoard(10, 10)
            val solver = CSPSolver(board)
            
            try {
                board.generateTopology()
                
                if (solver.generatePuzzle(CSPSolver.Difficulty.MEDIUM)) {
                    val json = board.toJson()
                    withContext(Dispatchers.Main) {
                        // Update UI with puzzle
                        displayPuzzle(json)
                    }
                }
            } finally {
                solver.destroy()
                board.destroy()
            }
        }
    }
}
```

## Performance Tips

### Python
1. **Reuse board objects** when generating multiple puzzles
2. **Use appropriate difficulty**: Start with "easy" for testing
3. **Profile first**: Check if C++ is actually the bottleneck

Example:
```python
# Good: Reuse board for multiple attempts
board = KakuroBoard(10, 10, use_cpp=True)
solver = CSPSolver(board)

for attempt in range(5):
    board.reset_values()
    if solver.generate_puzzle("medium"):
        print(f"Success on attempt {attempt}")
        break
```

### Android
1. **Generate on background thread**: Always use coroutines/AsyncTask
2. **Destroy resources**: Call `destroy()` in finally blocks
3. **Cache results**: Don't regenerate the same puzzle twice

Example:
```kotlin
// Good: Background generation with proper cleanup
suspend fun generatePuzzle(): String? = withContext(Dispatchers.Default) {
    val board = KakuroBoard(10, 10)
    val solver = CSPSolver(board)
    
    try {
        board.generateTopology()
        if (solver.generatePuzzle(CSPSolver.Difficulty.MEDIUM)) {
            board.toJson()
        } else {
            null
        }
    } finally {
        solver.destroy()
        board.destroy()
    }
}
```

## Troubleshooting

### "Module not found" (Python)
```bash
# Make sure you built the module
python setup.py install

# Or use development mode
pip install -e .
```

### "UnsatisfiedLinkError" (Android)
- Check that CMakeLists.txt is configured correctly
- Verify ABI filters in build.gradle match your test device
- Clean and rebuild: Build → Clean Project → Rebuild Project

### Slow Generation
- Try easier difficulty first
- For very large boards (15x15+), generation can take several seconds
- Consider implementing timeout/cancellation for user experience

### Memory Issues (Android)
- Always call `destroy()` on board and solver
- Don't keep references to destroyed objects
- Consider object pooling for frequent generation

## Next Steps

1. **Customize difficulty**: Modify weight distributions in solver
2. **Add features**: Implement hints, validation, etc.
3. **Optimize for your use case**: Adjust density, sector lengths
4. **Add UI**: Create puzzle rendering and interaction

## Need Help?

- Check the main README.md for detailed documentation
- Review the example code in kakuro_wrapper.py
- Look at the Java examples in KakuroBoard.java and CSPSolver.java