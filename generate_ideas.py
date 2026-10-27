import json
import os
import random
from datetime import datetime, timezone

TRENDS_FILE = "data/trends.json"
ANALYSIS_FILE = "data/analysis.json"
OUTPUT_FILE = "data/game_ideas.json"

GAME_TEMPLATES = [
    {
        "category": "Vie réelle",
        "genre": "Simulation",
        "title": "City Life Simulator",
        "description": "Développe ta vie dans une ville, trouve un métier, gagne de l'argent virtuel et construis ta maison.",
        "map": "Ville avec routes, maisons, commerces, parc et bâtiments publics.",
        "mechanics": ["Métiers", "Maisons personnalisables", "Économie virtuelle", "Multijoueur"],
        "difficulty": 2
    },
    {
        "category": "Vie réelle",
        "genre": "Gestion",
        "title": "Restaurant Empire",
        "description": "Commence avec un petit restaurant et transforme-le en établissement réputé.",
        "map": "Restaurant avec cuisine, salle, terrasse et quartier commerçant.",
        "mechanics": ["Préparation des commandes", "Améliorations", "Gestion du personnel fictif", "Progression"],
        "difficulty": 2
    },
    {
        "category": "Vie réelle",
        "genre": "Conduite",
        "title": "Ultimate Driving City",
        "description": "Explore une ville, conduis différents véhicules et participe à des défis routiers.",
        "map": "Ville ouverte avec routes, circuit, garage et zones d'exploration.",
        "mechanics": ["Conduite", "Courses", "Véhicules à débloquer", "Défis"],
        "difficulty": 3
    },
    {
        "category": "Tendance potentielle",
        "genre": "Survie",
        "title": "Seven Nights Survival",
        "description": "Survis à des nuits dangereuses, construis un abri et récupère des ressources avec tes amis.",
        "map": "Forêt originale avec camp, grottes, lac et zones secrètes.",
        "mechanics": ["Collecte de ressources", "Construction", "Cycles jour-nuit", "Coopération"],
        "difficulty": 3
    },
    {
        "category": "Tendance potentielle",
        "genre": "Simulator",
        "title": "Power Evolution",
        "description": "Entraîne ton personnage, améliore ses capacités et débloque des mondes différents.",
        "map": "Zones d'entraînement, arènes et mondes progressifs.",
        "mechanics": ["Progression", "Améliorations", "Collection", "Défis"],
        "difficulty": 2
    },
    {
        "category": "Fantasy originale",
        "genre": "Aventure",
        "title": "Kingdoms of the Sky",
        "description": "Explore des îles flottantes, découvre des trésors et développe tes pouvoirs.",
        "map": "Îles flottantes, cascades, temples et ponts suspendus.",
        "mechanics": ["Exploration", "Quêtes", "Pouvoirs fictifs", "Trésors"],
        "difficulty": 3
    },
    {
        "category": "Science-fiction",
        "genre": "Exploration",
        "title": "Planet Frontier",
        "description": "Explore une planète inconnue, collecte des matériaux et construis une colonie.",
        "map": "Planète originale avec cratères, cristaux, grottes et base spatiale.",
        "mechanics": ["Exploration", "Construction", "Collecte", "Amélioration de la base"],
        "difficulty": 3
    },
    {
        "category": "Inspiré du cinéma",
        "genre": "Horreur",
        "title": "The Forgotten Hotel",
        "description": "Explore un hôtel mystérieux, résous des énigmes et échappe à des dangers fictifs.",
        "map": "Hôtel original avec chambres, couloirs, sous-sol et passages secrets.",
        "mechanics": ["Exploration", "Énigmes", "Objets cachés", "Histoire originale"],
        "difficulty": 3
    },
    {
        "category": "Inspiré du cinéma",
        "genre": "Science-fiction",
        "title": "Galactic Defenders",
        "description": "Protège une colonie spatiale contre des menaces imaginaires et explore de nouveaux secteurs.",
        "map": "Station spatiale, hangar, laboratoire et planète extraterrestre.",
        "mechanics": ["Missions", "Équipement fictif", "Exploration", "Coopération"],
        "difficulty": 3
    },
    {
        "category": "Mystère",
        "genre": "Enquête",
        "title": "Secrets of Raven Manor",
        "description": "Résous des mystères dans un manoir et découvre une histoire créée spécialement pour le jeu.",
        "map": "Manoir, bibliothèque, jardin, cave et passages cachés.",
        "mechanics": ["Énigmes", "Indices", "Exploration", "Progression narrative"],
        "difficulty": 2
    },
    {
        "category": "Multijoueur",
        "genre": "Obby",
        "title": "Impossible Tower",
        "description": "Gravis une tour remplie d'obstacles, de pièges et de raccourcis.",
        "map": "Tour verticale avec plateformes, obstacles et points de contrôle.",
        "mechanics": ["Parcours", "Points de contrôle", "Chronomètre", "Classement"],
        "difficulty": 1
    },
    {
        "category": "Construction",
        "genre": "Tycoon",
        "title": "Dream Island Tycoon",
        "description": "Construis une île touristique, développe tes installations et attire des visiteurs fictifs.",
        "map": "Île avec plage, hôtel, commerces, port et attractions.",
        "mechanics": ["Construction", "Améliorations", "Gestion", "Déblocage de zones"],
        "difficulty": 2
    }
]


def load_json(path):
    if not os.path.exists(path):
        print(f"ℹ️ Fichier absent : {path}")
        return {}

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError) as error:
        print(f"⚠️ Impossible de lire {path} : {error}")
        return {}


def get_trending_genres(analysis, trends):
    genres = []

    if isinstance(analysis, dict):
        leading_genre = analysis.get("leading_genre")
        if isinstance(leading_genre, str) and leading_genre:
            genres.append(leading_genre)

        for item in analysis.get("top_genres", []):
            if isinstance(item, str):
                genres.append(item)
            elif isinstance(item, dict):
                genre = item.get("genre") or item.get("name")
                if isinstance(genre, str):
                    genres.append(genre)

    if isinstance(trends, dict):
        for game in trends.get("games", []):
            if not isinstance(game, dict):
                continue

            genre = game.get("genre")
            if isinstance(genre, str) and genre:
                genres.append(genre)

    unique_genres = []
    for genre in genres:
        if genre.lower() not in [g.lower() for g in unique_genres]:
            unique_genres.append(genre)

    return unique_genres


def calculate_score(game, trending_genres):
    score = 50
    reasons = []

    matching_genres = {
        genre.lower() for genre in trending_genres
    }

    if game["genre"].lower() in matching_genres:
        score += 25
        reasons.append("Genre présent dans les données du bot.")

    elif game["category"].lower() == "tendance potentielle":
        reasons.append("Concept proposé pour être testé, tendance non confirmée.")

    # Favorise les concepts les plus simples à développer en premier.
    score += max(0, 15 - game["difficulty"] * 4)
    reasons.append("La difficulté de développement est prise en compte.")

    score = min(score, 100)

    return score, reasons


def generate_ideas():
    print("🤖 Démarrage du générateur de concepts Roblox...")

    analysis = load_json(ANALYSIS_FILE)
    trends = load_json(TRENDS_FILE)

    trending_genres = get_trending_genres(analysis, trends)

    ideas = []

    for template in GAME_TEMPLATES:
        game = dict(template)
        game["mechanics"] = list(template["mechanics"])

        score, reasons = calculate_score(game, trending_genres)

        game["score"] = score
        game["score_reasons"] = reasons
        game["trend_confirmed"] = (
            game["genre"].lower()
            in {genre.lower() for genre in trending_genres}
        )

        game["generated_at"] = datetime.now(timezone.utc).isoformat()

        ideas.append(game)

    ideas.sort(key=lambda game: game["score"], reverse=True)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ideas_generated": len(ideas),
        "trending_genres_found": trending_genres,
        "warning": (
            "Les scores sont des heuristiques internes, pas des "
            "probabilités de succès. Les concepts ne sont pas encore "
            "des jeux Roblox fonctionnels. Les tendances et les droits "
            "sur les contenus doivent être vérifiés séparément."
        ),
        "ideas": ideas
    }

    os.makedirs("data", exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    print(f"✅ {len(ideas)} idées générées.")

    if trending_genres:
        print("📈 Genres trouvés :", ", ".join(trending_genres))
    else:
        print("ℹ️ Aucun genre exploitable trouvé dans les données.")

    print(f"📁 Fichier créé : {OUTPUT_FILE}")
    print("\n🎮 Les 5 concepts les mieux classés :")

    for index, idea in enumerate(ideas[:5], start=1):
        print(f"{index}. {idea['title']} — score {idea['score']}/100")
        print(f"   Catégorie : {idea['category']}")
        print(f"   Map : {idea['map']}")
        print(f"   Difficulté : {idea['difficulty']}/3")


if __name__ == "__main__":
    generate_ideas()
