import streamlit as st
import sys
import os
import pandas as pd
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.comisiones import procesar_excel, generar_excel_salida
from src.core.margenes import precio_venta_necesario
from src.web.components.sidebar import render_sidebar

import json

st.set_page_config(page_title="Mis Rubros en MeLi", page_icon="📊", layout="wide")
render_sidebar()

st.title("📊 Mis Rubros en MeLi")
st.markdown("Sube tu archivo de Flexxus para mapear tus categorías a Mercado Libre y analizar tus márgenes agrupados por rubro.")

col1, col2 = st.columns(2)
with col1:
    margen_obj = st.number_input("Margen Objetivo (%)", min_value=1.0, max_value=100.0, value=20.0, step=1.0)
with col2:
    iva_default = st.number_input("IVA (%)", min_value=0.0, max_value=100.0, value=21.0, step=1.0)

# Cargar estado guardado si existe
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "estado_rubros.json")
if "productos_procesados" not in st.session_state and os.path.exists(STATE_FILE):
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            st.session_state["productos_procesados"] = data.get("productos", [])
            st.session_state["col_map"] = data.get("col_map", {})
    except Exception:
        pass

uploaded_file = st.file_uploader("Sube el archivo Excel de Flexxus (.xlsx)", type=["xlsx", "xls"])

col_a, col_b = st.columns([1, 4])
with col_a:
    btn_analizar = st.button("Analizar", type="primary") if uploaded_file else False
with col_b:
    if "productos_procesados" in st.session_state:
        if st.button("🗑️ Borrar datos guardados"):
            del st.session_state["productos_procesados"]
            if os.path.exists(STATE_FILE):
                os.remove(STATE_FILE)
            st.rerun()

if btn_analizar or "productos_procesados" in st.session_state:
    if btn_analizar:
        with st.spinner("Analizando productos... Esto puede tomar unos minutos."):
            temp_path = "temp_uploaded.xlsx"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # Procesar
            res = procesar_excel(temp_path, margen_obj)
            if res:
                productos, col_map, cols_orig = res
                st.session_state["productos_procesados"] = productos
                st.session_state["col_map"] = col_map
                
                # Guardar en disco para persistencia
                try:
                    with open(STATE_FILE, "w", encoding="utf-8") as f:
                        json.dump({"productos": productos, "col_map": col_map}, f)
                except Exception:
                    pass
            else:
                st.error("Hubo un error al procesar el archivo.")
                st.stop()

        productos = st.session_state["productos_procesados"]
        col_map = st.session_state["col_map"]

        # Agrupar por rubros
        rubros = defaultdict(list)
        for p in productos:
            # En procesar_excel el superrubro podria estar en col_map["rubro"] pero procesar_excel no crea un campo "superrubro" explícito
            # Wait, procesar_excel no devuelve p["superrubro"], usa col_map["rubro"].
            superrubro = p.get(col_map.get("rubro", ""), "Sin Rubro")
            rubros[superrubro].append(p)

        datos_rubros = {}
        for sr, items in rubros.items():
            coms   = [i.get("__pct_clasica", 0) for i in items if i.get("__pct_clasica") is not None]
            mgs    = [i.get("__margen_flexxus", 0) for i in items if i.get("__margen_flexxus") is not None]
            mrs    = [i.get("__margen_clasica") for i in items if i.get("__margen_clasica") is not None]
            
            # Calcular mg_nec (A CARGAR / COSTO) - 1 ... no, usemos lo existente
            datos_rubros[sr] = {
                "Rubro Flexxus": sr,
                "Categoría MeLi": items[0].get("__cat_raiz") or "—",
                "Comisión MeLi": f"{round(sum(coms)/len(coms), 1)}%" if coms else "0%",
                "Productos": len(items),
                "Mg Flexxus": f"{round(sum(mgs)/len(mgs), 1)}%" if mgs else "—",
                "Mg Real MeLi": f"{round(sum(mrs)/len(mrs), 1)}%" if mrs else "—",
                "_mg_real_num": sum(mrs)/len(mrs) if mrs else 999,
                "items": items
            }

        # Mostrar tabla de rubros
        st.subheader("1. Resumen por Rubros")
        
        df_rubros = pd.DataFrame(list(datos_rubros.values()))
        df_rubros = df_rubros.sort_values(by="_mg_real_num").drop(columns=["_mg_real_num", "items"])
        
        st.dataframe(df_rubros, use_container_width=True, hide_index=True)

        st.subheader("2. Detalle de Productos")
        opciones_rubros = ["Selecciona un rubro..."] + sorted(datos_rubros.keys())
        rubro_sel = st.selectbox("Ver productos del rubro:", opciones_rubros)

        if rubro_sel != "Selecciona un rubro...":
            items_rubro = datos_rubros[rubro_sel]["items"]
            
            datos_prods = []
            for p in items_rubro:
                com = p.get("__pct_clasica", 0)
                costo_ars = p.get("__costo", 0) or 0
                precio_act = p.get("__precio", 0) or 0
                pv_ars = precio_venta_necesario(costo_ars, com, margen_obj) if costo_ars else None
                
                # IVA desde el excel o el input
                iva_pct = iva_default
                col_iva = col_map.get("iva", "")
                if col_iva and p.get(col_iva) not in ("", None, "nan"):
                    try:
                        iva_pct = float(p.get(col_iva))
                    except:
                        pass
                        
                factor_iva = 1 + iva_pct/100
                pv_usd = round(pv_ars / factor_iva, 2) if pv_ars else None # Asumimos TC=1 si no procesamos dolares por simplicidad web

                datos_prods.append({
                    "SKU": p.get(col_map.get("codigo", ""), ""),
                    "Descripción": p.get(col_map.get("descripcion", ""), ""),
                    "Comisión": f"{com}%",
                    "Costo ARS": f"${costo_ars:,.0f}",
                    "Precio Act.": f"${precio_act:,.0f}" if precio_act else "—",
                    "Mg Flexxus": f"{p.get('__margen_flexxus', 0):.1f}%" if p.get('__margen_flexxus') is not None else "—",
                    "Mg Real": f"{p.get('__margen_clasica', 0):.1f}%" if p.get('__margen_clasica') is not None else "—",
                    "A CARGAR (ARS)": f"${pv_ars:,.0f}" if pv_ars else "—"
                })
            
            st.dataframe(pd.DataFrame(datos_prods), use_container_width=True, hide_index=True)
