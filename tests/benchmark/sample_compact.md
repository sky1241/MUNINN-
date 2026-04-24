# Muninn v0.9+

## Architecture
- 11 compression layers, 25 filters (L0-L7 regex, L10-L11 Carmack, L9 LLM)
- Mycelium: co-occurrence tracker, .muninn/mycelium.json
- Tree: L-system fractal, memory/tree.json
- Budget: 30K tokens max loaded

## Compression ratios (tiktoken)
- verbose_memory.md: x4.1, 100% facts
- WINTER_TREE.md: x2.6, 96% facts
- README.md: x1.6, 93% facts

## Key files
- engine/core/muninn.py — main engine v0.9+
- engine/core/mycelium.py — co-occurrence network
- engine/core/tokenizer.py — tiktoken wrapper
- memory/tree.json — tree metadata
- memory/root.mn — always loaded at boot

## Dependencies
- Required: Python 3.13
- Optional: tiktoken (token counting), llmlingua (L8), anthropic (L9)
