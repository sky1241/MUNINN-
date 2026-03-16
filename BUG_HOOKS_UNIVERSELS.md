# BUG REPORT — Les hooks Muninn ne sont PAS universels

## Probleme

Quand Muninn est installe sur un nouveau repo (ex: `c:\Users\ludov\drugs`), les hooks Claude Code ne sont **pas configures automatiquement**. Resultat : Muninn ne capture aucune conversation de ce repo. Toute la data est perdue.

### Ce qui s'est passe

1. On a copie le engine Muninn dans `c:\Users\ludov\drugs\engine\`
2. On a travaille toute la journee sur ce repo (13 commits, scenarios JDR, encryption, etc.)
3. A 18h on decouvre que Muninn n'a RIEN capture depuis 13h22
4. Raison : le repo drugs n'avait pas de `.claude/settings.local.json`
5. Les hooks dans MUNINN- pointent en dur vers `--repo "C:\Users\ludov\MUNINN-"`
6. Le watchdog aussi ne poll que les transcripts du projet MUNINN-

### Le fix temporaire qu'on a fait

On a manuellement cree `drugs/.claude/settings.local.json` avec les hooks pointant vers le bon repo. Ca marche, mais c'est du bricolage.

## Ce qu'il faut coder

### 1. Auto-configuration des hooks a l'installation

Quand on fait `muninn bootstrap <repo>` ou `pip install muninn` dans un nouveau repo, Muninn DOIT :
- Detecter le chemin du repo courant
- Creer `.claude/settings.local.json` automatiquement avec les bons paths
- Les paths doivent pointer vers l'engine Muninn (wherever it's installed) + le repo courant comme `--repo`
- Si le fichier existe deja, merger les hooks sans ecraser les existants

### 2. Watchdog universel

Le watchdog (`engine/core/watchdog.py`) doit :
- Maintenir une LISTE de repos enregistres (pas un seul hardcode)
- Quand un nouveau repo est bootstrap, l'ajouter a la liste
- Poll les transcripts de TOUS les repos enregistres, pas juste MUNINN-

### 3. Commande `muninn install` ou `muninn init`

Une commande one-shot qui :
```bash
cd /path/to/any/repo
muninn init
```
- Cree `.claude/settings.local.json` avec les hooks
- Cree `.muninn/` si besoin
- Ajoute le repo au watchdog
- Done. Zero config manuelle.

### 4. Le bridge_hook.py doit etre universel

Actuellement le bridge_hook utilise `hook_input.get("cwd", os.getcwd())` pour le repo path, ce qui est bien. Mais le path vers le script est hardcode dans le settings. Il faudrait que `muninn init` genere le bon path automatiquement.

## Contrainte

Le fix doit etre **retroactif** — les repos deja installes (drugs, infernal-wheel, yggdrasil) doivent pouvoir faire `muninn init` et ca doit marcher sans tout reconfigurer.

## Priorite

HAUTE. Chaque minute sans hooks = data perdue = memoire perdue.
