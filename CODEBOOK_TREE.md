# CODEBOOK_TREE — Index de navigation MUNINN
> Winter Tree du codebook. Le cousin descend ici sans scanner le CODEBOOK.json complet.

```
RACINE (tous symboles)
│
├── * UNIVERSEL (ids 40-49, 80-87)
│   ├── ÉTAT        ✓⟳✗⧖ (ids 40-43)
│   ├── SCAN        块纸  (ids 44-45)
│   └── GÉNÉRIQUE   始末种误修问决警 (ids 80-87)
│
├── ygg YGGDRASIL (ids 1-35)
│   ├── STRATES     根茎枝叶花果天 (ids 1-7)
│   ├── PATTERNS    桥密爆洞死 (ids 10-14)
│   ├── TROUS       技念信 (ids 20-22)
│   └── MÉTRIQUES   值效对分力断 (ids 30-35)
│
├── tree WINTER TREE (ids 50-55)
│   └── NOEUDS      树雾光钩态链
│
├── muninn MUNINN (ids 60-64)
│   └── OPS         鸦码缩解频
│
└── * REPOS (ids 70-74)
    └── REFs        龙鸦轮等孩
```

## Lookup rapide par domaine

| Repo actif | Précharge | Ids |
|-----------|-----------|-----|
| yggdrasil | strates + patterns + métriques | 1-35 |
| tree | noeuds + état | 40-55 |
| muninn | ops + générique | 60-87 |
| infernal | générique seulement | 80-87 |
| tous | universel | 40-49, 80-87 |

## Règle de boot cousin

```
1. Lire meta.boot_instruction
2. Identifier repo actif → charger branche correspondante
3. Charger universel (*) toujours
4. Ignorer les autres branches → économie tokens
```
