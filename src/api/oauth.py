import http.server
import urllib.parse
import threading
import requests
from src.api.client import TOKEN_URL

REDIRECT_PORT = 8888
REDIRECT_URI  = f"http://localhost:{REDIRECT_PORT}"

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
    
    def log_message(self, *a): 
        pass

def iniciar_servidor_oauth():
    global _oauth_code, _oauth_server
    _oauth_code = None
    try:
        _oauth_server = http.server.HTTPServer(("localhost", REDIRECT_PORT), _OAuthHandler)
        t = threading.Thread(target=_oauth_server.handle_request, daemon=True)
        t.start()
        return t
    except Exception:
        return None

def has_oauth_code():
    global _oauth_code
    return _oauth_code is not None

def intercambiar_code(client_id: str, secret: str) -> dict:
    global _oauth_code
    if not _oauth_code:
        return None
    try:
        resp = requests.post(TOKEN_URL, data={
            "grant_type":    "authorization_code",
            "client_id":     client_id,
            "client_secret": secret,
            "code":          _oauth_code,
            "redirect_uri":  REDIRECT_URI,
        }, timeout=20)
        return resp.json() if resp.status_code == 200 else None
    except Exception:
        return None
