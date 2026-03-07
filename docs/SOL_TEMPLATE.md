# SOL.mn Template — Format machine optimal pour Claude

## Pourquoi ce format

Claude lit le texte via un tokenizer BPE. Chaque mot anglais court = 1 token.
Les articles (the, a, an), prepositions (of, in, for), et formulations longues
gaspillent des tokens sans ajouter d'information.

Ce template est le format le plus dense que Claude peut lire sans perte de sens.
Il est utilise pour TOUT ce qui vit dans .muninn/ (root.mn, branches, sessions).

## Le template

```
P:<nom>|<type>|<lang>|<lines-total>
D:<zero-dep>|<opt-dep1>,<opt-dep2>
E:<entry-point> <lines>L|<file2> <lines>L
S:<etat-version>|<date-dernier-commit>

F:
  <file> <lines>L <role>
  <file> <lines>L <role>
  ...

R:
  <date> <quoi>
  <date> <quoi>
  ...

T:
  ! <piege-a-eviter>
  ! <piege-a-eviter>
  ...

C:
  <convention>
  <convention>
  ...
```

## Legende

- P: = Project (nom, type, langage, taille)
- D: = Dependencies (zero obligatoire, optionnelles)
- E: = Entry points (fichiers principaux + taille)
- S: = State (version, date)
- F: = Files (carte des fichiers cles)
- R: = Recent (derniers changements)
- T: = Traps (erreurs connues, chemins morts)
- C: = Conventions (regles du projet)

## Exemple reel — Muninn

```
P:muninn|memory-compression-engine|python|2600L
D:zero-required|anthropic,llmlingua
E:engine/core/muninn.py 2100L|engine/core/mycelium.py 465L
S:v0.9|2026-03-07

F:
  muninn.py 2100L compress/boot/feed/ingest/bootstrap
  mycelium.py 465L co-occurrence+fusion+decay
  tokenizer.py 45L tiktoken wrapper+fallback
  tree.json L-system tree metadata
  .muninn/ per-repo data(mycelium,sessions,tree)

R:
  03-07 TF-IDF retrieval+auto-segmentation+ingest
  03-07 14 bugs fixed(6 scans)
  03-07 L9 tested: x5.2(50papers) x4.0(306papers)
  03-06 pivot: sinograms dead->BPE native
  03-06 mycelium=living codebook

T:
  ! sinograms cost 2-3tok vs 1 english—dead path
  ! L8 on pre-compressed loses 72% facts
  ! len//4 != real tokens—use tiktoken
  ! setx != os.environ—need registry fallback

C:
  user=french,informal,fast
  never show API keys/git tokens
  everything universal,zero hardcode
  python C:/Users/ludov/AppData/Local/Programs/Python/Python313/python.exe
```

## Gain mesure

Le meme contenu en prose (WINTER_TREE style): ~1200 tokens
En format SOL.mn: ~300 tokens
Gain: x4 sur le root seul, charge a CHAQUE session
