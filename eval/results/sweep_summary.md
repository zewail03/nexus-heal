# NEXUS-HEAL Retrieval Sweep — Results

Ran **9** configurations against the 40-query labeled set.

## Ranking metric

Composite score = 0.35·hit@3 + 0.30·mrr + 0.20·ndcg@3 + 0.15·precision@3. Weighted toward Hit@3 (app uses top_k=3) and MRR (first-hit rank).

## Winning config

- **Embedding:** `chroma-default-minilm-onnx`
- **chunk_size:** 300
- **overlap:** 0
- **Composite score:** 0.9002
- **Hit@1/3/5:** 0.850 / 0.950 / 1.000
- **MRR:** 0.907  |  **NDCG@3:** 0.890  |  **Precision@3:** 0.783
- **Wall-clock:** ingest 5.951s, queries 15.725s (393.13 ms/query)

## Top 3 configurations

| Rank | Embedding | chunk | overlap | Score | Hit@1 | Hit@3 | MRR | NDCG@3 | P@3 | Ingest(s) | Query(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `chroma-default-minilm-onnx` | 300 | 0 | 0.9002 | 0.850 | 0.950 | 0.907 | 0.890 | 0.783 | 5.951 | 15.725 |
| 2 | `chroma-default-minilm-onnx` | 300 | 100 | 0.8927 | 0.875 | 0.925 | 0.905 | 0.887 | 0.800 | 7.254 | 13.582 |
| 3 | `chroma-default-minilm-onnx` | 500 | 50 | 0.8911 | 0.850 | 0.950 | 0.890 | 0.881 | 0.771 | 6.098 | 12.685 |

## All configurations (ranked)

| Embedding | chunk | overlap | Score | Hit@1 | Hit@3 | Hit@5 | MRR | NDCG@3 | P@3 | R@3 | Ingest(s) | Query(s) | ms/query |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `chroma-default-minilm-onnx` | 300 | 0 | 0.9002 | 0.850 | 0.950 | 1.000 | 0.907 | 0.890 | 0.783 | 0.925 | 5.951 | 15.725 | 393.13 |
| `chroma-default-minilm-onnx` | 300 | 100 | 0.8927 | 0.875 | 0.925 | 0.950 | 0.905 | 0.887 | 0.800 | 0.900 | 7.254 | 13.582 | 339.55 |
| `chroma-default-minilm-onnx` | 500 | 50 | 0.8911 | 0.850 | 0.950 | 0.975 | 0.890 | 0.881 | 0.771 | 0.925 | 6.098 | 12.685 | 317.12 |
| `chroma-default-minilm-onnx` | 500 | 0 | 0.8903 | 0.850 | 0.950 | 1.000 | 0.903 | 0.875 | 0.746 | 0.912 | 5.088 | 15.731 | 393.27 |
| `chroma-default-minilm-onnx` | 800 | 0 | 0.8829 | 0.850 | 0.950 | 1.000 | 0.907 | 0.888 | 0.671 | 0.925 | 4.826 | 14.987 | 374.68 |
| `chroma-default-minilm-onnx` | 300 | 50 | 0.8731 | 0.825 | 0.925 | 0.950 | 0.881 | 0.859 | 0.754 | 0.887 | 6.474 | 14.076 | 351.9 |
| `chroma-default-minilm-onnx` | 500 | 100 | 0.8695 | 0.825 | 0.925 | 0.975 | 0.879 | 0.860 | 0.733 | 0.900 | 4.459 | 11.7 | 292.5 |
| `chroma-default-minilm-onnx` | 800 | 100 | 0.8617 | 0.825 | 0.925 | 0.975 | 0.879 | 0.843 | 0.704 | 0.875 | 4.325 | 12.043 | 301.08 |
| `chroma-default-minilm-onnx` | 800 | 50 | 0.8608 | 0.850 | 0.900 | 0.975 | 0.891 | 0.849 | 0.725 | 0.863 | 5.912 | 13.075 | 326.87 |
