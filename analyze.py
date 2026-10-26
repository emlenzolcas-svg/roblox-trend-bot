
import json
from pathlib import Path
from datetime import datetime, timezone

DATA = Path("data")
SOURCE = DATA / "trends.json"
HISTORY = DATA / "history.json"


def read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(
            "data/trends.json introuvable. Lance main.py d'abord."
        )

    now = datetime.now(timezone.utc).isoformat()
    report = read_json(SOURCE, {})
    games = report.get("games", [])

    # Garder une seule entrée par jeu
    unique = {}
    for game in games:
        uid = game.get("universeId")
        if uid:
            unique[str(uid)] = game

    games = list(unique.values())

    # Charger l'historique précédent
    history = read_json(HISTORY, {"snapshots": []})
    snapshots = history.get("snapshots", [])
    previous = {}

    if snapshots:
        previous = snapshots[-1].get("games", {})

    current = {}

    for game in games:
        uid = str(game["universeId"])
        players = game.get("playerCount") or 0
        up = game.get("totalUpVotes") or 0
        down = game.get("totalDownVotes") or 0
        votes = up + down
        approval = up / votes if votes else 0.5

        old_players = previous.get(uid, {}).get("players")
        if old_players is not None:
            growth = players - old_players
            growth_pct = (
                round((growth / old_players) * 100, 1)
                if old_players > 0 else None
            )
        else:
            growth = None
            growth_pct = None

        game["approval_rate"] = round(approval * 100, 1)
        game["player_growth"] = growth
        game["player_growth_pct"] = growth_pct

        # Score de popularité actuelle
        game["trend_score"] = round(
            players * (0.5 + approval), 2
        )

        # Score de croissance disponible après une comparaison
        game["growth_score"] = (
            round(max(growth, 0) * (0.5 + approval), 2)
            if growth is not None else None
        )

        current[uid] = {
            "name": game.get("name", "Jeu inconnu"),
            "players": players
        }

    # Enregistrer cette exécution pour la prochaine comparaison
    snapshots.append({
        "timestamp": now,
        "games": current
    })

    # Garder les 30 derniers relevés
    history["snapshots"] = snapshots[-30:]
    DATA.mkdir(exist_ok=True)
    HISTORY.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    ranking = sorted(
        games,
        key=lambda g: g["trend_score"],
        reverse=True
    )[:30]

    growth_ranking = sorted(
        [g for g in games if g["player_growth"] is not None],
        key=lambda g: g["growth_score"],
        reverse=True
    )[:30]

    categories = {}
    for game in games:
        genre = game.get("genreL1") or "Inconnu"
        categories[genre] = categories.get(genre, 0) + 1

    result = {
        "analyzed_at": now,
        "games_analyzed": len(games),
        "note": (
            "La croissance compare ce relevé au précédent. "
            "Le premier relevé ne permet pas encore de mesurer "
            "la croissance."
        ),
        "popular_categories": sorted(
            [
                {"genre": genre, "games": count}
                for genre, count in categories.items()
            ],
            key=lambda item: item["games"],
            reverse=True
        ),
        "top_games": ranking,
        "fastest_growing_games": growth_ranking
    }

    (DATA / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    genres = ", ".join(
        item["genre"] for item in result["popular_categories"][:3]
    ) or "Genres à confirmer"

    idea = f"""# Idée de jeu Roblox

Générée le : {now}

Genres observés : {genres}

## Prototype proposé : Obby Evolution

- Une zone de départ
- Cinq obstacles progressifs
- Des points de contrôle
- Des pièces à collecter
- Des améliorations à débloquer
- Une ligne d'arrivée
- Une interface adaptée au mobile

Cette proposition est un concept, pas encore un jeu publié.
La popularité et les revenus ne sont pas garantis.
"""

    (DATA / "game_idea.md").write_text(idea, encoding="utf-8")

    print(f"Jeux analysés : {len(games)}")
    print("Classement : data/analysis.json")
    print("Historique : data/history.json")
    print("Idée : data/game_idea.md")
    print(f"Jeux comparables : {len(growth_ranking)}")


if __name__ == "__main__":
    main()
