# Retrieval evaluation

`eval_cases.json` and `eval_challenge.json` contain labelled questions and expected source pages. They belong here rather than among application entry points.

Run from the repository root:

```bash
python evaluate.py --labels evaluation/eval_cases.json
python evaluate.py --labels evaluation/eval_challenge.json --report reports/challenge-evaluation.json
```

These commands require the corresponding PDFs to be indexed and the configured retrieval and reranking models to be available. They compare lexical, semantic, hybrid and reranked retrieval. Scores depend on the supplied corpus and labels; they are not general-purpose RAG accuracy claims.

The scorer deduplicates page hits and checks topic anchors. Exact quotation checks establish whether text appears in a source, not whether the answer interprets it correctly. Generated reports belong in the ignored local `reports/` directory. Publish an evaluation report only with its corpus, model/configuration and test conditions.
