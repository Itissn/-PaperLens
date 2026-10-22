# 本机部署与使用

适用于已安装便携 Python、依赖和本地模型的 Windows 电脑。此方式不依赖 Docker、WSL 或云服务器，也不需要重启 Windows。

## 打开与停止

1. 在 PaperLens 项目目录中双击 `Start.cmd`。脚本复用已运行的项目服务；未运行时启动它们，并打开浏览器。
2. 访问 http://127.0.0.1:8765 。保持后台进程运行即可使用；关闭浏览器不会停止服务。
3. 需要停止时，在项目目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Stop.ps1
```

执行策略参数仅作用于这一次 PowerShell 进程，不更改电脑的全局策略。停止脚本核验 PID、可执行文件和项目命令后，只停止本项目的服务。

## 使用 Agent

在页面选择 Agent 工作流和本地 Qwen 模型，输入英文研究问题。可先尝试：

> How many random seeds were used in the BN-GPGLS experiments? Search the papers and inspect the relevant page.

查看回答下面的工具调用轨迹、引文与来源检查；点击引文检查 PDF 原页。通过一项示例检查不代表所有问题都会回答正确。

## 地址与数据

- 网页：`127.0.0.1:8765`；本地 Qwen：`127.0.0.1:8766`；可选 Ollama：`127.0.0.1:11435`。
- 以上服务只监听回环地址，供这台电脑访问。本机模式没有开放外网端口；不应直接把当前免登录模式转发到公网。
- 当前模式为单机个人使用，无需登录。电脑进入睡眠、关机或项目进程停止后，页面无法工作；再次运行 `Start.cmd` 恢复。
- `data/` 保存 PDF、SQLite 索引、账户和对话；`.cache/` 保存下载的模型与本机配置；`reports/` 保存检查证据。
- 不要删除这些目录来“清理缓存”；尤其不要删除 SQLite 的 `-wal` 文件。跨电脑迁移时先停止项目服务，再复制完整的 `data/`、`.cache/` 和运行环境。仓库本身不包含这些本地文件。
- 本轮验证的数据库快照位于被 Git 忽略的 `.cache/deployment-backups/`；快照只是数据库备份，不能替代 PDF 和模型文件的完整备份。

## 部署边界

这是本机部署，没有云服务器费用，也不是长期在线的网站。GitHub Actions 已验证 Linux 容器并发布镜像；本机 Windows 的 Docker 引擎仍待以后由你选择重启并验证。本机原生程序可以先独立使用。

最新本机检查见 `reports/local-deployment-verification.json`。检查真实模型回答会消耗本机计算资源，不调用付费模型 API。
