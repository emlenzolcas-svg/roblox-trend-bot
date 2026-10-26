
import json
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://apis.roblox.com/explore-api/v1"


def get_json(url):
    """Télécharge des données JSON publiques."""
    request = Request(
        url,
        headers={"User-Agent": "RobloxTrendBot/1.0"}
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    session_id = str(uuid.uuid4())
    params = urlencode({"sessionId": session_id})
    url = f"{BASE_URL}/get-sorts?{params}"

    print("🤖 Roblox Trend Bot démarre...")
    print("📡 Recherche des catégories de découverte Roblox...")

    try:
        data = get_json(url)

        os.makedirs("data", exist_ok=True)
        report = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "source": url.split("?")[0],
            "data": data,
        }

        with open("data/trends.json", "w", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=False, indent=2)

        print("✅ Données enregistrées dans data/trends.json")
        print("Voici les premières informations reçues :")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])

    except Exception as error:
        print("❌ Impossible de récupérer les données Roblox.")
        print(f"Détail : {error}")
        raise


if __name__ == "__main__":
    main()
