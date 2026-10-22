# PaperLens 的 GitHub CI/CD

仓库：https://github.com/Itissn/-PaperLens
运行记录：https://github.com/Itissn/-PaperLens/actions

## 每次提交发生什么

1. GitHub 的 Ubuntu runner 安装 Python 3.12 和项目依赖，执行自动回归测试。此层同时包含测试替身控制流检查和下载固定 NLI 模型后的真实改写／矛盾检查，不代表一般模型质量。
2. 只有第一层通过，容器任务才下载固定版本的公开 Qwen GGUF，并核验大小和 SHA256。模型密钥临时生成，不写进代码或日志。
3. 构建 Linux 应用镜像，通过独立 Compose 项目验证真实模型 Agent/SSE、引用检查、登录权限、OCR、表格/公式和容器重建后的数据持久化。
4. 删除本次测试的容器及数据卷。测试或清理失败，流水线失败，不发布镜像。
5. 对 main 分支的 push，保留刚才通过验证的同一个应用镜像，用 GitHub 自动提供的短期 GITHUB_TOKEN 发布到 GHCR。PR 不执行发布。镜像标签包含完整提交 SHA，便于确定版本。

## 怎样判断真的通过

进入 Actions，打开对应提交的运行记录。两个任务都为绿色，才表示这些检查完成；查看容器测试 JSON 中的 passed、cleanup_passed，以及发布步骤输出的镜像名。运行结果与配置文件是两种证据。

第一次下载并构建需要时间；真实模型检查也可能失败。需要按日志定位依赖、网络、Linux 权限或模型行为问题，不能把失败改成跳过后再宣称全部通过。

## 这是不是线上部署

这里实现自动测试和镜像交付。GHCR 存放镜像，GitHub Pages 只托管静态页面，均不会自动运行 FastAPI 和 Qwen。长期在线服务仍需要选定 Docker 主机；再配置 HTTPS、账号、域名、持久卷、资源限制和备份。

本机 Windows 的 Docker 引擎若等待系统组件重启激活，GitHub Linux runner 可以独立执行容器验证。远端成功也不等于本机已经可用。

## 换电脑

克隆仓库，安装 Python 3.12 和 Docker；按 README 下载公开模型并初始化本机密钥及管理员。需要迁移私人会话时，应单独安全备份数据卷；GitHub 没有你的模型密钥、数据库、会话或下载缓存。

当前镜像不含 Qwen 权重；使用模型时仍需遵守上游 qwen-research 许可。本次镜像已通过匿名 manifest 请求验证，返回的摘要与发布日志一致，可公开拉取。具体测试版本、结果和摘要见 [验证记录](CI_VERIFICATION.md)。
## Linux 的文件型密钥

Compose 本地文件型 secret 使用 bind mount，不能依靠 uid/gid/mode 字段改变源文件权限。新建的模型密钥放在仅宿主机本人可进入的 0700 目录内，文件为 0644，让容器内 UID 10001 可读取挂载后的单个文件。既有密钥不会被替换或改权限。验证器在下载索引资产前实际检查非 root 用户能读取密钥；只检查读取成功，不输出密钥。若自行提供既有密钥，应按实际主机权限配置容器访问。
