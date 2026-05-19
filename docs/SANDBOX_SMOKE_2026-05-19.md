# Sandbox smoke checklist — battle plan unifié 2026-05-19

> CHUNK C13 deliverable. To run after every UX-touching chunk to catch
> regressions that automated tests can't (the cube 3D actually spins,
> the toggle button is visible, etc.).
>
> All steps below assume `cd /home/sky/Bureau/muninn-sandbox`.

## 1. Boot the UI

```bash
./run-ui.sh muninn-ui
```

**Expected** : window opens, 4-panel layout visible
(NeuronMap top-left, FileHeatmap middle-left, TreeView bottom-left,
Terminal top-right, DetailPanel bottom-right).

- [ ] window opens
- [ ] no crash on launch
- [ ] no Qt errors in stderr

## 2. Scan a small repo

```bash
/scan /tmp/btree-only
```

**Expected** : terminal shows scan progress ticker, mycelium gets
populated, neuron panel updates with cube nodes.

- [ ] scan completes
- [ ] terminal progress visible
- [ ] cube panel updates

## 3. C9 mode toggle — Mycelium ↔ Reconstruction

Top-right of the neuron panel : look for the `MYCELIUM` button.

- [ ] Click on it → button flips to `RECO` (orange).
- [ ] Cube colors switch instantly between degree-based and NCD-based.
- [ ] Click again → back to `MYCELIUM` (cyan).
- [ ] Quit + relaunch UI → previous mode is preserved
      (`~/.muninn/ui_config.json` clé `neuron_color_mode`).

## 4. Run a reconstruction

```bash
/reconstruct /tmp/btree-only/btree_google.go --max-cycles=2
```

**Expected** : during the run, cube colors update from grey → green / red
as each cube SHA-matches or fails.

- [ ] cube colors change live
- [ ] terminal shows per-cycle progress

## 5. C8 live neighbor refresh

At each CYCLE_END, the mycelium graph re-edges. Watch the cube panel.

- [ ] arêtes (edges) entre neurons changent entre cycles
- [ ] neurons ne disparaissent PAS (couleurs NCD/SHA préservées)
- [ ] Laplacien relance sans freeze

## 6. C10 DetailPanel — click on a cube

Click on a cube neuron in the panel.

**Expected** : DetailPanel (bottom-right) shows :
- [ ] SHA: ✓ ou ✗ (vert / rouge)
- [ ] NCD: 0.XXX (vert si <0.1, orange si <0.3, rouge sinon)
- [ ] Gap lines: N
- [ ] Unknown idents: N (avec preview)

Click on a non-cube neuron (mycelium normal) → ces 4 champs sont
**masqués**.

## 7. C11 file heatmap (bottom panel sous cube 3D)

Le panneau middle-left = file heatmap.

- [ ] le fichier reconstruit s'affiche
- [ ] gutter gauche colorisé : vert/rouge/orange par ligne
- [ ] les couleurs reflètent le state du cube qui contient chaque ligne

## 8. C12 fractal zoom — Ctrl+wheel

Focus sur le NeuronMap, presser **Ctrl+molette** :

- [ ] roll up → bascule x1 → x2 → x3 → x1
- [ ] nombre de neurons divisé par ~2/3 visuellement
- [ ] couleurs paintent au degree max (worst NCD wins)
- [ ] plain wheel (sans Ctrl) garde pan/zoom transform

## 9. Screenshot final

Capture le 4-panel + DetailPanel populé + heatmap colorisé.
Coller le path dans le commit body C13.

- [ ] screenshot captured
- [ ] joint au PR / commit final

---

## Si quelque chose échoue

1. Note l'étape précise + ce qui était attendu vs constaté.
2. Vérifier `~/.muninn/pipeline_trace.jsonl` pour les événements émis.
3. Si crash : `journalctl --user -t muninn-ui` pour le stderr complet.
4. Ouvrir un BUG-XXX dans `BUGS.md` avec repro steps.
