import json

estado = json.load(open("src/estado_rubros.json", "r", encoding="utf-8"))
col_map = estado.get("col_map", {})
productos = estado.get("productos", [])

texto_busqueda = "A48-003-0001"
prod_sel = None

for p in productos:
    sku = str(p.get(col_map.get("codigo", ""), "")).strip().upper()
    
    ean_key = col_map.get("ean")
    if not ean_key:
        for k in p.keys():
            if "EAN" in k.upper() or "BARRA" in k.upper():
                ean_key = k
                break
    
    ean = str(p.get(ean_key, "")).strip().upper() if ean_key else ""
    
    if (sku and sku == texto_busqueda) or (ean and ean == texto_busqueda):
        prod_sel = p
        if not col_map.get("ean") and ean_key:
            col_map["ean"] = ean_key
        break

print("prod_sel:", prod_sel.get("CODIGOPARTICULAR") if prod_sel else None)
print("col_map ean:", col_map.get("ean"))

if prod_sel:
    ean_val = str(prod_sel.get(col_map.get("ean", ""), ""))
    desc_val = str(prod_sel.get(col_map.get("descripcion", ""), ""))
    
    if not ean_val:
        ean_val = texto_busqueda

    print(f"Buscando: ean={ean_val}, desc={desc_val}")
