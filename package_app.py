import subprocess
import sys
import os
import shutil

def package():
    print("--- Starting KakuroGenerator Packaging ---")

    # 1. Ensure PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 2. Define paths
    main_script = "main.py"
    static_folder = "static"
    output_name = "KakuroGenerator"

    if not os.path.exists(main_script):
        print(f"Error: {main_script} not found in current directory.")
        return

    # 3. Build command
    # --onefile: Create a single executable
    # --add-data: Bundle the static folder
    # --name: Name of the output executable
    # --windowed: (Optional) Don't show console on Windows (use only if no terminal output is needed)
    
    # On Windows, add-data separator is ';'
    # On Linux/macOS, add-data separator is ':'
    separator = ";" if os.name == 'nt' else ":"
    
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        f"--add-data={static_folder}{separator}{static_folder}",
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.lifespan",
        "--hidden-import=uvicorn.lifespan.on",
        "--hidden-import=pydantic",
        "--name", output_name,
        main_script
    ]

    print(f"Running command: {' '.join(cmd)}")
    try:
        subprocess.check_call(cmd)
        print("\n--- Packaging Successful! ---")
        print(f"The executable can be found in the 'dist' folder as '{output_name}.exe' (on Windows).")
    except subprocess.CalledProcessError as e:
        print(f"\n--- Packaging Failed ---")
        print(e)

if __name__ == "__main__":
    package()
