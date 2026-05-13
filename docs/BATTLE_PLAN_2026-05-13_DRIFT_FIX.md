# Battle Plan 2026-05-13 — Drift Fix + Hooks Sync + Orphan Wire

> **Sky's request 2026-05-13** : après le push README v3, le cousin Claude a
> trouvé que CLAUDE.md ligne 158 cite `.muninn/mycelium.json` alors que le
> vrai fichier est `.muninn/mycelium.db`. Sky a demandé un deep audit pour
> savoir s'il y a d'autres conneries en série.
>
> 8 agents au total ont scanné le repo (4 drifts doc-vs-reality + 4 hooks).
> Ce plan compile **toutes les findings + plan d'exécution** chunk par chunk.

---

## 📋 État au 13 mai 2026 11h45 — Audits livrés

### Audit 1 (doc-vs-reality, 4 agents)

| Agent | Périmètre | Drifts critiques |
|---|---|---|
| 1 (doc-vs-code) | CLAUDE.md + README + QUICKSTART vs code | mycelium.json, LOC count, commands subset, test count |
| 2 (stats) | Tests/LOC/Q/version/bugs | tests 2608→2849, LOC 24731→26970, files 26→50, bugs 111→121 |
| 3 (commands+hooks) | argparse vs docs | CLAUDE.md liste 8 commandes / 32 réelles, 5 env vars orphelines |
| 4 (paths) | Tous chemins doc vs disque | mycelium.json + chunk9_final_verdict + memory/b + meta path flou |

### Audit 2 (hooks, 4 agents)

| Agent | Périmètre | Findings |
|---|---|---|
| 1 (mapping) | Rôle des 10 hooks | 7 actifs, 1 dormant intentional, 2 orphans (config_change + notification_audit) |
| 2 (qualité code) | Lecture entière des 10 hooks | Score 8.8/10. 2 bugs critiques bridge_hook (stdout L88 + logger L100), 1 bug post_failure (bare except) |
| 3 (wiring) | settings.local.json vs install_hooks() | MATCH parfait, 7 hooks wired correctement |
| 4 (régression F5) | Diff bridge/post_failure/subagent | Commit F5 (0e9a8f7, 2026-05-10) a perdu `_log_hook_error` dans 3 hooks. muninn_install.py génère templates appauvris. Audit trail éteint. |

---

## 🎯 Chunks à exécuter (15 items)

### Chunk 1 — Drifts doc CRITIQUES (15 min)

- [ ] **1.1** CLAUDE.md:158 : `.muninn/mycelium.json` → `.muninn/mycelium.db`
- [ ] **1.2** README badge + body : `2608 tests` → `2849+ collected` (badge dynamique)
- [ ] **1.3** README "Bugs status" : `111 RESOLVED, 0 OPEN` → `121 RESOLVED, 0 OPEN` (header BUGS.md déclare 90+10+8+1+1+4+7=121)
- [ ] **1.4** CLAUDE.md "État du projet" : `24 731 lignes, 26 fichiers core` → `26 970 lignes, 50 fichiers core`
- [ ] **1.5** Cohérence Q-modularity : README dit 0.670, CLAUDE.md dit 0.664. Source de vérité = `forge --modularity` (live = 0.670). Aligner CLAUDE.md sur 0.670.
- [ ] **1.6** README "1335 entries" → "1336" (drift +1 entry à recount)

### Chunk 2 — Drifts MOYENS (10 min)

- [ ] **2.1** CLAUDE.md L189-197 syntaxe : `muninn.py X` → `muninn-mem X` (post E.3 rename)
- [ ] **2.2** CLAUDE.md L188-198 : étendre les 8 commandes à 32 (ajouter cube, metrics, zones, think, trip, quarantine, etc.)
- [ ] **2.3** CLAUDE.md env vars table : audit les 5 orphelines (`MUNINN_BENCH_N`, `MUNINN_EVAL_*`, `MUNINN_RUN_REAL_*`, `MUNINN_TEST_REPOS`). Soit grep dans tests/ et confirmer "harness only", soit supprimer.

### Chunk 3 — Hooks régression F5 (45 min — LE PLUS COMPLEXE)

- [ ] **3.1** Lire `muninn_install.py` `_generate_bridge_hook()` + `_generate_post_tool_failure_hook()` + `_generate_subagent_start_hook()`
- [ ] **3.2** Réintégrer la fonction `_log_hook_error()` dans les 3 templates générés
- [ ] **3.3** Vérifier que `engine/core/_hook_logger.py` est toujours présent + signature `log_hook_event(name, context, exc)` inchangée
- [ ] **3.4** Re-run `muninn-mem init` dans tmp_path + vérifier que les hooks générés contiennent maintenant `_log_hook_error`
- [ ] **3.5** Optionnel : restore les versions riches sur disque (Sky's hooks live) en commitant les versions historiques OU en re-runnant `init`

### Chunk 4 — Hooks bugs qualité (20 min)

- [ ] **4.1** `bridge_hook.py:88` : Secret Sentinel `print(warning)` → `sys.stderr.write(warning + "\n")`
- [ ] **4.2** `bridge_hook.py:100-112` : wrapper `muninn.bridge_fast()` avec try/except + `_log_hook_error("bridge_fast", e)`
- [ ] **4.3** `post_tool_failure_hook.py:96` : remplacer bare except par try/except spécifique (`json.JSONDecodeError`, `OSError`, `ValueError`) avec log
- [ ] **4.4** Same fix dans `muninn_install.py` template generators (pour que `init` futur génère le bon code)

### Chunk 5 — Orphans hooks → ACTIF (Sky décision A, 30 min)

- [ ] **5.1** `config_change_hook.py` : ajouter au wiring `install_hooks()` (event = manual/cron OU PostToolUse Write sur `.claude/settings.local.json`)
- [ ] **5.2** `notification_audit_hook.py` : ajouter au wiring (event = Notification)
- [ ] **5.3** Update H.0 garde-fou : retirer ces 2 hooks du WHITELIST_DORMANT_HOOKS (puisque maintenant actifs)
- [ ] **5.4** Re-run `muninn-mem init` chez Sky pour appliquer le wiring
- [ ] **5.5** Test pin : vérifier que les 2 hooks tirent vraiment quand event fire

### Chunk 6 — README cleanup additionnel (15 min)

- [ ] **6.1** Repo Structure section : `.muninn/anomalies.jsonl` + `.muninn/hook_errors.log` → marquer "[generated on first error/cube run]"
- [ ] **6.2** Repo Structure section : `memory/b*.mn` → marquer "[legacy fallback, see H.5b note]"
- [ ] **6.3** Hook table README : updater les 10 hooks avec les vrais statuses (post wire orphans)

### Chunk 7 — Verification finale (10 min)

- [ ] **7.1** Full pytest sweep (non-UI) → 0 régression
- [ ] **7.2** `forge --modularity` → Q reste ≥ 0.67
- [ ] **7.3** `muninn-mem doctor` post-fix → output cohérent
- [ ] **7.4** Vérifier toutes les corrections dans un seul `git diff` propre

---

## 🚫 Hors scope ce battle plan

Reportés à plus tard, voir leur memory/plan :
- **H.6b** vault auto-lock (deferred indéfiniment, voir memory `project_h6b_vault_deferred.md`)
- **K.2** LaBSE embeddings (long terme 2.0.0)
- **Phase J** refactor zombies + tests greppy renforcement
- **Décision release PyPI prod** 1.1.0 ou bump 1.2.0
- Investigation possibles autres erreurs cachées (audit 3 en cours, 4 agents additionnels)

---

## 🎯 Workflow par chunk (anti-bullshit RULE 4)

```
1. READ        Lire le code/doc existant (Read tool, pas cat)
2. TEST PIN    Test pin AVANT le fix (si applicable)
3. RED         pytest → ROUGE attendu (prouve test mord)
4. FIX         Implémenter minimal
5. GREEN       pytest → VERT (output verbatim)
6. WIRE        Update config / settings si applicable
7. CHECK       Sanity grep pour confirmer pas de drift résiduel
8. FORGE       Si engine/core/ touché (RULE 5)
9. STAGE       git add fichiers précis
```

Un seul commit final après tous les chunks → push → watch CI.

---

## 🧭 Pourquoi ce plan

- Le cousin Claude a trouvé 1 drift (mycelium.json)
- Sky a demandé deep audit → 8 agents ont trouvé ~15 items concrets
- Sky a aussi pointé "j'oublie qui fait quoi avec ces hooks" → mapping clair dans Audit 2 Agent 1
- Sky décide A (= wirer les 2 orphans config_change + notification_audit)
- Audit 3 (additionnel) cherche s'il y a d'autres trous (4 agents en parallèle)

Une fois ce battle plan exécuté : la doc reflète exactement la réalité, les hooks
ont leur audit trail réintégré, les orphans deviennent actifs, et les bugs qualité
code sont corrigés. **Drift = 0** au prochain audit.
