# PaperLens Agent：运行、原理与学习练习

## 运行
双击项目目录的 Start.cmd，打开 http://127.0.0.1:8765 。将“Workflow”选为“Agent · Tool calling”，保留“Local Qwen · RAG”回答方式。试问：

> How many random seeds were used in the BN-GPGLS experiments? Search the papers and inspect the relevant page.

本机 CPU 执行涉及多次模型调用，可能需要一至数分钟。等待按钮恢复后查看“Agent tool trace”，展开每一步的参数和结果，点击最终引用核对 PDF 物理页码。结果可导出 JSON；不会上传到外部服务。

## 相比原来的 RAG，多了什么
普通 RAG 由程序直接执行一次检索，再请模型回答。这里模型会接收工具定义，返回真正的 function call；程序验证并执行参数，再将结果通过 role=tool 消息交回模型。模型可以重新检索、读页、结束研究。最终另有一次受来源约束的回答调用。

流程：问题 → 模型选工具/参数 → 参数检查 → 本地工具执行 → 工具结果反馈 → 下一轮规划 → 最终证据精排 → 生成与引用/数值检查。

这不是把预先写好的搜索步骤显示成模型行为。搜索词、具体论文和页码来自真实模型调用。但流程也有明确的控制策略：找到片段后，尚未读页时只提供 read_page 工具；模型从返回的候选论文/页码中选择。它是有边界的研究 Agent，不是无限自主执行器。

## 四个工具
| 工具 | 作用 | 边界 |
|---|---|---|
| list_papers | 查看库中论文、文档 ID、页数与状态 | 最多 20 条 |
| search_papers | 改写查询并进行混合检索与交叉编码器精排 | k=1–5；仅本地索引 |
| read_page | 读取指定论文的实际 PDF 页文本 | 已存在的文档 ID/页码；返回最多 4000 字符并标明截断 |
| finish_research | 请求结束取证，进入最终回答 | 至少成功读过一页 |

最多 4 轮、6 次工具调用，每轮最多接受 2 个调用。每次模型请求有 120 秒网络超时及输出上限。工具没有 shell、任意文件读取、发邮件或对外发布权限。参数由 Pydantic 检查：禁止多余字段、非法文档 ID、未知工具、越界页码与超大 k。达到轮次上限会明确记录停止原因；是否执行读页、最终引用页是否全部读过也分别显示。

## 已经真实观察到的例子
本机 Qwen2.5-3B Q4_K_M 曾选择：
1. search_papers，搜索 random seeds BN-GPGLS experiments；
2. read_page，读取 BN-GPGLS 的物理第 8 页；
3. finish_research。

最终回答各方法使用 30 个随机种子，所附原文为 “Each method is run with 30 random seeds matched across methods.”。完整调用参数、工具返回、token 计数及回答保存在 reports/agent-smoke.json；网页/API 验证另存 reports/agent-api-smoke.json（须实际运行测试后才会生成）。网页联调的另一次运行读了第 10 页，而最终正确引用来自搜索命中的第 8 页。这说明工具执行成功不等于选页正确；系统分别报告 read_pages 与 all_cited_pages_read，界面也区分读页动作和最终引用页的覆盖。单个成功例子不能证明 Agent 总能选对页码或回答完整。

## 哪些检查能做，哪些做不到
精排先筛掉低相关片段，模型再选择支持句编号。程序将编号解析回真实原文，不采用模型自行编造的引文字符串，并检查回答中的数值是否出现在支持句中。

这些检查能发现假引用、错来源、部分数字错误；不能证明语义蕴含、实验范围解释正确或回答完整。“读过一页”也不等于读对了页。请继续点击 PDF 核对。

模型初版 1.5B 曾在规划时重复文字、耗尽输出上限，或回答笼统。本机切换到已核验的 3B 版本进行研究学习；模型卡标为 qwen-research 许可，正式使用前应检查其适用条件。当前 llama.cpp 构建只接受字符串 tool_choice，代码使用 required，并通过缩小可用工具列表要求读页。输出截断会报告错误，不会假装执行成功。

## 读代码的顺序
1. paperlens/agent.py 的 MODELS / TOOLS：工具如何变成 JSON Schema。
2. native_plan：模型如何收到工具、返回 function.arguments 和 usage。
3. execute：为什么必须先验证参数；搜索和读页如何返回真实数据。
4. run：怎样反馈 role=tool，控制轮次、记录轨迹、收集证据。
5. paperlens/grounding.py：支持句编号、原文解析与有限数值检查。
6. paperlens/api.py 的 /api/agent：浏览器如何触发完整流程。

网页只展示可观察的调用和结果，不展示或伪造模型内部思维过程。

## 自己动手的三个练习
- 改问 DCL 的实例难度如何估计，观察搜索词与页码是否改变。先自己找答案，再评审输出。
- 比较同一问题的直接 RAG 与 Agent：相关页是否增加？耗时和总 token 多了多少？结果不一定更好。
- 运行 tests/test_agent.py，解释非法工具、错误文档 ID、循环上限的测试。再尝试在临时分支新增一个只读工具，并写真实失败用例。

运行自动检查：
```powershell
.\.runtime\python.exe -m pytest tests -q
.\.runtime\python.exe scripts/agent_smoke.py
# Start.cmd 已启动后，执行真正的网页/API/模型联调：
.\.runtime\python.exe scripts/agent_api_smoke.py
```

工具行为测试中的假模型用于验证控制逻辑；后两个脚本调用真实本地模型，不能相互替代。项目由 AI 辅助实现，能亲自解释、修改并重跑后，再将自己验证的部分用于面试。


v0.3 更新：现在会对未读的最终引用页进行单独标明的 controller 补读，不把它混入模型选择的工具轨迹。新加入流式草稿、历史会话、NLI 和列表完整性筛查；它们仍不能保证答案正确。详见 [v0.3 教程](V03_GUIDE.zh-CN.md)。
