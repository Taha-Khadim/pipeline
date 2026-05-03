@echo off
REM Build a Windows installer for Lumora Code — Client Pipeline.
REM
REM Run this from the project root inside a Windows venv that has
REM the project deps + pyinstaller installed.
REM
REM Output:
REM   build\dist\lumora-pipeline-setup.exe   (Inno Setup installer)
REM   build\dist-pyinstaller\lumora-pipeline\  (PyInstaller bundle)

setlocal enabledelayedexpansion

set ROOT=%~dp0..
pushd "%ROOT%"

if not exist venv (
  echo venv not found. Create one with:
  echo   python -m venv venv
  echo   venv\Scripts\activate
  echo   pip install -r requirements.txt pyinstaller
  exit /b 1
)
call venv\Scripts\activate.bat

echo ==^> Updating build deps
pip install --quiet --upgrade pip
pip install --quiet --upgrade pyinstaller

echo ==^> Running PyInstaller
rmdir /s /q build\dist-pyinstaller 2>nul
rmdir /s /q build\build 2>nul
rmdir /s /q dist 2>nul
pyinstaller lumora.spec --noconfirm --distpath build\dist-pyinstaller --workpath build\build || exit /b 1

echo ==^> Bundling Playwright Chromium
set BUNDLE=build\dist-pyinstaller\lumora-pipeline
if not exist "%BUNDLE%" (
  echo PyInstaller bundle missing at %BUNDLE%
  exit /b 1
)
set PLAYWRIGHT_BROWSERS_PATH=%CD%\%BUNDLE%\ms-playwright
mkdir "%PLAYWRIGHT_BROWSERS_PATH%" 2>nul
python -m playwright install chromium || exit /b 1

echo ==^> Building installer with Inno Setup
where iscc >nul 2>nul
if errorlevel 1 (
  echo.
  echo Inno Setup not found ^(iscc.exe not on PATH^).
  echo Install from https://jrsoftware.org/isinfo.php and re-run.
  echo The PyInstaller bundle is ready at:
  echo    %BUNDLE%
  exit /b 0
)
mkdir build\dist 2>nul
iscc build\installer.iss || exit /b 1

echo.
echo Built: build\dist\lumora-pipeline-setup.exe
popd
endlocal
