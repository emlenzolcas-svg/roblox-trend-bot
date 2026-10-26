import json
import math
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path("data")
TRENDS_FILE = DATA_DIR / "trends.json"
HISTORY_FILE = DATA_DIR / "history.json"
ANALYSIS_FILE = DATA_DIR / "analysis.json"
IDEA_FILE = DATA_DIR / "game_idea.md"

MIN_COMPARISON_HOURS = 0.5
MAX_HISTORY_SNAPSHOTS = 100
MIN_PLAYERS_FOR_GROWTH = 25


def read_json(path, default):
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    temporary.replace(path)


def parse_timestamp(value):
    if not value or not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def number(value, default=0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def game_id(game):
    value = game.get("universeId", game.get("game_id"))
    return str(value) if value is not None else None


def deduplicate(games):
    result = {}
    for game in games:
        if not isinstance(game, dict):
            continue
        identifier = game_id(game)
        if identifier:
            result[identifier] = dict(game)
            result[identifier]["game_id"] = identifier
    return list(result.values())


def approval_rate(game):
    up = number(game.get("totalUpVotes"))
    down = number(game.get("totalDownVotes"))
    total = up + down
    return round(100 * up / total, 1) if total > 0 else None


def main():
    now = datetime.now(timezone.utc)
    analyzed_at = now.isoformat()

    raw_games = read_json(TRENDS_FILE, [])
    if isinstance(raw_games, dict):
        raw_games = raw_games.get("games", [])

    games = deduplicate(raw_games)
    if not games:
        raise RuntimeError(
            "Aucun jeu trouvé dans data/trends.json. "
            "Vérifie que main.py a bien récupéré les jeux."
        )

    history = read_json(HISTORY_FILE, [])
    if not isinstance(history, list):
        history = []

    # Récupérer le relevé historique le plus récent AVANT celui-ci.
    previous_snapshot = None
    previous_time = None

    for snapshot in history:
        if not isinstance(snapshot, dict):
            continue
        stamp = parse_timestamp(snapshot.get("timestamp"))
        if stamp is None or stamp >= now:
            continue
        if previous_time is None or stamp > previous_time:
            previous_snapshot = snapshot
            previous_time = stamp

    comparison_hours = None
    previous_games = {}

    if previous_snapshot:
        previous_time = parse_timestamp(previous_snapshot.get("timestamp"))
        if previous_time:
            comparison_hours = (now - previous_time).total_seconds() / 3600

        old_games = previous_snapshot.get("games", [])
        for old_game in deduplicate(old_games):
            previous_games[game_id(old_game)] = old_game

    enough_time = (
        comparison_hours is not None
        and comparison_hours >= MIN_COMPARISON_HOURS
    )

    # Conserver tous les relevés : ils servent aux prochaines analyses.
    history.append({
        "timestamp": analyzed_at,
        "games": [
            {
                "universeId": game_id(game),
                "name": game.get("name", "Jeu inconnu"),
                "playerCount": int(number(game.get("playerCount"))),
                "genreL1": game.get("genreL1", ""),
            }
            for game in games
        ],
    })
    history = history[-MAX_HISTORY_SNAPSHOTS:]
    write_json(HISTORY_FILE, history)

    # Calculer les variations et les scores.
    player_counts = [number(g.get("playerCount")) for g in games]
    max_players = max(player_counts, default=0)

    enriched = []
    comparable = 0

    for game in games:
        identifier = game_id(game)
        players = int(number(game.get("playerCount")))
        old = previous_games.get(identifier)

        growth = None
        growth_pct = None
        growth_per_hour = None

        if old is not None:
            old_players = int(number(old.get("playerCount")))
            if old_players >= MIN_PLAYERS_FOR_GROWTH:
                comparable += 1
                growth = players - old_players
                growth_pct = round(100 * growth / old_players, 2)

                if enough_time:
                    growth_per_hour = round(
                        growth / comparison_hours, 2
                    )

        up = number(game.get("totalUpVotes"))
        down = number(game.get("totalDownVotes"))
        rate = approval_rate(game)

        # Popularité basée sur les joueurs actuels, pas sur la croissance.
        popularity = (
            100 * math.log1p(max(0, players))
            / math.log1p(max_players)
            if max_players > 0 else 0
        )

        # Croissance seulement lorsque l'intervalle est assez long.
        if enough_time and growth_pct is not None:
            growth_score = max(0, min(100, 50 + growth_pct * 5))
        else:
            growth_score = 0

        # Potentiel indicatif : popularité, avis et croissance positive.
        rating_score = rate if rate is not None else 50
        positive_growth_bonus = (
            min(20, max(0, growth_pct))
            if enough_time and growth_pct is not None else 0
        )
        potential = (
            0.55 * popularity
            + 0.35 * rating_score
            + 0.10 * (positive_growth_bonus * 5)
        )

        trend_score = (
            0.60 * popularity + 0.40 * growth_score
            if enough_time and growth_pct is not None
            else 0.75 * popularity + 0.25 * rating_score
        )

        item = dict(game)
        item.update({
            "game_id": identifier,
            "genre": game.get("genreL1") or "Inconnu",
            "approval_rate": rate,
            "player_growth": growth,
            "player_growth_pct": growth_pct,
            "growth_per_hour": growth_per_hour,
            "comparison_hours": (
                round(comparison_hours, 2)
                if comparison_hours is not None else None
            ),
            "popularity_score": round(popularity, 1),
            "growth_score": round(growth_score, 1),
            "potential_score": round(potential, 1),
            "trend_score": round(trend_score, 1),
            "trend_confirmed": bool(
                enough_time and growth_pct is not None
            ),
        })
        enriched.append(item)

    # La croissance n'est classée que si l'intervalle dépasse 30 minutes.
    valid_growth = [
        g for g in enriched
        if enough_time and g["player_growth"] is not None
        and g["player_growth"] > 0
    ]
    valid_decline = [
        g for g in enriched
        if enough_time and g["player_growth"] is not None
        and g["player_growth"] < 0
    ]

    fastest_growing = sorted(
        valid_growth,
        key=lambda g: (
            g["growth_per_hour"] if g["growth_per_hour"] is not None else 0
        ),
        reverse=True,
    )[:20]

    rising_games = sorted(
        [
            g for g in valid_growth
            if g["player_growth_pct"] is not None
            and g["player_growth_pct"] >= 1
        ],
        key=lambda g: g["player_growth_pct"],
        reverse=True,
    )[:20]

    declining_games = sorted(
        [
            g for g in valid_decline
            if g["player_growth_pct"] is not None
            and g["player_growth_pct"] <= -1
        ],
        key=lambda g: g["player_growth_pct"],
    )[:20]

    high_potential = sorted(
        enriched,
        key=lambda g: g["potential_score"],
        reverse=True,
    )[:20]

    top_games = sorted(
        enriched,
        key=lambda g: g["popularity_score"],
        reverse=True,
    )[:20]

    category_counts = {}
    for game in enriched:
        genre = game["genre"]
        category_counts[genre] = category_counts.get(genre, 0) + 1

    popular_categories = [
        {"genre": genre, "games": count}
        for genre, count in sorted(
            category_counts.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    ]

    note = (
        "Les classements de croissance nécessitent un intervalle "
        "d'au moins 30 minutes. Une variation sur un seul intervalle "
        "ne prouve pas une tendance durable. Les joueurs en ligne "
        "varient selon l'heure, les mises à jour et les événements."
    )

    if not enough_time:
        note = (
            f"Comparaison trop récente ({comparison_hours * 60:.1f} minutes) "
            "ou historique insuffisant. Les classements de croissance "
            "seront disponibles après au moins 30 minutes entre deux relevés."
        ) if comparison_hours is not None else (
            "Premier relevé : aucune comparaison historique disponible. "
            "Attends au moins 30 minutes avant la prochaine analyse."
        )

    analysis = {
        "analyzed_at": analyzed_at,
        "games_analyzed": len(enriched),
        "games_comparable": comparable,
        "history_snapshots": len(history),
        "comparison_hours": (
            round(comparison_hours, 2)
            if comparison_hours is not None else None
        ),
        "popular_categories": popular_categories,
        "top_games": top_games,
        "fastest_growing_games": fastest_growing,
        "high_potential_games": high_potential,
        "rising_games": rising_games,
        "declining_games": declining_games,
        "note": note,
    }

    write_json(ANALYSIS_FILE, analysis)

    # Générer une idée fondée sur les genres observés.
    leading_genre = (
        popular_categories[0]["genre"]
        if popular_categories else "Simulation"
    )
    rising_genre = (
        rising_games[0].get("genre")
        if rising_games else leading_genre
    )

    idea = f"""# Idée de jeu Roblox

## Concept recommandé : {rising_genre} avec une mécanique de progression

### Pourquoi ce choix ?
- Genre le plus représenté dans les données : **{leading_genre}**.
- Genre en croissance : **{rising_genre if rising_games else "pas encore confirmé"}**.
- Jeux analysés : **{len(enriched)}**.
- Comparaison suffisamment longue : **{"oui" if enough_time else "non"}**.

### Boucle de jeu
1. Le joueur commence avec un équipement simple.
2. Il réalise des défis courts pour gagner des récompenses.
3. Il améliore son équipement et débloque de nouvelles zones.
4. Il peut jouer avec ses amis et comparer ses résultats.
5. Des événements temporaires apportent de nouveaux objectifs.

### Pour se différencier
- Une progression rapide au début.
- Des objectifs quotidiens faciles à comprendre.
- Des récompenses visuelles rares.
- Des mises à jour régulières sans rendre le jeu pay-to-win.

### Attention
Cette idée est une piste à tester, pas une prédiction de succès.
Les données actuelles mesurent les joueurs en ligne, pas les revenus,
la rétention ni la difficulté de développement.
"""
    IDEA_FILE.write_text(idea, encoding="utf-8")

    print(f"Jeux analysés : {len(enriched)}")
    print(f"Jeux comparables : {comparable}")
    print(f"Historique : {len(history)} relevés")
    print(f"Intervalle (heures) : {analysis['comparison_hours']}")
    print(f"Croissances détectées : {len(fastest_growing)}")
    print(f"Tendances haussières : {len(rising_games)}")
    print(f"Tendances baissières : {len(declining_games)}")
    print(f"Rapport écrit : {ANALYSIS_FILE}")
    print(f"Idée écrite : {IDEA_FILE}")
    print(note)


if __name__ == "__main__":
    main()
