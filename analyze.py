
import json
from pathlib import Path
from datetime import datetime, timezone

DATA = Path("data")
SOURCE = DATA / "trends.json"


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(
            "data/trends.json introuvable. Lance main.py d'abord."
        )

    report = json.loads(SOURCE.read_text(encoding="utf-8"))
    games = report.get("games", [])

    unique = {}
    for game in games:
        uid = game.get("universeId")
        if uid:
            unique[uid] = game

    games = list(unique.values())

    for game in games:
        players = game.get("playerCount") or 0
        up = game.get("totalUpVotes") or 0
        down = game.get("totalDownVotes") or 0
        votes = up + down
        approval = up / votes if votes else 0.5

        game["approval_rate"] = round(approval * 100, 1)
        game["trend_score"] = round(
            players * (0.5 + approval), 2
        )

    ranking = sorted(
        games,
        key=lambda g: g["trend_score"],
        reverse=True
    )[:30]

    categories = {}
    for game in games:
        genre = game.get("genreL1") or "Unknown"
        categories[genre] = categories.get(genre, 0) + 1

    result = {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "games_analyzed": len(games),
        "ranking_method": "Popularite actuelle et votes, pas croissance",
        "popular_categories": sorted(
            [
                {"genre": genre, "games": count}
                for genre, count in categories.items()
            ],
            key=lambda x: x["games"],
            reverse=True
        ),
        "top_games": ranking
    }

    DATA.mkdir(exist_ok=True)
    (DATA / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    genres = ", ".join(
        item["genre"] for item in result["popular_categories"][:3]
    )

    idea = f"""# Idee de jeu Roblox

Generee le : {result['analyzed_at']}

Genres observes : {genres}

## Prototype propose : Obby Evolution

- Une zone de depart
- Cinq obstacles progressifs
- Des points de controle
- Des pieces a collecter
- Des ameliorations debloquables
- Une ligne d'arrivee
- Une interface adaptee au mobile

Cette proposition est un concept, pas encore un jeu publie.
La popularite et les revenus ne sont pas garantis.
"""

    (DATA / "game_idea.md").write_text(
        idea, encoding="utf-8"
    )

    print(f"Jeux analyses : {len(games)}")
    print("Classement : data/analysis.json")
    print("Idee : data/game_idea.md")


if __name__ == "__main__":
    main()
