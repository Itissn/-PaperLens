# PaperLens

PaperLens is a local PDF reader for researchers. Ask a question across papers, read the passages behind the answer and open each citation at its physical PDF page.

## Why build it?

When two papers discuss the same method, finding a relevant answer is only half the task. A reader still needs to identify which paper made the claim and inspect the surrounding text. PaperLens keeps that trail from question to source page.

## How it works

| Stage | Implementation |
|---|---|
| Import | Extract text, retain physical page numbers and store overlapping chunks in SQLite. |
| Retrieve | BM25 ranks matching terms. Optional embeddings support semantic search. Hybrid mode combines the two rankings using reciprocal-rank fusion. |
| Answer | Extractive mode returns passages verbatim. Optional local generation uses retrieved evidence and checks source references. |
| Verify | Open the cited page in the original PDF. Each passage carries its document ID and physical page number. |

## Results

On three versioned public papers, BM25 returned a labelled page and topic in its top five passages for **10 of 12 answerable development questions** and **3 of 4 answerable challenge questions**. It abstained on **1 of 3** unanswerable development questions and **0 of 4** challenge questions. This makes source inspection especially important when a question may fall outside the library. An agent prepared the small, domain-specific label sets before evaluation. [Evaluation and reproduction](evaluation/README.md)

![Three retrieved passages traced to the first page of a public paper](docs/paperlens-evidence.png)

The demonstration used one four-page paper, 32 chunks and extractive retrieval. All three passages led back to page 1. [Demonstration details](docs/DEMONSTRATION.md)

All 53 repository tests passed locally, including PDF upload, OCR, retrieval, physical-page citations and the pinned entailment model. The retrieval scores above measure the BM25 path.

## Try the reader

Use a Python 3.11+ environment. The following starts local search for text PDFs.

```bash
python -m pip install "fastapi>=0.115,<1" uvicorn python-multipart pypdf numpy
python manage.py serve
```

1. Open `http://127.0.0.1:8765`. Choose **Lexical · BM25** before importing a text PDF. Leave OCR off for text PDFs.
2. Select **Extractive · No LLM** and clear **Rerank evidence**. Ask a question using terms from the paper.
3. Open a citation to check its source. The app retains imports and their indexes across restarts. Pass `--data-dir PATH` to choose a library.

On Windows, **Start.cmd** prepares the full environment for hybrid retrieval. **Setup-AI.cmd** prepares optional local generation. **Stop.cmd** stops the service. These setup paths need internet access on first use. [Windows guide in Chinese](docs/QUICKSTART.zh-CN.md)

## Code and skills

- **Python, FastAPI, SQLite** — [ingestion, local storage and API](paperlens/)
- **Information retrieval and RAG** — [ranking](paperlens/retrieval.py), [source checks](paperlens/grounding.py) and [labelled evaluation](evaluation/)
- **Browser interface** — [upload, question and citation views](web/)
- **Testing and operations** — [regression tests](tests/), [automation and Windows launchers](scripts/) and [learning guide](docs/LEARNING_GUIDE.zh-CN.md)
