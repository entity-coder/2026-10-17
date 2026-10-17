@echo off
REM ============================================================
REM  RepairDesk - one-click Windows build
REM  Run this ONCE on the shop PC (Windows 10/11, Python 3.10+ installed
REM  from python.org with "Add python.exe to PATH" ticked).
REM  It installs the needed packages and compiles RepairDesk.exe.
REM  After this, the shop PC never needs Python again - just run
REM  dist\RepairDesk.exe.
REM  NOTE: a Windows .exe can only be built on Windows. This script
REM  will NOT work on Linux or Mac.
REM ============================================================
cd /d "%~dp0"

echo Installing dependencies...
python -m pip install --upgrade pip
python -m pip install customtkinter pyinstaller reportlab
if errorlevel 1 (
    echo.
    echo ERROR: pip install failed. Check your internet connection and
    echo that Python was installed with "Add python.exe to PATH" ticked.
    pause
    exit /b 1
)

echo.
echo Building RepairDesk.exe (this takes a few minutes)...
pyinstaller --noconfirm --onefile --windowed --name RepairDesk main.py
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed. See the output above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Done! Your app is at:  dist\RepairDesk.exe
echo  Copy RepairDesk.exe to the shop PC Desktop and double-click it.
echo  Your data lives in the "repairdesk_data" folder next to the .exe -
echo  keep that folder with the .exe, and back it up regularly from
echo  inside the app (Backup screen).
echo ============================================================
pause
