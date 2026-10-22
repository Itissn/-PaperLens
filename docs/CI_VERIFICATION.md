# Verified CI and container delivery

Validation snapshot: **22 October 2026**.

- Tested source commit: `2024246207818af97080d5606d6d8dbabe6c7f52`.
- [Successful GitHub Actions run](https://github.com/Itissn/-PaperLens/actions/runs/39715621797).
- Execution environment: GitHub-hosted Ubuntu 24.04, Linux amd64.

| Check | Observed result |
| --- | --- |
| Python regressions, including real NLI and OCR | 86 passed |
| Full Docker integration | 15 stages passed |
| Local Qwen Agent over SSE | Generated a source-backed answer; 3 native tool calls; drafts and source checks passed |
| Authentication and isolation | Admin/viewer permissions, private conversations and logout revocation passed |
| Synthetic documents | Recognized OCR text, exact table cells, restricted formula parsing and PNG region rendering passed |
| Container recreation | Accounts, sessions, documents, index and conversation history persisted |
| Cleanup | Only the unique verification project's containers/volumes were removed; cleanup passed |
| Delivery | The same tested app image was published to GHCR |

## Published image

Tag:

`ghcr.io/itissn/paperlens:sha-2024246207818af97080d5606d6d8dbabe6c7f52`

Manifest digest:

`sha256:942acc68e4193c615c4610c679ddb86ece4dd267e5fa550383bb7b4ca3278982`

An independent anonymous registry manifest request returned this same digest after publication. The image is publicly pullable. Downloaded Qwen, embedding, reranker and NLI assets remain separate from the app image; RapidOCR's packaged OCR assets are installed with its dependency.

## Scope

The Agent smoke case uses three fixed public papers and verifies the seed-count protocol on physical PDF page 8. It is an end-to-end functional check, not a general answer-accuracy benchmark. Learned checks can reject valid answers or miss errors. Formula support is restricted parsing with source-region rendering.

These results establish the Linux container path and automatic image delivery. They do not establish that a particular Windows Docker engine is ready, or provision an always-on public application server. Regression coverage includes volatile-cache exclusion from the asset inventory, the model's actual health-check port, non-root secret reads and valid structured-document upload.