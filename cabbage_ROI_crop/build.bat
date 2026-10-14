@echo off
rem 사용: build.bat [버전]  예) build.bat 1.1.0
cd /d "%~dp0"
set VER=%1
if "%VER%"=="" set VER=0.0.0
python -m PyInstaller --noconfirm --onedir --windowed --name ROI_Cropper ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick ^
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtMultimedia --exclude-module tkinter ^
  app.py || exit /b 1
set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
"%ISCC%" /Q /DAppVersion=%VER% installer.iss || exit /b 1
echo Output: dist\ROI_Cropper_Setup_%VER%.exe
