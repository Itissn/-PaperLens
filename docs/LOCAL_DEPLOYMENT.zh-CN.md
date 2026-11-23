# 本机启动与文件位置

双击 Start.cmd 打开 http://127.0.0.1:8765；双击 Stop.cmd 停止后台服务。
首次启动会准备本机 Python 环境、安装依赖并下载检索模型，需保持联网。
Setup-AI.cmd 下载本地 Qwen 与证据校验模型；模型可用后 Start.cmd 会自动启动它。

运行环境和模型：%LOCALAPPDATA%\PaperLens（不在 OneDrive）。
论文、索引和历史：项目 data/。日志：项目 reports/。
本机模型服务端口：8766。网页端口：8765。

初次体验选 RAG · Direct retrieval 和 Extractive · No LLM，导入 PDF 后提问。
使用 AI 选择 Local Qwen · RAG；体验工具调用再选择 Agent · Tool calling。
上传、检索和回答均在本机运行；本机模型不需要付费 API。
CPU 生成可能需要几十秒或更长，请查看进度，也可以取消。

复制到另一台电脑时，需要在新机器重新准备环境和模型；保留 data/ 才能保留论文及历史。
关闭浏览器不等于停止后台服务。不要删除 data/ 或 SQLite 的 -wal 文件来清理空间。
