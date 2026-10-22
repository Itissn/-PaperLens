# PaperLens

[![CI](https://github.com/Itissn/-PaperLens/actions/workflows/ci.yml/badge.svg)](https://github.com/Itissn/-PaperLens/actions/workflows/ci.yml)

An inspectable research-paper assistant built with Python, FastAPI and local Qwen inference. It combines hybrid retrieval, source-grounded answers and bounded Agent tool calling. English application, with Chinese learning guides.

## What it does

- Ingest PDFs with physical-page citations; extract text, image-page OCR, tables and supported formula source regions.
- Compare BM25, neural retrieval and reciprocal-rank fusion, with optional cross-encoder reranking.
- Run a local Qwen Agent that can list/search papers and read source pages within a bounded tool budget.
- Stream model drafts and progress, support cancellation, and check source quotations/numbers and learned textual entailment before showing a verified answer.
- Persist conversations and contextual follow-ups in SQLite, with optional admin/viewer login and owner isolation.
- Expose health, strict deployment readiness and process-local metrics.

## Architecture

```text
English web UI -> FastAPI -> bounded Agent / direct retrieval
                             | tools: list, search, read page
                             v
                 SQLite + BM25 + BGE vectors + cross-encoder
                             |
                      local Qwen / llama.cpp
                             |
                 source checks + ONNX NLI -> cited response
```

Final source-page reads performed by the controller are labelled separately from model-selected tool actions. Answers can still be incomplete, wrong or conservatively withheld; a passed smoke check is not a general accuracy claim.

## Run with Docker Compose

Python 3.12 and a working Linux Docker daemon are required. Runtime models, credentials, user data and local reports are excluded from this repository and image.

```bash
python -m pip install httpx==0.28.1 pymupdf==1.27.2.3
python -m scripts.prepare_ci_assets
python -m scripts.container_preflight
docker compose build paperlens
docker compose run --rm --no-deps paperlens python manage.py user-add --username admin --role admin
docker compose run --rm --no-deps bootstrap
docker compose up -d paperlens
```

The administrator password is requested privately by the CLI. Open **http://127.0.0.1:8767**. Initial setup downloads the pinned public corpus and local inference assets; later app startup uses the persisted volumes. The model endpoint is internal to Compose. See [Docker guide](docs/DOCKER_GUIDE.zh-CN.md).

## Tests and continuous delivery

```bash
python -m pip install -r requirements-ci.txt
python -m pytest tests -q -p no:cacheprovider
# Opt-in: builds a separate image, runs real inference/OCR/auth/persistence,
# and removes only its uniquely named test containers and volumes.
python -m scripts.verify_container --run
```

GitHub Actions runs the fixture regression suite, then builds and exercises the Linux Compose stack with real local Qwen inference, OCR and container recreation. A successful main-branch push publishes the **same tested app image** to `ghcr.io/itissn/paperlens:sha-<commit>`; PR runs never publish. See the [workflow](.github/workflows/ci.yml) for actual checks and [Actions](https://github.com/Itissn/-PaperLens/actions) for run results. Configuration alone does not prove a successful run.

Image publication is continuous delivery. GitHub Pages cannot run this Python/model service; an always-on live application requires a separate Docker host, HTTPS and deployment-specific configuration. No cloud host is provisioned by this repository.

## Learning and scope

- [Learning guide](docs/LEARNING_GUIDE.zh-CN.md)
- [Agent guide](docs/AGENT_GUIDE.zh-CN.md)
- [CI/CD guide](docs/CI_CD_GUIDE.zh-CN.md)

Built as an AI-assisted personal engineering and learning project. The baseline corpus contains three public research papers; no private recruitment documents or correspondence are included. The pinned Qwen2.5-3B model uses the upstream **qwen-research** license; model weights are downloaded separately, not included in the app image. Upstream asset licenses remain applicable.