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
P:muninn|memory-compression-engine|python|4921L
D:zero-required|anthropic,tiktoken
E:engine/core/muninn.py 3776L|engine/core/mycelium.py 1105L
S:v0.9+|2026-03-08

F:
  muninn.py 3776L compress/boot/feed/ingest/bootstrap/prune(60 funcs)
  mycelium.py 1105L co-occurrence+fusion+decay+spreading-activation
  tokenizer.py 40L tiktoken wrapper+fallback
  tree.json L-system tree metadata+temperature
  .muninn/ per-repo data(mycelium,sessions,tree,errors)

R:
  03-08 spreading activation(Collins&Loftus1975)+sleep consolidation(Wilson&McNaughton1994)
  03-08 full pipeline 4repos 230files x4.4 $0.21
  03-07 TF-IDF retrieval+auto-segmentation+ingest
  03-07 L9 tested: x5.2(50papers) x4.0(306papers)
  03-06 pivot: sinograms dead->BPE native

T:
  ! sinograms cost 2-3tok vs 1 english—dead path
  ! L8 on pre-compressed loses 72% facts
  ! len//4 != real tokens—use tiktoken
  ! setx != os.environ—need registry fallback
  ! NCD threshold 0.6 not 0.4 for short texts

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
