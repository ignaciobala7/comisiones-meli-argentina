import requests
import time

def safe_get(url, params=None, headers=None, timeout=14):
    try:
        r = requests.get(url, params=params, headers=headers or {}, timeout=timeout)
        try:
            body = r.json()
        except Exception:
            body = {}
        return r.status_code, body
    except Exception:
        return 0, {}

def normalizar_items(raw_list, fuente="catalog"):
    out = []
    for it in raw_list:
        if fuente == "search":
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

def fmt_envio(ship):
    if not ship:
        return "Ver"
    tags = ship.get("tags", [])
    mode = ship.get("mode", "")
    free = ship.get("free_shipping", False)
    cost = ship.get("cost")
    if "fulfillment" in tags or mode == "fulfillment":
        return "🏭 Full"
    if free:
        return "🚚 Gratis"
    if cost and cost > 0:
        return f"${cost:,.0f}"
    if mode in ("me2", "me1"):
        return "Con envío"
    return "Ver"

def buscar_competencia(ean, desc, token, seller_id_propio=None):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    TIPOS = {"gold_premium": "Premium ⭐", "gold_special": "Clásica", "gold": "Gold", "silver": "Silver", "free": "Gratis"}

    # FASE 1
    queries = []
    if ean: queries.append(ean)
    if desc:
        ws = desc.split()
        for slc in [ws[:6], ws[:5], ws[:4], ws[:3], ws[1:6], ws[1:5], ws[2:6]]:
            q = " ".join(slc).strip()
            if q and q not in queries:
                queries.append(q)
    queries = list(dict.fromkeys(q for q in queries if len(q) >= 3))

    catalog_id = ""
    catalog_name = ""
    for q in queries:
        sc, data = safe_get("https://api.mercadolibre.com/products/search", {"site_id": "MLA", "q": q, "limit": 5, "status": "active"}, headers=h)
        if sc == 200:
            results = data.get("results", [])
            if results:
                catalog_id   = results[0].get("id", "")
                catalog_name = results[0].get("name", "")
                break
        elif sc == 0:
            time.sleep(0.5)

    # FASE 2
    items_raw = []
    fuente = "catalog"
    if catalog_id:
        sc, data = safe_get(f"https://api.mercadolibre.com/products/{catalog_id}/items", headers=h)
        if sc == 200:
            items_raw = data.get("results", [])
    
    if not items_raw and catalog_id:
        sc, data = safe_get("https://api.mercadolibre.com/sites/MLA/search", {"catalog_product_id": catalog_id, "limit": 50}, headers=h)
        if sc == 200 and data.get("results"):
            items_raw = data["results"]
            fuente = "search"

    if not items_raw and catalog_name:
        sc, data = safe_get("https://api.mercadolibre.com/sites/MLA/search", {"q": catalog_name[:80], "limit": 50}, headers=h)
        if sc == 200 and data.get("results"):
            items_raw = data["results"]
            fuente = "search"

    if not items_raw:
        last_q = ean or (desc[:60] if desc else "")
        if last_q:
            sc, data = safe_get("https://api.mercadolibre.com/sites/MLA/search", {"q": last_q, "limit": 50}, headers=h)
            if sc == 200 and data.get("results"):
                items_raw = data["results"]
                fuente = "search"
                if not catalog_name:
                    catalog_name = last_q

    if not items_raw:
        return None, catalog_name

    # FASE 3
    norm = normalizar_items(items_raw, fuente=fuente)
    sellers_sin_nick = [it["seller_id"] for it in norm if not it.get("_nick")]
    nick_map = {}
    if sellers_sin_nick:
        ids_uniq = list(dict.fromkeys(sellers_sin_nick))[:20]
        sc, data = safe_get("https://api.mercadolibre.com/users", {"ids": ",".join(str(s) for s in ids_uniq), "attributes": "id,nickname"})
        if sc == 200:
            for entry in data:
                body = entry.get("body", {})
                nick_map[body.get("id")] = body.get("nickname", "?")

    items_enriquecidos = []
    for it in norm:
        iid = it.get("item_id", "")
        digits = iid.replace("MLA", "").lstrip("-")
        plink = f"https://articulo.mercadolibre.com.ar/MLA-{digits}" if digits else f"https://www.mercadolibre.com.ar/p/{catalog_id or 'MLA'}"
        ship = it.get("shipping", {})
        lt = it.get("listing_type_id", "")
        acepta_mp = it.get("accepts_mercadopago", True)
        
        if not acepta_mp: cuotas_txt = "—"
        elif lt == "gold_premium": cuotas_txt = "12 s/int ⭐"
        else: cuotas_txt = "hasta 12"

        sid = it.get("seller_id", 0)
        nick = it.get("_nick") or nick_map.get(sid) or str(sid) or "?"
        
        items_enriquecidos.append({
            "item_id": iid,
            "precio": it["price"],
            "seller_id": sid,
            "vendedor": nick,
            "tipo": TIPOS.get(lt, lt or "—"),
            "cuotas": cuotas_txt,
            "envio": fmt_envio(ship),
            "permalink": plink,
            "es_propio": str(sid) == str(seller_id_propio) if seller_id_propio else False,
            "official": bool(it.get("official_store_id"))
        })

    items_enriquecidos.sort(key=lambda x: x["precio"])
    return items_enriquecidos, catalog_name
