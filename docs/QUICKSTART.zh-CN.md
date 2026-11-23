# PaperLens 本地精简版

目的：导入英文论文 PDF，通过关键词与语义检索找到证据，显示原文摘答或本地 Qwen 回答，并保留可核对的页码。

## 开始使用

1. 双击 `Start.cmd`。首次运行会准备独立 Python 环境和检索模型，需要联网；以后直接启动。
2. 浏览器打开 http://127.0.0.1:8765 。点击 **Import PDF** 导入论文，或按评估说明下载公开示例论文。
3. 默认 **RAG · Direct retrieval / Extractive · No LLM** 是原文摘答。先问一个自己知道答案的问题，再点击引用页码核对。
4. **Local Qwen · RAG** 使用本地模型组织回答；**Agent · Tool calling** 允许模型调用搜索和读页工具。本地 CPU 生成可能较慢。
5. 新电脑需要 AI 模型时，双击 `Setup-AI.cmd`。下载和校验完成后重新启动。无需付费 API 密钥。
6. 双击 `Stop.cmd` 停止本项目服务。仅关闭浏览器不会停止服务。

示例问题：How does DCL-GPGLS estimate instance difficulty?

## 文件用途

- `paperlens/`：PDF 处理、检索、回答、Agent、来源校验和 API。
- `web/`：网页界面。
- `scripts/`：必要的模型准备与示例论文下载；小型测试 PDF 工具。
- `tests/`：保留核心回归测试，避免后续修复破坏功能。
- `docs/`：中文学习教程、Agent 说明和本机使用说明。
- `data/`：论文、索引及对话历史。不要当成缓存删除。
- `evaluate.py` 与 `evaluation/*.json`：检索评估与标注案例。
- `reports/`：本机运行日志和评估结果。

## 本机文件位置

Python、依赖、模型及本地推理凭据放在 `%LOCALAPPDATA%\PaperLens`，不放进 OneDrive。

只监听本机地址；这不是公开网站。答案和来源检查都可能有误，请核对论文。
项目使用预训练模型，是 AI 辅助的个人工程与学习项目，不是从头训练大语言模型。

深入阅读：[中文学习教程](LEARNING_GUIDE.zh-CN.md) · [Agent 教程](AGENT_GUIDE.zh-CN.md)
