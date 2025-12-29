from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
import sys
import os
import subprocess
import pathlib
import shutil
import glob

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
        
        cmake_args = [
            f'-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={extdir}',
            f'-DPYTHON_EXECUTABLE={sys.executable}',
            '-DBUILD_PYTHON_BINDINGS=ON',
        ]

        cfg = 'Debug' if self.debug else 'Release'
        build_args = ['--config', cfg]

        cmake_args += [f'-DCMAKE_BUILD_TYPE={cfg}']
        
        # Add parallel build
        build_args += ['--', '-j4']

        env = os.environ.copy()
        env['CXXFLAGS'] = f'{env.get("CXXFLAGS", "")} -DVERSION_INFO=\\"{self.distribution.get_version()}\\"'
        
        if not os.path.exists(self.build_temp):
            os.makedirs(self.build_temp)
        
        print(f"Building extension in: {self.build_temp}")
        print(f"Output directory: {extdir}")
        
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
            extdir,
            self.build_temp,
            os.path.join(self.build_temp, 'Release'),
            os.path.join(self.build_temp, 'Debug'),
        ]
        
        for search_path in search_paths:
            pattern = os.path.join(search_path, 'kakuro_cpp*.so')
            built_extensions.extend(glob.glob(pattern))
            pattern = os.path.join(search_path, 'kakuro_cpp*.pyd')
            built_extensions.extend(glob.glob(pattern))
        
        if built_extensions:
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
        
        print()  # Add empty line for cleaner output


setup(
    ext_modules=[CMakeExtension('kakuro_cpp', sourcedir='cpp')],
    cmdclass=dict(build_ext=CMakeBuild),
    zip_safe=False,
    python_requires='>=3.12',
    packages=['python', 'routes'],
    package_dir={'python': 'python', 'routes': 'routes'},
)