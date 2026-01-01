from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
import sys
import os
import subprocess
import pathlib
import shutil
import glob

# Try to import pybind11 to get the exact cmake path
try:
    import pybind11
except ImportError:
    print("Error: pybind11 not installed.")
    print("Please install it via: pip install pybind11")
    sys.exit(1)

class CMakeExtension(Extension):
    def __init__(self, name, sourcedir=''):
        Extension.__init__(self, name, sources=[])
        self.sourcedir = os.path.abspath(sourcedir)

class CMakeBuild(build_ext):
    def run(self):
        try:
            subprocess.check_output(['cmake', '--version'])
        except OSError:
            raise RuntimeError(
                "CMake must be installed to build the following extensions: " +
                ", ".join(e.name for e in self.extensions)
            )

        for ext in self.extensions:
            self.build_extension(ext)

    def build_extension(self, ext):
        extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))
        
        # For in-place builds, put the extension in the python/ directory
        if self.inplace:
            extdir = os.path.abspath('python')
        
        # Get pybind11 cmake path directly from python
        pybind11_dir = pybind11.get_cmake_dir()

        # Windows-safe path handling for Python executable
        python_exe = sys.executable.replace('\\', '/')

        cmake_args = [
            f'-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={extdir}',
            f'-DPYTHON_EXECUTABLE={python_exe}',  # Legacy CMake
            f'-DPython_EXECUTABLE={python_exe}',  # Modern CMake (3.12+)
            f'-DPython3_EXECUTABLE={python_exe}', # Explicit Python 3 hint
            f'-Dpybind11_DIR={pybind11_dir}',      # Explicitly point to pybind11
            '-DBUILD_PYTHON_BINDINGS=ON',
        ]


        cfg = 'Debug' if self.debug else 'Release'
        build_args = ['--config', cfg]

        cmake_args += [f'-DCMAKE_BUILD_TYPE={cfg}']
        
        # Windows-specific configuration
        if sys.platform.startswith("win"):
            cmake_args += [f'-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_{cfg.upper()}={extdir}']
            # If using Visual Studio generator, ensure 64-bit build if Python is 64-bit
            if sys.maxsize > 2**32:
                cmake_args += ['-A', 'x64']
            
            build_args += ['--', '/m'] # Parallel build for MSVC
        else:
            build_args += ['--', '-j4'] # Parallel build for Makefiles

        env = os.environ.copy()
        env['CXXFLAGS'] = f'{env.get("CXXFLAGS", "")} -DVERSION_INFO=\\"{self.distribution.get_version()}\\"'
        
        if not os.path.exists(self.build_temp):
            os.makedirs(self.build_temp)
        
        print(f"Building extension in: {self.build_temp}")
        print(f"Output directory: {extdir}")
        print(f"Using Python: {python_exe}")
        print(f"Using Pybind11: {pybind11_dir}")
        
        # Run CMake
        subprocess.check_call(
            ['cmake', ext.sourcedir] + cmake_args, 
            cwd=self.build_temp, 
            env=env
        )
        subprocess.check_call(
            ['cmake', '--build', '.'] + build_args, 
            cwd=self.build_temp
        )
        
        # Find the built extension and copy it to the right place
        # CMake might put it in various locations depending on the system
        built_extensions = []
        
        # Common locations where CMake might put the file
        search_paths = [
            self.build_temp,
            os.path.join(self.build_temp, cfg),
            os.path.join(self.build_temp, 'Release'),
            os.path.join(self.build_temp, 'Debug'),
            extdir,
        ]

        # Look for .pyd on Windows, .so on Linux
        ext_pattern = '*.pyd' if sys.platform.startswith("win") else '*.so'
        
        for search_path in search_paths:
            pattern = os.path.join(search_path, f'kakuro_cpp{ext_pattern}')
            # Also try matching specific naming conventions like kakuro_cpp.cp312-win_amd64.pyd
            glob_results = glob.glob(pattern)
            if not glob_results:
                # Try wildcard for safety
                pattern = os.path.join(search_path, f'kakuro_cpp*{ext_pattern}')
                glob_results = glob.glob(pattern)
            
            built_extensions.extend(glob_results)
        
        if built_extensions:
            # Sort by modification time to get the freshest build
            built_extensions.sort(key=os.path.getmtime, reverse=True)
            source_file = built_extensions[0]
            
            target_dir = os.path.abspath('python')
            os.makedirs(target_dir, exist_ok=True)
            target_file = os.path.join(target_dir, os.path.basename(source_file))
            
            # Only copy if source and target are different files
            if os.path.abspath(source_file) != os.path.abspath(target_file):
                print(f"Copying {source_file} -> {target_file}")
                shutil.copy2(source_file, target_file)
            else:
                print(f"Source and target are the same: {source_file}")
        else:
            print("Warning: Could not find built extension in:")
            for path in search_paths:
                print(f"  - {path}")
        
        print() 


setup(
    ext_modules=[CMakeExtension('kakuro_cpp', sourcedir='cpp')],
    cmdclass=dict(build_ext=CMakeBuild),
    zip_safe=False,
    python_requires='>=3.12',
    packages=['python', 'routes'],
    package_dir={'python': 'python', 'routes': 'routes'},
)