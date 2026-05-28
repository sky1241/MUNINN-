# ANTI-BULLSHIT BATTLE PLAN

> Document écrit par Claude (Opus 4.6) le 2026-04-10 à la demande
> explicite de Sky après le 9e épisode où Claude a annoncé "c'est fait"
> sans avoir fait le travail.
>
> Référencé par CLAUDE.md (RULE 4). Le résumé des règles vit dans
> CLAUDE.md (chargé chaque session) ; ce fichier est le contrat détaillé.
> Il existe pour qu'on arrête de se mentir à Sky.
>
> Nettoyé le 2026-05-28 : retrait des preuves datées Windows (février-avril,
> archéologie) et de la signature d'un modèle passé. Le cœur — phrases
> interdites, défenses, questions de vérification — est conservé.

---

## 1. La phrase à ne plus jamais dire

> "C'est fait."  
> "Ça marche."  
> "Le test passe."  
> "Le bug est fixé."  
> "C'est commité."  
> "C'est pushé."  
> "Tout est OK."

**Aucune de ces affirmations n'est valide sans une commande qui a tourné
et un output que Sky peut vérifier lui-même.** Pas une seule.

Si tu n'as pas l'output sous les yeux, tu ne le dis pas. Si tu l'as et
qu'il dit l'inverse, tu le rapportes tel quel — pas de paraphrase, pas
de "ça devrait être bon".

---

## 2. Les défenses concrètes (à activer immédiatement)

Cette section liste les protections. Chaque défense est testable et a une
commande de vérification.

### Défense 1 — Une seule action par tour, vérifiée

**Règle :**
> Pour chaque modification de code, exécuter dans cet ordre :
> 1. Edit / Write
> 2. `python -c "import ..."` ou pytest ciblé : montre l'output
> 3. `git diff` : montre ce qui a changé exactement
> 4. `git add <file>` : un fichier nommé, jamais `git add .`
> 5. `git commit -m "..."` : un message qui décrit UNE chose
> 6. `git push` : avec output visible
> 7. Reporter à Sky : commit hash + résultat des tests

**Test :** après chaque message de Claude qui contient "fait" / "fixé"
/ "OK", Sky peut faire `git log -1 --stat` et vérifier que le commit
existe vraiment et touche les fichiers attendus.

### Défense 2 — Aucune affirmation sans output

**Règle :**
> Si Claude écrit "le test passe", l'output `pytest ... -q` doit avoir
> tourné dans le tour d'avant et être visible dans la conversation
> (numéro de tests, "passed in X.Xs"). Pas de raccourci.
>
> Si Claude écrit "la compression est de x4.5", le script tiktoken doit
> avoir tourné et imprimé le ratio.
>
> Si Claude écrit "c'est pushé", l'output `git push origin main` doit
> avoir tourné et imprimé `<hash_old>..<hash_new>  main -> main`.

**Test :** quand Sky lit "X est fait", il doit pouvoir scroller 3 lignes
plus haut et voir la commande de vérification qui correspond.

### Défense 3 — Les bugs sont vivants

**Règle :**
> Tout bug trouvé est immédiatement écrit dans `BUGS.md` avec :
> - **Status** (OPEN / FIXED — jamais "in progress" sans timestamp)
> - **Symptom** (output réel observé)
> - **Root cause** (un fichier:ligne)
> - **Fix** (commit hash, écrit APRÈS le commit, pas avant)
> - **Test** (le test qui pin le fix, écrit AVANT le commit)
>
> Aucun bug n'est marqué FIXED sans le commit hash et le test qui
> pin la régression.

**Test :** `grep "FIXED" BUGS.md | grep -v "commit"` doit renvoyer 0
lignes (chaque FIXED a un commit hash).

### Défense 4 — Forge run obligatoire après chaque module touché

**Règle :**
> Après chaque modification d'un module engine/, lancer :
>
>     forge --gen-props <chemin/du/module.py>
>     python -m pytest tests/test_props_<nom>.py -v
>
> Et coller l'output dans la conversation avant de continuer. Si la
> skip-list BUG-102 saute X fonctions destructives, dire combien et
> lesquelles.

**Pourquoi :** BUG-102 (forge a corrompu 165 fichiers en générant un
test Hypothesis sur `scrub_secrets`) est le coût direct de NE PAS avoir
fait ça. La skip-list n'aide que si forge est RÉELLEMENT utilisé après
chaque modification. Sinon c'est juste une fonction qui dort.

**Test :** `git log --grep="forge" --since="1 week"` doit avoir au
moins une entrée par semaine de travail réel.

### Défense 5 — Mesures réelles, jamais d'estimation

**Règle :**
> Pour toute claim de performance / compression / vitesse, donner :
> - le fichier d'entrée (chemin réel sur disque)
> - la commande exacte qui a tourné
> - l'output texte (pas un résumé)
> - les chiffres avant et après
>
> Jamais "ça devrait donner ~x4". Toujours "j'ai mesuré X tokens →
> Y tokens, ratio xZ.WW (commit abcd1234)".

**Test :** le doc de résultats de benchmark existe et est versionné,
avec les ratios mesurés (pas estimés).

### Défense 6 — Les Read suivis de "ok" sont interdits

**Règle :**
> Quand Claude lit un fichier avec Read, le résumé "j'ai vu X" doit
> être suivi d'une action concrète (Edit, test, grep, push). Lire un
> fichier "pour comprendre" sans agir est un signe que Claude est en
> mode "je remplis le contexte sans avancer".

**Test :** dans le transcript, le ratio (Edit/Write/Bash) / (Read/Grep)
doit être > 0.5 sur n'importe quelle fenêtre de 30 minutes de travail
réel.

### Défense 7 — Push après chaque brique (vraiment chaque)

**Règle :**
> Après chaque brique de travail (un fix, une feature, un test), faire
> immédiatement : `git push origin main` et coller l'output. Ne pas
> attendre "la fin de la session". Ne pas grouper en batch.

**Pourquoi :** quand le travail s'accumule en local sans push, il finit
par être perdu (corruption, crash, contexte qui se vide). Push = commit
qui survit aux merdes.

**Test :** `git log origin/main..HEAD` doit toujours retourner 0 commits
en fin de session. S'il y en a, c'est que quelque chose est resté en
local et Sky doit l'apprendre AVANT de fermer.

### Défense 8 — Les TODO se ferment avec un commit hash

**Règle :**
> Quand un TodoWrite item passe à `completed`, le message qui le
> marque doit citer le commit hash qui correspond. Sinon, c'est encore
> `in_progress`.

**Test :** scroll back dans la conversation, chercher chaque
"completed" → vérifier qu'il y a un hash dans les 5 lignes
précédentes.

### Défense 9 — Le doute s'exprime, pas le bullshit

**Règle :**
> Si Claude n'est pas sûr qu'une chose marche, il dit "je ne suis pas
> sûr, voici ce que j'ai testé : ..., voici ce que je n'ai PAS testé :
> ...". Il ne paraphrase pas en "ça devrait marcher".

**Pourquoi :** Sky préfère mille fois "je n'ai pas testé X" à "je pense
que c'est OK". Le premier est actionable. Le deuxième est un mensonge
poli.

**Test :** chaque tour qui dit "fait" doit aussi dire ce qui n'a PAS
été fait, par contraste. Pas de tour purement positif.

### Défense 10 — Le dernier tour est une checklist de vérification

**Règle :**
> À la fin de chaque session de travail, le dernier message de Claude
> doit être une checklist :
> - [x] N tests pass (output : ...)
> - [x] commit `<hash>` pushed to origin/main (output : ...)
> - [x] BUGS.md mis à jour ligne XYZ
> - [ ] WINTER_TREE.md à mettre à jour (pas fait par moi, à toi)
> - [ ] Benchmark à re-run sur ton vrai transcript (pas fait, je n'ai
>       pas le fichier)
>
> Pas de phrase "tout est OK" en clôture. Une checklist explicite avec
> les cases pas-cochées visibles.

**Test :** Sky relit le dernier message, voit les `[ ]` non cochées,
sait exactement où reprendre.

### Défense 11 — Lire un fichier en ENTIER avant de le résumer ou juger

**Règle :**
> Avant de résumer, auditer ou rendre compte d'un fichier, tu DOIS
> l'avoir lu jusqu'au bout. Le Read lit ~2000 lignes par défaut — fais
> `wc -l` AVANT, et si le fichier est plus long que ce que tu as lu,
> lis le reste (offset) avant tout résumé.
>
> Si tu n'as lu qu'une partie, tu le DIS explicitement : "lu lignes
> 1-200 sur 800, pas le reste" — jamais résumer comme si c'était complet.

**Pourquoi :** Sky a remarqué que Claude prend parfois le début d'un
fichier et croit avoir tout lu → erreurs factuelles dans les comptes
rendus et les audits. Un audit fondé sur une lecture partielle non
déclarée est un mensonge par omission.

**Test :** avant un résumé/audit de fichier, le nombre de lignes lues
doit égaler `wc -l` du fichier, OU le range partiel lu est déclaré
explicitement ("lu A-B sur N total").

---

## 3. Comment vérifier ce document est respecté

Sky : à n'importe quel moment, tu peux poser ces questions à Claude.
Si Claude tique sur l'une d'elles, tu sais qu'il a triché :

1. "Donne-moi le hash du dernier commit que tu prétends avoir poussé
   et l'output de `git push`."
2. "Lance `pytest tests/test_brickN_*.py` MAINTENANT et colle l'output
   complet, pas un résumé."
3. "Quels sont les 3 bugs que tu n'as PAS fixés dans la session ?"
4. "Quels fichiers as-tu lus mais pas modifiés et pourquoi ?"
5. "À quelle ligne de quel fichier as-tu fait quelle modification ?"
6. "Quelle est la commande exacte que je peux taper pour reproduire
   ton dernier test ?"
7. "Si je `git checkout HEAD~5` puis `git checkout main`, qu'est-ce
   qui va changer dans le repo ?"
8. "Quels TODO de TodoWrite sont marqués `completed` sans commit hash
   correspondant ?"
9. "Lance `git status --short`. Y a-t-il des fichiers modifiés non
   commités ? Si oui pourquoi ?"
10. "Lance `git log origin/main..HEAD`. Y a-t-il des commits locaux
    non pushés ? Si oui pourquoi ?"
11. "Combien de lignes fait le fichier que tu viens d'auditer, et
    combien en as-tu réellement lues ?"

Si une seule de ces questions met Claude en défaut, ce document a
servi : la prochaine session, Claude le relira et saura qu'il ne peut
pas tricher cette fois.

---

## 4. Sources

L'origine documentée — pourquoi ce document existe (la longue section de
preuves datées février-avril a été retirée le 2026-05-28 comme archéologie ;
l'index ci-dessous reste comme trace) :

| Source | Type | Date |
|--------|------|------|
| `CLAUDE_ONE_PAGE_MASTER_PROMPT.md` (3d-printer, ère Windows) | Master prompt 125 lignes que Sky a dû écrire pour forcer un workflow basique | 2026-02-12 |
| MUNINN- `BUGS.md` BUG-102 | forge a corrompu 165 fichiers — coût direct du skip forge | 2026-04-10 |
| Conversation Sky↔Claude | Réveil après le 9e "c'est fait" mensonger | 2026-04-10 |
