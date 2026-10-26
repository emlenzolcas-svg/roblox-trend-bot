
import json
import os
from datetime import datetime, timezone

DATA_DIR = "data"
TRENDS_FILE = os.path.join(DATA_DIR, "trends.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
ANALYSIS_FILE = os.path.join(DATA_DIR, "analysis.json")
GAME_IDEA_FILE = os.path.join(DATA_DIR, "game_idea.md")

MIN_COMPARISON_HOURS = 0.5
MAX_HISTORY_SNAPSHOTS = 100
MIN_PLAYERS_FOR_GROWTH = 25
MIN_TREND_INTERVALS = 2
MIN_GROWTH_PCT = 1.0
MAX_REPORT_GAMES = 50


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def parse_datetime(value):
    if not value:
        return None

    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def snapshot_time(snapshot):
    if not isinstance(snapshot, dict):
        return None

    return parse_datetime(
        snapshot.get("timestamp") or snapshot.get("time")
    )


def game_id_of(game):
    if not isinstance(game, dict):
        return None

    value = game.get("universeId") or game.get("id")
    return str(value) if value is not None else None


def player_count(game):
    if not isinstance(game, dict):
        return 0

    for key in ("playing", "playerCount", "players", "playingCount"):
        value = game.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return max(0, int(value))

    return 0


def game_name(game):
    return game.get("name") or game.get("title") or "Jeu Roblox sans nom"


def game_genre(game):
    for key in ("genreL1", "genre", "genreName", "category", "genreL2"):
        value = game.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return "Inconnu"


def pct_change(previous, current):
    if previous <= 0:
        return None

    return round((current - previous) / previous * 100, 2)


def deduplicate_games(games):
    """Garde une seule entrée par univers Roblox."""
    merged = {}

    if not isinstance(games, list):
        return []

    for game in games:
        if not isinstance(game, dict):
            continue

        game_id = game_id_of(game)
        if game_id is None:
            continue

        if game_id not in merged:
            merged[game_id] = dict(game)
        else:
            existing = merged[game_id]

            # Complète les champs absents.
            for key, value in game.items():
                if existing.get(key) in (None, "") and value not in (None, ""):
                    existing[key] = value

            # Garde le plus grand nombre de joueurs observé dans les fiches.
            if player_count(game) > player_count(existing):
                for key, value in game.items():
                    if value not in (None, ""):
                        existing[key] = value

        merged[game_id]["id"] = game_id
        merged[game_id]["players"] = player_count(merged[game_id])

    return list(merged.values())


def normalize_history(history, now):
    """Nettoie l'historique et trie les snapshots par date."""
    by_timestamp = {}

    if not isinstance(history, list):
        return []

    for snapshot in history:
        if not isinstance(snapshot, dict):
            continue

        timestamp = snapshot_time(snapshot)
        games = snapshot.get("games")

        if timestamp is None or timestamp > now:
            continue
        if not isinstance(games, list):
            continue

        by_timestamp[timestamp.isoformat()] = {
            "timestamp": timestamp,
            "games": deduplicate_games(games),
        }

    result = sorted(
        by_timestamp.values(),
        key=lambda item: item["timestamp"],
    )

    return result[-MAX_HISTORY_SNAPSHOTS:]


def make_game_map(games):
    return {
        game_id_of(game): game
        for game in games
        if game_id_of(game) is not None
    }


def calculate_game_trend(game_id, history, current_count, now):
    """
    Calcule les variations entre snapshots espacés d'au moins 30 minutes.
    Une tendance n'est confirmée qu'après plusieurs intervalles cohérents.
    """
    observations = []

    for snapshot in history:
        game = make_game_map(snapshot["games"]).get(str(game_id))

        if game is None:
            continue

        count = player_count(game)
        timestamp = snapshot["timestamp"]

        if count >= MIN_PLAYERS_FOR_GROWTH and timestamp < now:
            observations.append((timestamp, count))

    observations.append((now, current_count))
    observations.sort(key=lambda item: item[0])

    # Une seule observation par instant.
    unique = {}
    for timestamp, count in observations:
        unique[timestamp] = count

    observations = sorted(unique.items())
    deltas = []

    for index in range(1, len(observations)):
        previous_time, previous_count = observations[index - 1]
        current_time, observed_count = observations[index]

        hours = (current_time - previous_time).total_seconds() / 3600

        if hours < MIN_COMPARISON_HOURS:
            continue
        if previous_count < MIN_PLAYERS_FOR_GROWTH:
            continue

        growth = pct_change(previous_count, observed_count)
        if growth is None:
            continue

        deltas.append({
            "hours": hours,
            "previous": previous_count,
            "current": observed_count,
            "change": observed_count - previous_count,
            "growth_pct": growth,
        })

    if not deltas:
        return {
            "growth_pct": None,
            "player_change": None,
            "comparison_hours": None,
            "trend_confirmed": False,
            "trend_intervals": 0,
            "trend_direction": "insufficient_data",
            "interval_growth_pct": [],
        }

    latest = deltas[-1]
    recent = deltas[-3:]
    changes = [item["growth_pct"] for item in recent]

    rising_count = sum(value >= MIN_GROWTH_PCT for value in changes)
    falling_count = sum(value <= -MIN_GROWTH_PCT for value in changes)

    confirmed_up = (
        len(recent) >= MIN_TREND_INTERVALS
        and rising_count >= MIN_TREND_INTERVALS
        and changes[-1] >= MIN_GROWTH_PCT
    )

    confirmed_down = (
        len(recent) >= MIN_TREND_INTERVALS
        and falling_count >= MIN_TREND_INTERVALS
        and changes[-1] <= -MIN_GROWTH_PCT
    )

    if confirmed_up:
        direction = "up"
        interval_count = rising_count
    elif confirmed_down:
        direction = "down"
        interval_count = falling_count
    else:
        direction = "uncertain"
        interval_count = len(recent)

    return {
        "growth_pct": latest["growth_pct"],
        "player_change": latest["change"],
        "comparison_hours": round(latest["hours"], 2),
        "trend_confirmed": direction in ("up", "down"),
        "trend_intervals": interval_count,
        "trend_direction": direction,
        "interval_growth_pct": changes,
    }


def choose_leading_genre(games, rising_games):
    """Choisit un genre en hausse confirmée, sinon le plus populaire."""
    rising_scores = {}

    for game in rising_games:
        genre = game["genre"]

        if genre == "Inconnu":
            continue

        rising_scores[genre] = (
            rising_scores.get(genre, 0) + game["players"]
        )

    if rising_scores:
        genre = max(rising_scores, key=rising_scores.get)
        return genre, "genre avec le plus de joueurs parmi les hausses confirmées"

    popularity_scores = {}

    for game in games:
        genre = game["genre"]

        if genre == "Inconnu":
            continue

        popularity_scores[genre] = (
            popularity_scores.get(genre, 0) + game["players"]
        )

    if popularity_scores:
        genre = max(popularity_scores, key=popularity_scores.get)
        return genre, "genre le plus populaire; tendance non confirmée"

    return "À déterminer", "données de genre insuffisantes"


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    trends_data = load_json(TRENDS_FILE, {})
    old_history = load_json(HISTORY_FILE, [])

    if isinstance(trends_data, dict):
        raw_games = trends_data.get("games", [])
        source_timestamp = (
            trends_data.get("timestamp")
            or trends_data.get("time")
            or trends_data.get("generated_at")
        )
    elif isinstance(trends_data, list):
        raw_games = trends_data
        source_timestamp = None
    else:
        raw_games = []
        source_timestamp = None

    if not isinstance(raw_games, list):
        raw_games = []

    current_games = deduplicate_games(raw_games)
    now = parse_datetime(source_timestamp) or datetime.now(timezone.utc)

    history = normalize_history(old_history, now)

    # Évite de comparer un snapshot avec lui-même.
    history = [
        snapshot for snapshot in history
        if snapshot["timestamp"] != now
    ]

    analyzed_games = []

    for game in current_games:
        game_id = game_id_of(game)
        if game_id is None:
            continue

        players = player_count(game)

        trend = calculate_game_trend(
            game_id=game_id,
            history=history,
            current_count=players,
            now=now,
        )

        growth = trend["growth_pct"]
        popularity_score = min(100.0, round(players / 1000, 2))

        growth_score = (
            0.0
            if growth is None
            else max(-50.0, min(50.0, growth * 2))
        )

        trend_bonus = (
            15.0
            if trend["trend_confirmed"]
            and trend["trend_direction"] == "up"
            else 0.0
        )

        trend_penalty = (
            10.0
            if trend["trend_confirmed"]
            and trend["trend_direction"] == "down"
            else 0.0
        )

        analyzed_games.append({
            **game,
            "id": game_id,
            "name": game_name(game),
            "genre": game_genre(game),
            "players": players,
            "player_change": trend["player_change"],
            "growth_pct": growth,
            "comparison_hours": trend["comparison_hours"],
            "trend_confirmed": trend["trend_confirmed"],
            "trend_intervals": trend["trend_intervals"],
            "trend_direction": trend["trend_direction"],
            "interval_growth_pct": trend["interval_growth_pct"],
            "popularity_score": popularity_score,
            "growth_score": growth_score,
            "trend_score": round(
                popularity_score + growth_score
                + trend_bonus - trend_penalty,
                2,
            ),
        })

    analyzed_games.sort(
        key=lambda game: (game["trend_score"], game["players"]),
        reverse=True,
    )

    rising_games = [
        game for game in analyzed_games
        if game["trend_confirmed"]
        and game["trend_direction"] == "up"
        and game["growth_pct"] is not None
        and game["growth_pct"] >= MIN_GROWTH_PCT
    ]

    declining_games = [
        game for game in analyzed_games
        if game["trend_confirmed"]
        and game["trend_direction"] == "down"
        and game["growth_pct"] is not None
        and game["growth_pct"] <= -MIN_GROWTH_PCT
    ]

    leading_genre, reason = choose_leading_genre(
        analyzed_games,
        rising_games,
    )

    # Enregistre le snapshot actuel pour les prochaines analyses.
    history.append({
        "timestamp": now,
        "games": current_games,
    })
    history = history[-MAX_HISTORY_SNAPSHOTS:]

    report = {
        "generated_at": now.isoformat(),
        "games_analyzed": len(analyzed_games),
        "rising_games_count": len(rising_games),
        "declining_games_count": len(declining_games),
        "history_snapshots": len(history),
        "leading_genre": leading_genre,
        "recommendation_reason": reason,
        "rising_games": rising_games[:MAX_REPORT_GAMES],
        "declining_games": declining_games[:MAX_REPORT_GAMES],
        "top_games": analyzed_games[:MAX_REPORT_GAMES],
        "games": analyzed_games,
    }

    save_json(ANALYSIS_FILE, report)

    history_to_save = [
        {
            "timestamp": snapshot["timestamp"].isoformat(),
            "games": snapshot["games"],
        }
        for snapshot in history
    ]
    save_json(HISTORY_FILE, history_to_save)

    idea_lines = [
        "# Idée de jeu Roblox",
        "",
        "## Genre recommandé",
        leading_genre,
        "",
        "## Pourquoi ce choix ?",
        reason,
        "",
        "## Jeux en hausse confirmée",
    ]

    if rising_games:
        for game in rising_games[:10]:
            hours = game["comparison_hours"]
            duration = (
                f"{hours} heure(s)"
                if hours is not None
                else "durée inconnue"
            )
            idea_lines.append(
                f"- **{game['name']}** — {game['players']:,} joueurs, "
                f"variation de {game['growth_pct']} % sur {duration}."
            )
    else:
        idea_lines.append(
            "- Pas encore de hausse confirmée. "
            "Le bot attend plusieurs intervalles cohérents."
        )

    idea_lines.extend([
        "",
        "## Prochaine étape",
        "Créer un concept original à partir des tendances détectées, "
        "sans copier directement un jeu existant.",
        "",
    ])

    with open(GAME_IDEA_FILE, "w", encoding="utf-8") as file:
        file.write("\n".join(idea_lines))

    print("Analyse terminée.")
    print(f"Jeux uniques analysés : {len(analyzed_games)}")
    print(f"Tendances en hausse : {len(rising_games)}")
    print(f"Tendances en baisse : {len(declining_games)}")
    print(f"Snapshots historiques : {len(history)}")
    print(f"Genre recommandé : {leading_genre}")
    print(f"Rapport : {ANALYSIS_FILE}")
    print(f"Idée de jeu : {GAME_IDEA_FILE}")


if __name__ == "__main__":
    main()
