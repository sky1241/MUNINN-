# MUNINN — Carte Systeme Complete

## Vue d'ensemble: qui parle a qui

```
╔══════════════════════════════════════════════════════════════════════════╗
║                        TOI (Sky) + CLAUDE                              ║
║                     conversation en cours                              ║
╚════════════════════════════╤═════════════════════════════════════════════╝
                             │
                             │ tu parles, je reponds
                             │ Claude Code ecrit TOUT dans:
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  JSONL TRANSCRIPT (format Claude Code — PAS Muninn)                    ║
║  ~/.claude/projects/c--Users-ludov-MUNINN-/{session-id}.jsonl          ║
║                                                                        ║
║  577 Mo total, 320 fichiers (+ subagents/)                             ║
║  Chaque session = 1 fichier JSONL                                      ║
║  Chaque ligne = 1 event JSON (user, assistant, progress, tool...)      ║
║                                                                        ║
║  C'EST CLAUDE CODE QUI ECRIT CA. PAS MUNINN.                           ║
║  Muninn le LIT mais ne le controle pas.                                ║
╚════════════════════════════╤═════════════════════════════════════════════╝
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
     HOOK 1              HOOK 2             HOOK 3
   UserPromptSubmit    PreCompact          SessionEnd/Stop
   (a chaque msg)    (contexte plein)    (fin de session)
          │                  │                  │
          ▼                  ▼                  ▼
    bridge_hook.py    muninn.py feed      muninn.py feed
    (5s timeout)      (180s timeout)      (120-180s timeout)
          │                  │                  │
          │                  └────────┬─────────┘
          │                           │
          │                           ▼
          │              ╔═══════════════════════════╗
          │              ║  FEED PIPELINE             ║
          │              ║                           ║
          │              ║  1. parse_transcript()    ║
          │              ║     JSONL -> textes bruts ║
          │              ║                           ║
          │              ║  2. observe() mycelium    ║
          │              ║     textes -> co-occur    ║
          │              ║                           ║
          │              ║  3. compress_transcript() ║
          │              ║     L0-L7, L10, L11       ║
          │              ║     -> fichier .mn         ║
          │              ║                           ║
          │              ║  4. grow_branches()       ║
          │              ║     .mn -> branches arbre ║
          │              ║                           ║
          │              ║  5. sync_to_meta()        ║
          │              ║     local -> global       ║
          │              ╚═══════════╤═══════════════╝
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
```

## Les 5 stockages (ou va la data)

```
┌─────────────────────────────────────────────────────────────────┐
│  1. MYCELIUM LOCAL                                              │
│     .muninn/mycelium.db (SQLite, 309 Mo)                        │
│                                                                 │
│     QU'EST-CE QUE C'EST:                                        │
│     Reseau de co-occurrences. Quels mots apparaissent ensemble. │
│     "threshold" <-> "score" <-> "prune" = connexion forte.      │
│     Les connexions fortes deviennent des FUSIONS (abbreviations)│
│                                                                 │
│     FORMAT: SQLite, 3 tables principales:                       │
│       concepts(id, name)     — chaque mot = 1 ID entier         │
│       connections(a, b, w, zones, dates...)  — poids + metadata  │
│       fusions(pattern, replacement) — abbreviations apprises    │
│                                                                 │
│     QUI ECRIT DEDANS: observe() pendant le feed                 │
│     QUI LIT:          compress (L6), boot (spreading activation)│
│     SCOPE:            CE repo seulement                         │
│                                                                 │
│     AVANT: c'etait mycelium.json (376 Mo JSON plat = lent)      │
│     APRES: SQLite normalized, x5 plus petit, x100 plus rapide   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  2. META-MYCELIUM (global)                                      │
│     ~/.muninn/meta_mycelium.db (SQLite, 1.2 Go)                 │
│                                                                 │
│     QU'EST-CE QUE C'EST:                                        │
│     Le MEME format que le mycelium local, mais CROSS-REPO.      │
│     Quand tu bosses sur Muninn, Yggdrasil, infernal-wheel,      │
│     chaque mycelium local sync ses connexions ici.               │
│     Resultat: "scan" connecte a "arxiv" meme si t'as jamais     │
│     parle d'arxiv dans le repo Muninn.                           │
│                                                                 │
│     QUI ECRIT: sync_to_meta() a la fin du feed                  │
│     QUI LIT:   pull_from_meta() au boot                         │
│     SCOPE:     TOUS les repos                                   │
│                                                                 │
│     C'EST LE CHAMPIGNON GLOBAL. Le local = 1 jardin.            │
│     Le meta = toute la foret.                                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  3. L'ARBRE (memoire structuree)                                │
│     .muninn/tree/ (34 fichiers, 1 Mo total)                     │
│       tree.json  — structure (17 Ko, noms + metadata)           │
│       root.mn    — resume permanent du projet (~100 lignes)     │
│       b00.mn     — branche 0 (un sujet)                         │
│       b01.mn     — branche 1 (un autre sujet)                   │
│       ...                                                       │
│                                                                 │
│     QU'EST-CE QUE C'EST:                                        │
│     La MEMOIRE PERSISTANTE. Ce qui survit entre sessions.       │
│     Chaque branche = un sujet (compression, bio-vectors, etc.)  │
│     Chaque branche a une TEMPERATURE:                           │
│       chaud = lu souvent, utile                                 │
│       froid = pas lu, oublie progressivement                    │
│     Les branches froides sont ELAGUEES (prune) ou RECONSOLIDEES │
│                                                                 │
│     QUI ECRIT: grow_branches() pendant feed                     │
│     QUI LIT:   boot() au demarrage de session                   │
│     FORMAT:    .mn = texte compresse (anglais compact, tags)    │
│                                                                 │
│     C'EST L'ARBRE. Le mycelium = le sol. L'arbre = ce qui pousse│
│     dessus. Le mycelium NOURRIT l'arbre, pas l'inverse.         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  4. SESSIONS COMPRESSEES                                        │
│     .muninn/sessions/ (10 fichiers .mn, 72 Ko total)            │
│                                                                 │
│     QU'EST-CE QUE C'EST:                                        │
│     Le transcript COMPRESSE de chaque session.                  │
│     Le JSONL fait 11 Mo. Le .mn fait 7 Ko. Ratio x143.         │
│     Seuls les faits, decisions, chiffres survivent.             │
│                                                                 │
│     QUI ECRIT: compress_transcript() pendant feed               │
│     QUI LIT:   boot() charge le dernier .mn                     │
│                 recall() cherche dans tous les .mn               │
│                                                                 │
│     session_index.json = index de recherche (quel .mn parle     │
│     de quoi). Comme une table des matieres.                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  5. JSONL TRANSCRIPTS (pas Muninn — Claude Code)                │
│     ~/.claude/projects/.../ (577 Mo, 320 fichiers)              │
│                                                                 │
│     QU'EST-CE QUE C'EST:                                        │
│     Le BRUT. Tout ce qu'on se dit. Chaque message, chaque       │
│     tool call, chaque resultat. C'est Claude Code qui les ecrit.│
│     Muninn les LIT (feed) mais ne les ecrit pas.                │
│                                                                 │
│     APRES le feed, le JSONL est INUTILE pour Muninn.            │
│     (Claude Code en a encore besoin pour relire ses sessions)   │
│                                                                 │
│     C'EST LA SOURCE BRUTE. 577 Mo de source → 72 Ko compresse. │
└─────────────────────────────────────────────────────────────────┘
```

## Le cycle de vie d'une session

```
BOOT (debut de session)
│
├─ Charge root.mn (toujours)
├─ TF-IDF + Spreading Activation → choisit les branches pertinentes
├─ pull_from_meta() → tire du meta-mycelium les connexions utiles
├─ Charge le dernier .mn (session precedente)
├─ Charge errors.json si pertinent
│
▼
SESSION (toi + moi qui bossons)
│
│   Pendant ce temps: RIEN ne se passe cote Muninn.
│   Claude Code ecrit le JSONL en temps reel.
│   Les hooks attendent leur declencheur.
│
▼
TRIGGER (un des 3 events)
│
├─ PreCompact: "le contexte est plein, Claude va compresser"
├─ SessionEnd: "la session se ferme"
├─ Stop: "l'utilisateur a stop un message"
│
▼
FEED (le gros morceau)
│
├─ 1. Lit le JSONL, extrait les textes (user + assistant)
├─ 2. observe() → nourrit le mycelium avec les co-occurrences
├─ 3. Compression L0 → L7 → L10 → L11 → fichier .mn
├─ 4. grow_branches() → cree/met a jour les branches de l'arbre
├─ 5. sync_to_meta() → pousse les nouvelles connexions dans le meta
├─ 6. Update session_index.json
│
▼
PRET POUR LA PROCHAINE SESSION
```

## Tailles reelles (maintenant)

```
BRUT (Claude Code)          COMPRESSE (Muninn)
─────────────────           ──────────────────
JSONL: 577 Mo               .mn sessions: 72 Ko      (x8000)
                            Arbre: 1 Mo
                            Mycelium local: 309 Mo
                            Meta-mycelium: 1.2 Go     ← LE PLUS GROS
                            Divers (.json): 200 Ko
                            ─────────────────────
                            Total Muninn: ~1.5 Go

Total sur disque: ~2.1 Go
```

## Le probleme que tu vois

```
CE QUI EST GROS ET POURQUOI:

1. JSONL (577 Mo) — format Claude Code, pas optimise, on controle pas
   → APRES feed, c'est du dechet. Muninn a tout extrait.
   → Solution: archiver/supprimer apres feed

2. Meta-mycelium (1.2 Go) — toutes les co-occurrences de tous les repos
   → C'est VOULU. C'est la foret entiere.
   → Mais 1.2 Go pour des connexions mot↔mot c'est beaucoup
   → Solution possible: purge des connexions faibles (< seuil)

3. Mycelium local (309 Mo) — co-occurrences de CE repo
   → Normal pour 92K concepts × 2.37M connexions

4. Arbre (1 Mo) — PETIT. C'est la ou est la valeur.
   → 72 Ko de .mn = tout ce qui compte de 577 Mo de conversation

LE JSONL EST LE SEUL TRUC QUI DEVRAIT PAS ETRE LA APRES FEED.
```

## Format de chaque fichier

```
JSONL (Claude Code):
  {"type":"user","message":{"role":"user","content":[{"type":"text","text":"..."}]}}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"text",...},{"type":"tool_use",...}]}}
  → 1 ligne JSON par event. Types: user, assistant, progress, queue-operation, file-history-snapshot, system

.mn (Muninn compresse):
  B> boot: scoring blend 70% ebbinghaus 30% actr, h adaptive beta=0.5
  D> decision: migrate mycelium json->sqlite, x5 disk x100 ram
  F> fact: benchmark 37/40 (92%), 12 files x4.5 avg
  E> error: feed_from_transcript silently skipped on lock contention
  → Texte brut, anglais compact, tags B/D/F/E/A en debut de ligne

tree.json:
  {"nodes":[{"id":"root","file":"root.mn","temp":1.0,"reviews":5,...},
            {"id":"b00","file":"b00.mn","temp":0.8,...},...]}
  → Structure de l'arbre. Metadata par noeud. Le CONTENU est dans les .mn.

mycelium.db (SQLite):
  Table concepts: (id INTEGER, name TEXT)
  Table connections: (concept_a INT, concept_b INT, weight REAL, zones TEXT, ...)
  Table fusions: (pattern TEXT, replacement TEXT)
  → Reseau de co-occurrences. Pas du texte, des RELATIONS.

session_index.json:
  {"session_id": {"concepts": ["compression","mycelium"], "date": "2026-03-15"}}
  → Index pour retrouver quelle session parlait de quoi.
```
