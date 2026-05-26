import requests
import time
from src.config.settings import cargar_config, guardar_config

AUTH_URL      = "https://auth.mercadolibre.com.ar/authorization"
TOKEN_URL     = "https://api.mercadolibre.com/oauth/token"

def token_vigente(cfg: dict) -> bool:
    token = cfg.get("access_token")
    expires = cfg.get("token_expires_at", 0)
    return bool(token) and time.time() < expires - 300

def renovar_token(cfg: dict) -> str:
    try:
        resp = requests.post(TOKEN_URL, data={
            "grant_type":    "refresh_token",
            "client_id":     cfg.get("client_id"),
            "client_secret": cfg.get("client_secret"),
            "refresh_token": cfg.get("refresh_token"),
        }, timeout=20)
        if resp.status_code == 200:
            d = resp.json()
            guardar_config({
                "access_token":      d["access_token"],
                "refresh_token":     d.get("refresh_token", cfg.get("refresh_token")),
                "token_expires_at":  time.time() + d.get("expires_in", 21600),
            })
            return d["access_token"]
    except Exception:
        pass
    return None

def obtener_token() -> str:
    cfg = cargar_config()
    if token_vigente(cfg):
        return cfg["access_token"]
    if cfg.get("refresh_token") and cfg.get("client_id"):
        return renovar_token(cfg)
    return None

def consultar_comision_api(precio: float, cat_id: str, tipo_id: str, token: str) -> tuple:
    """Llama al endpoint real de MeLi con el token del usuario"""
    try:
        resp = requests.get(
            "https://api.mercadolibre.com/sites/MLA/listing_prices",
            params={"price": precio, "listing_type_id": tipo_id, "category_id": cat_id},
            headers={"Authorization": f"Bearer {token}"},
            timeout=12,
        )
        if resp.status_code == 200:
            d = resp.json()
            monto = d.get("sale_fee_amount", 0)
            base  = d.get("amount", precio)
            pct   = (monto / base * 100) if base > 0 else 0
            return round(pct, 2), round(monto, 2)
    except Exception:
        pass
    return None, None
