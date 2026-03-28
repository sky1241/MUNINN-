#!/usr/bin/env python3
"""
WINTER TREE ENGINE v1.0
=======================
Moteur de classification, génération et validation d'arbres de projets.

Basé sur :
- Lindenmayer (1968) — L-Systems
- Prusinkiewicz & Lindenmayer (1990) — Algorithmic Beauty of Plants
- Tomer & Schach (2000) — Evolution Tree
- Fowler (2004) — Strangler Fig Application
- Barnes (2013, CMU) — Software Architecture Evolution

Auteur : Sky — l'architecte de l'architecte
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ============================================================================
# KNOWLEDGE BASE — Les 6 familles et leurs règles
# ============================================================================

FAMILIES = {
    "conifere": {
        "emoji": "🌲",
        "nom": "Conifère",
        "forme": "Pyramide verticale",
        "desc": "Pipeline linéaire avec leader dominant. Le tronc d'abord, les branches subordonnées.",
        "quand": "Pipeline linéaire (signal → analyse → action)",
        "exemples": "Trading algo, ETL, CI/CD pipeline",
        "regles": {
            "TRUNK_FIRST": {
                "desc": "Toujours étendre le tronc (pipeline principal) avant les branches",
                "bio": "Le leader terminal dépasse les latérales grâce au contrôle apical fort",
                "violation": "Développer une feature avant que le pipeline end-to-end fonctionne"
            },
            "BRANCH_SUBORDINATION": {
                "desc": "branch.size < 0.6 × trunk.size",
                "bio": "Les branches restent plus petites que le tronc (contrôle apical)",
                "violation": "Un module secondaire dépasse en complexité le pipeline principal"
            },
            "TOP_DOWN_GROWTH": {
                "desc": "L'énergie/info descend de l'apex",
                "bio": "Flux d'auxine basipétal (apex → base)",
                "violation": "Dépendance circulaire ou bottom-up non planifiée"
            },
            "NO_RECOVERY_ON_OLD_WOOD": {
                "desc": "Si le leader casse, refactoring majeur nécessaire",
                "bio": "La plupart des conifères ne régénèrent pas sur vieux bois",
                "violation": "Ignorer une cassure du pipeline principal"
            },
            "ENVIRONMENTAL_ADAPTATION": {
                "desc": "Forêt dense → plus vertical ; terrain ouvert → plus large",
                "bio": "La compétition façonne la forme même chez les excurrents",
                "violation": "Ignorer les contraintes de l'écosystème (API limits, hardware, etc.)"
            }
        },
        "risques": [
            "Si le tronc (pipeline) casse, tout l'arbre meurt",
            "Pas de redondance naturelle — single point of failure",
            "Les branches ne peuvent pas prendre le relais du leader"
        ],
        "diagnostic_keywords": ["pipeline", "séquentiel", "linéaire", "signal", "étape", "flux", "stream"]
    },

    "feuillu": {
        "emoji": "🍁",
        "nom": "Feuillu",
        "forme": "Canopée large",
        "desc": "Multi-modules en parallèle. Tronc court, branches compétitives.",
        "quand": "Projet multi-modules interdépendants",
        "exemples": "App mobile full-stack, moteur 3D, framework",
        "regles": {
            "TRUNK_THEN_BRANCH": {
                "desc": "Tronc court (architecture de base) puis branches en compétition",
                "bio": "Dominance apicale forte la 1ère année, puis latérales libérées",
                "violation": "Développer des branches sans avoir un tronc stable"
            },
            "LATERAL_COMPETITION": {
                "desc": "Les branches peuvent DÉPASSER le tronc — le module le plus utilisé devient dominant",
                "bio": "Contrôle apical faible — les latérales dépassent le leader",
                "violation": "Forcer un module à rester petit quand l'usage le pousse à grandir"
            },
            "CO_DOMINANCE_RISK": {
                "desc": "Deux branches de même taille = point de rupture structurel",
                "bio": "V-shape avec écorce incluse = défaillance en tempête",
                "violation": "Deux modules rivaux de même taille sans arbitrage"
            },
            "CANOPY_SPREAD": {
                "desc": "L'énergie se distribue en LARGEUR",
                "bio": "Forme décurrente — canopée étalée",
                "violation": "Concentrer tout l'effort sur un seul module au détriment des autres"
            },
            "SEASONAL_CYCLE": {
                "desc": "Build → ship → pause → rebuild",
                "bio": "Alternance croissance/dormance essentielle pour libérer les bourgeons",
                "violation": "Développer sans jamais faire de pause (burnout technique)"
            },
            "ENVIRONMENT_SHAPES_FORM": {
                "desc": "Compétition → vertical (MVP rapide) ; open → spread (features riches)",
                "bio": "Plasticité extrême — même espèce, formes différentes selon l'environnement",
                "violation": "Ignorer le contexte marché/concurrence dans les décisions d'architecture"
            }
        },
        "risques": [
            "Co-dominance : deux modules rivaux créent un point de rupture",
            "Le leader se perd parmi les branches — qui pilote ?",
            "Complexité croissante des inter-dépendances"
        ],
        "diagnostic_keywords": ["modules", "parallel", "composants", "multi", "bricks", "interdépendant", "full-stack"]
    },

    "palmier": {
        "emoji": "🌴",
        "nom": "Palmier",
        "forme": "Colonne + couronne",
        "desc": "Un seul méristème, zéro branche. Pipeline étroit, output riche au sommet.",
        "quand": "Pipeline étroit avec output riche concentré",
        "exemples": "Audio processing, data transformation, traduction",
        "regles": {
            "SINGLE_MERISTEM": {
                "desc": "Tout passe par UN SEUL point de production",
                "bio": "Un seul SAM (Shoot Apical Meristem) par tige",
                "violation": "Créer un deuxième point d'entrée ou de traitement parallèle"
            },
            "DIAMETER_FIRST": {
                "desc": "Fixer l'architecture/scope AVANT de coder",
                "bio": "Establishment growth : diamètre fixé avant la hauteur",
                "violation": "Commencer à coder avant d'avoir fixé le scope et l'API"
            },
            "NO_LATERAL_BRANCHING": {
                "desc": "Zéro module secondaire — tout dans le pipeline",
                "bio": "Pas de branches latérales (extrêmement rare chez les palmiers)",
                "violation": "Ajouter des features hors du pipeline principal"
            },
            "PERMANENT_WOUNDS": {
                "desc": "Bugs et dette technique sont permanents — pas de refactoring du tronc",
                "bio": "Pas de compartimentalisation — blessures permanentes",
                "violation": "Compter sur un refactoring futur du core pour résoudre les problèmes"
            },
            "FLEXIBLE_RESILIENCE": {
                "desc": "Adaptable aux changements externes mais structure interne fixe",
                "bio": "Les palmiers résistent aux tempêtes par flexibilité",
                "violation": "Changer la structure interne au lieu de s'adapter en surface"
            }
        },
        "risques": [
            "Si le méristème (core) meurt, TOUT meurt",
            "Pas de branche de secours — single pipeline",
            "Les blessures au tronc sont permanentes"
        ],
        "diagnostic_keywords": ["audio", "fft", "pipeline", "transform", "conversion", "traduction", "narrow", "processing"]
    },

    "baobab": {
        "emoji": "🌳",
        "nom": "Baobab",
        "forme": "Tronc massif",
        "desc": "Gros moteur, petite interface. Consolider le core avant d'étendre.",
        "quand": "Gros moteur/solveur avec petite interface de sortie",
        "exemples": "Solveur de contraintes, moteur de rendu, compilateur",
        "regles": {
            "TRUNK_IS_STORAGE": {
                "desc": "Le core accumule les ressources — l'interface est petite relative au core",
                "bio": "Tronc massif (10-14m diamètre), canopée petite (5-25m hauteur)",
                "violation": "Interface aussi complexe que le core"
            },
            "CONSOLIDATE_BEFORE_EXPAND": {
                "desc": "Remplir le tronc d'abord, puis faire pousser les branches",
                "bio": "Le bois mou doit être massif pour ne pas s'effondrer",
                "violation": "Ajouter des features avant que le core soit solide"
            },
            "SOFT_WOOD_PARADOX": {
                "desc": "Le code n'a pas besoin d'hyper-optimisation — il a besoin de COUVERTURE",
                "bio": "Densité 0.09-0.17 g/cm³, 69-88% parenchyme, 5% bois solide",
                "violation": "Optimiser prématurément au lieu de couvrir tous les cas"
            },
            "BARK_REGENERATION": {
                "desc": "L'interface peut être endommagée/régénérée ; le core est protégé",
                "bio": "Écorce de 8cm qui régénère même après dommages sévères",
                "violation": "Laisser un bug d'interface corrompre le core"
            },
            "SEASONAL_CYCLE": {
                "desc": "Phase de dev intensive → phase de maintenance minimale",
                "bio": "4 mois de pluie (croissance) → 8 mois secs (survie)",
                "violation": "Développement continu sans phase de stabilisation"
            },
            "EXTREME_LONGEVITY": {
                "desc": "Architecture zéro-dépendance pour survie multi-année",
                "bio": "Longévité 1000+ ans, troncs multi-tiges fusionnés",
                "violation": "Dépendances sur des libs/APIs instables"
            }
        },
        "risques": [
            "Tirer trop de ressources du core trop vite → collapse",
            "Le transport interne est LENT (haute résistance)",
            "Le tronc peut être creux — attention à la dette technique cachée"
        ],
        "diagnostic_keywords": ["moteur", "engine", "solver", "solveur", "constraint", "core", "calcul", "massif"]
    },

    "buisson": {
        "emoji": "🌿",
        "nom": "Buisson",
        "forme": "Multi-tiges",
        "desc": "Pas de tronc dominant. Collection d'outils indépendants.",
        "quand": "Collection d'outils/scripts/templates indépendants",
        "exemples": "Toolkit, dotfiles, collection de prompts, utils",
        "regles": {
            "NO_CENTRAL_TRUNK": {
                "desc": "Pas de module principal — tous les composants sont au même niveau",
                "bio": "Pas de tige dominante — toutes égales depuis la base",
                "violation": "Créer une dépendance centrale dont tout dépend"
            },
            "REDUNDANCY_IS_RESILIENCE": {
                "desc": "Si un outil meurt, les autres continuent — pas de single point of failure",
                "bio": "Si une tige meurt, les autres continuent",
                "violation": "Créer des dépendances entre les outils"
            },
            "HORIZONTAL_EXPANSION": {
                "desc": "Ajouter de nouveaux outils, ne pas approfondir les existants",
                "bio": "Suckering = expansion horizontale par les racines",
                "violation": "Sur-développer un outil au détriment de la collection"
            },
            "REJUVENATION_BY_PRUNING": {
                "desc": "Le refactoring radical est bénéfique, pas destructif",
                "bio": "Taille radicale → regrowth vigoureux en une saison",
                "violation": "Avoir peur de supprimer/réécrire un outil obsolète"
            },
            "LOW_INVESTMENT_PER_STEM": {
                "desc": "Chaque outil petit, simple, jetable",
                "bio": "Investissement faible par tige, remplacement facile",
                "violation": "Un outil qui prend plus de temps que la somme des autres"
            },
            "SUCKERING_CLONAL_SPREAD": {
                "desc": "Les bons patterns se propagent à travers les outils",
                "bio": "Les rejets créent des colonies clonales",
                "violation": "Chaque outil a ses propres conventions, pas de cohérence"
            }
        },
        "risques": [
            "Ne grandit jamais très haut — pas de produit impressionnant unique",
            "Peut devenir un fouillis sans organisation",
            "Manque de direction claire si pas de curation"
        ],
        "diagnostic_keywords": ["toolkit", "outils", "collection", "scripts", "utils", "prompts", "templates", "indépendant"]
    },

    "liane": {
        "emoji": "🌿",
        "nom": "Liane",
        "forme": "Grimpe sur un hôte",
        "desc": "Utilise l'infrastructure existante. Vitesse > structure.",
        "quand": "Plugin, extension, wrapper d'API, migration legacy",
        "exemples": "Chrome extension, Flutter plugin, API wrapper, legacy migration",
        "regles": {
            "HOST_REQUIRED": {
                "desc": "L'hôte (API, framework, système legacy) doit exister d'abord",
                "bio": "Germination dans l'hôte — pas d'existence autonome initiale",
                "violation": "Développer le plugin avant que l'API hôte soit stable"
            },
            "SPEED_OVER_STRUCTURE": {
                "desc": "Pas d'infrastructure propre nécessaire — investir en vitesse de dev",
                "bio": "Tiges pleines de vasculaire (transport) mais pas de bois dur",
                "violation": "Construire une infrastructure lourde pour un simple wrapper"
            },
            "CLIMBING_STRATEGIES": {
                "desc": "Hooks, callbacks, wrappers — multiples points d'accroche",
                "bio": "Vrilles, épines, racines adventives, poils adhésifs, enroulement",
                "violation": "Un seul point d'accroche fragile"
            },
            "STRANGLER_PATTERN": {
                "desc": "Coexister → progressivement remplacer → l'hôte meurt, la liane est autonome",
                "bio": "Figuier étrangleur : coexistence → enveloppement → remplacement",
                "violation": "Big bang rewrite au lieu de migration progressive"
            },
            "CONTAGION_SPREAD": {
                "desc": "Un plugin peut s'étendre à travers plusieurs plateformes",
                "bio": "Une liane peut s'étendre sur 49+ arbres hôtes",
                "violation": "Limiter le plugin à un seul hôte quand il pourrait s'étendre"
            },
            "FRAGILE_WITHOUT_HOST": {
                "desc": "Si l'hôte tombe, la liane tombe — changement d'API = mort",
                "bio": "Si l'arbre hôte tombe, la liane tombe",
                "violation": "Ignorer les risques de dépendance sur l'hôte (API deprecation, etc.)"
            }
        },
        "risques": [
            "Dépendance totale sur l'hôte — breaking changes = mort",
            "Pas d'autonomie avant la phase finale du strangling",
            "L'hôte peut vous couper l'accès à tout moment"
        ],
        "diagnostic_keywords": ["plugin", "extension", "wrapper", "api", "migration", "legacy", "hook", "addon"]
    }
}

# ============================================================================
# ANATOMIE BIOLOGIQUE — Les 10 niveaux de l'arbre
# ============================================================================

ANATOMY = {
    # ── AU-DESSUS DU SOL ──
    "+5": {
        "zone": "Cime",
        "bio": "Terminal buds / apex",
        "bio_detail": "Bourgeons terminaux, méristèmes apicaux — produisent les auxines qui contrôlent TOUTE la croissance",
        "dev": "Tests, CI/CD, release, docs",
        "dev_detail": "Ce qui se 'reproduit' : déploiement = reproduction de l'arbre",
        "lifespan": "Saisonnier",
        "color_logic": "green si tests pass + CI ok, yellow si partiel, red si absent",
        "paradox": None
    },
    "+4": {
        "zone": "Feuilles",
        "bio": "Foliage / leaves",
        "bio_detail": "5% de la masse totale mais produisent 100% de l'énergie via photosynthèse",
        "dev": "UI, endpoints, outputs visibles",
        "dev_detail": "Ce que l'utilisateur voit et touche — petit en code, 100% de la valeur perçue",
        "lifespan": "Saisonnier",
        "color_logic": "green si UI fonctionnelle, yellow si partielle, red si cassée",
        "paradox": "5% mass → 100% energy. UI = small code → all perceived value."
    },
    "+3": {
        "zone": "Rameaux",
        "bio": "Twigs / branchlets",
        "bio_detail": "Subdivisions des branches, <4 ans. Les plus flexibles, se plient au vent, premiers à casser",
        "dev": "Sous-features, sous-modules, composants",
        "dev_detail": "Flexibles, remplaçables, supportent les outputs directs",
        "lifespan": "1-4 ans",
        "color_logic": "green si implémenté, yellow si WIP, red si manquant et bloquant",
        "paradox": None
    },
    "+2": {
        "zone": "Branches",
        "bio": "Scaffold branches / boughs",
        "bio_detail": "Branches principales 4+ ans. DOIVENT être plus petites que le tronc sinon l'attache casse",
        "dev": "Modules majeurs, features principales",
        "dev_detail": "Structural, long-lived. Si une branche dépasse le tronc → co-dominance risk",
        "lifespan": "Décennies",
        "color_logic": "green si stable, yellow si en dev actif, red si conflit co-dominance",
        "paradox": "Branch MUST be smaller than trunk. Module > core = structural failure."
    },
    "+1": {
        "zone": "Tronc",
        "bio": "Trunk / bole",
        "bio_detail": "Duramen (heartwood) = MORT mais supporte 20 tonnes. Transport bidirectionnel eau↑ sucres↓",
        "dev": "Core engine, pipeline principal",
        "dev_detail": "Tout passe par lui — si le tronc casse, l'arbre meurt",
        "lifespan": "Vie de l'arbre",
        "color_logic": "green si core solide, yellow si dette technique, red si cassé",
        "paradox": "Heartwood is DEAD but supports 20 tons. Legacy code = dead but load-bearing."
    },

    # ── LE SOL ──
    "0": {
        "zone": "● SOL ●",
        "bio": "Root collar / trunk flare",
        "bio_detail": "Anneaux de croissance 2x plus larges. 93% des arbres urbains ont un collet enterré → mort lente",
        "dev": "Interface Sky ↔ Claude",
        "dev_detail": "Le point de communication. Doit être VISIBLE sinon le projet meurt lentement",
        "lifespan": "Permanent",
        "color_logic": "green si interface claire, yellow si ambiguë, red si enterrée/cachée",
        "paradox": "93% of urban trees have buried collars → slow death. Hidden interface = slow project death."
    },

    # ── SOUS LE SOL ──
    "-1": {
        "zone": "Racines structurelles",
        "bio": "Structural / lateral roots",
        "bio_detail": "5-15 racines principales, jusqu'à 30cm diamètre. Spread = 2-4x couronne. 80-90% dans top 60cm",
        "dev": "Frameworks, APIs, contraintes techniques évidentes",
        "dev_detail": "Visible quand on creuse un peu. Structurant, changeable avec effort",
        "lifespan": "Décennies",
        "color_logic": "green si documenté, yellow si implicite, red si inconnu",
        "paradox": None
    },
    "-2": {
        "zone": "Racines pivotantes",
        "bio": "Taproot / sinker roots",
        "bio_detail": "Racines verticales ~2cm depuis les latérales. Stockage eau + énergie. Souvent perdues à maturité",
        "dev": "Décisions d'architecture profondes, choix structurants",
        "dev_detail": "Décisions prises tôt qui ancrent le projet — difficiles à changer",
        "lifespan": "Vie de l'arbre",
        "color_logic": "green si explicite, yellow si implicite, red si contradictoire",
        "paradox": "Often lost at maturity. Early architecture decisions get buried but still anchor."
    },
    "-3": {
        "zone": "Radicelles",
        "bio": "Fine / feeder roots",
        "bio_detail": "≤2mm, non-ligneuses, éphémères (turnover = mois). Absorption directe eau + nutriments",
        "dev": "Contraintes business (budget, deadline, marché, users)",
        "dev_detail": "Changent constamment mais nourrissent tout le projet",
        "lifespan": "Mois",
        "color_logic": "green si alimenté, yellow si stress, red si coupé (plus de budget/users)",
        "paradox": "Ephemeral but feed everything. Business constraints change but nourish the project."
    },
    "-4": {
        "zone": "Poils absorbants",
        "bio": "Root hairs",
        "bio_detail": "Extensions microscopiques de l'épiderme. Cuticule très fine. Filtrent TOUT ce qui entre",
        "dev": "Contraintes légales/réglementaires (GDPR, licences, EN 71, normes)",
        "dev_detail": "Invisibles à l'œil nu mais filtrent tout ce qui peut entrer dans le projet",
        "lifespan": "Jours",
        "color_logic": "green si conforme, yellow si pas vérifié, red si violation",
        "paradox": "Microscopic but filter EVERYTHING entering. Laws are invisible but non-negotiable."
    },
    "-5": {
        "zone": "Mycorhizes",
        "bio": "Mycorrhizae",
        "bio_detail": "Champignons symbiotiques. Amplifient absorption x100. 2500+ espèces. SANS ELLES rien ne pousse",
        "dev": "Lois physiques, mathématiques, contraintes hardware immuables",
        "dev_detail": "Invisibles, symbiotiques. Tu ne les vois pas mais elles amplifient tout x100 quand comprises",
        "lifespan": "Permanent",
        "color_logic": "green si respecté, yellow si testé aux limites, red si violé (impossible)",
        "paradox": "Amplify absorption 100x. Physics laws are not limits — they AMPLIFY when understood."
    }
}

# Ratios biologiques réels
BIO_RATIOS = {
    "root_shoot_weight": {
        "value": "0.25-0.38",
        "meaning": "Racines = 20-28% du poids total",
        "source": "Mokany et al. 2006, Global Change Biology"
    },
    "root_surface_vs_leaf": {
        "value": "2.5-4.5x",
        "meaning": "Surface racinaire = 2.5-4.5x surface foliaire",
        "source": "Perry (1989), ISA Arboriculture"
    },
    "root_spread_vs_crown": {
        "value": "2-4x",
        "meaning": "Spread latéral = 2-4x diamètre couronne (jusqu'à 7x)",
        "source": "Colorado State University, Iowa State"
    },
    "roots_in_top_60cm": {
        "value": "80-90%",
        "meaning": "La plupart des racines sont proches de la surface",
        "source": "Biology Insights 2025, ISA Arboriculture"
    },
    "structural_roots_count": {
        "value": "5-15",
        "meaning": "Nombre de racines structurelles par arbre",
        "source": "ISA Arboriculture (Sutton & Tinus 1983)"
    },
    "mycorrhizae_amplification": {
        "value": "100x",
        "meaning": "Les mycorhizes amplifient la surface d'absorption x100",
        "source": "Perry, cité par ISA Arboriculture"
    },
    "leaves_mass_percent": {
        "value": "5%",
        "meaning": "Les feuilles = 5% de la masse mais produisent 100% de l'énergie",
        "source": "richardstreeservice.com"
    },
    "buried_collar_urban": {
        "value": "93%",
        "meaning": "93% des arbres urbains ont un collet enterré → mort lente",
        "source": "Smiley 1991, Bartlett Tree Research"
    }
}

# Root types par famille d'arbre
FAMILY_ROOT_TYPES = {
    "conifere": {
        "root_type": "Taproot + latérales",
        "depth": "1-10m (pin jusqu'à 3.9m documenté)",
        "spread": "2-3x rayon couronne",
        "rs_ratio": "0.25-0.30",
        "detail": "Racine pivotante profonde, latérales modérées. Moins de biomasse racinaire que feuillus."
    },
    "feuillu": {
        "root_type": "Heart (oblique) + latérales massives",
        "depth": "Chêne jusqu'à 9m",
        "spread": "2-4x rayon couronne",
        "rs_ratio": "0.25-0.38",
        "detail": "Plus de biomasse racinaire totale que conifères. Racines en cœur, très plastiques."
    },
    "palmier": {
        "root_type": "Adventives uniformes",
        "depth": "1-2m (peu profondes)",
        "spread": "Dense mais limité",
        "rs_ratio": "N/A (monocot, pas de croissance secondaire)",
        "detail": "PAS de racine pivotante. Toutes adventives, même diamètre. Diamètre tronc ≠ indicateur racines."
    },
    "baobab": {
        "root_type": "Latérales massives, peu profondes",
        "depth": "Peu profond",
        "spread": "Jusqu'à 50m pour arbre de 14m diamètre",
        "rs_ratio": "0.15-0.20 (tronc tellement massif)",
        "detail": "Les racines vont chercher l'eau très loin horizontalement. Transport interne lent."
    },
    "buisson": {
        "root_type": "Réseau large > partie aérienne",
        "depth": "Peu profond (30-60cm)",
        "spread": "2-3x largeur des tiges",
        "rs_ratio": "0.40-0.68",
        "detail": "Racines PLUS LARGES que partie visible. C'est pourquoi un buisson repousse après taille radicale."
    },
    "liane": {
        "root_type": "Minimales → complètes (progression)",
        "depth": "Variable (dépend de l'hôte)",
        "spread": "Le long du tronc hôte puis au sol",
        "rs_ratio": "Progresse de ~0 à normal",
        "detail": "Racines aériennes d'abord, puis terrestres. Le figuier étrangleur développe un système complet seulement au sol."
    }
}


# ============================================================================
# CLASSIFICATEUR — Diagnostic de famille
# ============================================================================

def classify_interactive():
    """Classification interactive par questions."""
    print("\n" + "=" * 60)
    print("  🌲 WINTER TREE — CLASSIFICATEUR DE PROJET")
    print("=" * 60)

    name = input("\nNom du projet : ").strip()
    if not name:
        print("Nom requis.")
        return None

    desc = input("Description courte : ").strip()

    print("\n--- QUESTIONS DE DIAGNOSTIC ---\n")

    # Q1 : Structure
    print("Q1. La structure du projet est principalement :")
    print("  [1] Un pipeline linéaire (A → B → C → résultat)")
    print("  [2] Des modules en parallèle (composant A + B + C)")
    print("  [3] Un gros moteur avec une petite interface")
    print("  [4] Des outils indépendants (pas de lien fort entre eux)")
    print("  [5] Un plugin/extension pour un système existant")
    q1 = input("Réponse (1-5) : ").strip()

    # Q2 : Output
    print("\nQ2. L'output du projet est :")
    print("  [1] Concentré (un seul résultat riche en bout de pipeline)")
    print("  [2] Distribué (plusieurs features/modules accessibles)")
    print("  [3] Minimal (un oui/non, un fichier, une décision)")
    print("  [4] Multiple (chaque outil produit son propre résultat)")
    q2 = input("Réponse (1-4) : ").strip()

    # Q3 : Dépendances
    print("\nQ3. Les parties du projet sont :")
    print("  [1] Séquentielles (chaque étape dépend de la précédente)")
    print("  [2] Interdépendantes (les modules se parlent)")
    print("  [3] Le core est indépendant, l'interface dépend du core")
    print("  [4] Indépendantes (chaque partie fonctionne seule)")
    print("  [5] Dépendantes d'un système externe (API, framework)")
    q3 = input("Réponse (1-5) : ").strip()

    # Scoring
    scores = {f: 0 for f in FAMILIES}

    # Q1 scoring
    q1_map = {"1": ["conifere", "palmier"], "2": ["feuillu"],
              "3": ["baobab"], "4": ["buisson"], "5": ["liane"]}
    for f in q1_map.get(q1, []):
        scores[f] += 3

    # Q2 scoring
    q2_map = {"1": ["palmier", "conifere"], "2": ["feuillu"],
              "3": ["baobab"], "4": ["buisson"]}
    for f in q2_map.get(q2, []):
        scores[f] += 2

    # Q3 scoring
    q3_map = {"1": ["conifere", "palmier"], "2": ["feuillu"],
              "3": ["baobab"], "4": ["buisson"], "5": ["liane"]}
    for f in q3_map.get(q3, []):
        scores[f] += 2

    # Keyword bonus from description
    desc_lower = desc.lower()
    for fam_id, fam in FAMILIES.items():
        for kw in fam["diagnostic_keywords"]:
            if kw.lower() in desc_lower:
                scores[fam_id] += 1

    # Trier par score
    ranked = sorted(scores.items(), key=lambda x: x[-1], reverse=True)
    winner_id = ranked[0][0]
    winner = FAMILIES[winner_id]

    print("\n" + "=" * 60)
    print(f"  DIAGNOSTIC : {winner['emoji']} {winner['nom'].upper()}")
    print("=" * 60)
    print(f"\n  {winner['desc']}")
    print(f"  Quand l'utiliser : {winner['quand']}")
    print(f"\n  Scores : ", end="")
    for fam_id, score in ranked:
        f = FAMILIES[fam_id]
        print(f"{f['emoji']}{score} ", end="")
    print()

    return {"name": name, "desc": desc, "family": winner_id}


def classify_auto(name, desc, structure, output, deps):
    """Classification automatique (pour usage par Claude ou script).

    Args:
        name: nom du projet
        desc: description courte
        structure: 'pipeline' | 'parallel' | 'engine' | 'tools' | 'plugin'
        output: 'concentrated' | 'distributed' | 'minimal' | 'multiple'
        deps: 'sequential' | 'interdependent' | 'core-interface' | 'independent' | 'external'
    """
    scores = {f: 0 for f in FAMILIES}

    struct_map = {
        "pipeline": ["conifere", "palmier"],
        "parallel": ["feuillu"],
        "engine": ["baobab"],
        "tools": ["buisson"],
        "plugin": ["liane"]
    }
    for f in struct_map.get(structure, []):
        scores[f] += 3

    output_map = {
        "concentrated": ["palmier", "conifere"],
        "distributed": ["feuillu"],
        "minimal": ["baobab"],
        "multiple": ["buisson"]
    }
    for f in output_map.get(output, []):
        scores[f] += 2

    deps_map = {
        "sequential": ["conifere", "palmier"],
        "interdependent": ["feuillu"],
        "core-interface": ["baobab"],
        "independent": ["buisson"],
        "external": ["liane"]
    }
    for f in deps_map.get(deps, []):
        scores[f] += 2

    desc_lower = desc.lower()
    for fam_id, fam in FAMILIES.items():
        for kw in fam["diagnostic_keywords"]:
            if kw.lower() in desc_lower:
                scores[fam_id] += 1

    ranked = sorted(scores.items(), key=lambda x: x[-1], reverse=True)
    return {"name": name, "desc": desc, "family": ranked[0][0], "scores": dict(ranked)}


# ============================================================================
# GÉNÉRATEUR DE TEMPLATE
# ============================================================================

def generate_template(project_info):
    """Génère un Winter Tree template v2 pré-rempli."""
    name = project_info["name"]
    family_id = project_info["family"]
    desc = project_info.get("desc", "")
    fam = FAMILIES[family_id]
    now = datetime.now().strftime("%Y-%m-%d")

    # Build growth rules section
    rules_text = ""
    for rule_id, rule in fam["regles"].items():
        rules_text += f"### {rule_id}\n"
        rules_text += f"- **Règle :** {rule['desc']}\n"
        rules_text += f"- **Bio :** {rule['bio']}\n"
        rules_text += f"- **Violation :** {rule['violation']}\n\n"

    # Build risks section
    risks_text = "\n".join(f"- {r}" for r in fam["risques"])

    template = f"""# {fam['emoji']} {name.upper()} — ARBRE HIVER v2

## METADATA
```yaml
project: "{name}"
family: {family_id}
forme: "{fam['forme']}"
desc: "{desc}"
last_updated: "{now}"
```

## (1) TREE_SILHOUETTE

```
          ☆  Cime (tests, CI, packaging, docs)
         /|\\
        / | \\  Branches (modules, features)
       /  |  \\
      /   |   \\
─────/────|────\\───── ← LE SOL = interface Sky ↔ Claude
     \\    |    /
      \\   |   /  Tronc (moteur principal, core)
       \\  |  /
        \\ | /
         \\|/
          ▼  Racines (contraintes fondamentales)
```

> TODO: Personnaliser l'arbre avec les vrais noms de modules.
> Max 9 branches, noms sur les nœuds, max 110 chars de large.

## (2) NODE_REGISTRY

```yaml
# ── RACINES (contraintes fondamentales) ──
- id: R1
  label: "[contrainte #1]"
  level: R
  parent: null
  status: todo
  entry: "fichier.py: fonction() L???"
  depends: []
  desc: "[à remplir]"

# ── TRONC (moteur principal) ──
- id: T1
  label: "[module core]"
  level: T
  parent: R1
  status: todo
  entry: "main.py: __init__() L???"
  depends: [R1]
  desc: "[à remplir]"

# ── BRANCHES (features, modules) ──
- id: B1
  label: "[feature #1]"
  level: B
  parent: T1
  status: todo
  entry: "module.py: func() L???"
  depends: [T1]
  desc: "[à remplir]"

# ── CIME (tests, packaging, docs) ──
- id: C1
  label: "Tests"
  level: C
  parent: T1
  status: todo
  entry: "test_main.py: test_suite() L1"
  depends: [B1]
  desc: "Suite de tests"
```

## (3) GROWTH RULES — Famille : {fam['emoji']} {fam['nom']}

{fam['desc']}

{rules_text}
## (4) RISQUES STRUCTURELS

{risks_text}

## (5) QUICK SUMMARY

```
Ce projet est surtout un ─── {desc if desc else '[à remplir]'}
Sa famille d'arbre est ─── {fam['emoji']} {fam['nom']} ({fam['forme']})
Le tronc est ─────────── [fichier principal + ce qu'il fait]
Les branches dominantes ─ [les 2-3 modules les plus importants]
La contrainte racine la plus forte est ─ [la contrainte #1]
Le risque structurel principal est ─── {fam['risques'][0]}
```

## QUALITY CHECK

```
[ ] Famille identifiée et justifiée
[ ] Arbre BAS→HAUT, un tronc, max 110 chars de large
[ ] NODE_REGISTRY contient TOUS les IDs du dessin
[ ] Chaque nœud a : id, label, level, parent, status, entry, depends, desc
[ ] GROWTH RULES copiées depuis {family_id}
[ ] QUICK SUMMARY rempli
```

## RAPPEL

- **Sky monte** : il regarde status → voit le progrès
- **Claude descend** : il regarde entry → plonge dans le code
- **depends** : les deux savent ce qui bloque quoi
- **Les racines sont toujours plus grandes que l'arbre**
"""
    return template


# ============================================================================
# VALIDATEUR DE CROISSANCE
# ============================================================================

def validate_growth(project_info, nodes):
    """Valide la croissance d'un projet selon les règles de sa famille.

    Args:
        project_info: dict avec au minimum 'family'
        nodes: liste de dicts avec au minimum 'id', 'level', 'status', 'depends'

    Returns:
        Liste de warnings/violations
    """
    family_id = project_info["family"]
    fam = FAMILIES[family_id]
    warnings = []

    # Compter les nœuds par niveau
    levels = {"R": [], "T": [], "B": [], "C": []}
    for node in nodes:
        level = node.get("level", "?")
        if level in levels:
            levels[level].append(node)

    done_count = sum(1 for n in nodes if n.get("status") == "done")
    total_count = len(nodes)
    wip_count = sum(1 for n in nodes if n.get("status") == "wip")

    # --- Règles universelles ---
    if not levels["R"]:
        warnings.append("⚠️  CRITIQUE : Aucune racine (contrainte) définie. Les racines sont TOUJOURS plus grandes que l'arbre.")

    if not levels["T"]:
        warnings.append("⚠️  CRITIQUE : Aucun tronc (core) défini.")

    if len(levels["B"]) > 9:
        warnings.append(f"⚠️  Trop de branches ({len(levels['B'])}). Max recommandé : 9.")

    # Vérifier les dépendances
    all_ids = {n["id"] for n in nodes}
    for node in nodes:
        for dep in node.get("depends", []):
            if dep not in all_ids:
                warnings.append(f"⚠️  Nœud {node['id']} dépend de {dep} qui n'existe pas.")

    # Vérifier status cohérence : un nœud 'done' dont les dépendances ne sont pas 'done'
    status_map = {n["id"]: n.get("status", "todo") for n in nodes}
    for node in nodes:
        if node.get("status") == "done":
            for dep in node.get("depends", []):
                if status_map.get(dep) != "done":
                    warnings.append(f"⚠️  {node['id']} est 'done' mais sa dépendance {dep} est '{status_map.get(dep, '?')}'.")

    # --- Règles spécifiques par famille ---

    if family_id == "conifere":
        # TRUNK_FIRST : les branches ne devraient pas être 'done' si le tronc n'est pas 'done'
        trunk_done = all(n.get("status") == "done" for n in levels["T"])
        branch_done = any(n.get("status") == "done" for n in levels["B"])
        if branch_done and not trunk_done:
            warnings.append("🌲 VIOLATION TRUNK_FIRST : Des branches sont terminées mais le tronc n'est pas fini.")

        # BRANCH_SUBORDINATION : alerter si plus de branches que de tronc
        if len(levels["B"]) > 2 * len(levels["T"]) and len(levels["T"]) > 0:
            warnings.append("🌲 ATTENTION BRANCH_SUBORDINATION : Beaucoup de branches pour peu de tronc.")

    elif family_id == "feuillu":
        # CO_DOMINANCE_RISK : deux branches WIP de même profondeur
        wip_branches = [n for n in levels["B"] if n.get("status") == "wip"]
        if len(wip_branches) >= 2:
            warnings.append("🍁 ATTENTION CO_DOMINANCE_RISK : Plusieurs branches en développement simultané. Risque de conflit.")

        # SEASONAL_CYCLE : alerter si tout est WIP et rien n'est done
        if wip_count > 3 and done_count == 0:
            warnings.append("🍁 ATTENTION SEASONAL_CYCLE : Beaucoup de WIP, rien de terminé. Penser à shipper.")

    elif family_id == "palmier":
        # SINGLE_MERISTEM : il ne devrait y avoir qu'UN seul tronc
        if len(levels["T"]) > 1:
            warnings.append("🌴 VIOLATION SINGLE_MERISTEM : Plusieurs troncs détectés. Le palmier n'a qu'un seul méristème.")

        # NO_LATERAL_BRANCHING : alerter si des branches existent
        if len(levels["B"]) > 2:
            warnings.append("🌴 ATTENTION NO_LATERAL_BRANCHING : Trop de branches pour un palmier. Le pipeline devrait être linéaire.")

    elif family_id == "baobab":
        # CONSOLIDATE_BEFORE_EXPAND : branches avant que le tronc soit solide
        trunk_done = all(n.get("status") == "done" for n in levels["T"])
        branch_wip = any(n.get("status") in ("wip", "done") for n in levels["B"])
        if branch_wip and not trunk_done:
            warnings.append("🌳 VIOLATION CONSOLIDATE_BEFORE_EXPAND : Branches en cours mais le core n'est pas consolidé.")

        # TRUNK_IS_STORAGE : le tronc devrait être plus gros que les branches
        if len(levels["B"]) > len(levels["T"]) * 3:
            warnings.append("🌳 ATTENTION TRUNK_IS_STORAGE : L'interface (branches) semble plus grande que le core (tronc).")

    elif family_id == "buisson":
        # NO_CENTRAL_TRUNK : il ne devrait PAS y avoir de tronc dominant
        if len(levels["T"]) > 1:
            pass  # normal pour un buisson
        if len(levels["T"]) == 1 and len(levels["B"]) < 3:
            warnings.append("🌿 ATTENTION NO_CENTRAL_TRUNK : Un buisson devrait avoir plusieurs tiges indépendantes, pas un tronc dominant.")

        # LOW_INVESTMENT_PER_STEM : alerter si une branche a trop de dépendances
        for node in levels["B"]:
            deps = node.get("depends", [])
            if len(deps) > 3:
                warnings.append(f"🌿 ATTENTION LOW_INVESTMENT_PER_STEM : {node['id']} a {len(deps)} dépendances. Garder chaque outil simple.")

    elif family_id == "liane":
        # HOST_REQUIRED : vérifier qu'il y a une racine de type "hôte"
        has_host = any("host" in n.get("label", "").lower() or "api" in n.get("label", "").lower()
                      or "hôte" in n.get("label", "").lower() for n in levels["R"])
        if not has_host:
            warnings.append("🌿 ATTENTION HOST_REQUIRED : Aucune racine de type 'hôte' ou 'API' détectée. La liane a besoin d'un hôte.")

    # --- Résumé ---
    if not warnings:
        warnings.append(f"✅ Aucune violation détectée pour {fam['emoji']} {fam['nom']}. L'arbre pousse sainement.")

    return warnings


# ============================================================================
# EXPORT — JSON pour interop
# ============================================================================

def display_anatomy(family_id=None):
    """Affiche l'anatomie biologique des 10 niveaux avec couleurs."""
    print("\n" + "=" * 80)
    print("  🌳 ANATOMIE BIOLOGIQUE — LES 10 NIVEAUX DE L'ARBRE")
    print("=" * 80)

    levels_order = ["+5", "+4", "+3", "+2", "+1", "0", "-1", "-2", "-3", "-4", "-5"]

    for lvl in levels_order:
        a = ANATOMY[lvl]
        if lvl == "0":
            print("─" * 80)
            print(f"  {'●':>4} {a['zone']:.<28s} {a['bio']:<28s} {a['dev']}")
            print("─" * 80)
        else:
            marker = "▲" if int(lvl) > 0 else "▼"
            print(f"  {lvl:>4} {marker} {a['zone']:.<26s} {a['bio']:<28s} {a['dev']}")

    if family_id and family_id in FAMILY_ROOT_TYPES:
        frt = FAMILY_ROOT_TYPES[family_id]
        fam = FAMILIES[family_id]
        print(f"\n  Famille : {fam['emoji']} {fam['nom']}")
        print(f"  Type racines : {frt['root_type']}")
        print(f"  Profondeur : {frt['depth']}")
        print(f"  Spread : {frt['spread']}")
        print(f"  Ratio R:S : {frt['rs_ratio']}")

    print(f"\n  📊 RATIOS BIOLOGIQUES")
    print(f"  Surface racinaire = {BIO_RATIOS['root_surface_vs_leaf']['value']} surface foliaire")
    print(f"  Spread racines = {BIO_RATIOS['root_spread_vs_crown']['value']} diamètre couronne")
    print(f"  {BIO_RATIOS['roots_in_top_60cm']['value']} des racines dans les premiers 60cm")
    print(f"  Mycorhizes amplifient absorption {BIO_RATIOS['mycorrhizae_amplification']['value']}")


def detect_gaps(nodes, family_id):
    """Détecte les trous dans l'arbre — niveaux manquants, racines absentes.

    Returns list of gap descriptions with severity (red/yellow/green).
    """
    gaps = []
    fam = FAMILIES.get(family_id, {})

    # Mapper les nœuds aux niveaux biologiques
    level_map = {
        "C": "+5",   # Cime = tests/CI
        "F": "+4",   # Feuilles = UI/outputs
        "b": "+3",   # Rameaux = sous-features
        "B": "+2",   # Branches = modules
        "T": "+1",   # Tronc = core
        "R": "-1",   # Racines structurelles par défaut
    }

    # Compter les nœuds par niveau projet
    node_levels = {"C": [], "F": [], "b": [], "B": [], "T": [], "R": []}
    for node in nodes:
        level = node.get("level", "?")
        if level in node_levels:
            node_levels[level].append(node)

    # Compter les racines par profondeur (utiliser le label ou un champ 'depth')
    root_depths = {"-1": 0, "-2": 0, "-3": 0, "-4": 0, "-5": 0}
    for node in nodes:
        if node.get("level") == "R":
            depth = node.get("depth", "-1")
            if depth in root_depths:
                root_depths[depth] += 1
            else:
                root_depths["-1"] += 1  # default

    # ── GAPS AU-DESSUS DU SOL ──

    # +5 Cime : tests/CI manquants
    if not node_levels["C"]:
        gaps.append({
            "level": "+5",
            "zone": "Cime",
            "severity": "red",
            "msg": "AUCUN test/CI/release défini. L'arbre ne peut pas se reproduire (déployer).",
            "action": "Ajouter des nœuds de niveau C (tests, CI pipeline, docs)"
        })

    # +4 Feuilles : pas de nœud UI/output
    if not node_levels["F"]:
        # Pas critique pour tous les projets (moteur sans UI)
        if family_id not in ("baobab",):
            gaps.append({
                "level": "+4",
                "zone": "Feuilles",
                "severity": "yellow",
                "msg": "Aucun output/UI défini. L'arbre ne fait pas de photosynthèse (pas de valeur visible).",
                "action": "Définir les outputs visibles du projet (UI, API endpoints, fichiers générés)"
            })

    # +2 Branches : vérifier le nombre
    if len(node_levels["B"]) > 9:
        gaps.append({
            "level": "+2",
            "zone": "Branches",
            "severity": "yellow",
            "msg": f"{len(node_levels['B'])} branches. Trop dense — difficulté de maintenance.",
            "action": "Regrouper les modules ou créer des sous-niveaux (+3 rameaux)"
        })

    # +1 Tronc : manquant
    if not node_levels["T"] and family_id != "buisson":
        gaps.append({
            "level": "+1",
            "zone": "Tronc",
            "severity": "red",
            "msg": "AUCUN core/tronc défini. L'arbre n'a pas de structure porteuse.",
            "action": "Définir le module central (main.py, core engine, pipeline)"
        })

    # ── LE SOL ──
    # Vérifier si l'interface est documentée
    has_interface = any(
        "interface" in n.get("label", "").lower() or
        "sol" in n.get("label", "").lower() or
        "api" in n.get("label", "").lower()
        for n in nodes
    )
    if not has_interface:
        gaps.append({
            "level": "0",
            "zone": "SOL",
            "severity": "yellow",
            "msg": "Interface (collet racinaire) pas explicitement définie. 93% des projets meurent d'interfaces enterrées.",
            "action": "Documenter explicitement le point d'interaction Sky ↔ Claude"
        })

    # ── GAPS SOUS LE SOL ──

    if not node_levels["R"]:
        gaps.append({
            "level": "-1",
            "zone": "Racines structurelles",
            "severity": "red",
            "msg": "AUCUNE racine/contrainte définie. L'arbre n'est pas ancré.",
            "action": "Identifier les contraintes fondamentales (frameworks, APIs, limites techniques)"
        })
    else:
        # Vérifier la couverture des 5 niveaux de racines
        root_labels = " ".join(n.get("label", "").lower() for n in node_levels["R"])

        # -3 Business
        biz_keywords = ["budget", "deadline", "marché", "market", "user", "client", "revenue", "cost"]
        has_business = any(kw in root_labels for kw in biz_keywords)
        if not has_business:
            gaps.append({
                "level": "-3",
                "zone": "Radicelles",
                "severity": "yellow",
                "msg": "Aucune contrainte business identifiée (budget, deadline, marché, users).",
                "action": "Définir les contraintes business qui alimentent le projet"
            })

        # -4 Legal
        legal_keywords = ["gdpr", "licence", "license", "legal", "norme", "standard", "en 71",
                         "rgpd", "copyright", "compliance", "regulation"]
        has_legal = any(kw in root_labels for kw in legal_keywords)
        if not has_legal:
            gaps.append({
                "level": "-4",
                "zone": "Poils absorbants",
                "severity": "yellow",
                "msg": "Aucune contrainte légale/réglementaire identifiée.",
                "action": "Vérifier GDPR, licences, normes applicables au projet"
            })

        # -5 Physics
        phys_keywords = ["physique", "physics", "hardware", "math", "limite", "fdm", "pla",
                        "bandwidth", "latency", "memory", "cpu", "gpu"]
        has_physics = any(kw in root_labels for kw in phys_keywords)
        if not has_physics and family_id in ("baobab", "conifere", "palmier"):
            gaps.append({
                "level": "-5",
                "zone": "Mycorhizes",
                "severity": "yellow",
                "msg": "Aucune contrainte physique/hardware identifiée pour un projet technique.",
                "action": "Identifier les limites physiques (mémoire, CPU, tolérance FDM, etc.)"
            })

    return gaps


def print_gap_report(gaps):
    """Affiche le rapport de gaps avec couleurs."""
    if not gaps:
        print("  ✅ Aucun trou détecté. L'arbre est complet.")
        return

    severity_icons = {"red": "🔴", "yellow": "🟡", "green": "🟢"}

    print(f"\n{'=' * 70}")
    print(f"  🔍 RAPPORT DE GAPS — {len(gaps)} trou(s) détecté(s)")
    print(f"{'=' * 70}")

    reds = [g for g in gaps if g["severity"] == "red"]
    yellows = [g for g in gaps if g["severity"] == "yellow"]

    if reds:
        print(f"\n  🔴 CRITIQUES ({len(reds)})")
        for g in reds:
            print(f"    [{g['level']:>3}] {g['zone']}: {g['msg']}")
            print(f"         → {g['action']}")

    if yellows:
        print(f"\n  🟡 ATTENTION ({len(yellows)})")
        for g in yellows:
            print(f"    [{g['level']:>3}] {g['zone']}: {g['msg']}")
            print(f"         → {g['action']}")

    # Résumé visuel
    print(f"\n  COUVERTURE :")
    levels_order = ["+5", "+4", "+3", "+2", "+1", "0", "-1", "-2", "-3", "-4", "-5"]
    gap_levels = {g["level"] for g in gaps}
    for lvl in levels_order:
        a = ANATOMY[lvl]
        if lvl in gap_levels:
            sev = next(g["severity"] for g in gaps if g["level"] == lvl)
            icon = severity_icons[sev]
        else:
            icon = "🟢"
        print(f"    {icon} [{lvl:>3}] {a['zone']}")


# ============================================================================
# DOMAINES — Patterns de nœuds typiques par type de projet
# ============================================================================

DOMAIN_PATTERNS = {
    "audio": {
        "keywords": ["audio", "son", "music", "shazam", "piano", "micro", "fréquence",
                     "note", "accord", "pitch", "frequency", "recording", "wav", "mp3"],
        "typical_nodes": {
            "-5": ["FFT (transformée de Fourier rapide)", "Fréquences harmoniques & physique du son",
                   "Latence audio hardware (~10ms incompressible)"],
            "-4": ["Permission microphone (iOS/Android)", "Licences audio (si samples)",
                   "Privacy policy (enregistrement audio)"],
            "-3": ["Public cible (musiciens débutants/pro)", "App Store / Play Store rules",
                   "Modèle gratuit/premium"],
            "-2": ["Architecture audio pipeline (capture→FFT→matching→display)",
                   "Choix : traitement on-device vs cloud"],
            "-1": ["Framework mobile (Flutter/React Native/Swift)",
                   "Lib audio (AudioKit, TarsosDSP, flutter_audio)",
                   "Lib FFT (fftea, dart:typed_data)"],
            "+1": ["Pipeline : capture micro → buffer → FFT → détection fréquence → matching note → affichage"],
            "+2": ["Module capture micro", "Module analyse FFT",
                   "Module matching note/accord", "Module affichage résultat"],
            "+3": ["Bouton record/stop", "Visualisation fréquences", "Historique des détections",
                   "Réglages sensibilité", "Accordeur (tuner mode)"],
            "+4": ["Écran principal (note détectée)", "Écran historique",
                   "Écran settings", "Feedback visuel temps réel"],
            "+5": ["Tests unitaires matching", "Test micro simulé",
                   "CI/CD build APK/IPA", "Publication store"],
        }
    },
    "trading": {
        "keywords": ["trading", "algo", "bourse", "stock", "forex", "crypto", "signal",
                     "backtest", "portfolio", "hedge", "quant", "market", "price"],
        "typical_nodes": {
            "-5": ["Probabilités & statistiques", "Séries temporelles (ARIMA, GARCH)",
                   "Latence réseau/exécution"],
            "-4": ["Régulation financière (MiFID II, SEC)", "Licences broker API",
                   "Règles anti-manipulation"],
            "-3": ["Capital disponible", "Frais (commissions, spread, slippage)",
                   "Fréquence de trading", "Drawdown max acceptable"],
            "-2": ["Architecture : monolith vs microservices",
                   "Choix : event-driven vs polling", "Base de données marché (tick vs OHLCV)"],
            "-1": ["Python + pandas + numpy", "API broker (IBKR, Alpaca, Binance)",
                   "Base de données (PostgreSQL, InfluxDB)"],
            "+1": ["Pipeline : data feed → signal generation → risk check → execution → logging"],
            "+2": ["Module data ingestion", "Module signal/stratégie",
                   "Module risk management", "Module execution", "Module reporting"],
            "+3": ["Indicateurs techniques", "Stop-loss/take-profit logic",
                   "Position sizing", "Slippage model", "P&L tracking"],
            "+4": ["Dashboard P&L", "Alertes temps réel",
                   "Visualisation positions", "Log des trades"],
            "+5": ["Backtests automatisés", "Paper trading mode",
                   "CI tests sur données historiques", "Monitoring production"],
        }
    },
    "mobile_app": {
        "keywords": ["app", "mobile", "ios", "android", "flutter", "react native",
                     "téléphone", "smartphone", "application"],
        "typical_nodes": {
            "-5": ["Limites mémoire mobile (~2GB)", "Batterie / consommation CPU",
                   "Taille écran / densité pixels"],
            "-4": ["Privacy (GDPR, CCPA)", "Permissions (caméra, localisation, contacts)",
                   "App Store Review Guidelines", "Google Play policies"],
            "-3": ["Public cible", "Modèle de monétisation",
                   "Stores (iOS + Android ?)", "Budget / timeline"],
            "-2": ["Natif vs cross-platform", "State management (BLoC, Provider, Redux)",
                   "Architecture (MVVM, Clean Architecture)", "Backend : Firebase vs custom"],
            "-1": ["Framework (Flutter, React Native, SwiftUI)",
                   "Backend/BaaS (Firebase, Supabase)", "CI/CD (Fastlane, Codemagic)"],
            "+1": ["Navigation principale + routing", "Auth flow", "Data layer"],
            "+2": ["Auth/profil", "Feature principale",
                   "Settings", "Notifications"],
            "+3": ["Écrans par feature", "Composants UI réutilisables",
                   "Offline mode", "Deep linking"],
            "+4": ["Écran d'accueil", "Écran principal",
                   "Profil utilisateur", "Onboarding"],
            "+5": ["Tests widget + intégration", "CI builds",
                   "Beta testing (TestFlight/Firebase)", "Publication stores"],
        }
    },
    "web_app": {
        "keywords": ["web", "site", "dashboard", "saas", "webapp", "frontend",
                     "backend", "api", "rest", "graphql"],
        "typical_nodes": {
            "-5": ["HTTP/TCP latence", "Limites navigateur (CORS, storage)",
                   "Bande passante"],
            "-4": ["GDPR / cookies", "HTTPS obligatoire", "Accessibilité WCAG",
                   "Licences open source"],
            "-3": ["Hosting budget", "Nombre d'utilisateurs attendus",
                   "SLA requis", "SEO nécessaire ?"],
            "-2": ["SSR vs SPA vs SSG", "Monolith vs API+frontend",
                   "Base de données (SQL vs NoSQL)", "Auth strategy (JWT, OAuth, session)"],
            "-1": ["Frontend (React, Vue, Svelte)", "Backend (Node, Python, Go)",
                   "DB (PostgreSQL, MongoDB)", "Hosting (Vercel, AWS, Railway)"],
            "+1": ["API routes + auth middleware + DB connection"],
            "+2": ["Auth système", "CRUD principal",
                   "Admin panel", "API externe"],
            "+3": ["Pages/vues", "Composants forms",
                   "Recherche/filtres", "Notifications"],
            "+4": ["Landing page", "Dashboard utilisateur",
                   "Pages de contenu", "Responsive mobile"],
            "+5": ["Tests E2E (Playwright)", "CI/CD",
                   "Monitoring (Sentry)", "Déploiement auto"],
        }
    },
    "hardware_3d": {
        "keywords": ["3d", "printer", "stl", "cad", "fdm", "cnc", "robot",
                     "mécanique", "mechanical", "automate", "automata", "impression"],
        "typical_nodes": {
            "-5": ["Tolérances mécaniques (FDM ~0.2mm)", "Propriétés matériau (PLA, ABS)",
                   "Géométrie manifold / topologie STL", "Gravité, friction, jeu mécanique"],
            "-4": ["Normes sécurité (EN 71 jouets, CE)", "Propriété intellectuelle designs",
                   "Restrictions d'export"],
            "-3": ["Coût matériau par pièce", "Temps d'impression",
                   "Public cible (makers, enfants, industrie)"],
            "-2": ["Parametric vs direct modeling", "Format de sortie (STL, STEP, 3MF)",
                   "Architecture contraintes (CSP, optimisation)"],
            "-1": ["Python + NumPy/SciPy", "Lib 3D (trimesh, OpenSCAD, CadQuery)",
                   "Slicer integration (Cura, PrusaSlicer)"],
            "+1": ["Pipeline : paramètres → géométrie → contraintes → validation → export STL"],
            "+2": ["Générateur de géométrie", "Moteur de contraintes/collision",
                   "Validateur printabilité", "Exporteur STL", "Base de données formes"],
            "+3": ["Templates par type", "Profils matériau",
                   "Visualisation 3D", "Paramètres utilisateur"],
            "+4": ["CLI ou GUI", "Preview 3D",
                   "Rapport de validation", "Fichier STL final"],
            "+5": ["Self-tests géométrie", "Validation manifold automatique",
                   "Test print réel", "CI sur bibliothèque de formes"],
        }
    },
    "tool_cli": {
        "keywords": ["outil", "tool", "cli", "script", "automatisation", "batch",
                     "utility", "toolkit", "helper"],
        "typical_nodes": {
            "-5": ["Limites OS (filesystem, mémoire)", "Encodage (UTF-8, line endings)"],
            "-4": ["Licences dépendances", "Permissions filesystem"],
            "-3": ["Utilisateurs cibles (devs, ops, tous)",
                   "Distribution (pip, npm, binaire)"],
            "-2": ["Architecture : monolith script vs modules",
                   "Config : args vs fichier vs env vars"],
            "-1": ["Langage (Python, Bash, Go, Rust)",
                   "Libs (click, argparse, inquirer)"],
            "+1": ["CLI entry point + arg parsing + dispatch"],
            "+2": ["Commande 1", "Commande 2", "Commande 3"],
            "+3": ["Options/flags par commande", "Output formatters",
                   "Error handling"],
            "+4": ["Help text", "Output console / fichier",
                   "Progress bars", "Couleurs terminal"],
            "+5": ["Tests par commande", "CI", "Publication package"],
        }
    },
}


def detect_domain(desc):
    """Détecte le domaine d'un projet à partir de sa description."""
    desc_lower = desc.lower()
    scores = {}
    for domain, data in DOMAIN_PATTERNS.items():
        score = sum(1 for kw in data["keywords"] if kw in desc_lower)
        if score > 0:
            scores[domain] = score
    if scores:
        return max(scores, key=scores.get)
    return "tool_cli"  # default


def plant(idea, lang=None, platform=None):
    """🌱 PLANTER UN ARBRE — Génère un arbre complet à partir d'une idée.

    C'est LA fonction centrale. Le vibe codeur dit son idée,
    et l'arbre lui montre tout ce qu'il faut, dans le bon ordre.

    Args:
        idea: description en langage naturel ("je veux un Shazam pour piano")
        lang: langage préféré (optionnel, auto-détecté sinon)
        platform: plateforme cible (optionnel)

    Returns:
        dict avec l'arbre complet, la famille, et l'ordre de construction
    """
    # 1. Détecter le domaine
    domain = detect_domain(idea)
    pattern = DOMAIN_PATTERNS[domain]

    # 2. Classifier la famille automatiquement
    # Heuristiques par domaine
    domain_family_hints = {
        "audio": "palmier",       # un seul pipeline critique
        "trading": "conifere",    # pipeline linéaire signal→exec
        "mobile_app": "feuillu",  # multi-modules
        "web_app": "feuillu",     # multi-modules
        "hardware_3d": "baobab",  # gros moteur
        "tool_cli": "buisson",    # collection de commandes
    }
    family_id = domain_family_hints.get(domain, "feuillu")

    # Affiner avec des signaux dans la description
    idea_lower = idea.lower()
    if any(kw in idea_lower for kw in ["collection", "toolkit", "utils", "outils"]):
        family_id = "buisson"
    if any(kw in idea_lower for kw in ["plugin", "extension", "wrapper", "addon"]):
        family_id = "liane"
    if any(kw in idea_lower for kw in ["pipeline", "etl", "flux", "stream"]):
        family_id = "conifere"
    if any(kw in idea_lower for kw in ["moteur", "engine", "solver", "generator"]):
        family_id = "baobab"

    family = FAMILIES[family_id]

    # 3. Générer les nœuds à partir du pattern domaine
    nodes = []
    node_counter = {"M": 0, "P": 0, "D": 0, "A": 0, "R": 0, "S": 0,
                    "T": 0, "B": 0, "b": 0, "F": 0, "C": 0}

    level_mapping = {
        "-5": ("M", "R", -5),   # Mycorhizes
        "-4": ("P", "R", -4),   # Poils
        "-3": ("D", "R", -3),   # radicelles (business/Demand)
        "-2": ("A", "R", -2),   # Architecture pivotante
        "-1": ("R", "R", -1),   # Racines structurelles
        "+1": ("T", "T", None), # Tronc
        "+2": ("B", "B", None), # Branches
        "+3": ("b", "b", None), # rameaux
        "+4": ("F", "F", None), # Feuilles
        "+5": ("C", "C", None), # Cime
    }

    for level_key, typical_items in pattern["typical_nodes"].items():
        prefix, node_level, depth = level_mapping.get(level_key, ("?", "?", None))

        for item in typical_items:
            node_counter[prefix] = node_counter.get(prefix, 0) + 1
            node_id = f"{prefix}{node_counter[prefix]}"

            node = {
                "id": node_id,
                "level": node_level,
                "label": item,
                "status": "todo",
                "entry": "~",
                "depends": [],
                "desc": "",
                "confidence": 0,  # 0-100% — taux de complétion de la connaissance
                                  # 0-30  = 🔴 flou → deep research obligatoire
                                  # 31-70 = 🟡 surface → deep research recommandée
                                  # 71-100 = 🟢 solide → prêt à coder
            }
            if depth is not None:
                node["depth"] = depth

            nodes.append(node)

    # Override language if specified
    if lang:
        for n in nodes:
            if n.get("depth") == -1 and "framework" in n["label"].lower():
                n["label"] = f"{lang} — {n['label']}"

    # 4. Générer l'ordre de construction
    build_order = generate_build_order(family_id, nodes)

    # 5. Assembler le résultat
    result = {
        "idea": idea,
        "domain": domain,
        "family": family_id,
        "family_name": family["nom"],
        "family_emoji": family["emoji"],
        "date": datetime.now().isoformat(),
        "phase": "GRAINE",
        "scale": calculate_scale(0),  # nouveau projet = 0 lignes, grandira avec le dev
        "nodes": nodes,
        "build_order": build_order,
        "next_step": build_order[0]["action"] if build_order else "Définir les contraintes",
    }

    return result


def generate_build_order(family_id, nodes):
    """Génère l'ordre de construction basé sur la famille.

    La biologie dicte : racines d'abord, toujours.
    La famille dicte : quel ordre pour le reste.
    """
    order = []

    # Grouper les nœuds par niveau
    by_depth = {}
    for n in nodes:
        d = n.get("depth", None)
        lvl = n["level"]
        key = f"depth_{d}" if d is not None else f"level_{lvl}"
        by_depth.setdefault(key, []).append(n["id"])

    # Phase 0 : Mycorhizes (-5) — lois physiques
    ids = by_depth.get("depth_-5", [])
    if ids:
        order.append({
            "phase": 0,
            "name": "Mycorhizes — lois physiques",
            "ids": ids,
            "action": "Identifier les lois physiques/math immuables du projet",
            "bio": "Sans mycorhizes, rien ne pousse. Sans comprendre les lois, rien ne marche."
        })

    # Phase 1 : Racines -4 à -1
    for depth, name in [(-4, "Poils — contraintes légales"),
                        (-3, "Radicelles — business"),
                        (-2, "Pivot — architecture"),
                        (-1, "Structurelles — stack technique")]:
        ids = by_depth.get(f"depth_{depth}", [])
        if ids:
            order.append({
                "phase": 1,
                "name": name,
                "ids": ids,
                "action": f"Définir les contraintes de niveau {depth}",
                "bio": ANATOMY[str(depth)]["bio_detail"]
            })

    # Phase 2+ : dépend de la famille
    if family_id == "conifere":
        # Tronc d'abord, branches subordonnées
        if "level_T" in by_depth:
            order.append({"phase": 2, "name": "Tronc — pipeline principal",
                         "ids": by_depth["level_T"],
                         "action": "Construire le pipeline end-to-end minimal",
                         "bio": "Le leader terminal pousse en premier (contrôle apical)"})
        if "level_B" in by_depth:
            order.append({"phase": 3, "name": "Branches — modules subordonnés",
                         "ids": by_depth["level_B"],
                         "action": "Ajouter les modules UN PAR UN, toujours subordonnés au tronc",
                         "bio": "Les latérales ne dépassent jamais le leader"})

    elif family_id == "baobab":
        # Consolider le tronc massivement avant d'étendre
        if "level_T" in by_depth:
            order.append({"phase": 2, "name": "Tronc — core engine MASSIF",
                         "ids": by_depth["level_T"],
                         "action": "Construire et CONSOLIDER le core avant toute extension",
                         "bio": "Le baobab met toute son énergie dans le tronc d'abord"})
        if "level_B" in by_depth:
            order.append({"phase": 3, "name": "Branches — petites extensions",
                         "ids": by_depth["level_B"],
                         "action": "Extensions petites — ne pas rivaliser avec le tronc",
                         "bio": "Les branches du baobab sont fines comparées au tronc massif"})

    elif family_id == "palmier":
        # Un seul chemin, protéger à tout prix
        if "level_T" in by_depth:
            order.append({"phase": 2, "name": "Tronc — LE chemin unique",
                         "ids": by_depth["level_T"],
                         "action": "Construire LE pipeline unique — le protéger à tout prix",
                         "bio": "Un seul méristème. Si il meurt, le palmier meurt."})
        # Pas de branches pour un palmier — direct aux feuilles
        if "level_F" in by_depth:
            order.append({"phase": 3, "name": "Feuilles — output riche",
                         "ids": by_depth["level_F"],
                         "action": "Output riche au sommet du pipeline unique",
                         "bio": "Les palmes sont grandes et complexes — tout l'output est au sommet"})

    elif family_id == "feuillu":
        if "level_T" in by_depth:
            order.append({"phase": 2, "name": "Tronc — core minimal",
                         "ids": by_depth["level_T"],
                         "action": "Core minimal — il va perdre la dominance face aux branches",
                         "bio": "Le tronc du feuillu se perd parmi les branches (forme décurrente)"})
        if "level_B" in by_depth:
            order.append({"phase": 3, "name": "Branches — modules en parallèle",
                         "ids": by_depth["level_B"],
                         "action": "Modules en parallèle — SURVEILLER la co-dominance",
                         "bio": "⚠️ Si une branche dépasse le tronc = risque de rupture"})

    elif family_id == "buisson":
        # Pas de tronc — tiges en parallèle
        if "level_B" in by_depth:
            order.append({"phase": 2, "name": "Tiges — lancer en parallèle",
                         "ids": by_depth["level_B"],
                         "action": "Lancer plusieurs tiges indépendantes — PAS de hiérarchie",
                         "bio": "Le buisson n'a pas de tronc dominant. Redondance = résilience."})

    elif family_id == "liane":
        if "level_B" in by_depth:
            order.append({"phase": 2, "name": "Point d'attache — interface hôte",
                         "ids": by_depth.get("level_B", [])[:1],
                         "action": "Se connecter au système hôte d'abord",
                         "bio": "La liane s'accroche avant de grandir"})

    # Rameaux, feuilles, cime — toujours en dernier
    for lvl, name in [("b", "Rameaux — sous-features"),
                      ("F", "Feuilles — UI/outputs"),
                      ("C", "Cime — tests et déploiement")]:
        if f"level_{lvl}" in by_depth:
            order.append({
                "phase": 4 if lvl != "C" else 5,
                "name": name,
                "ids": by_depth[f"level_{lvl}"],
                "action": f"Implémenter {name.lower()}",
                "bio": ANATOMY.get({"b": "+3", "F": "+4", "C": "+5"}.get(lvl, "+3"), {}).get("bio_detail", "")
            })

    return order


def print_planted_tree(result):
    """Affiche un arbre planté de manière lisible."""
    f = result
    fam = FAMILIES[f["family"]]

    print(f"\n{'=' * 70}")
    print(f"  🌱 ARBRE PLANTÉ — {f['idea']}")
    print(f"{'=' * 70}")
    print(f"  Famille  : {f['family_emoji']} {f['family_name']} ({fam['forme']})")
    print(f"  Domaine  : {f['domain']}")
    print(f"  Phase    : {f['phase']}")
    print(f"  Nœuds    : {len(f['nodes'])}")
    scale = f.get("scale")
    if scale:
        print(f"  Taille   : {scale['label']} (×{scale['factor']})")
    print()

    # Afficher par niveau (de -5 à +5)
    level_names = {
        -5: "🔬 -5 MYCORHIZES (physique/math)",
        -4: "⚖️  -4 POILS ABSORBANTS (légal)",
        -3: "💰 -3 RADICELLES (business)",
        -2: "⚓ -2 PIVOTANTES (architecture)",
        -1: "🔧 -1 STRUCTURELLES (stack)",
        "+1": "🏗️  +1 TRONC (core)",
        "+2": "🪵 +2 BRANCHES (modules)",
        "+3": "🌿 +3 RAMEAUX (sous-features)",
        "+4": "🍃 +4 FEUILLES (outputs/UI)",
        "+5": "🌱 +5 CIME (tests/deploy)",
    }

    # Sous le sol
    print("  ▼ SOUS LE SOL (racines)")
    print("  " + "─" * 50)
    for depth in [-5, -4, -3, -2, -1]:
        depth_nodes = [n for n in f["nodes"] if n.get("depth") == depth]
        if depth_nodes:
            print(f"\n  {level_names[depth]}")
            for n in depth_nodes:
                print(f"    🔴 [{n['id']:>3}] {n['label']}")

    # Sol
    print(f"\n  {'═' * 50}")
    print(f"  🌍  0  SOL — Interface Sky ↔ Claude")
    print(f"  {'═' * 50}")

    # Au-dessus du sol
    print(f"\n  ▲ AU-DESSUS DU SOL (visible)")
    print("  " + "─" * 50)
    for lvl_key in ["+1", "+2", "+3", "+4", "+5"]:
        level_char = {"T": "+1", "B": "+2", "b": "+3", "F": "+4", "C": "+5"}
        reverse_map = {v: k for k, v in level_char.items()}
        char = reverse_map.get(lvl_key, "?")
        lvl_nodes = [n for n in f["nodes"] if n["level"] == char and n.get("depth") is None]
        if lvl_nodes:
            print(f"\n  {level_names[lvl_key]}")
            for n in lvl_nodes:
                print(f"    🔴 [{n['id']:>3}] {n['label']}")

    # Ordre de construction
    print(f"\n{'=' * 70}")
    print(f"  🔨 ORDRE DE CONSTRUCTION ({fam['emoji']} {fam['nom']})")
    print(f"{'=' * 70}")

    for step in f["build_order"]:
        phase = step["phase"]
        ids_str = ", ".join(step["ids"][:5])
        if len(step["ids"]) > 5:
            ids_str += f" +{len(step['ids'])-5} autres"
        print(f"\n  Phase {phase} : {step['name']}")
        print(f"    → {step['action']}")
        print(f"    📦 {ids_str}")

    print(f"\n{'═' * 70}")
    print(f"  ⏭️  PROCHAIN PAS : {f['next_step']}")
    print(f"{'═' * 70}")


def save_planted_tree(result, filepath=None):
    """Sauvegarde l'arbre planté en YAML-like markdown."""
    f = result
    fam = FAMILIES[f["family"]]

    if filepath is None:
        name_slug = f["idea"].lower()
        for char in " /'\"()[]{}!?,;:":
            name_slug = name_slug.replace(char, "-")
        name_slug = name_slug[:50].strip("-")
        filepath = f"scans/{name_slug}_tree.md"

    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else "scans", exist_ok=True)

    lines = []
    lines.append(f"# WINTER TREE — {f['idea']}")
    lines.append(f"")
    lines.append(f"- Famille : {f['family_emoji']} {f['family_name']}")
    lines.append(f"- Domaine : {f['domain']}")
    lines.append(f"- Date plantation : {f['date']}")
    lines.append(f"- Phase : {f['phase']}")
    lines.append(f"")
    lines.append(f"## ARBRE")
    lines.append(f"")

    # Group nodes by level
    level_order = [
        ("-5", "mycorhizes", "Lois physiques / math / hardware"),
        ("-4", "poils_absorbants", "Contraintes légales"),
        ("-3", "radicelles", "Contraintes business"),
        ("-2", "pivotantes", "Décisions d'architecture"),
        ("-1", "structurelles", "Stack technique"),
        ("+1", "tronc", "Core engine / pipeline"),
        ("+2", "branches", "Modules majeurs"),
        ("+3", "rameaux", "Sous-features"),
        ("+4", "feuilles", "Outputs / UI"),
        ("+5", "cime", "Tests / déploiement"),
    ]

    for depth_key, section_name, section_desc in level_order:
        if depth_key.startswith("-") or depth_key.startswith("+"):
            if depth_key.startswith("-"):
                depth_val = int(depth_key)
                section_nodes = [n for n in f["nodes"] if n.get("depth") == depth_val]
            else:
                level_char = {"+1": "T", "+2": "B", "+3": "b", "+4": "F", "+5": "C"}[depth_key]
                section_nodes = [n for n in f["nodes"] if n["level"] == level_char and n.get("depth") is None]

            lines.append(f"### [{depth_key}] {section_name} — {section_desc}")
            lines.append(f"")
            if section_nodes:
                for n in section_nodes:
                    lines.append(f"```yaml")
                    lines.append(f"- id: {n['id']}")
                    lines.append(f"  label: \"{n['label']}\"")
                    lines.append(f"  status: {n['status']}")
                    lines.append(f"  entry: {n.get('entry', '~')}")
                    lines.append(f"  depends: {n.get('depends', [])}")
                    lines.append(f"```")
                    lines.append(f"")
            else:
                lines.append(f"_Aucun nœud — à remplir_")
                lines.append(f"")

    lines.append(f"## ORDRE DE CONSTRUCTION")
    lines.append(f"")
    for step in f["build_order"]:
        ids_str = ", ".join(step["ids"])
        status = "⬜"
        lines.append(f"- {status} **Phase {step['phase']}** : {step['name']}")
        lines.append(f"  - Action : {step['action']}")
        lines.append(f"  - Nœuds : {ids_str}")
        lines.append(f"")

    lines.append(f"## PROCHAIN PAS")
    lines.append(f"")
    lines.append(f"> {f['next_step']}")

    content = "\n".join(lines)
    with open(filepath, "w", encoding="utf-8") as fp:
        fp.write(content)

    return filepath


# ============================================================================
# 🔬 SCANNER DE REPO — Analyse un projet existant et génère l'arbre
# ============================================================================

# Patterns de détection par fichier/dossier
SCAN_PATTERNS = {
    # -1 Racines structurelles (frameworks, libs, stack)
    "roots": {
        "pubspec.yaml": {"label": "Flutter/Dart", "depth": -1},
        "pubspec.lock": {"label": "Flutter deps lockfile", "depth": -1, "skip_node": True},
        "package.json": {"label": "Node.js", "depth": -1},
        "package-lock.json": {"label": "Node deps lockfile", "depth": -1, "skip_node": True},
        "requirements.txt": {"label": "Python deps", "depth": -1},
        "Pipfile": {"label": "Python Pipenv", "depth": -1},
        "pyproject.toml": {"label": "Python project config", "depth": -1},
        "setup.py": {"label": "Python package", "depth": -1},
        "Cargo.toml": {"label": "Rust", "depth": -1},
        "go.mod": {"label": "Go modules", "depth": -1},
        "Gemfile": {"label": "Ruby", "depth": -1},
        "composer.json": {"label": "PHP Composer", "depth": -1},
        "build.gradle": {"label": "Java/Kotlin Gradle", "depth": -1},
        "pom.xml": {"label": "Java Maven", "depth": -1},
        "CMakeLists.txt": {"label": "C/C++ CMake", "depth": -1},
        "Makefile": {"label": "Make build system", "depth": -1},
        ".swift": {"label": "Swift/iOS", "depth": -1, "ext_match": True},
    },
    # -2 Architecture (config structurante)
    "architecture": {
        "docker-compose.yml": {"label": "Docker Compose (microservices)", "depth": -2},
        "docker-compose.yaml": {"label": "Docker Compose (microservices)", "depth": -2},
        "Dockerfile": {"label": "Docker containerisation", "depth": -2},
        ".env": {"label": "Environment config", "depth": -2},
        ".env.example": {"label": "Env template", "depth": -2},
        "firebase.json": {"label": "Firebase backend", "depth": -2},
        "supabase/": {"label": "Supabase backend", "depth": -2, "is_dir": True},
        "prisma/": {"label": "Prisma ORM", "depth": -2, "is_dir": True},
        "terraform/": {"label": "Terraform infra-as-code", "depth": -2, "is_dir": True},
    },
    # -4 Legal
    "legal": {
        "LICENSE": {"label": "Licence projet", "depth": -4},
        "LICENSE.md": {"label": "Licence projet", "depth": -4},
        "PRIVACY.md": {"label": "Privacy policy", "depth": -4},
        "SECURITY.md": {"label": "Security policy", "depth": -4},
    },
    # +5 Cime (tests, CI)
    "cime": {
        "test/": {"label": "Tests (dossier test/)", "is_dir": True},
        "tests/": {"label": "Tests (dossier tests/)", "is_dir": True},
        "__tests__/": {"label": "Tests Jest", "is_dir": True},
        "spec/": {"label": "Tests spec/", "is_dir": True},
        ".github/workflows/": {"label": "GitHub Actions CI", "is_dir": True},
        ".gitlab-ci.yml": {"label": "GitLab CI"},
        "Jenkinsfile": {"label": "Jenkins CI"},
        ".circleci/": {"label": "CircleCI", "is_dir": True},
        "jest.config.js": {"label": "Jest config"},
        "pytest.ini": {"label": "Pytest config"},
        "tox.ini": {"label": "Tox test runner"},
    },
}

# Extensions → langage
EXT_LANG = {
    ".py": "Python", ".dart": "Dart", ".js": "JavaScript", ".ts": "TypeScript",
    ".jsx": "React JSX", ".tsx": "React TSX", ".vue": "Vue",
    ".swift": "Swift", ".kt": "Kotlin", ".java": "Java",
    ".rs": "Rust", ".go": "Go", ".rb": "Ruby", ".php": "PHP",
    ".c": "C", ".cpp": "C++", ".h": "C/C++ header",
    ".cs": "C#", ".r": "R", ".m": "MATLAB/Obj-C",
    ".sh": "Shell", ".ps1": "PowerShell",
}

# Extensions considérées comme du code (tout le reste = data)
CODE_EXTENSIONS = set(EXT_LANG.keys()) | {
    ".html", ".css", ".scss", ".less", ".xml", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".md", ".rst", ".txt",
    ".sql", ".graphql", ".proto", ".gradle", ".cmake",
}

# Fichiers/dossiers à ignorer
IGNORE = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".idea", ".vscode", ".DS_Store", "build", "dist", ".next",
    ".dart_tool", ".pub-cache", "coverage", ".gradle", "target",
    "Pods", ".flutter-plugins", ".flutter-plugins-dependencies",
}


def scan_repo(path):
    """🔬 Scanne un repo existant et génère un arbre Winter Tree.

    Analyse :
    1. Structure de fichiers → branches et rameaux
    2. Fichiers de config → racines (-1 stack, -2 architecture)
    3. Licences → racines légales (-4)
    4. Tests/CI → cime (+5)
    5. Taille des fichiers → détecte les troncs (plus gros fichier de code)
    6. Langages → détecte le domaine

    Args:
        path: chemin vers le repo (dossier)

    Returns:
        dict — arbre complet prêt pour le gardien
    """
    path = Path(path).resolve()
    if not path.is_dir():
        print(f"  ❌ '{path}' n'est pas un dossier")
        return None

    project_name = path.name

    # ── Collecter tous les fichiers ──
    all_files = []
    all_dirs = set()
    lang_count = {}
    total_code_lines = 0
    biggest_file = {"path": "", "lines": 0, "lang": ""}

    for root, dirs, files in os.walk(path):
        # Filtrer les dossiers ignorés
        dirs[:] = [d for d in dirs if d not in IGNORE]

        rel_root = Path(root).relative_to(path)
        for d in dirs:
            all_dirs.add(str(rel_root / d))

        for f in files:
            fpath = Path(root) / f
            rel = str(fpath.relative_to(path))
            ext = fpath.suffix.lower()

            # Compter les lignes de code
            lines = 0
            if ext in EXT_LANG:
                try:
                    lines = sum(1 for _ in open(fpath, "r", encoding="utf-8", errors="ignore"))
                except:
                    lines = 0

                lang = EXT_LANG[ext]
                lang_count[lang] = lang_count.get(lang, 0) + lines

                if lines > biggest_file["lines"]:
                    biggest_file = {"path": rel, "lines": lines, "lang": lang}

                total_code_lines += lines

            size = fpath.stat().st_size if fpath.exists() else 0
            all_files.append({
                "path": rel,
                "name": f,
                "ext": ext,
                "size": size,
                "lines": lines,
                "lang": EXT_LANG.get(ext, ""),
            })

    # ── Détecter les nœuds ──
    nodes = []
    node_id_counter = {"M": 0, "P": 0, "D": 0, "A": 0, "R": 0,
                       "T": 0, "B": 0, "b": 0, "F": 0, "C": 0}
    found_patterns = set()

    def add_node(prefix, level, depth, label, entry="~", status="done", confidence=0):
        node_id_counter[prefix] = node_id_counter.get(prefix, 0) + 1
        nid = f"{prefix}{node_id_counter[prefix]}"
        # Si le fichier existe (status=done), confidence auto à 80
        # Si absent (status=todo), confidence reste à 0
        if confidence == 0 and status == "done":
            confidence = 80
        node = {
            "id": nid, "level": level, "label": label,
            "status": status, "entry": entry, "depends": [], "desc": "",
            "confidence": confidence,
        }
        if depth is not None:
            node["depth"] = depth
        nodes.append(node)
        return nid

    # --- Scan patterns (racines, archi, legal, cime) ---
    for category, patterns in SCAN_PATTERNS.items():
        for pattern, info in patterns.items():
            if info.get("skip_node"):
                continue

            matched = False
            entry = "~"

            if info.get("is_dir"):
                dir_name = pattern.rstrip("/")
                if dir_name in all_dirs or any(d.startswith(dir_name) for d in all_dirs):
                    matched = True
                    entry = dir_name + "/"
            elif info.get("ext_match"):
                ext = pattern
                if any(f["ext"] == ext for f in all_files):
                    matched = True
            else:
                if any(f["name"] == pattern or f["path"] == pattern for f in all_files):
                    matched = True
                    entry = pattern

            if matched and pattern not in found_patterns:
                found_patterns.add(pattern)
                depth = info.get("depth")
                label = info["label"]

                if depth == -1:
                    add_node("R", "R", -1, label, entry)
                elif depth == -2:
                    add_node("A", "R", -2, label, entry)
                elif depth == -4:
                    add_node("P", "R", -4, label, entry)
                elif category == "cime":
                    add_node("C", "C", None, label, entry)

    # --- Détecter le langage principal → mycorhizes ---
    if lang_count:
        main_lang = max(lang_count, key=lang_count.get)
        main_lines = lang_count[main_lang]
        add_node("M", "R", -5, f"Langage principal : {main_lang} ({main_lines} lignes)")

        if len(lang_count) > 1:
            secondary = sorted(lang_count.items(), key=lambda x: -x[1])
            for lang, lines in secondary[1:3]:
                if lines > total_code_lines * 0.1:  # > 10% du code
                    add_node("M", "R", -5, f"Langage secondaire : {lang} ({lines} lignes)")

    # --- Tronc = le plus gros fichier de code ---
    if biggest_file["lines"] > 0:
        add_node("T", "T", None,
                 f"Core : {biggest_file['path']} ({biggest_file['lines']} lignes, {biggest_file['lang']})",
                 biggest_file["path"], "done")

    # --- Branches = dossiers de premier niveau avec du code ---
    top_dirs = {}
    for f in all_files:
        parts = f["path"].split(os.sep)
        if len(parts) > 1 and f["lines"] > 0:
            top_dir = parts[0]
            if top_dir not in IGNORE:
                if top_dir not in top_dirs:
                    top_dirs[top_dir] = {"files": 0, "lines": 0, "langs": set()}
                top_dirs[top_dir]["files"] += 1
                top_dirs[top_dir]["lines"] += f["lines"]
                if f["lang"]:
                    top_dirs[top_dir]["langs"].add(f["lang"])

    # Trier par lignes de code
    sorted_dirs = sorted(top_dirs.items(), key=lambda x: -x[1]["lines"])
    for dirname, info in sorted_dirs[:10]:
        langs = ", ".join(list(info["langs"])[:2])
        add_node("B", "B", None,
                 f"{dirname}/ ({info['files']} fichiers, {info['lines']}L, {langs})",
                 f"{dirname}/", "done")

        # Rameaux = sous-dossiers
        sub_dirs = {}
        for f in all_files:
            parts = f["path"].split(os.sep)
            if len(parts) > 2 and parts[0] == dirname and f["lines"] > 0:
                sub = parts[1]
                if sub not in sub_dirs:
                    sub_dirs[sub] = {"files": 0, "lines": 0}
                sub_dirs[sub]["files"] += 1
                sub_dirs[sub]["lines"] += f["lines"]

        for subname, subinfo in sorted(sub_dirs.items(), key=lambda x: -x[1]["lines"])[:5]:
            add_node("b", "b", None,
                     f"{dirname}/{subname}/ ({subinfo['files']}f, {subinfo['lines']}L)",
                     f"{dirname}/{subname}/", "done")

    # --- Fichiers racine avec du code (pas dans un sous-dossier) ---
    root_code_files = [f for f in all_files if os.sep not in f["path"]
                       and f["lines"] > 50 and f["ext"] in EXT_LANG]
    for f in sorted(root_code_files, key=lambda x: -x["lines"]):
        # Pas un doublon du tronc
        if f["path"] != biggest_file["path"]:
            add_node("B", "B", None,
                     f"{f['path']} ({f['lines']}L, {f['lang']})",
                     f["path"], "done")

    # --- Nœuds manquants (gaps) → todo ---
    # Pas de tests ?
    if not any(n["level"] == "C" for n in nodes):
        add_node("C", "C", None, "Tests/CI — ABSENT", "~", "todo")

    # Pas de licence ?
    if not any(n.get("depth") == -4 for n in nodes):
        add_node("P", "R", -4, "Licence/Legal — ABSENT", "~", "todo")

    # Pas de README ?
    has_readme = any(f["name"].lower().startswith("readme") for f in all_files)
    if not has_readme:
        add_node("F", "F", None, "README — ABSENT", "~", "todo")

    # ── Classifier la famille ──
    family_id = _classify_from_scan(nodes, top_dirs, biggest_file, total_code_lines, path, all_files)

    # ── Détecter le domaine ──
    # Utiliser les noms de fichiers et dossiers pour deviner
    all_text = " ".join(f["path"] for f in all_files).lower()
    domain = detect_domain(all_text + " " + project_name)

    # ── Construire l'arbre ──
    build_order = generate_build_order(family_id, nodes)

    # Calculer le poids des données (tout sauf le code et .git)
    data_weight_mb = 0
    try:
        for root_dir, dirs, filenames in os.walk(path):
            # Ignorer .git
            if ".git" in root_dir:
                continue
            dirs[:] = [d for d in dirs if d != ".git"]
            for fname in filenames:
                fpath = os.path.join(root_dir, fname)
                ext = os.path.splitext(fname)[1].lower()
                # Si c'est pas du code, c'est de la data
                if ext not in CODE_EXTENSIONS:
                    try:
                        data_weight_mb += os.path.getsize(fpath) / (1024 * 1024)
                    except:
                        pass
    except:
        pass

    # Calculer l'échelle visuelle (hauteur = code, épaisseur = data)
    scale = calculate_scale(total_code_lines, data_weight_mb)

    tree = {
        "idea": f"[scanned] {project_name}",
        "domain": domain,
        "family": family_id,
        "family_name": FAMILIES[family_id]["nom"],
        "family_emoji": FAMILIES[family_id]["emoji"],
        "date": datetime.now().isoformat(),
        "phase": "MATURE",  # sera recalculé
        "scanned_from": str(path),
        "scale": scale,
        "stats": {
            "total_files": len(all_files),
            "total_code_lines": total_code_lines,
            "data_weight_mb": round(data_weight_mb, 1),
            "languages": lang_count,
            "biggest_file": biggest_file,
        },
        "nodes": nodes,
        "build_order": build_order,
        "next_step": "Vérifier l'arbre scanné et compléter les nœuds manquants",
    }

    _update_phase(tree)

    return tree


def _classify_from_scan(nodes, top_dirs, biggest_file, total_code_lines, repo_path=None, all_files=None):
    """Classifie la famille selon l'arbre de décision Q1→Q6.

    Fondements scientifiques :
    - Lindenmayer 1968 : L-Systems, réécriture parallèle
    - Prusinkiewicz & Lindenmayer 1990 : The Algorithmic Beauty of Plants
    - Tomer & Schach 2000 : Evolution Tree (CSMR, Zurich)
    - Fowler 2004 : Strangler Fig Application
    - Barnes 2013 (CMU) : Software Architecture Evolution

    Arbre de décision (réf: GROWTH_PATTERNS_6_FAMILIES.md l.339-362) :
        Q3: Core énorme, petite interface ?       → 🌳 BAOBAB
        Q6: Wrappe un système existant ?           → 🌿 LIANE
        Q1: Pipeline linéaire (flux input→output) ?
            Q2: Étroit, single meristem ?          → 🌴 PALMIER
            Q2: Large, branches subordonnées ?     → 🌲 CONIFÈRE
        Q4: Modules parallèles ?
            Q5: Interdépendants ?                  → 🍁 FEUILLU
            Q5: Indépendants ?                     → 🌿 BUISSON
    """
    import re

    files = all_files or []
    trunk_lines = biggest_file["lines"] if biggest_file else 0
    trunk_ratio = trunk_lines / total_code_lines if total_code_lines > 0 else 0
    branch_nodes = [n for n in nodes if n["level"] == "B"]
    n_branches = len(branch_nodes)

    # ══════════════════════════════════════════════════════════════
    # EXTRACTION DES MÉTRIQUES
    # ══════════════════════════════════════════════════════════════

    # ── Séparer cœur / périphérie ──
    CORE_DIRS = {"src", "lib", "core", "app", "pkg", "internal", "modules",
                 "binance_bot", "engine", "api", "server", "services"}
    PERIPHERAL_DIRS = {"scripts", "tools", "utils", "outputs", "docs",
                       "examples", "samples", "notebooks", "archives",
                       "data", "assets", "static", "templates", "config",
                       "test", "tests", "__tests__", "spec"}

    core_lines = 0
    peripheral_lines = 0
    core_dirs_found = set()

    if files:
        for f in files:
            if f["lines"] == 0:
                continue
            parts = f["path"].split(os.sep if os.sep in f["path"] else "/")
            if len(parts) > 1:
                top = parts[0].lower()
                if top in CORE_DIRS:
                    core_lines += f["lines"]
                    core_dirs_found.add(parts[0])
                elif top in PERIPHERAL_DIRS:
                    peripheral_lines += f["lines"]
                else:
                    core_lines += f["lines"]
                    core_dirs_found.add(parts[0])
            else:
                core_lines += f["lines"]

    n_core_dirs = len(core_dirs_found)

    # ── Taille des branches vs tronc (Règle C2: BRANCH_SUBORDINATION) ──
    branch_sizes = []
    for dirname, info in top_dirs.items():
        if isinstance(info, dict) and info.get("lines", 0) > 0:
            branch_sizes.append(info["lines"])

    # C2: branch.size < 0.6 × trunk.size
    branches_subordinate = (
        all(bs < trunk_lines * 0.6 for bs in branch_sizes)
        if (branch_sizes and trunk_lines > 0) else False
    )

    # ── Tracer les imports ──
    import_graph = {}

    if repo_path and files:
        project_modules = set()
        for f in files:
            if f["ext"] in (".py", ".dart", ".js", ".ts", ".jsx", ".tsx"):
                mod = f["path"].replace(os.sep, ".").replace("/", ".")
                for ext in (".py", ".dart", ".js", ".ts", ".jsx", ".tsx"):
                    mod = mod.replace(ext, "")
                project_modules.add(mod)
                parts = f["path"].split(os.sep)
                for i in range(len(parts)):
                    project_modules.add(".".join(parts[:i + 1]).replace(".py", "").replace(".dart", ""))

        for f in files:
            if f["ext"] not in (".py", ".dart", ".js", ".ts"):
                continue
            if f["lines"] == 0:
                continue
            parts = f["path"].split(os.sep)
            if len(parts) > 1 and parts[0].lower() in PERIPHERAL_DIRS:
                continue

            fpath = Path(repo_path) / f["path"]
            imports = set()

            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        line = line.strip()
                        if line.startswith("from ") and " import " in line:
                            module = line.split("from ")[1].split(" import")[0].strip()
                            if module.startswith("."):
                                base = ".".join(parts[:-1])
                                module = base + module
                            imports.add(module)
                        elif line.startswith("import ") and not line.startswith("import "):
                            module = line.split("import ")[1].split(" as ")[0].split(",")[0].strip()
                            imports.add(module)
                        elif line.startswith("import '") or line.startswith('import "'):
                            path_str = line.split("'")[1] if "'" in line else line.split('"')[1]
                            if not path_str.startswith("dart:") and not path_str.startswith("package:flutter"):
                                imports.add(path_str)
                        elif line.startswith("import ") and "from " in line:
                            module = line.split("from ")[1].strip().strip("'\"").strip(";")
                            if module.startswith("."):
                                imports.add(module)
            except:
                continue

            internal_imports = set()
            for imp in imports:
                imp_clean = imp.replace("/", ".").replace("\\", ".")
                for pm in project_modules:
                    if imp_clean.startswith(pm) or pm.startswith(imp_clean):
                        internal_imports.add(imp_clean)
                        break
                if imp.startswith("."):
                    internal_imports.add(imp)

            if internal_imports:
                import_graph[f["path"]] = internal_imports

    # ── Métriques du graphe d'imports ──
    chain_depth = _find_longest_chain(import_graph)
    n_files_with_imports = len(import_graph)
    has_imports = n_files_with_imports > 0

    imported_by_count = {}
    for src_file, imports in import_graph.items():
        for imp in imports:
            imported_by_count[imp] = imported_by_count.get(imp, 0) + 1
    max_hub = max(imported_by_count.values()) if imported_by_count else 0

    # ── Cross-imports entre branches (Q5: interdépendance) ──
    cross_branch_imports = 0
    if import_graph:
        for src_file, imports in import_graph.items():
            src_parts = src_file.split(os.sep if os.sep in src_file else "/")
            src_branch = src_parts[0] if len(src_parts) > 1 else ""
            for imp in imports:
                imp_parts = imp.replace(".", "/")
                for target_file in import_graph.keys():
                    t_parts = target_file.split(os.sep if os.sep in target_file else "/")
                    t_branch = t_parts[0] if len(t_parts) > 1 else ""
                    if t_branch and t_branch != src_branch and imp_parts in target_file:
                        cross_branch_imports += 1
                        break

    # ── Détection de domaine fonctionnel (pour Q1) ──
    CODE_EXTS = {".py", ".dart", ".js", ".ts", ".jsx", ".tsx", ".cpp", ".c", ".h",
                 ".hpp", ".rs", ".go", ".java", ".kt", ".swift", ".rb", ".php",
                 ".sh", ".ps1"}
    code_paths = [f["path"].lower() for f in files if f.get("ext", "") in CODE_EXTS]
    all_names_lower = [f["name"].lower() for f in files]
    all_dirs_lower = set()
    for f in files:
        parts = f["path"].split(os.sep if os.sep in f["path"] else "/")
        if len(parts) > 1:
            all_dirs_lower.add(parts[0].lower())

    # Domaines pipeline (Prusinkiewicz: excurrent growth = flux linéaire)
    # Word boundaries pour éviter "bot" ∈ "bottom", "step" ∈ "steps.png"
    # IMPORTANT : on compte les DOSSIERS uniques contenant le pattern,
    # pas les fichiers individuels. src/audio/ = 1 hit, pas 17.
    PIPELINE_PATTERNS = [
        r'\bpipeline\b', r'\bstage[s]?\b', r'\bphase\b', r'\betape\b',
        r'\bworkflow\b', r'\bichimoku\b', r'\bbacktest\b', r'\btrading\b',
        r'\bstrategy\b', r'\boptimizer\b', r'\broutine[s]?\b', r'\bscheduler\b',
        r'\bcron\b', r'\bbot\b', r'\bsignal[s]?\b', r'\bfft\b',
        r'\bcapture\b', r'\bpitch\b', r'\btranslat', r'\btransform\b',
        r'\bconversion\b', r'\bprocessing\b', r'\betl\b',
    ]
    _pipeline_re = re.compile("|".join(PIPELINE_PATTERNS))

    # Compter les dossiers de 1er niveau contenant un pattern pipeline
    pipeline_dirs = set()
    for p in code_paths:
        if _pipeline_re.search(p):
            parts = p.split("/")
            # Identifier le dossier de 1er ou 2ème niveau
            dir_key = parts[0] if len(parts) <= 2 else "/".join(parts[:2])
            pipeline_dirs.add(dir_key)
    # Aussi checker les noms de dossiers top-level
    for d in all_dirs_lower:
        if _pipeline_re.search(d):
            pipeline_dirs.add(d)

    pipeline_hits = len(pipeline_dirs)
    has_versioned = _detect_versioned_files(files)

    # Détection liane (Fowler 2004: Strangler Fig)
    LIANE_MARKERS = {"setup.py", "setup.cfg", "pyproject.toml", "plugin.xml",
                     "manifest.json", "extension.json"}
    WRAPPER_KW = {"wrapper", "plugin", "extension", "addon", "bridge",
                  "binding", "adapter", "connector", "proxy"}
    liane_marker_count = len(LIANE_MARKERS & set(all_names_lower))
    wrapper_re = re.compile(r'\b(?:' + '|'.join(WRAPPER_KW) + r')\b')
    wrapper_hits = sum(1 for p in code_paths if wrapper_re.search(p))

    # Détection app framework (pour Q5: interdépendance structurelle)
    FLUTTER_MARKERS = {"pubspec.yaml", "pubspec.lock"}
    is_flutter = bool(FLUTTER_MARKERS & set(all_names_lower)) and "lib" in all_dirs_lower
    SHARED_CORE_DIRS = {"lib", "core", "src", "engine", "app", "pkg", "internal", "modules"}
    has_shared_core = bool(SHARED_CORE_DIRS & all_dirs_lower)

    # ══════════════════════════════════════════════════════════════
    # ARBRE DE DÉCISION Q1→Q6
    # Réf: GROWTH_PATTERNS_6_FAMILIES.md l.339-362
    # ══════════════════════════════════════════════════════════════

    # ── Q3 : Core énorme, petite interface ? → BAOBAB ──
    # Règle B1: TRUNK_IS_STORAGE — "tronc massif, canopée petite"
    # Chapotin et al. 2006 : parenchyme 69-88%, densité 0.09-0.17 g/cm³
    # Seuil : un seul fichier contient 70%+ du code = monolithe de stockage
    if trunk_ratio > 0.70:
        return "baobab"

    # ── Q6 : Wrappe un système existant ? → LIANE ──
    # Fowler 2004 — HOST_REQUIRED, SPEED_OVER_STRUCTURE
    if liane_marker_count >= 2 and wrapper_hits >= 2 and n_branches <= 4:
        return "liane"

    # ── Q1 : Pipeline linéaire (flux input → process → output) ? ──
    # Lindenmayer 1968 — pattern excurrent (dominance apicale)
    # Un pipeline = un flux de données qui traverse des étapes séquentielles
    # Signaux : chaîne d'imports, domaine fonctionnel, subordination des branches
    #
    # NOTE : le trunk_ratio peut être artificiellement bas si le repo contient
    # beaucoup de fichiers non-code (HTML, data, outputs). Les signaux forts
    # (chaîne d'imports, domaine fonctionnel) n'ont pas besoin de trunk dominant.
    # Seuls les signaux faibles (subordination structurelle) nécessitent un tronc.

    is_pipeline = False

    # ── Signaux forts (pas besoin de trunk dominant) ──

    # Import chain prouvé (A→B→C→D) — preuve directe de flux linéaire
    if chain_depth >= 3:
        is_pipeline = True

    # Hub central orchestrateur + chaîne
    if max_hub >= 4 and chain_depth >= 2:
        is_pipeline = True

    # Domaine fonctionnel pipeline fort (plusieurs keywords)
    if pipeline_hits >= 4:
        is_pipeline = True

    # Fichiers versionnés = itérations sur même pipeline
    if has_versioned:
        is_pipeline = True

    # Domaine pipeline + au moins un signal structurel
    if pipeline_hits >= 2 and (has_versioned or chain_depth >= 2 or trunk_ratio > 0.1):
        is_pipeline = True

    # ── Signaux faibles (nécessitent trunk dominant — Brown 1971) ──

    # Branches subordonnées : nécessite dominance apicale mesurable
    if branches_subordinate and trunk_ratio > 0.15 and n_branches >= 2:
        is_pipeline = True

    if is_pipeline:
        # ── Q2 : Pipeline étroit (palmier) ou large (conifère) ? ──
        #
        # PALMIER (Tomlinson 1990) :
        #   P1: SINGLE_MERISTEM — un seul point de production
        #   P3: NO_LATERAL_BRANCHING — zéro branche latérale
        #   → Pipeline concentré, peu/pas de modules séparés
        #
        # CONIFÈRE (Brown 1971, Wilson 2000) :
        #   C1: TRUNK_FIRST — tronc d'abord
        #   C2: BRANCH_SUBORDINATION — branches < 0.6 × tronc
        #   → Pipeline avec stages multiples, branches subordonnées
        #
        # IMPORTANT : les dossiers platform Flutter/mobile (android/, ios/,
        # windows/, macos/, linux/, web/) sont du boilerplate, PAS des branches
        # fonctionnelles. On les filtre pour Q2 (Tomlinson: structure vs delivery).

        PLATFORM_BOILERPLATE = {"android", "ios", "macos", "windows", "linux", "web",
                                "test", "tests", "docs", "scripts", "demo", "examples"}

        significant_branches = 0
        for dirname, info in top_dirs.items():
            if isinstance(info, dict) and info.get("lines", 0) > trunk_lines * 0.1:
                if dirname.lower() not in PLATFORM_BOILERPLATE:
                    significant_branches += 1

        # Palmier : peu de branches fonctionnelles significatives
        # SAUF si on a des stages versionnés → multi-stage = conifère
        if significant_branches <= 2 and not has_versioned and pipeline_hits <= 2:
            return "palmier"

        # Palmier : tronc très dominant, code concentré, pas de stages
        if trunk_ratio > 0.35 and significant_branches <= 1 and not has_versioned:
            return "palmier"

        # Conifère : pipeline avec plusieurs stages subordonnés
        return "conifere"

    # ── Q4 : Modules parallèles ? ──
    has_parallel_modules = n_branches >= 3 or n_core_dirs >= 2

    if has_parallel_modules:
        # ── Q5 : Modules interdépendants ? ──
        #
        # FEUILLU (ISA Arboriculture, Virginia Tech) :
        #   F2: LATERAL_COMPETITION — branches rivalisent avec le leader
        #   F4: CO_DOMINANCE_RISK — modules connectés, risque de rupture
        #   → Modules qui s'importent mutuellement, base commune
        #
        # BUISSON (U. Minnesota, Iowa State) :
        #   S1: NO_CENTRAL_TRUNK — pas de module principal
        #   S2: REDUNDANCY_IS_RESILIENCE — si un meurt, les autres vivent
        #   → Outils indépendants, pas de cross-imports

        # Avec imports : cross-imports prouvent l'interdépendance
        if has_imports:
            if cross_branch_imports >= 2 or max_hub >= 3:
                return "feuillu"
            if n_files_with_imports <= 1 and n_branches >= 3:
                return "buisson"

        # App framework intégré = modules interdépendants par design
        # (Flutter/React app : lib/ screens dépendent de lib/ services)
        if is_flutter and has_shared_core:
            return "feuillu"

        # Convention de nommage partagée = même produit = interdépendant
        # Ex: "infernal-app", "infernal-migration" → préfixe commun = même système
        dir_names = [d.lower() for d in top_dirs.keys() if top_dirs[d].get("lines", 0) > 0]
        if len(dir_names) >= 2:
            for i, d1 in enumerate(dir_names):
                for d2 in dir_names[i+1:]:
                    # Préfixe commun d'au moins 4 caractères
                    prefix = os.path.commonprefix([d1, d2])
                    if len(prefix) >= 4:
                        return "feuillu"

        # Shared core dir (lib/, src/, core/) = architecture unifiée → feuillu
        if has_shared_core and core_lines > peripheral_lines:
            return "feuillu"

        # Multi core dirs vrais (src/ + lib/, etc.) = feuillu
        real_core = {"src", "lib", "core", "app"} & all_dirs_lower
        if len(real_core) >= 2:
            return "feuillu"

        # Pas de core partagé, que du périphérique = outils indépendants → buisson
        if not has_shared_core and core_lines == 0:
            return "buisson"

        # Pas d'indice d'interdépendance → buisson par défaut
        # (S2: "si un composant meurt, les autres continuent")
        return "buisson"

    # ── Pas de pipeline, pas de modules parallèles ──
    # Peu de branches = projet simple

    # Palmier si très petit/simple
    if n_branches <= 1:
        return "palmier"

    # Fallback : feuillu (Q6 NON → feuillu par défaut)
    return "feuillu"


def _find_longest_chain(import_graph):
    """Trouve la plus longue chaîne d'imports A→B→C→D.

    Une chaîne longue = pipeline linéaire = conifère.
    """
    if not import_graph:
        return 0

    # Simplifier : mapper les imports vers des fichiers connus du graphe
    file_keys = set(import_graph.keys())

    def match_import_to_file(imp):
        """Essayer de matcher un import à un fichier du graphe."""
        imp_parts = imp.replace(".", "/")
        for fk in file_keys:
            fk_clean = fk.replace(".py", "").replace(".dart", "").replace(".js", "")
            if imp_parts in fk_clean or fk_clean.endswith(imp_parts):
                return fk
        return None

    # Construire le graphe simplifié fichier → fichier
    graph = {}
    for src_file, imports in import_graph.items():
        targets = set()
        for imp in imports:
            target = match_import_to_file(imp)
            if target and target != src_file:
                targets.add(target)
        if targets:
            graph[src_file] = targets

    # DFS pour trouver la plus longue chaîne
    max_depth = 0

    def dfs(node, visited):
        nonlocal max_depth
        max_depth = max(max_depth, len(visited))
        for neighbor in graph.get(node, set()):
            if neighbor not in visited:
                visited.add(neighbor)
                dfs(neighbor, visited)
                visited.discard(neighbor)

    for start in graph:
        dfs(start, {start})

    return max_depth


def _detect_versioned_files(all_files):
    """Détecte des fichiers versionnés (v1, v2, v3...).

    Si on trouve ça, c'est des itérations d'un même pipeline,
    pas des outils indépendants. → conifère, pas buisson.
    """
    import re
    version_pattern = re.compile(r'_v\d+[\._]')
    versioned = [f["path"] for f in all_files
                 if version_pattern.search(f["path"]) and f["ext"] in (".py", ".dart", ".js")]

    # Si on trouve au moins 2 fichiers versionnés avec le même préfixe
    if len(versioned) >= 2:
        prefixes = set()
        for v in versioned:
            prefix = version_pattern.split(v)[0]
            prefixes.add(prefix)
        # Si un même préfixe a plusieurs versions → oui
        for prefix in prefixes:
            count = sum(1 for v in versioned if v.startswith(prefix))
            if count >= 2:
                return True

    return False


def calculate_scale(total_lines, data_weight_mb=0):
    """Calcule l'échelle visuelle de l'arbre — 2 dimensions.

    HAUTEUR (factor, height_px) = lignes de code = le bois, la structure.
    ÉPAISSEUR (density, trunk_width) = poids des données = la nourriture, les racines.

    Un projet de 35k lignes + 7Go de data sera moins haut qu'un projet de 40k
    mais avec un tronc bien plus épais et un sol riche autour.

    Args:
        total_lines: nombre de lignes de code
        data_weight_mb: poids total du repo hors code (en MB)

    Retourne un dict avec :
    - lines, factor, height_px: dimension HAUTEUR (code)
    - data_mb, density, trunk_width: dimension ÉPAISSEUR (data)
    - category, label: résumé lisible

    Échelle hauteur (code) :
        < 500       → graine      (factor 0.5)
        500-2000    → pousse      (factor 0.8)
        2000-10000  → arbre       (factor 1.0)
        10000-50000 → grand arbre (factor 1.5)
        50000-200k  → géant       (factor 2.0)
        200k+       → titan       (factor 2.5)

    Échelle épaisseur (data) :
        < 10 MB     → léger       (density 1.0)
        10-100 MB   → normal      (density 1.3)
        100-1000 MB → dense       (density 1.6)
        1-10 GB     → massif      (density 2.0)
        10 GB+      → colossal    (density 2.5)
    """
    import math

    if total_lines <= 0:
        return {"lines": 0, "factor": 0.5, "category": "graine",
                "height_px": 200, "data_mb": data_weight_mb, "density": 1.0,
                "trunk_width": 1.0, "label": "🌰 Graine (0 lignes)"}

    # ── HAUTEUR (code) ──
    log_lines = math.log10(max(total_lines, 1))

    if total_lines < 500:
        cat, emoji, factor, height = "graine", "🌰", 0.5, 200
    elif total_lines < 2000:
        cat, emoji, factor, height = "pousse", "🌱", 0.8, 300
    elif total_lines < 10000:
        cat, emoji, factor, height = "arbre", "🌳", 1.0, 400
    elif total_lines < 50000:
        cat, emoji, factor, height = "grand arbre", "🌲", 1.5, 500
    elif total_lines < 200000:
        cat, emoji, factor, height = "géant", "🏔️", 2.0, 600
    else:
        cat, emoji, factor, height = "titan", "⛰️", 2.5, 700

    # Smooth interpolation within category
    ranges = [(0, 500), (500, 2000), (2000, 10000),
              (10000, 50000), (50000, 200000), (200000, 1000000)]
    for low, high in ranges:
        if low <= total_lines < high:
            position = (total_lines - low) / (high - low)
            factor += position * 0.3
            height += int(position * 50)
            break

    # ── ÉPAISSEUR (data) ──
    if data_weight_mb < 10:
        density = 1.0
        data_cat = "léger"
    elif data_weight_mb < 100:
        density = 1.3
        data_cat = "normal"
    elif data_weight_mb < 1000:
        density = 1.6
        data_cat = "dense"
    elif data_weight_mb < 10000:
        density = 2.0
        data_cat = "massif"
    else:
        density = 2.5
        data_cat = "colossal"

    # Smooth interpolation épaisseur
    data_ranges = [(0, 10), (10, 100), (100, 1000), (1000, 10000), (10000, 100000)]
    for low, high in data_ranges:
        if low <= data_weight_mb < high:
            pos = (data_weight_mb - low) / (high - low)
            density += pos * 0.3
            break

    trunk_width = round(density, 2)

    # Format human-readable
    lines_str = f"{total_lines // 1000}k" if total_lines >= 1000 else str(total_lines)
    if data_weight_mb >= 1000:
        data_str = f"{data_weight_mb / 1000:.1f}Go"
    elif data_weight_mb > 0:
        data_str = f"{int(data_weight_mb)}Mo"
    else:
        data_str = "~"

    return {
        "lines": total_lines,
        "factor": round(factor, 2),
        "category": cat,
        "height_px": height,
        "data_mb": data_weight_mb,
        "density": round(density, 2),
        "trunk_width": trunk_width,
        "data_category": data_cat,
        "label": f"{emoji} {cat.title()} ({lines_str} lignes, {data_str} data)",
    }


def print_scan_report(tree):
    """Affiche le rapport de scan."""
    stats = tree["stats"]
    fam = FAMILIES[tree["family"]]

    print(f"\n{'=' * 60}")
    print(f"  🔬 SCAN TERMINÉ — {tree['scanned_from']}")
    print(f"{'=' * 60}")
    print(f"  Famille  : {tree['family_emoji']} {tree['family_name']} ({fam['forme']})")
    print(f"  Domaine  : {tree['domain']}")
    print(f"  Fichiers : {stats['total_files']}")
    print(f"  Code     : {stats['total_code_lines']} lignes")

    data_mb = stats.get('data_weight_mb', 0)
    if data_mb >= 1000:
        print(f"  Data     : {data_mb / 1000:.1f} Go")
    elif data_mb > 0:
        print(f"  Data     : {int(data_mb)} Mo")

    if stats["languages"]:
        langs = sorted(stats["languages"].items(), key=lambda x: -x[1])
        lang_str = ", ".join(f"{l} ({n}L)" for l, n in langs[:5])
        print(f"  Langages : {lang_str}")

    if stats["biggest_file"]["path"]:
        bf = stats["biggest_file"]
        print(f"  Plus gros: {bf['path']} ({bf['lines']}L, {bf['lang']})")

    print(f"  Nœuds    : {len(tree['nodes'])}")
    scale = tree.get("scale")
    if scale:
        print(f"  Taille   : {scale['label']} (×{scale['factor']})")

    # Résumé par niveau
    done = sum(1 for n in tree["nodes"] if n["status"] == "done")
    todo = sum(1 for n in tree["nodes"] if n["status"] == "todo")
    print(f"  Trouvés  : {done} ✅  Manquants : {todo} 🔴")

    # Gaps
    gaps = [n for n in tree["nodes"] if n["status"] == "todo"]
    if gaps:
        print(f"\n  --- Manquants détectés ---")
        for n in gaps:
            print(f"    🔴 [{n['id']}] {n['label']}")

    print(f"\n{'=' * 60}")


# ============================================================================
# 🔍 RESEARCH PROMPTS — Génère les requêtes de recherche par nœud
# ============================================================================

# Stratégie de recherche par profondeur
RESEARCH_STRATEGY = {
    -5: {
        "zone": "Mycorhizes",
        "cherche": "FORMULES, CONSTANTES, LIMITES physiques, théorèmes",
        "template": "{sujet} formule calcul constantes limites {contexte}",
        "exemples": ["FFT window size latence minimum", "barème impôt progressif formule"],
        "depth_target": "Chiffres exacts, formules, seuils, limites physiques"
    },
    -4: {
        "zone": "Poils absorbants",
        "cherche": "LOIS, ARTICLES de loi, NORMES, DATES, CERTIFICATIONS",
        "template": "{sujet} loi réglementation obligations {contexte} {année}",
        "exemples": ["GDPR obligations app mobile", "nLPD Suisse logiciel données personnelles"],
        "depth_target": "Numéros d'articles, dates d'entrée en vigueur, sanctions"
    },
    -3: {
        "zone": "Radicelles",
        "cherche": "CHIFFRES de marché, CONCURRENTS, PRIX, UTILISATEURS",
        "template": "{sujet} marché concurrents parts prix {contexte}",
        "exemples": ["logiciel fiscal suisse concurrent GeTax prix", "app piano marché taille"],
        "depth_target": "Noms de concurrents, prix, nombre d'utilisateurs, parts de marché"
    },
    -2: {
        "zone": "Pivotantes",
        "cherche": "ARCHITECTURES existantes, PATTERNS, comment les autres ont résolu",
        "template": "{sujet} architecture technique solution existante {contexte}",
        "exemples": ["architecture logiciel fiscal calcul", "audio pipeline mobile architecture"],
        "depth_target": "Diagrammes d'architecture, choix techniques des concurrents, patterns"
    },
    -1: {
        "zone": "Structurelles",
        "cherche": "LIBS, FRAMEWORKS, APIs concrètes avec VERSIONS",
        "template": "{sujet} framework library API {contexte} {année}",
        "exemples": ["python tax calculation library", "flutter audio recording package 2025"],
        "depth_target": "Noms de packages, versions, liens GitHub, documentation"
    },
}


def generate_research_prompts(tree, context=""):
    """🔍 Génère les prompts de recherche pour remplir les racines.

    Le plant enrichi utilise ces prompts pour chercher automatiquement.
    La deep research utilise le même format mais creuse plus profond.

    Args:
        tree: l'arbre planté
        context: contexte donné par Sky ("suisse, genève, particuliers")

    Returns:
        list de dicts {node_id, level, prompt, strategy, depth_target}
    """
    idea = tree["idea"]
    prompts = []

    for node in tree["nodes"]:
        depth = node.get("depth")
        if depth is None or depth not in RESEARCH_STRATEGY:
            continue

        strategy = RESEARCH_STRATEGY[depth]

        # Construire le prompt de recherche
        sujet = node["label"]
        année = "2025"
        prompt = strategy["template"].format(
            sujet=sujet, contexte=context, année=année
        ).strip()

        prompts.append({
            "node_id": node["id"],
            "node_label": node["label"],
            "level": depth,
            "zone": strategy["zone"],
            "prompt": prompt,
            "strategy": strategy["cherche"],
            "depth_target": strategy["depth_target"],
            "confidence": node.get("confidence", 0),
        })

    # Trier : les moins confiants d'abord (besoin de recherche en premier)
    prompts.sort(key=lambda x: x["confidence"])

    return prompts


def confidence_bar(pct, width=10):
    """Génère une barre de confiance visuelle."""
    filled = int((pct / 100) * width)
    empty = width - filled
    bar = "█" * filled + "░" * empty

    if pct <= 30:
        icon = "🔴"
        label = "deep research obligatoire"
    elif pct <= 70:
        icon = "🟡"
        label = "deep research recommandée"
    else:
        icon = "🟢"
        label = "prêt à coder"

    return f"{icon} {bar} {pct:3d}%  {label}"


def print_research_prompts(prompts):
    """Affiche les prompts de recherche."""
    print(f"\n{'=' * 60}")
    print(f"  🔍 PROMPTS DE RECHERCHE")
    print(f"{'=' * 60}")

    current_level = None
    for p in prompts:
        if p["level"] != current_level:
            current_level = p["level"]
            strategy = RESEARCH_STRATEGY[current_level]
            print(f"\n  [{current_level}] {strategy['zone']} — cherche: {strategy['cherche']}")
            print(f"  " + "─" * 50)

        bar = confidence_bar(p["confidence"])
        print(f"    [{p['node_id']:>3}] {p['node_label']}")
        print(f"          {bar}")
        print(f"          🔎 \"{p['prompt']}\"")
        print(f"          📎 Cible: {p['depth_target']}")
        print()

    # Résumé
    total = len(prompts)
    red = sum(1 for p in prompts if p["confidence"] <= 30)
    yellow = sum(1 for p in prompts if 30 < p["confidence"] <= 70)
    green = sum(1 for p in prompts if p["confidence"] > 70)
    print(f"  {'─' * 50}")
    print(f"  Résumé: {red} 🔴 deep obligatoire | {yellow} 🟡 recommandée | {green} 🟢 prêt")
    print(f"{'=' * 60}")


def print_confidence_map(tree):
    """Affiche la carte de confiance de l'arbre — vue rapide."""
    nodes = tree["nodes"]

    print(f"\n{'=' * 60}")
    print(f"  📊 CARTE DE CONFIANCE — {tree['idea']}")
    print(f"{'=' * 60}")

    level_order = [
        (-5, "🔬 Mycorhizes"), (-4, "⚖️  Poils abs."),
        (-3, "💰 Radicelles"), (-2, "⚓ Pivotantes"),
        (-1, "🔧 Structurelles"),
    ]

    for depth, label in level_order:
        depth_nodes = [n for n in nodes if n.get("depth") == depth]
        if not depth_nodes:
            continue
        print(f"\n  {label}")
        for n in depth_nodes:
            conf = n.get("confidence", 0)
            bar = confidence_bar(conf)
            print(f"    [{n['id']:>3}] {n['label'][:45]:45s} {bar}")

    # Au-dessus du sol — résumé simple
    above = [n for n in nodes if n.get("depth") is None]
    if above:
        avg_conf = sum(n.get("confidence", 0) for n in above) // len(above) if above else 0
        print(f"\n  🌳 Au-dessus du sol ({len(above)} nœuds)")
        print(f"    Confiance moyenne: {confidence_bar(avg_conf)}")

    print(f"\n{'=' * 60}")


# ============================================================================
# 🛡️ GARDIEN — Protège l'ordre + maintient l'index
# ============================================================================

def load_tree(filepath):
    """Charge un arbre planté depuis un fichier JSON ou depuis le dict."""
    if isinstance(filepath, dict):
        return filepath

    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_tree_json(tree, filepath=None):
    """Sauvegarde l'arbre en JSON pour persistance entre sessions."""
    if filepath is None:
        name_slug = tree["idea"].lower()
        for char in " /'\"()[]{}!?,;:":
            name_slug = name_slug.replace(char, "-")
        name_slug = name_slug[:50].strip("-")
        filepath = f"scans/{name_slug}.json"

    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else "scans", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(tree, f, indent=2, ensure_ascii=False)
    return filepath


def guardian_check(tree, target_node_id):
    """🛡️ GARDIEN — Vérifie si on peut travailler sur un nœud.

    Avant de coder quoi que ce soit, le gardien vérifie :
    1. Est-ce que les dépendances du nœud sont satisfaites ?
    2. Est-ce que l'ordre de construction de la famille est respecté ?
    3. Est-ce qu'on saute pas des niveaux ?

    Returns:
        dict avec:
        - ok: bool — peut-on travailler sur ce nœud ?
        - warnings: list — avertissements non-bloquants
        - blockers: list — blocages (nœuds manquants)
        - recommendation: str — ce qu'il faudrait faire à la place
    """
    nodes = tree["nodes"]
    family_id = tree["family"]
    family = FAMILIES[family_id]

    target = None
    for n in nodes:
        if n["id"] == target_node_id:
            target = n
            break

    if target is None:
        return {
            "ok": False,
            "warnings": [],
            "blockers": [f"Nœud '{target_node_id}' introuvable dans l'arbre"],
            "recommendation": f"Nœuds disponibles : {', '.join(n['id'] for n in nodes)}"
        }

    result = {"ok": True, "warnings": [], "blockers": [], "recommendation": ""}

    # --- CHECK 1 : Dépendances directes ---
    if target.get("depends"):
        for dep_id in target["depends"]:
            dep = next((n for n in nodes if n["id"] == dep_id), None)
            if dep and dep["status"] != "done":
                result["blockers"].append(
                    f"⛔ {target_node_id} dépend de {dep_id} ({dep['label']}) — status: {dep['status']}"
                )

    # --- CHECK 2 : Ordre des niveaux (racines avant tronc, tronc avant branches) ---
    level_priority = {"R": 0, "T": 1, "B": 2, "b": 3, "F": 4, "C": 5}
    target_priority = level_priority.get(target["level"], 99)

    # Vérifier que les niveaux inférieurs ont au moins UN nœud done
    for level_char, priority in level_priority.items():
        if priority < target_priority:
            level_nodes = [n for n in nodes if n["level"] == level_char]
            if level_nodes:
                done_count = sum(1 for n in level_nodes if n["status"] == "done")
                if done_count == 0:
                    level_names = {"R": "Racines", "T": "Tronc", "B": "Branches", "b": "Rameaux", "F": "Feuilles", "C": "Cime"}
                    result["warnings"].append(
                        f"⚠️ Aucun nœud {level_names.get(level_char, level_char)} n'est done — "
                        f"tu construis {target_node_id} ({target['level']}) avant les {level_names.get(level_char, level_char).lower()}"
                    )

    # --- CHECK 3 : Profondeur des racines ---
    target_depth = target.get("depth")
    if target_depth is not None:
        # Vérifier que les racines plus profondes existent
        deeper_roots = [n for n in nodes if n.get("depth") is not None
                       and n["depth"] < target_depth and n["status"] == "todo"]
        if deeper_roots:
            result["warnings"].append(
                f"⚠️ Des racines plus profondes sont encore todo : "
                f"{', '.join(n['id'] for n in deeper_roots[:3])}"
            )

    # --- CHECK 4 : Règles spécifiques à la famille ---
    if family_id == "palmier" and target["level"] == "B":
        result["warnings"].append(
            "⚠️ PALMIER : pas de branches ! Un palmier a un tronc et des feuilles, jamais de branches."
        )

    if family_id == "conifere" and target["level"] == "B":
        trunk_nodes = [n for n in nodes if n["level"] == "T"]
        trunk_done = any(n["status"] == "done" for n in trunk_nodes)
        if not trunk_done:
            result["blockers"].append(
                "⛔ CONIFÈRE : le tronc (pipeline) DOIT être done avant de toucher aux branches. "
                "Contrôle apical = le leader d'abord."
            )

    if family_id == "baobab" and target["level"] in ("B", "b", "F"):
        trunk_nodes = [n for n in nodes if n["level"] == "T"]
        trunk_done = all(n["status"] == "done" for n in trunk_nodes)
        if not trunk_done:
            result["warnings"].append(
                "⚠️ BAOBAB : consolider le tronc avant d'étendre. "
                "Le core doit être solide avant les branches."
            )

    if family_id == "buisson":
        # Vérifier LOW_INVESTMENT_PER_STEM
        stem_nodes = [n for n in nodes if n["level"] == "B"]
        if len(stem_nodes) > 9:
            result["warnings"].append(
                f"⚠️ BUISSON : {len(stem_nodes)} tiges — le max recommandé est 9. "
                "Trop dense = risque d'étouffement."
            )

    # --- VERDICT ---
    if result["blockers"]:
        result["ok"] = False
        # Trouver quoi faire à la place
        todo_roots = [n for n in nodes if n["level"] == "R" and n["status"] == "todo"]
        todo_trunk = [n for n in nodes if n["level"] == "T" and n["status"] == "todo"]
        if todo_roots:
            result["recommendation"] = f"Commence par les racines : {todo_roots[0]['id']} — {todo_roots[0]['label']}"
        elif todo_trunk:
            result["recommendation"] = f"Commence par le tronc : {todo_trunk[0]['id']} — {todo_trunk[0]['label']}"
        else:
            result["recommendation"] = f"Résous d'abord les dépendances bloquantes."
    else:
        result["recommendation"] = f"✅ OK — tu peux travailler sur {target_node_id}"

    return result


def guardian_update(tree, node_id, status=None, entry=None, desc=None, confidence=None):
    """Met à jour un nœud de l'arbre (status, entry, description, confidence).

    Le champ `entry` est LA boussole de Claude dans le code.
    Format : "fichier:ligne:fonction" ou "fichier:ligne"
    Exemple : "lib/mic_engine.dart:340:matchNote()"

    Le champ `confidence` (0-100) indique le taux de connaissance :
    - 0-30  🔴 deep research obligatoire
    - 31-70 🟡 deep research recommandée
    - 71-100 🟢 prêt à coder

    Returns:
        Le nœud mis à jour, ou None si introuvable.
    """
    for n in tree["nodes"]:
        if n["id"] == node_id:
            if status is not None:
                old_status = n["status"]
                n["status"] = status
                _update_phase(tree)
                print(f"  📝 {node_id} : {old_status} → {status}")

            if entry is not None:
                n["entry"] = entry
                print(f"  📍 {node_id} entry → {entry}")

            if desc is not None:
                n["desc"] = desc

            if confidence is not None:
                old_conf = n.get("confidence", 0)
                n["confidence"] = confidence
                bar = confidence_bar(confidence)
                print(f"  📊 {node_id} confiance : {old_conf}% → {bar}")

            return n

    print(f"  ❌ Nœud {node_id} introuvable")
    return None


def _update_phase(tree):
    """Met à jour la phase du projet en fonction des status."""
    nodes = tree["nodes"]
    total = len(nodes)
    done = sum(1 for n in nodes if n["status"] == "done")
    wip = sum(1 for n in nodes if n["status"] == "wip")

    roots_done = all(n["status"] == "done" for n in nodes if n["level"] == "R")
    trunk_done = all(n["status"] == "done" for n in nodes if n["level"] == "T")
    all_done = all(n["status"] == "done" for n in nodes)

    if all_done:
        tree["phase"] = "MATURE"
    elif trunk_done:
        tree["phase"] = "CROISSANCE"
    elif roots_done:
        tree["phase"] = "JEUNE POUSSE"
    elif done > 0 or wip > 0:
        tree["phase"] = "GERMINATION"
    else:
        tree["phase"] = "GRAINE"


def guardian_session_report(tree):
    """🛡️ Rapport de session — à exécuter au début de chaque conversation.

    Affiche :
    - Phase du projet
    - Santé de l'arbre (niveaux couverts/manquants)
    - Prochains pas recommandés
    - Index des entrées code (la carte pour Claude)
    """
    nodes = tree["nodes"]
    family_id = tree["family"]
    fam = FAMILIES[family_id]

    total = len(nodes)
    done = sum(1 for n in nodes if n["status"] == "done")
    wip = sum(1 for n in nodes if n["status"] == "wip")
    todo = sum(1 for n in nodes if n["status"] == "todo")

    _update_phase(tree)

    print(f"\n{'=' * 60}")
    print(f"  🛡️ GARDIEN — Rapport de session")
    print(f"{'=' * 60}")
    print(f"  Projet  : {tree['idea']}")
    print(f"  Famille : {fam['emoji']} {fam['nom']} ({fam['forme']})")
    print(f"  Phase   : {tree['phase']}")
    scale = tree.get("scale")
    if scale:
        print(f"  Taille  : {scale['label']} (×{scale['factor']})")
    print(f"  Nœuds   : {done}✅ {wip}🔨 {todo}🔴 / {total} total")

    # Barre de progression
    bar_len = 40
    done_bars = int((done / total) * bar_len) if total > 0 else 0
    wip_bars = int((wip / total) * bar_len) if total > 0 else 0
    todo_bars = bar_len - done_bars - wip_bars
    bar = "█" * done_bars + "▓" * wip_bars + "░" * todo_bars
    pct = int((done / total) * 100) if total > 0 else 0
    print(f"  [{bar}] {pct}%")

    # Santé par niveau
    print(f"\n  --- Santé par niveau ---")
    level_order = [
        ("R", -5, "🔬 Mycorhizes"),
        ("R", -4, "⚖️  Poils abs."),
        ("R", -3, "💰 Radicelles"),
        ("R", -2, "⚓ Pivotantes"),
        ("R", -1, "🔧 Structurelles"),
        ("T", None, "🏗️  Tronc"),
        ("B", None, "🪵 Branches"),
        ("b", None, "🌿 Rameaux"),
        ("F", None, "🍃 Feuilles"),
        ("C", None, "🌱 Cime"),
    ]

    for level_char, depth, label in level_order:
        if depth is not None:
            lvl_nodes = [n for n in nodes if n["level"] == level_char and n.get("depth") == depth]
        else:
            lvl_nodes = [n for n in nodes if n["level"] == level_char and n.get("depth") is None]

        if not lvl_nodes:
            # Check if level was expected
            if level_char == "T" and family_id != "buisson":
                print(f"    {label:20s}  ⬜ absent")
            continue

        d = sum(1 for n in lvl_nodes if n["status"] == "done")
        w = sum(1 for n in lvl_nodes if n["status"] == "wip")
        t = sum(1 for n in lvl_nodes if n["status"] == "todo")
        total_lvl = len(lvl_nodes)

        if d == total_lvl:
            icon = "✅"
        elif t == total_lvl:
            icon = "🔴"
        else:
            icon = "🔨"
        print(f"    {label:20s}  {icon} {d}/{total_lvl} done")

    # Prochains pas (nœuds todo triés par priorité de construction)
    print(f"\n  --- Prochains pas recommandés ---")
    build_order = tree.get("build_order", [])
    shown = 0
    for step in build_order:
        step_nodes = [n for n in nodes if n["id"] in step["ids"] and n["status"] == "todo"]
        if step_nodes and shown < 3:
            print(f"    Phase {step['phase']} : {step['name']}")
            for n in step_nodes[:3]:
                print(f"      🔴 [{n['id']}] {n['label']}")
            shown += 1

    if shown == 0:
        wip_nodes = [n for n in nodes if n["status"] == "wip"]
        if wip_nodes:
            print(f"    Terminer les WIP :")
            for n in wip_nodes[:3]:
                print(f"      🔨 [{n['id']}] {n['label']}")
        else:
            print(f"    🌳 Tout est done ! L'arbre est mature.")

    # Index code (entrées non-vides)
    entries = [(n["id"], n["label"], n.get("entry", "~")) for n in nodes if n.get("entry") and n["entry"] != "~"]
    if entries:
        print(f"\n  --- Index code (carte pour Claude) ---")
        for nid, label, entry in entries:
            print(f"    [{nid:>3}] {entry}")
            print(f"          └─ {label}")
    else:
        print(f"\n  --- Index code ---")
        print(f"    (vide — les entrées se rempliront au fur et à mesure du dev)")

    print(f"\n{'=' * 60}")

    return {
        "phase": tree["phase"],
        "progress": f"{done}/{total}",
        "pct": pct,
        "entries": len(entries),
    }


def guardian_find(tree, query):
    """🔍 Cherche dans l'arbre — par ID, label, ou entry.

    Claude utilise ça pour trouver où aller dans le code.
    Sky utilise ça pour trouver un nœud par mot-clé.

    Returns:
        Liste de nœuds matchés.
    """
    query_lower = query.lower()
    results = []

    for n in tree["nodes"]:
        score = 0
        # Match exact ID
        if n["id"].lower() == query_lower:
            score = 100
        # Match in label
        elif query_lower in n.get("label", "").lower():
            score = 50
        # Match in entry
        elif query_lower in n.get("entry", "").lower():
            score = 40
        # Match in desc
        elif query_lower in n.get("desc", "").lower():
            score = 30

        if score > 0:
            results.append((score, n))

    results.sort(key=lambda x: -x[0])
    return [n for _, n in results]


def print_guardian_check(result):
    """Affiche le résultat d'un guardian_check de manière lisible."""
    if result["ok"]:
        print(f"\n  ✅ {result['recommendation']}")
    else:
        print(f"\n  ⛔ BLOQUÉ")

    if result["blockers"]:
        print(f"\n  Blocages :")
        for b in result["blockers"]:
            print(f"    {b}")

    if result["warnings"]:
        print(f"\n  Avertissements :")
        for w in result["warnings"]:
            print(f"    {w}")

    if not result["ok"]:
        print(f"\n  💡 Recommandation : {result['recommendation']}")


def export_knowledge_base(filepath="winter_tree_kb.json"):
    """Exporte toute la knowledge base en JSON."""
    data = {
        "version": "1.1",
        "date": datetime.now().isoformat(),
        "source": "Winter Tree Engine",
        "references": {
            "lindenmayer_1968": {
                "author": "Aristid Lindenmayer",
                "year": 1968,
                "title": "Mathematical models for cellular interactions in development",
                "journal": "Journal of Theoretical Biology",
                "volume": 18,
                "pages": "280-315",
                "concept": "L-Systems — parallel string rewriting for plant growth"
            },
            "prusinkiewicz_1990": {
                "authors": ["Przemyslaw Prusinkiewicz", "Aristid Lindenmayer"],
                "year": 1990,
                "title": "The Algorithmic Beauty of Plants",
                "publisher": "Springer",
                "concept": "Turtle graphics interpretation of L-systems"
            },
            "tomer_schach_2000": {
                "authors": ["Amir Tomer", "Stephen R. Schach"],
                "year": 2000,
                "title": "The Evolution Tree: A Maintenance-Oriented Software Development Model",
                "venue": "CSMR 2000, Zurich",
                "concept": "Software development as tree of engineering decisions"
            },
            "fowler_2004": {
                "author": "Martin Fowler",
                "year": 2004,
                "title": "Strangler Fig Application",
                "url": "https://martinfowler.com/bliki/StranglerFigApplication.html",
                "concept": "Gradual legacy system replacement inspired by strangler figs"
            },
            "barnes_2013": {
                "author": "Jeffrey M. Barnes",
                "year": 2013,
                "title": "Software Architecture Evolution",
                "institution": "Carnegie Mellon University",
                "ref": "CMU-ISR-13-118",
                "concept": "Evolution paths as graph of architectural states"
            }
        },
        "families": FAMILIES,
        "anatomy": ANATOMY,
        "bio_ratios": BIO_RATIOS,
        "family_root_types": FAMILY_ROOT_TYPES
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return filepath


# ============================================================================
# CLI — Interface en ligne de commande
# ============================================================================

def print_family(family_id):
    """Affiche les détails d'une famille."""
    fam = FAMILIES[family_id]
    print(f"\n{fam['emoji']} {fam['nom'].upper()} — {fam['forme']}")
    print(f"{'=' * 50}")
    print(f"\n{fam['desc']}")
    print(f"\nQuand l'utiliser : {fam['quand']}")
    print(f"Exemples : {fam['exemples']}")
    print(f"\n--- RÈGLES DE CROISSANCE ---")
    for rule_id, rule in fam["regles"].items():
        print(f"\n  {rule_id}")
        print(f"    Règle : {rule['desc']}")
        print(f"    Bio   : {rule['bio']}")
        print(f"    ⚠️     : {rule['violation']}")
    print(f"\n--- RISQUES ---")
    for r in fam["risques"]:
        print(f"  - {r}")


def print_all_families():
    """Affiche un résumé de toutes les familles."""
    print("\n" + "=" * 60)
    print("  🌲 LES 6 FAMILLES D'ARBRES")
    print("=" * 60)
    for fid, fam in FAMILIES.items():
        print(f"\n  {fam['emoji']} {fam['nom']:10s} | {fam['forme']:20s} | {fam['quand']}")


# ============================================================================
# 🖼️ RENDERER — Vue profil (Planche II) + serveur local
# ============================================================================

# Mapping famille → fichier image dans assets/
FAMILY_IMAGE_MAP = {
    "conifere": "winter_tree_planche_II.png",
    "baobab":   "winter_tree_planche_III_baobab.png",
    "feuillu":  "winter_tree_planche_IV_chene.png",
    "buisson":  "winter_tree_planche_V_buisson.png",
    "liane":    "winter_tree_planche_VI_liane.png",
    "palmier":  "winter_tree_planche_VII_palmier.png",
}

# Positions Y des niveaux sur l'image Planche II (922×1244px)
LEVEL_Y_MAP = {
    "C":  {"y": 100, "label": "CIME",             "color": "#28c862", "zone": "aerial"},
    "F":  {"y": 215, "label": "FEUILLES",          "color": "#32b555", "zone": "aerial"},
    "b":  {"y": 330, "label": "RAMEAUX",            "color": "#38a048", "zone": "aerial"},
    "B":  {"y": 440, "label": "BRANCHES",           "color": "#3d8a3a", "zone": "aerial"},
    "T":  {"y": 530, "label": "TRONC",              "color": "#5a9a35", "zone": "aerial"},
    # SOL = 575
    "R-1": {"y": 650, "label": "R.STRUCTURELLES",   "color": "#9a7453", "zone": "underground"},
    "R-2": {"y": 760, "label": "R.PIVOTANTES",      "color": "#8a6344", "zone": "underground"},
    "R-3": {"y": 870, "label": "RADICELLES",        "color": "#7a5235", "zone": "underground"},
    "R-4": {"y": 960, "label": "POILS ABSORBANTS",  "color": "#6b4226", "zone": "underground"},
    "R-5": {"y": 1060, "label": "MYCORHIZES",       "color": "#5c3317", "zone": "underground"},
}


def _node_level_key(node):
    """Convertit un noeud en clé pour LEVEL_Y_MAP."""
    level = node.get("level", "")
    depth = node.get("depth")
    if level == "R" and depth is not None:
        return f"R{depth}"
    if level == "M":
        return "R-5"
    return level


def _generate_profile_html(tree, image_base64):
    """Génère le HTML de la vue profil d'un arbre avec la Planche II en fond."""

    project_name = tree.get("idea", "Projet").replace("[scanned] ", "")
    family = tree.get("family_name", "Inconnu")
    family_emoji = tree.get("family_emoji", "🌳")
    scale = tree.get("scale", {})
    stats = tree.get("stats", {})
    nodes = tree.get("nodes", [])

    # Grouper les nodes par niveau
    level_groups = {}
    for node in nodes:
        key = _node_level_key(node)
        if key not in level_groups:
            level_groups[key] = []
        level_groups[key].append(node)

    # Générer les éléments SVG pour chaque node
    svg_nodes = []
    center_x = 461  # Centre de l'image

    for level_key, level_info in LEVEL_Y_MAP.items():
        y = level_info["y"]
        color = level_info["color"]
        label = level_info["label"]
        zone = level_info["zone"]

        group_nodes = level_groups.get(level_key, [])

        # Label du niveau à gauche
        opacity = "0.9" if zone == "aerial" else "0.8"
        svg_nodes.append(f'''
        <text x="38" y="{y}" fill="{color}" font-size="12" font-weight="600"
              font-family="JetBrains Mono, monospace" opacity="{opacity}"
              filter="url(#textShadow)">{label}</text>''')

        if not group_nodes:
            # Niveau vide — cercle gris discret
            svg_nodes.append(f'''
        <circle cx="{center_x}" cy="{y}" r="3" fill="#333" opacity="0.3"/>''')
            continue

        # Distribuer les nodes sur l'axe si plusieurs au même niveau
        n_count = len(group_nodes)
        for i, node in enumerate(group_nodes):
            # Offset Y pour éviter les chevauchements (±15px par node supplémentaire)
            offset_y = (i - (n_count - 1) / 2) * 24
            ny = y + offset_y

            status = node.get("status", "todo")
            confidence = node.get("confidence", 0)
            node_id = node.get("id", "?")
            node_label = node.get("label", "")
            entry = node.get("entry", "~")

            # Couleur du node selon status
            if status == "done":
                fill = color
                inner_fill = "#fff"
                inner_opacity = "0.8"
            elif status == "wip":
                fill = "#FFB74D"
                inner_fill = "#fff"
                inner_opacity = "0.6"
            else:
                fill = "#FF5252"
                inner_fill = "#FF5252"
                inner_opacity = "0.4"

            # Taille selon confidence
            radius = 5 + (confidence / 100) * 3  # 5-8px

            # Node circle avec glow
            svg_nodes.append(f'''
        <g class="node-group" data-id="{node_id}" data-status="{status}"
           data-confidence="{confidence}">
          <circle cx="{center_x}" cy="{ny}" r="{radius:.0f}" fill="{fill}"
                  opacity="0.85" filter="url(#nodeGlow)"/>
          <circle cx="{center_x}" cy="{ny}" r="{radius/2.5:.1f}" fill="{inner_fill}"
                  opacity="{inner_opacity}"/>''')

            # Ligne de connexion + texte descriptif à droite
            # Tronquer le label pour l'affichage
            display_label = node_label[:50]
            if len(node_label) > 50:
                display_label += "…"

            # Status icon
            status_icon = {"done": "✓", "wip": "◐", "todo": "○"}.get(status, "?")

            # Confidence bar compacte
            conf_width = 40
            conf_filled = int((confidence / 100) * conf_width)

            svg_nodes.append(f'''
          <line x1="{center_x + radius + 2}" y1="{ny}" x2="530" y2="{ny}"
                stroke="{color}" stroke-width="0.7" opacity="0.35" stroke-dasharray="3,3"/>
          <text x="538" y="{ny - 3}" fill="{color}" font-size="10" font-weight="400"
                font-family="JetBrains Mono, monospace" opacity="0.85"
                filter="url(#textShadow)">{status_icon} {node_id} {display_label}</text>
          <rect x="538" y="{ny + 3}" width="{conf_width}" height="3" rx="1.5"
                fill="#1a1a1a" opacity="0.6"/>
          <rect x="538" y="{ny + 3}" width="{conf_filled}" height="3" rx="1.5"
                fill="{fill}" opacity="0.6"/>
          <text x="{538 + conf_width + 6}" y="{ny + 8}" fill="{color}" font-size="8"
                font-family="JetBrains Mono, monospace" opacity="0.5"
                filter="url(#textShadow)">{confidence}%</text>
        </g>''')

    # Assembler le SVG complet
    svg_content = "\n".join(svg_nodes)

    # Stats pour le panneau info
    total_lines = stats.get("total_code_lines", 0)
    total_files = stats.get("total_files", 0)
    data_mb = stats.get("data_weight_mb", 0)
    scale_label = scale.get("label", "")
    done_count = sum(1 for n in nodes if n.get("status") == "done")
    wip_count = sum(1 for n in nodes if n.get("status") == "wip")
    todo_count = sum(1 for n in nodes if n.get("status") == "todo")

    html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Winter Tree — {project_name}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600&display=swap');

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    background: #050805;
    color: #EDE5DB;
    font-family: 'JetBrains Mono', monospace;
    display: flex;
    min-height: 100vh;
  }}

  .sidebar {{
    width: 280px;
    min-width: 280px;
    background: #0a0d08;
    border-right: 1px solid rgba(255,255,255,0.06);
    padding: 24px 16px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 20px;
  }}

  .sidebar h1 {{
    font-size: 14px;
    letter-spacing: 4px;
    text-transform: uppercase;
    color: #8B6914;
    font-weight: 400;
  }}

  .sidebar h2 {{
    font-size: 20px;
    font-weight: 300;
    letter-spacing: 2px;
    color: #EDE5DB;
  }}

  .stat-block {{
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.04);
    border-radius: 6px;
    padding: 12px;
  }}

  .stat-block .label {{
    font-size: 9px;
    letter-spacing: 2px;
    text-transform: uppercase;
    opacity: 0.4;
    margin-bottom: 6px;
  }}

  .stat-block .value {{
    font-size: 16px;
    font-weight: 300;
  }}

  .stat-row {{
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
    font-size: 11px;
    opacity: 0.7;
    border-bottom: 1px solid rgba(255,255,255,0.03);
  }}

  .status-badge {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
  }}

  .status-done {{ background: rgba(40,200,98,0.15); color: #28c862; }}
  .status-wip {{ background: rgba(255,183,77,0.15); color: #FFB74D; }}
  .status-todo {{ background: rgba(255,82,82,0.15); color: #FF5252; }}

  .tree-container {{
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    overflow: auto;
  }}

  .tree-wrapper {{
    position: relative;
    width: 922px;
    height: 1244px;
    flex-shrink: 0;
  }}

  .tree-wrapper img {{
    width: 100%;
    height: 100%;
    display: block;
    border-radius: 4px;
  }}

  .tree-overlay {{
    position: absolute;
    top: 0; left: 0;
    width: 100%; height: 100%;
  }}

  .node-group {{ pointer-events: all; cursor: default; }}
  .node-group:hover circle {{ filter: url(#nodeGlowStrong); }}

  .footer {{
    margin-top: auto;
    font-size: 9px;
    opacity: 0.25;
    letter-spacing: 2px;
    text-align: center;
  }}
</style>
</head>
<body>

<div class="sidebar">
  <div>
    <a href="/forest" style="text-decoration:none; color:#8B6914; font-size:10px;
       letter-spacing:2px; opacity:0.6; display:block; margin-bottom:12px;">← LA FORÊT</a>
    <h1>Winter Tree</h1>
    <h2>{family_emoji} {project_name}</h2>
  </div>

  <div class="stat-block">
    <div class="label">Famille</div>
    <div class="value">{family}</div>
  </div>

  <div class="stat-block">
    <div class="label">Échelle</div>
    <div class="value">{scale_label}</div>
  </div>

  <div class="stat-block">
    <div class="label">Code</div>
    <div class="value">{total_lines:,} lignes</div>
    <div class="stat-row"><span>Fichiers</span><span>{total_files}</span></div>
    <div class="stat-row"><span>Data</span><span>{data_mb:.0f} Mo</span></div>
  </div>

  <div class="stat-block">
    <div class="label">Nœuds ({len(nodes)})</div>
    <div style="display: flex; gap: 8px; margin-top: 6px; flex-wrap: wrap;">
      <span class="status-badge status-done">✓ {done_count}</span>
      <span class="status-badge status-wip">◐ {wip_count}</span>
      <span class="status-badge status-todo">○ {todo_count}</span>
    </div>
  </div>

  <div class="stat-block">
    <div class="label">Langages</div>
    {"".join(f'<div class="stat-row"><span>{lang}</span><span>{lines:,}L</span></div>' for lang, lines in sorted(stats.get("languages", {}).items(), key=lambda x: -x[1])[:6])}
  </div>

  <div class="footer">
    racines &gt; arbre — 2026
  </div>
</div>

<div class="tree-container">
  <div class="tree-wrapper">
    <img src="data:image/png;base64,{image_base64}" alt="Winter Tree Planche II"/>

    <svg class="tree-overlay" viewBox="0 0 922 1244" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3" result="blur"/>
          <feComposite in="SourceGraphic" in2="blur" operator="over"/>
        </filter>
        <filter id="nodeGlow" x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur stdDeviation="5" result="blur"/>
          <feComposite in="SourceGraphic" in2="blur" operator="over"/>
        </filter>
        <filter id="nodeGlowStrong" x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur stdDeviation="10" result="blur"/>
          <feComposite in="SourceGraphic" in2="blur" operator="over"/>
        </filter>
        <filter id="textShadow" x="-10%" y="-10%" width="120%" height="120%">
          <feDropShadow dx="0" dy="0" stdDeviation="4" flood-color="#000" flood-opacity="0.9"/>
        </filter>
      </defs>

      <!-- Axe central -->
      <line x1="{center_x}" y1="60" x2="{center_x}" y2="1100"
            stroke="rgba(139,105,20,0.15)" stroke-width="1" stroke-dasharray="6,4"/>

      <!-- SOL label -->
      <text x="860" y="580" fill="#8B6914" font-size="11" font-weight="600"
            font-family="JetBrains Mono, monospace" opacity="0.7"
            text-anchor="end" filter="url(#textShadow)">SOL</text>

      <!-- Nodes -->
      {svg_content}

      <!-- Footer -->
      <text x="461" y="1170" text-anchor="middle" fill="#555" font-size="10"
            font-family="JetBrains Mono, monospace" letter-spacing="3" opacity="0.4">
        WINTER TREE ENGINE v1 — {project_name}
      </text>
      <text x="461" y="1190" text-anchor="middle" fill="#444" font-size="8"
            font-family="JetBrains Mono, monospace" letter-spacing="2" opacity="0.3">
        racines toujours &gt; arbre — sky1241 — 2026
      </text>
    </svg>
  </div>
</div>

</body>
</html>'''

    return html


def scan_github_repo(owner, repo_name, token=None):
    """🌐 Scanne un repo GitHub distant via l'API (sans cloner).

    Utilise l'API GitHub pour :
    - Récupérer l'arbre de fichiers complet
    - Les langages et leur répartition
    - Les métadonnées du repo

    Args:
        owner: nom d'utilisateur GitHub
        repo_name: nom du repo
        token: (optionnel) token GitHub pour repos privés

    Returns:
        dict — arbre Winter Tree
    """
    import urllib.request
    import urllib.error

    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "WinterTree/1.0"}
    if token:
        headers["Authorization"] = f"token {token}"

    def api_get(url):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 403:
                print(f"  ⚠️ Rate limit GitHub — attendez ou utilisez un token")
            elif e.code == 404:
                print(f"  ⚠️ Repo non trouvé : {owner}/{repo_name}")
            return None
        except Exception as e:
            print(f"  ⚠️ Erreur API : {e}")
            return None

    # ── Métadonnées du repo ──
    repo_info = api_get(f"https://api.github.com/repos/{owner}/{repo_name}")
    if not repo_info:
        return None

    default_branch = repo_info.get("default_branch", "main")
    description = repo_info.get("description", "") or ""
    repo_size_kb = repo_info.get("size", 0)

    # ── Langages ──
    languages = api_get(f"https://api.github.com/repos/{owner}/{repo_name}/languages") or {}

    # Convertir bytes → lignes approximatives (1 ligne ≈ 40 bytes)
    lang_lines = {lang: max(1, bytes_count // 40) for lang, bytes_count in languages.items()}
    total_code_lines = sum(lang_lines.values())

    # ── Arbre de fichiers ──
    tree_data = api_get(f"https://api.github.com/repos/{owner}/{repo_name}/git/trees/{default_branch}?recursive=1")

    all_files = []
    all_dirs = set()
    biggest_file = {"path": "", "lines": 0, "lang": ""}

    if tree_data and "tree" in tree_data:
        for item in tree_data["tree"]:
            path = item.get("path", "")
            item_type = item.get("type", "")
            size = item.get("size", 0) or 0

            # Filtrer les dossiers ignorés
            parts = path.split("/")
            if any(p in IGNORE for p in parts):
                continue

            if item_type == "tree":
                all_dirs.add(path)
            elif item_type == "blob":
                ext = os.path.splitext(path)[1].lower()
                lang = EXT_LANG.get(ext, "")
                # Estimer les lignes depuis la taille
                lines = max(1, size // 40) if ext in EXT_LANG else 0

                all_files.append({
                    "path": path,
                    "name": os.path.basename(path),
                    "ext": ext,
                    "size": size,
                    "lines": lines,
                    "lang": lang,
                })

                if lines > biggest_file["lines"]:
                    biggest_file = {"path": path, "lines": lines, "lang": lang}

    # Guard : si l'API tree a échoué (rate limit), pas de fichiers = scan inutile
    # On retourne None pour que sync_all conserve l'ancien scan
    if not all_files:
        print(f"  ⚠️ Aucun fichier récupéré pour {repo_name} (rate limit probable)")
        return None

    # ── Construire les nœuds (même logique que scan_repo) ──
    nodes = []
    node_id_counter = {"M": 0, "P": 0, "D": 0, "A": 0, "R": 0,
                       "T": 0, "B": 0, "b": 0, "F": 0, "C": 0}
    found_patterns = set()

    def add_node(prefix, level, depth, label, entry="~", status="done", confidence=0):
        node_id_counter[prefix] = node_id_counter.get(prefix, 0) + 1
        nid = f"{prefix}{node_id_counter[prefix]}"
        if confidence == 0 and status == "done":
            confidence = 80
        node = {
            "id": nid, "level": level, "label": label,
            "status": status, "entry": entry, "depends": [], "desc": "",
            "confidence": confidence,
        }
        if depth is not None:
            node["depth"] = depth
        nodes.append(node)
        return nid

    # Scan patterns
    for category, patterns in SCAN_PATTERNS.items():
        for pattern, info in patterns.items():
            if info.get("skip_node"):
                continue
            matched = False
            entry = "~"
            if info.get("is_dir"):
                dir_name = pattern.rstrip("/")
                if dir_name in all_dirs or any(d.startswith(dir_name) for d in all_dirs):
                    matched = True
                    entry = dir_name + "/"
            elif info.get("ext_match"):
                ext = pattern
                if any(f["ext"] == ext for f in all_files):
                    matched = True
            else:
                if any(f["name"] == pattern or f["path"] == pattern for f in all_files):
                    matched = True
                    entry = pattern
            if matched and pattern not in found_patterns:
                found_patterns.add(pattern)
                depth = info.get("depth")
                label = info["label"]
                if depth == -1:
                    add_node("R", "R", -1, label, entry)
                elif depth == -2:
                    add_node("A", "R", -2, label, entry)
                elif depth == -4:
                    add_node("P", "R", -4, label, entry)
                elif category == "cime":
                    add_node("C", "C", None, label, entry)

    # Langages → mycorhizes
    if lang_lines:
        main_lang = max(lang_lines, key=lang_lines.get)
        add_node("M", "R", -5, f"Langage principal : {main_lang} ({lang_lines[main_lang]} lignes)")
        for lang, lines in sorted(lang_lines.items(), key=lambda x: -x[1])[1:3]:
            if lines > total_code_lines * 0.1:
                add_node("M", "R", -5, f"Langage secondaire : {lang} ({lines} lignes)")

    # Tronc
    if biggest_file["lines"] > 0:
        add_node("T", "T", None,
                 f"Core : {biggest_file['path']} (~{biggest_file['lines']}L, {biggest_file['lang']})",
                 biggest_file["path"])

    # Branches = dossiers de premier niveau
    top_dirs = {}
    for f in all_files:
        parts = f["path"].split("/")
        if len(parts) > 1 and f["lines"] > 0:
            top_dir = parts[0]
            if top_dir not in IGNORE:
                if top_dir not in top_dirs:
                    top_dirs[top_dir] = {"files": 0, "lines": 0, "langs": set()}
                top_dirs[top_dir]["files"] += 1
                top_dirs[top_dir]["lines"] += f["lines"]
                if f["lang"]:
                    top_dirs[top_dir]["langs"].add(f["lang"])

    for dirname, info in sorted(top_dirs.items(), key=lambda x: -x[1]["lines"])[:10]:
        langs = ", ".join(list(info["langs"])[:2])
        add_node("B", "B", None,
                 f"{dirname}/ ({info['files']}f, ~{info['lines']}L, {langs})",
                 f"{dirname}/")
        # Rameaux
        sub_dirs = {}
        for f in all_files:
            parts = f["path"].split("/")
            if len(parts) > 2 and parts[0] == dirname and f["lines"] > 0:
                sub = parts[1]
                if sub not in sub_dirs:
                    sub_dirs[sub] = {"files": 0, "lines": 0}
                sub_dirs[sub]["files"] += 1
                sub_dirs[sub]["lines"] += f["lines"]
        for subname, subinfo in sorted(sub_dirs.items(), key=lambda x: -x[1]["lines"])[:5]:
            add_node("b", "b", None,
                     f"{dirname}/{subname}/ ({subinfo['files']}f, ~{subinfo['lines']}L)",
                     f"{dirname}/{subname}/")

    # Gaps
    if not any(n["level"] == "C" for n in nodes):
        add_node("C", "C", None, "Tests/CI — ABSENT", "~", "todo")
    if not any(n.get("depth") == -4 for n in nodes):
        add_node("P", "R", -4, "Licence/Legal — ABSENT", "~", "todo")
    has_readme = any(f["name"].lower().startswith("readme") for f in all_files)
    if not has_readme:
        add_node("F", "F", None, "README — ABSENT", "~", "todo")

    # Classifier — on passe all_files pour l'analyse structurelle
    family_id = _classify_from_scan(nodes, top_dirs, biggest_file, total_code_lines, repo_path=None, all_files=all_files)
    domain = detect_domain((description + " " + repo_name + " " + " ".join(f["path"] for f in all_files[:50])).lower())
    build_order = generate_build_order(family_id, nodes)

    data_weight_mb = max(0, (repo_size_kb / 1024) - (total_code_lines * 40 / 1024 / 1024))
    scale = calculate_scale(total_code_lines, data_weight_mb)

    tree = {
        "idea": f"[scanned] {repo_name}",
        "domain": domain,
        "family": family_id,
        "family_name": FAMILIES[family_id]["nom"],
        "family_emoji": FAMILIES[family_id]["emoji"],
        "date": datetime.now().isoformat(),
        "phase": "MATURE",
        "scanned_from": f"https://github.com/{owner}/{repo_name}",
        "scale": scale,
        "stats": {
            "total_files": len(all_files),
            "total_code_lines": total_code_lines,
            "data_weight_mb": round(data_weight_mb, 1),
            "languages": lang_lines,
            "biggest_file": biggest_file,
        },
        "nodes": nodes,
        "build_order": build_order,
        "next_step": "Vérifier l'arbre scanné",
    }
    _update_phase(tree)
    return tree


def scan_github_user(username, token=None, max_repos=20):
    """🌐 Scanne tous les repos d'un utilisateur GitHub.

    Args:
        username: nom d'utilisateur GitHub
        token: (optionnel) token pour repos privés
        max_repos: nombre max de repos à scanner

    Returns:
        list[dict] — liste d'arbres Winter Tree
    """
    import urllib.request
    import urllib.error

    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "WinterTree/1.0"}
    if token:
        headers["Authorization"] = f"token {token}"

    # Lister les repos
    url = f"https://api.github.com/users/{username}/repos?per_page={max_repos}&sort=updated"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            repos = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  ❌ Impossible de lister les repos de {username}: {e}")
        return []

    if not isinstance(repos, list):
        print(f"  ❌ Réponse inattendue de l'API GitHub")
        return []

    # Filtrer les forks (optionnel)
    repos = [r for r in repos if not r.get("fork", False)]

    print(f"\n  🌐 GitHub : {username} — {len(repos)} repos trouvés")
    print(f"  {'─' * 50}")

    trees = []
    for i, repo in enumerate(repos[:max_repos]):
        name = repo["name"]
        print(f"  [{i+1}/{min(len(repos), max_repos)}] Scan de {name}...", end="", flush=True)

        tree = scan_github_repo(username, name, token)
        if tree:
            # Sauvegarder le scan
            script_dir = Path(__file__).parent
            scans_dir = script_dir / "scans"
            scans_dir.mkdir(exist_ok=True)
            filepath = scans_dir / f"{name}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(tree, f, indent=2, ensure_ascii=False)

            lines = tree.get("stats", {}).get("total_code_lines", 0)
            emoji = tree.get("family_emoji", "🌳")
            print(f" {emoji} {lines:,}L ✅")
            trees.append(tree)
        else:
            print(f" ⚠️ skip")

    print(f"\n  {'─' * 50}")
    print(f"  ✅ {len(trees)} arbres scannés et sauvés dans scans/")

    return trees


def _generate_forest_html(trees, image_base64_map):
    """Génère le HTML de la vue forêt — tous les arbres côte à côte."""

    # Trier par taille (plus gros d'abord)
    trees_sorted = sorted(trees, key=lambda t: t.get("stats", {}).get("total_code_lines", 0), reverse=True)

    # Générer les cartes d'arbres
    tree_cards = []
    for tree in trees_sorted:
        name = tree.get("idea", "?").replace("[scanned] ", "")
        family = tree.get("family", "conifere")
        family_name = tree.get("family_name", "Inconnu")
        emoji = tree.get("family_emoji", "🌳")
        scale = tree.get("scale", {})
        stats = tree.get("stats", {})
        nodes = tree.get("nodes", [])
        json_file = tree.get("_json_file", "")

        total_lines = stats.get("total_code_lines", 0)
        data_mb = stats.get("data_weight_mb", 0)
        scale_factor = scale.get("factor", 1.0)
        density = scale.get("density", 1.0)
        category = scale.get("category", "arbre")

        # Dimensions visuelles de l'arbre
        base_height = 180
        tree_height = int(base_height * scale_factor)
        tree_width = int(120 * density)

        # Image de la famille
        img_key = FAMILY_IMAGE_MAP.get(family, "winter_tree_planche_II.png")
        if img_key not in image_base64_map:
            img_key = "winter_tree_planche_II.png"
        img_src = f"/assets/{img_key}"

        # Compteurs status
        done = sum(1 for n in nodes if n.get("status") == "done")
        total = len(nodes)
        health_pct = int((done / total * 100)) if total > 0 else 0

        # Couleur de santé
        if health_pct >= 70:
            health_color = "#28c862"
        elif health_pct >= 40:
            health_color = "#FFB74D"
        else:
            health_color = "#FF5252"

        # Langages principaux
        langs = stats.get("languages", {})
        top_langs = sorted(langs.items(), key=lambda x: -x[1])[:3]
        lang_str = " · ".join(l[0] for l in top_langs) if top_langs else "—"

        tree_cards.append(f'''
      <a href="/tree/{json_file}" class="tree-card" style="--tree-h: {tree_height}px; --tree-w: {tree_width}px;">
        <div class="tree-visual">
          <img src="{img_src}" alt="{family_name}"
               style="height: {tree_height}px; width: {tree_width}px;"/>
        </div>
        <div class="tree-info">
          <div class="tree-name">{emoji} {name}</div>
          <div class="tree-meta">{total_lines:,}L · {data_mb:.0f}Mo · {family_name}</div>
          <div class="tree-langs">{lang_str}</div>
          <div class="tree-health">
            <div class="health-bar">
              <div class="health-fill" style="width: {health_pct}%; background: {health_color};"></div>
            </div>
            <span style="color: {health_color};">{done}/{total}</span>
          </div>
        </div>
      </a>''')

    cards_html = "\n".join(tree_cards)

    # Stats globales
    total_projects = len(trees)
    total_all_lines = sum(t.get("stats", {}).get("total_code_lines", 0) for t in trees)
    total_all_files = sum(t.get("stats", {}).get("total_files", 0) for t in trees)
    total_all_data = sum(t.get("stats", {}).get("data_weight_mb", 0) for t in trees)

    html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Winter Tree — La Forêt</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600&display=swap');

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    background: #050805;
    color: #EDE5DB;
    font-family: 'JetBrains Mono', monospace;
    min-height: 100vh;
  }}

  .header {{
    text-align: center;
    padding: 48px 24px 24px;
    border-bottom: 1px solid rgba(139,105,20,0.15);
  }}

  .header h1 {{
    font-size: 28px;
    font-weight: 300;
    letter-spacing: 10px;
    text-transform: uppercase;
    color: #EDE5DB;
    margin-bottom: 8px;
  }}

  .header .subtitle {{
    font-size: 11px;
    letter-spacing: 4px;
    color: #8B6914;
    opacity: 0.7;
  }}

  .global-stats {{
    display: flex;
    justify-content: center;
    gap: 32px;
    margin-top: 24px;
    flex-wrap: wrap;
  }}

  .global-stat {{
    text-align: center;
  }}

  .global-stat .val {{
    font-size: 20px;
    font-weight: 300;
    color: #EDE5DB;
  }}

  .global-stat .lbl {{
    font-size: 9px;
    letter-spacing: 2px;
    text-transform: uppercase;
    opacity: 0.35;
    margin-top: 4px;
  }}

  .forest-ground {{
    position: relative;
    display: flex;
    align-items: flex-end;
    justify-content: center;
    flex-wrap: wrap;
    gap: 12px;
    padding: 60px 40px 0;
    min-height: 60vh;
  }}

  /* Ligne de sol */
  .forest-ground::after {{
    content: '';
    position: absolute;
    bottom: 0;
    left: 5%;
    right: 5%;
    height: 2px;
    background: linear-gradient(90deg, transparent, #8B6914, transparent);
    opacity: 0.4;
  }}

  .tree-card {{
    display: flex;
    flex-direction: column;
    align-items: center;
    text-decoration: none;
    color: #EDE5DB;
    padding: 8px;
    border-radius: 8px;
    transition: all 0.3s ease;
    cursor: pointer;
    position: relative;
  }}

  .tree-card:hover {{
    background: rgba(139,105,20,0.08);
    transform: translateY(-4px);
  }}

  .tree-card:hover .tree-visual img {{
    filter: brightness(1.2) saturate(1.1);
  }}

  .tree-visual {{
    display: flex;
    align-items: flex-end;
    justify-content: center;
    min-height: 100px;
  }}

  .tree-visual img {{
    object-fit: cover;
    object-position: top center;
    border-radius: 4px;
    filter: brightness(0.9);
    transition: filter 0.3s ease;
  }}

  .tree-info {{
    text-align: center;
    padding: 10px 4px 6px;
    max-width: 160px;
  }}

  .tree-name {{
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 160px;
  }}

  .tree-meta {{
    font-size: 9px;
    opacity: 0.4;
    margin-bottom: 2px;
  }}

  .tree-langs {{
    font-size: 8px;
    opacity: 0.3;
    margin-bottom: 6px;
  }}

  .tree-health {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 9px;
  }}

  .health-bar {{
    flex: 1;
    height: 3px;
    background: rgba(255,255,255,0.06);
    border-radius: 2px;
    overflow: hidden;
    min-width: 50px;
  }}

  .health-fill {{
    height: 100%;
    border-radius: 2px;
    transition: width 0.5s ease;
  }}

  .footer {{
    text-align: center;
    padding: 40px;
    font-size: 9px;
    opacity: 0.2;
    letter-spacing: 3px;
  }}

  /* Sol texturé sous les arbres */
  .soil-zone {{
    width: 100%;
    height: 80px;
    background: linear-gradient(180deg,
      rgba(90,60,30,0.15) 0%,
      rgba(60,35,15,0.25) 50%,
      rgba(40,20,8,0.3) 100%);
    border-top: 2px solid rgba(139,105,20,0.2);
  }}
</style>
</head>
<body>

<div class="header">
  <h1>🌲 La Forêt</h1>
  <div class="subtitle">Winter Tree Engine v1 — vue globale</div>
  <div class="global-stats">
    <div class="global-stat">
      <div class="val">{total_projects}</div>
      <div class="lbl">Projets</div>
    </div>
    <div class="global-stat">
      <div class="val">{total_all_lines:,}</div>
      <div class="lbl">Lignes de code</div>
    </div>
    <div class="global-stat">
      <div class="val">{total_all_files:,}</div>
      <div class="lbl">Fichiers</div>
    </div>
    <div class="global-stat">
      <div class="val">{total_all_data:,.0f} Mo</div>
      <div class="lbl">Données</div>
    </div>
  </div>
</div>

<div class="forest-ground">
  {cards_html}
</div>
<div class="soil-zone"></div>

<div class="footer">
  racines &gt; arbre — sky1241 — 2026
</div>

</body>
</html>'''

    return html


def serve_tree(json_path=None):
    """🌐 Lance un serveur local interactif.

    Sans argument → vue forêt (tous les scans/)
    Avec argument → vue profil interactive (un arbre)
    """
    import http.server
    import socketserver
    import webbrowser
    import base64
    import urllib.parse

    script_dir = Path(__file__).parent
    assets_dir = script_dir / "assets"
    scans_dir = script_dir / "scans"
    templates_dir = script_dir / "templates"

    # ── Charger les images en mémoire (raw bytes pour /assets/) ──
    image_raw = {}
    if assets_dir.exists():
        for img_file in assets_dir.glob("*.png"):
            with open(img_file, "rb") as f:
                image_raw[img_file.name] = f.read()

    if "winter_tree_planche_II.png" not in image_raw:
        print(f"  ❌ Image non trouvée : assets/winter_tree_planche_II.png")
        return

    def get_tree_image_name(tree):
        family_id = tree.get("family", "conifere")
        img = FAMILY_IMAGE_MAP.get(family_id, "winter_tree_planche_II.png")
        if img not in image_raw:
            img = "winter_tree_planche_II.png"
        return img

    # ── Charger les arbres ──
    all_trees = {}
    if scans_dir.exists():
        for jf in scans_dir.glob("*.json"):
            tree = load_tree(str(jf))
            if tree:
                tree["_json_file"] = jf.name
                all_trees[jf.name] = tree

    # ── Charger le template interactif ──
    interactive_tpl = ""
    tpl_path = templates_dir / "interactive_profile.html"
    if tpl_path.exists():
        with open(tpl_path, "r", encoding="utf-8") as f:
            interactive_tpl = f.read()

    # ── Charger le template cube 3D ──
    cube_tpl = ""
    cube_path = templates_dir / "cube_forest.html"
    if cube_path.exists():
        with open(cube_path, "r", encoding="utf-8") as f:
            cube_tpl = f.read()

    # ── Charger le template skeleton export ──
    skeleton_tpl = ""
    skeleton_path = templates_dir / "skeleton_export.html"
    if skeleton_path.exists():
        with open(skeleton_path, "r", encoding="utf-8") as f:
            skeleton_tpl = f.read()

    # ── Charger le template planche overlay ──
    planche_overlay_tpl = ""
    overlay_path = templates_dir / "planche_overlay.html"
    if overlay_path.exists():
        with open(overlay_path, "r", encoding="utf-8") as f:
            planche_overlay_tpl = f.read()

    # ── Générer le HTML forêt (avec base64 pour inline) ──
    image_base64_map = {k: base64.b64encode(v).decode("utf-8") for k, v in image_raw.items()}
    forest_html = _generate_forest_html(list(all_trees.values()), image_base64_map)

    # ── Port dispo ──
    port = 8420
    for attempt in range(20):
        try:
            test_socket = socketserver.TCPServer(("", port + attempt), None)
            test_socket.server_close()
            port = port + attempt
            break
        except OSError:
            continue

    # Si json spécifique
    single_tree = None
    page_title = "La Forêt"
    if json_path:
        single_tree = load_tree(json_path)
        if not single_tree:
            print(f"  ❌ Impossible de charger : {json_path}")
            return
        page_title = single_tree.get("idea", "Projet").replace("[scanned] ", "")

    # ── Handler avec routing ──
    class TreeHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path = urllib.parse.unquote(self.path)

            # Static template files (images)
            if path.startswith("/tpl/"):
                fname = path[5:]
                tpl_file = templates_dir / fname
                if tpl_file.exists() and tpl_file.suffix in (".png", ".jpg", ".jpeg", ".webp"):
                    ct = "image/png" if tpl_file.suffix == ".png" else "image/jpeg"
                    data = tpl_file.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-type", ct)
                    self.send_header("Content-Length", len(data))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self._serve_404(fname)
                return

            # Images: /assets/filename.png
            if path.startswith("/assets/"):
                fname = path[8:]
                if fname in image_raw:
                    self.send_response(200)
                    self.send_header("Content-type", "image/png")
                    self.send_header("Cache-Control", "max-age=3600")
                    self.end_headers()
                    self.wfile.write(image_raw[fname])
                else:
                    self._serve_404(fname)
                return

            # API: tree JSON
            if path.startswith("/api/tree/"):
                fname = path[10:]
                tree = all_trees.get(fname)
                if tree:
                    self._serve_json(tree)
                else:
                    self._serve_404(fname)
                return

            # API: all trees
            if path == "/api/trees":
                trees_list = []
                for fname, t in all_trees.items():
                    trees_list.append({
                        "file": fname,
                        "name": t.get("idea", "?").replace("[scanned] ", ""),
                        "family": t.get("family", "conifere"),
                        "family_name": t.get("family_name", "?"),
                        "family_emoji": t.get("family_emoji", "🌳"),
                        "stats": t.get("stats", {}),
                        "scale": t.get("scale", {}),
                        "nodes_count": len(t.get("nodes", [])),
                        "done": sum(1 for n in t.get("nodes", []) if n.get("status") == "done"),
                        "image": f"/assets/{get_tree_image_name(t)}",
                    })
                self._serve_json({"trees": trees_list})
                return

            # Interactive profile: /tree/filename.json
            if path.startswith("/tree/") and path.endswith(".json"):
                fname = path[6:]
                tree = all_trees.get(fname)
                if tree and interactive_tpl:
                    html = _build_interactive(tree)
                    self._serve_html(html)
                else:
                    self._serve_404(fname)
                return

            # Skeleton export
            if path == "/skeleton-export" and skeleton_tpl:
                self._serve_html(skeleton_tpl)
                return

            # Planche overlay
            if path == "/planche-overlay" and planche_overlay_tpl:
                self._serve_html(planche_overlay_tpl)
                return

            # Cube 3D (dispo sur /cube si besoin)
            if path == "/cube" and cube_tpl:
                self._serve_html(cube_tpl)
                return

            # Root → single tree or forest
            if path == "/" and single_tree and interactive_tpl:
                html = _build_interactive(single_tree)
                self._serve_html(html)
                return

            # Default: forest
            self._serve_html(forest_html)

        def _serve_html(self, html):
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)

        def _serve_json(self, obj):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)

        def _serve_404(self, name):
            self.send_response(404)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h1>404 — {name}</h1>".encode("utf-8"))

        def log_message(self, format, *args):
            pass

    def _build_interactive(tree):
        tree_json = json.dumps(tree, ensure_ascii=False)
        img_name = get_tree_image_name(tree)
        html = interactive_tpl.replace(
            '__TREE_JSON__', tree_json
        ).replace(
            '__IMG_SRC__',
            f'"/assets/{img_name}"'
        )
        return html

    server = socketserver.TCPServer(("", port), TreeHandler)

    n_trees = len(all_trees)
    if single_tree:
        print(f"\n  🌲 WINTER TREE — {page_title}")
    else:
        print(f"\n  🌲 WINTER TREE — La Forêt ({n_trees} arbres)")
    print(f"  {'─' * 40}")
    print(f"  🌐 http://localhost:{port}")
    if not single_tree and n_trees > 0:
        print(f"  🌐 http://localhost:{port}/forest")
        for fname in sorted(all_trees.keys()):
            name = all_trees[fname].get("idea", "?").replace("[scanned] ", "")
            print(f"     └─ /tree/{fname}  ({name})")
    print(f"  Ctrl+C pour arrêter")
    print()

    webbrowser.open(f"http://localhost:{port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  🛑 Serveur arrêté.")
        server.server_close()


def main():
    """Point d'entrée CLI."""
    if len(sys.argv) < 2:
        print("""
🌲 WINTER TREE ENGINE v1.2
==========================

Usage:
  python engine.py serve [json]        🌐 VISUALISE l'arbre dans le navigateur
  python engine.py serve               🌲 FORÊT — tous les scans côte à côte
  python engine.py serve --github <user>  🌐 Scanne GitHub + ouvre la forêt
  python engine.py github <user>       🌐 SCANNE tous les repos GitHub d'un user
  python engine.py github <user/repo>  🌐 SCANNE un repo GitHub spécifique
  python engine.py plant "<idée>"     🌱 PLANTE UN ARBRE à partir d'une idée
  python engine.py scan <dossier>     🔬 SCANNE un repo existant
  python engine.py research <json> [contexte]  🔍 Prompts de recherche
  python engine.py confidence <json>  📊 Carte de confiance
  python engine.py guard <json>       🛡️ Rapport gardien (début de session)
  python engine.py check <json> <id>  🛡️ Peut-on bosser sur ce nœud ?
  python engine.py update <json> <id> <status> [entry]  📝 Update un nœud
  python engine.py find <json> <query>  🔍 Cherche dans l'arbre
  python engine.py classify           Classification interactive
  python engine.py families           Liste toutes les familles
  python engine.py family <id>        Détails d'une famille
  python engine.py anatomy [id]       Anatomie biologique 10 niveaux
  python engine.py gaps <id>          Détecte les trous
  python engine.py export             Exporte la knowledge base en JSON

Familles: conifere, feuillu, palmier, baobab, buisson, liane

Exemples:
  python engine.py serve scans/hsbc.json
  python engine.py serve                          # vue forêt
  python engine.py serve --github sky1241          # scan GitHub + forêt
  python engine.py github sky1241                  # scan tous les repos
  python engine.py github sky1241/hsbc-algo        # scan un repo
  python engine.py plant "je veux un Shazam pour piano"
  python engine.py scan /path/to/my/repo
  python engine.py guard scans/shazam.json
  python engine.py check scans/shazam.json B1
  python engine.py update scans/shazam.json T1 done "lib/engine.dart:40"
  python engine.py find scans/shazam.json "matching"
""")
        return

    cmd = sys.argv[1].lower()

    if cmd == "plant":
        if len(sys.argv) < 3:
            print("Usage: python engine.py plant \"<idée>\"")
            print("Exemple: python engine.py plant \"je veux un Shazam pour piano\"")
            return
        idea = " ".join(sys.argv[2:])
        result = plant(idea)
        print_planted_tree(result)

        # Sauvegarder en markdown + JSON
        filepath_md = save_planted_tree(result)
        filepath_json = save_tree_json(result)
        print(f"\n  💾 Arbre sauvé : {filepath_md}")
        print(f"  💾 JSON sauvé  : {filepath_json}")

    elif cmd == "scan":
        if len(sys.argv) < 3:
            print("Usage: python engine.py scan <dossier>")
            print("Exemple: python engine.py scan /path/to/my-project")
            return
        repo_path = sys.argv[2]
        tree = scan_repo(repo_path)
        if tree:
            print_scan_report(tree)
            print_planted_tree(tree)
            filepath_json = save_tree_json(tree)
            filepath_md = save_planted_tree(tree)
            print(f"\n  💾 JSON sauvé : {filepath_json}")
            print(f"  💾 MD sauvé   : {filepath_md}")

    elif cmd == "research":
        if len(sys.argv) < 3:
            print("Usage: python engine.py research <fichier.json> [contexte]")
            print("Exemple: python engine.py research scans/impots.json \"suisse genève particuliers\"")
            return
        tree = load_tree(sys.argv[2])
        context = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else ""
        prompts = generate_research_prompts(tree, context)
        print_research_prompts(prompts)

    elif cmd == "confidence":
        if len(sys.argv) < 3:
            print("Usage: python engine.py confidence <fichier.json>")
            return
        tree = load_tree(sys.argv[2])
        print_confidence_map(tree)

    elif cmd == "guard":
        if len(sys.argv) < 3:
            print("Usage: python engine.py guard <fichier.json>")
            return
        tree = load_tree(sys.argv[2])
        guardian_session_report(tree)

    elif cmd == "check":
        if len(sys.argv) < 4:
            print("Usage: python engine.py check <fichier.json> <node_id>")
            return
        tree = load_tree(sys.argv[2])
        result = guardian_check(tree, sys.argv[3].upper())
        print_guardian_check(result)

    elif cmd == "update":
        if len(sys.argv) < 5:
            print("Usage: python engine.py update <fichier.json> <node_id> <status> [entry]")
            print("Status: todo, wip, done")
            print("Entry: fichier:ligne:fonction (ex: lib/engine.dart:40:main)")
            return
        tree = load_tree(sys.argv[2])
        node_id = sys.argv[3].upper()
        status = sys.argv[4].lower()
        entry = sys.argv[5] if len(sys.argv) > 5 else None
        guardian_update(tree, node_id, status=status, entry=entry)
        save_tree_json(tree, sys.argv[2])
        print(f"  💾 Arbre mis à jour : {sys.argv[2]}")

    elif cmd == "find":
        if len(sys.argv) < 4:
            print("Usage: python engine.py find <fichier.json> <query>")
            return
        tree = load_tree(sys.argv[2])
        query = " ".join(sys.argv[3:])
        results = guardian_find(tree, query)
        if results:
            print(f"\n  🔍 {len(results)} résultat(s) pour '{query}' :")
            for n in results:
                status_icon = {"done": "✅", "wip": "🔨", "todo": "🔴"}.get(n["status"], "?")
                entry = n.get("entry", "~")
                print(f"    {status_icon} [{n['id']:>3}] {n['label']}")
                if entry != "~":
                    print(f"           📍 {entry}")
        else:
            print(f"\n  Aucun résultat pour '{query}'")

    elif cmd == "classify":
        result = classify_interactive()
        if result:
            print(f"\n--- RÉSULTAT ---")
            print(f"Projet : {result['name']}")
            print(f"Famille : {FAMILIES[result['family']]['emoji']} {result['family']}")

            save = input("\nGénérer le template ? (o/n) : ").strip().lower()
            if save == "o":
                template = generate_template(result)
                filename = f"scans/{result['name'].lower().replace(' ', '-')}_tree.md"
                os.makedirs("scans", exist_ok=True)
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(template)
                print(f"\n✅ Template sauvé : {filename}")

    elif cmd == "families":
        print_all_families()

    elif cmd == "family":
        if len(sys.argv) < 3:
            print("Usage: python engine.py family <id>")
            print(f"IDs disponibles : {', '.join(FAMILIES.keys())}")
            return
        fid = sys.argv[2].lower()
        if fid in FAMILIES:
            print_family(fid)
        else:
            print(f"Famille inconnue : {fid}")
            print(f"IDs disponibles : {', '.join(FAMILIES.keys())}")

    elif cmd == "anatomy":
        fid = sys.argv[2].lower() if len(sys.argv) > 2 else None
        if fid and fid not in FAMILIES:
            print(f"Famille inconnue : {fid}")
            print(f"IDs disponibles : {', '.join(FAMILIES.keys())}")
            return
        display_anatomy(fid)

    elif cmd == "gaps":
        if len(sys.argv) < 3:
            print("Usage: python engine.py gaps <family_id>")
            print("Démonstration avec des nœuds exemples.")
            return
        fid = sys.argv[2].lower()
        if fid not in FAMILIES:
            print(f"Famille inconnue : {fid}")
            return

        # Demo : nœuds minimaux pour montrer la détection de gaps
        demo_nodes = [
            {"id": "T1", "level": "T", "status": "wip", "depends": [], "label": "Core engine"},
            {"id": "B1", "level": "B", "status": "wip", "depends": ["T1"], "label": "Module A"},
            {"id": "B2", "level": "B", "status": "todo", "depends": ["T1"], "label": "Module B"},
            {"id": "R1", "level": "R", "status": "done", "depends": [], "label": "Python 3.12"},
        ]
        fam = FAMILIES[fid]
        print(f"\n  Analyse gaps pour {fam['emoji']} {fam['nom']} (nœuds demo)")
        gaps = detect_gaps(demo_nodes, fid)
        print_gap_report(gaps)

    elif cmd == "generate":
        if len(sys.argv) < 3:
            print("Usage: python engine.py generate <family_id> [nom_projet]")
            return
        fid = sys.argv[2].lower()
        name = sys.argv[3] if len(sys.argv) > 3 else "Mon Projet"
        if fid in FAMILIES:
            template = generate_template({"name": name, "family": fid, "desc": ""})
            print(template)
        else:
            print(f"Famille inconnue : {fid}")

    elif cmd == "serve":
        # Check for --github flag
        if len(sys.argv) > 2 and sys.argv[2] == "--github":
            username = sys.argv[3] if len(sys.argv) > 3 else None
            if not username:
                print("Usage: python engine.py serve --github <username>")
                return
            token = None
            # Check for token file
            token_file = Path(__file__).parent / "CLEGITJAMAISTOUCHER.txt"
            if token_file.exists():
                token = token_file.read_text().strip()
            print(f"  🌐 Scan GitHub de {username}...")
            scan_github_user(username, token)
            serve_tree(None)
        else:
            json_path = sys.argv[2] if len(sys.argv) > 2 else None
            serve_tree(json_path)

    elif cmd == "github":
        if len(sys.argv) < 3:
            print("Usage: python engine.py github <username> [--token <token>]")
            print("       python engine.py github <username>/<repo>")
            print("\nScanne les repos GitHub et génère les arbres dans scans/")
            return
        target = sys.argv[2]
        token = None
        if "--token" in sys.argv:
            idx = sys.argv.index("--token")
            if idx + 1 < len(sys.argv):
                token = sys.argv[idx + 1]
        # Check for token file
        if not token:
            token_file = Path(__file__).parent / "CLEGITJAMAISTOUCHER.txt"
            if token_file.exists():
                token = token_file.read_text().strip()

        if "/" in target:
            # Scan un repo spécifique
            owner, repo_name = target.split("/", 1)
            tree = scan_github_repo(owner, repo_name, token)
            if tree:
                print_scan_report(tree)
                filepath = save_tree_json(tree)
                print(f"\n  💾 JSON sauvé : {filepath}")
        else:
            # Scan tous les repos d'un utilisateur
            trees = scan_github_user(target, token)
            if trees:
                print(f"\n  🌲 Lance: python engine.py serve")
                print(f"  pour voir ta forêt !")

    elif cmd == "export":
        path = export_knowledge_base()
        print(f"✅ Knowledge base exportée : {path}")

    elif cmd == "validate":
        print("TODO: Implémenter la lecture de fichiers YAML pour validation.")
        print("En attendant, utiliser validate_growth() en Python directement.")

    else:
        print(f"Commande inconnue : {cmd}")
        print("Utiliser 'python engine.py' sans arguments pour l'aide.")


if __name__ == "__main__":
    main()
