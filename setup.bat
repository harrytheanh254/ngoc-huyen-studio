@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

title Ngoc Huyen Studio - Setup
color 0A

echo ============================================================
echo  Ngoc Huyen Studio - Setup Tu Dong
echo  Cai dat Piper TTS + ffmpeg + Python + Web App
echo ============================================================
echo.

:: ---- Config ----
set "INSTALL_DIR=%USERPROFILE%\NgocHuyenStudio"
set "PYTHON_URL=https://www.python.org/ftp/python/3.12.7/python-3.12.7-embed-amd64.zip"
set "FFMPEG_URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-8.1.2-essentials_build.7z"
set "PIPER_URL=https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_windows_x86_64.zip"
:: Voice model URL - can thay bang link cua LO
set "VOICE_MODEL_URL="

:: Parse arguments
for %%a in (%*) do (
    if "%%a"=="/dir" set "NEXT=DIR"
    if "%%a"=="/voice" set "NEXT=VOICE"
    if "!NEXT!"=="DIR" if not "%%a"=="/dir" set "INSTALL_DIR=%%a" & set "NEXT="
    if "!NEXT!"=="VOICE" if not "%%a"=="/voice" set "VOICE_MODEL_URL=%%a" & set "NEXT="
)

echo Thu muc cai dat: %INSTALL_DIR%
echo.

:: ---- Helper functions ----
:check_cmd
set "CMD=%~1"
where %CMD% >nul 2>&1
if %errorlevel% equ 0 (set "HAS_%CMD%=1") else (set "HAS_%CMD%=0")
goto :eof

:download
set "URL=%~1"
set "OUT=%~2"
echo    Dang tai: %URL%
curl.exe -L -o "%OUT%" "%URL%" --connect-timeout 30 --max-time 300
if %errorlevel% neq 0 (
    echo    [LOI] Tai that bai!
    exit /b 1
)
goto :eof

:extract_zip
set "ZIP=%~1"
set "DEST=%~2"
echo    Dang giai nen...
powershell -Command "Expand-Archive -Force -Path '%ZIP%' -DestinationPath '%DEST%'" >nul 2>&1
if %errorlevel% neq 0 (
    echo    [LOI] Giai nen that bai!
    exit /b 1
)
goto :eof

:extract_7z
set "ARC=%~1"
set "DEST=%~2"
echo    Dang giai nen (7z)...
if not exist "7z.exe" (
    echo    Tai 7z...
    curl.exe -L -o 7z.exe "https://www.7-zip.org/a/7zr.exe" --connect-timeout 30
)
7z.exe x "%ARC%" -o"%DEST%" -y >nul 2>&1
if %errorlevel% neq 0 (
    echo    [LOI] Giai nen that bai!
    exit /b 1
)
goto :eof

:: ---- Step 1: Kiem tra cac cong cu san co ----
echo [1/6] Kiem tra he thong...
echo.

call :check_cmd python
call :check_cmd ffmpeg
call :check_cmd curl

set "HAS_PIPER=0"
if exist "%INSTALL_DIR%\piper\piper.exe" set "HAS_PIPER=1"

echo   Python:  %HAS_python%
echo   ffmpeg:  %HAS_ffmpeg%
echo   curl:    %HAS_curl%
echo   Piper:   %HAS_PIPER%
echo.

:: ---- Step 2: Tao thu muc cai dat ----
echo [2/6] Tao thu muc cai dat...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
cd /d "%INSTALL_DIR%"
mkdir python 2>nul
mkdir ffmpeg 2>nul
mkdir piper 2>nul
mkdir pipeline 2>nul
mkdir data 2>nul
mkdir preview 2>nul
mkdir san-pham 2>nul
mkdir upload_images 2>nul
mkdir video_output 2>nul
echo   Da tao xong thu muc.
echo.

:: ---- Step 3: Cai Python embed ----
echo [3/6] Cai Python embed...
if %HAS_python% equ 1 (
    echo   Python da co san tren he thong - bo qua (van cai embed cho tu do).
)
if not exist "python\python.exe" (
    echo   Tai Python embed...
    call :download "%PYTHON_URL%" "python-embed.zip"
    call :extract_zip "python-embed.zip" "python"
    del python-embed.zip
    
    :: Tai get-pip.py
    echo   Cai pip...
    curl.exe -L -o python\get-pip.py "https://bootstrap.pypa.io/get-pip.py" --connect-timeout 30
    python\python.exe python\get-pip.py >nul 2>&1
    del python\get-pip.py
    echo   Da cai xong Python + pip.
) else (
    echo   Python embed da ton tai - bo qua.
)
echo.

:: ---- Step 4: Cai ffmpeg ----
echo [4/6] Cai ffmpeg...
if %HAS_ffmpeg% equ 1 (
    echo   ffmpeg da co san tren PATH - bo qua (van cai local cho tu do).
)
if not exist "ffmpeg\bin\ffmpeg.exe" if not exist "ffmpeg\ffmpeg.exe" (
    echo   Tai ffmpeg...
    call :download "%FFMPEG_URL%" "ffmpeg.7z"
    call :extract_7z "ffmpeg.7z" "ffmpeg"
    del ffmpeg.7z
    if exist "ffmpeg\ffmpeg-*" (
        for /d %%d in (ffmpeg\ffmpeg-*) do (
            xcopy /E /Y "%%d\*" "ffmpeg\" >nul
            rmdir /S /Q "%%d" 2>nul
        )
    )
    echo   Da cai xong ffmpeg.
) else (
    echo   ffmpeg da ton tai - bo qua.
)
echo.

:: ---- Step 5: Cai piper-tts (Python package) + Voice model ----
echo [5/6] Cai piper-tts + Voice model...
echo   Cai piper-tts (Python package)...
python\python.exe -m pip install --quiet piper-tts 2>nul
echo   Da cai piper-tts.

:: Voice model files (ngoc_huyen.onnx + .json) - can tai tu link cua LO
if not exist "piper" mkdir piper
if not exist "piper\ngoc_huyen.onnx" (
    echo   Can voice model ngoc_huyen.onnx + .json (~60MB)
    if "%VOICE_MODEL_URL%"=="" (
        echo   [CANH BAO] Chua co link voice model!
        echo   Hay chay lai voi: setup.bat /voice "https://link-voice-model.onnx"
        echo   Ho copy thu cong 2 file vao thu muc piper\
        pause
    ) else (
        echo   Tai voice model...
        call :download "%VOICE_MODEL_URL%" "piper\ngoc_huyen.onnx"
        call :download "%VOICE_MODEL_URL%.json" "piper\ngoc_huyen.onnx.json" 2>nul
        echo   Da tai xong voice model.
    )
) else (
    echo   Voice model da ton tai - bo qua.
)
echo.

:: ---- Step 6: Cai pip packages + Copy app ----
echo [6/6] Cai thu vien Python + Copy app...
echo.

:: Cai Flask + dependencies
python\python.exe -m pip install --quiet flask flask-cors 2>nul
echo   Da cai Flask.

:: Copy pipeline code
echo   Copy pipeline code...
xcopy /E /Y /Q "%~dp0pipeline\*" "pipeline\" >nul
echo   Da copy pipeline.

:: Copy web app
echo   Copy web app...
if exist "%~dp0app.py" copy /Y "%~dp0app.py" . >nul
if exist "%~dp0templates" xcopy /E /Y /Q "%~dp0templates\" "templates\" >nul
if exist "%~dp0static" xcopy /E /Y /Q "%~dp0static\" "static\" >nul
echo   Da copy web app.

:: Copy data (loanwords fresh)
echo   Khoi tao kho tu...
if not exist "data\loanwords_dynamic.json" echo {} > data\loanwords_dynamic.json
echo   Da khoi tao.

:: Copy start.bat
copy /Y "%~dp0start.bat" . >nul

:: Tao shortcut tren Desktop
echo.
echo [+] Tao shortcut Desktop...
powershell -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%USERPROFILE%\Desktop\Ngoc Huyen Studio.lnk'); ^
   $s.TargetPath='%INSTALL_DIR%\start.bat'; ^
   $s.WorkingDirectory='%INSTALL_DIR%'; ^
   $s.IconLocation='%INSTALL_DIR%\python\python.exe,0'; ^
   $s.Save()" 2>nul
echo   Da tao shortcut.

echo.
echo ============================================================
echo  SETUP HOAN TAT!
echo ============================================================
echo.
echo  Thu muc cai dat: %INSTALL_DIR%
echo  Chay:            start.bat (hoai click shortcut tren Desktop)
echo  Web:             http://127.0.0.1:5000
echo.
echo  Cau truc thu muc:
echo    %INSTALL_DIR%\
echo    |-- python\        (Python embed + pip)
echo    |-- ffmpeg\        (ffmpeg binaries)
echo    |-- piper\         (piper.exe + ngoc_huyen.onnx)
echo    |-- pipeline\      (ma nguon TTS)
echo    |-- app.py         (Flask server)
echo    |-- templates\     (HTML)
echo    |-- static\        (CSS/JS)
echo    |-- data\          (loanwords_dynamic.json)
echo    |-- preview\       (audio tam - tu xoa >15 ngay)
echo    |-- san-pham\      (audio da luu)
echo    |-- upload_images\ (anh upload video)
echo    |-- video_output\  (video da render)
echo    |-- start.bat      (launcher)
echo.
pause