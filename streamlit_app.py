# -*- coding: utf-8 -*-
"""
COMISIONES MERCADO LIBRE ARGENTINA — Streamlit
Réplica completa de la app tkinter original.
"""

import streamlit as st
import pandas as pd
import requests
import json
import time
import os
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import consulta_comisiones as backend
import analizar_margenes   as am

# ════════════════════════════════════════════════════════════
# CONFIG / TOKEN
# ════════════════════════════════════════════════════════════
CONFIG_FILE    = os.path.join(PROJECT_DIR, "configuracion.json")
TOKEN_URL      = "https://api.mercadolibre.com/oauth/token"
MELI_SELLER_ID = 32331880

TIPOS_PUBLICACION = {
    "gold_premium": "Premium ⭐",
    "gold_special": "Clásica",
    "gold":         "Gold",
    "silver":       "Silver",
    "free":         "Gratis",
}

def cargar_config():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def guardar_config_file(data):
    cfg = cargar_config()
    cfg.update(data)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def token_vigente(cfg):
    token   = cfg.get("access_token")
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
            guardar_config_file({
                "access_token":     d["access_token"],
                "refresh_token":    d.get("refresh_token", cfg.get("refresh_token")),
                "token_expires_at": time.time() + d.get("expires_in", 21600),
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

# ════════════════════════════════════════════════════════════
# HELPERS API COMPETENCIA
# ════════════════════════════════════════════════════════════

def _safe_get(url, params=None, headers=None, timeout=8):
    try:
        r = requests.get(url, params=params, headers=headers or {}, timeout=timeout)
        try: body = r.json()
        except Exception: body = {}
        return r.status_code, body
    except Exception:
        return 0, {}

def _fmt_envio(ship):
    if not ship: return "Ver"
    tags = ship.get("tags", [])
    mode = ship.get("mode", "")
    free = ship.get("free_shipping", False)
    cost = ship.get("cost")
    if "fulfillment" in tags or mode == "fulfillment": return "🏭 Full"
    if free: return "🚚 Gratis"
    if cost and cost > 0: return f"${cost:,.0f}"
    if mode in ("me2", "me1"): return "Con envío"
    return "Ver"

def _normalizar_items(raw_list, fuente="catalog"):
    out = []
    for it in raw_list:
        if fuente == "search":
            seller = it.get("seller", {})
            out.append({
                "item_id":             it.get("id", ""),
                "seller_id":           seller.get("id", 0),
                "_nick":               seller.get("nickname", ""),
                "price":               it.get("price", 0),
                "listing_type_id":     it.get("listing_type_id", ""),
                "shipping":            it.get("shipping", {}),
                "accepts_mercadopago": it.get("accepts_mercadopago", True),
                "official_store_id":   it.get("official_store_id"),
            })
        else:
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

@st.cache_data(ttl=300, show_spinner=False)
def buscar_competencia(ean, desc="", token=None):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    def _get(url, params=None): return _safe_get(url, params=params, headers=h)

    STOP_WORDS = {"WEB","CAM","HD","USB","NEGRO","NEGRA","BLANCO","BLANCA","GRIS",
                  "NUEVO","CON","SIN","PARA","DE","LA","EL","LOS","LAS"}

    # ── Build queries ──
    queries = []
    if ean and ean.isdigit():
        queries.append(ean)
        if ean.startswith("0") and len(ean) > 8:
            queries.append(ean.lstrip("0"))
    if desc:
        palabras = [w for w in desc.upper().split() if w not in STOP_WORDS and len(w) > 2]
        ws_orig  = desc.split()
        for slc in [ws_orig[:6], ws_orig[:5], ws_orig[:4], ws_orig[:3],
                    palabras[:5], palabras[:4], palabras[:3]]:
            q = " ".join(slc).strip()
            if q and q not in queries and len(q) >= 3:
                queries.append(q)
    queries = list(dict.fromkeys(q for q in queries if len(q) >= 3))
    if not queries:
        return [], "", f"No se encontró «{(desc or ean)[:40]}» en MeLi."

    primary = queries[0]

    # ── FASE 1 + búsqueda directa en paralelo ──────────────────────
    # sites/MLA/search devuelve items con nicknames incluidos (1 sola llamada).
    # products/search devuelve catalog_id para matching más preciso.
    # Ambas se disparan simultáneamente; si el directo llega con datos
    # no necesitamos esperar las fases 2 y 3.
    def _catalog(q):
        sc, data = _get("https://api.mercadolibre.com/products/search",
                        {"site_id": "MLA", "q": q, "limit": 8, "status": "active"})
        if sc == 200:
            rs = data.get("results", [])
            if rs:
                return rs[0].get("id", ""), rs[0].get("name", "")
        return "", ""

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_cat    = ex.submit(_catalog, primary)
        f_direct = ex.submit(_get, "https://api.mercadolibre.com/sites/MLA/search",
                             {"q": primary, "limit": 50})
        catalog_id, catalog_name = f_cat.result()
        sc_dir, d_dir            = f_direct.result()

    direct_items = d_dir.get("results", []) if sc_dir == 200 else []

    # Fast path: búsqueda directa ya tiene suficientes resultados →
    # saltar FASE 2 y FASE 3 (los items ya traen nickname del vendedor)
    items_raw = []; fuente = "search"
    if len(direct_items) >= 5:
        items_raw = direct_items
        if not catalog_name:
            catalog_name = primary

    # Slow path: direct search vacío/escaso (SKU interno, EAN raro) →
    # usar catalog_id para búsqueda precisa
    if not items_raw and catalog_id:
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_items = ex.submit(_get, f"https://api.mercadolibre.com/products/{catalog_id}/items")
            f_srch  = ex.submit(_get, "https://api.mercadolibre.com/sites/MLA/search",
                                {"catalog_product_id": catalog_id, "limit": 50})
            sc1, d1 = f_items.result()
            sc2, d2 = f_srch.result()
        cat_items  = d1.get("results", []) if sc1 == 200 else []
        srch_items = d2.get("results", []) if sc2 == 200 else []
        if cat_items:
            items_raw = cat_items; fuente = "catalog"
        elif srch_items:
            items_raw = srch_items
        if not items_raw:
            items_raw = direct_items

    # Fallback: queries alternativas (solo si todo falló)
    if not items_raw:
        for q in queries[1:]:
            sc, data = _get("https://api.mercadolibre.com/sites/MLA/search",
                            {"q": q, "limit": 50})
            if sc == 200 and data.get("results"):
                items_raw = data["results"]
                if not catalog_name: catalog_name = q
                break

    if not items_raw:
        return [], catalog_name, f"No se encontró «{(desc or ean)[:40]}» en MeLi."

    # ── FASE 3: nicknames (solo para items sin nick — catalog endpoint) ──
    norm = _normalizar_items(items_raw, fuente=fuente)
    sellers_sin_nick = [it["seller_id"] for it in norm if not it.get("_nick")]
    nick_map = {}
    if sellers_sin_nick:
        ids_uniq = list(dict.fromkeys(sellers_sin_nick))[:20]
        sc, data = _get("https://api.mercadolibre.com/users",
                        {"ids": ",".join(str(s) for s in ids_uniq), "attributes": "id,nickname"})
        if sc == 200:
            for entry in data:
                body = entry.get("body", {})
                nick_map[body.get("id")] = body.get("nickname", "?")

    items_enriquecidos = []
    for it in norm:
        iid    = it.get("item_id", "")
        digits = iid.replace("MLA", "").lstrip("-")
        plink  = (f"https://articulo.mercadolibre.com.ar/MLA-{digits}" if digits
                  else f"https://www.mercadolibre.com.ar/p/{catalog_id or 'MLA'}")
        lt     = it.get("listing_type_id", "")
        acepta = it.get("accepts_mercadopago", True)
        cuotas = "—" if not acepta else ("12 s/int ⭐" if lt == "gold_premium" else "hasta 12")
        sid    = it.get("seller_id", 0)
        nick   = it.get("_nick") or nick_map.get(sid) or str(sid) or "?"
        items_enriquecidos.append({
            "item_id":   iid,
            "precio":    it["price"],
            "seller_id": sid,
            "vendedor":  nick,
            "tipo":      TIPOS_PUBLICACION.get(lt, lt or "—"),
            "cuotas":    cuotas,
            "envio":     _fmt_envio(it.get("shipping", {})),
            "permalink": plink,
            "es_propio": sid == MELI_SELLER_ID,
            "official":  bool(it.get("official_store_id")),
        })

    items_enriquecidos.sort(key=lambda x: x["precio"])
    return items_enriquecidos, catalog_name, None

# ════════════════════════════════════════════════════════════
# STREAMLIT CONFIG
# ════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Comisiones MeLi Argentina",
    page_icon="🛒",
    layout="wide",
)

st.markdown("""
<style>
.header-bar {
    background: #0F172A;
    padding: 14px 20px;
    border-left: 5px solid #D97706;
    border-radius: 6px;
    margin-bottom: 12px;
}
.header-bar h2 { color: white; margin: 0 0 2px 0; font-size: 1.25rem; }
.header-bar p  { color: #94A3B8; margin: 0; font-size: 0.82rem; }
.section-title { font-size: 0.95rem; font-weight: 700; color: #1E293B;
                 border-bottom: 2px solid #E2E8F0; padding-bottom: 4px; margin: 8px 0; }
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────
st.markdown("""
<div class="header-bar">
  <h2>🛒 Comisiones Mercado Libre Argentina</h2>
  <p>Consultas en tiempo real · Rubros Flexxus · Competencia</p>
</div>
""", unsafe_allow_html=True)

# ── Token status ─────────────────────────────────────────────
token = obtener_token()
if token:
    st.success("✓  Conectado a la API de MeLi — comisiones en tiempo real")
else:
    cfg = cargar_config()
    if cfg.get("client_id"):
        st.warning("⚠  Token vencido — reconectá en la barra lateral")
    else:
        st.error("○  Sin API — configurá las credenciales en la barra lateral")

# ── Sidebar ──────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configurar API")
    cfg = cargar_config()
    cid = st.text_input("Client ID (App ID)", value=cfg.get("client_id", ""))
    sec = st.text_input("Client Secret", value=cfg.get("client_secret", ""), type="password")
    if st.button("💾 Guardar credenciales"):
        if cid:
            guardar_config_file({"client_id": cid, "client_secret": sec})
            st.success("Guardado. Reiniciá para reconectar.")
            st.rerun()
    st.markdown("---")
    st.caption(f"SELLER_ID: `{MELI_SELLER_ID}`")

# ════════════════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════════════════
tab_rubros, tab_consulta, tab_comp, tab_excel = st.tabs([
    "📦  Mis Rubros en MeLi",
    "🔍  Consulta Individual",
    "🏪  Competencia en MeLi",
    "📊  Procesar Excel",
])

# ════════════════════════════════════════════════════════════
# TAB 1: MIS RUBROS EN MELI  (pestaña principal)
# ════════════════════════════════════════════════════════════
with tab_rubros:
    st.subheader("Mis Rubros en MeLi")
    st.caption("Cargá tu Excel de Flexxus para ver comisiones, márgenes reales y precio a cargar por rubro y producto.")

    col_up, col_cfg = st.columns([3, 2])
    with col_up:
        archivo = st.file_uploader(
            "📂 Elegir archivo Excel de Flexxus (.xlsx)",
            type=["xlsx", "xls"],
            key="archivo_rubros",
        )
    with col_cfg:
        margen_obj_r = st.number_input("Margen objetivo (%)", min_value=1.0, max_value=80.0,
                                        value=20.0, step=1.0, key="margen_rubros")
        iva_default  = st.number_input("IVA por defecto (%)", min_value=0.0, max_value=27.0,
                                        value=21.0, step=0.5, key="iva_rubros")

    analizar_btn = st.button("⚡ ANALIZAR", type="primary", key="btn_analizar_rubros",
                              disabled=(archivo is None))

    # ── Guardar/recuperar resultado del análisis en session_state ──
    if analizar_btn and archivo is not None:
        import tempfile, io
        with st.spinner("Analizando productos... (puede tardar 1-2 min según la cantidad)"):
            # Guardar el archivo subido en un temp file para que analizar_margenes lo lea
            suffix = ".xlsx" if archivo.name.endswith(".xlsx") else ".xls"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(archivo.read())
            tmp.flush()
            tmp_path = tmp.name
            tmp.close()

            msgs = []
            def prog(i, total, desc):
                pass  # no podemos actualizar UI desde thread, omitimos

            try:
                prods, tc, _ = am.procesar(tmp_path, margen_obj_r,
                                            progress_cb=prog, iva_default=iva_default)
                st.session_state["rubros_prods"]    = prods
                st.session_state["rubros_tc"]       = tc
                st.session_state["rubros_margen"]   = margen_obj_r
                st.session_state["rubros_archivo"]  = archivo.name
                st.success(f"✓ {len(prods)} productos procesados — TC: ${tc:,.0f}")
            except Exception as e:
                st.error(f"Error al procesar: {e}")
            finally:
                try: os.unlink(tmp_path)
                except Exception: pass

    # ── Mostrar resultados ──────────────────────────────────
    prods = st.session_state.get("rubros_prods", [])
    tc    = st.session_state.get("rubros_tc", 1420.0)
    margen_obj_actual = st.session_state.get("rubros_margen", 20.0)

    if prods:
        archivo_nombre = st.session_state.get("rubros_archivo", "")
        st.info(f"📁 Datos cargados de: **{archivo_nombre}**  |  "
                f"{len(prods)} productos  |  TC: ${tc:,.0f}  |  "
                f"Margen objetivo: {margen_obj_actual:.0f}%")

        # ── Construir resumen por rubro ──────────────────────
        rubros_dict = defaultdict(list)
        for p in prods:
            rubros_dict[p["superrubro"]].append(p)

        rubros_rows = []
        for sr, items in rubros_dict.items():
            tipos = list(items[0]["tipos"].keys()) if items else []
            t0 = tipos[0] if tipos else "Clasica"
            coms  = [i["tipos"].get(t0,{}).get("comision",0) for i in items]
            mgs   = [i["mg_flexxus"] for i in items if i["mg_flexxus"] is not None]
            mrs   = [i["tipos"].get(t0,{}).get("margen_real") for i in items
                     if i["tipos"].get(t0,{}).get("margen_real") is not None]
            mnecs = [i["tipos"].get(t0,{}).get("mg_nec") for i in items
                     if i["tipos"].get(t0,{}).get("mg_nec") is not None]
            mg_act  = round(sum(mgs)/len(mgs),1) if mgs else None
            mg_real = round(sum(mrs)/len(mrs),1) if mrs else None
            mg_nec  = round(sum(mnecs)/len(mnecs),1) if mnecs else None
            ajuste  = round(mg_nec - mg_act, 1) if (mg_nec and mg_act) else None
            cat_raiz = items[0]["cat_raiz"] if items else ""

            rubros_rows.append({
                "Rubro Flexxus":     sr,
                "Categoría MeLi":    cat_raiz or "—",
                "Comisión MeLi %":   round(sum(coms)/len(coms), 1) if coms else 0,
                "Productos":         len(items),
                "Mg Flexxus prom %": mg_act,
                "Mg real MeLi %":    mg_real,
                "Mg necesario %":    mg_nec,
                "↑ Ajuste":          f"+{ajuste:.1f}%" if (ajuste and ajuste > 0)
                                     else ("✓ OK" if ajuste is not None else "—"),
                "_mg_real":          mg_real,  # para ordenar y colorear
            })

        rubros_rows.sort(key=lambda x: (x["_mg_real"] or 999))

        # Filtros
        col_f1, col_f2, col_f3 = st.columns([2, 2, 2])
        with col_f1:
            opciones_filtro = ["Todos"] + sorted(rubros_dict.keys())
            filtro_rubro = st.selectbox("Filtrar rubro", opciones_filtro, key="filtro_rubro_tab")
        with col_f2:
            buscar_sku = st.text_input("Buscar SKU o descripción", key="buscar_sku_tab")
        with col_f3:
            st.write("")

        # ── Tabla de rubros ──────────────────────────────────
        st.markdown('<div class="section-title">Rubros Flexxus → Categoría MeLi</div>',
                    unsafe_allow_html=True)

        cols_mostrar = ["Rubro Flexxus","Categoría MeLi","Comisión MeLi %",
                        "Productos","Mg Flexxus prom %","Mg real MeLi %",
                        "Mg necesario %","↑ Ajuste"]

        df_rubros = pd.DataFrame([{k: v for k,v in r.items() if k != "_mg_real"}
                                   for r in rubros_rows], columns=cols_mostrar)

        # Colorear filas según mg_real
        def color_rubro(row):
            mg = next((r["_mg_real"] for r in rubros_rows
                       if r["Rubro Flexxus"] == row["Rubro Flexxus"]), None)
            if mg is None: return [""] * len(row)
            if mg < 0:   color = "background-color: #FCE4D6"
            elif mg < margen_obj_actual: color = "background-color: #FFF2CC"
            else:        color = "background-color: #E2EFDA"
            return [color] * len(row)

        styled_rubros = df_rubros.style.apply(color_rubro, axis=1)

        selected_rubro = st.dataframe(
            styled_rubros,
            use_container_width=True,
            height=280,
            on_select="rerun",
            selection_mode="single-row",
            key="tabla_rubros",
        )

        # ── Tabla de productos ───────────────────────────────
        rubro_sel = None
        if selected_rubro and selected_rubro.selection and selected_rubro.selection.rows:
            idx_sel   = selected_rubro.selection.rows[0]
            rubro_sel = rubros_rows[idx_sel]["Rubro Flexxus"]

        # Si hay filtro por selectbox, usar ese
        if filtro_rubro != "Todos":
            rubro_sel = filtro_rubro

        st.markdown('<div class="section-title">Productos del rubro seleccionado</div>',
                    unsafe_allow_html=True)

        prods_filtrados = prods
        if rubro_sel:
            prods_filtrados = [p for p in prods if p["superrubro"] == rubro_sel]
        if buscar_sku:
            txt_b = buscar_sku.lower()
            prods_filtrados = [p for p in prods_filtrados
                               if txt_b in str(p.get("sku","")).lower()
                               or txt_b in str(p.get("desc","")).lower()]

        filas_prods = []
        for p in prods_filtrados:
            tipos = list(p["tipos"].keys())
            t0    = tipos[0] if tipos else "Clasica"
            td    = p["tipos"].get(t0, {})
            mg_real = td.get("margen_real")
            com     = td.get("comision", 0)
            pv_ars  = am.precio_venta_necesario(p["costo_ars"], com, margen_obj_actual)
            factor_iva = 1 + (p.get("iva") or 0) / 100
            pv_usd  = round(pv_ars / tc / factor_iva, 2) if pv_ars and tc else None
            filas_prods.append({
                "SKU":              p.get("sku",""),
                "Descripción":      p.get("desc",""),
                "Rubro MeLi":       p.get("cat_raiz",""),
                "Comisión %":       f"{com:.1f}%",
                "Costo ARS":        f"${p.get('costo_ars',0):,.0f}",
                "Precio actual ARS":f"${p.get('precio_ars',0):,.0f}",
                "Mg Flexxus %":     f"{p['mg_flexxus']:.1f}%" if p.get("mg_flexxus") is not None else "—",
                "Mg real MeLi %":   f"{mg_real:.1f}%" if mg_real is not None else "—",
                "PRECIO A CARGAR ARS": f"${pv_ars:,.0f}" if pv_ars else "—",
                "PRECIO A CARGAR USD": f"USD {pv_usd:,.2f}" if pv_usd else "—",
                "_mg_real": mg_real,
            })

        def color_prod(row):
            mg = row.get("_mg_real") if isinstance(row, dict) else None
            # Para styled df necesitamos acceder por nombre
            return [""] * len(row)

        df_prods = pd.DataFrame([{k:v for k,v in f.items() if k!="_mg_real"}
                                  for f in filas_prods])

        if not df_prods.empty:
            def color_prod_row(row):
                mg_val = next((f["_mg_real"] for f in filas_prods
                               if f["SKU"] == row["SKU"] and f["Descripción"] == row["Descripción"]), None)
                if mg_val is None: return [""] * len(row)
                if mg_val < 0:   c = "background-color: #FCE4D6"
                elif mg_val < margen_obj_actual: c = "background-color: #FFF2CC"
                else: c = "background-color: #E2EFDA"
                return [c] * len(row)

            st.dataframe(
                df_prods.style.apply(color_prod_row, axis=1),
                use_container_width=True,
                height=380,
                key="tabla_prods",
            )
            st.caption(f"🟢 Verde = margen OK  🟡 Amarillo = bajo el objetivo  🔴 Rojo = margen negativo  |  {len(filas_prods)} productos")
        else:
            if rubro_sel or buscar_sku:
                st.info("No hay productos para ese filtro.")
            else:
                st.info("Hacé clic en un rubro arriba para ver sus productos.")
    else:
        st.info("⬆️ Subí el Excel de Flexxus arriba y presioná **ANALIZAR** para empezar.")


# ════════════════════════════════════════════════════════════
# TAB 2: CONSULTA INDIVIDUAL
# ════════════════════════════════════════════════════════════
with tab_consulta:
    st.subheader("Consulta Individual de Comisiones")

    col_q1, col_q2 = st.columns([3, 1])
    with col_q1:
        q_texto = st.text_input("Escribí el nombre del producto",
                                 placeholder="Ej: Smart TV 55 4K, Notebook Intel i7...",
                                 key="consulta_q")
    with col_q2:
        st.write("")
        buscar_cat_btn = st.button("🔍 Buscar categoría", key="btn_buscar_cat")

    if buscar_cat_btn and q_texto.strip():
        with st.spinner("Buscando categorías en MeLi..."):
            cats = backend.buscar_categoria(q_texto.strip(), 8)
        if cats:
            st.session_state["consulta_cats"] = cats
            st.success(f"Se encontraron {len(cats)} categorías.")
        else:
            st.warning("No se encontraron categorías. Probá con otro término.")
            st.session_state["consulta_cats"] = []

    cats = st.session_state.get("consulta_cats", [])
    if cats:
        opciones_cat = []
        for c in cats:
            dom = c.get("domain_name",""); nom = c.get("category_name",""); cid_c = c.get("category_id","")
            lbl = f"{dom} > {nom}" if dom and nom and dom != nom else (dom or nom)
            opciones_cat.append(f"{lbl}  ({cid_c})")

        cat_elegida = st.selectbox("Categoría de MeLi", opciones_cat, key="cat_sel")
        idx_cat = opciones_cat.index(cat_elegida) if cat_elegida in opciones_cat else 0

        st.markdown("---")
        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            precio_str = st.text_input("Precio de venta ($)", placeholder="Ej: 150000", key="cons_precio")
        with col_p2:
            costo_str  = st.text_input("Costo neto ($)",      placeholder="Ej: 90000",  key="cons_costo")
        with col_p3:
            margen_obj_c = st.number_input("Margen objetivo (%)", value=20.0, min_value=1.0, key="cons_margen")

        st.caption("Si solo tenés el costo, dejá Precio vacío y te calculamos el precio a publicar.")

        calcular_btn = st.button("⚡ CALCULAR COMISIONES", type="primary", key="btn_calcular_cons")

        if calcular_btn:
            cat_data = cats[idx_cat]
            cat_id   = cat_data.get("category_id","")
            cat_nom  = cat_data.get("domain_name") or cat_data.get("category_name","")

            precio = None
            if precio_str.strip():
                try: precio = float(precio_str.replace(",",".").replace("$","").strip())
                except: st.error("Precio inválido"); st.stop()

            costo = None
            if costo_str.strip():
                try: costo = float(costo_str.replace(",",".").replace("$","").strip())
                except: st.error("Costo inválido"); st.stop()

            if precio is None and costo is None:
                st.warning("Ingresá al menos el precio o el costo.")
            else:
                with st.spinner("Calculando..."):
                    cat_raiz = backend.obtener_raiz_categoria(cat_id)
                    tok = obtener_token()
                    res = {}
                    via_api = False
                    for tipo_nom, tipo_id in backend.TIPOS_PUBLICACION.items():
                        precio_ref = precio if precio else backend.calcular_precio_sugerido(
                            costo, 15.5, margen_obj_c)
                        pct = fee = None
                        if tok:
                            resp = requests.get(
                                "https://api.mercadolibre.com/sites/MLA/listing_prices",
                                params={"price": precio_ref, "listing_type_id": tipo_id,
                                        "category_id": cat_id},
                                headers={"Authorization": f"Bearer {tok}"}, timeout=12)
                            if resp.status_code == 200:
                                d = resp.json()
                                monto = d.get("sale_fee_amount", 0)
                                base  = d.get("amount", precio_ref)
                                pct   = round(monto/base*100, 2) if base > 0 else 0
                                fee   = round(monto, 2)
                                via_api = True
                        if pct is None:
                            tasas = backend.obtener_comision(cat_raiz)
                            pct   = tasas.get(tipo_nom, 14.0)
                            fee   = round((precio_ref or 0) * pct / 100, 2)
                        d_res = {"pct": pct}
                        if precio:
                            fee_r = precio * pct / 100
                            neto  = precio - fee_r
                            d_res.update({"fee": fee_r, "neto": neto})
                            if costo:
                                gan = neto - costo
                                mg  = gan / precio * 100
                                sug = backend.calcular_precio_sugerido(costo, pct, margen_obj_c)
                                d_res.update({"ganancia": gan, "margen": mg, "precio_sug": sug})
                        else:
                            sug      = backend.calcular_precio_sugerido(costo, pct, margen_obj_c)
                            fee_sug  = sug * pct / 100
                            neto_sug = sug - fee_sug
                            d_res.update({"modo_inverso": True, "precio_sug": sug,
                                          "fee": fee_sug, "neto": neto_sug,
                                          "ganancia": neto_sug - costo})
                        res[tipo_nom] = d_res

                fuente_txt = "API en tiempo real ✓" if via_api else "tabla local"
                st.info(f"📂 Categoría: **{cat_nom}** · Raíz: {cat_raiz} · Fuente: {fuente_txt}")

                col_c, col_p = st.columns(2)
                cards = list(res.items())
                for col_idx, (tipo_nom, d) in enumerate(cards):
                    col_use = col_c if col_idx == 0 else col_p
                    with col_use:
                        color = "#1E293B" if tipo_nom == "Clasica" else "#059669"
                        st.markdown(f"""
                        <div style='border:2px solid {color};border-radius:8px;padding:14px;'>
                        <h4 style='color:{color};margin:0 0 10px 0'>PUBLICACIÓN {tipo_nom.upper()}</h4>
                        """, unsafe_allow_html=True)
                        if d.get("modo_inverso"):
                            st.metric("PUBLICAR A", f"${d['precio_sug']:,.2f}")
                            m1, m2 = st.columns(2)
                            m1.metric("Comisión", f"{d['pct']:.1f}%")
                            m2.metric("Comisión $", f"${d['fee']:,.2f}")
                            m1.metric("Neto cobrás", f"${d['neto']:,.2f}")
                            m2.metric("Ganancia", f"${d['ganancia']:,.2f}")
                        else:
                            m1, m2 = st.columns(2)
                            m1.metric("Comisión %", f"{d['pct']:.1f}%")
                            m2.metric("Comisión $", f"${d['fee']:,.2f}")
                            m1.metric("Lo que cobrás", f"${d['neto']:,.2f}")
                            if "margen" in d:
                                mg = d["margen"]
                                delta_color = "normal" if mg >= margen_obj_c else "inverse"
                                m2.metric("Tu Margen", f"{mg:.1f}%",
                                          delta=f"obj: {margen_obj_c:.0f}%",
                                          delta_color=delta_color)
                                m1.metric("Ganancia $", f"${d['ganancia']:,.2f}")
                                if d.get("precio_sug"):
                                    st.metric(f"Precio sugerido ({margen_obj_c:.0f}% mg)",
                                              f"${d['precio_sug']:,.2f}")
                        st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# TAB 3: COMPETENCIA EN MELI
# ════════════════════════════════════════════════════════════
with tab_comp:
    st.subheader("Competencia en MeLi")

    col_ci, col_cb = st.columns([4, 1])
    with col_ci:
        comp_query = st.text_input(
            "Buscar por EAN, código de barra o descripción",
            placeholder="Ej: 7798164740528 · Samsung Galaxy S24 · MacBook Pro M3",
            key="comp_q2",
        )
    with col_cb:
        st.write("")
        comp_buscar = st.button("🔍 BUSCAR", type="primary", key="btn_comp2")

    # Buscar en cache de productos cargados (tab rubros) por SKU/EAN
    prods_cache = st.session_state.get("rubros_prods", [])
    prod_encontrado = None
    if comp_query.strip() and prods_cache:
        txt_up = comp_query.strip().upper()
        for p in prods_cache:
            if (str(p.get("sku","")).upper() == txt_up or
                str(p.get("ean","")).strip() == comp_query.strip()):
                prod_encontrado = p; break

    col_mio2, col_comp2 = st.columns([2, 5])

    with col_mio2:
        st.markdown("**👤 Mi Producto**")
        if prod_encontrado:
            st.write(f"**SKU:** {prod_encontrado.get('sku','—')}")
            st.write(f"**Desc:** {str(prod_encontrado.get('desc','—'))[:50]}")
            st.write(f"**EAN:** {prod_encontrado.get('ean','—')}")
            st.write(f"**Costo ARS:** ${prod_encontrado.get('costo_ars',0):,.0f}")
            st.write(f"**Precio actual:** ${prod_encontrado.get('precio_ars',0):,.0f}")
            mg_f = prod_encontrado.get("mg_flexxus")
            st.write(f"**Mg Flexxus:** {f'{mg_f:.1f}%' if mg_f is not None else '—'}")
            tipos = list(prod_encontrado.get("tipos",{}).keys())
            if tipos:
                t0  = tipos[0]; cat = prod_encontrado.get("cat_raiz","—")
                com = prod_encontrado["tipos"][t0].get("comision","—")
                st.write(f"**Cat. MeLi:** {cat}")
                st.write(f"**Comisión:** {f'{com:.1f}%' if isinstance(com, float) else str(com)}")
            precio_default = int(prod_encontrado.get("precio_ars", 0))
        else:
            st.caption("(cargá el Excel en 'Mis Rubros' para ver tus datos acá)")
            precio_default = 0

        precio_pub2 = st.number_input("Precio a publicar ($)", min_value=0.0,
                                       value=float(precio_default), step=100.0,
                                       key="precio_pub2")

        if prod_encontrado and precio_pub2 > 0:
            tipos = list(prod_encontrado.get("tipos",{}).keys())
            if tipos:
                t0  = tipos[0]
                com = prod_encontrado["tipos"][t0].get("comision", 0)
                fee  = precio_pub2 * com / 100
                neto = precio_pub2 - fee
                costo = prod_encontrado.get("costo_ars", 0) or 0
                mg = (neto - costo) / precio_pub2 * 100 if precio_pub2 > 0 else 0
                st.write(f"**Lo que cobrás:** ${neto:,.0f}")
                color_mg = "🟢" if mg >= 20 else "🟡" if mg >= 0 else "🔴"
                st.write(f"**Margen real:** {color_mg} {mg:.1f}%")

    if comp_buscar and comp_query.strip():
        if prod_encontrado:
            ean_buscar  = prod_encontrado.get("ean","").strip()
            desc_buscar = prod_encontrado.get("desc","")
        else:
            raw = comp_query.strip()
            ean_buscar  = raw if raw.replace("0","").isdigit() else ""
            desc_buscar = raw if not ean_buscar else ""
        with st.spinner(f"Buscando «{desc_buscar or ean_buscar}»..."):
            items, cat_name, err = buscar_competencia(ean_buscar, desc_buscar, obtener_token())
        st.session_state["comp2_items"]   = items
        st.session_state["comp2_catalog"] = cat_name
        st.session_state["comp2_err"]     = err

    items2       = st.session_state.get("comp2_items", [])
    catalog_name2= st.session_state.get("comp2_catalog", "")
    comp2_err    = st.session_state.get("comp2_err", None)

    with col_comp2:
        if comp2_err and not items2:
            st.warning(comp2_err)
        elif items2:
            if catalog_name2:
                st.markdown(f"**Catálogo:** {catalog_name2} — **{len(items2)} vendedores**")

            precio_mio2 = precio_pub2 if precio_pub2 > 0 else None
            precios_comp2 = [it["precio"] for it in items2
                             if not it.get("es_propio") and it["precio"] > 0]

            if precios_comp2:
                pmin = min(precios_comp2); pprom = sum(precios_comp2)/len(precios_comp2); pmax = max(precios_comp2)
                mi_pos = None
                if precio_mio2:
                    menores = sum(1 for p in precios_comp2 if p < precio_mio2)
                    mi_pos  = menores + 1
                    total_c = len(precios_comp2) + 1
                    if mi_pos == 1: pos_str = "#1 ✅ EL MÁS BARATO"
                    elif mi_pos <= total_c * 0.25: pos_str = f"#{mi_pos} de {total_c} 🟢"
                    elif mi_pos <= total_c * 0.50: pos_str = f"#{mi_pos} de {total_c} 🟡"
                    else: pos_str = f"#{mi_pos} de {total_c} 🔴"
                else: pos_str = "—"

                c1,c2,c3,c4,c5 = st.columns(5)
                c1.metric("💙 Mínimo",       f"${pmin:,.0f}")
                c2.metric("⬛ Promedio",      f"${pprom:,.0f}")
                c3.metric("🔴 Máximo",        f"${pmax:,.0f}")
                c4.metric("🟠 Competidores",  str(len(precios_comp2)))
                c5.metric("🎯 Tu posición",   pos_str)

                if precio_mio2:
                    dif_min = (precio_mio2 - pmin) / pmin * 100
                    dif_prom= (precio_mio2 - pprom)/ pprom* 100
                    if dif_min < 0:   st.success(f"✓ Sos el más barato (${abs(precio_mio2-pmin):,.0f} menos que el mínimo)")
                    elif dif_min == 0: st.info("= Igual al precio mínimo")
                    elif dif_min <= 5: st.info(f"≈ Muy competitivo (+{dif_min:.1f}% sobre el mínimo)")
                    else: st.warning(f"▲ Estás {dif_min:.1f}% sobre el más barato | {'sobre' if dif_prom>=0 else 'bajo'} el promedio: {abs(dif_prom):.1f}%")

            # Tabla HTML con colores y links
            filas_html = []
            pos_html = 0
            items_ord2 = sorted(items2, key=lambda x: x["precio"])
            mi_insertado = False
            filas_lista = []
            if precio_mio2:
                for it in items_ord2:
                    if not mi_insertado and it["precio"] > precio_mio2 and not it.get("es_propio"):
                        filas_lista.append({"_mi": True, "precio": precio_mio2}); mi_insertado = True
                    filas_lista.append(it)
                if not mi_insertado: filas_lista.append({"_mi": True, "precio": precio_mio2})
            else: filas_lista = items_ord2

            for it in filas_lista:
                pos_html += 1
                if it.get("_mi"):
                    filas_html.append(
                        f"<tr style='background:#FEF3C7;color:#92400E;font-weight:700'>"
                        f"<td style='padding:5px 8px'>▶ #{pos_html}</td>"
                        f"<td style='padding:5px 8px'>${it['precio']:,.0f}</td>"
                        f"<td colspan='5' style='padding:5px 8px'>👤 TU PRECIO</td></tr>")
                    continue
                precio_it = it["precio"]; vend = it.get("vendedor","?")
                if it.get("official"): vend = "🏪 " + vend
                if it.get("es_propio"): vend = "★ " + vend
                link = it.get("permalink","#"); tipo = it.get("tipo","—")
                envio = it.get("envio","—"); cuotas = it.get("cuotas","—")
                if it.get("es_propio"): rs = "background:#DBEAFE;color:#1D4ED8;font-weight:700"
                elif pos_html == 1: rs = "background:#D1FAE5;color:#065F46;font-weight:700"
                elif precio_mio2 and precio_it > precio_mio2*1.10: rs = "background:#FEE2E2;color:#991B1B"
                else: rs = ""
                filas_html.append(
                    f"<tr style='{rs}'>"
                    f"<td style='padding:5px 8px'>#{pos_html}</td>"
                    f"<td style='padding:5px 8px'>${precio_it:,.0f}</td>"
                    f"<td style='padding:5px 8px'>{vend}</td>"
                    f"<td style='padding:5px 8px;text-align:center'>{tipo}</td>"
                    f"<td style='padding:5px 8px;text-align:center'>{envio}</td>"
                    f"<td style='padding:5px 8px;text-align:center'>{cuotas}</td>"
                    f"<td style='padding:5px 8px;text-align:center'>"
                    f"<a href='{link}' target='_blank' style='color:#3B82F6'>↗</a></td></tr>")

            tabla = f"""
            <table style='width:100%;border-collapse:collapse;font-size:0.85rem;
                          border:1px solid #CBD5E1;border-radius:6px'>
              <thead><tr style='background:#1E293B;color:white'>
                <th style='padding:7px 8px;text-align:left'>#</th>
                <th style='padding:7px 8px;text-align:left'>Precio</th>
                <th style='padding:7px 8px;text-align:left'>Vendedor</th>
                <th style='padding:7px 8px;text-align:center'>Publicación</th>
                <th style='padding:7px 8px;text-align:center'>Envío</th>
                <th style='padding:7px 8px;text-align:center'>Cuotas</th>
                <th style='padding:7px 8px;text-align:center'>Ver</th>
              </tr></thead>
              <tbody>{''.join(filas_html)}</tbody>
            </table>"""
            st.markdown(tabla, unsafe_allow_html=True)
            st.caption("🟢 Verde = más barato · 🟡 Ámbar = tu precio · 🔵 Azul = tuyo · ★ = tu tienda")
        else:
            st.info("Ingresá un EAN o descripción y presioná BUSCAR.")


# ════════════════════════════════════════════════════════════
# TAB 4: PROCESAR EXCEL (análisis de márgenes completo)
# ════════════════════════════════════════════════════════════
with tab_excel:
    st.subheader("Procesar Excel — Análisis de Márgenes Flexxus vs MeLi")
    st.caption("Genera un Excel detallado con comisiones, márgenes reales y precios sugeridos por producto.")

    col_e1, col_e2 = st.columns([3, 2])
    with col_e1:
        archivo_excel = st.file_uploader(
            "📂 Excel de Flexxus",
            type=["xlsx","xls"],
            key="archivo_excel_tab",
        )
    with col_e2:
        margen_obj_e = st.number_input("Margen objetivo (%)", value=20.0, min_value=1.0, key="margen_excel")
        nombre_salida = st.text_input("Nombre del archivo resultado",
                                       value="comisiones_meli.xlsx", key="nombre_salida")

    procesar_btn = st.button("⚡ PROCESAR Y GENERAR ANÁLISIS", type="primary",
                              key="btn_procesar_excel", disabled=(archivo_excel is None))

    if procesar_btn and archivo_excel is not None:
        import tempfile, io as _io
        progress_bar = st.progress(0)
        status_txt   = st.empty()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(archivo_excel.read())
            tmp_path = tmp.name

        try:
            total_ref = [0]
            def prog_e(i, total, desc):
                total_ref[0] = total
                pct = int(i / total * 100) if total > 0 else 0
                progress_bar.progress(pct)
                status_txt.text(f"[{i}/{total}] {desc[:50]}...")

            with st.spinner("Procesando... (puede tardar varios minutos)"):
                resultados, tc_e, _ = am.procesar(tmp_path, margen_obj_e, progress_cb=prog_e)

            progress_bar.progress(100)
            status_txt.text(f"✓ {len(resultados)} productos procesados — generando Excel...")

            # Generar excel en memoria
            out_path = os.path.join(tempfile.gettempdir(), nombre_salida)
            am.generar_excel(resultados, out_path, margen_obj_e, tc_e)

            necesitan = sum(1 for r in resultados
                            if any((r["tipos"].get(t,{}).get("ajuste") or 0) > 0
                                   for t in r["tipos"]))
            status_txt.text(f"✓ Listo — {necesitan} productos necesitan ajuste de margen")

            with open(out_path, "rb") as f:
                st.download_button(
                    label="⬇️ Descargar Excel con Resultados",
                    data=f.read(),
                    file_name=nombre_salida,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                )
            st.success(f"✓ Excel generado. {len(resultados)} productos · {necesitan} con ajuste necesario.")
        except Exception as e:
            import traceback
            st.error(f"Error: {e}")
            st.code(traceback.format_exc())
        finally:
            try: os.unlink(tmp_path)
            except: pass
    else:
        if archivo_excel is None:
            st.info("⬆️ Subí el Excel de Flexxus arriba para empezar.")
