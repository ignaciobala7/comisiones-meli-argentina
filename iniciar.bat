@echo off
chcp 65001 > nul
title Comisiones MeLi Argentina
cd /d "%~dp0"

pip install -r requirements.txt -q --disable-pip-version-check 2>nul

python -m streamlit run streamlit_app.py --server.headless false

if errorlevel 1 (
    echo.
    echo  Error al iniciar. Presiona una tecla para cerrar.
    pause
)
