@echo off
echo Cleaning old build files...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "MediaProcessor.spec" del /q "MediaProcessor.spec"

echo Building Media Processor...

REM Activate virtual environment and use explicit python commands
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    python -m pip install pyinstaller
    python -m PyInstaller --name "MediaProcessor" --onefile --windowed --noconfirm app.py
) else (
    pip install pyinstaller
    pyinstaller --name "MediaProcessor" --onefile --windowed --noconfirm app.py
)

echo Build complete! The executable is located in the "dist" folder.
pause

