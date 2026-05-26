import json
import os

# Raíz del proyecto (asumiendo que src/config/settings.py está a dos niveles de la raíz)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_FILE = os.path.join(BASE_DIR, "configuracion.json")

def cargar_config() -> dict:
    """Carga la configuración desde el archivo JSON."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def guardar_config(data: dict) -> dict:
    """Actualiza la configuración y la guarda en el archivo JSON."""
    cfg = cargar_config()
    cfg.update(data)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    return cfg
