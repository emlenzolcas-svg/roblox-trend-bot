
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


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
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
    return parse_datetime(snapshot.get("timestamp") or snapshot.get("time"))


def game_map(games):
    result = {}
    if not isinstance(games, list):
        return result

    for game in games:
        if not isinstance(game, dict):
            continue
        game_id = game.get("id") or game.get("universeId")
        if game_id is not None:
            result[str(game_id)] = game
    return result


def player_count(game):
    for key in ("playing", "playerCount", "players", "playingCount"):
        value = game.get(key)
        if isinstance(value, (int, float)):
            return max(0, int(value))
    return 0


def game_name(game):
    return game.get("name") or game.get("title") or "Jeu Roblox sans nom"


def game_genre(game):
    return (
        game.get("genre")
        or game.get("genreName")
        or game.get("category")
        or "Inconnu"
    )


def pct_change(previous, current):
    if previous <= 0:
        return None
    return round((current - previous) / previous * 100, 2)


def get_valid_history(history, now):
    valid = []

    if not isinstance(history, list):
        return valid

    for snapshot in history:
        if not isinstance(snapshot, dict):
            continue

        timestamp = snapshot_time(snapshot)
        games = snapshot.get("games")

        if timestamp is None or not isinstance(games, list):
            continue

        if timestamp <= now:
            valid.append({
                "timestamp": timestamp,
                "games": games,
            })

    valid.sort(key=lambda item: item["timestamp"])
    return valid[-MAX_HISTORY_SNAPSHOTS:]


def calculate_game_trend(game_id, history, current_count, now):
    observations = []

    for snapshot in history:
        elapsed = (now - snapshot["timestamp"]).total_seconds() / 3600

        if elapsed < MIN_COMPARISON_HOURS:
            continue

        games = game_map(snapshot["games"])
        previous_game = games.get(str(game_id))

        if previous_game is None:
            continue

        previous_count = player_count(previous_game)

        if previous_count < MIN_PLAYERS_FOR_GROWTH:
            continue

        observations.append({
            "hours": round(elapsed, 2),
            "players": previous_count,
        })

    observations.sort(key=lambda item: item["hours"])
    observations = observations[:MAX_HISTORY_SNAPSHOTS]

    if not observations:
        return {
            "growth_pct": None,
            "player_change": None,
            "comparison_hours": None,
            "trend_confirmed": False,
            "trend_intervals": 0,
            "trend_direction": "insufficient_data",
        }

    nearest = observations[0]
    change = current_count - nearest["players"]
    growth = pct_change(nearest["players"], current_count)

    # Compte les comparaisons historiques qui vont dans la même direction.
    directions = []

    for observation in observations:
        delta = current_count - observation["players"]
        if delta > 0:
            directions.append("up")
        elif delta < 0:
            directions.append("down")
        else:
            directions.append("flat")

    positive_intervals = sum(1 for direction in directions if direction == "up")
    negative_intervals = sum(1 for direction in directions if direction == "down")

    if positive_intervals >= MIN_TREND_INTERVALS and positive_intervals > negative_intervals:
        direction = "up"
    elif negative_intervals >= MIN_TREND_INTERVALS and negative_intervals > positive_intervals:
        direction = "down"
    else:
        direction = "uncertain"

    return {
        "growth_pct": growth,
        "player_change": change,
        "comparison_hours": nearest["hours"],
        "trend_confirmed": direction in ("up", "down"),
        "trend_intervals": max(positive_intervals, negative_intervals),
        "trend_direction": direction,
    }


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    trends_data = load_json(TRENDS_FILE, {})
    history = load_json(HISTORY_FILE, [])

    if isinstance(trends_data, dict):
        games = trends_data.get("games", [])
        source_timestamp = (
            trends_data.get("timestamp")
            or trends_data.get("time")
        )
    elif isinstance(trends_data, list):
        games = trends_data
        source_timestamp = None
    else:
        games = []
        source_timestamp = None

    if not isinstance(games, list):
        games = []

    now = parse_datetime(source_timestamp) or datetime.now(timezone.utc)
    valid_history = get_valid_history(history, now)

    # Évite d'enregistrer plusieurs fois exactement le même relevé.
    if not valid_history or valid_history[-1]["timestamp"] != now:
        valid_history.append({
            "timestamp": now,
            "games": games,
        })

    valid_history = valid_history[-MAX_HISTORY_SNAPSHOTS:]

    analyzed_games = []

    for game in games:
        if not isinstance(game, dict):
            continue

        game_id = game.get("id") or game.get("universeId")
        if game_id is None:
            continue

        current_players = player_count(game)
        trend = calculate_game_trend(
            game_id,
            valid_history[:-1],
            current_players,
            now,
        )

        growth_pct = trend["growth_pct"]
        player_change = trend["player_change"]

        popularity_score = min(100, round(current_players / 1000, 2))

        growth_score = 0
        if growth_pct is not None:
            growth_score = max(-100, min(100, growth_pct))

        trend_score = round(
            popularity_score + growth_score,
            2,
        )

        analyzed_games.append({
            **game,
            "id": str(game_id),
            "name": game_name(game),
            "genre": game_genre(game),
            "players": current_players,
            "player_change": player_change,
            "growth_pct": growth_pct,
            "comparison_hours": trend["comparison_hours"],
            "trend_confirmed": trend["trend_confirmed"],
            "trend_intervals": trend["trend_intervals"],
            "trend_direction": trend["trend_direction"],
            "popularity_score": popularity_score,
            "growth_score": growth_score,
            "trend_score": trend_score,
        })

    analyzed_games.sort(
        key=lambda item: item["trend_score"],
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

    # Le genre dominant parmi les jeux en hausse est prioritaire.
    genre_counts = {}
    for game in rising_games:
        genre = game["genre"]
        if genre != "Inconnu":
            genre_counts[genre] = genre_counts.get(genre, 0) + 1

    if genre_counts:
        leading_genre = max(genre_counts, key=genre_counts.get)
        recommendation_reason = "genre en hausse confirmé"
    else:
        popular_genres = {}
        for game in analyzed_games:
            genre = game["genre"]
            if genre != "Inconnu":
                popular_genres[genre] = (
                    popular_genres.get(genre, 0) + game["players"]
                )

        leading_genre = (
            max(popular_genres, key=popular_genres.get)
            if popular_genres else "À déterminer"
        )
        recommendation_reason = "genre populaire, tendance non confirmée"

    report = {
        "generated_at": now.isoformat(),
        "games_analyzed": len(analyzed_games),
        "rising_games_count": len(rising_games),
        "declining_games_count": len(declining_games),
        "history_snapshots": len(valid_history),
        "leading_genre": leading_genre,
        "recommendation_reason": recommendation_reason,
        "rising_games": rising_games[:30],
        "declining_games": declining_games[:30],
        "top_games": analyzed_games[:50],
        "games": analyzed_games,
    }

    save_json(ANALYSIS_FILE, report)

    history_to_save = [
        {
            "timestamp": item["timestamp"].isoformat(),
            "games": item["games"],
        }
        for item in valid_history
    ]
    save_json(HISTORY_FILE, history_to_save)

    idea = f"""# Idée de jeu Roblox

## Genre recommandé
{leading_genre}

## Pourquoi ce choix ?
{recommendation_reason}

## Jeux en hausse confirmée
"""

    if rising_games:
        for game in rising_games[:10]:
            idea += (
                f"- **{game['name']}** — "
                f"{game['players']} joueurs, "
                f"évolution de {game['growth_pct']} % "
                f"sur environ {game['comparison_hours']} h.\\n"
            )
    else:
        idea += (
            "- Aucune hausse confirmée pour le moment. "
            "Le bot attend davantage de relevés.\\n"
        )

    idea += """
## Prochaine étape
Créer un concept original dans ce genre, puis tester son gameplay.
Ne copie pas directement les jeux existants.
"""

    with open(GAME_IDEA_FILE, "w", encoding="utf-8") as file:
        file.write(idea)

    print("Analyse terminée.")
    print(f"Jeux analysés : {len(analyzed_games)}")
    print(f"Tendances en hausse confirmées : {len(rising_games)}")
    print(f"Tendances en baisse confirmées : {len(declining_games)}")
    print(f"Genre recommandé : {leading_genre}")
    print(f"Rapport : {ANALYSIS_FILE}")
    print(f"Idée de jeu : {GAME_IDEA_FILE}")


if __name__ == "__main__":
    main()
