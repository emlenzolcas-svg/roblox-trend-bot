
import json
import math
import os
from datetime import datetime, timezone
from collections import Counter, defaultdict

DATA_DIR = "data"
TRENDS_FILE = f"{DATA_DIR}/trends.json"
HISTORY_FILE = f"{DATA_DIR}/history.json"
ANALYSIS_FILE = f"{DATA_DIR}/analysis.json"
IDEA_FILE = f"{DATA_DIR}/game_idea.md"

MAX_HISTORY = 30
MIN_INTERVAL_HOURS = 0.5
MIN_BASE_PLAYERS = 25


# ==================================================
# OUTILS
# ==================================================

def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    os.replace(temp, path)


def num(value, default=0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, OverflowError):
        return None


def game_key(game):
    for field in ("universeId", "rootPlaceId", "placeId", "id"):
        value = game.get(field)
        if value is not None:
            return str(value)
    return str(game.get("name", "")).strip().casefold()


def clean_games(items):
    result = {}
    if not isinstance(items, list):
        return []

    for item in items:
        if not isinstance(item, dict):
            continue
        key = game_key(item)
        if key:
            result[key] = item

    return list(result.values())


def players(game):
    return max(0, num(game.get("playerCount", game.get("playing", 0))))


def approval(game):
    up = num(game.get("totalUpVotes", game.get("upVotes", 0)))
    down = num(game.get("totalDownVotes", game.get("downVotes", 0)))
    total = up + down
    return round(up * 100 / total, 1) if total else None


def rank_score(value, values):
    """Score relatif entre 0 et 100."""
    if not values:
        return 50.0
    return round(
        100 * sum(v <= value for v in values) / len(values), 1
    )


def clamp(value, low=0, high=100):
    return max(low, min(high, value))


# ==================================================
# CHARGEMENT DES DONNÉES
# ==================================================

os.makedirs(DATA_DIR, exist_ok=True)

raw = read_json(TRENDS_FILE, [])
if isinstance(raw, dict):
    raw = raw.get("games", raw.get("data", []))

current_games = clean_games(raw)

if not current_games:
    raise SystemExit(
        "ERREUR : aucun jeu trouvé dans data/trends.json. "
        "Vérifie d'abord l'exécution de main.py."
    )

history = read_json(HISTORY_FILE, [])
if not isinstance(history, list):
    history = []

now = datetime.now(timezone.utc)
now_ts = now.timestamp()
now_iso = now.isoformat()

# Accepte les anciens snapshots utilisant timestamp ou analyzed_at.
valid_history = []

for snapshot in history:
    if not isinstance(snapshot, dict):
        continue

    stamp = parse_date(
        snapshot.get("timestamp", snapshot.get("analyzed_at"))
    )
    snapshot_games = snapshot.get("games", [])

    if stamp is not None and isinstance(snapshot_games, list):
        valid_history.append((stamp, snapshot))

valid_history.sort(key=lambda item: item[0])

# Trouve le snapshot précédent, sans utiliser un relevé futur.
previous_snapshot = None
previous_ts = None

for stamp, snapshot in reversed(valid_history):
    if stamp < now_ts:
        previous_snapshot = snapshot
        previous_ts = stamp
        break

previous_games = {}

if previous_snapshot:
    previous_games = {
        game_key(g): g
        for g in clean_games(previous_snapshot.get("games", []))
    }

elapsed_hours = (
    (now_ts - previous_ts) / 3600
    if previous_ts is not None else None
)

# Historique de chaque jeu, construit à partir des relevés datés.
observations = defaultdict(list)

for stamp, snapshot in valid_history:
    for game in clean_games(snapshot.get("games", [])):
        observations[game_key(game)].append((stamp, game))


# ==================================================
# ANALYSE DES JEUX
# ==================================================

records = []

for game in current_games:
    key = game_key(game)
    count = players(game)
    old_game = previous_games.get(key)

    growth = None
    growth_pct = None
    growth_hour = None

    if old_game is not None and elapsed_hours and elapsed_hours > 0:
        old_count = players(old_game)
        growth = count - old_count
        growth_hour = growth / elapsed_hours

        if old_count >= MIN_BASE_PLAYERS:
            growth_pct = 100 * growth / old_count

    # Construit une série d'observations avec le relevé actuel.
    series = observations.get(key, []) + [(now_ts, game)]
    by_timestamp = {stamp: item for stamp, item in series}
    series = sorted(by_timestamp.items())

    rates = []
    positive_intervals = 0

    for i in range(1, len(series)):
        t0, old = series[i - 1]
        t1, new = series[i]
        hours = (t1 - t0) / 3600

        if hours < MIN_INTERVAL_HOURS:
            continue

        old_count = players(old)
        new_count = players(new)

        if old_count < MIN_BASE_PLAYERS:
            continue

        rates.append((new_count - old_count) / hours)

        if new_count > old_count:
            positive_intervals += 1

    consistency = (
        100 * positive_intervals / len(rates)
        if rates else 0.0
    )

    genre = (
        game.get("genreL1")
        or game.get("genre")
        or game.get("genreL2")
        or "Inconnu"
    )

    distinct_history = len({
        stamp for stamp, _ in observations.get(key, [])
    })

    records.append({
        **game,
        "name": str(game.get("name", "Jeu inconnu")).strip(),
        "game_id": key,
        "playerCount": int(count),
        "genre": genre,
        "approval_rate": approval(game),
        "player_growth": growth,
        "player_growth_pct": (
            round(growth_pct, 2) if growth_pct is not None else None
        ),
        "growth_per_hour": (
            round(growth_hour, 2) if growth_hour is not None else None
        ),
        "comparison_hours": (
            round(elapsed_hours, 2)
            if elapsed_hours is not None else None
        ),
        "history_observations": distinct_history,
        "valid_growth_intervals": len(rates),
        "growth_consistency": round(consistency, 1),
    })


# ==================================================
# SCORES
# ==================================================

pop_values = [math.log1p(g["playerCount"]) for g in records]

growth_values = [
    math.copysign(math.log1p(abs(g["growth_per_hour"])),
                  g["growth_per_hour"])
    for g in records
    if g["growth_per_hour"] is not None
    and g["comparison_hours"] is not None
    and g["comparison_hours"] >= MIN_INTERVAL_HOURS
]

approval_values = [
    g["approval_rate"]
    for g in records
    if g["approval_rate"] is not None
]

for game in records:
    pop = rank_score(math.log1p(game["playerCount"]), pop_values)

    rate = game["growth_per_hour"]
    valid_interval = (
        rate is not None
        and game["comparison_hours"] is not None
        and game["comparison_hours"] >= MIN_INTERVAL_HOURS
    )

    if valid_interval:
        transformed_rate = math.copysign(
            math.log1p(abs(rate)), rate
        )
        growth_score = rank_score(transformed_rate, growth_values)
        if rate <= 0:
            growth_score = 0.0
    else:
        growth_score = 0.0

    approval_value = game["approval_rate"]
    approval_score = (
        rank_score(approval_value, approval_values)
        if approval_value is not None else 50.0
    )

    # Aucun score de croissance n'est accordé sans intervalle valide.
    potential = (
        0.50 * growth_score
        + 0.25 * pop
        + 0.15 * approval_score
        + 0.10 * game["growth_consistency"]
    )

    confirmed = (
        valid_interval
        and game["player_growth"] is not None
        and game["player_growth"] > 0
        and game["history_observations"] >= 1
        and game["valid_growth_intervals"] >= 1
        and game["growth_consistency"] >= 50
    )

    trend = (
        0.45 * pop
        + 0.35 * growth_score
        + 0.10 * approval_score
        + 0.10 * game["growth_consistency"]
    )

    if not confirmed:
        trend *= 0.65

    game.update({
        "popularity_score": round(pop, 1),
        "growth_score": round(growth_score, 1),
        "potential_score": round(clamp(potential), 1),
        "trend_score": round(clamp(trend), 1),
        "trend_confirmed": bool(confirmed),
    })


# ==================================================
# CLASSEMENTS
# ==================================================

top_games = sorted(
    records,
    key=lambda g: g["playerCount"],
    reverse=True
)[:20]

fastest_growing = sorted(
    [
        g for g in records
        if g["player_growth"] is not None
        and g["player_growth"] > 0
        and g["comparison_hours"] is not None
        and g["comparison_hours"] >= MIN_INTERVAL_HOURS
    ],
    key=lambda g: g["growth_per_hour"],
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
        and g["player_growth"] < 0
        and g["comparison_hours"] is not None
        and g["comparison_hours"] >= MIN_INTERVAL_HOURS
    ],
    key=lambda g: g["player_growth"]
)[:20]

category_counts = Counter(g["genre"] for g in records)

popular_categories = [
    {"genre": genre, "games": count}
    for genre, count in category_counts.most_common()
]


# ==================================================
# ENREGISTREMENT DE L'HISTORIQUE
# ==================================================

# Conserve le format déjà utilisé par ton fichier.
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

# Évite les doublons d'horodatage, conserve les autres relevés.
history = [
    item for item in history
    if not isinstance(item, dict)
    or item.get("timestamp", item.get("analyzed_at")) != now_iso
]

history.append(snapshot)
history.sort(
    key=lambda item: parse_date(
        item.get("timestamp", item.get("analyzed_at"))
    ) or 0
)
history = history[-MAX_HISTORY:]
write_json(HISTORY_FILE, history)


# ==================================================
# RAPPORT JSON
# ==================================================

analysis = {
    "analyzed_at": now_iso,
    "games_analyzed": len(records),
    "games_comparable": sum(
        1 for g in records if g["player_growth"] is not None
    ),
    "history_snapshots": len(history),
    "comparison_hours": (
        round(elapsed_hours, 2)
        if elapsed_hours is not None else None
    ),
    "popular_categories": popular_categories,
    "top_games": top_games,
    "fastest_growing_games": fastest_growing,
    "high_potential_games": high_potential,
    "rising_games": rising_games,
    "declining_games": declining_games,
    "note": (
        "Scores heuristiques, pas des prédictions. Les classements "
        "de croissance utilisent uniquement les intervalles d'au moins "
        "30 minutes. Les variations de joueurs dépendent aussi de "
        "l'heure, des mises à jour et des événements. Plusieurs relevés "
        "sur plusieurs heures ou jours sont nécessaires pour évaluer "
        "une tendance durable."
    ),
}

write_json(ANALYSIS_FILE, analysis)


# ==================================================
# IDÉE DE JEU
# ==================================================

best = next(
    (
        g for g in high_potential
        if g["playerCount"] >= MIN_BASE_PLAYERS
    ),
    None
)

if best:
    idea = f"""# Idée de jeu Roblox

## Jeu inspirant
**{best['name']}**

- Genre : {best['genre']}
- Joueurs actuels : {best['playerCount']:,}
- Votes positifs : {best['approval_rate'] if best['approval_rate'] is not None else 'Inconnu'} %
- Score de potentiel : {best['potential_score']}/100
- Tendance confirmée : {'Oui' if best['trend_confirmed'] else 'Pas encore'}

## Concept original à tester

Créer un jeu original du genre **{best['genre']}**, avec une boucle de jeu
facile à comprendre, une progression visible et une première récompense
rapide.

## Fonctionnalités proposées
1. Un tutoriel court et adapté au mobile.
2. Des objectifs simples et des récompenses régulières.
3. Des objets à collectionner et des améliorations déblocables.
4. Des défis renouvelés pour donner envie de revenir.
5. Un prototype jouable à tester avec de vrais joueurs.

## Validation
Mesurer la rétention, la durée des sessions et les retours des joueurs
avant d'investir dans du contenu supplémentaire.

Le score est un indicateur heuristique, pas une garantie de succès.
"""
else:
    idea = """# Idée de jeu Roblox

Continue à collecter les données. Le bot a besoin de plusieurs relevés
espacés pour identifier les tendances de croissance.

En attendant, crée un prototype original avec une boucle de jeu courte,
une progression visible et des commandes adaptées au mobile.
"""

with open(IDEA_FILE, "w", encoding="utf-8") as file:
    file.write(idea)

print("===================================")
print(" ROBLOX TREND BOT : ANALYSE TERMINEE")
print("===================================")
print(f"Jeux analysés : {len(records)}")
print(f"Jeux comparables : {analysis['games_comparable']}")
print(f"Snapshots conservés : {len(history)}")
print(f"Tendances confirmées : {len(rising_games)}")
print(f"Classement croissance : {len(fastest_growing)} jeux")
print(f"Rapport : {ANALYSIS_FILE}")
print(f"Idée : {IDEA_FILE}")
