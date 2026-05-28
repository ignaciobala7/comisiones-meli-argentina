# 🚀 Setup - Comisiones MeLi Argentina

## Paso 1: Clonar o actualizar el repo

```bash
# Si es primera vez:
git clone https://github.com/ignaciobala7/comisiones-meli-argentina.git
cd comisiones-meli-argentina

# Si ya lo tienes:
git pull origin feature/streamlit
```

## Paso 2: Crear el archivo de configuración

**NUNCA** subas credenciales a GitHub. Debes crear tu propio archivo `configuracion.json`:

```bash
# Copia el template:
copy configuracion.ejemplo.json configuracion.json
```

Edita `configuracion.json` e ingresa TUS credenciales de Mercado Libre:

```json
{
  "client_id": "AQUI_TU_APP_ID",
  "client_secret": "AQUI_TU_SECRET",
  "access_token": "TU_TOKEN",
  "refresh_token": "TU_REFRESH_TOKEN",
  "user_id": "TU_USER_ID"
}
```

### ¿De dónde obtengo los tokens?

**Opción A: Si ya tienes una app de MeLi registrada**
1. Ve a https://developers.mercadolibre.com/my-applications
2. Copia tu `client_id` y `client_secret`
3. Ejecuta: `python crear_template.py` para obtener los access/refresh tokens

**Opción B: Primera vez (sin app aún)**
1. Regístrate en https://developers.mercadolibre.com
2. Crea una nueva aplicación
3. Sigue el paso anterior

## Paso 3: Instalar dependencias

```bash
pip install -r requirements.txt
```

## Paso 4: Ejecutar la app

```bash
# Windows:
iniciar.bat

# Linux/Mac:
streamlit run src/web/app.py
```

---

⚠️ **IMPORTANTE**: 
- **NUNCA** hagas git commit de `configuracion.json`
- Está en `.gitignore` para proteger tus credenciales
- Cada persona que use el proyecto necesita su PROPIO `configuracion.json`

