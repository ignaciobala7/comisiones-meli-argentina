@echo off
chcp 65001 > nul
title Comisiones MeLi Argentina (Web App)
cd /d "%~dp0"

echo Instalando dependencias necesarias...
pip install -r requirements.txt -q --disable-pip-version-check 2>nul

echo Iniciando aplicacion...
python -m streamlit run src\web\1_Consulta_Individual.py

if errorlevel 1 (
    echo.
    echo  Error al iniciar. Presiona una tecla para cerrar.
    pause
)
