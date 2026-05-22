import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.comisiones import buscar_categoria, obtener_raiz_categoria, obtener_comision, calcular_precio_sugerido
from src.api.client import obtener_token, consultar_comision_api
from src.web.components.sidebar import render_sidebar

st.set_page_config(page_title="Consulta Individual", page_icon="🔍", layout="wide")

# Renderizar el sidebar de configuración de API en todas las páginas
render_sidebar()

st.title("🔍 Consulta Individual de Comisiones")
st.markdown("Busca un producto para ver la comisión que cobra Mercado Libre según la categoría.")

query = st.text_input("¿Qué producto querés consultar? (ej: 'celular samsung', 'zapatillas')", placeholder="Escribe aquí y presiona Enter")

if query:
    with st.spinner("Buscando categorías..."):
        cats = buscar_categoria(query)
    
    if not cats:
        st.warning("No se encontraron categorías. Probá con otro término.")
    else:
        st.subheader("Selecciona la categoría correcta:")
        cat_options = {}
        for cat in cats:
            dominio = cat.get("domain_name", "")
            nombre  = cat.get("category_name", "")
            cat_id  = cat.get("category_id", "")
            display = f"{dominio} > {nombre}" if dominio and nombre and dominio != nombre else (dominio or nombre)
            cat_options[display] = cat
        
        selected_cat_name = st.selectbox("Categoría:", options=list(cat_options.keys()))
        cat_sel = cat_options[selected_cat_name]
        
        cat_id     = cat_sel.get("category_id")
        cat_nombre = cat_sel.get("domain_name") or cat_sel.get("category_name", cat_id)
        
        cat_raiz = obtener_raiz_categoria(cat_id)
        tasas    = obtener_comision(cat_raiz)
        
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            precio = st.number_input("Precio de venta ($)", min_value=0.0, value=10000.0, step=100.0)
        with col2:
            costo = st.number_input("Tu costo (opcional) ($)", min_value=0.0, value=0.0, step=100.0)
            
        st.divider()
        
        token = obtener_token()
        if not token:
            st.info("Usando tabla de tasas locales. Conecta la API en Inicio para obtener datos en tiempo real.")
        
        st.markdown(f"**Categoría:** {cat_nombre} ({cat_id})  |  **Raíz:** {cat_raiz}")
        
        cols = st.columns(len(tasas))
        for idx, (tipo_nombre, pct_local) in enumerate(tasas.items()):
            with cols[idx]:
                st.markdown(f"### {tipo_nombre.upper()}")
                
                pct = pct_local
                fee = round(precio * pct / 100, 2)
                
                # Si tenemos token, usamos la API en tiempo real
                if token:
                    tipo_id = "gold_special" if "clasica" in tipo_nombre.lower() else "gold_premium"
                    pct_api, fee_api = consultar_comision_api(precio, cat_id, tipo_id, token)
                    if pct_api is not None:
                        pct = pct_api
                        fee = fee_api
                        st.caption("✅ Dato en tiempo real (API MeLi)")
                    else:
                        st.caption("⚠️ Usando tabla local (Fallo API)")
                else:
                    st.caption("⚠️ Usando tabla local")
                
                neto = round(precio - fee, 2)
                
                st.metric("Comisión MeLi", f"${fee:,.2f}", f"{pct}%", delta_color="inverse")
                st.metric("Lo que cobrás", f"${neto:,.2f}")
                
                if costo > 0:
                    ganancia = neto - costo
                    margen   = (ganancia / precio * 100) if precio > 0 else 0
                    roi      = (ganancia / costo * 100)
                    
                    st.markdown("---")
                    st.metric("Tu Ganancia", f"${ganancia:,.2f}", f"{margen:.1f}% Margen")
                    st.write(f"**ROI:** {roi:.1f}%")
                    
                    st.markdown("**Precios sugeridos**")
                    for m in [15, 20, 25, 30]:
                        ps = calcular_precio_sugerido(costo, pct, m)
                        if ps:
                            st.write(f"Para {m}% margen: **${ps:,.2f}**")
                        else:
                            st.write(f"Para {m}% margen: Imposible")
