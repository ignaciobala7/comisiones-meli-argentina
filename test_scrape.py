import requests
import re

def search_meli(q):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
        'Accept-Language': 'es-AR,es;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
    }
    q_formatted = q.replace(' ', '-')
    url = f"https://listado.mercadolibre.com.ar/{q_formatted}"
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            print("Successfully fetched HTML")
            # Try to find __PRELOADED_STATE__
            match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(.*?);', r.text)
            if match:
                print("Found PRELOADED_STATE")
                return
            
            # Try to find NEXT_DATA
            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text)
            if match:
                print("Found NEXT_DATA")
                return

            # Try to find elements by class
            items = re.findall(r'ui-search-layout__item', r.text)
            print(f"Found {len(items)} items using regex class search")
            if len(items) > 0:
                # find prices
                prices = re.findall(r'<span class="andes-money-amount__fraction">([\d\.]+)</span>', r.text)
                print(f"Found prices: {prices[:5]}")
        else:
            print(f"Error {r.status_code}")
    except Exception as e:
        print(f"Exception: {e}")

search_meli("gamepad redragon saturn cable pc g807")
