import streamlit as st
import pandas as pd
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.web.components.sidebar import render_sidebar
from src.core.competencia import buscar_competencia
from src.api.client import obtener_token
import json

st.set_page_config(page_title="Competencia en MeLi", page_icon="🕵️", layout="wide")
render_sidebar()

# ── Cargar productos del Excel (si ya se procesó en Mis Rubros) ──
STATE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "estado_rubros.json")
if "productos_procesados" not in st.session_state and os.path.exists(STATE_FILE):
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            st.session_state["productos_procesados"] = data.get("productos", [])
            st.session_state["col_map"] = data.get("col_map", {})
    except Exception:
        pass

SELLER_ID_PROPIO = 32331880   # CLUBDIGITALSTORE

# ══════════════════════════════════════════════════════════════════
st.title("🕵️ Competencia en MeLi")
st.caption("Buscá un producto por SKU o EAN y ve tu posición de precio entre todos los vendedores.")

# ── Inputs ────────────────────────────────────────────────────────
col_inp, col_price = st.columns([3, 2])
with col_inp:
    busqueda = st.text_input(
        "Buscar por SKU, EAN o descripción:",
        placeholder="Ej: A20-010-0100, 0977855130037, Logitech MeetUp...")
with col_price:
    precio_mio_input = st.number_input(
        "Tu precio de venta ($ ARS):",
        min_value=0.0, step=500.0,
        help="Si tu SKU está en el Excel se precarga automáticamente.")

btn_buscar = st.button("🔍 Buscar Competencia", type="primary", use_container_width=False)

if not btn_buscar:
    st.stop()

# ── Validar input ─────────────────────────────────────────────────
if not busqueda.strip():
    st.warning("Ingresá un SKU, EAN o descripción para buscar.")
    st.stop()

# ── Buscar producto en caché del Excel ────────────────────────────
productos = st.session_state.get("productos_procesados", [])
col_map   = st.session_state.get("col_map", {})

prod_sel      = None
texto_up      = busqueda.strip().upper()

for p in productos:
    sku = str(p.get(col_map.get("codigo", ""), "")).strip().upper()
    ean_key = col_map.get("ean") or next(
        (k for k in p.keys() if "EAN" in k.upper() or "BARRA" in k.upper()), None)
    ean = str(p.get(ean_key, "")).strip().upper() if ean_key else ""
    if (sku and sku == texto_up) or (ean and ean == texto_up):
        prod_sel = p
        if not col_map.get("ean") and ean_key:
            col_map["ean"] = ean_key
        break

# ── Armar EAN / desc para la búsqueda ─────────────────────────────
ean_val  = ""
desc_val = ""
precio_mio = precio_mio_input if precio_mio_input > 0 else None

if prod_sel:
    desc_en_excel = str(prod_sel.get(col_map.get("descripcion", ""), ""))
    ean_en_excel  = str(prod_sel.get(col_map.get("ean", ""), "")).strip()
    st.success(f"📦 Producto en tu Excel: **{desc_en_excel}**")
    ean_val  = ean_en_excel or busqueda.strip()
    desc_val = desc_en_excel
    precio_act = prod_sel.get("__precio", 0) or 0
    if precio_act > 0 and not precio_mio:
        precio_mio = float(precio_act)
        st.info(f"Precio tomado del Excel: **${precio_mio:,.0f}**")
else:
    if busqueda.strip().isnumeric() and len(busqueda.strip()) > 8:
        ean_val  = busqueda.strip()
    else:
        desc_val = busqueda.strip()

# ── Llamar a la API ───────────────────────────────────────────────
with st.spinner("Buscando en Mercado Libre..."):
    token = obtener_token()
    items, catalog_name = buscar_competencia(
        ean_val.strip(), desc_val.strip(), token,
        seller_id_propio=SELLER_ID_PROPIO)

if not items:
    st.error(
        f"No se encontraron vendedores para **{busqueda}**. "
        "Verificá el EAN o la descripción.")
    st.stop()

st.success(f"**{catalog_name}** — {len(items)} vendedores encontrados")

# ══════════════════════════════════════════════════════════════════
# ESTADÍSTICAS
# ══════════════════════════════════════════════════════════════════
precios_comp = [it["precio"] for it in items if not it.get("es_propio") and it["precio"] > 0]

mi_pos_num = None
if precio_mio and precios_comp:
    menores    = sum(1 for p in precios_comp if p < precio_mio)
    mi_pos_num = menores + 1

st.divider()
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("💰 Precio mínimo",  f"${min(precios_comp):,.0f}"  if precios_comp else "—")
c2.metric("📊 Precio prom.",   f"${sum(precios_comp)/len(precios_comp):,.0f}" if precios_comp else "—")
c3.metric("📈 Precio máximo",  f"${max(precios_comp):,.0f}"  if precios_comp else "—")
c4.metric("👥 Competidores",   str(len(items)))

if mi_pos_num and precios_comp:
    total_con_mio = len(precios_comp) + 1
    if mi_pos_num == 1:
        pos_label = f"#1 ✅ EL MÁS BARATO"
    elif mi_pos_num <= total_con_mio * 0.25:
        pos_label = f"#{mi_pos_num} de {total_con_mio} 🟢"
    elif mi_pos_num <= total_con_mio * 0.50:
        pos_label = f"#{mi_pos_num} de {total_con_mio} 🟡"
    else:
        pos_label = f"#{mi_pos_num} de {total_con_mio} 🔴"
    c5.metric("🎯 Tu posición", pos_label)
else:
    c5.metric("🎯 Tu posición", "—")

# ── Análisis competitivo ──────────────────────────────────────────
if precio_mio and precios_comp:
    precio_min = min(precios_comp)
    prom       = sum(precios_comp) / len(precios_comp)
    dif_min    = (precio_mio - precio_min) / precio_min * 100
    dif_prom   = (precio_mio - prom)       / prom       * 100
    signo_prom = "sobre" if dif_prom >= 0 else "bajo"

    if dif_min < 0:
        st.success(f"✓ **Sos el más barato** — ${abs(precio_mio - precio_min):,.0f} menos que el mínimo del mercado")
    elif dif_min == 0:
        st.info("= Tu precio es **igual al mínimo** del mercado")
    elif dif_min <= 5:
        st.info(f"≈ **Muy competitivo** — solo {dif_min:.1f}% sobre el más barato | {abs(dif_prom):.1f}% {signo_prom} el promedio")
    elif dif_min <= 15:
        st.warning(f"▲ Estás **{dif_min:.1f}% sobre el más barato** | {abs(dif_prom):.1f}% {signo_prom} el promedio")
    else:
        st.error(f"⚠ Estás **{dif_min:.1f}% sobre el más barato** — considerá ajustar tu precio | {abs(dif_prom):.1f}% {signo_prom} el promedio")

st.divider()

# ══════════════════════════════════════════════════════════════════
# TABLA CON FILA "TU PRECIO" INSERTADA EN LA POSICIÓN CORRECTA
# ══════════════════════════════════════════════════════════════════
filas_raw = []
mi_precio_insertado = False
items_ordenados = sorted(items, key=lambda x: x["precio"])

for item in items_ordenados:
    if (precio_mio
            and not mi_precio_insertado
            and item["precio"] > precio_mio
            and not item.get("es_propio")):
        filas_raw.append({"_tipo": "mi_precio", "precio": precio_mio})
        mi_precio_insertado = True
    filas_raw.append({"_tipo": "item", **item})

if precio_mio and not mi_precio_insertado:
    filas_raw.append({"_tipo": "mi_precio", "precio": precio_mio})

# Construir DataFrame
rows   = []
colores = []
pos    = 0
comp_pos = 0   # posición entre competidores reales

for fila in filas_raw:
    pos += 1

    if fila["_tipo"] == "mi_precio":
        rows.append({
            "Pos":      f"▶ #{pos}",
            "Precio":   f"${fila['precio']:,.0f}",
            "Vendedor": "👤  TU PRECIO",
            "Tipo":     "—",
            "Envío":    "—",
            "Cuotas":   "—",
            "Link":     "",
        })
        colores.append("mi_precio")
        continue

    comp_pos += 1
    item  = fila
    precio = item["precio"]
    vend  = item["vendedor"]
    if item.get("official"):  vend = "🏪 " + vend
    if item.get("es_propio"): vend = "★ " + vend

    if item.get("es_propio"):
        color = "propio"
    elif comp_pos == 1:
        color = "primero"
    elif precio_mio and precio > precio_mio * 1.10:
        color = "mas_caro"
    else:
        color = "normal"

    rows.append({
        "Pos":      f"#{pos}",
        "Precio":   f"${precio:,.0f}",
        "Vendedor": vend,
        "Tipo":     item.get("tipo", "—"),
        "Envío":    item.get("envio", "—"),
        "Cuotas":   item.get("cuotas", "—"),
        "Link":     item.get("permalink", ""),
    })
    colores.append(color)

df = pd.DataFrame(rows)

# ── Colorear filas con pandas Styler ─────────────────────────────
COLOR_MAP = {
    "mi_precio": "background-color:#FEF3C7; color:#92400E; font-weight:bold",
    "primero":   "background-color:#D1FAE5; color:#065F46; font-weight:bold",
    "propio":    "background-color:#DBEAFE; color:#1D4ED8; font-weight:bold",
    "mas_caro":  "background-color:#FEE2E2; color:#991B1B",
    "normal":    "",
}

color_por_fila = colores   # lista alineada con el índice del df

def _aplicar_colores(df_inner):
    styles = pd.DataFrame("", index=df_inner.index, columns=df_inner.columns)
    for idx in df_inner.index:
        s = COLOR_MAP.get(color_por_fila[idx], "")
        if s:
            styles.loc[idx, :] = s
    return styles

styled = df.style.apply(_aplicar_colores, axis=None)

st.dataframe(
    styled,
    column_config={
        "Link": st.column_config.LinkColumn("Ver ↗", display_text="Abrir"),
    },
    use_container_width=True,
    hide_index=True,
)

st.caption("🟢 Más barato · 🟡 Tu precio (ámbar) · 🔵 Tu publicación · 🔴 Más caro que tu precio")
