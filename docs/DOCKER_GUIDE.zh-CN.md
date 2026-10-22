# PaperLens Docker 使用与学习说明

2026 年 10 月 22 日，GitHub Linux 环境已通过全部 15 项容器验证并发布应用镜像。具体提交、运行链接和摘要见 [验证记录](CI_VERIFICATION.md)。

Docker 路径包含公开资源初始化、非 root 应用、独立模型服务和真实集成验证。当前远端运行结果请看 [GitHub Actions](https://github.com/Itissn/-PaperLens/actions)，持续交付流程见 [CI/CD 学习说明](CI_CD_GUIDE.zh-CN.md)。本机 Docker 是否就绪需要单独检查；远端 Linux runner 的结果不代表本机 Windows 引擎已可用。
## 三个服务如何配合

| 服务 | 职责 | 数据 |
| --- | --- | --- |
| bootstrap | 下载固定公开论文和 ONNX 资源，建立向量索引，试运行嵌入／重排／NLI／OCR模型，写入完成标记 | 与应用共享命名数据卷 |
| llm | 用 CPU 运行 Qwen 3B，提供内部模型 API | 仅读取指定 GGUF 和独立密钥文件 |
| paperlens | 英文网页、登录、检索、Agent、历史、OCR | data／cache／reports 三个独立命名卷 |

应用等待 bootstrap 成功完成后启动。模型服务可能仍在加载，此时应用保持可访问，但 readiness 返回 503；模型加载完成且密钥认证通过后才返回 200。不依赖模型镜像里安装 curl。

默认容器网页是 http://127.0.0.1:8767 ，原生版本仍使用 8765。模型端口不发布到主机。首次初始化需要网络，论文与模型保存在容器卷中；应用运行时的 Hugging Face 加载设为离线缓存模式。

## 已具备 Docker 环境后的启动步骤

以下命令需要在项目目录执行，并要求已存在可用的本地 Linux 容器引擎。这份说明不会安装它。

先检查现有 Qwen 3B 文件的长度、SHA-256 和密钥文件格式：
```powershell
.\.runtime\python.exe -X utf8 -m scripts.container_preflight
docker compose config --quiet
docker compose build paperlens
```

首次创建管理员，密码在私密提示中输入，不写入 Compose 环境变量、命令参数或镜像：
```powershell
docker compose run --rm --no-deps paperlens python manage.py user-add --username saining --role admin
docker compose up -d
```

已有同名管理员时无需再次创建；命令不会覆盖账户。首次启动需下载公开资源和执行 CPU 推理，可能耗时较长：
```powershell
docker compose ps --all
docker compose logs --tail 60 bootstrap
docker compose logs --tail 60 llm
Invoke-RestMethod http://127.0.0.1:8767/api/readiness
```

正常停止：
```powershell
docker compose down
```

命名卷保留论文、账户、会话和模型缓存。删除卷会清除这些容器数据。原生 data 目录没有挂载进容器，两套数据相互独立。

如果初始化失败，修复网络或磁盘问题后：
```powershell
docker compose run --rm --no-deps bootstrap
docker compose up -d
```

成功标记仅在初始化所有阶段通过后写入。固定论文、NLI、重排模型及其配置有公开文件校验值；损坏或不完整的固定资源先改名保留，再重新下载。不能修复的错误会使初始化失败，不会伪装成成功。

## 自动集成验证

只检查主机资源，不调用 Docker daemon：
```powershell
.\.runtime\python.exe -X utf8 -m scripts.verify_container
```

环境具备后，显式运行真实容器验证：
```powershell
.\.runtime\python.exe -X utf8 -m scripts.verify_container --run
```

脚本会建立唯一的 paperlens-verify-* Compose 项目、选择空闲端口、生成仅在内存和私密标准输入中使用的测试密码。它检查：

1. 镜像构建、公开论文／索引／ONNX 初始化、严格就绪状态。
2. 未登录访问限制、管理员登录、viewer 权限和会话归属。
3. 混合检索、真实 Qwen Agent SSE 草稿／工具调用／页面引用／来源与 NLI 检查。
4. Linux 容器中的扫描 PDF OCR、表格和公式区域。
5. 强制重建应用容器后，账户、登录会话、索引和对话仍保留。
6. 退出登录后会话失效。

结束或失败后，只清理此次唯一项目的容器、数据卷和镜像。CI 可用 --keep-image 仅保留全部检查及清理成功后的同一镜像用于发布；测试数据卷仍删除。不会停止原生进程或删除主机 GGUF。若清理失败，报告仍判定失败并保留项目名称供排查。遇到模型拒答、引用不满足要求或推理失败，也不会算通过。

结果写入 reports/container-runtime-verification.json，报告不记录密码、密钥、Cookie 或完整回答。实际执行状态和提交版本以对应 GitHub Actions 运行记录为准。

## 文件与检查边界

- Dockerfile：固定直接 Python 包版本，非 root 应用用户；应用根文件系统只读，缓存和临时空间可写。
- compose.yaml：启动依赖、localhost 端口、指定单文件只读 GGUF、密钥文件和命名卷。
- paperlens/deployment.py：检查初始化标记、资源大小、数据库／索引、管理员和经过认证的模型发现。
- scripts/container_bootstrap.py：实际初始化和校验；scripts/container-assets.json 记录固定公开资源 SHA-256。
- scripts/container_preflight.py：主机文件检查，既不安装 Docker，也不输出密钥。
- scripts/verify_container.py：需要 --run 才执行真实容器验证。
- scripts/setup_compose_validator.py：可选的 Windows 便携 Compose 配置检查器，校验官方二进制 SHA-256；不安装软件或操作容器。

readiness 是运行依赖检查，不是答案准确率证明；日常检查资源文件存在及大小，完整 SHA-256 在 bootstrap 时核对。直接依赖已固定，基础 Python 镜像标签和传递依赖仍不是完整不可变锁定。跨平台 pip dry-run 检查了 Linux wheel 候选，但环境标记仍由 Windows 主机求值，不能代替 Linux 镜像构建。

Linux 主机使用时，模型和密钥文件还需对容器相应用户可读；不要通过把密钥写到镜像／环境变量中解决文件权限问题。正常使用前，仍需完成实际构建、挂载权限、模型调用和数据持久化的容器验证。

依据：[Compose 启动顺序](https://docs.docker.com/compose/how-tos/startup-order/)、[Compose 密钥文件](https://docs.docker.com/compose/how-tos/use-secrets/)、[服务定义](https://docs.docker.com/reference/compose-file/services/)、[所选 llama.cpp 版本](https://github.com/ggml-org/llama.cpp/blob/b10868/tools/server/README.md)。
