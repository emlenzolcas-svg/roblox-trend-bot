
import json
from pathlib import Path
from datetime import datetime, timezone

DATA = Path("data")
SOURCE = DATA / "trends.json"
HISTORY = DATA / "history.json"
MAX_SNAPSHOTS = 30


def read_json(path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(
            "data/trends.json introuvable. Lance main.py d'abord."
        )

    now = datetime.now(timezone.utc).isoformat()
    report = read_json(SOURCE, {})
    games = report.get("games", [])

    # Supprimer les doublons
    unique = {}
    for game in games:
        uid = game.get("universeId")
        if uid is not None:
            unique[str(uid)] = game

    games = list(unique.values())

    # Charger l'historique
    history = read_json(HISTORY, {"snapshots": []})
    snapshots = history.get("snapshots", [])

    if not isinstance(snapshots, list):
        snapshots = []

    current = {}
    comparable_count = 0

    for game in games:
        uid = str(game["universeId"])
        players = game.get("playerCount") or 0
        up = game.get("totalUpVotes") or 0
        down = game.get("totalDownVotes") or 0

        votes = up + down
        approval = up / votes if votes else 0.5

        # Chercher le relevé le plus récent où ce jeu existe
        old_players = None

        for snapshot in reversed(snapshots):
            old_game = snapshot.get("games", {}).get(uid)

            if old_game is not None and "players" in old_game:
                old_players = old_game["players"]
                break

        if old_players is not None:
            growth = players - old_players

            growth_pct = (
                round(growth / old_players * 100, 1)
                if old_players > 0
                else None
            )
            comparable_count += 1
        else:
            growth = None
            growth_pct = None

        game["approval_rate"] = round(approval * 100, 1)
        game["player_growth"] = growth
        game["player_growth_pct"] = growth_pct

        # Popularité actuelle
        game["trend_score"] = round(
            players * (0.5 + approval), 2
        )

        # Croissance positive pondérée par les votes
        game["growth_score"] = (
            round(max(growth, 0) * (0.5 + approval), 2)
            if growth is not None
            else None
        )

        current[uid] = {
            "name": game.get("name", "Jeu inconnu"),
            "players": players
        }

    # Ajouter le relevé actuel après les comparaisons
    snapshots.append({
        "timestamp": now,
        "games": current
    })

    history["snapshots"] = snapshots[-MAX_SNAPSHOTS:]
    DATA.mkdir(parents=True, exist_ok=True)

    HISTORY.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # Classement des jeux les plus populaires
    ranking = sorted(
        games,
        key=lambda g: g["trend_score"],
        reverse=True
    )[:30]

    # Classement des plus fortes hausses
    growth_ranking = sorted(
        [
            g for g in games
            if g["player_growth"] is not None
            and g["player_growth"] > 0
        ],
        key=lambda g: g["growth_score"],
        reverse=True
    )[:30]

    # Jeux qui perdent des joueurs
    declining = sorted(
        [
            g for g in games
            if g["player_growth"] is not None
            and g["player_growth"] < 0
        ],
        key=lambda g: g["player_growth"]
    )[:20]

    # Catégories présentes
    categories = {}
    for game in games:
        genre = game.get("genreL1") or "Inconnu"
        categories[genre] = categories.get(genre, 0) + 1

    result = {
        "analyzed_at": now,
        "games_analyzed": len(games),
        "games_comparable": comparable_count,
        "history_snapshots": len(history["snapshots"]),
        "note": (
            "La croissance compare chaque jeu au relevé "
            "précédent où il apparaît. Les jeux sans historique "
            "suffisant ont une croissance null."
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
        "fastest_growing_games": growth_ranking,
        "declining_games": declining
    }

    (DATA / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    genres = ", ".join(
        item["genre"]
        for item in result["popular_categories"][:3]
    ) or "Genres à confirmer"

    best_growth = (
        growth_ranking[0]["name"]
        if growth_ranking
        else "Pas encore déterminé"
    )

    idea = f"""# Idée de jeu Roblox

Générée le : {now}

Genres observés : {genres}

Jeu avec la plus forte hausse mesurée : {best_growth}

## Prototype proposé : Obby Evolution

- Une zone de départ simple
- Cinq obstacles progressifs
- Des points de contrôle
- Des pièces à collecter
- Des améliorations à débloquer
- Des défis quotidiens
- Une interface adaptée au mobile

Cette idée est un prototype à tester, pas une garantie
de popularité ou de revenus.
"""

    (DATA / "game_idea.md").write_text(
        idea,
        encoding="utf-8"
    )

    print(f"Jeux analysés : {len(games)}")
    print(f"Jeux comparables : {comparable_count}")
    print(f"Relevés conservés : {len(history['snapshots'])}")
    print(f"Jeux en hausse : {len(growth_ranking)}")
    print(f"Jeux en baisse : {len(declining)}")
    print("Rapport : data/analysis.json")
    print("Historique : data/history.json")
    print("Idée : data/game_idea.md")


if __name__ == "__main__":
    main()

