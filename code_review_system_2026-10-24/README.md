# 智能代码审查与漏洞修复系统

这是项目的第一版网站，已接入 Python AST 基础静态分析、项目目录扫描、可配置的大语言模型审查，以及修复方案预览与静态复检。项目和扫描数据目前保存在内存中。

网页中的单文件静态分析现已增加审查历史与版本对比，使用本地 SQLite 保存代码快照和结果；这部分在服务重启后仍可查看。

网站还提供 GitHub Pull Request 审查入口：输入公开 PR 地址后，系统会读取 PR 的变更文件，并对其中的 Python 文件运行现有静态分析；勾选“大语言模型审查”后，会复用当前配置的 Codex 或 OpenAI 兼容服务。当前版本只读取和展示结果，不会自动向 GitHub 发布评论或修改远程分支。

项目已提供 PyCharm 运行配置。用 PyCharm 打开本目录后，选择 `Code Review System` 运行配置即可启动网站服务。

## 启动方式

Windows 上直接双击项目目录中的 `start.cmd`，脚本会检查依赖、选择空闲端口并打开网站首页。首次安装依赖需要联网。

要在手机浏览器访问，双击 `start-mobile.cmd`。电脑与手机连接同一 Wi-Fi，脚本会显示当前 WLAN 地址、访问网址和本次启动的登录密码。在手机浏览器输入脚本显示的网址，弹出登录框后输入用户名 `review` 和该密码。电脑上的脚本窗口需保持打开；电脑更换 Wi-Fi 或重启脚本后，以窗口新显示的网址和密码为准。此方式适合可信的局域网，访问使用 HTTP。

也可以在 PowerShell 中执行：

```powershell
cd D:\PythonEmv\codeSpace\PythonProject\code_review_system
.\start.cmd
```

手动启动后端：

```powershell
cd code_review_system
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

运行测试：`python -m pip install -r requirements-dev.txt`，然后执行 `python -m pytest tests -q`。

启动后访问（以默认的 8000 端口为例；若端口被占用，`start.cmd` 会显示实际端口）：

- `http://127.0.0.1:8000/`：网站首页
- `GET http://127.0.0.1:8000/api/health`
- `GET http://127.0.0.1:8000/docs`

## 当前已实现的代码分析接口

```http
POST /api/analysis/python
Content-Type: application/json
```

请求示例：

```json
{
  "file_path": "demo.py",
  "code": "import os\\nos.system(user_input)"
}
```

接口会返回规则编号、文件位置、风险等级和问题说明。目前包含动态代码执行、命令执行、危险反序列化、硬编码敏感信息、直接拼接 SQL、关闭 TLS 证书验证和语法错误等基础规则。

在网站上运行静态分析后，选中一个问题并点击“生成修复方案”。当前仅对符合条件的 `yaml.load(stream)` 生成 `yaml.safe_load(stream)` 候选代码；其他规则返回需要人工处理的原因。页面会展示原代码、候选代码和候选代码的静态复检结果。点击“应用到编辑器并复检”只会修改浏览器编辑器中的内容，不会写入服务器上的源码文件。静态复检不能证明程序行为正确，应用后仍需审阅代码并运行项目测试。

分析结果下方的“代码作用与完整代码”区域会根据当前代码、函数/类结构、导入模块和静态分析结果生成基础作用总结；如果已经生成修复候选代码，会优先展示候选的完整代码，并提供复制按钮。导出的审查报告也会包含这段总结和完整代码。

## 审查历史与版本对比

分析结果支持按风险等级筛选，并搜索规则编号、问题描述或文件路径。筛选后的数量会同时显示，导出的报告仍包含完整结果。同类项目对比与后续功能建议见 [功能对比记录](docs/github-feature-comparison-20261023.md)。

网页点击“开始静态分析”后，自动保存当前文件的完整代码和静态分析结果。在“本次问题变化”中显示新增、仍存在和未再检出的问题；左侧“审查历史”可按文件路径查询、分页查看，并将历史代码与结果载入审查台继续修改。导出报告包含历史记录编号与对比结果。

- 首个可解析版本只建立基线；后续版本与同一文件路径的最近可解析版本比较。不同项目的同名文件请填写不同路径。
- 按规则、函数/类位置和 AST 结构进行匹配，忽略注释、空行和位置移动，并保留同类问题的重复次数。修改调用结构或重命名函数可能被视为旧问题消失、新问题出现。
- 语法错误时仍保存记录，但暂停比较，防止错误地把未完成分析的问题标为消失。连续分析相同代码与结果会复用最新记录。
- “未再检出”只代表当前静态规则不再命中，不能替代业务测试。历史只覆盖网页中的单文件静态分析，项目扫描与 GitHub PR 结果暂不归档。
- 默认数据库位于 `data/review_history.sqlite3`，保存原始代码，保留此文件即可保留历史；可用 `CODE_REVIEW_HISTORY_DB` 指定其他数据库文件。单份代码最多 1 MB。

接口：`POST /api/reviews` 分析并保存，`GET /api/reviews?file_path=demo.py&limit=30&offset=0` 查询历史，`GET /api/reviews/{id}` 获取完整版本。原有 `POST /api/analysis/python` 仍为不保存的分析接口。

功能设计参考 [reviewdog 的差异过滤](https://github.com/reviewdog/reviewdog#filter-mode)、[Gitleaks 的基线比较](https://github.com/gitleaks/gitleaks#creating-a-baseline)以及 [DefectDojo 的漏洞跟踪](https://github.com/DefectDojo/django-DefectDojo)。本项目对比基于编辑器版本快照，不要求 Git 仓库或额外插件。

## 代码知识图谱与函数理解

网页左侧“代码知识图谱”提供独立的代码理解工作区。可以粘贴长代码、从审查台导入、选择多个 `.py` 文件、选择项目文件夹，或上传 ZIP。点击“试试多文件示例”可直接查看订单接口、业务服务、价格计算和订单记录之间的调用关系。

- 在本机解析 Python AST，提取文件、类、函数/异步函数/方法，以及包含、导入、调用、继承关系。每个节点保留路径、行号、签名、参数、返回类型注解和源码。
- 支持常见相对导入、导入别名、包重导出、局部函数、简单实例和实例字段绑定。重复调用合并为一条关系并保留调用行号；无法确定的目标标为“外部 / 未解析”，不会仅凭同名就连接函数。
- 基础说明优先展示文档字符串，否则概括可见的调用、分支、循环和 return 表达式。来源会明确标记，这类结构说明不等于业务语义理解。
- 点击“Codex 解释此节点”或“Codex 解释全部函数”，通过现有本机 Codex SDK 生成中文用途说明和当前解释范围内的协作流程。每批最多 8 个函数，可停止后续批次；已经完成的说明保留。每个节点发送最多 7000 个字符并标注是否截断，模型只能更新说明，不能新增图的边。单次 Codex 请求限时 180 秒；模型失败不影响基础图谱。
- 关系图支持函数调用 / 文件依赖 / 全部结构切换、文件筛选、外部调用开关、所选节点邻居筛选、拖动与缩放。为保持可读性，画布最多绘制 120 个节点、400 条关系，完整节点保留在索引和 JSON 导出中。
- 单次最多 150 个 Python 文件，单文件最多 512 KB，源码合计最多 3 MB；ZIP 最大 10 MB。忽略 `.venv`、`node_modules` 等依赖目录，ZIP 在内存中读取、不落盘解压、不执行上传代码。普通文件导入按 UTF-8 读取；ZIP 支持 Python 源文件编码声明。

接口：`POST /api/knowledge/graph` 接收 `{"files":[{"path":"app/main.py","code":"..."}]}`；`POST /api/knowledge/archive` 接收 ZIP 二进制请求体；`POST /api/knowledge/explain` 接收相同 files 及最多 8 个 `node_ids`。结构图在本机生成；Codex 解释会把所选源码片段提交到当前登录账户使用的模型服务。图谱暂存在浏览器内存，可导出 JSON；刷新后需重新导入。

范围：当前是结构知识图谱，不是 Joern CPG，也没有实现完整 CFG、控制/数据依赖或污点追踪。Python 动态分派、复杂字段、反射、星号导入以及部分继承调用可能无法解析；实例方法关系属于静态推断，图中以虚线区分。源码文档字符串也可能过时，应结合实际源码核对。

## GitHub Pull Request 审查

网页左侧的“GitHub PR”入口调用 `POST /api/github/pr/review`。公共仓库可以直接读取；私有仓库或访问频繁时，在启动服务前设置 Token：

```powershell
$env:GITHUB_TOKEN = "github_pat_你的令牌"
python run.py
```

Token 只从后端进程的环境变量读取，不放在网页请求中，也不会写入项目文件。建议使用只读仓库权限的 fine-grained token。系统目前只分析 PR head 中可读取的 Python 文本文件，单次最多 30 个文件；其他文件会在结果中标记为跳过。

修复接口为 `POST /api/repair/python`，请求包括 `file_path`、`code`、所选告警的 `rule_id`、`line` 和 `column`。接口会核对告警位置；找不到对应告警时返回 422。网站的“导出审查报告”会下载包含当前分析、修复方案和修复前分析结果的 JSON 文件。

项目创建时也可以传入本地 Python 源码目录：

```json
{
  "name": "demo-project",
  "language": "python",
  "source_path": "D:/workspace/demo-project"
}
```

随后调用 `POST /api/scans` 创建扫描任务，扫描完成后通过 `GET /api/scans/{scan_id}/findings` 查看结果。当前扫描是同步执行的，后续再替换为异步任务队列。

## 当前目录说明

- `app/api`：HTTP 接口
- `app/schemas.py`：请求和响应模型
- `app/services`：业务服务层
- `app/analyzers`：静态分析器扩展位置
- `app/llm`：大语言模型扩展位置
- `app/repair`：漏洞修复扩展位置
- `app/repositories`：数据存储扩展位置
- `app/knowledge`：代码知识图谱、归档导入和函数说明
- `app/tasks`：异步任务扩展位置
- `frontend`：网站页面、样式和浏览器交互

项目和扫描任务暂存在服务内存中，重启后会清空；单文件审查历史保存在 SQLite，代码知识图谱暂存在浏览器内存中。

## 大语言模型审查

接口为 `POST /api/review/llm`，默认使用 `codex` 本机模式，也可以将 `provider` 设为 `openai-compatible` 使用外部 OpenAI 兼容服务。

使用 Codex 时，需要先在本机 Codex 中完成登录，并配置可选的 `CODEX_MODEL`、`CODEX_WORKDIR`。Codex 审查固定使用只读沙箱和禁止审批，网页默认已经选择 Codex 本机模式。若改用外部 OpenAI 兼容服务，再配置 `LLM_API_KEY`、`LLM_BASE_URL` 和 `LLM_MODEL` 环境变量。

Codex SDK 通过本机 Codex app-server 工作，不需要在项目中保存 API Key。发送审查请求时，请求中的源代码和静态分析结果会提交给当前登录的 Codex 账户；避免将不应外发的代码提交审查。

Codex 请求示例：

```json
{
  "provider": "codex",
  "file_path": "demo.py",
  "code": "import os\\nos.system(user_input)",
  "context": "登录模块",
  "static_findings": [
    {"rule_id": "PY-CMD-001", "severity": "HIGH", "line": 2}
  ]
}
```
