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
    """Charge un fichier JSON sans faire planter le programme."""
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    """Enregistre des données au format JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def parse_datetime(value):
    """Convertit une date en datetime compatible avec UTC."""
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def get_snapshot_time(snapshot):
    """Récupère la date d'un relevé historique."""
    return parse_datetime(
        snapshot.get("timestamp") or snapshot.get("time")
    )


def get_game_map(games):
    """Indexe les jeux par leur identifiant Roblox."""
    result = {}

    if not isinstance(games, list):
        return result

    for game in games:
        if not isinstance(game, dict):
            continue

        game_id = game.get("id") or game.get("universeId")

        if game_id is None:
            continue

        result[str(game_id)] = game

    return result


def get_player_count(game):
    """Récupère le nombre de joueurs actifs."""
    for key in ("playing", "playerCount", "players", "playingCount"):
        value = game.get(key)

        if isinstance(value, (int, float)):
            return max(0, int(value))

    return 0


def get_game_name(game):
    """Récupère le nom du jeu."""
    return (
        game.get("name")
        or game.get("title")
        or "Jeu Roblox sans nom"
    )


def get_genre(game):
    """Récupère le genre si les données le contiennent."""
    return (
        game.get("genre")
        or game.get("genreName")
        or game.get("category")
        or "Inconnu"
    )


def percentage_change(previous, current):
    """Calcule l'évolution en pourcentage."""
    if previous <= 0:
        return None

    return round(((current - previous) / previous) * 100, 2)
