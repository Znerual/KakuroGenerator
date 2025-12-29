#!/bin/bash

# KakuroGenerator C++ Build Script
# Builds the C++ extension for your FastAPI project

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_step() {
    echo -e "${GREEN}==>${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

print_error() {
    echo -e "${RED}✗${NC}  $1"
}

print_success() {
    echo -e "${GREEN}✓${NC}  $1"
}

print_usage() {
    echo "Usage: ./build.sh [build|clean|test|install|docker]"
    echo ""
    echo "Options:"
    echo "  build   - Build C++ extension in-place (default)"
    echo "  clean   - Clean all build artifacts"
    echo "  test    - Build and run tests"
    echo "  install - Install the package with C++ extension"
    echo "  docker  - Build Docker image with C++ support"
    echo ""
}

check_dependencies() {
    print_step "Checking dependencies..."
    
    # Check CMake
    if ! command -v cmake &> /dev/null; then
        print_error "CMake not found"
        echo "  Install with: sudo apt-get install cmake (Ubuntu/Debian)"
        echo "            or: brew install cmake (macOS)"
        exit 1
    fi
    print_success "CMake found: $(cmake --version | head -n1)"
    
    # Check C++ compiler
    if ! command -v g++ &> /dev/null && ! command -v clang++ &> /dev/null; then
        print_error "No C++ compiler found"
        echo "  Install with: sudo apt-get install g++ (Ubuntu/Debian)"
        exit 1
    fi
    if command -v g++ &> /dev/null; then
        print_success "GCC found: $(g++ --version | head -n1)"
    else
        print_success "Clang found: $(clang++ --version | head -n1)"
    fi
    
    # Check pybind11
    if ! python3 -c "import pybind11" 2>/dev/null; then
        print_warning "pybind11 not found, installing..."
        pip install pybind11
    fi
    print_success "pybind11 found"
}

build_cpp() {
    print_step "Building C++ extension..."
    
    check_dependencies
    
    # Build the extension
    python3 setup.py build_ext --inplace
    
    # Check if build succeeded
    if ls python/kakuro_cpp*.so python/kakuro_cpp*.pyd 2>/dev/null; then
        print_success "C++ extension built successfully!"
        
        # Show the built file
        BUILT_FILE=$(ls python/kakuro_cpp*.so python/kakuro_cpp*.pyd 2>/dev/null | head -n1)
        echo "  Built: $BUILT_FILE"
        echo "  Size: $(du -h "$BUILT_FILE" | cut -f1)"
    else
        print_error "Build failed - extension not found"
        exit 1
    fi
    
    # Test import
    print_step "Testing import..."
    if python3 -c "import sys; sys.path.insert(0, 'python'); import kakuro_cpp; print('✓ Import successful')" 2>/dev/null; then
        print_success "C++ module imports correctly"
    else
        print_warning "C++ module built but cannot be imported"
        print_warning "This might be normal if dependencies are in a different location"
    fi
}

clean_build() {
    print_step "Cleaning build artifacts..."
    
    rm -rf build/
    rm -rf dist/
    rm -rf *.egg-info
    rm -f python/kakuro_cpp*.so
    rm -f python/kakuro_cpp*.pyd
    rm -f cpp/*.o
    
    # Clean Python cache
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    
    print_success "Clean complete!"
}

run_tests() {
    print_step "Building and running tests..."
    
    # Build first
    build_cpp
    
    # Run wrapper test
    print_step "Testing wrapper..."
    python3 kakuro_wrapper.py
    
    # Run pytest if available
    if command -v pytest &> /dev/null; then
        print_step "Running pytest..."
        pytest tests/ -v
    else
        print_warning "pytest not found, skipping tests"
        echo "  Install with: pip install pytest"
    fi
}

install_package() {
    print_step "Installing package..."
    
    check_dependencies
    
    # Install in editable mode
    pip install -e .
    
    print_success "Package installed!"
    echo ""
    echo "You can now import from anywhere:"
    echo "  from kakuro_wrapper import KakuroBoard, CSPSolver"
}

build_docker() {
    print_step "Building Docker image with C++ support..."
    
    if [ ! -f Dockerfile ]; then
        print_warning "Dockerfile not found, creating one..."
        cat > Dockerfile << 'EOF'
FROM python:3.12-slim

# Install build tools
RUN apt-get update && apt-get install -y \
    cmake \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY . .

# Install Python dependencies and build C++ extension
RUN pip install --no-cache-dir pybind11 && \
    pip install --no-cache-dir -e .

# Expose FastAPI port
EXPOSE 8000

# Run FastAPI
CMD ["uvicorn", "python.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF
        print_success "Dockerfile created"
    fi
    
    docker build -t kakuro-generator:latest .
    
    print_success "Docker image built!"
    echo ""
    echo "Run with:"
    echo "  docker run -p 8000:8000 kakuro-generator:latest"
}

# Main script
case "${1:-build}" in
    build)
        build_cpp
        ;;
    clean)
        clean_build
        ;;
    test)
        run_tests
        ;;
    install)
        install_package
        ;;
    docker)
        build_docker
        ;;
    help|--help|-h)
        print_usage
        ;;
    *)
        echo "Unknown option: $1"
        print_usage
        exit 1
        ;;
esac

print_success "Done!"