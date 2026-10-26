
import json
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://apis.roblox.com/explore-api/v1"
GAMES_URL = "https://games.roblox.com/v1/games"


def get_json(url):
    request = Request(
        url,
        headers={"User-Agent": "RobloxTrendBot/1.0"}
    )
    with urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    session_id = str(uuid.uuid4())
    params = urlencode({"sessionId": session_id})
    print("🤖 Roblox Trend Bot démarre...")
    games = []
    errors = []

    try:
        discovery = get_json(f"{BASE_URL}/get-sorts?{params}")
        sorts = discovery.get("sorts") or []

        for sort in sorts:
            sort_id = sort.get("sortId") or sort.get("id")
            name = sort.get("sortDisplayName") or sort_id

            if not sort_id or sort.get("contentType") == "Filters":
                continue

            try:
                query = urlencode({
                    "sessionId": session_id,
                    "sortId": sort_id
                })
                result = get_json(
                    f"{BASE_URL}/get-sort-content?{query}"
                )

                items = result.get("games", [])
                if not isinstance(items, list):
                    items = []

                for item in items:
                    item["source_category"] = name
                    games.append(item)

                print(f"📊 {name}: {len(items)} jeux")

            except Exception as error:
                errors.append(f"{name}: {error}")

        ids = []
        for game in games:
            game_id = game.get("universeId") or game.get("id")
            if game_id and str(game_id).isdigit():
                ids.append(str(game_id))

        unique_ids = list(dict.fromkeys(ids))
        details = []

        for start in range(0, len(unique_ids), 50):
            batch = unique_ids[start:start + 50]
            try:
                url = GAMES_URL + "?" + urlencode({
                    "universeIds": ",".join(batch)
                })
                result = get_json(url)
                details.extend(result.get("data", []))
            except Exception as error:
                errors.append(f"Statistiques: {error}")

        report = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "games_found": len(games),
            "games_with_stats": len(details),
            "games": games,
            "stats": details,
            "errors": errors
        }

        os.makedirs("data", exist_ok=True)
        with open("data/trends.json", "w", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=False, indent=2)

        print(f"✅ {len(games)} entrées récupérées.")
        print(f"📈 {len(details)} jeux avec statistiques.")
        print("📁 Rapport enregistré dans data/trends.json")

        if not games:
            print("⚠️ Aucune liste de jeux reçue.")
            print("L'API a peut-être changé de format.")

    except Exception as error:
        print(f"❌ Erreur de découverte Roblox : {error}")
        raise


if __name__ == "__main__":
    main()
