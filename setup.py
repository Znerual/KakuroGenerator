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
    PYBIND11_AVAILABLE = True
except ImportError:
    PYBIND11_AVAILABLE = False
    print("Warning: pybind11 not installed. C++ extensions will not be built.")
    print("The package will be installed without C++ acceleration.")

class CMakeExtension(Extension):
    def __init__(self, name, sourcedir=''):
        Extension.__init__(self, name, sources=[])
        self.sourcedir = os.path.abspath(sourcedir)

class CMakeBuild(build_ext):
    def run(self):
        try:
            subprocess.check_output(['cmake', '--version'])
        except OSError:
            print("Warning: CMake not found. Skipping C++ extension build.")
            print("The package will be installed without C++ acceleration.")
            return

        # Check if pybind11 is available
        if not PYBIND11_AVAILABLE:
            print("Warning: pybind11 not available. Skipping C++ extension build.")
            return

        for ext in self.extensions:
            try:
                self.build_extension(ext)
            except Exception as e:
                print(f"Warning: Failed to build extension {ext.name}: {e}")
                print("The package will be installed without C++ acceleration.")

    def build_extension(self, ext):
        try:
            extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))
            if not os.path.exists(extdir):
                os.makedirs(extdir)
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
                "-DCMAKE_BUILD_TYPE=Release",
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
            
            print() 
        except Exception as e:
            raise RuntimeError(
                f"C++ extension build failed: {e}\n"
                "Refusing to build wheel with precompiled binaries."
            )

ext_modules = []
if PYBIND11_AVAILABLE:
    try:
        subprocess.check_output(['cmake', '--version'])
        ext_modules = [CMakeExtension('kakuro.kakuro_cpp', sourcedir='cpp')]
    except OSError:
        print("CMake not found - installing without C++ extensions")
setup(
    ext_modules=ext_modules,
    cmdclass=dict(build_ext=CMakeBuild),
    zip_safe=False,
    python_requires='>=3.12',
    packages=['kakuro'],
    package_dir={'kakuro': 'python'},
    package_data={'kakuro': ['*.so', '*.pyd', '*.dll']},
)