import requests

def geolocate_ip(ip: str, provider: str = "ipapi", token: str = ""):
    """
    Retourne un dict {country, region, city, lat, lon} ou {} si échec.
    Utilisation optionnelle, gère les erreurs silencieusement.
    """
    try:
        if ip in ("127.0.0.1", "::1"):
            return {"country": "Local", "region": "", "city": "localhost", "lat": None, "lon": None}

        if provider == "ipinfo":
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            r = requests.get(f"https://ipinfo.io/{ip}/json", headers=headers, timeout=4)
            if r.ok:
                data = r.json()
                loc = data.get("loc", ",").split(",")
                return {
                    "country": data.get("country"),
                    "region": data.get("region"),
                    "city": data.get("city"),
                    "lat": float(loc[0]) if len(loc) == 2 else None,
                    "lon": float(loc[1]) if len(loc) == 2 else None,
                }
        else:
            # ipapi.co sans clé
            r = requests.get(f"https://ipapi.co/{ip}/json/", timeout=4)
            if r.ok:
                data = r.json()
                return {
                    "country": data.get("country_name"),
                    "region": data.get("region"),
                    "city": data.get("city"),
                    "lat": data.get("latitude"),
                    "lon": data.get("longitude"),
                }
    except Exception:
        pass
    return {}
