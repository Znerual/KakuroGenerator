# Simple Makefile for testing the C++ code without Python bindings

CXX = g++
CXXFLAGS = -std=c++17 -O2 -Wall -Wextra
LDFLAGS = 

# Source files
SOURCES = kakuro_board.cpp kakuro_solver.cpp
OBJECTS = $(SOURCES:.cpp=.o)
TEST_SRC = test_kakuro.cpp
TEST_BIN = test_kakuro

# Default target
all: $(TEST_BIN)

# Build test executable
$(TEST_BIN): $(OBJECTS) $(TEST_SRC)
	$(CXX) $(CXXFLAGS) $(OBJECTS) $(TEST_SRC) -o $(TEST_BIN) $(LDFLAGS)

# Compile object files
%.o: %.cpp kakuro_cpp.h
	$(CXX) $(CXXFLAGS) -c $< -o $@

# Run tests
test: $(TEST_BIN)
	./$(TEST_BIN)

# Clean build artifacts
clean:
	rm -f $(OBJECTS) $(TEST_BIN)

.PHONY: all test clean