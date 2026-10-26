
import json
from pathlib import Path
from datetime import datetime, timezone

DATA = Path("data")
SOURCE = DATA / "trends.json"


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(
            "data/trends.json introuvable. Lance main.py d'abord."
        )

    report = json.loads(SOURCE.read_text(encoding="utf-8"))
    games = report.get("games", [])

    # Conserver une seule entrée par jeu.
    unique = {}
    for game in games:
        uid = game.get("universeId")
        if uid:
            unique[uid] = game

    games = list(unique.values())

    # Score indicatif : joueurs + appréciation des joueurs.
    for game in games:
        players = game.get("playerCount") or 0
        up = game.get("totalUpVotes") or 0
        down = game.get("totalDownVotes") or 0
        votes = up + down
        approval = up / votes if votes else 0.5

        game["approval_rate"] = round(approval * 100, 1)
        game["trend_score"] = round(
            players * (0.5 + approval), 2
        )

    ranking = sorted(
        games,
        key=lambda g: g["trend_score"],
        reverse=True
    )[:30]

    categories = {}
    for game in games:
        genre = game.get("genreL1") or "Unknown"
        categories[genre] = categories.get(genre, 0) + 1

    result = {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "games_analyzed": len(games),
        "ranking_method": (
            "Joueurs actuels pondérés par le taux de votes positifs. "
            "Ce score n'est pas une mesure de croissance."
        ),
        "popular_categories": sorted(
            [
                {"genre": genre, "games": count}
                for genre, count in categories.items()
            ],
            key=lambda x: x["games"],
            reverse=True
        ),
        "top_games": ranking
    }

    DATA.mkdir(exist_ok=True)
    (DATA / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # Générer une première proposition de jeu original.
    top_genres = result["popular_categories"][:3]
    genre_text = ", ".join(
        item["genre"] for item in top_genres
    ) or "Obby & Platformer"

    idea = f"""# Proposition de jeu Roblox

Générée le : {result['analyzed_at']}

## Concept
Créer un jeu original qui combine des mécaniques simples
de parcours, de progression et de rejouabilité.

## Genres observés
{genre_text}

## Boucle de jeu proposée
1. Le joueur démarre dans une zone sûre.
2. Il relève un défi court et facile à comprendre.
3. Il gagne des pièces ou débloque une amélioration.
4. Il accède à un défi plus difficile.
5. Il peut rejouer pour améliorer son temps ou son score.

## Première version jouable
- Une zone de départ.
- Cinq obstacles.
- Des points de contrôle.
- Un compteur de pièces.
- Une ligne d'arrivée.
- Une interface adaptée aux téléphones.

## Important
Cette proposition est un concept initial, pas encore un jeu
Roblox publié. Les catégories observées ne garantissent
ni la popularité future ni des revenus.
"""

    (DATA / "game_idea.md").write_text(
        idea, encoding="utf-8"
    )

    print(f"✅ {len(games)} jeux analysés")
    print("🏆 Classement : data/analysis.json")
    print("💡 Idée de jeu : data/game_idea.md")


if __name__ == "__main__":
    main()
