# Muninn v0.8

## Architecture
- 9 compression layers (L1-L7 regex, L8 LLMLingua, L9 LLM)
- Mycelium: co-occurrence tracker, .muninn/mycelium.json
- Tree: L-system fractal, memory/tree.json
- Budget: 30K tokens max loaded

## Compression ratios (tiktoken)
- verbose_memory.md: x4.1, 100% facts
- WINTER_TREE.md: x2.6, 96% facts
- README.md: x1.6, 93% facts

## Key files
- engine/core/muninn.py — main engine v0.8
- engine/core/mycelium.py — co-occurrence network
- engine/core/tokenizer.py — tiktoken wrapper
- memory/tree.json — tree metadata
- memory/root.mn — always loaded at boot

## Dependencies
- Required: Python 3.13
- Optional: tiktoken (token counting), llmlingua (L8), anthropic (L9)
