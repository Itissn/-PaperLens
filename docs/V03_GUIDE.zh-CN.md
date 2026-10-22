# PaperLens v0.3：新增功能怎么用、怎么学

我们继续用中文讲解，程序本身使用英文。

## 1. 多轮对话和历史
正常提问后，结果会存到左侧 Conversations。点 New 开始新会话，点标题恢复，点 × 删除。刷新或重启程序后，SQLite 中的历史仍在。

追问如 “How many seeds did it use?” 会从同一会话上一轮的问题和引用论文标题补充上下文。程序保留 original_question 和 resolved_question，便于核对它如何理解代词。这是有边界的上下文规则，不是无限记忆，也不是已经验证可靠的通用指代消解。每个会话最多 50 轮。

代码：paperlens/history.py、api.py。学习重点是所有查询都携带 owner，避免不同账户读取彼此的历史。

## 2. 流式输出与停止
点击 Search & read 或 Run Agent 后，会逐步显示检索、工具执行、生成和验证状态。语言模型真正返回的片段会形成 UNVERIFIED DRAFT；只有检查完成才成为正式结果。

Stop 会断开请求并取消后续处理，未完成草稿不会保存成成功对话。正在进行的非流式规划请求可能需要等它结束或超时，才能释放那次计算；生成阶段可在下一片段返回时取消。不要把“按钮立即响应”理解为所有 CPU 计算立即结束。

代码：llm_transport.py 读取模型的真实流；events.py 提取临时文本；api.py 用有界队列转成 SSE；web/app.js 消费流并在最终事件后保存显示状态。最多两个进行/等待中的研究任务，其余请求会得到明确的容量提示。

## 3. Agent 的引用页补读
模型仍然可能先读错页。现在回答形成后，程序会检查最终引用页是否都已经读过；缺少的页会执行额外的 controller 读页，最多四页。失败时不展示未经读页核对的正式回答。

工具轨迹分别标明模型调用与程序补读。真实测试中，模型读第 10 页，答案引用第 8 页，程序自动补读第 8 页后才返回。覆盖了引用页仍不证明答案含义正确。

## 4. 回答完整性和语义检查
程序用本地 ONNX NLI 模型筛查支持原文是否支持回答；同时保留来源、数字检查。明确要求六项时，会要求实际列出六个不同名称，而不是用框架介绍代替。

实际结果有进步，也有问题：现在能从方法页生成三种算子的评价份额和执行率，共六个具体名称，但 NLI 模型对这类数学组合描述仍会误拒绝。界面提供 Review withheld draft · not verified，可以展开草稿和支持原文，自己核对。不能把这个状态当成“系统已经证明错误”或“已经保证正确”。

代码：quality.py 为列举题补充定义上下文；local_llm.py 使用列举专用 JSON Schema；completeness.py 检查个数与名称；semantic.py 运行真实 NLI。阈值是开发策略，不是可靠度承诺。

## 5. 扫描件、表格和公式
上传时保留 Use OCR for image pages。文本不足的图片页会在本机执行 OCR，再切块、索引。OCR 最多处理 30 页/次，整份 PDF 仍受页数、大小和文本总量限制。检索结果会标明 OCR 来源与识别分数。

点击论文卡片 Inspect page，选择物理 PDF 页码，再点 Inspect page：
- Tables 提取数字 PDF 中可识别的表格几何结构和单元格。
- Formula candidates 保留公式文字、坐标与原始截图。
- 简单表达式，如 f(x)=x+1，可转换成受限语法树和 LaTeX 文本。
- 复杂排版、隐式乘法、分行公式等可能只提供原文截图；没有通用公式识别或数学证明保证。

符号解析使用 AST 白名单，不执行 PDF 中的表达式。扫描表格不会因此自动获得可靠的单元格结构；OCR 和几何表格提取是两个不同步骤。

运行 scripts/document_smoke.py，reports 中会生成 sample-scanned.pdf、sample-structured.pdf、sample-formula.png 和结果 JSON。它们是合成学习数据，可手动上传试验，不包含私人资料。

## 6. 登录与权限
当前桌面启动仍默认本地免登录。可选保护模式已用独立测试账户和浏览器实测：
- admin 可以上传、修复索引、创建用户；
- viewer 可以阅读和提问；
- 论文库共享，会话按账户隔离；
- 密码使用加盐 PBKDF2，数据库仅保存会话 token 哈希；cookie 为 HttpOnly、SameSite Strict，有效期八小时。

启用前，先创建管理员：
```powershell
.\.runtime\python.exe manage.py user-add --username saining --role admin
```
密码会私密提示输入与确认。不要写进命令行、文档或聊天。随后 Stop，再运行 manage.py serve --auth；若继续用 Start.cmd，把 .cache/app-settings.json 的 auth_required 改成 true 后重启。新 viewer 用相同命令加 --role viewer 创建。

这是本地可运行的账户控制，不代表已经完成公网生产部署。未对外发布。

## 7. Ollama、监控与 Docker
Ollama 现在也做过真实流式调用，使用项目内便携版和现有已校验 GGUF，没有安装 Windows 服务。当前在 localhost:11435，默认服务仍由 Start/Stop 脚本控制。规划阶段用 llama.cpp；回答可以选择 Ollama。

API 提供 /api/health、/api/readiness、管理员可读的 /api/metrics。Readiness 目前检查数据库，并报告语义模型资产状态，不是全链路负载或模型准确性检测。

Docker 配置和检查脚本已经整理，镜像元数据已核对。按你之前的决定，仍没有启用 WSL/虚拟机组件、没有安装 Docker、没有运行容器，也没有重启 Windows。

## 8. 面试中怎样如实描述
你可以在真正读懂并重跑后，介绍 AI 辅助完成的本地应用：检索与精排、工具调用、真实 SSE、会话持久化、账户隔离、OCR、结构化来源、语义筛查和失败案例。

需要明确区分：功能实现、单元测试通过、真实小样本联调和生产可靠性。你的论文已有算法/模型评估经验；这个项目补充的是 AI 应用工程与系统集成的实践。
