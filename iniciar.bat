@echo off
chcp 65001 > nul
title Comisiones MeLi Argentina (Web App)

echo Instalando dependencias necesarias...
pip install -r requirements.txt -q --disable-pip-version-check 2>nul

echo Iniciando aplicacion...
python -m streamlit run src\web\1_Consulta_Individual.py

if errorlevel 1 (
    echo.
    echo  Hubo un error. Presiona una tecla para ver el detalle.
    pause
    python -m streamlit run src\web\1_Consulta_Individual.py
)
