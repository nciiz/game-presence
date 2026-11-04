@echo off
rem Builds dist\GamePresence\GamePresence.exe and adds a Desktop shortcut.
cd /d "%~dp0.."

if not exist gamepresence\app.py (
    echo Run this from the project folder: scripts\build_windows.bat
    goto fail
)

echo Installing build tools...
python -m pip install --upgrade pyinstaller pywebview requests pypresence
if errorlevel 1 goto fail

echo.
echo Building GamePresence (this takes a few minutes)...
python -m PyInstaller --noconfirm --clean --onedir --windowed --name GamePresence --icon assets\icon.ico --add-data "gamepresence\ui;gamepresence\ui" --collect-all webview --collect-all pythonnet --collect-all clr_loader --hidden-import clr run.py
if errorlevel 1 goto fail

echo.
echo Creating desktop shortcut...
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\GamePresence.lnk'); $s.TargetPath='%CD%\dist\GamePresence\GamePresence.exe'; $s.WorkingDirectory='%CD%\dist\GamePresence'; $s.Save()"

echo.
echo Done! Your app: %CD%\dist\GamePresence\GamePresence.exe
echo A shortcut was added to your Desktop.
explorer "%CD%\dist\GamePresence"
pause
exit /b 0

:fail
echo.
echo Build failed. Check the error above, or open an issue with it.
pause
exit /b 1
