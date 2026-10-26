import json
import math
from pathlib import Path
from datetime import datetime, timezone

DATA = Path("data")
SOURCE = DATA / "trends.json"
HISTORY = DATA / "history.json"
ANALYSIS = DATA / "analysis.json"
IDEA = DATA / "game_idea.md"
MAX_SNAPSHOTS = 30
MIN_PLAYERS_FOR_RANKING = 25


def read_json(path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def number(value, default=0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def parse_timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def game_id(game):
    uid = game.get("universeId")
    return str(uid) if uid is not None else None


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(
            "data/trends.json introuvable. Lance main.py d'abord."
        )

    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()

    source_report = read_json(SOURCE, {})
    raw_games = source_report.get("games", [])

    if not isinstance(raw_games, list):
        raise ValueError(
            "Le champ 'games' dans data/trends.json doit être une liste."
        )

    # Supprimer les doublons de jeux.
    unique = {}
    for item in raw_games:
        if isinstance(item, dict) and game_id(item) is not None:
            unique[game_id(item)] = item

    games = list(unique.values())

    history = read_json(HISTORY, {"snapshots": []})
    snapshots = history.get("snapshots", [])

    if not isinstance(snapshots, list):
        snapshots = []

    history_by_game = {}

    # Organiser l'historique par jeu.
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue

        stamp = parse_timestamp(snapshot.get("timestamp"))
        snapshot_games = snapshot.get("games", {})

        if not isinstance(snapshot_games, dict):
            continue

        for uid, old_game in snapshot_games.items():
            if isinstance(old_game, dict) and "players" in old_game:
                history_by_game.setdefault(str(uid), []).append(
                    (stamp, old_game)
                )

    for uid in history_by_game:
        history_by_game[uid].sort(
            key=lambda item: item[0]
            or datetime.min.replace(tzinfo=timezone.utc)
        )

    current = {}

    for game in games:
        uid = game_id(game)

        players = max(0, int(number(game.get("playerCount"))))
        up = max(0, int(number(game.get("totalUpVotes"))))
        down = max(0, int(number(game.get("totalDownVotes"))))

        votes = up + down
        approval = up / votes if votes else None

        approval_score = (
            round(approval * 100, 1)
            if approval is not None
            else None
        )

        # Trouver le relevé antérieur le plus récent.
        previous = None

        for stamp, old_game in reversed(history_by_game.get(uid, [])):
            if stamp is not None and stamp < now_dt:
                old_players = max(
                    0, int(number(old_game.get("players")))
                )
                previous = (stamp, old_players)
                break

        growth = None
        growth_pct = None
        growth_per_hour = None
        elapsed_hours = None

        if previous is not None:
            old_stamp, old_players = previous
            growth = players - old_players

            if old_players > 0:
                growth_pct = round(
                    growth * 100 / old_players, 2
                )

            elapsed_hours = (
                now_dt - old_stamp
            ).total_seconds() / 3600

            if elapsed_hours > 0:
                growth_per_hour = round(
                    growth / elapsed_hours, 2
                )

        # Popularité : logarithmique pour limiter l'avantage
        # automatique des plus grands jeux.
        popularity_score = clamp(
            math.log10(players + 1)
            / math.log10(1_000_001)
            * 100
        )

        # Croissance relative plafonnée pour réduire les extrêmes.
        if growth_pct is not None:
            limited_growth = max(-15, min(15, growth_pct))
            growth_score = clamp(50 + 3 * limited_growth)
        else:
            growth_score = None

        # Potentiel : croissance, taille, approbation et base de joueurs.
        if growth_pct is not None:
            limited_growth = max(-15, min(15, growth_pct))
            size_bonus = 18 * (1 - min(players / 500_000, 1))
            base_bonus = min(
                10, math.log10(players + 1) * 3
            )

            approval_bonus = (
                (approval_score - 50) * 0.20
                if approval_score is not None
                else 0
            )

            potential_score = clamp(
                50
                + 2.5 * limited_growth
                + size_bonus
                + base_bonus
                + approval_bonus
            )
        else:
            potential_score = None

        # Score de tendance équilibré.
        effective_growth = (
            growth_score if growth_score is not None else 50
        )
        effective_approval = (
            approval_score if approval_score is not None else 50
        )

        trend_score = clamp(
            popularity_score * 0.25
            + effective_growth * 0.45
            + effective_approval * 0.30
        )

        # Une tendance n'est confirmée qu'après plusieurs relevés.
        prior_observations = len(history_by_game.get(uid, []))
        trend_confirmed = (
            prior_observations >= 2
            and growth_pct is not None
        )

        game["approval_rate"] = approval_score
        game["player_growth"] = growth
        game["player_growth_pct"] = growth_pct
        game["growth_per_hour"] = growth_per_hour
        game["comparison_hours"] = (
            round(elapsed_hours, 2)
            if elapsed_hours is not None
            else None
        )
        game["popularity_score"] = round(
            popularity_score, 1
        )
        game["growth_score"] = (
            round(growth_score, 1)
            if growth_score is not None
            else None
        )
        game["potential_score"] = (
            round(potential_score, 1)
            if potential_score is not None
            else None
        )
        game["trend_confirmed"] = trend_confirmed
        game["trend_score"] = round(trend_score, 1)

        current[uid] = {
            "name": game.get("name", "Jeu inconnu"),
            "players": players,
        }

    # Enregistrer le snapshot après les comparaisons.
    snapshots.append({
        "timestamp": now,
        "games": current,
    })

    history["snapshots"] = [
        snapshot
        for snapshot in snapshots[-MAX_SNAPSHOTS:]
        if isinstance(snapshot, dict)
        and isinstance(snapshot.get("games"), dict)
    ]

    write_json(HISTORY, history)

    # Classement général.
    top_games = sorted(
        games,
        key=lambda game: (
            number(game.get("trend_score")),
            number(game.get("playerCount")),
        ),
        reverse=True,
    )[:30]

    comparable = [
        game for game in games
        if game["player_growth"] is not None
    ]

    eligible = [
        game for game in comparable
        if number(game.get("playerCount"))
        >= MIN_PLAYERS_FOR_RANKING
    ]

    # Jeux qui gagnent le plus de joueurs par heure.
    fastest_growing_games = sorted(
        [
            game for game in eligible
            if number(game.get("player_growth")) > 0
        ],
        key=lambda game: (
            number(game.get("growth_per_hour")),
            number(game.get("player_growth")),
        ),
        reverse=True,
    )[:30]

    # Jeux en hausse avec un potentiel intéressant.
    high_potential_games = sorted(
        [
            game for game in eligible
            if number(game.get("player_growth_pct")) > 0
            and game.get("potential_score") is not None
        ],
        key=lambda game: (
            number(game.get("potential_score")),
            number(game.get("player_growth_pct")),
        ),
        reverse=True,
    )[:30]

    # Hausse en pourcentage.
    rising_games = sorted(
        [
            game for game in eligible
            if number(game.get("player_growth_pct")) > 0
        ],
        key=lambda game: number(
            game.get("player_growth_pct")
        ),
        reverse=True,
    )[:30]

    # Jeux qui perdent des joueurs.
    declining_games = sorted(
        [
            game for game in eligible
            if number(game.get("player_growth")) < 0
        ],
        key=lambda game: (
            number(game.get("growth_per_hour")),
            number(game.get("player_growth")),
        ),
    )[:20]

    # Genres les plus présents dans les données collectées.
    categories = {}

    for game in games:
        genre = game.get("genreL1") or "Inconnu"
        categories[genre] = categories.get(genre, 0) + 1

    result = {
        "analyzed_at": now,
        "games_analyzed": len(games),
        "games_comparable": len(comparable),
        "history_snapshots": len(history["snapshots"]),
        "note": (
            "Les scores sont des indicateurs heuristiques, pas des "
            "prédictions. La croissance horaire facilite les comparaisons "
            "entre relevés espacés différemment. Les joueurs peuvent "
            "varier selon l'heure, les mises à jour et les événements. "
            "Plusieurs relevés sont nécessaires pour confirmer une tendance."
        ),
        "popular_categories": sorted(
            [
                {"genre": genre, "games": count}
                for genre, count in categories.items()
            ],
            key=lambda item: item["games"],
            reverse=True,
        ),
        "top_games": top_games,
        "fastest_growing_games": fastest_growing_games,
        "high_potential_games": high_potential_games,
        "rising_games": rising_games,
        "declining_games": declining_games,
    }

    write_json(ANALYSIS, result)

    # Créer une idée à partir des données, si un signal existe.
    genres = [
        item["genre"]
        for item in result["popular_categories"][:3]
    ]

    best = high_potential_games[0] if high_potential_games else None

    if best:
        best_name = best.get("name", "Jeu à étudier")
        best_genre = best.get("genreL1") or "genre à confirmer"
        best_growth = best.get("player_growth_pct")

        evidence = (
            f"Signal observé : {best_growth:+.2f}% entre deux relevés."
            if isinstance(best_growth, (int, float))
            else "Signal de croissance à confirmer."
        )

        concept = (
            f"Étudier les mécaniques générales du genre {best_genre}, "
            f"observées notamment dans {best_name}, sans copier ce jeu. "
            "Créer une boucle de progression courte, un objectif "
            "multijoueur clair et des événements variables."
        )
    else:
        best_name = (
            "Pas encore de tendance émergente suffisamment documentée"
        )
        evidence = "Attendre davantage de relevés comparables."
        concept = (
            "Tester un petit prototype multijoueur avec une boucle "
            "simple, puis comparer les résultats aux tendances suivantes."
        )

    idea = f"""# Idée de jeu Roblox

Générée le : {now}

## Genres les plus présents
{chr(10).join(f"- {genre}" for genre in genres) if genres else "- À confirmer"}

## Signal à étudier
{best_name}

{evidence}

## Prototype proposé : mini-jeu multijoueur à progression

{concept}

### Boucle de jeu à tester
- Une partie courte avec un objectif facile à comprendre
- Des améliorations débloquées grâce à la progression
- Des événements variables pour renouveler les parties
- Une expérience adaptée aux contrôles mobiles
- Des tests auprès de joueurs avant d'ajouter beaucoup de contenu

### Limites
Les données ne garantissent pas le succès d'un nouveau jeu.
Les variations peuvent dépendre de l'heure, des mises à jour et des événements.
Ne copie pas les noms, cartes, personnages ou contenus protégés d'autres jeux.
"""

    IDEA.write_text(idea, encoding="utf-8")

    print(f"Jeux analysés : {len(games)}")
    print(f"Jeux comparables : {result['games_comparable']}")
    print(f"Relevés conservés : {len(history['snapshots'])}")
    print(f"Jeux en hausse : {len(rising_games)}")
    print(f"Jeux à potentiel : {len(high_potential_games)}")
    print(f"Jeux en déclin : {len(declining_games)}")
    print(f"Rapport : {ANALYSIS}")


if __name__ == "__main__":
    main()
