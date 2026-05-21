# -*- coding: utf-8 -*-
"""
Punto de entrada de la aplicación.
"""
import sys
import os

# Asegurar que la ruta src esté en PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gui.app_window import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
