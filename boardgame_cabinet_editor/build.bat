@echo off
rem 사용: build.bat
rem dist\보드게임_현황판_편집기.exe 생성
cd /d "%~dp0"
python -m PyInstaller --onefile --windowed --name "보드게임_현황판_편집기" ^
  --icon "app_icon.ico" ^
  "보드게임_현황판_편집기.py" || exit /b 1
echo Output: dist\보드게임_현황판_편집기.exe
