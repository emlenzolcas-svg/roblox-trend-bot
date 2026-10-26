
import json
import math
import os
import re
from datetime import datetime, timezone
from collections import defaultdict

DATA_DIR = "data"
TRENDS_FILE = os.path.join(DATA_DIR, "trends.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
ANALYSIS_FILE = os.path.join(DATA_DIR, "analysis.json")
IDEA_FILE = os.path.join(DATA_DIR, "game_idea.md")

MAX_HISTORY_SNAPSHOTS = 30
MIN_COMPARISON_HOURS = 0.5
MIN_PLAYERS_FOR_GROWTH = 25


# -----------------------------
# Fichiers et données
# -----------------------------

def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(temp_path, path)


def number(value, default=0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def game_id(game):
    for key in ("universeId", "rootPlaceId", "placeId", "id"):
        value = game.get(key)
        if value is not None:
            return str(value)
    return re.sub(r"\s+", " ", str(game.get("name", "")).strip().lower())


def unique_games(games):
    result = {}
    for game in games if isinstance(games, list) else []:
        if not isinstance(game, dict):
            continue
        key = game_id(game)
        if key and key.strip():
            # Garde la dernière version rencontrée du jeu.
            result[key] = game
    return list(result.values())


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def percentile_rank(value, values):
    """Rang relatif entre 0 et 100, moins sensible aux valeurs extrêmes."""
    if not values:
        return 50.0
    below = sum(v < value for v in values)
    equal = sum(v == value for v in values)
    return 100.0 * (below + 0.5 * equal) / len(values)


def get_player_count(game):
    return max(0, number(game.get("playerCount", game.get("playing", 0))))


def get_approval_rate(game):
    up = number(game.get("totalUpVotes", game.get("upVotes", 0)))
    down = number(game.get("totalDownVotes", game.get("downVotes", 0)))
    total = up + down
    return round(100 * up / total, 1) if total > 0 else None


# -----------------------------
# Chargement
# -----------------------------

os.makedirs(DATA_DIR, exist_ok=True)

raw_games = read_json(TRENDS_FILE, [])
if isinstance(raw_games, dict):
    raw_games = raw_games.get("games", raw_games.get("data", []))

games = unique_games(raw_games)

if not games:
    raise SystemExit(
        "ERREUR : aucun jeu trouvé dans data/trends.json. "
        "Vérifie que main.py a bien récupéré les jeux."
    )

history = read_json(HISTORY_FILE, [])
if not isinstance(history, list):
    history = []

now = datetime.now(timezone.utc)
now_iso = now.isoformat()

# Normalise les anciens snapshots et ignore ceux sans date exploitable.
valid_history = []
for snapshot in history:
    if not isinstance(snapshot, dict):
        continue
    stamp = timestamp(snapshot.get("timestamp", snapshot.get("analyzed_at")))
    snapshot_games = snapshot.get("games", [])
    if stamp is not None and isinstance(snapshot_games, list):
        valid_history.append((stamp, snapshot))

valid_history.sort(key=lambda item: item[0])

# Ne compare qu'avec le dernier snapshot réellement antérieur au relevé actuel.
previous = None
previous_stamp = None
for stamp, snapshot in reversed(valid_history):
    if stamp < now.timestamp():
        previous = snapshot
        previous_stamp = stamp
        break

previous_games = {}
if previous:
    for game in unique_games(previous.get("games", [])):
        previous_games[game_id(game)] = game

comparison_hours = (
    (now.timestamp() - previous_stamp) / 3600
    if previous_stamp is not None else None
)

# Historique par jeu : on ne compte que les snapshots datés et distincts.
observations_by_game = defaultdict(list)
for stamp, snapshot in valid_history:
    for game in unique_games(snapshot.get("games", [])):
        observations_by_game[game_id(game)].append((stamp, game))


# -----------------------------
# Mesures de croissance
# -----------------------------

records = []

for game in games:
    key = game_id(game)
    players = get_player_count(game)
    old_game = previous_games.get(key)
    old_players = get_player_count(old_game) if old_game else None

    growth = None
    growth_pct = None
    growth_per_hour = None

    comparable = (
        old_game is not None
        and old_players is not None
        and comparison_hours is not None
        and comparison_hours > 0
    )

    if comparable:
        growth = players - old_players
        # Évite les pourcentages explosifs quand le nombre initial est minuscule.
        if old_players >= MIN_PLAYERS_FOR_GROWTH:
            growth_pct = 100 * growth / old_players
        growth_per_hour = growth / comparison_hours

    observations = observations_by_game.get(key, [])
    distinct_times = len(set(stamp for stamp, _ in observations))
    recent_growth_rates = []

    # Calcul des taux historiques sur des intervalles d'au moins 30 minutes.
    series = observations + [(now.timestamp(), game)]
    series.sort(key=lambda item: item[0])

    # Conserve uniquement la dernière observation par horodatage.
    dedup_series = {}
    for stamp, item in series:
        dedup_series[stamp] = item
    series = sorted(dedup_series.items())

    for i in range(1, len(series)):
        t0, g0 = series[i - 1]
        t1, g1 = series[i]
        hours = (t1 - t0) / 3600
        p0 = get_player_count(g0)
        p1 = get_player_count(g1)

        if hours >= MIN_COMPARISON_HOURS and p0 >= MIN_PLAYERS_FOR_GROWTH:
            recent_growth_rates.append((p1 - p0) / hours)

    # Mesure la régularité : plusieurs intervalles valides doivent progresser.
    positive_intervals = sum(rate > 0 for rate in recent_growth_rates)
    interval_count = len(recent_growth_rates)
    consistency = (
        100 * positive_intervals / interval_count
        if interval_count else 0.0
    )

    approval = get_approval_rate(game)
    genre = (
        game.get("genreL1")
        or game.get("genre")
        or game.get("genreL2")
        or "Inconnu"
    )

    records.append({
        **game,
        "name": str(game.get("name", "Jeu sans nom")).strip(),
        "game_id": key,
        "playerCount": int(players),
        "approval_rate": approval,
        "genre": genre,
        "player_growth": growth,
        "player_growth_pct": (
            round(growth_pct, 2) if growth_pct is not None else None
        ),
        "growth_per_hour": (
            round(growth_per_hour, 2)
            if growth_per_hour is not None else None
        ),
        "comparison_hours": (
            round(comparison_hours, 2)
            if comparison_hours is not None else None
        ),
        "history_observations": distinct_times,
        "valid_growth_intervals": interval_count,
        "growth_consistency": round(consistency, 1),
    })


# -----------------------------
# Scores robustes
# -----------------------------

player_values = [math.log1p(g["playerCount"]) for g in records]
positive_growth_values = [
    math.log1p(max(0, g["growth_per_hour"]))
    for g in records if g["growth_per_hour"] is not None
]
approval_values = [
    g["approval_rate"] for g in records if g["approval_rate"] is not None
]

for game in records:
    popularity_raw = math.log1p(game["playerCount"])
    popularity_score = percentile_rank(popularity_raw, player_values)

    rate = game["growth_per_hour"]
    if rate is None:
        growth_score = 0.0
    else:
        growth_score = percentile_rank(
            math.log1p(max(0, rate)),
            positive_growth_values
        )
        if rate <= 0:
            growth_score = 0.0

    approval = game["approval_rate"]
    approval_score = (
        percentile_rank(approval, approval_values)
        if approval is not None else 50.0
    )

    # Le potentiel favorise les jeux qui progressent, sont appréciés
    # et ont déjà une audience suffisante, sans confondre potentiel et certitude.
    growth_positive = max(0.0, growth_score)
    potential_score = (
        0.50 * growth_positive
        + 0.25 * popularity_score
        + 0.15 * approval_score
        + 0.10 * game["growth_consistency"]
    )

    # Le score de tendance exige une comparaison suffisamment longue.
    interval_valid = (
        game["comparison_hours"] is not None
        and game["comparison_hours"] >= MIN_COMPARISON_HOURS
        and game["player_growth"] is not None
    )

    confirmed = (
        interval_valid
        and game["history_observations"] >= 2
        and game["valid_growth_intervals"] >= 1
        and game["growth_consistency"] >= 50
        and game["player_growth"] > 0
    )

    trend_score = (
        0.45 * popularity_score
        + 0.35 * growth_positive
        + 0.10 * approval_score
        + 0.10 * game["growth_consistency"]
    )

    # Une tendance non confirmée ne peut pas dominer le classement.
    if not confirmed:
        trend_score *= 0.65

    game.update({
        "popularity_score": round(popularity_score, 1),
        "growth_score": round(growth_score, 1),
        "potential_score": round(clamp(potential_score), 1),
        "trend_score": round(clamp(trend_score), 1),
        "trend_confirmed": bool(confirmed),
    })


# -----------------------------
# Classements
# -----------------------------

def sort_players(game):
    return game["playerCount"]


def sort_growth(game):
    value = game.get("growth_per_hour")
    return value if value is not None else float("-inf")


top_games = sorted(records, key=sort_players, reverse=True)[:20]

fastest_growing = sorted(
    [
        g for g in records
        if g["growth_per_hour"] is not None
        and g["comparison_hours"] is not None
        and g["comparison_hours"] >= MIN_COMPARISON_HOURS
        and g["player_growth"] is not None
        and g["player_growth"] > 0
    ],
    key=lambda g: (sort_growth(g), g["player_growth"]),
    reverse=True
)[:20]

high_potential = sorted(
    records,
    key=lambda g: g["potential_score"],
    reverse=True
)[:20]

rising_games = sorted(
    [g for g in records if g["trend_confirmed"]],
    key=lambda g: (g["trend_score"], g["growth_consistency"]),
    reverse=True
)[:20]

declining_games = sorted(
    [
        g for g in records
        if g["player_growth"] is not None
        and g["comparison_hours"] is not None
        and g["comparison_hours"] >= MIN_COMPARISON_HOURS
        and g["player_growth"] < 0
    ],
    key=lambda g: g["player_growth"]
)[:20]

genre_counts = defaultdict(int)
for game in records:
    genre_counts[game["genre"]] += 1

popular_categories = [
    {"genre": genre, "games": count}
    for genre, count in sorted(
        genre_counts.items(),
        key=lambda item: item[1],
        reverse=True
    )
]

analysis = {
    "analyzed_at": now_iso,
    "games_analyzed": len(records),
    "games_comparable": sum(
        1 for g in records if g["player_growth"] is not None
    ),
    "history_snapshots": len(valid_history) + 1,
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
    "note": (
        "Scores heuristiques, pas des prédictions. "
        "La croissance horaire n'est classée que sur des intervalles "
        "d'au moins 30 minutes. Une tendance confirmée nécessite des "
        "relevés historiques distincts et une hausse positive. "
        "Les joueurs peuvent varier selon l'heure, les mises à jour "
        "et les événements. Plusieurs relevés sur plusieurs heures "
        "ou jours sont nécessaires pour confirmer une tendance durable."
    ),
}

write_json(ANALYSIS_FILE, analysis)

# -----------------------------
# Historique
# -----------------------------

snapshot = {
    "timestamp": now_iso,
    "games": [
        {
            "universeId": g.get("universeId"),
            "rootPlaceId": g.get("rootPlaceId"),
            "name": g.get("name"),
            "playerCount": g["playerCount"],
            "genreL1": g.get("genreL1", g.get("genre")),
        }
        for g in records
    ],
}

# Évite d'ajouter deux snapshots avec le même timestamp.
history = [
    item for item in history
    if not isinstance(item, dict)
    or item.get("timestamp") != now_iso
]
history.append(snapshot)
history = history[-MAX_HISTORY_SNAPSHOTS:]
write_json(HISTORY_FILE, history)


# -----------------------------
# Idée de jeu générée
# -----------------------------

best = next(
    (
        g for g in high_potential
        if g["playerCount"] >= MIN_PLAYERS_FOR_GROWTH
    ),
    None
)

if best:
    idea = f"""# Idée de jeu Roblox

## Inspiration détectée
**{best['name']}**

- Genre : {best['genre']}
- Joueurs observés : {best['playerCount']:,}
- Approbation : {best['approval_rate'] if best['approval_rate'] is not None else 'Inconnue'} %
- Score de potentiel heuristique : {best['potential_score']}/100
- Tendance confirmée : {'Oui' if best['trend_confirmed'] else 'Pas encore'}

## Concept original proposé
Créer un jeu du genre **{best['genre']}** avec une identité visuelle propre,
une boucle de jeu facile à comprendre en moins de 30 secondes et une
progression qui récompense les sessions courtes.

## Fonctionnalités à tester
1. Une première récompense dans la première minute.
2. Des objectifs quotidiens simples.
3. Une progression visible et des objets à collectionner.
4. Des événements réguliers qui donnent une raison de revenir.
5. Un tutoriel court et un gameplay adapté au mobile.

## Plan de validation
- Créer un prototype jouable avant d'ajouter beaucoup de contenu.
- Tester avec de vrais joueurs et observer où ils quittent la partie.
- Comparer la rétention et la durée des sessions avant d'investir davantage.

**Attention :** ce concept est une piste à tester, pas une garantie de succès.
"""
else:
    idea = """# Idée de jeu Roblox

Les données sont encore insuffisantes pour choisir une opportunité avec
confiance. Continue les relevés, puis vérifie les jeux qui progressent
sur plusieurs intervalles d'au moins 30 minutes.

En attendant, construis un prototype original avec une boucle de jeu courte,
une progression visible et des commandes faciles à utiliser sur mobile.
"""

with open(IDEA_FILE, "w", encoding="utf-8") as f:
    f.write(idea)

print(f"Analyse terminée : {len(records)} jeux analysés.")
print(f"Jeux comparables : {analysis['games_comparable']}")
print(f"Tendances confirmées : {len(rising_games)}")
print(f"Rapport créé : {ANALYSIS_FILE}")
print(f"Idée générée : {IDEA_FILE}")
