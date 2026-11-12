@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ===========================================
echo  Image Stylizer 1.0 - Compilation Windows
echo ===========================================
echo.

if not exist ".venv_build\Scripts\python.exe" (
    echo [1/3] Creation de l'environnement Python 3.12...
    py -3.12 -m venv ".venv_build" 2>nul
    if errorlevel 1 (
        echo Python 3.12 via py indisponible, tentative avec python...
        python -m venv ".venv_build"
    )
)

if not exist ".venv_build\Scripts\python.exe" (
    echo ERREUR: Impossible de creer l'environnement Python.
    goto fail
)

set "PY=%CD%\.venv_build\Scripts\python.exe"

echo [2/3] Installation des dependances de compilation...
"%PY%" -m pip install --upgrade pip
if errorlevel 1 goto fail
"%PY%" -m pip install -r "requirements_build.txt"
if errorlevel 1 goto fail

if not exist "assets\image_stylizer.ico" (
    echo ERREUR: L'icone assets\image_stylizer.ico est introuvable.
    goto fail
)

echo [3/3] Compilation PyInstaller...
"%PY%" -m PyInstaller --noconfirm --clean --onedir --windowed ^
    --name "Image Stylizer" ^
    --icon "assets\image_stylizer.ico" ^
    --add-data "assets\image_stylizer.ico;assets" ^
    --distpath "dist" ^
    --workpath "build\onedir" ^
    --specpath "." ^
    "main.py"

if errorlevel 1 goto fail

echo.
echo ===========================================
echo  COMPILATION REUSSIE
echo  Exe: dist\Image Stylizer\Image Stylizer.exe
echo ===========================================
echo.
pause
exit /b 0
:fail
echo.
echo La compilation a echoue. Consulte le message ci-dessus.
pause
exit /b 1
