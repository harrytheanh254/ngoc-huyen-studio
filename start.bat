@echo off
chcp 65001 >nul 2>&1
title Ngoc Huyen Studio

echo ========================================
echo    Ngoc Huyen Studio - Piper TTS
echo ========================================
echo.

set "BASE_DIR=%~dp0"
cd /d "%BASE_DIR%"

:: Kiểm tra Python embed
if not exist "python\python.exe" (
    echo [LOI] Khong tim thay Python embed!
    echo Vui long chay setup.bat de cai dat.
    pause
    exit /b 1
)

:: Kiểm tra ffmpeg
set "FFMPEG="
if exist "ffmpeg\bin\ffmpeg.exe" set "FFMPEG=ffmpeg\bin\ffmpeg.exe"
if exist "ffmpeg\ffmpeg.exe" set "FFMPEG=ffmpeg\ffmpeg.exe"
if "%FFMPEG%"=="" (
    echo [CANH BAO] Khong tim thay ffmpeg - xuat MP3 se khong hoat dong
)

:: Set PYTHONPATH cho pipeline
set "PYTHONPATH=%BASE_DIR%pipeline;%PYTHONPATH%"

:: Chạy server
echo Dang khoi dong server...
echo.
echo Mo trinh duyet: http://127.0.0.1:5000
echo.
python\python.exe app.py

pause