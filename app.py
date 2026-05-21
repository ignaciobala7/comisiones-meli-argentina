# -*- coding: utf-8 -*-
"""
COMISIONES MERCADO LIBRE ARGENTINA
Aplicacion grafica con conexion a la API oficial de MeLi
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import webbrowser
import http.server
import urllib.parse
import requests
import json
import os
import sys
import io
import time
from datetime import datetime

# UTF-8 en consola de Windows
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import consulta_comisiones as backend

# ============================================================
# CONSTANTES
# ============================================================

DIR           = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE   = os.path.join(DIR, "configuracion.json")
REDIRECT_PORT = 8888
REDIRECT_URI  = f"http://localhost:{REDIRECT_PORT}"
AUTH_URL      = "https://auth.mercadolibre.com.ar/authorization"
TOKEN_URL     = "https://api.mercadolibre.com/oauth/token"

# ============================================================
# GESTION DE CONFIGURACION Y TOKEN
# ============================================================

def cargar_config():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def guardar_config(data):
    cfg = cargar_config()
    cfg.update(data)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    return cfg

def token_vigente(cfg):
    token = cfg.get("access_token")
    expires = cfg.get("token_expires_at", 0)
    return bool(token) and time.time() < expires - 300

def renovar_token(cfg):
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

def obtener_token():
    cfg = cargar_config()
    if token_vigente(cfg):
        return cfg["access_token"]
    if cfg.get("refresh_token") and cfg.get("client_id"):
        return renovar_token(cfg)
    return None

# ============================================================
# API MELI CON AUTENTICACION
# ============================================================

def consultar_comision_api(precio, cat_id, tipo_id, token):
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

def fallback_tabla(cat_raiz, tipo_nombre, precio):
    """Calcula comision desde la tabla local si la API no responde"""
    tasas = backend.obtener_comision(cat_raiz)
    pct   = tasas.get(tipo_nombre, backend.TABLA.get("_default", {}).get(tipo_nombre, 14.0))
    fee   = round(precio * pct / 100, 2)
    return pct, fee

# ============================================================
# OAUTH2 — CAPTURA DE CODIGO
# ============================================================

_oauth_code   = None
_oauth_server = None

class _OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global _oauth_code
        params     = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _oauth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        cuerpo = (
            "<html><body style='font-family:Arial;text-align:center;margin-top:80px'>"
            "<h2 style='color:green'>✓ Autorización recibida correctamente</h2>"
            "<p>Podes cerrar esta ventana y volver a la aplicación.</p>"
            "</body></html>"
            if _oauth_code else
            "<html><body style='font-family:Arial;text-align:center;margin-top:80px'>"
            "<h2 style='color:red'>Error: No se recibió el código de autorización.</h2>"
            "</body></html>"
        )
        self.wfile.write(cuerpo.encode())
    def log_message(self, *a): pass

def _iniciar_servidor_oauth():
    global _oauth_code, _oauth_server
    _oauth_code = None
    try:
        _oauth_server = http.server.HTTPServer(("localhost", REDIRECT_PORT), _OAuthHandler)
        t = threading.Thread(target=_oauth_server.handle_request, daemon=True)
        t.start()
        return t
    except Exception:
        return None

def _intercambiar_code(client_id, secret, code):
    try:
        resp = requests.post(TOKEN_URL, data={
            "grant_type":    "authorization_code",
            "client_id":     client_id,
            "client_secret": secret,
            "code":          code,
            "redirect_uri":  REDIRECT_URI,
        }, timeout=20)
        return resp.json() if resp.status_code == 200 else None
    except Exception:
        return None

# ============================================================
# COLORES Y ESTILOS
# ============================================================

# ── Paleta moderna ────────────────────────────────────────────
BG      = "#F1F5F9"    # slate-100  fondo general
CARD    = "#FFFFFF"    # blanco     paneles/cards
HDR     = "#0F172A"    # slate-950  header oscuro
HDR2    = "#1E293B"    # slate-800  cabeceras tabla

BLUE    = "#3B82F6"    # blue-500   botones principales
BLUE_D  = "#1D4ED8"    # blue-700   hover
GREEN   = "#059669"    # emerald-600 positivo / ANALIZAR
GREEN_D = "#047857"    # emerald-700 hover
AMBER   = "#D97706"    # amber-600  advertencia
RED     = "#DC2626"    # red-600    error

TX1     = "#0F172A"    # slate-950  texto principal
TX2     = "#475569"    # slate-600  texto secundario
TX3     = "#94A3B8"    # slate-400  texto muted
BORD    = "#CBD5E1"    # slate-300  bordes

# Aliases legado (usan todo el código existente)
C1  = HDR
C2  = BLUE
C3  = GREEN
CF  = BG
CW  = CARD

# ── Tipografía ────────────────────────────────────────────────
_FF = "Segoe UI"   # disponible en Windows 10/11
FONT_TIT  = (_FF, 14, "bold")
FONT_H    = (_FF, 10, "bold")
FONT_N    = (_FF, 10)
FONT_S    = (_FF, 9)
FONT_BIG  = (_FF, 12, "bold")
FONT_MONO = ("Consolas", 9)

def _darken(hex_color, pct=0.80):
    """Oscurece un color hex en pct (0-1)."""
    r = max(0, int(int(hex_color[1:3], 16) * pct))
    g = max(0, int(int(hex_color[3:5], 16) * pct))
    b = max(0, int(int(hex_color[5:7], 16) * pct))
    return f"#{r:02x}{g:02x}{b:02x}"

def _btn(parent, text, command, bg=None, **kw):
    if bg is None: bg = BLUE
    hover = _darken(bg)
    kw.setdefault("padx", 14)
    kw.setdefault("pady", 7)
    kw.setdefault("font", FONT_H)
    b = tk.Button(parent, text=text, command=command,
                  bg=bg, fg="white", relief=tk.FLAT, cursor="hand2",
                  activebackground=hover, activeforeground="white",
                  bd=0, highlightthickness=0, **kw)
    b.bind("<Enter>", lambda e, _b=b, _h=hover: _b.config(bg=_h))
    b.bind("<Leave>", lambda e, _b=b, _c=bg:    _b.config(bg=_c))
    return b

def _lbl(parent, text, font=FONT_N, fg=TX1, bg=BG, **kw):
    return tk.Label(parent, text=text, font=font, fg=fg, bg=bg, **kw)

def _card(parent, title="", **kw):
    """Devuelve (outer_frame, inner_frame) con estilo card/panel."""
    outer = tk.Frame(parent, bg=BORD, padx=1, pady=1, **kw)
    inner = tk.LabelFrame(outer, text=f"  {title}  " if title else "",
                          bg=CARD, fg=TX2, font=FONT_S,
                          relief=tk.FLAT, bd=0, padx=12, pady=8)
    inner.pack(fill=tk.BOTH, expand=True)
    return outer, inner

# ============================================================
# DIALOGO: CONFIGURACION API
# ============================================================

class DialogConfig(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent   = parent
        self.title("Configurar API de Mercado Libre")
        self.geometry("620x660")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.grab_set()
        self._build()

    def _build(self):
        # Header oscuro con acento
        hdr = tk.Frame(self, bg=HDR)
        hdr.pack(fill=tk.X)
        tk.Frame(hdr, bg=AMBER, width=5).pack(side=tk.LEFT, fill=tk.Y)
        _lbl(hdr, "  Conectar con la API de Mercado Libre",
             FONT_TIT, fg="white", bg=HDR, pady=14).pack(side=tk.LEFT)

        # Pasos
        fr_steps = tk.LabelFrame(self,
            text=" Cómo obtener tus credenciales (solo la primera vez) ",
            font=FONT_H, fg=TX2, bg=CARD, padx=14, pady=10, relief=tk.FLAT)
        fr_steps.pack(fill=tk.X, padx=15, pady=12)

        pasos = [
            "1.  Ir al portal de desarrolladores de MeLi  (botón abajo)",
            "2.  Iniciar sesión con TU cuenta de MeLi",
            "3.  Hacer click en  'Crear aplicación'",
            "4.  Nombre y descripción: cualquiera  (ej: 'Mi Stock')",
            "5.  En  'URIs de redirección'  escribir exactamente:   http://localhost:8888",
            "6.  Guardar  →  copiar el  'App ID'  y  'Secret Key'  que aparecen",
            "7.  Pegar los dos valores abajo y hacer click en  'Conectar cuenta MeLi'",
        ]
        for p in pasos:
            _lbl(fr_steps, p, FONT_S, fg=TX2, bg=CARD, anchor=tk.W, justify=tk.LEFT).pack(
                anchor=tk.W, pady=1)

        _btn(fr_steps, "  Abrir portal de desarrolladores MeLi  ",
             lambda: webbrowser.open("https://developers.mercadolibre.com.ar/apps/"),
             bg=BLUE, padx=14, pady=5).pack(anchor=tk.W, pady=(10, 0))

        # Campos
        fr_creds = tk.LabelFrame(self,
            text=" Credenciales de tu app MeLi ",
            font=FONT_H, fg=TX2, bg=CARD, padx=14, pady=10, relief=tk.FLAT)
        fr_creds.pack(fill=tk.X, padx=15, pady=5)
        fr_creds.columnconfigure(1, weight=1)

        cfg = cargar_config()
        _lbl(fr_creds, "Client ID  (App ID):", fg=TX2, bg=CARD).grid(
            row=0, column=0, sticky=tk.W, pady=6, padx=(0, 10))
        self.var_cid = tk.StringVar(value=cfg.get("client_id", ""))
        ttk.Entry(fr_creds, textvariable=self.var_cid,
                  font=FONT_N, width=36).grid(row=0, column=1, sticky=tk.EW)

        _lbl(fr_creds, "Client Secret:", fg=TX2, bg=CARD).grid(
            row=1, column=0, sticky=tk.W, pady=6, padx=(0, 10))
        self.var_sec = tk.StringVar(value=cfg.get("client_secret", ""))
        ttk.Entry(fr_creds, textvariable=self.var_sec,
                  font=FONT_N, width=36, show="•").grid(row=1, column=1, sticky=tk.EW)

        # Estado
        self.lbl_estado = _lbl(self, "", FONT_N, bg=BG)
        self.lbl_estado.pack(padx=20, pady=4, anchor=tk.W)
        self._actualizar_lbl_estado()

        # Botones
        fr_btns = tk.Frame(self, bg=BG)
        fr_btns.pack(pady=12)

        _btn(fr_btns, "  Conectar cuenta MeLi  ",
             self._conectar, bg=GREEN, padx=16, pady=9).pack(side=tk.LEFT, padx=8)
        _btn(fr_btns, "  Guardar y cerrar  ",
             self._guardar_cerrar, bg=BLUE, padx=16, pady=9).pack(side=tk.LEFT, padx=8)
        _btn(fr_btns, "Cancelar",
             self.destroy, bg=TX3, padx=16, pady=9).pack(side=tk.LEFT, padx=8)

    def _actualizar_lbl_estado(self):
        token = obtener_token()
        if token:
            self.lbl_estado.config(
                text="✓  Conectado — token vigente, comisiones en tiempo real",
                fg="#155724")
        elif cargar_config().get("access_token"):
            self.lbl_estado.config(
                text="⚠  Token expirado — hacé click en 'Conectar cuenta MeLi' para renovar",
                fg="#856404")
        else:
            self.lbl_estado.config(
                text="○  Sin conexión — ingresá las credenciales y conectá",
                fg="#721C24")

    def _guardar_cerrar(self):
        cid = self.var_cid.get().strip()
        sec = self.var_sec.get().strip()
        if cid:
            guardar_config({"client_id": cid, "client_secret": sec})
        self.parent._actualizar_estado_barra()
        self.destroy()

    def _conectar(self):
        cid = self.var_cid.get().strip()
        sec = self.var_sec.get().strip()
        if not cid or not sec:
            messagebox.showwarning("Falta info",
                "Ingresá el Client ID y el Client Secret antes de conectar.", parent=self)
            return

        guardar_config({"client_id": cid, "client_secret": sec})

        self.lbl_estado.config(text="Iniciando servidor local...", fg=BLUE)
        self.update_idletasks()

        hilo = _iniciar_servidor_oauth()
        if not hilo:
            messagebox.showerror("Error",
                "No se pudo iniciar el servidor en el puerto 8888.\n"
                "Verificá que ningún otro programa lo esté usando.", parent=self)
            return

        url = f"{AUTH_URL}?response_type=code&client_id={cid}&redirect_uri={REDIRECT_URI}"
        webbrowser.open(url)

        self.lbl_estado.config(
            text="Esperando que autorices en el navegador...  (tenés 2 minutos)",
            fg=AMBER)
        self.update_idletasks()

        def esperar():
            hilo.join(timeout=120)
            self.after(0, self._finalizar_oauth, cid, sec)

        threading.Thread(target=esperar, daemon=True).start()

    def _finalizar_oauth(self, cid, sec):
        global _oauth_code
        if not _oauth_code:
            self.lbl_estado.config(
                text="No se recibió autorización. Intentá de nuevo.", fg="#CC0000")
            return

        self.lbl_estado.config(text="Obteniendo token...", fg=BLUE)
        self.update_idletasks()

        data = _intercambiar_code(cid, sec, _oauth_code)
        _oauth_code = None

        if not data or "access_token" not in data:
            self.lbl_estado.config(
                text=f"Error al obtener token. Verificá las credenciales.",
                fg="#CC0000")
            return

        guardar_config({
            "access_token":     data["access_token"],
            "refresh_token":    data.get("refresh_token"),
            "token_expires_at": time.time() + data.get("expires_in", 21600),
            "user_id":          data.get("user_id"),
        })

        self.parent._actualizar_estado_barra()
        self.lbl_estado.config(
            text=f"✓  Conectado correctamente!  (User ID: {data.get('user_id')})",
            fg="#155724")
        messagebox.showinfo("¡Conectado!",
            "Conexión con Mercado Libre establecida.\n"
            "Las comisiones ahora se consultan en tiempo real desde la API oficial.",
            parent=self)

# ============================================================
# PESTAÑA: CONSULTA INDIVIDUAL
# ============================================================

class TabConsulta(ttk.Frame):
    def __init__(self, nb, app_ref):
        super().__init__(nb)
        self.app = app_ref
        self.configure(style="TFrame")
        self._cats = []
        self._build()

    def _build(self):
        # ── Sección búsqueda ──
        fr1 = tk.LabelFrame(self, text=" 1.  Buscar producto ",
                            font=FONT_H, fg=TX2, bg=CARD,
                            padx=12, pady=10, relief=tk.FLAT)
        fr1.pack(fill=tk.X, padx=15, pady=(12, 6))
        fr1.columnconfigure(0, weight=1)

        _lbl(fr1, "Escribí el nombre del producto:", fg=TX2, bg=CARD).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))

        fr_row = tk.Frame(fr1, bg=CARD)
        fr_row.grid(row=1, column=0, sticky=tk.EW)
        fr_row.columnconfigure(0, weight=1)

        self.var_q = tk.StringVar()
        ent = ttk.Entry(fr_row, textvariable=self.var_q, font=(_FF, 11))
        ent.grid(row=0, column=0, sticky=tk.EW, padx=(0, 8))
        ent.bind("<Return>", lambda _: self._buscar())

        _btn(fr_row, "Buscar en MeLi", self._buscar, bg=BLUE).grid(row=0, column=1)

        _lbl(fr1, "Categoría de MeLi:", fg=TX2, bg=CARD).grid(
            row=2, column=0, sticky=tk.W, pady=(10, 2))

        self.var_cat = tk.StringVar()
        self.combo = ttk.Combobox(fr1, textvariable=self.var_cat,
                                  font=FONT_N, state="readonly", width=62)
        self.combo.grid(row=3, column=0, sticky=tk.EW, pady=(0, 4))
        self.combo.bind("<<ComboboxSelected>>", self._on_cat)

        self.lbl_cat_info = _lbl(fr1,
            "Escribí un producto y hacé click en 'Buscar en MeLi'",
            FONT_S, fg=TX3, bg=CARD)
        self.lbl_cat_info.grid(row=4, column=0, sticky=tk.W)

        # ── Sección precios ──
        fr2 = tk.LabelFrame(self, text=" 2.  Ingresar precios ",
                            font=FONT_H, fg=TX2, bg=CARD,
                            padx=12, pady=10, relief=tk.FLAT)
        fr2.pack(fill=tk.X, padx=15, pady=6)

        def campo(row, label, attr, default=""):
            _lbl(fr2, label, fg=TX2, bg=CARD).grid(row=row, column=0, sticky=tk.W,
                                          padx=(0, 12), pady=5)
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            ent = ttk.Entry(fr2, textvariable=var, font=(_FF, 11), width=20)
            ent.grid(row=row, column=1, sticky=tk.W, pady=5)

        campo(0, "Precio de venta ($):", "var_precio")
        campo(1, "Costo neto ($):",      "var_costo")
        campo(2, "Margen objetivo (%):", "var_margen", "20")

        _lbl(fr2,
             "Si tenés el costo pero no el precio → dejá Precio en blanco y calculamos el precio a publicar",
             FONT_S, fg=TX3, bg=CARD).grid(row=3, column=0, columnspan=2, sticky=tk.W)

        # ── Botones ──
        fr_btns = tk.Frame(self, bg=BG)
        fr_btns.pack(pady=(6, 8))
        _btn(fr_btns, "  CALCULAR COMISIONES  ", self._calcular,
             bg=GREEN, padx=22, pady=11, font=FONT_BIG).pack(side=tk.LEFT, padx=(0, 10))
        _btn(fr_btns, "  Nueva consulta  ", self._limpiar,
             bg=TX3, padx=14, pady=11, font=FONT_BIG).pack(side=tk.LEFT)

        # ── Resultados ──
        self.fr_result = tk.Frame(self, bg=BG)
        self.fr_result.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 12))

    # ── Acciones ──

    def _buscar(self):
        q = self.var_q.get().strip()
        if not q:
            messagebox.showwarning("Falta info", "Escribí el nombre del producto primero.")
            return
        self.lbl_cat_info.config(text="Buscando en MeLi...", fg=BLUE)
        self.update_idletasks()

        def run():
            cats = backend.buscar_categoria(q, 8)
            self.after(0, self._mostrar_cats, cats, q)

        threading.Thread(target=run, daemon=True).start()

    def _mostrar_cats(self, cats, q):
        self._cats = cats
        if not cats:
            self.lbl_cat_info.config(
                text=f"No se encontraron categorías para '{q}'. Probá otro término.",
                fg="#CC0000")
            self.combo["values"] = []
            return

        opciones = []
        for c in cats:
            dom = c.get("domain_name", "")
            nom = c.get("category_name", "")
            cid = c.get("category_id", "")
            lbl = f"{dom} > {nom}" if dom and nom and dom != nom else (dom or nom)
            opciones.append(f"{lbl}  ({cid})")

        self.combo["values"] = opciones
        self.combo.current(0)
        self._on_cat(None)
        self.lbl_cat_info.config(
            text=f"Se encontraron {len(cats)} categorías. Verificá que sea la correcta.",
            fg="#155724")

    def _on_cat(self, _):
        idx = self.combo.current()
        if 0 <= idx < len(self._cats):
            cid = self._cats[idx].get("category_id", "")
            self.lbl_cat_info.config(
                text=f"ID: {cid}  —  obteniendo tasas...", fg=BLUE)
            self.update_idletasks()

            def run():
                raiz  = backend.obtener_raiz_categoria(cid)
                tasas = backend.obtener_comision(raiz)
                txt = (f"ID: {cid}  |  Categoría raíz: {raiz}  |  "
                       f"Tasas tabla: Clásica {tasas.get('Clasica','?')}%  /  "
                       f"Premium {tasas.get('Premium','?')}%")
                self.after(0, lambda: self.lbl_cat_info.config(text=txt, fg="#155724"))

            threading.Thread(target=run, daemon=True).start()

    def _calcular(self):
        idx = self.combo.current()
        if idx < 0 or not self._cats:
            messagebox.showwarning("Falta info",
                "Primero buscá y seleccioná una categoría.")
            return

        precio = None
        sp = self.var_precio.get().strip().replace(",", ".").replace("$", "").replace(" ", "")
        if sp:
            try:
                precio = float(sp)
                if precio <= 0: raise ValueError
            except ValueError:
                messagebox.showwarning("Precio inválido", "El precio ingresado no es válido.")
                return

        costo = None
        sc = self.var_costo.get().strip().replace(",", ".").replace("$", "")
        if sc:
            try:
                costo = float(sc)
                if costo <= 0: raise ValueError
            except ValueError:
                messagebox.showwarning("Costo inválido", "El costo no es un número válido.")
                return

        if precio is None and costo is None:
            messagebox.showwarning("Falta info",
                "Ingresá al menos el Precio de venta o el Costo neto.")
            return

        try:
            margen_obj = float(self.var_margen.get().replace("%", ""))
        except ValueError:
            margen_obj = 20

        cat    = self._cats[idx]
        cat_id  = cat.get("category_id")
        cat_nom = cat.get("domain_name") or cat.get("category_name", cat_id)

        def run():
            cat_raiz = backend.obtener_raiz_categoria(cat_id)
            token    = self.app.token_activo()
            via_api  = False
            res = {}

            for tipo_nom, tipo_id in backend.TIPOS_PUBLICACION.items():
                pct, fee = None, None

                # Precio de referencia: si no hay precio ingresado usamos el sugerido provisorio
                precio_ref = precio if precio else backend.calcular_precio_sugerido(
                    costo, 15.5, margen_obj)  # estimación inicial para pedir a API

                if token:
                    pct, fee = consultar_comision_api(precio_ref, cat_id, tipo_id, token)
                    if pct is None:
                        nuevo = renovar_token(cargar_config())
                        if nuevo:
                            self.app._token = nuevo
                            pct, fee = consultar_comision_api(precio_ref, cat_id, tipo_id, nuevo)
                    if pct is not None:
                        via_api = True

                if pct is None:
                    pct, fee = fallback_tabla(cat_raiz, tipo_nom, precio_ref)

                d = {"pct": pct}

                if precio:
                    # Modo análisis: tengo precio → calculo comisión y margen
                    fee_real = precio * pct / 100
                    neto = precio - fee_real
                    d.update({"fee": fee_real, "neto": neto})
                    if costo:
                        gan = neto - costo
                        mg  = gan / precio * 100
                        sug = backend.calcular_precio_sugerido(costo, pct, margen_obj)
                        d.update({"ganancia": gan, "margen": mg, "precio_sug": sug})
                else:
                    # Modo inverso: solo tengo costo → calculo precio sugerido
                    sug = backend.calcular_precio_sugerido(costo, pct, margen_obj)
                    fee_sug = sug * pct / 100
                    neto_sug = sug - fee_sug
                    gan_sug  = neto_sug - costo
                    d.update({
                        "modo_inverso": True,
                        "precio_sug": sug,
                        "fee": fee_sug,
                        "neto": neto_sug,
                        "ganancia": gan_sug,
                    })

                res[tipo_nom] = d

            self.after(0, self._mostrar_resultado,
                       cat_nom, cat_raiz, precio, costo, margen_obj, res, via_api)

        threading.Thread(target=run, daemon=True).start()

    def _mostrar_resultado(self, cat_nom, cat_raiz, precio, costo, margen_obj, res, via_api):
        for w in self.fr_result.winfo_children():
            w.destroy()

        fuente = "API en tiempo real  ✓" if via_api else "tabla local  (configurar API para datos exactos)"
        tk.Label(self.fr_result,
                 text=f"  Categoría: {cat_nom}   |   Raíz: {cat_raiz}   |   Fuente: {fuente}  ",
                 bg="#EFF6FF", fg=BLUE_D, font=FONT_S, pady=6,
                 anchor=tk.W).pack(fill=tk.X, pady=(0, 8))

        colores = {
            "Clasica": (HDR2,  "#F8FAFC", "#EFF6FF"),
            "Premium": (GREEN, "#F0FDF4", "#DCFCE7"),
        }

        for tipo_nom, d in res.items():
            col_osc, col_cl, _col_hdr_bg = colores.get(tipo_nom, (HDR2, CARD, BG))

            fr = tk.Frame(self.fr_result, bg=BORD, padx=1, pady=1)
            fr.pack(fill=tk.X, pady=5)
            inner = tk.Frame(fr, bg=col_cl)
            inner.pack(fill=tk.BOTH)

            # Header de la card
            hdr_fr = tk.Frame(inner, bg=col_osc)
            hdr_fr.pack(fill=tk.X)
            tk.Frame(hdr_fr, bg=AMBER if tipo_nom == "Clasica" else "#34D399",
                     width=5).pack(side=tk.LEFT, fill=tk.Y)
            _lbl(hdr_fr, f"  PUBLICACIÓN {tipo_nom.upper()}",
                 (_FF, 11, "bold"), "white", col_osc, pady=9).pack(side=tk.LEFT)

            body = tk.Frame(inner, bg=col_cl, padx=16, pady=10)
            body.pack(fill=tk.X)

            def fila(r, l1, v1, l2="", v2="", col_v1=col_osc):
                _lbl(body, l1, FONT_N, fg=TX2, bg=col_cl).grid(
                    row=r, column=0, sticky=tk.W, pady=3)
                _lbl(body, v1, (_FF, 11, "bold"), col_v1, col_cl).grid(
                    row=r, column=1, sticky=tk.W, padx=(6, 24), pady=3)
                if l2:
                    _lbl(body, l2, FONT_N, fg=TX2, bg=col_cl).grid(
                        row=r, column=2, sticky=tk.W, pady=3)
                    _lbl(body, v2, (_FF, 11, "bold"), col_osc, col_cl).grid(
                        row=r, column=3, sticky=tk.W, padx=6, pady=3)

            if d.get("modo_inverso"):
                # Modo: solo costo ingresado → mostramos precio a publicar
                fila(0, f"PUBLICAR A:",        f"${d['precio_sug']:,.2f}",
                         col_v1="#155724")
                fila(1, "Comisión MeLi:",      f"{d['pct']:.1f}%",
                         "Comisión $:",        f"${d['fee']:,.2f}")
                fila(2, "Lo que cobrás neto:", f"${d['neto']:,.2f}",
                         "Tu Ganancia:",       f"${d['ganancia']:,.2f}")
                fila(3, f"Margen objetivo:",   f"{margen_obj:.0f}%")
            else:
                fila(0, "Comisión MeLi:",   f"{d['pct']:.1f}%",
                         "Comisión $:",     f"${d['fee']:,.2f}")
                fila(1, "Lo que cobrás:",   f"${d['neto']:,.2f}")

                if "margen" in d:
                    mg = d["margen"]
                    col_mg = ("#155724" if mg >= margen_obj
                              else "#856404" if mg >= 0 else "#CC0000")
                    fila(2, "Tu Margen:",   f"{mg:.1f}%",
                             "Tu Ganancia:", f"${d['ganancia']:,.2f}",
                             col_v1=col_mg)
                    if d.get("precio_sug"):
                        fila(3, f"Precio sugerido ({margen_obj}% mg):",
                                 f"${d['precio_sug']:,.2f}")

    def _limpiar(self):
        self.var_q.set("")
        self.var_precio.set("")
        self.var_costo.set("")
        self.var_margen.set("20")
        self.var_cat.set("")
        self.combo["values"] = []
        self._cats = []
        self.lbl_cat_info.config(
            text="Escribí un producto y hacé click en 'Buscar en MeLi'",
            fg="#666666")
        for w in self.fr_result.winfo_children():
            w.destroy()

# ============================================================
# PESTAÑA: PROCESAR EXCEL
# ============================================================

class TabExcel(ttk.Frame):
    def __init__(self, nb, app_ref):
        super().__init__(nb)
        self.app = app_ref
        self._q  = queue.Queue()
        self._ruta_salida = None
        self._build()

    def _build(self):
        # ── Archivo ──
        fr1 = tk.LabelFrame(self,
            text=" 1.  Elegir tu planilla Excel de Flexxus ",
            font=FONT_H, fg=TX2, bg=CARD, padx=12, pady=10, relief=tk.FLAT)
        fr1.pack(fill=tk.X, padx=15, pady=(12, 6))
        fr1.columnconfigure(0, weight=1)

        fr_arch = tk.Frame(fr1, bg=CARD)
        fr_arch.pack(fill=tk.X)
        fr_arch.columnconfigure(0, weight=1)

        self.var_arch = tk.StringVar(value="(ningún archivo seleccionado)")
        tk.Label(fr_arch, textvariable=self.var_arch,
                 bg=BG, relief=tk.FLAT, font=FONT_N,
                 anchor=tk.W, padx=8, pady=6,
                 fg=TX2).grid(row=0, column=0, sticky=tk.EW, padx=(0, 8))
        _btn(fr_arch, "Elegir Archivo", self._elegir,
             bg=BLUE, padx=10).grid(row=0, column=1)

        _lbl(fr1,
             "Columnas que reconoce: CODIGO, DESCRIPCION, RUBRO, SUB_RUBRO, PRECIO_VENTA, COSTO_NETO, STOCK",
             FONT_S, fg=TX3, bg=CARD).pack(anchor=tk.W, pady=(6, 0))

        # ── Config ──
        fr2 = tk.LabelFrame(self, text=" 2.  Configuración ",
                            font=FONT_H, fg=TX2, bg=CARD, padx=12, pady=10, relief=tk.FLAT)
        fr2.pack(fill=tk.X, padx=15, pady=6)

        row = tk.Frame(fr2, bg=CARD)
        row.pack(fill=tk.X)

        _lbl(row, "Margen objetivo (%):", fg=TX2, bg=CARD).pack(side=tk.LEFT)
        self.var_margen = tk.StringVar(value="20")
        ttk.Entry(row, textvariable=self.var_margen,
                  font=(_FF, 11), width=7).pack(side=tk.LEFT, padx=(6, 30))

        _lbl(row, "Nombre del archivo resultado:", fg=TX2, bg=CARD).pack(side=tk.LEFT)
        self.var_salida = tk.StringVar(value="comisiones_meli.xlsx")
        ttk.Entry(row, textvariable=self.var_salida,
                  font=(_FF, 11), width=28).pack(side=tk.LEFT, padx=6)

        # ── Botones ──
        fr_btns2 = tk.Frame(self, bg=BG)
        fr_btns2.pack(pady=(6, 4))

        self.btn_proc = _btn(fr_btns2, "  PROCESAR Y GENERAR ANÁLISIS  ",
                             self._procesar, bg=GREEN,
                             padx=18, pady=11, font=FONT_BIG)
        self.btn_proc.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_margenes = _btn(fr_btns2,
                             "  ANALIZAR MÁRGENES FLEXXUS vs MeLi  ",
                             self._analizar_margenes, bg="#6D28D9",
                             padx=18, pady=11, font=FONT_BIG)
        self.btn_margenes.pack(side=tk.LEFT)

        _lbl(self,
             "↑ Calculá cuánto subir el margen en Flexxus por rubro para no perder con las comisiones",
             FONT_S, fg="#7C3AED", bg=BG).pack()

        # ── Progreso ──
        fr_prog = tk.Frame(self, bg=BG)
        fr_prog.pack(fill=tk.X, padx=15)

        self.var_prog_txt = tk.StringVar(value="")
        _lbl(fr_prog, "", FONT_S, fg=TX2, bg=BG,
             textvariable=self.var_prog_txt).pack(anchor=tk.W)

        self.pbar = ttk.Progressbar(fr_prog, length=600, mode="determinate")
        self.pbar.pack(fill=tk.X, pady=4)

        self.btn_abrir = _btn(self, "  Abrir Excel con Resultados  ",
                              self._abrir, bg=HDR, padx=16, pady=8,
                              state=tk.DISABLED)
        self.btn_abrir.pack(pady=4)

        # ── Log ──
        fr_log = tk.LabelFrame(self, text=" Progreso detallado ",
                               font=FONT_S, fg=TX2, bg=CARD, relief=tk.FLAT)
        fr_log.pack(fill=tk.BOTH, expand=True, padx=15, pady=(6, 12))

        self.txt_log = tk.Text(fr_log, height=7, font=("Courier", 9),
                               bg="#1B1B2F", fg="#E0E0FF",
                               state=tk.DISABLED, wrap=tk.WORD)
        sb = ttk.Scrollbar(fr_log, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_log.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    def _log(self, msg):
        self.txt_log.config(state=tk.NORMAL)
        ts = datetime.now().strftime("%H:%M:%S")
        self.txt_log.insert(tk.END, f"[{ts}] {msg}\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state=tk.DISABLED)

    def _elegir(self):
        ruta = filedialog.askopenfilename(
            title="Elegir Excel de Flexxus",
            filetypes=[("Excel", "*.xlsx *.xls"), ("Todos", "*.*")])
        if ruta:
            self.var_arch.set(ruta)

    def _procesar(self):
        ruta = self.var_arch.get()
        if not ruta or ruta == "(ningún archivo seleccionado)":
            messagebox.showwarning("Falta archivo",
                "Primero elegí el archivo Excel de Flexxus.")
            return
        if not os.path.exists(ruta):
            messagebox.showerror("No encontrado", f"No se encontró:\n{ruta}")
            return

        try:
            margen_obj = float(self.var_margen.get().replace("%", ""))
        except ValueError:
            margen_obj = 20

        nombre = self.var_salida.get().strip() or "comisiones_meli.xlsx"
        if not nombre.endswith(".xlsx"):
            nombre += ".xlsx"

        ruta_salida = os.path.join(os.path.dirname(ruta), nombre)

        self.btn_proc.config(state=tk.DISABLED, text="Procesando...")
        self.btn_abrir.config(state=tk.DISABLED)
        self.pbar["value"] = 0
        self.var_prog_txt.set("Iniciando...")
        self._q = queue.Queue()

        token = self.app.token_activo()

        def run():
            import pandas as pd
            try:
                df = pd.read_excel(ruta, dtype=str)
                df.columns = [str(c).strip() for c in df.columns]
                df = df.dropna(how="all").reset_index(drop=True)
                total = len(df)
                self._q.put(("log", f"Archivo: {os.path.basename(ruta)}  ({total} productos)"))

                col_map = backend.detectar_columnas(df.columns)
                self._q.put(("log",
                    f"Columnas detectadas: {', '.join(f'{k}→{v}' for k,v in col_map.items())}"))

                fuente_txt = "API MeLi (tiempo real)" if token else "tabla local"
                self._q.put(("log", f"Fuente de comisiones: {fuente_txt}"))

                mapa_cats = {}
                resultados = []

                for idx, fila in df.iterrows():
                    d    = fila.to_dict()
                    dato = {c: ("" if str(d.get(c, "")) == "nan" else d.get(c, ""))
                            for c in df.columns}

                    precio = backend.limpiar_numero(d.get(col_map.get("precio", "")))
                    costo  = backend.limpiar_numero(d.get(col_map.get("costo", "")))

                    texto = ""
                    if "rubro" in col_map:
                        texto = str(d.get(col_map["rubro"], "")).strip()
                        if "subrubro" in col_map:
                            sub = str(d.get(col_map["subrubro"], "")).strip()
                            if sub and sub != "nan":
                                texto = f"{texto} {sub}".strip()
                    if not texto or texto in ("nan", "None"):
                        if "descripcion" in col_map:
                            texto = str(d.get(col_map["descripcion"], ""))[:50].strip()

                    cat_id = cat_nom = cat_raiz = ""
                    tasas  = backend.TABLA.get("_default", {})

                    if texto and texto not in ("nan", "None"):
                        if texto in mapa_cats:
                            cat_id, cat_nom, cat_raiz, tasas = mapa_cats[texto]
                        else:
                            cats = backend.buscar_categoria(texto, 1)
                            if cats:
                                cat_id   = cats[0].get("category_id", "")
                                cat_nom  = cats[0].get("domain_name") or cats[0].get("category_name", "")
                                cat_raiz = backend.obtener_raiz_categoria(cat_id) if cat_id else ""
                                tasas    = backend.obtener_comision(cat_raiz)
                            mapa_cats[texto] = (cat_id, cat_nom, cat_raiz, tasas)
                            time.sleep(0.12)

                    dato["__cat_id"]    = cat_id
                    dato["__cat_nombre"] = cat_nom
                    dato["__cat_raiz"]  = cat_raiz
                    dato["__precio"]    = precio
                    dato["__costo"]     = costo

                    for tipo_nom, tipo_id in backend.TIPOS_PUBLICACION.items():
                        p = tipo_nom.lower()
                        pct = fee = None

                        if token and precio and cat_id:
                            pct, fee = consultar_comision_api(precio, cat_id, tipo_id, token)

                        if pct is None:
                            pct, fee = fallback_tabla(cat_raiz, tipo_nom, precio) if precio else (None, None)

                        dato[f"__pct_{p}"] = pct
                        dato[f"__fee_{p}"] = fee

                        if precio and fee is not None:
                            neto = precio - fee
                            dato[f"__neto_{p}"] = round(neto, 2)
                            if costo and costo > 0:
                                mg  = (neto - costo) / precio * 100
                                sug = backend.calcular_precio_sugerido(costo, pct, margen_obj)
                                dato[f"__margen_{p}"] = round(mg, 2)
                                dato[f"__sug_{p}"]    = sug
                            else:
                                dato[f"__margen_{p}"] = None
                                dato[f"__sug_{p}"]    = None
                        else:
                            dato[f"__neto_{p}"] = dato[f"__margen_{p}"] = dato[f"__sug_{p}"] = None

                    resultados.append(dato)
                    pct_av = int((idx + 1) / total * 100)
                    desc = str(d.get(col_map.get("descripcion", ""), ""))[:30]
                    self._q.put(("prog", pct_av,
                                 f"[{idx+1}/{total}]  {desc}  —  {cat_nom or 'buscando...'}"))

                self._q.put(("log", "Generando Excel de análisis..."))
                backend.generar_excel_salida(
                    resultados, col_map, list(df.columns), ruta_salida, margen_obj)
                self._q.put(("done", ruta_salida))

            except Exception as e:
                import traceback
                self._q.put(("error", str(e), traceback.format_exc()))

        threading.Thread(target=run, daemon=True).start()
        self.after(200, self._poll)

    def _poll(self):
        try:
            while True:
                msg = self._q.get_nowait()
                if msg[0] == "prog":
                    self.pbar["value"] = msg[1]
                    self.var_prog_txt.set(msg[2])
                elif msg[0] == "log":
                    self._log(msg[1])
                elif msg[0] == "done":
                    self._ruta_salida = msg[1]
                    self.pbar["value"] = 100
                    self.var_prog_txt.set("¡Listo!")
                    self.btn_proc.config(state=tk.NORMAL,
                                         text="  PROCESAR Y GENERAR ANÁLISIS  ")
                    self.btn_abrir.config(state=tk.NORMAL)
                    self._log(f"ARCHIVO GENERADO: {msg[1]}")
                    messagebox.showinfo("¡Proceso completado!",
                        f"Análisis guardado en:\n{msg[1]}\n\n"
                        "El archivo tiene 3 hojas:\n"
                        "  • Análisis Comisiones  — detalle por producto\n"
                        "  • Resumen por Categoría  — totales y promedios\n"
                        "  • Instrucciones  — cómo leer cada columna")
                    return
                elif msg[0] == "error":
                    self._log(f"ERROR: {msg[1]}")
                    self.btn_proc.config(state=tk.NORMAL,
                                         text="  PROCESAR Y GENERAR ANÁLISIS  ")
                    messagebox.showerror("Error al procesar",
                        f"Ocurrió un error:\n{msg[1]}")
                    return
        except queue.Empty:
            pass
        self.after(150, self._poll)

    def _abrir(self):
        if self._ruta_salida and os.path.exists(self._ruta_salida):
            os.startfile(self._ruta_salida)

    def _analizar_margenes(self):
        ruta = self.var_arch.get()
        if not ruta or ruta == "(ningún archivo seleccionado)":
            messagebox.showwarning("Falta archivo", "Primero elegí el archivo Excel de Flexxus.")
            return
        if not os.path.exists(ruta):
            messagebox.showerror("No encontrado", f"No se encontró:\n{ruta}")
            return

        try:
            margen_obj = float(self.var_margen.get().replace("%", ""))
        except ValueError:
            margen_obj = 20

        ruta_salida = ruta.replace(".xlsx", f"_margenes_meli_{int(margen_obj)}pct.xlsx")

        self.btn_margenes.config(state=tk.DISABLED, text="Analizando...")
        self.btn_proc.config(state=tk.DISABLED)
        self.btn_abrir.config(state=tk.DISABLED)
        self.pbar["value"] = 0
        self.var_prog_txt.set("Iniciando análisis de márgenes...")
        self._log("━━━ ANALISIS DE MARGENES FLEXXUS vs MeLi ━━━")

        import analizar_margenes as am

        def progress_cb(i, total, desc):
            pct = i / total * 100
            self.after(0, lambda p=pct, d=desc, ii=i, t=total: (
                self.pbar.__setitem__("value", p),
                self.var_prog_txt.set(f"[{ii}/{t}]  {d}"),
            ))

        def run():
            try:
                self.after(0, lambda: self._log(f"Archivo: {os.path.basename(ruta)}"))
                resultados, tc, mg = am.procesar(ruta, margen_obj, progress_cb=progress_cb)
                self.after(0, lambda: self._log(
                    f"Procesados {len(resultados)} productos  |  TC: ${tc:,.0f}"))

                am.generar_excel(resultados, ruta_salida, mg, tc)
                self._ruta_salida = ruta_salida

                necesitan = sum(1 for r in resultados
                                if any(r["tipos"].get(t, {}).get("ajuste", 0) or 0 > 0
                                       for t in r["tipos"]))
                self.after(0, lambda: (
                    self._log(f"✓ Excel generado: {os.path.basename(ruta_salida)}"),
                    self._log(f"  → {necesitan} productos necesitan ajuste de margen"),
                    self.btn_abrir.config(state=tk.NORMAL),
                    self.var_prog_txt.set(
                        f"✓ Listo — {necesitan} productos con margen insuficiente"),
                    self.pbar.__setitem__("value", 100),
                    self.btn_margenes.config(state=tk.NORMAL,
                        text="  ANALIZAR MÁRGENES FLEXXUS vs MeLi  "),
                    self.btn_proc.config(state=tk.NORMAL),
                ))
            except Exception as e:
                import traceback
                err = traceback.format_exc()
                self.after(0, lambda: (
                    self._log(f"[ERROR] {e}"),
                    self._log(err[:500]),
                    self.btn_margenes.config(state=tk.NORMAL,
                        text="  ANALIZAR MÁRGENES FLEXXUS vs MeLi  "),
                    self.btn_proc.config(state=tk.NORMAL),
                ))

        threading.Thread(target=run, daemon=True).start()

# ============================================================
# PESTAÑA: COMPETENCIA EN MELI
# ============================================================

class TabCompetencia(ttk.Frame):
    """
    Buscás por SKU o EAN y ves a la izquierda tu producto con precios
    y a la derecha todos los competidores de MeLi con análisis.
    """

    MELI_SELLER_ID = 32331880   # tu cuenta CLUBDIGITALSTORE

    def __init__(self, nb, app_ref):
        super().__init__(nb)
        self.app = app_ref
        self._productos_cache = []   # referencia a los productos cargados en TabRubros
        self._tc = 1420.0
        self._prod_actual = None
        self._build()

    # ── UI ───────────────────────────────────────────────────

    def _build(self):
        self.configure(style="TFrame")

        # ── Barra de búsqueda ──
        fr_top = tk.Frame(self, bg=BG, padx=12, pady=10)
        fr_top.pack(fill=tk.X)

        _lbl(fr_top, "Buscar por SKU o EAN:", fg=TX1, bg=BG).pack(side=tk.LEFT)
        self.var_buscar = tk.StringVar()
        ent = ttk.Entry(fr_top, textvariable=self.var_buscar,
                        font=(_FF, 12), width=26)
        ent.pack(side=tk.LEFT, padx=(6, 8))
        ent.bind("<Return>", lambda _: self._buscar())
        _btn(fr_top, "  BUSCAR  ", self._buscar, bg=GREEN, padx=14).pack(side=tk.LEFT)

        self.lbl_estado = _lbl(fr_top, "", FONT_S, fg=TX2, bg=BG)
        self.lbl_estado.pack(side=tk.LEFT, padx=20)

        # ── Panel dividido ──
        fr_main = tk.Frame(self, bg=BG)
        fr_main.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        fr_main.columnconfigure(0, weight=2)
        fr_main.columnconfigure(1, weight=5)
        fr_main.rowconfigure(0, weight=1)

        # ── PANEL IZQUIERDO: mi producto ──
        fr_mio = tk.LabelFrame(fr_main, text=" Mi Producto ",
                               font=FONT_H, fg=TX2,
                               bg=CARD, padx=14, pady=12,
                               relief=tk.FLAT, bd=1,
                               highlightbackground=BORD,
                               highlightthickness=1)
        fr_mio.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        def fld(parent, label, attr, valor="", editable=False, bold=False):
            row = tk.Frame(parent, bg=CARD)
            row.pack(fill=tk.X, pady=3)
            _lbl(row, label, FONT_N, fg=TX2, bg=CARD).pack(side=tk.LEFT)
            var = tk.StringVar(value=valor)
            setattr(self, attr, var)
            if editable:
                e = ttk.Entry(row, textvariable=var, font=(_FF, 11), width=16)
                e.pack(side=tk.RIGHT)
            else:
                color = GREEN if bold else TX1
                tk.Label(row, textvariable=var,
                         font=(_FF, 11, "bold") if bold else FONT_N,
                         fg=color, bg=CARD).pack(side=tk.RIGHT)

        fld(fr_mio, "SKU:",               "lbl_sku")
        fld(fr_mio, "Descripción:",        "lbl_desc")
        fld(fr_mio, "EAN / Cód. de barra:","lbl_ean")
        fld(fr_mio, "IVA:",                "lbl_iva")

        tk.Frame(fr_mio, bg=BORD, height=1).pack(fill=tk.X, pady=8)

        fld(fr_mio, "Costo ARS:",          "lbl_costo")
        fld(fr_mio, "Precio actual ARS:",  "lbl_precio_act")
        fld(fr_mio, "Margen Flexxus:",     "lbl_mg_flexxus")

        tk.Frame(fr_mio, bg=BORD, height=1).pack(fill=tk.X, pady=8)

        _lbl(fr_mio, "Precio a publicar ($):", FONT_N, fg=TX2, bg=CARD).pack(anchor=tk.W)
        self.var_precio_pub = tk.StringVar()
        ttk.Entry(fr_mio, textvariable=self.var_precio_pub,
                  font=(_FF, 12), width=18).pack(anchor=tk.W, pady=(2,6))
        _btn(fr_mio, "CALCULAR", self._calcular_mio,
             bg=GREEN, padx=12, pady=7, font=FONT_H).pack(anchor=tk.W, pady=2)

        tk.Frame(fr_mio, bg=BORD, height=1).pack(fill=tk.X, pady=8)

        fld(fr_mio, "Categoría MeLi:",     "lbl_cat")
        fld(fr_mio, "Comisión MeLi:",      "lbl_com")
        fld(fr_mio, "Lo que cobrás:",      "lbl_neto")
        fld(fr_mio, "Margen real:",        "lbl_margen", bold=True)

        # ── PANEL DERECHO: competencia ──
        fr_comp = tk.LabelFrame(fr_main, text=" Competencia en MeLi ",
                                font=FONT_H, fg=TX2,
                                bg=CARD, padx=6, pady=6,
                                relief=tk.FLAT, bd=1,
                                highlightbackground=BORD,
                                highlightthickness=1)
        fr_comp.grid(row=0, column=1, sticky="nsew")

        # ── Resumen estadístico — tarjetas de color ──────────────
        fr_stats = tk.Frame(fr_comp, bg=BG, pady=8, padx=8)
        fr_stats.pack(fill=tk.X, pady=(0, 6))
        for i in range(5):
            fr_stats.columnconfigure(i, weight=1)

        STAT_CARDS = [
            ("lbl_st_min",  "Precio mínimo",  BLUE,  "#EFF6FF"),
            ("lbl_st_prom", "Precio prom.",   HDR2,  "#F1F5F9"),
            ("lbl_st_max",  "Precio máximo",  RED,   "#FEF2F2"),
            ("lbl_st_cant", "Competidores",   AMBER, "#FFFBEB"),
            ("lbl_st_pos",  "Tu posición",    GREEN, "#ECFDF5"),
        ]
        for i, (attr, titulo, accent, bg_card) in enumerate(STAT_CARDS):
            card = tk.Frame(fr_stats, bg=bg_card,
                            relief=tk.FLAT, bd=0,
                            padx=10, pady=6)
            card.grid(row=0, column=i, padx=5, sticky="nsew")
            # Accent bar top
            tk.Frame(card, bg=accent, height=3).pack(fill=tk.X)
            _lbl(card, titulo, FONT_S, fg=TX2, bg=bg_card).pack(pady=(4,0))
            var = tk.StringVar(value="—")
            setattr(self, attr, var)
            tk.Label(card, textvariable=var,
                     font=(_FF, 13, "bold"),
                     fg=accent, bg=bg_card).pack()

        # Tabla de competidores
        cols_c = ("pos","precio","vendedor","tipo","envio","cuotas","link")
        self.tree_comp = ttk.Treeview(fr_comp, columns=cols_c,
                                      show="headings", height=16)
        hdrs_c = [
            ("pos",      "#",           38),
            ("precio",   "Precio",     110),
            ("vendedor", "Vendedor",   200),
            ("tipo",     "Publicación", 80),
            ("envio",    "Envío",       90),
            ("cuotas",   "Cuotas",      55),
            ("link",     "Ver ↗",       55),
        ]
        for cid, txt, w in hdrs_c:
            self.tree_comp.heading(cid, text=txt)
            anch = "w" if cid == "vendedor" else "center"
            self.tree_comp.column(cid, width=w, anchor=anch, stretch=(cid=="vendedor"))

        sb_cy = ttk.Scrollbar(fr_comp, orient="vertical",
                               command=self.tree_comp.yview)
        self.tree_comp.configure(yscrollcommand=sb_cy.set)
        sb_cy.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_comp.pack(fill=tk.BOTH, expand=True)
        self.tree_comp.bind("<Double-1>", self._abrir_link)

        # Tags con nueva paleta
        self.tree_comp.tag_configure("propio",    background="#DBEAFE",
                                     foreground="#1D4ED8", font=(_FF, 9, "bold"))
        self.tree_comp.tag_configure("primero",   background="#D1FAE5",
                                     foreground="#065F46", font=(_FF, 9, "bold"))
        self.tree_comp.tag_configure("normal",    background=CARD, foreground=TX1)
        self.tree_comp.tag_configure("mas_caro",  background="#FEE2E2",
                                     foreground="#991B1B")
        # Fila virtual "Tu precio" — fondo ámbar
        self.tree_comp.tag_configure("mi_precio", background="#FEF3C7",
                                     foreground="#92400E", font=(_FF, 9, "bold"))

    # ── Búsqueda ─────────────────────────────────────────────

    def _get_cache_productos(self):
        """Obtiene la lista de productos del cache de TabRubros."""
        try:
            return self.app.tab_r._productos
        except Exception:
            return []

    def _buscar(self):
        texto = self.var_buscar.get().strip()
        if not texto:
            return

        prods = self._get_cache_productos()
        prod  = None

        # Buscar en cache por SKU o EAN
        texto_up = texto.upper()
        for p in prods:
            if (str(p.get("sku","")).upper() == texto_up or
                str(p.get("ean","")).strip() == texto):
                prod = p
                break

        ean  = prod.get("ean","") if prod else texto
        desc = prod.get("desc","") if prod else ""

        # Limpiar panel izquierdo
        self._prod_actual = prod
        self._mostrar_mi_producto(prod, ean)

        # Buscar competencia: primero por EAN, fallback por descripción
        if ean and ean not in ("nan","None",""):
            self.lbl_estado.config(text=f"Buscando EAN {ean} en MeLi...", fg=BLUE)
            self.update_idletasks()
            threading.Thread(target=self._buscar_competencia,
                             args=(ean, desc), daemon=True).start()
        elif desc:
            self.lbl_estado.config(text=f"Sin EAN — buscando por descripción en MeLi...", fg=BLUE)
            self.update_idletasks()
            threading.Thread(target=self._buscar_competencia,
                             args=("", desc), daemon=True).start()
        else:
            self.lbl_estado.config(
                text="Este producto no tiene EAN ni descripción para buscar",
                fg="#CC0000")

    def _mostrar_mi_producto(self, prod, ean):
        if prod:
            tc   = self.app.tab_r._tc if hasattr(self.app, "tab_r") else 1420.0
            self._tc = tc
            self.lbl_sku.set(prod.get("sku","—"))
            self.lbl_desc.set(prod.get("desc","—")[:55])
            self.lbl_ean.set(ean or "—")
            self.lbl_iva.set(f"{prod.get('iva',0):.0f}%" if prod.get('iva') is not None else "—")
            self.lbl_costo.set(f"${prod.get('costo_ars',0):,.0f}")
            self.lbl_precio_act.set(f"${prod.get('precio_ars',0):,.0f}")
            mg_f = prod.get("mg_flexxus")
            self.lbl_mg_flexxus.set(f"{mg_f:.1f}%" if mg_f is not None else "—")
            self.var_precio_pub.set(f"{prod.get('precio_ars',0):,.0f}")
            # Cat y comisión
            tipos = list(prod.get("tipos",{}).keys())
            if tipos:
                t0  = tipos[0]
                cat = prod.get("cat_raiz","—")
                com = prod["tipos"][t0].get("comision","—")
                self.lbl_cat.set(cat)
                self.lbl_com.set(f"{com:.1f}%" if isinstance(com, float) else str(com))
            else:
                self.lbl_cat.set("—")
                self.lbl_com.set("—")
            self.lbl_neto.set("—")
            self.lbl_margen.set("—")
        else:
            # Solo EAN, sin datos propios
            for attr in ("lbl_sku","lbl_desc","lbl_iva","lbl_costo","lbl_precio_act",
                         "lbl_mg_flexxus","lbl_cat","lbl_com","lbl_neto","lbl_margen"):
                getattr(self, attr).set("—")
            self.lbl_ean.set(ean or "—")
            self.var_precio_pub.set("")

    def _calcular_mio(self):
        """Calcula comisión y margen con el precio que ingresó el usuario."""
        prod = self._prod_actual
        if not prod:
            return
        try:
            precio = float(self.var_precio_pub.get().replace("$","").replace(",","").replace(".","",1 if "." in self.var_precio_pub.get() else 0).strip())
        except Exception:
            try:
                precio = float(self.var_precio_pub.get().replace("$","").replace(",",".").strip())
            except Exception:
                messagebox.showwarning("Precio inválido", "Ingresá un precio válido.")
                return

        tipos = list(prod.get("tipos",{}).keys())
        if not tipos:
            return
        t0  = tipos[0]
        com = prod["tipos"][t0].get("comision", 0)
        fee  = precio * com / 100
        neto = precio - fee
        costo = prod.get("costo_ars", 0) or 0
        margen = (neto - costo) / precio * 100 if precio > 0 else 0

        self.lbl_neto.set(f"${neto:,.0f}")
        col = "#155724" if margen >= 20 else "#856404" if margen >= 0 else "#CC0000"
        self.lbl_margen.set(f"{margen:.1f}%")
        # Actualizar color manualmente buscando el label
        for w in self.winfo_children():
            self._set_margen_color(w, col)

    def _set_margen_color(self, widget, color):
        for child in widget.winfo_children():
            try:
                if hasattr(child, 'cget') and child.cget('textvariable') and \
                   str(child.cget('textvariable')) == str(self.lbl_margen):
                    child.config(fg=color)
            except Exception:
                pass
            self._set_margen_color(child, color)

    # ── helpers internos ─────────────────────────────────────────

    @staticmethod
    def _fmt_envio(ship):
        """Convierte el objeto shipping de MeLi en texto legible."""
        if not ship:
            return "Ver"
        tags  = ship.get("tags", [])
        mode  = ship.get("mode", "")
        free  = ship.get("free_shipping", False)
        cost  = ship.get("cost")

        # Mercado Envíos Full: desde depósito MeLi, el más rápido
        if "fulfillment" in tags or mode == "fulfillment":
            return "🏭 Full"
        # Envío gratis (MeLi obliga para montos altos o vendedor absorbe)
        if free:
            return "🚚 Gratis"
        # Envío con costo explícito
        if cost and cost > 0:
            return f"${cost:,.0f}"
        # Tiene envío pero no es gratis y no hay costo (se ve en el ítem)
        if mode in ("me2", "me1"):
            return "Con envío"
        return "Ver"

    @staticmethod
    def _safe_get(url, params=None, headers=None, timeout=14):
        """GET que nunca lanza excepción. Devuelve (status_code, dict_json)."""
        try:
            r = requests.get(url, params=params, headers=headers or {}, timeout=timeout)
            try:
                body = r.json()
            except Exception:
                body = {}
            return r.status_code, body
        except Exception:
            return 0, {}

    @staticmethod
    def _normalizar_items(raw_list, fuente="catalog"):
        """
        Convierte cualquier formato de resultado MeLi a la estructura interna:
          {item_id, seller_id, price, listing_type_id, shipping, accepts_mercadopago, official_store_id}
        Soporta el formato de /products/{id}/items  Y  /sites/MLA/search results.
        """
        out = []
        for it in raw_list:
            if fuente == "search":
                # /sites/MLA/search: seller es un objeto {id, nickname}
                seller = it.get("seller", {})
                sid    = seller.get("id", 0)
                nick   = seller.get("nickname", "")
                out.append({
                    "item_id":             it.get("id", ""),
                    "seller_id":           sid,
                    "_nick":               nick,
                    "price":               it.get("price", 0),
                    "listing_type_id":     it.get("listing_type_id", ""),
                    "shipping":            it.get("shipping", {}),
                    "accepts_mercadopago": it.get("accepts_mercadopago", True),
                    "official_store_id":   it.get("official_store_id"),
                })
            else:
                # /products/{id}/items: seller_id es directo
                out.append({
                    "item_id":             it.get("item_id", ""),
                    "seller_id":           it.get("seller_id", 0),
                    "_nick":               "",
                    "price":               it.get("price", 0),
                    "listing_type_id":     it.get("listing_type_id", ""),
                    "shipping":            it.get("shipping", {}),
                    "accepts_mercadopago": it.get("accepts_mercadopago", True),
                    "official_store_id":   it.get("official_store_id"),
                })
        return [x for x in out if x["price"] > 0]

    # ─────────────────────────────────────────────────────────────────────

    def _buscar_competencia(self, ean, desc=""):
        """
        Búsqueda en cascada con 4 estrategias para nunca devolver vacío si el
        producto existe en MeLi.

        FASE 1 — Encontrar catalog_product_id:
          A) products/search?q={EAN}            ← coincidencia exacta barcode
          B) products/search?q={desc recortada} ← múltiples variantes de palabras

        FASE 2 — Obtener vendedores:
          A) products/{id}/items                ← endpoint oficial del catálogo
          B) sites/MLA/search?catalog_product_id={id}  ← fallback con token usuario
          C) sites/MLA/search?q={nombre catálogo}      ← fallback por texto
          D) sites/MLA/search?q={EAN o desc}           ← último recurso
        """
        token = self.app.token_activo()
        h     = {"Authorization": f"Bearer {token}"} if token else {}

        def _get(url, params=None):
            return self._safe_get(url, params=params, headers=h)

        def _status(txt):
            self.after(0, lambda t=txt: self.lbl_estado.config(text=t, fg=BLUE))

        TIPOS = {"gold_premium": "Premium ⭐",
                 "gold_special": "Clásica",
                 "gold":         "Gold",
                 "silver":       "Silver",
                 "free":         "Gratis"}

        # ══════════════════════════════════════════════════════════════════
        # FASE 1 — catalog_product_id
        # ══════════════════════════════════════════════════════════════════
        # Armar todas las queries posibles, de más a menos precisa
        queries = []
        if ean:
            queries.append(ean)
        if desc:
            ws = desc.split()
            for slc in [ws[:6], ws[:5], ws[:4], ws[:3], ws[1:6], ws[1:5], ws[2:6]]:
                q = " ".join(slc).strip()
                if q and q not in queries:
                    queries.append(q)
        queries = list(dict.fromkeys(q for q in queries if len(q) >= 3))

        catalog_id = catalog_name = ""
        for i, q in enumerate(queries):
            _status(f"Buscando ({i+1}/{len(queries)}): «{q[:40]}»...")
            sc, data = _get("https://api.mercadolibre.com/products/search",
                            {"site_id": "MLA", "q": q, "limit": 5, "status": "active"})
            if sc == 200:
                results = data.get("results", [])
                if results:
                    catalog_id   = results[0].get("id", "")
                    catalog_name = results[0].get("name", "")
                    break
            elif sc == 0:
                time.sleep(0.5)   # error de red → pausar y reintentar en la siguiente

        # ══════════════════════════════════════════════════════════════════
        # FASE 2 — Obtener lista de vendedores
        # ══════════════════════════════════════════════════════════════════
        items_raw = []
        fuente    = "catalog"

        # — 2A: endpoint principal —
        if catalog_id:
            _status(f"Cargando vendedores de «{catalog_name[:35]}»...")
            sc, data = _get(f"https://api.mercadolibre.com/products/{catalog_id}/items")
            if sc == 200:
                items_raw = data.get("results", [])

        # — 2B: fallback catalog_product_id en search (funciona con token de usuario) —
        if not items_raw and catalog_id and token:
            _status("Buscando vendedores por ID de catálogo...")
            sc, data = _get("https://api.mercadolibre.com/sites/MLA/search",
                            {"catalog_product_id": catalog_id, "limit": 50})
            if sc == 200 and data.get("results"):
                items_raw = data["results"]
                fuente    = "search"

        # — 2C: fallback por nombre del catálogo —
        if not items_raw and catalog_name and token:
            _status(f"Buscando por nombre: «{catalog_name[:35]}»...")
            sc, data = _get("https://api.mercadolibre.com/sites/MLA/search",
                            {"q": catalog_name[:80], "limit": 50})
            if sc == 200 and data.get("results"):
                items_raw = data["results"]
                fuente    = "search"

        # — 2D: último recurso — buscar por EAN o descripción directamente —
        if not items_raw and token:
            last_q = ean or (desc[:60] if desc else "")
            if last_q:
                _status(f"Último intento: «{last_q[:35]}»...")
                sc, data = _get("https://api.mercadolibre.com/sites/MLA/search",
                                {"q": last_q, "limit": 50})
                if sc == 200 and data.get("results"):
                    items_raw = data["results"]
                    fuente    = "search"
                    if not catalog_name:
                        catalog_name = last_q

        # — Sin resultados —
        if not items_raw:
            msg = (f"No se encontró «{(desc or ean)[:40]}» en MeLi. "
                   "Verificá el EAN o la descripción.")
            self.after(0, lambda m=msg: self.lbl_estado.config(text=m, fg=AMBER))
            self.after(0, self._limpiar_stats)
            return

        # ══════════════════════════════════════════════════════════════════
        # FASE 3 — Normalizar y enriquecer
        # ══════════════════════════════════════════════════════════════════
        norm = self._normalizar_items(items_raw, fuente=fuente)

        # Nicknames en batch solo para los que no vienen del search
        sellers_sin_nick = [it["seller_id"] for it in norm if not it.get("_nick")]
        nick_map = {}
        if sellers_sin_nick:
            _status("Obteniendo nombres de vendedores...")
            ids_uniq = list(dict.fromkeys(sellers_sin_nick))[:20]
            sc, data = _get("https://api.mercadolibre.com/users",
                            {"ids": ",".join(str(s) for s in ids_uniq),
                             "attributes": "id,nickname"})
            if sc == 200:
                for entry in data:
                    body = entry.get("body", {})
                    nick_map[body.get("id")] = body.get("nickname", "?")

        items_enriquecidos = []
        for it in norm:
            iid    = it.get("item_id", "")
            digits = iid.replace("MLA", "").lstrip("-")
            plink  = (f"https://articulo.mercadolibre.com.ar/MLA-{digits}"
                      if digits else
                      f"https://www.mercadolibre.com.ar/p/{catalog_id or 'MLA'}")
            ship      = it.get("shipping", {})
            lt        = it.get("listing_type_id", "")
            acepta_mp = it.get("accepts_mercadopago", True)

            if not acepta_mp:
                cuotas_txt = "—"
            elif lt == "gold_premium":
                cuotas_txt = "12 s/int ⭐"
            else:
                cuotas_txt = "hasta 12"

            sid  = it.get("seller_id", 0)
            nick = (it.get("_nick") or
                    nick_map.get(sid) or
                    str(sid) or "?")

            items_enriquecidos.append({
                "item_id":   iid,
                "precio":    it["price"],
                "seller_id": sid,
                "vendedor":  nick,
                "tipo":      TIPOS.get(lt, lt or "—"),
                "cuotas":    cuotas_txt,
                "envio":     self._fmt_envio(ship),
                "permalink": plink,
                "es_propio": sid == self.MELI_SELLER_ID,
                "official":  bool(it.get("official_store_id")),
            })

        items_enriquecidos.sort(key=lambda x: x["precio"])

        self.after(0, lambda: self._mostrar_competencia(
            items_enriquecidos, catalog_name, len(items_enriquecidos)))

    def _limpiar_stats(self):
        for attr in ("lbl_st_min","lbl_st_prom","lbl_st_max","lbl_st_cant","lbl_st_pos"):
            getattr(self, attr).set("—")
        for row in self.tree_comp.get_children():
            self.tree_comp.delete(row)

    def _mostrar_competencia(self, items, catalog_name, total):
        for row in self.tree_comp.get_children():
            self.tree_comp.delete(row)

        if not items:
            self.lbl_estado.config(
                text=f"No hay vendedores activos para «{catalog_name}»",
                fg=AMBER)
            self._limpiar_stats()
            return

        # ── Precio que el usuario quiere publicar ─────────────────
        try:
            precio_mio = float(
                self.var_precio_pub.get().replace("$","").replace(",","").strip())
            if precio_mio <= 0:
                precio_mio = None
        except Exception:
            precio_mio = None

        # ── Precios de competidores (excluye propio) ──────────────
        precios_comp = [it["precio"] for it in items
                        if it.get("precio", 0) > 0 and not it.get("es_propio")]

        # ── Calcular posición de nuestro precio ───────────────────
        mi_pos_num = None   # posición 1-based entre la competencia
        if precio_mio and precios_comp:
            # cuántos tienen precio MENOR → su posición es ese número + 1
            menores    = sum(1 for p in precios_comp if p < precio_mio)
            mi_pos_num = menores + 1

        # ── Construir lista a mostrar: competencia + fila "TU PRECIO" ──
        # Insertamos un ítem virtual en la posición correcta
        filas = []
        mi_precio_insertado = False
        pos_contador = 0   # posición real (solo competidores)

        items_ordenados = sorted(items, key=lambda x: x["precio"])

        for item in items_ordenados:
            precio = item["precio"]

            # Insertar fila "TU PRECIO" justo antes del primer competidor
            # que supere nuestro precio (si no está ya insertado)
            if (precio_mio and not mi_precio_insertado
                    and precio > precio_mio
                    and not item.get("es_propio")):
                filas.append({"_mi_precio": True, "precio": precio_mio})
                mi_precio_insertado = True

            filas.append(item)

        # Si nuestro precio es el más caro (o no insertamos todavía), agregar al final
        if precio_mio and not mi_precio_insertado:
            filas.append({"_mi_precio": True, "precio": precio_mio})

        # ── Poblar la tabla ───────────────────────────────────────
        pos_real  = 0   # posición entre TODOS los ítems (incluyendo virtual)
        comp_real = 0   # posición solo entre competidores reales
        for i, item in enumerate(filas):
            pos_real += 1

            # ── Fila virtual "Tu precio" ──────────────────────────
            if item.get("_mi_precio"):
                iid_v = "__mi_precio__"
                self.tree_comp.insert("", "end", iid=iid_v, tags=("mi_precio",),
                    values=(
                        f"▶ #{pos_real}",
                        f"${item['precio']:,.0f}",
                        "👤  TU PRECIO",
                        "—", "—", "—", "—",
                    ))
                continue

            comp_real += 1
            precio = item["precio"]
            vend   = item["vendedor"]
            if item.get("official"):  vend = "🏪 " + vend
            if item.get("es_propio"): vend = "★ " + vend

            # Tag visual
            if item.get("es_propio"):
                tag = "propio"
            elif comp_real == 1:
                tag = "primero"
            elif precio_mio and precio > precio_mio * 1.10:
                tag = "mas_caro"
            else:
                tag = "normal"

            iid = item.get("item_id", f"r_{i}")
            self.tree_comp.insert("", "end", iid=iid, tags=(tag,),
                values=(
                    f"#{pos_real}",
                    f"${precio:,.0f}",
                    vend,
                    item.get("tipo", "—"),
                    item.get("envio", "—"),
                    item.get("cuotas", "—"),
                    "Abrir ↗",
                ))
            self.tree_comp.set(iid, "link", item.get("permalink", ""))

        # Hacer scroll hasta la fila "TU PRECIO" si existe
        try:
            self.tree_comp.see("__mi_precio__")
            self.tree_comp.selection_set("__mi_precio__")
        except Exception:
            pass

        # ── Estadísticas ──────────────────────────────────────────
        if precios_comp:
            self.lbl_st_min.set(f"${min(precios_comp):,.0f}")
            self.lbl_st_prom.set(f"${sum(precios_comp)/len(precios_comp):,.0f}")
            self.lbl_st_max.set(f"${max(precios_comp):,.0f}")
        else:
            for a in ("lbl_st_min", "lbl_st_prom", "lbl_st_max"):
                getattr(self, a).set("—")

        self.lbl_st_cant.set(str(total))

        if mi_pos_num and precios_comp:
            total_con_mio = len(precios_comp) + 1
            # Indicador de situación
            if mi_pos_num == 1:
                pos_txt = f"#1 ✓ EL MÁS BARATO"
            elif mi_pos_num <= total_con_mio * 0.25:
                pos_txt = f"#{mi_pos_num} de {total_con_mio}  🟢"
            elif mi_pos_num <= total_con_mio * 0.50:
                pos_txt = f"#{mi_pos_num} de {total_con_mio}  🟡"
            else:
                pos_txt = f"#{mi_pos_num} de {total_con_mio}  🔴"
            self.lbl_st_pos.set(pos_txt)
        else:
            self.lbl_st_pos.set("—")

        # Análisis de competitividad en la barra de estado
        if precio_mio and precios_comp:
            precio_min = min(precios_comp)
            prom       = sum(precios_comp) / len(precios_comp)
            dif_min    = (precio_mio - precio_min) / precio_min * 100
            dif_prom   = (precio_mio - prom) / prom * 100

            if dif_min < 0:
                analisis = f"✓ Sos el más barato (${abs(precio_mio - precio_min):,.0f} menos que el mínimo)"
            elif dif_min == 0:
                analisis = "= Igual al precio mínimo"
            elif dif_min <= 5:
                analisis = f"≈ Muy competitivo (+{dif_min:.1f}% sobre el mínimo)"
            else:
                analisis = (f"▲ Estás {dif_min:.1f}% sobre el más barato  |  "
                            f"{'sobre' if dif_prom >= 0 else 'bajo'} el promedio: "
                            f"{abs(dif_prom):.1f}%")
        else:
            analisis = "Doble click para abrir  ·  Verde = más barato  ·  ★ = tuyo"

        self.lbl_estado.config(
            text=f"«{catalog_name[:40]}» — {total} vendedores  |  {analisis}",
            fg="#155724")

    def _abrir_link(self, event):
        item = self.tree_comp.selection()
        if item:
            url = self.tree_comp.set(item[0], "link")
            if url and url.startswith("http"):
                webbrowser.open(url)


# ============================================================
# PESTAÑA: MIS RUBROS EN MELI
# ============================================================

class TabRubros(ttk.Frame):
    """
    Muestra tus rubros de Flexxus mapeados a categorías MeLi con
    sus comisiones. Elegís el margen objetivo y ves al instante
    qué precio poner en Flexxus por cada producto.
    """

    def __init__(self, nb, app_ref):
        super().__init__(nb)
        self.app = app_ref
        self._productos = []   # lista completa procesada
        self._rubros    = {}   # superrubro -> dict con datos
        self._tc        = 1420.0
        self._build()
        # Cargar cache al iniciar (no bloquea la UI)
        self.after(300, self._cargar_cache)

    # ── Construcción UI ──────────────────────────────────────

    def _build(self):
        # ── Barra superior ──
        fr_top = tk.Frame(self, bg=BG, padx=12, pady=10)
        fr_top.pack(fill=tk.X)

        _lbl(fr_top, "Archivo Flexxus:", fg=TX2, bg=BG).pack(side=tk.LEFT)
        self.var_arch = tk.StringVar(value="(ningún archivo)")
        tk.Label(fr_top, textvariable=self.var_arch,
                 bg=CARD, relief=tk.FLAT, font=FONT_N, fg=TX2,
                 anchor=tk.W, padx=8, width=38).pack(side=tk.LEFT, padx=(6,6))
        _btn(fr_top, "Elegir", self._elegir, bg=BLUE, padx=8).pack(side=tk.LEFT)
        self.btn_cargar = _btn(fr_top, "  ANALIZAR  ", self._cargar,
                               bg=GREEN, padx=14).pack(side=tk.LEFT, padx=(10,0))

        # ── Controles de margen y filtro ──
        fr_ctrl = tk.Frame(self, bg=BG, padx=12, pady=4)
        fr_ctrl.pack(fill=tk.X)

        _lbl(fr_ctrl, "Margen objetivo (%):", fg=TX2, bg=BG).pack(side=tk.LEFT)
        self.var_margen = tk.StringVar(value="20")
        self.var_margen.trace_add("write", self._on_margen_change)
        ttk.Entry(fr_ctrl, textvariable=self.var_margen,
                  font=(_FF, 11), width=6).pack(side=tk.LEFT, padx=(5,16))

        _lbl(fr_ctrl, "IVA (%):", fg=TX2, bg=BG).pack(side=tk.LEFT)
        self.var_iva = tk.StringVar(value="21")
        ttk.Entry(fr_ctrl, textvariable=self.var_iva,
                  font=(_FF, 11), width=5).pack(side=tk.LEFT, padx=(4,20))

        _lbl(fr_ctrl, "Filtrar rubro:", fg=TX2, bg=BG).pack(side=tk.LEFT)
        self.var_filtro = tk.StringVar(value="Todos")
        self.combo_rubro = ttk.Combobox(fr_ctrl, textvariable=self.var_filtro,
                                        state="readonly", width=32, font=FONT_N)
        self.combo_rubro.pack(side=tk.LEFT, padx=(5,20))
        self.combo_rubro.bind("<<ComboboxSelected>>", self._on_filtro)

        _lbl(fr_ctrl, "Buscar SKU o descripción:", fg=TX2, bg=BG).pack(side=tk.LEFT)
        self.var_buscar = tk.StringVar()
        ttk.Entry(fr_ctrl, textvariable=self.var_buscar,
                  font=(_FF, 11), width=22).pack(side=tk.LEFT, padx=(5,4))
        _btn(fr_ctrl, "Buscar", self._buscar_sku, bg=BLUE, padx=8).pack(side=tk.LEFT)

        self.lbl_estado = _lbl(fr_ctrl, "", FONT_S, fg=TX2, bg=BG)
        self.lbl_estado.pack(side=tk.RIGHT, padx=10)

        # ── Tabla rubros ──
        fr_rubros = tk.LabelFrame(self, text=" Rubros Flexxus → Categoría MeLi ",
                                  font=FONT_S, fg=TX2, bg=CARD,
                                  padx=4, pady=4, relief=tk.FLAT)
        fr_rubros.pack(fill=tk.X, padx=10, pady=(4,2))

        cols_r = ("superrubro","cat_meli","comision","n_prods",
                  "mg_actual","mg_real","mg_nec","ajuste")
        self.tree_rubros = ttk.Treeview(fr_rubros, columns=cols_r,
                                        show="headings", height=7,
                                        selectmode="browse")
        hdrs_r = [
            ("superrubro", "Rubro Flexxus",          220),
            ("cat_meli",   "Categoría MeLi",          180),
            ("comision",   "Comisión MeLi",             90),
            ("n_prods",    "Productos",                 70),
            ("mg_actual",  "Mg Flexxus prom.",         110),
            ("mg_real",    "Mg real en MeLi",          110),
            ("mg_nec",     f"Subir a (obj.%)",         110),
            ("ajuste",     "↑ Ajuste",                  80),
        ]
        for cid, txt, w in hdrs_r:
            self.tree_rubros.heading(cid, text=txt,
                command=lambda c=cid: self._sort_rubros(c))
            self.tree_rubros.column(cid, width=w, anchor="center")
        self.tree_rubros.column("superrubro", anchor="w")
        self.tree_rubros.column("cat_meli",   anchor="w")

        sb_r = ttk.Scrollbar(fr_rubros, orient="horizontal",
                              command=self.tree_rubros.xview)
        self.tree_rubros.configure(xscrollcommand=sb_r.set)
        sb_r.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_rubros.pack(fill=tk.X)
        self.tree_rubros.bind("<<TreeviewSelect>>", self._on_rubro_select)

        # Tags de color
        self.tree_rubros.tag_configure("rojo",     background="#FCE4D6")
        self.tree_rubros.tag_configure("amarillo",  background="#FFF2CC")
        self.tree_rubros.tag_configure("verde",     background="#E2EFDA")

        # ── Tabla productos del rubro seleccionado ──
        fr_prods = tk.LabelFrame(self, text=" Productos del rubro seleccionado ",
                                 font=FONT_S, fg=TX2, bg=CARD,
                                 padx=4, pady=4, relief=tk.FLAT)
        fr_prods.pack(fill=tk.BOTH, expand=True, padx=10, pady=(2,8))

        cols_p = ("sku","desc","rubro","comision","costo","precio_act",
                  "mg_flexxus","mg_real","precio_ars","precio_usd")
        self.tree_prods = ttk.Treeview(fr_prods, columns=cols_p,
                                       show="headings", height=10,
                                       selectmode="browse")
        hdrs_p = [
            ("sku",         "SKU",                    110),
            ("desc",        "Descripción",             260),
            ("rubro",       "Rubro MeLi",              160),
            ("comision",    "Comisión MeLi",            100),
            ("costo",       "Costo ARS",                110),
            ("precio_act",  "Precio actual ARS",        130),
            ("mg_flexxus",  "Mg Flexxus %",              90),
            ("mg_real",     "Mg real MeLi %",           100),
            ("precio_ars",  "PRECIO A CARGAR ARS",      140),
            ("precio_usd",  "PRECIO A CARGAR USD",      130),
        ]
        for cid, txt, w in hdrs_p:
            self.tree_prods.heading(cid, text=txt)
            self.tree_prods.column(cid, width=w, anchor="center")
        self.tree_prods.column("desc",  anchor="w")
        self.tree_prods.column("rubro", anchor="w")

        sb_py = ttk.Scrollbar(fr_prods, orient="vertical",
                              command=self.tree_prods.yview)
        sb_px = ttk.Scrollbar(fr_prods, orient="horizontal",
                              command=self.tree_prods.xview)
        self.tree_prods.configure(yscrollcommand=sb_py.set,
                                  xscrollcommand=sb_px.set)
        sb_py.pack(side=tk.RIGHT, fill=tk.Y)
        sb_px.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_prods.pack(fill=tk.BOTH, expand=True)

        self.tree_prods.tag_configure("rojo",    background="#FCE4D6")
        self.tree_prods.tag_configure("amarillo", background="#FFF2CC")
        self.tree_prods.tag_configure("verde",    background="#E2EFDA")

    # ── Cache ─────────────────────────────────────────────────

    CACHE_FILE = os.path.join(DIR, "cache_rubros.json")

    def _guardar_cache(self, ruta_arch):
        try:
            import json as _json
            data = {
                "archivo":    ruta_arch,
                "tc":         self._tc,
                "productos":  self._productos,
                "timestamp":  datetime.now().isoformat(),
            }
            with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                _json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print(f"[cache] No se pudo guardar: {e}")

    def _cargar_cache(self):
        try:
            import json as _json
            if not os.path.exists(self.CACHE_FILE):
                return False
            with open(self.CACHE_FILE, encoding="utf-8") as f:
                data = _json.load(f)
            self._tc        = data.get("tc", 1420.0)
            self._productos = data.get("productos", [])
            ruta_arch       = data.get("archivo", "")
            ts              = data.get("timestamp", "")
            if ruta_arch:
                self.var_arch.set(ruta_arch)
            self._construir_rubros()
            self._poblar_todo()
            fecha = ts[:16].replace("T", " ") if ts else "?"
            self.lbl_estado.config(
                text=f"Datos cargados del último análisis ({fecha})  —  "
                     f"Re-analizá si actualizaste el archivo",
                fg="#856404")
            return True
        except Exception as e:
            print(f"[cache] No se pudo cargar: {e}")
            return False

    # ── Acciones ─────────────────────────────────────────────

    def _elegir(self):
        ruta = filedialog.askopenfilename(
            title="Elegir Excel de Flexxus",
            filetypes=[("Excel", "*.xlsx *.xls"), ("Todos", "*.*")])
        if ruta:
            self.var_arch.set(ruta)

    def _margen_objetivo(self):
        try:
            return float(self.var_margen.get().replace("%","").strip())
        except ValueError:
            return 20.0

    def _cargar(self):
        ruta = self.var_arch.get()
        if not ruta or ruta == "(ningún archivo)":
            messagebox.showwarning("Falta archivo", "Elegí el archivo Excel de Flexxus.")
            return
        if not os.path.exists(ruta):
            messagebox.showerror("No encontrado", f"No se encontró:\n{ruta}")
            return

        self.lbl_estado.config(text="Cargando...", fg=BLUE)
        self._productos = []
        self._rubros    = {}
        self._limpiar_tablas()

        margen_obj = self._margen_objetivo()
        try:
            iva_default = float(self.var_iva.get())
        except ValueError:
            iva_default = 21.0

        def run():
            try:
                import analizar_margenes as am
                total_ref = [0]

                def prog(i, total, desc):
                    total_ref[0] = total
                    self.after(0, lambda ii=i, t=total, d=desc:
                        self.lbl_estado.config(
                            text=f"Analizando {ii}/{t}  {d[:30]}...", fg=BLUE))

                prods, tc, _ = am.procesar(ruta, margen_obj,
                                           progress_cb=prog, iva_default=iva_default)
                self._tc        = tc
                self._productos = prods
                self._guardar_cache(ruta)
                self._construir_rubros()
                self.after(0, self._poblar_todo)
            except Exception as e:
                import traceback
                self.after(0, lambda: self.lbl_estado.config(
                    text=f"Error: {e}", fg="#CC0000"))
                print(traceback.format_exc())

        threading.Thread(target=run, daemon=True).start()

    def _construir_rubros(self):
        """Agrupa productos por superrubro y calcula promedios."""
        from collections import defaultdict
        rubros = defaultdict(list)
        for p in self._productos:
            rubros[p["superrubro"]].append(p)

        self._rubros = {}
        for sr, items in rubros.items():
            tipos = list(items[0]["tipos"].keys()) if items else []
            t0 = tipos[0] if tipos else "Clasica"
            coms   = [i["tipos"].get(t0,{}).get("comision",0) for i in items]
            mgs    = [i["mg_flexxus"] for i in items if i["mg_flexxus"] is not None]
            mrs    = [i["tipos"].get(t0,{}).get("margen_real") for i in items
                      if i["tipos"].get(t0,{}).get("margen_real") is not None]
            mnecs  = [i["tipos"].get(t0,{}).get("mg_nec") for i in items
                      if i["tipos"].get(t0,{}).get("mg_nec") is not None]
            self._rubros[sr] = {
                "cat_raiz":  items[0]["cat_raiz"],
                "comision":  round(sum(coms)/len(coms), 1) if coms else 0,
                "n_prods":   len(items),
                "mg_actual": round(sum(mgs)/len(mgs), 1) if mgs else None,
                "mg_real":   round(sum(mrs)/len(mrs), 1) if mrs else None,
                "mg_nec":    round(sum(mnecs)/len(mnecs), 1) if mnecs else None,
                "items":     items,
            }

    def _poblar_todo(self):
        """Rellena combo de rubros y tabla de rubros."""
        opciones = ["Todos"] + sorted(self._rubros.keys())
        self.combo_rubro["values"] = opciones
        self.combo_rubro.set("Todos")
        self._poblar_rubros()
        n_ajuste = sum(1 for p in self._productos
                       if any((p["tipos"].get(t,{}).get("ajuste") or 0) > 0
                              for t in p["tipos"]))
        self.lbl_estado.config(
            text=f"{len(self._productos)} productos  |  {n_ajuste} necesitan ajuste",
            fg="#155724")

    def _poblar_rubros(self, filtro_texto=""):
        """Rellena la tabla de rubros con filtro opcional."""
        margen_obj = self._margen_objetivo()
        for row in self.tree_rubros.get_children():
            self.tree_rubros.delete(row)

        for sr, d in sorted(self._rubros.items(),
                             key=lambda x: (x[1]["mg_real"] or 999)):
            if filtro_texto and filtro_texto.lower() not in sr.lower():
                continue
            mg_real  = d["mg_real"]
            mg_nec   = d["mg_nec"]
            mg_act   = d["mg_actual"]
            ajuste   = round(mg_nec - mg_act, 1) if (mg_nec and mg_act) else None

            tag = ("rojo" if (mg_real is not None and mg_real < 0)
                   else "amarillo" if (mg_real is not None and mg_real < margen_obj)
                   else "verde")

            self.tree_rubros.insert("", "end", iid=sr, tags=(tag,), values=(
                sr,
                d["cat_raiz"] or "—",
                f"{d['comision']:.1f}%",
                d["n_prods"],
                f"{mg_act:.1f}%" if mg_act is not None else "—",
                f"{mg_real:.1f}%"  if mg_real is not None else "—",
                f"{mg_nec:.1f}%"   if mg_nec  is not None else "—",
                f"+{ajuste:.1f}%"  if (ajuste and ajuste > 0)
                else ("✓ OK"        if (ajuste is not None and ajuste <= 0) else "—"),
            ))

    def _poblar_prods(self, superrubro):
        """Rellena la tabla de productos para el rubro seleccionado."""
        for row in self.tree_prods.get_children():
            self.tree_prods.delete(row)

        if superrubro not in self._rubros:
            return

        margen_obj = self._margen_objetivo()
        tipos = list(self._rubros[superrubro]["items"][0]["tipos"].keys())
        t0 = tipos[0] if tipos else "Clasica"

        buscar = self.var_buscar.get().lower().strip()

        for p in self._rubros[superrubro]["items"]:
            if buscar and buscar not in str(p.get("desc","")).lower() \
                      and buscar not in str(p.get("sku","")).lower():
                continue

            td      = p["tipos"].get(t0, {})
            mg_real = td.get("margen_real")
            pv_ars  = td.get("precio_flexxus_ars")
            pv_usd  = td.get("precio_flexxus_usd")

            # Recalcular con margen_obj actual
            com = td.get("comision", 0)
            import analizar_margenes as am
            pv_ars  = am.precio_venta_necesario(p["costo_ars"], com, margen_obj)
            iva     = p.get("iva", 0) or 0
            factor_iva = 1 + iva/100
            pv_usd  = round(pv_ars / self._tc / factor_iva, 2) if pv_ars else None

            tag = ("rojo" if (mg_real is not None and mg_real < 0)
                   else "amarillo" if (mg_real is not None and mg_real < margen_obj)
                   else "verde")

            def fmt_ars(v):
                return f"${v:,.0f}" if v else "—"

            self.tree_prods.insert("", "end", tags=(tag,), values=(
                p.get("sku",""),
                p.get("desc",""),
                p.get("cat_raiz",""),
                f"{com:.1f}%",
                fmt_ars(p.get("costo_ars")),
                fmt_ars(p.get("precio_ars")),
                f"{p['mg_flexxus']:.1f}%" if p.get("mg_flexxus") is not None else "—",
                f"{mg_real:.1f}%"  if mg_real is not None else "—",
                fmt_ars(pv_ars),
                f"USD {pv_usd:,.2f}" if pv_usd else "—",
            ))

    def _limpiar_tablas(self):
        for row in self.tree_rubros.get_children():
            self.tree_rubros.delete(row)
        for row in self.tree_prods.get_children():
            self.tree_prods.delete(row)

    # ── Eventos ──────────────────────────────────────────────

    def _on_rubro_select(self, _):
        sel = self.tree_rubros.selection()
        if sel:
            self._poblar_prods(sel[0])

    def _on_filtro(self, _):
        filtro = self.var_filtro.get()
        self._poblar_rubros("" if filtro == "Todos" else filtro)

    def _buscar_sku(self):
        """Busca en TODOS los productos sin importar el rubro seleccionado."""
        texto = self.var_buscar.get().strip().lower()
        if not texto:
            return
        for row in self.tree_prods.get_children():
            self.tree_prods.delete(row)

        margen_obj = self._margen_objetivo()
        encontrados = 0

        import analizar_margenes as am
        for p in self._productos:
            if texto not in str(p.get("sku","")).lower() \
               and texto not in str(p.get("desc","")).lower():
                continue

            tipos = list(p["tipos"].keys())
            t0 = tipos[0] if tipos else "Clasica"
            td = p["tipos"].get(t0, {})
            mg_real = td.get("margen_real")
            com     = td.get("comision", 0)
            iva     = p.get("iva", 0) or 0
            factor_iva = 1 + iva / 100
            pv_ars  = am.precio_venta_necesario(p["costo_ars"], com, margen_obj)
            pv_usd  = round(pv_ars / self._tc / factor_iva, 2) if pv_ars and self._tc else None

            tag = ("rojo" if (mg_real is not None and mg_real < 0)
                   else "amarillo" if (mg_real is not None and mg_real < margen_obj)
                   else "verde")

            def fmt(v): return f"${v:,.0f}" if v else "—"

            self.tree_prods.insert("", "end", tags=(tag,), values=(
                p.get("sku",""),
                p.get("desc",""),
                p.get("cat_raiz", p.get("superrubro","")),
                f"{com:.1f}%",
                fmt(p.get("costo_ars")),
                fmt(p.get("precio_ars")),
                f"{p['mg_flexxus']:.1f}%" if p.get("mg_flexxus") is not None else "—",
                f"{mg_real:.1f}%"  if mg_real is not None else "—",
                fmt(pv_ars),
                f"USD {pv_usd:,.2f}" if pv_usd else "—",
            ))
            encontrados += 1

        self.lbl_estado.config(
            text=f"Búsqueda '{self.var_buscar.get()}': {encontrados} resultado(s)",
            fg="#155724" if encontrados else "#CC0000")

    def _on_buscar(self, *_):
        sel = self.tree_rubros.selection()
        if sel:
            self._poblar_prods(sel[0])

    def _on_margen_change(self, *_):
        """Cuando cambia el margen objetivo, recalcula todo."""
        if not self._rubros:
            return
        self._construir_rubros()
        filtro = self.var_filtro.get()
        self._poblar_rubros("" if filtro == "Todos" else filtro)
        sel = self.tree_rubros.selection()
        if sel:
            self._poblar_prods(sel[0])

    def _sort_rubros(self, col):
        """Ordena la tabla de rubros al hacer click en una columna."""
        rows = [(self.tree_rubros.set(r, col), r)
                for r in self.tree_rubros.get_children("")]
        rows.sort(key=lambda x: x[0])
        for i, (_, r) in enumerate(rows):
            self.tree_rubros.move(r, "", i)

# ============================================================
# VENTANA PRINCIPAL
# ============================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Comisiones Mercado Libre Argentina")
        self.geometry("960x860")
        self.minsize(820, 680)
        self.configure(bg=BG)
        self._token = None

        # ── ttk styles ────────────────────────────────────────
        s = ttk.Style()
        try:    s.theme_use("vista")
        except Exception:
            try: s.theme_use("clam")
            except Exception: pass

        # Notebook tabs
        s.configure("TNotebook",       background=BG,  borderwidth=0)
        s.configure("TNotebook.Tab",   font=FONT_H,    padding=[20, 8],
                    background="#CBD5E1", foreground=TX2)
        s.map("TNotebook.Tab",
              background=[("selected", CARD)],
              foreground=[("selected", TX1)])

        # Treeview
        s.configure("Treeview",
                    background=CARD, fieldbackground=CARD,
                    foreground=TX1,  font=FONT_N,
                    rowheight=26)
        s.configure("Treeview.Heading",
                    background=HDR2, foreground="white",
                    font=FONT_H,     relief=tk.FLAT)
        s.map("Treeview.Heading",
              background=[("active", BLUE_D)])
        s.map("Treeview",
              background=[("selected", BLUE)],
              foreground=[("selected", "white")])

        # Frame / LabelFrame
        s.configure("TFrame", background=BG)

        self._build()
        self._actualizar_estado_barra()

    def token_activo(self):
        if not self._token:
            self._token = obtener_token()
        return self._token

    def _actualizar_estado_barra(self):
        self._token = obtener_token()
        if self._token:
            bg, fg = "#DCFCE7", "#166534"
            txt = "  ✓  Conectado a la API de MeLi  —  comisiones en tiempo real"
        else:
            cfg = cargar_config()
            if cfg.get("client_id"):
                bg, fg = "#FEF9C3", "#92400E"
                txt = "  ⚠  Token vencido  —  hacé click en ⚙ Configurar API para reconectar"
            else:
                bg, fg = "#FEE2E2", "#991B1B"
                txt = ("  ○  Sin API  —  usando tabla de tasas locales  |  "
                       "Hacé click en ⚙ Configurar API para conectar MeLi")
        self.fr_estado.config(bg=bg)
        self.lbl_estado.config(text=txt, bg=bg, fg=fg)

    def _build(self):
        # ── Header oscuro ────────────────────────────────────
        hdr = tk.Frame(self, bg=HDR)
        hdr.pack(fill=tk.X)

        # Franja de acento amber (izquierda)
        tk.Frame(hdr, bg=AMBER, width=5).pack(side=tk.LEFT, fill=tk.Y)

        # Bloque de texto
        txt_blk = tk.Frame(hdr, bg=HDR, padx=14, pady=10)
        txt_blk.pack(side=tk.LEFT)
        _lbl(txt_blk, "Comisiones Mercado Libre Argentina",
             (_FF, 15, "bold"), "white", HDR).pack(anchor=tk.W)
        _lbl(txt_blk, "Consultas en tiempo real · Rubros Flexxus · Competencia",
             FONT_S, TX3, HDR).pack(anchor=tk.W)

        # Botón configurar (derecha)
        _btn(hdr, "⚙  Configurar API", self._config,
             bg=HDR2, padx=14, pady=8,
             font=FONT_H).pack(side=tk.RIGHT, padx=16, pady=12)

        # ── Barra de estado ──────────────────────────────────
        self.fr_estado = tk.Frame(self, height=32)
        self.fr_estado.pack(fill=tk.X)
        self.fr_estado.pack_propagate(False)

        self.lbl_estado = tk.Label(self.fr_estado, text="",
                                   font=FONT_S, anchor=tk.W,
                                   padx=14)
        self.lbl_estado.pack(fill=tk.BOTH, expand=True)

        # Separador
        tk.Frame(self, bg=BORD, height=1).pack(fill=tk.X)

        # ── Notebook ─────────────────────────────────────────
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=(10, 12))

        self.tab_c = TabConsulta(nb, self)
        nb.add(self.tab_c, text="  Consulta Individual  ")

        self.tab_r = TabRubros(nb, self)
        nb.add(self.tab_r, text="  Mis Rubros en MeLi  ")

        self.tab_comp = TabCompetencia(nb, self)
        nb.add(self.tab_comp, text="  Competencia en MeLi  ")

    def _config(self):
        DialogConfig(self)


# ============================================================
if __name__ == "__main__":
    App().mainloop()
