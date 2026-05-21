════════════════════════════════════════════════════════
  CONSULTA DE COMISIONES — MERCADO LIBRE ARGENTINA
  Sistema de Inteligencia de Precios
════════════════════════════════════════════════════════

PARA QUE SIRVE:
  Consultar cuanto cobra MeLi de comision por categoria y calcular:
    - Cuanto neto te queda despues de la comision
    - Tu margen real de ganancia
    - A que precio deberias publicar para alcanzar el margen que queres

PRIMERA VEZ — INSTALACION:
  1. Abre una terminal (CMD o PowerShell) en esta carpeta
  2. Ejecuta:  pip install -r requirements.txt
  3. Listo!

OPCION FACIL — DOBLE CLICK:
  Abre "iniciar.bat" y segui el menu.

────────────────────────────────────────────────────────
MODO 1: CONSULTA INDIVIDUAL (sin Excel)
────────────────────────────────────────────────────────
  Comando:
    python consulta_comisiones.py

  Te pregunta:
    - Nombre del producto (busca la categoria en MeLi automaticamente)
    - Precio de venta que pensas poner
    - Tu costo (opcional)

  Te muestra:
    - Comision % y $ para Clasica y Premium
    - Lo que cobras neto
    - Tu margen de ganancia
    - Precios sugeridos para distintos margenes objetivo (10%, 15%, 20%, 25%, 30%)

────────────────────────────────────────────────────────
MODO 2: PROCESAR EXCEL DE FLEXXUS
────────────────────────────────────────────────────────
  Exporta tu stock desde Flexxus con estas columnas (los nombres pueden variar,
  el sistema las detecta automaticamente):
    - Codigo / SKU
    - Descripcion / Nombre del producto
    - Rubro / Categoria (MUY IMPORTANTE para detectar la comision correcta)
    - Sub-Rubro (opcional, mejora la busqueda)
    - Precio de venta (el precio al que lo queres publicar)
    - Costo neto
    - Stock (opcional)

  Comando:
    python consulta_comisiones.py --excel "mi_stock.xlsx"

  Con margen objetivo distinto al 20% (por ejemplo 25%):
    python consulta_comisiones.py --excel "mi_stock.xlsx" --margen 25

  Con nombre de archivo de salida personalizado:
    python consulta_comisiones.py --excel "mi_stock.xlsx" --salida "analisis_mayo.xlsx"

  Genera un Excel con 3 hojas:
    1. "Analisis Comisiones"   — Una fila por producto con todas las comisiones
    2. "Resumen por Categoria" — Totales y promedios por categoria
    3. "Instrucciones"         — Como interpretar cada columna

────────────────────────────────────────────────────────
CREAR TEMPLATE EXCEL:
────────────────────────────────────────────────────────
  Si no sabes como armar el Excel, crea uno de ejemplo:
    python crear_template.py

  Genera "template_mis_productos.xlsx" con el formato correcto y datos de ejemplo.

────────────────────────────────────────────────────────
COLORES EN EL EXCEL DE SALIDA:
────────────────────────────────────────────────────────
  Verde   = Margen igual o mayor al objetivo -> Publicar a ese precio
  Amarillo = Margen positivo pero menor al objetivo -> Evaluar
  Rojo    = Margen negativo -> Perdes plata a ese precio

════════════════════════════════════════════════════════
