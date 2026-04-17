# Cube Reconstruction Results — Full Battery (2026-04-15 to 2026-04-17)

## 1. NCD Benchmark: HTM vs QTM (analytics.py, deepseek-coder:6.7b, 20 cubes)

| Face | Tokens | Avg NCD | NCD<0.3 | Erreurs |
|------|--------|---------|---------|---------|
| 10   | 80     | 0.641   | 1/20 (5%)  | 2/20 |
| 11   | 88     | 0.659   | 0/20       | 0/20 |
| 12   | 96     | 0.645   | 0/20       | 0/20 |
| 13   | 104    | 0.566   | 1/20 (5%)  | 9/20 |
| **14** | **112** | **0.622** | **0/20** | **0/20** |
| 15   | 120    | 0.641   | 1/20 (5%)  | 5/20 |
| 26   | 208    | 0.727   | 0/20       | 17/20 |

**Winner: face=14 (112 tok)** — best NCD with zero errors and zero timeouts.

## 2. Go vs Python (server.go, deepseek-coder:6.7b, 20 cubes)

| Config | Face | Avg NCD | NCD<0.3 | Erreurs |
|--------|------|---------|---------|---------|
| HTM (88 tok) | 11.4 | 0.518 | 6/20 (30%) | 0/20 |
| QTM (112 tok) | 14.7 | 0.566 | 4/20 (20%) | 0/20 |

Go with HTM (88) performs better than QTM (112) — Go has shorter natural blocks.

## 3. Wave Test: Haiku API (server.go, 3 cubes, 3 waves x 3)

| Cube | Size | Best NCD | Evolution | Memory helps? |
|------|------|----------|-----------|---------------|
| 1 (L1-L27) | 99 tok | 0.737 | 0.749 -> 0.738 | Yes, -1.5% |
| 2 (L28-L50) | 352 tok | 0.651 | 0.654 -> 0.680 | v2a1 best, then plateau |
| 3 (L51-L51) | 162 tok | 0.800 | 0.800 -> 0.800 | No, total plateau |

Memory injection shows marginal improvement. Haiku plateaus quickly (temperature=0.0 = deterministic).

## 4. Model Comparison (server.go, 5 cubes, single attempt)

### Haiku 4.5
| Cube | NCD | What happened |
|------|-----|---------------|
| 5 | 0.570 | Wrong struct (ErrorResponse vs PaginatedResponse) |
| 10 | 0.412 | Partial match, extra code |
| 15 | 0.263 | Near-perfect circuit breaker code |

### Sonnet 4.6
| Cube | NCD | What happened |
|------|-----|---------------|
| 5 | 0.735 | Wrong struct (Metrics vs PaginatedResponse) |
| 10 | **0.182** | Circuit Breaker header near-perfect |
| 15 | **0.082** | Almost SHA match — tab difference only |
| 20 | 0.351 | Logic close but reformulated |
| 25 | **0.140** | NewMetricsCollector near-perfect |

**Sonnet gets NCD=0.082** on cube 15. Near-SHA territory.
3/5 cubes under NCD=0.2 with Sonnet vs 0/3 with Haiku.

## 5. Key Findings

### Why SHA-256 never matches
- At atomic level (112 tok), cubes are isolated fragments
- Neighbors don't always reference the cube's specific content
- Example: PaginatedResponse struct has no usage in neighbors, so LLM invents wrong struct
- Cubes WITH context in neighbors (circuit breaker, metrics collector) reconstruct near-perfectly

### Why historical Sonnet results showed NCD=1.000
- RESULTS.txt and CONVERGENCE.txt had ALL NCD=1.000 — means reconstructions were EMPTY
- ClaudeProvider.generate() returns "" on API failure without error
- Those benchmark runs were broken (API issue), not real results

### Memory injection (B40)
- Works: previous attempts are compressed by Muninn L1-L7 and injected in prompt
- Marginal improvement at atomic level with Haiku (temperature=0.0 = deterministic)
- Needs: higher temperature for variety, and/or progressive levels for more context

### God's Number metric confirmed
- QTM face=14 (112 tok) = optimal for Python (best NCD + zero errors)
- HTM face=11 (88 tok) = better for Go (shorter blocks)
- 3x3x3 QTM (208 tok) = too big, causes timeouts and worse NCD
