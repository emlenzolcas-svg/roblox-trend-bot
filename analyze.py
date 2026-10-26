
import json
import math
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


def clamp(value, low=0, high=100):
    return max(low, min(high, value))


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(
            "data/trends.json introuvable. Lance main.py d'abord."
        )

    now = datetime.now(timezone.utc).isoformat()
    report = read_json(SOURCE, {})
    games = report.get("games", [])

    unique = {}
    for game in games:
        uid = game.get("universeId")
        if uid is not None:
            unique[str(uid)] = game
    games = list(unique.values())

    history = read_json(HISTORY, {"snapshots": []})
    snapshots = history.get("snapshots", [])
    if not isinstance(snapshots, list):
        snapshots = []

    # Calculs de base et comparaison avec le relevé précédent disponible
    current = {}
    for game in games:
        uid = str(game["universeId"])
        players = max(0, game.get("playerCount") or 0)
        up = max(0, game.get("totalUpVotes") or 0)
        down = max(0, game.get("totalDownVotes") or 0)
        votes = up + down
        approval = up / votes if votes else 0.5

        old_players = None
        old_timestamp = None

        for snapshot in reversed(snapshots):
            old_game = snapshot.get("games", {}).get(uid)
            if old_game is not None and "players" in old_game:
                old_players = old_game["players"]
                old_timestamp = snapshot.get("timestamp")
                break

        if old_players is not None:
            growth = players - old_players
            growth_pct = (
                round(growth * 100 / old_players, 2)
                if old_players > 0 else None
            )
        else:
            growth = None
            growth_pct = None

        # Score actuel de popularité, sur 100
        popularity_score = clamp(
            math.log10(players + 1) / math.log10(1_000_001) * 100
        )

        # Score de croissance, plafonné pour éviter les valeurs extrêmes
        if growth_pct is not None:
            growth_score = clamp(50 + growth_pct * 2)
        else:
            growth_score = None

        approval_score = clamp(approval * 100)

        # Le potentiel favorise les jeux qui grandissent sans être déjà énormes
        if growth_pct is not None:
            size_factor = 1 - min(players / 1_000_000, 1)
            potential_score = clamp(
                50 + growth_pct * 2 + size_factor * 20
            )
        else:
            potential_score = None

        # Un seul relevé ne permet pas de confirmer une tendance durable.
        game["approval_rate"] = round(approval_score, 1)
        game["player_growth"] = growth
        game["player_growth_pct"] = growth_pct
        game["popularity_score"] = round(popularity_score, 1)
        game["growth_score"] = (
            round(growth_score, 1)
            if growth_score is not None else None
        )
        game["potential_score"] = (
            round(potential_score, 1)
            if potential_score is not None else None
        )
        game["trend_confirmed"] = False

        # Le score provisoire combine popularité, croissance et votes.
        # La croissance est neutre quand elle n'est pas encore disponible.
        effective_growth = growth_score if growth_score is not None else 50
        game["trend_score"] = round(
            popularity_score * 0.35
            + effective_growth * 0.40
            + approval_score * 0.25,
            1
        )

        current[uid] = {
            "name": game.get("name", "Jeu inconnu"),
            "players": players
        }

    # Enregistrer le relevé actuel après les comparaisons
    snapshots.append({"timestamp": now, "games": current})
    history["snapshots"] = snapshots[-MAX_SNAPSHOTS:]
    DATA.mkdir(parents=True, exist_ok=True)

    HISTORY.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    top_games = sorted(
        games, key=lambda g: g["trend_score"], reverse=True
    )[:30]

    growing_games = sorted(
        [
            g for g in games
            if g["player_growth"] is not None
            and g["player_growth"] > 0
        ],
        key=lambda g: g["potential_score"],
        reverse=True
    )[:30]

    rising_games = sorted(
        [
            g for g in games
            if g["player_growth_pct"] is not None
            and g["player_growth_pct"] > 0
        ],
        key=lambda g: g["player_growth_pct"],
        reverse=True
    )[:30]

    declining_games = sorted(
        [
            g for g in games
            if g["player_growth"] is not None
            and g["player_growth"] < 0
        ],
        key=lambda g: g["player_growth"]
    )[:20]

    categories = {}
    for game in games:
        genre = game.get("genreL1") or "Inconnu"
        categories[genre] = categories.get(genre, 0) + 1

    result = {
        "analyzed_at": now,
        "games_analyzed": len(games),
        "games_comparable": sum(
            g["player_growth"] is not None for g in games
        ),
        "history_snapshots": len(history["snapshots"]),
        "note": (
            "Les scores sont des indicateurs heuristiques, pas des "
            "prédictions. Une croissance durable nécessite plusieurs "
            "relevés espacés dans le temps."
        ),
        "popular_categories": sorted(
            [
                {"genre": genre, "games": count}
                for genre, count in categories.items()
            ],
            key=lambda item: item["games"],
            reverse=True
        ),
        "top_games": top_games,
        "fastest_growing_games": rising_games,
        "high_potential_games": growing_games,
        "declining_games": declining_games
    }

    (DATA / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    genres = ", ".join(
        item["genre"] for item in result["popular_categories"][:3]
    ) or "Genres à confirmer"

    best = (
        growing_games[0]["name"]
        if growing_games else "Attente de données de croissance"
    )

    idea = f"""# Idée de jeu Roblox

Générée le : {now}

Genres fréquents : {genres}

Jeu à étudier : {best}

## Prototype proposé : Fusion Survival

- Une petite carte de survie multijoueur
- Des ressources à récolter
- Des améliorations à débloquer
- Des événements aléatoires
- Des parties courtes adaptées au mobile
- Des récompenses quotidiennes

Cette idée est une piste à tester. Les scores ne garantissent
ni la popularité ni les revenus d'un futur jeu.
"""

    (DATA / "game_idea.md").write_text(idea, encoding="utf-8")

    print(f"Jeux analysés : {len(games)}")
    print(f"Jeux comparables : {result['games_comparable']}")
    print(f"Relevés conservés : {len(history['snapshots'])}")
    print(f"Jeux en hausse : {len(rising_games)}")
    print(f"Jeux à potentiel : {len(growing_games)}")
    print("Rapport : data/analysis.json")


if __name__ == "__main__":
    main()

