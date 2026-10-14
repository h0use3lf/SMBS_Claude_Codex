@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --name ROI_Cropper ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick ^
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtMultimedia --exclude-module tkinter ^
  app.py
echo Output: dist\ROI_Cropper.exe
