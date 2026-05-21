@echo off
chcp 65001 > nul
title Comisiones MeLi Argentina

pip install pandas openpyxl requests -q --disable-pip-version-check 2>nul

python app.py

if errorlevel 1 (
    echo.
    echo  Hubo un error. Presiona una tecla para ver el detalle.
    pause
    python app.py
)
