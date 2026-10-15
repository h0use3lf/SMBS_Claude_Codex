@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/3] 패키지 설치
py -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto fail
echo [2/3] 실행 파일 빌드
py -m PyInstaller --noconfirm --onefile --windowed --name CashFlow --collect-data matplotlib --hidden-import win32com.client main.py
if errorlevel 1 goto fail
echo [3/3] 완료: dist\CashFlow.exe
pause
exit /b 0
:fail
echo 빌드 실패. Python 3.10 이상이 설치되어 있는지 확인하세요.
pause
exit /b 1
