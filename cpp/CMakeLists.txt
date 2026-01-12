cmake_minimum_required(VERSION 3.12)
project(kakuro_cpp)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# For Android NDK compatibility
if(ANDROID)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fPIC -frtti -fexceptions")
else()
    if(MSVC)
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /O2")
    else()
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O3 -fPIC")
    endif()
endif()

# Option to build Python bindings (disable for Android)
option(BUILD_PYTHON_BINDINGS "Build Python bindings with pybind11" ON)

# Core C++ library (can be used standalone or with Python)
add_library(kakuro_core STATIC
    kakuro_board.cpp
    kakuro_solver.cpp
    kakuro_difficulty.cpp
    kakuro_hybrid_uniqueness.cpp
)

target_include_directories(kakuro_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

# Python bindings (only if not building for Android)
if(BUILD_PYTHON_BINDINGS AND NOT ANDROID)
# Set policy to prefer GLUE hints (variables passed via command line)
    if(POLICY CMP0074)
        cmake_policy(SET CMP0074 NEW)
    endif()

    # Find Python and pybind11
    find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
    
    # Try to find pybind11
    find_package(pybind11 CONFIG)
    
    if(pybind11_FOUND)
        pybind11_add_module(kakuro_cpp kakuro_bindings.cpp)
        target_link_libraries(kakuro_cpp PRIVATE kakuro_core)
        
        # Set output directory to python package folder
        set_target_properties(kakuro_cpp PROPERTIES
            LIBRARY_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
        )
        
        message(STATUS "Python bindings will be built")
    else()
        message(WARNING "pybind11 not found. Python bindings will not be built.")
        message(STATUS "Install with: pip install pybind11")
    endif()
endif()

# For Android: create a shared library that can be called via JNI
if(ANDROID)
    add_library(kakuro_jni SHARED
        kakuro_board.cpp
        kakuro_solver.cpp
        kakuro_difficulty.cpp
        kakuro_hybrid_uniqueness.cpp
        kakuro_jni.cpp
    )
    
    target_link_libraries(kakuro_jni log)
    
    message(STATUS "Building for Android NDK")
endif()