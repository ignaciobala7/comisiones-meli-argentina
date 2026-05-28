import streamlit as st
import time
import urllib.parse
import webbrowser
from src.config.settings import cargar_config, guardar_config
from src.api.client import obtener_token, AUTH_URL
from src.api.oauth import iniciar_servidor_oauth, has_oauth_code, intercambiar_code, REDIRECT_URI

def render_sidebar():
    cfg = cargar_config()
    with st.sidebar:
        st.header("⚙️ Configuración API")
        client_id = st.text_input("Client ID", value=cfg.get("client_id", ""))
        client_secret = st.text_input("Client Secret", value=cfg.get("client_secret", ""), type="password")
        
        if st.button("Guardar Credenciales"):
            cfg["client_id"] = client_id
            cfg["client_secret"] = client_secret
            guardar_config(cfg)
            st.success("Guardado.")

        st.divider()
        st.subheader("Estado de Conexión")
        token = obtener_token()
        
        if token:
            st.success("✅ Conectado a MeLi")
        else:
            st.error("❌ Desconectado")
            
            if client_id and client_secret:
                if st.button("🔌 Conectar con Mercado Libre"):
                    iniciar_servidor_oauth()
                    params = urllib.parse.urlencode({
                        "response_type": "code",
                        "client_id": client_id,
                        "redirect_uri": REDIRECT_URI
                    })
                    url = f"{AUTH_URL}?{params}"
                    webbrowser.open(url)
                    st.info("Revisa la ventana del navegador que se acaba de abrir. Luego haz clic abajo.")
                
                if st.button("🔄 Verificar Autorización"):
                    if has_oauth_code():
                        d = intercambiar_code(client_id, client_secret)
                        if d and "access_token" in d:
                            cfg["access_token"] = d["access_token"]
                            cfg["refresh_token"] = d.get("refresh_token", "")
                            cfg["token_expires_at"] = time.time() + d.get("expires_in", 21600)
                            guardar_config(cfg)
                            st.success("¡Autorizado con éxito!")
                            st.rerun()
                        else:
                            st.error("Error al intercambiar el código.")
                    else:
                        st.warning("Aún no se recibió la autorización.")
