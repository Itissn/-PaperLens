# Retrieval evaluation

Can a reader find the annotated source page among the first five passages? Each positive hit requires the correct versioned paper, physical PDF page and at least one labelled text anchor. Multiple matching chunks on the same page count once for page recall.

## BM25 baseline

| Label set | Hit in top 5, answerable | Mean annotated-page recall | Mean reciprocal rank | Abstained, unanswerable |
|---|---:|---:|---:|---:|
| [Development](eval_cases.json) | 10 / 12 | 0.750 | 0.725 | 1 / 3 |
| [Challenge](eval_challenge.json) | 3 / 4 | 0.625 | 0.417 | 0 / 4 |

The reader indexed 33 physical pages from three [fixed public paper versions](../scripts/download_corpus.py) into 151 chunks, using a 120-word window and 25-word overlap. Retrieval used BM25 and the extractive answer mode, with embedding, reranking and generation disabled. This run used Python 3.11.9 with pypdf 7.1.1. Corpus and label hashes are recorded in each generated report.

The challenge set shows a failure mode. When all four out-of-scope questions were asked, the reader returned passages each time. Retrieval hits and verbatim quotes measure different things from answer correctness. An agent prepared both small, domain-specific sets before the relevant retrieval runs. The labels are incomplete and have no independent human validation.

## Reproduce

Install the reader dependencies from the [quickstart](../README.md) and run these commands from the repository root.

```bash
python -m scripts.download_corpus
python manage.py index --lexical-only
python evaluate.py --lexical-only --report reports/bm25-development.json
python evaluate.py --lexical-only --labels evaluation/eval_challenge.json --report reports/bm25-challenge.json
```

The downloader retrieves the versioned PDFs on first use. The evaluator selects exactly those source URLs and excludes unrelated imports. To compare semantic, hybrid and reranked retrieval, use the full dependencies, index vectors with `python manage.py index`, and omit `--lexical-only` from the evaluator. Raw local reports include per-question passages, configuration, hashes and warm-run latency. They stay in the ignored `reports/` folder.
