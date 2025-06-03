@echo off
REM Setup script for installing Python dependencies
IF EXIST requirements.txt (
    pip install -r requirements.txt
) ELSE (
    echo requirements.txt not found
    exit /B 1
)
