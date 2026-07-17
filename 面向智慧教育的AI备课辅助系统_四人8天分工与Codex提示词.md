# 面向智慧教育的 AI 备课辅助系统

## 四人 8 天开发分工与 Codex 提示词执行手册

> 适用对象：四名几乎没有完整项目开发经验、主要依靠 Codex 完成编码的小组成员。  
> 核心技术：Vue 3、TypeScript、FastAPI、MySQL、SQLAlchemy、DeepSeek、LangChain、RAG、Chroma、LangGraph、Slidev。  
> 使用原则：人负责明确目标、运行验收、同步代码和做最终判断；Codex 负责阅读现有项目、编写代码、运行测试和修复错误。

---

## 1. 最终要做成什么

系统面向小学教师。教师创建备课项目并填写年级、学科、课题、课时等信息，上传教材、课程标准或教案资料后，系统能够：

1. 解析资料并建立可追溯的知识库；
2. 根据教材与课标生成教学目标、重点难点和课堂流程；
3. 生成可用 Slidev 预览的课件；
4. 为每一页课件生成对应讲稿、提问和过渡语；
5. 生成基础、巩固、提高三个层次的练习及教师版答案解析；
6. 显示关键结论来自哪份资料、哪一页或哪个分块；
7. 允许教师只修改当前页、某个教学环节或某组练习；
8. 使用 LangGraph 展示多智能体的生成、审校、返修和人工确认过程；
9. 导出教师备课包和不含答案的学生练习包。

第一阶段只需稳定演示一个小学单课时案例，不要试图覆盖所有学段、所有学科，也不要开发复杂权限、在线协作或类似 PowerPoint 的拖拽编辑器。

---

## 2. 四个人的固定身份

### 成员 1：组长、系统集成、GitHub 与演示负责人

- 负责根目录、公共接口契约、Docker Compose、集成测试、代码合并、最终演示；
- 主要目录：仓库根目录、`contracts/`、`deploy/`、`tests/e2e/`；
- 不直接重写成员 2、3、4 已经完成的内部业务代码；
- 每天最后负责把其他三人的成果合并到 `main` 并做一次主流程检查。

### 成员 2：Vue 3 前端负责人

- 负责页面、路由、状态管理、表单、任务进度、课件预览、来源查看、版本和导出界面；
- 主要目录：`frontend/`；
- 只通过接口访问后端，不能在前端写死 AI 生成结果或直接连接 MySQL。

### 成员 3：FastAPI、MySQL 与工程接口负责人

- 负责 FastAPI、MySQL 表、SQLAlchemy、Alembic、文件上传、任务状态、产物版本、导出接口和部署；
- 主要目录：`backend/app/` 中除 `ai/` 之外的目录、`backend/migrations/`、`backend/tests/`；
- 维护 `backend/requirements/base.txt`，不能把密钥写入代码。

### 成员 4：AI、RAG、Skills 与 LangGraph 负责人

- 负责 DeepSeek、LangChain、Chroma、资料解析、检索、五类教学 Skills、生成链和 LangGraph；
- 主要目录：`backend/app/ai/`、`backend/tests/ai/`、`backend/requirements/ai.txt`；
- AI 输出必须结构化、可校验、可追溯，禁止伪造资料来源。

---

## 3. 小白每天怎样使用 Codex

每天每个人都按下面的顺序操作：

1. 打开 GitHub Desktop，点击 **Fetch origin**，然后将本地 `main` 更新到最新版本。
2. 从最新 `main` 新建自己的当日分支，例如：
   - `day01-member1-integration`
   - `day01-member2-frontend`
   - `day01-member3-backend`
   - `day01-member4-ai`
3. 用 Codex 打开同一个本地仓库文件夹，确认 Codex 当前所在目录就是项目根目录。
4. 复制本手册中属于自己当天的整段提示词，原样发给 Codex。
5. Codex 工作时如果询问普通技术选择，让它按照提示词里的默认方案继续；只有涉及删除大量文件、覆盖他人代码、修改项目范围或需要真实账号密钥时才暂停确认。
6. Codex 完成后，重点看它最后报告的三项内容：修改了哪些文件、运行了哪些命令、哪些测试通过。
7. 自己按照“完成标志”点开页面或调用接口。不会运行时，直接对 Codex 说：`请根据当前仓库，逐条带我完成今天的人工验收，不要假设我懂命令。`
8. 验收通过后在 GitHub Desktop 中查看 Changes。不要提交 `.env`、密钥、数据库文件、上传文件和 `node_modules`。
9. Commit 信息使用 `day01(member2): 完成前端工程骨架` 这种格式，然后 Push origin。
10. 在 GitHub 创建 Pull Request，目标分支选择 `main`，把 PR 链接发给成员 1。成员 1 合并后，其他成员再更新 `main`。

### GitHub 冲突时不要自己乱点

把下面这句话发给 Codex：

```text
当前分支与 main 合并时发生冲突。我是新手。请先只读检查 git status、冲突文件和双方差异，解释每个冲突分别属于哪个成员；保留双方有效功能并完成最小合并，禁止用 git reset --hard、禁止整文件覆盖、禁止丢弃未提交修改。合并后运行受影响模块的测试，并列出你如何解决了每个冲突。不要自动 push。
```

---

## 4. 所有提示词都遵守的底线

下面 32 段提示词已经把这些要求写进去，但四个人仍要记住：

- 先检查现有代码再修改，绝不能假设仓库为空；
- 保留其他成员的未提交修改，不越界重写其他模块；
- 不使用硬编码 AI 答案冒充真实生成；
- 不把 DeepSeek Key、数据库密码或 GitHub Token 写入源码；
- 不使用机器专属绝对路径；
- 不只“写代码”，还要实际运行测试、构建或接口检查；
- 测试失败时 Codex 应继续定位和修复，不能把明显错误留给小白；
- 不自动 push，不擅自删除大量文件；
- 完成后必须给出小白可执行的验收步骤。

---

# 第 1 天：范围冻结与工程骨架

## 成员 1：仓库、目录、协作与集成骨架

### 当天任务

建立统一仓库、目录边界、公共配置、GitHub 协作规则和 Docker Compose 骨架，让另外三个人能在同一套工程中开发。

### 直接发给 Codex 的提示词

```text
你现在是本项目的资深技术负责人和结对开发者。请直接在当前仓库完成“面向智慧教育的 AI 备课辅助系统”的第 1 天集成骨架。我是新手，请不要只给建议，要检查仓库并实际修改、验证。

项目目标：教师创建小学单课时备课项目，上传教材/课标，经过 RAG、DeepSeek、LangChain/LangGraph 生成教案、Slidev 课件、逐页讲稿和分层练习，并能追溯来源、局部修改、版本保存和导出。技术栈固定为 Vue 3 + TypeScript + Vite、FastAPI、MySQL 8、SQLAlchemy、PyMySQL、Alembic、DeepSeek、LangChain、Chroma、LangGraph、Slidev。

开始前必须：
1. 输出当前绝对路径，确认它是项目根目录；
2. 运行 git status 和简要目录检查，识别已有文件与未提交修改；
3. 如果仓库已有内容，必须复用并保护，不能重建覆盖；
4. 禁止运行 git reset --hard，禁止自动 push，禁止删除他人文件。

请完成：
1. 建立或补齐清晰目录：frontend/、backend/、backend/app/ai/、backend/requirements/、contracts/、deploy/、tests/e2e/、data/.gitkeep。
2. 创建根目录 .gitignore，至少忽略 .env、*.env.local、node_modules、dist、__pycache__、.pytest_cache、.venv、上传文件、MySQL/Chroma 本地数据、日志和 IDE 临时文件，但保留 .env.example 与 data/.gitkeep。
3. 创建根目录 .env.example，只放变量名与安全示例：MYSQL_HOST、MYSQL_PORT、MYSQL_DATABASE、MYSQL_USER、MYSQL_PASSWORD、DEEPSEEK_API_KEY、DEEPSEEK_BASE_URL、DEEPSEEK_MODEL、CHROMA_PERSIST_DIR、UPLOAD_DIR、VITE_API_BASE_URL。不得放真实密钥。
4. 创建 deploy/docker-compose.yml 骨架，包含 mysql:8 服务、utf8mb4 配置、健康检查、命名 volume；为 backend 和 frontend 预留服务配置。如果对应 Dockerfile 尚不存在，可保留明确注释，但 docker compose config 至少应能解析。
5. 在 contracts/ 创建 README.md，冻结公共字段：project_id、source_id、chunk_id、task_id、artifact_id、version_id、slide_id、trace_id；说明任务状态只能是 pending/running/succeeded/failed/cancelled。
6. 在根 README.md 只写项目简介、目录职责、四人分支边界、环境变量复制方法和当天能执行的最小命令。不要写冗长形式文档。
7. 如果仓库还不是 git 仓库，可以初始化 git；但不要创建远程仓库、不要使用我的 GitHub 凭据、不要 push。
8. 检查所有 YAML、环境变量示例和目录引用，确保无机器专属绝对路径。

验证要求：
- 运行 docker compose -f deploy/docker-compose.yml config；如果 Docker 未安装，先静态检查 YAML 并明确告诉我如何安装/验证，不要伪造成功；
- 检查 git status，确认没有真实 .env、密钥或大文件进入跟踪；
- 给出 Windows PowerShell 下从仓库根目录开始的准确命令。

完成后请用中文报告：A. 修改文件清单；B. 每个目录由谁负责；C. 实际运行的验证命令和结果；D. 我在 GitHub Desktop 中怎样提交；E. 另外三名成员拉取后第一步做什么；F. 仍存在的真实阻塞。不要自动 commit 或 push。
```

### 完成标志

- 四个人拉取后看到相同目录；
- `.env.example` 可复制但不含真实密码；
- Docker Compose 配置可以解析；
- GitHub 中没有密钥、上传资料或依赖目录。

## 成员 2：Vue 3 前端工程骨架

### 当天任务

建立可运行的 Vue 3 前端、五个页面和统一的加载/空白/错误状态。

### 直接发给 Codex 的提示词

```text
你是负责本项目 Vue 3 前端的资深工程师。请在当前仓库完成第 1 天前端骨架。我是新手，请直接检查、编码、安装依赖、运行验证并修复错误，不要只给代码片段。

先执行 git status 和目录检查。只主要修改 frontend/；可读取 contracts/ 和根配置，但不要重写 backend/、deploy/ 或其他成员未提交修改。禁止自动 push，禁止写死 AI 结果。

固定技术方案：Vue 3、TypeScript、Vite、Vue Router、Pinia、Axios，UI 组件优先使用 Element Plus；包管理器优先沿用仓库已有方案，没有时使用 pnpm。所有 API 地址必须读取 VITE_API_BASE_URL。

请完成：
1. 如果 frontend/ 为空，创建标准 Vue 3 + TypeScript + Vite 工程；如果已存在，基于现有工程补齐，不能覆盖。
2. 配置路由与基础布局，建立五个可访问页面：项目列表 /projects、知识库 /knowledge、备课工作台 /workbench/:projectId、质量检查 /quality/:projectId、导出 /export/:projectId。
3. 建立 src/api/http.ts：Axios 实例、baseURL、合理超时、响应错误转换；不得在组件中散落完整 URL。
4. 建立 Pinia 的 app/project 基础 store，至少能保存当前项目 ID 和后端健康状态。
5. 建立可复用 AppLoading、AppEmpty、AppError、StatusTag 组件，并在页面中展示真实的三态切换示例。示例只能是 UI 状态，不得伪造最终 AI 内容。
6. 建立顶部导航和左侧菜单，中文界面，标题使用“面向智慧教育的 AI 备课辅助系统”。
7. 增加 /health 的 API 函数与首页健康检查卡片；后端未就绪时要显示“暂时无法连接后端”和重试按钮，不能白屏。
8. 配置 ESLint 或项目已有 lint、TypeScript 检查和 production build。
9. 创建 frontend/.env.example，只包含 VITE_API_BASE_URL=http://localhost:8000。

验收与修复：
- 实际运行依赖安装、开发构建所需检查、typecheck 和 build；
- 修复所有由本次修改导致的错误和明显警告；
- 检查浏览器控制台和路由刷新问题；
- 如果无法启动浏览器，也要运行构建并给出准确启动命令，不得声称看过页面。

完成后用中文告诉我：修改文件、启动命令、访问地址、五个页面地址、验证结果、我应当点哪里验收、建议的 commit 信息。不要自动 push，不要让我手工补代码。
```

### 完成标志

- 前端能启动和构建；
- 五个页面可以跳转；
- 后端不可用时页面仍能正常显示错误和重试。

## 成员 3：FastAPI 与 MySQL 工程骨架

### 当天任务

建立 FastAPI 分层工程，连接 MySQL，完成迁移、健康检查和第一张项目表。

### 直接发给 Codex 的提示词

```text
你是负责 FastAPI、MySQL 和后端工程质量的资深开发者。请在当前仓库直接完成第 1 天后端骨架。我是新手，请从检查代码开始，实际实现、运行测试并修复，不要只描述步骤。

先运行 git status 并检查 backend/、contracts/、deploy/。主要修改 backend/ 中除 backend/app/ai/ 以外的内容，以及 backend/requirements/base.txt。不得覆盖 AI 成员的目录，不自动 push，不使用 SQLite，本项目关系型数据库固定为 MySQL 8。

请完成：
1. 创建或补齐分层 FastAPI 结构：app/main.py、api/routes/、core/config.py、core/database.py、models/、schemas/、services/、repositories/；保持适度简单，不要过度架构。
2. 使用 pydantic-settings 读取 .env，使用 SQLAlchemy 2.x + PyMySQL 连接 MySQL；连接串由独立变量拼装，字符集 utf8mb4，密码不得打印到日志。
3. 建立 Project 模型：id 使用 UUID 字符串或统一的 UUID 类型；字段至少包含 name、subject、grade、textbook_version、lesson_topic、lesson_count、status、created_at、updated_at。
4. 配置 Alembic 并生成首个迁移。不能使用启动时无条件 create_all 代替正式迁移；测试可以有独立策略。
5. 实现 GET /health 返回服务状态，GET /health/db 实际执行 SELECT 1 并返回 MySQL 状态；数据库失败时返回可读但不泄漏密码的信息。
6. 实现最小 POST /api/projects 与 GET /api/projects/{id}，使用 Pydantic 请求/响应模型和统一错误格式。
7. 配置 CORS，开发环境允许前端 localhost，但不要无条件允许任意来源和凭据组合。
8. 建立 pytest 测试：health、项目创建/查询、无效 ID；优先使用独立测试库或可替换 session，不得把测试写入生产库。
9. 在 backend/requirements/base.txt 写入准确依赖并提供 PowerShell 启动命令。

请实际验证：安装依赖、导入 app、运行测试；如果本机 MySQL/Docker 可用，执行迁移并实测 /health/db 和项目写入；如果不可用，不得退回 SQLite，请明确阻塞并完成可静态验证部分。主动修复本次引入的问题。

最后用中文报告：目录结构、数据库变量、迁移命令、启动命令、Swagger 地址、测试结果、前端应调用的接口、我怎样人工验收、建议 commit 信息。不要自动 push。
```

### 完成标志

- FastAPI 可以启动，Swagger 可打开；
- `/health` 正常；
- MySQL 可连接并完成迁移；
- 能创建和查询一个备课项目。

## 成员 4：DeepSeek、Chroma 与 AI 适配层

### 当天任务

完成 DeepSeek 和 Chroma 的最小真实连通，为后续 RAG 与 Agent 留下稳定接口。

### 直接发给 Codex 的提示词

```text
你是负责 DeepSeek、LangChain、RAG、Chroma 和 LangGraph 的资深 AI 工程师。请在当前仓库完成第 1 天 AI 基础层。我是新手，请检查现有项目后直接实现、运行最小测试并修复问题。

只主要修改 backend/app/ai/、backend/tests/ai/、backend/requirements/ai.txt；读取 backend 的配置方式并复用，不能另造第二套 .env，不能重写成员 3 的数据库与主应用。新增 Python 依赖只写 requirements/ai.txt。禁止将 DEEPSEEK_API_KEY 写入源码、测试、日志或提交记录，不自动 push。

请完成：
1. 创建清晰的 AI 配置和适配层：llm_client、embeddings、vector_store、exceptions、schemas。上层业务不能直接散落调用 SDK。
2. DeepSeek 使用其 OpenAI 兼容接口，base_url、model、api_key、timeout、temperature 均从环境变量读取；默认 temperature 适合结构化生成。
3. 创建统一 chat/invoke 方法，能返回文本、模型名、耗时和可选 token 使用信息；超时、无密钥、401、限流和网络错误转换为自定义可读异常。
4. Chroma 使用持久化目录，集合名必须包含安全处理后的 project_id，防止不同备课项目串库；封装 add_documents、similarity_search、delete_by_source。
5. Embedding 设计为可替换接口。优先使用仓库可用的中文 embedding；如果需要下载大模型，先检查环境，不要擅自下载数 GB 文件。可提供轻量默认方案和清楚的配置入口。
6. 实现 smoke test：向测试集合写入一段小学课文/课标样例，检索回来；若 DEEPSEEK_API_KEY 已存在，再让模型基于检索文本回答一个问题。没有密钥时测试应明确 skip，不能伪造成功。
7. 保证测试集合与测试数据可清理，不污染正式 Chroma 目录。
8. 写最少量模块说明，告诉成员 3 后续怎样调用，不要写无用长文档。

实际运行 AI 单元测试。检查日志中没有密钥。完成后用中文报告：修改文件、环境变量、最小调用示例、Chroma 隔离规则、真实运行/跳过的测试、成员 3 需要接入的函数、我怎样验收、建议 commit 信息。不要自动 push。
```

### 完成标志

- 有密钥时 DeepSeek 最小调用成功；无密钥时明确提示而不是崩溃；
- Chroma 能写入并检索测试文本；
- 不同 `project_id` 使用不同集合。

---

# 第 2 天：资料上传、解析与可追溯知识库

## 成员 1：冻结资料链路契约并完成第一次集成

### 当天任务

统一前端、后端和 AI 的文件/分块/任务字段，并用一个真实文件走通上传到检索。

### 直接发给 Codex 的提示词

```text
你是本项目第 2 天的集成负责人。请在当前仓库实际完成“上传资料→保存元数据→解析→写入 Chroma→检索并返回来源”的跨模块集成。项目是面向智慧教育的 AI 备课辅助系统，我是新手，请你主动检查、运行并修复。

开始前运行 git status，确认当前分支来自最新 main，阅读 contracts/、frontend/、backend/ 和 backend/app/ai/ 的现有实现。保护所有未提交修改，不整文件覆盖，不自动 push。你的主要修改范围是 contracts/、tests/e2e/ 和必要的集成胶水；内部问题应尽量在所属模块做最小修复并清楚说明。

请完成：
1. 冻结 SourceDocument、Chunk、IndexTask、SearchResult 的 JSON 契约。必需字段包括 project_id、source_id、filename、media_type、size、status、error_message、chunk_id、location、content、score、created_at；location 能表示 PDF 页码或 DOCX 标题/段落。
2. 统一状态流：uploaded→parsing→indexing→ready，失败为 failed；前端、后端和 AI 不得各用不同单词。
3. 准备一个小型、可公开使用的 TXT/Markdown 测试资料；如果仓库已有合适样例则复用。不要提交可能有版权或隐私的真实教材。
4. 建立端到端测试或可执行 smoke 脚本：先创建项目，再上传样例，触发索引，轮询状态，搜索一个确定问题，断言返回 content、source_id 和 location。
5. 发现字段不一致时统一到 contracts 定义，并同步最小修复；禁止用复制的假 JSON 绕过真实接口。
6. 检查不同 project_id 的检索不会串库；删除资料后 MySQL 元数据和 Chroma 向量均应处理。
7. 如果某模块 PR 尚未合并，先列出缺少的具体接口和阻塞，不要凭空造一套重复实现；仍要完成能完成的契约和测试框架。

请实际运行契约测试和能运行的端到端流程，修复本次发现的阻断问题。最后用中文报告：统一后的字段表、状态流、实际通过的链路、失败步骤和原因、需要成员 2/3/4 各自修复什么、成员 1 在 GitHub 合并 PR 的推荐顺序、人工验收步骤。不要自动 push。
```

### 完成标志

- 公共字段只有一套命名；
- 至少一个真实测试文件能从上传走到带来源的检索结果；
- 不同项目的数据不会混在一起。

## 成员 2：知识库与资料上传页面

### 当天任务

实现真实资料上传、状态轮询、失败重试、删除和检索测试界面。

### 直接发给 Codex 的提示词

```text
你是本项目 Vue 3 前端负责人。请完成第 2 天“知识库与资料上传页面”，直接在现有 frontend/ 上实现并接入现有 FastAPI 契约。我是新手，请你检查代码、编码、运行和修复。

开始前运行 git status，阅读 contracts/ 和后端 OpenAPI/路由，不要猜字段。只主要修改 frontend/，不改数据库和 AI 内部实现，不自动 push。禁止在前端伪造上传成功或检索结果；后端暂不可用时可以用明确标注为开发模式的 MSW/mock adapter，但默认必须走真实接口，并且最终验收前关闭 mock。

请完成：
1. 在知识库页面提供项目选择或从路由取得 projectId；没有项目时引导先创建项目。
2. 拖拽/选择上传，前端校验允许的 PDF、DOCX、TXT、MD 类型和后端公布的大小限制；显示文件名、大小和校验错误。
3. 调用真实上传接口，展示上传进度；上传后轮询 uploaded/parsing/indexing/ready/failed 状态，页面刷新后能重新拉取而不是丢失。
4. 文件列表显示类型、大小、创建时间、索引状态、失败原因；实现失败重试和删除二次确认。按钮在请求中禁用，防止重复提交。
5. 增加“检索测试”：输入问题、top_k，调用真实搜索接口；结果卡片展示原文摘要、文件名、页码/章节、score；低相关或空结果给出清晰提示。
6. 所有请求统一放在 src/api/sources.ts 和 types 中，组件不拼 URL；错误通过现有 AppError/消息组件展示。
7. 补充关键组件/工具测试，至少覆盖文件校验、状态标签和空结果；运行 typecheck、test、build。
8. 检查 1366×768 下不横向溢出，长文件名和长原文能换行。

完成后用中文给我：修改文件、依赖变化、实际调用的接口与字段、启动/测试结果、从页面上传并检索的逐步验收方法、后端未就绪时的真实阻塞、建议 commit 信息。不要自动 push，不要让我手动补代码。
```

### 完成标志

- 能在界面上传文件并看到真实状态；
- 能输入问题并查看带文件名和页码/章节的结果；
- 失败可以重试，页面刷新不丢列表。

## 成员 3：资料元数据、上传和任务接口

### 当天任务

实现资料表、文件安全保存、索引任务和检索代理接口。

### 直接发给 Codex 的提示词

```text
你是本项目 FastAPI 与 MySQL 负责人。请完成第 2 天资料上传与索引接口。直接基于现有 backend/ 实现、迁移、测试和修复。我是新手，不要只给示例。

先运行 git status，阅读 contracts/ 与 backend/app/ai/ 已暴露的解析/索引函数。主要修改 backend/app/ 中非 ai 目录、migrations 和后端测试。不得绕过 MySQL，不得把上传二进制塞入数据库，不得自动 push。

请完成：
1. 建立 SourceDocument 和 IndexTask SQLAlchemy 模型及 Alembic 迁移。SourceDocument 至少含 id、project_id 外键、original_name、stored_name、media_type、size、sha256、storage_path、status、error_message、created_at、updated_at；同一项目可用 project_id+sha256 防重复。
2. 实现安全文件存储：文件名净化、UUID 存储名、项目隔离目录、扩展名/MIME/大小校验、防路径穿越；路径来自 UPLOAD_DIR，不使用机器绝对路径。
3. 实现 POST /api/projects/{project_id}/sources、GET 列表、GET 单项、DELETE、POST /{source_id}/index、GET /api/tasks/{task_id}。
4. 索引请求调用成员 4 的 AI ingestion 服务。先使用 FastAPI BackgroundTasks 或项目已有轻量机制，不引入 Redis/Celery；任务状态持久化到 MySQL。
5. 实现 POST /api/projects/{project_id}/search，验证 top_k 范围并代理 AI 检索，返回 contracts 规定的 content、source_id、filename、location、score。
6. 文件保存与数据库写入要有补偿：数据库失败删除已保存文件；删除资料时调用 AI 删除向量，向量删除失败要记录可重试错误，不能静默不一致。
7. 实现统一错误：项目不存在、空文件、重复文件、错误类型、超大文件、任务不存在、未索引搜索。
8. 补齐 pytest：成功上传、重复、非法类型、路径穿越名、状态查询、删除、项目隔离。运行迁移和测试。

如果 AI 接口尚未合并，创建明确的 service protocol/adapter 和可替换测试 stub，但不得把 stub 当成生产结果。完成后报告修改文件、表结构、迁移和启动命令、OpenAPI 路径、测试结果、前端调用顺序、与成员 4 的接口约定、人工 Swagger 验收步骤、建议 commit 信息。不要自动 push。
```

### 完成标志

- MySQL 中能看到资料和任务状态；
- 上传接口处理非法/重复文件；
- 搜索结果返回来源定位；
- 删除后文件、元数据和向量保持一致或有明确补偿状态。

## 成员 4：资料解析、切分、向量化和检索

### 当天任务

实现 PDF/DOCX/TXT/Markdown 解析，写入 Chroma，并建立 20 条检索回归样例。

### 直接发给 Codex 的提示词

```text
你是本项目 AI/RAG 负责人。请完成第 2 天资料入库与可追溯检索，直接修改 backend/app/ai/、backend/tests/ai/ 和 requirements/ai.txt。我是新手，请实际实现、运行测试并修复。

先运行 git status，阅读 contracts/ 和成员 3 的 source/index service 接口。保护其他目录，不重写 FastAPI 主路由和 MySQL 模型，不自动 push。禁止下载超大模型而不说明，禁止伪造来源。

请完成：
1. ingestion 解析器支持 PDF、DOCX、TXT、Markdown。PDF 尽量保留 page_number；DOCX 保留标题层级和 paragraph_index；TXT/MD 保留章节或行范围。扫描版 PDF 无文本时返回“需要 OCR，当前版本不支持”的明确错误。
2. 清洗空白、页眉页脚重复和空块，但不得改变关键原文；记录 source_id、project_id、filename、location、content_hash。
3. 采用适合中文教学资料的分层切分：先按标题/段落，再按可配置 chunk_size 和 overlap；每个 chunk 有稳定 chunk_id。
4. 写入 Chroma 时 metadata 必须包含 project_id、source_id、chunk_id、filename、location；重复索引同一 source 应先替换或幂等更新，不能产生重复块。
5. 实现项目内检索：top_k、最低分阈值、可选 source_ids；返回 content、score 和完整来源。不同 project_id 必须物理/逻辑隔离。
6. 如条件允许实现轻量“向量召回 + 关键词加权”的混合排序；不要引入需要独立服务器的复杂搜索引擎。
7. 建立不少于 20 条黄金查询数据，覆盖课标、教材知识点、课堂活动和无答案问题；测试正确来源是否进入 Top-3。样例资料必须可公开或自造。
8. 输出可计算的 Top-3 命中率；目标 85%，达不到时分析切分/阈值原因并调整，不能改测试答案迎合结果。
9. 为删除 source、重复索引、空文档、跨项目隔离写测试。

实际运行 AI 测试。最后用中文报告：解析支持范围、chunk 配置、metadata、成员 3 调用的函数签名、20 条查询结果和命中率、未支持场景、人工验收方法、建议 commit 信息。不要自动 push。
```

### 完成标志

- 四种文本资料能解析；
- 检索结果可回到原文件位置；
- 20 条问题的 Top-3 命中率尽量达到 85%；
- 项目之间不会串库。

---

# 第 3 天：项目向导、业务接口与五类教学 Skills

## 成员 1：冻结 Skill 与产物 Schema

### 当天任务

统一五类 Skills、任务和产物的数据结构，避免前后端与 AI 各写一套字段。

### 直接发给 Codex 的提示词

```text
你是第 3 天系统集成和契约负责人。请检查最新仓库，完成五类教学 Skills、AI 任务和产物 Schema 的统一，并建立契约测试。我是新手，请直接修改和验证。

先运行 git status，阅读现有 contracts、前端 types、FastAPI schemas 和 AI Pydantic 模型。主要修改 contracts/、tests/contract/ 和必要的公共生成脚本；不要重写各模块业务，不自动 push。

五类 Skill 固定为：1 课程标准解读；2 学情与教学目标设计；3 教学活动与课堂流程设计；4 课件叙事与页面规划；5 练习与评价设计。

请完成：
1. 为每类 Skill 明确 id、名称、用途、触发条件、必填输入、可选输入、结构化输出和常见错误。
2. 统一 LessonContext：project_id、subject、grade、textbook_version、lesson_topic、lesson_count、student_profile、selected_source_ids、teacher_requirements。
3. 统一 Citation：source_id、chunk_id、filename、location、quote；quote 只能来自检索原文。
4. 统一 Task：task_id、type、status、stage、progress、trace_id、error_code、error_message、created_at、updated_at。
5. 统一最小 Artifact：artifact_id、project_id、type、version_no、content、citations、warnings、created_at。
6. 契约应以 JSON Schema/OpenAPI 可复用形式保存；检查前端 TypeScript、后端 Pydantic、AI 输出字段是否能映射。能自动生成类型时提供脚本，不能时建立验证测试。
7. 写契约测试，加载 Schema 并验证正常样例、缺字段样例和错误枚举；不得仅写 Markdown 表格。
8. 对不一致做最小修复并列出影响，不要擅自删除已有字段。

运行契约测试。完成后报告最终字段、自动生成/验证方法、发现并修复的不一致、成员 2/3/4 要遵守的接口、GitHub 合并顺序、人工验收步骤。不要自动 push。
```

### 完成标志

- 前端、后端、AI 使用同一套核心字段；
- 契约测试能发现缺字段和错误枚举；
- 五类 Skill 边界清楚、不重叠。

## 成员 2：项目创建向导和三栏工作台骨架

### 当天任务

让教师能创建项目、选择资料和 Skill，并在三栏工作台发起 AI 任务。

### 直接发给 Codex 的提示词

```text
你是 Vue 3 前端负责人。请在现有 frontend/ 完成第 3 天项目创建向导和三栏备课工作台，并严格使用 contracts/OpenAPI。我要依靠 Codex 完成，请直接实现、测试和修复。

先运行 git status，阅读现有路由、store、API 和 contracts。只主要修改 frontend/，不改后端/AI 内部，不自动 push，不写死最终 AI 结果。

请完成：
1. 项目列表：真实加载、创建、进入、空状态；项目卡显示学科、年级、课题、更新时间和状态。
2. 创建向导分步表单：基础信息（项目名、学科、年级、教材版本、课题、课时）、学情（班级特点/薄弱点，可选）、选择已 ready 的资料、教师补充要求。提供合理校验和默认值，但不得把演示答案写死。
3. 创建成功进入 /workbench/:projectId，刷新后从后端重新加载项目。
4. 三栏工作台：左栏显示项目输入、资料选择和五类 Skill；中栏预留教案/课件/讲稿/练习标签；右栏显示来源、警告、质量和版本。当前没有产物时显示引导。
5. Skill 卡片显示用途和所需输入；点击运行时创建真实任务，显示 pending/running/succeeded/failed，支持取消或重试（以现有接口能力为准）。
6. 建立 typed API：projects、skills、tasks、artifacts；类型来自 contracts/OpenAPI，避免 any。
7. 任务轮询应在页面卸载时停止，防止多个定时器；按钮防重复请求；错误含 trace_id 时允许复制。
8. 补测试：表单校验、创建成功跳转、任务状态渲染；运行 lint/typecheck/test/build 并修复。

完成后用中文报告：页面路径、字段映射、调用接口顺序、测试结果、我怎样从首页创建项目并发起 Skill、后端缺失接口、建议 commit 信息。不要自动 push。
```

### 完成标志

- 能创建项目并进入工作台；
- 三栏区域清楚；
- 能选择 Skill 发起真实任务并查看状态。

## 成员 3：项目、任务、产物与版本基础接口

### 当天任务

实现项目配置、Skill 列表、后台任务、产物和版本的 MySQL 持久化。

### 直接发给 Codex 的提示词

```text
你是 FastAPI/MySQL 负责人。请完成第 3 天项目、AI 任务、产物与版本基础接口，直接在现有 backend/ 实现迁移、测试和修复。我是新手。

先运行 git status，阅读 contracts 和 AI Skill service。主要修改 backend/app 非 ai 目录、migrations、backend/tests 和 base requirements。不自动 push，不使用 SQLite 替代 MySQL，不在路由中直接堆全部业务逻辑。

请完成：
1. 完善 Project 模型以支持 student_profile、teacher_requirements，并提供列表、更新、删除（有资料/产物时采用安全策略）。
2. 建立 AITask 表：id、project_id、type、status、stage、progress、trace_id、idempotency_key、input_snapshot JSON、result_artifact_id、error_code、error_message、created_at、started_at、finished_at。
3. 建立 LessonArtifact 与 ArtifactVersion：type 枚举支持 lesson_plan、slide_deck、speaker_notes、exercise_set；保存结构化 JSON、citations、warnings、version_no。
4. 实现 GET /api/skills（可从 contracts/AI registry 读取），POST /api/projects/{id}/tasks、GET task、POST retry、POST cancel、GET artifacts。
5. 创建任务时校验项目、资料状态和输入；使用 idempotency_key 防止用户双击产生重复模型调用。
6. 长任务用 service 层调 AI registry，状态转换严格校验；失败保存错误摘要，不保存密钥、完整 Prompt 或学生隐私。
7. 产物保存必须事务化；AI 输出先经 Pydantic 验证，再落 MySQL。无效输出进入 failed，不让坏 JSON 传给前端。
8. 生成 Alembic 迁移，补状态机、幂等、项目隔离、失败任务和产物版本测试。

运行测试和迁移。完成后报告表结构、路由、任务状态流、AI service 调用边界、测试结果、前端轮询示例、Swagger 人工验收、建议 commit 信息。不要自动 push。
```

### 完成标志

- 任务状态和输入快照保存在 MySQL；
- 重复点击不会重复创建任务；
- AI 输出经校验后保存为第一版产物。

## 成员 4：五类 Skills 和智能路由

### 当天任务

将 AI 能力拆成五个可独立测试的 Skill，并让路由器根据任务选择正确 Skill。

### 直接发给 Codex 的提示词

```text
你是 AI、LangChain 和 RAG 负责人。请完成第 3 天五类教学 Skills 与智能路由，直接修改 backend/app/ai/ 和 AI 测试。我是新手，请完整实现、运行和修复。

先运行 git status，读取 contracts 中最新 Skill/LessonContext/Citation Schema，读取现有 retriever 和 LLM adapter。不得创建第二套冲突 Schema，不改 FastAPI 主路由和 MySQL 模型，不自动 push。

实现五类独立 Skill：course_standard_interpretation、learning_objectives、teaching_activities、slide_narrative、exercise_assessment。

每个 Skill 必须：
1. 有独立 Pydantic 输入/输出模型、用途说明和注册信息；
2. 只接收明确 LessonContext 和参数，不依赖全局可变状态；
3. 根据 project_id 与 selected_source_ids 调用 RAG；
4. 输出 citations 使用真实 source_id/chunk_id/location；无充分资料时把通用建议放入 warnings，绝不能制造引用；
5. 通过 DeepSeek 结构化输出；解析失败最多自动修复一次，仍失败返回可识别错误；
6. 记录 trace_id、skill_id、耗时、检索数量和模型状态，但不记录密钥与完整敏感输入。

另外实现 Skill registry 和 router：显式 task type 优先；自然语言意图只用于辅助选择；低置信度时返回需要用户选择，不能随机调用。建立至少 10 条意图测试，覆盖五类正常选择、模糊请求、缺少参数；每个 Skill 至少有一个不调用真实模型的结构测试，有密钥时可加集成测试并标记。

Prompt 要体现小学年龄适配、目标—活动—评价一致性和教师最终确认。不要一次生成完整课件，那是第 5 天任务。

实际运行 AI 测试，主动修复。完成后报告 5 个 Skill 的输入输出、registry/router 调用方法、10 条选择测试结果、引用与无资料策略、成员 3 应调用的函数、人工验收步骤、建议 commit 信息。不要自动 push。
```

### 完成标志

- 五个 Skill 能分别调用；
- 至少 10 条意图测试能正确选择；
- 输出能通过 Schema 校验并带真实来源或明确警告。

---

# 第 4 天：真实 AI 链路、来源查看与追踪

## 成员 1：首条端到端链路联调

### 当天任务

打通“创建项目→选择资料→生成教学目标与活动→保存→重新打开”的真实链路。

### 直接发给 Codex 的提示词

```text
你是第 4 天系统集成负责人。请在最新仓库打通第一条真实 AI 链路：浏览器创建项目、选择已索引资料、发起教学目标/活动任务、RAG 检索、DeepSeek 结构化生成、MySQL 保存、前端展示来源，刷新后仍能打开。我要依靠 Codex，请你直接检查、运行、定位和修复。

开始前运行 git status，检查 frontend、backend、ai、contracts 的当前状态和未提交修改。主要修改 tests/e2e、contracts 和必要的最小集成点，禁止为通过测试在前端/后端写死结果，禁止自动 push。

请完成：
1. 选择一个自造或公开的小学课例测试资料和明确问题；保证没有版权/隐私风险。
2. 确认 trace_id 从前端请求经过 FastAPI、任务、AI Skill、RAG 到产物保存，错误返回也带 trace_id。
3. 建立三条集成场景：正常资料成功；未选择资料或资料未 ready；DeepSeek 超时/不可用。成功要有产物和 citations，失败要有可恢复提示。
4. 运行前后端和 MySQL/Chroma 所需服务；用接口测试或浏览器自动化实际走一遍。不能只验证单元测试。
5. 对字段、跨域、任务轮询、事务、状态停滞等问题做最小修复；每次修复运行所属模块测试。
6. 刷新工作台重新加载产物，确认不是只存在前端内存。
7. 输出一条从 trace_id 定位问题的操作方法。

完成后报告：真实链路每一步、实际使用的输入、三种场景结果、修改文件、运行命令、剩余风险、成员 2/3/4 各自需处理的问题、GitHub 合并顺序、我怎样按按钮验收。不要自动 push。
```

### 完成标志

- 浏览器能完成一次真实生成；
- 成功结果有来源并保存；
- 无资料、模型失败都有明确提示；
- 刷新后结果仍在。

## 成员 2：真实任务进度、来源侧栏和错误恢复

### 当天任务

把工作台从页面骨架变成可查看真实进度、结果、引用和错误的界面。

### 直接发给 Codex 的提示词

```text
你是 Vue 3 前端负责人。请完成第 4 天真实 AI 任务联调界面：任务阶段、产物展示、来源侧栏、错误恢复和刷新恢复。请直接在 frontend/ 实现、测试并修复，我是新手。

先运行 git status，读取最新 OpenAPI/contracts，不猜字段。只主要修改 frontend/，不得写死成功结果，不自动 push。

请完成：
1. 发起任务后展示 pending、资料检索、教学分析、模型生成、结构校验、保存、成功/失败等阶段；以后端实际 stage 为准，不在前端虚构进度。
2. 轮询任务并在成功后加载 artifact；离开页面停止轮询，重新进入能根据 task_id/project_id 恢复。
3. 在中栏以清晰结构展示教学目标、重点难点、教学活动和评价方式；支持最小文本编辑并调用保存接口。
4. 右侧来源抽屉：点击 citation 显示 filename、页码/章节、quote；若引用对应资料已删除，显示不可用状态而非崩溃。
5. 错误按 error_code 显示可读说明：资料未索引、检索为空、模型超时、结构校验失败、服务器错误；显示并可复制 trace_id，提供合理重试。
6. 处理重复点击、取消、网络断开、请求超时、空产物、部分 citations 缺失；不得白屏。
7. 用 Markdown 安全渲染时禁止危险 HTML/XSS；用户编辑内容也要安全展示。
8. 补测试：阶段渲染、来源点击、失败重试、刷新恢复；运行 lint/typecheck/test/build。

完成后报告实际接口、组件、测试结果、浏览器逐步验收、后端缺失字段、建议 commit 信息。不要自动 push。
```

### 完成标志

- 任务阶段可见；
- 成功结果和来源可查看；
- 失败可重试并显示 trace_id；
- 刷新后能恢复。

## 成员 3：任务执行器、统一错误和 trace_id

### 当天任务

让长任务状态可靠、错误可定位、日志不泄密，保存检索与生成结果。

### 直接发给 Codex 的提示词

```text
你是 FastAPI/MySQL 负责人。请完成第 4 天任务执行、统一错误、trace_id 和产物保存闭环。直接在现有 backend/ 实现、迁移、测试并修复。我是新手。

先运行 git status，阅读 AI Skill 的异常和 tracing 接口、contracts 错误码。主要修改非 ai 后端、测试和必要迁移，不自动 push。

请完成：
1. 为每个 HTTP 请求和 AI 任务生成/传递 trace_id；响应头或响应体可获取；日志每行包含 trace_id、task_id、stage。
2. 统一错误码至少覆盖 PROJECT_NOT_FOUND、SOURCE_NOT_READY、NO_RETRIEVAL_RESULT、LLM_TIMEOUT、LLM_AUTH_FAILED、OUTPUT_VALIDATION_FAILED、TASK_CONFLICT、DATABASE_ERROR、INTERNAL_ERROR。
3. 实现可靠任务 runner：pending→running，逐阶段更新 stage/progress；成功先校验再事务保存 artifact/version；任何异常进入 failed 并记录安全摘要。
4. 任务超时、有限重试和取消。模型调用只对可重试网络/限流错误重试，结构化输出修复次数有限；取消后不得继续写成功产物。
5. idempotency_key 防止重复任务与重复扣费；retry 创建新尝试或清晰记录 attempt，不覆盖旧错误历史。
6. 结构化日志脱敏：不得记录 API key、MySQL 密码、完整上传原文；可记录 source_id、chunk 数量、耗时。
7. 提供 GET task 和项目最近任务，支持前端刷新恢复。
8. 写并发/重复、超时、取消、AI 异常、事务回滚和 trace_id 测试。

运行 pytest 与迁移。完成后报告状态机、错误码、日志例子（无敏感值）、测试结果、前端如何恢复任务、AI 异常如何映射、Swagger 验收步骤、建议 commit 信息。不要自动 push。
```

### 完成标志

- 一个 trace_id 能贯穿整条链路；
- 失败任务有明确错误并可重试；
- 重复点击不会重复调用模型；
- 日志没有密钥和完整敏感原文。

## 成员 4：目标—活动—评价真实生成链

### 当天任务

完成第一条可演示的 production-like AI 链，突出课标/教材依据和三者一致性。

### 直接发给 Codex 的提示词

```text
你是 AI/RAG 负责人。请完成第 4 天真实“教学目标—教学活动—评价”生成链。直接在 backend/app/ai/ 实现、测试和修复。我是新手。

先运行 git status，读取最新 LessonContext、Citation、Artifact Schema、retriever 和 Skill registry。只主要修改 ai 目录和 AI 测试，不改主路由/MySQL，不自动 push，禁止伪造引用。

请完成：
1. 链路顺序固定：校验上下文→检索课标/教材→检查证据充分性→调用目标 Skill→调用活动 Skill→生成评价方式→一致性校验→返回结构化结果。
2. 输出至少包含 objectives（可观察行为、条件、评价标准）、key_points、difficult_points、activities（阶段、时间、教师活动、学生活动、目标编号）、assessments（方式、目标编号）、citations、warnings。
3. Prompt 约束小学年级语言、总课时、时间总和、教师最终确认；不得声称替代教师判断。
4. 关键课程事实与课标要求带真实 citation；模型自己提出的教学策略可标记为 general_suggestion，不伪装成教材原文。
5. 检索证据不足时不要硬编课标条款，返回 warning 并允许生成通用教学框架；证据冲突时列出冲突。
6. Pydantic/JSON 结构化输出；校验失败自动修复最多一次。记录 token/耗时/检索数量和 trace_id。
7. 建立测试：正常证据、无证据、冲突证据、模型格式错误、超时；有密钥时增加真实小课例集成测试，无密钥明确 skip。
8. 增加目标—活动—评价一致性检查，至少验证每个核心目标有活动和评价，课堂时间总和合理。

运行 AI 测试并修复。完成后报告输出示例结构、真实引用策略、一致性规则、测试结果、成员 3 调用函数、前端应展示字段、人工验收步骤、建议 commit 信息。不要自动 push。
```

### 完成标志

- 能真实生成教学目标、活动和评价；
- 每个核心目标有对应活动和评价；
- 有依据的结论可追溯，无资料时不伪造引用。

---

# 第 5 天：完整备课产物、Slidev 与局部修改

## 成员 1：冻结四类产物、版本和局部修改契约

### 当天任务

统一教案、课件、讲稿、练习的关联方式，保证局部修改只影响指定内容。

### 直接发给 Codex 的提示词

```text
你是第 5 天系统集成与契约负责人。请在最新仓库冻结完整备课产物、版本和局部修改契约，并用一个真实课题做跨模块验证。我是新手，请直接检查、修改、运行和修复。

先运行 git status，阅读 contracts、前端 artifact types、后端模型和 AI 输出。主要修改 contracts/、tests/e2e/ 与必要的最小集成代码，不覆盖其他成员业务，不自动 push。

四类产物固定为 lesson_plan、slide_deck、speaker_notes、exercise_set。请完成：
1. 教案结构包括 objectives、key_points、difficult_points、stages、time_minutes、teacher_actions、student_actions、assessments、citations。
2. slide_deck 包含 deck_title、theme、slides；每页有稳定 slide_id、order、title、layout、markdown、teaching_stage、objective_ids、citations。
3. speaker_notes 按 slide_id 对应，包含 explanation、questions、transition、board_notes、estimated_minutes。
4. exercise_set 包含基础/巩固/提高三个层次；每题有 exercise_id、objective_ids、question、type、difficulty、answer、explanation、source/citation、needs_teacher_review。
5. 所有产物包含 artifact_id、version_id、version_no、project_id。课件页与讲稿必须通过 slide_id 一一关联。
6. 局部修改请求统一为 artifact_id、base_version_no、target_type、target_id、instruction、sync_related。响应包含 new_version_no、changed_ids、unchanged_hashes、warnings。
7. 建立契约和端到端测试：修改一个 slide_id 后只允许该页以及用户明确选择同步的讲稿/习题发生变化；其他页内容哈希保持不变；旧版本仍可读取。
8. 使用一个真实小学课题跑通四类产物并验证目标编号关联。禁止用手写固定结果假装 AI 生成。

运行测试并修复字段不一致。完成后报告最终结构、局部修改规则、跨产物关联、实际测试结果、成员 2/3/4 的接口要求、GitHub 合并顺序、人工验收步骤。不要自动 push。
```

### 完成标志

- 四类产物使用统一 ID 和版本；
- 课件页与讲稿一一对应；
- 局部修改不会无故改变其他页面。

## 成员 2：完整三栏工作台与 Slidev 预览

### 当天任务

展示教案、课件、逐页讲稿、分层练习、来源和版本，并支持局部修改。

### 直接发给 Codex 的提示词

```text
你是 Vue 3 前端负责人。请完成第 5 天完整备课工作台和 Slidev 课件预览，直接在现有 frontend/ 实现、测试和修复。我是新手。

先运行 git status，读取最新 contracts/OpenAPI 和已有工作台。只主要修改 frontend/，不自动 push，不在前端写死课件、讲稿或习题答案。

请完成：
1. 工作台中栏标签：教学设计、课件、讲稿、练习；右栏标签：来源、质量、版本。项目和任务状态从真实接口加载。
2. 教学设计用结构化区块显示目标、重难点、课堂阶段、时间、教师/学生活动和评价；阶段时间总和可见。
3. 课件支持 Slidev 预览。优先使用安全 iframe 或项目已有 Slidev 服务；同时提供 Markdown 源码查看/编辑。禁止直接执行不可信脚本，失败时显示源码和错误。
4. 课件缩略列表按 order 展示；点击页后同步选中同 slide_id 的讲稿。讲稿显示讲解、提问、过渡语、板书和预计时间。
5. 练习按基础、巩固、提高分组；教师视图显示答案解析和“需教师确认”，学生预览隐藏答案。
6. 局部修改：当前页/当前讲稿/当前练习提供自然语言输入，发送 artifact_id、base_version_no、target_id、instruction、sync_related；生成中禁用重复提交。
7. 修改成功后只刷新 changed_ids，显示“改了哪些内容”；版本面板能切换旧版/新版并回滚（以接口为准），处理版本冲突。
8. citations 在对应目标、页面或题目旁可点开来源；无来源的 AI 建议要明确标识。
9. 处理长 Markdown、空课件、渲染失败、任务超时、版本冲突和页面刷新；补测试并运行 lint/typecheck/test/build。

完成后报告页面组件、真实接口、Slidev 启动方式、测试结果、从生成到局部修改的完整点击步骤、后端缺失项、建议 commit 信息。不要自动 push。
```

### 完成标志

- 四类产物都能查看；
- 点击课件页能联动讲稿；
- 局部修改与版本切换可用；
- 学生预览不显示答案。

## 成员 3：产物版本、局部更新和回滚接口

### 当天任务

完善 MySQL 版本模型，保存四类产物，支持乐观锁、局部更新和回滚。

### 直接发给 Codex 的提示词

```text
你是 FastAPI/MySQL 负责人。请完成第 5 天四类产物、版本、局部修改和回滚接口，直接实现迁移、测试和修复。我是新手。

先运行 git status，读取最新 Artifact/Version/LocalRevision contracts 和 AI generation service。主要修改 backend/app 非 ai 目录、migrations 和测试，不自动 push，不使用文件覆盖代替数据库版本。

请完成：
1. 审核/完善 LessonArtifact 与 ArtifactVersion 模型。每次生成或修改创建不可变版本，记录 version_no、parent_version_id、change_type、changed_ids、content JSON、citations、warnings、created_at。
2. 四类产物可以作为同一 lesson bundle 管理，确保同一生成批次和版本关系清楚。不要为了省事把无法查询的所有内容塞进一个无结构字符串。
3. API：获取项目最新产物、按 type/版本获取、列出版本、创建完整生成任务、局部修改、回滚。回滚也创建新版本，不删除历史。
4. 局部修改把当前内容、目标块、instruction 和必要来源交给 AI；AI 只返回 changed block，后端负责合并并验证未改块哈希。
5. 使用 base_version_no 乐观锁；用户基于旧版本提交时返回 409 和当前版本，不静默覆盖。
6. 课件 slide_id 与 speaker notes 的一致更新采用事务；sync_related=false 时不得改关联产物，true 时只改明确关联项。
7. 对 JSON 内容做 Pydantic 校验，坏结构不落库。限制 instruction 长度，记录操作者为 demo user 即可，不开发完整权限。
8. 迁移和测试覆盖：完整保存、局部修改、未改块不变、版本冲突、回滚、事务失败、项目隔离。

实际运行测试和迁移。完成后报告表结构和 API、版本规则、冲突处理、测试结果、成员 2/4 的调用边界、Swagger 验收步骤、建议 commit 信息。不要自动 push。
```

### 完成标志

- 每次生成/修改都有新版本；
- 旧版本可查看和回滚；
- 并发修改不会互相覆盖；
- 局部修改只改变目标块。

## 成员 4：教案、课件、讲稿、练习完整生成链

### 当天任务

先生成统一教学蓝图，再派生四类一致产物，并实现局部改写。

### 直接发给 Codex 的提示词

```text
你是 AI/RAG 负责人。请完成第 5 天完整备课生成链和局部改写能力，直接在 backend/app/ai/ 实现、测试和修复。我是新手。

先运行 git status，读取最新四类 Artifact Schema、版本契约、现有目标—活动—评价链和 retriever。只主要修改 AI 目录/测试，不改数据库和前端，不自动 push，不伪造来源。

请完成：
1. 不要四次互不相关地调用模型。先生成统一 LessonBlueprint：目标、重难点、阶段、时间、教学策略、评价、来源；通过校验后再派生教案、课件、讲稿、练习。
2. 课件生成 12—18 页适合课堂投影的 Slidev Markdown。每页有稳定 slide_id、适度文字密度、teaching_stage、objective_ids 和 citations；不要追求花哨图片而忽略教学。
3. 逐页讲稿按 slide_id 生成 explanation、提问、预期学生回答、过渡语、板书提示和时间；所有页时间总和与课时接近。
4. 练习至少基础、巩固、提高各一题；包含答案、解析、难度、目标编号、来源或 generated 标识和 needs_teacher_review。没有授权题库时允许模型原创，但必须明确标识，不伪造题库来源。
5. 做一致性审查：每个核心目标至少被一个活动和一道评价/练习覆盖；slide_id 与讲稿完整对应；练习难度适合年级；时间总和合理。
6. 局部改写函数输入完整当前版本、target_type、target_id、instruction、sync_related、citations，只返回 changed block 和 changed_ids。Prompt 明确禁止重写无关内容。
7. 引用沿用 source_id/chunk_id/location；修改涉及事实时重新检索，纯风格调整不虚构新引用。
8. 测试正常生成、资料不足、局部改当前页、同步讲稿、不同步讲稿、练习改难度、模型返回无效 slide_id。有密钥时跑一个真实课例，无密钥则集成测试明确 skip。

实际运行测试并修复。完成后报告生成顺序、四类输出结构、一致性结果、局部修改保护措施、真实/跳过的测试、成员 3 调用方法、人工验收步骤、建议 commit 信息。不要自动 push。
```

### 完成标志

- 一个真实课题能生成四类一致产物；
- 课件 12—18 页并对应逐页讲稿；
- 练习分层且关联目标；
- 局部改写不动无关内容。

---

# 第 6 天：LangGraph 多智能体、质量审校与导出

## 成员 1：LangGraph 和导出端到端集成

### 当天任务

验证正常、资料不足、审校返修和用户取消四条图流程，并检查双版本导出。

### 直接发给 Codex 的提示词

```text
你是第 6 天系统集成负责人。请在最新仓库完成 LangGraph 多智能体与教师/学生双版本导出的端到端集成测试和最小修复。我是新手，请直接运行并处理问题。

先运行 git status，阅读图状态契约、后端任务/导出接口、前端状态展示和 AI graph。主要修改 contracts、tests/e2e、deploy 集成点；不重写模块内部，不自动 push。

请完成：
1. 冻结可见节点：资料分析、教学设计、课件生成、讲稿/练习、质量审校、人工确认、导出。状态包含 node_id、status、attempt、started_at、finished_at、issues。
2. 建立四条端到端场景：正常通过；资料不足转人工确认；审校发现某页过密后只返修课件相关节点；用户运行中取消。
3. 验证返修最多两次，不能死循环；返修后旧的已通过模块不应无故重生成。
4. 验证进程/服务重启后任务状态仍可查询，能恢复时恢复，不能恢复时明确失败，不能永远 running。
5. 验证教师包包含教案、课件源码/HTML或PDF、讲稿、含答案练习和引用；学生包不含讲稿、答案和解析。
6. 导出必须对应用户选择的当前版本；ZIP 内文件名安全、可打开，不包含 .env、密钥、日志和原始私密上传文件。
7. 运行四条场景并修复接口/字段/状态问题；不要通过手工改数据库让测试通过。

完成后报告图节点和条件、四场景结果、导出内容清单、实际修改、剩余风险、成员 2/3/4 各自问题、PR 合并顺序、完整人工验收步骤。不要自动 push。
```

### 完成标志

- 四条流程都结束在明确状态；
- 返修没有死循环；
- 教师包和学生包内容边界正确。

## 成员 2：多智能体流程、质量问题和导出界面

### 当天任务

让用户看懂 AI 正在做什么、为什么返修，并能确认后导出。

### 直接发给 Codex 的提示词

```text
你是 Vue 3 前端负责人。请完成第 6 天 LangGraph 流程可视化、质量问题定位、人工确认和导出体验。直接在 frontend/ 实现、测试、构建和修复，我是新手。

先运行 git status，读取真实 graph/task/export contracts，不虚构节点，不自动 push。

请完成：
1. 工作台增加流程面板，按真实顺序展示资料分析→教学设计→课件→讲稿/练习→审校→人工确认→导出；状态清晰区分未开始、运行、成功、警告、返修、失败、取消。
2. 当前节点显示阶段说明、尝试次数和耗时；页面刷新后从后端恢复。
3. 质量问题列表显示 severity、issue_type、target_id、suggestion；点击能跳转到具体教学目标、slide_id 或 exercise_id。
4. 审校返修时显示“只返修了什么”，避免让用户误以为全部重来；超过重试次数显示人工处理。
5. 人工确认面板允许教师接受、返回修改或继续导出。没有确认前导出按钮禁用。
6. 导出页面选择版本、教师包/学生包和格式；显示进度、失败重试、下载文件名。学生包预览明确隐藏答案和讲稿。
7. 下载使用后端返回的安全 URL/blob，处理超时和过期；禁止把密钥放查询参数。
8. 适配 1366×768，长问题不溢出；补流程状态、问题跳转、人工确认、导出测试，运行 lint/typecheck/test/build。

完成后报告组件和路由、接口、测试结果、从运行图到下载两类包的点击步骤、后端缺失项、建议 commit 信息。不要自动 push。
```

### 完成标志

- 节点和返修状态可见；
- 问题能跳转到具体内容；
- 人工确认后才能导出；
- 两类包均能下载。

## 成员 3：图状态持久化、恢复和导出服务

### 当天任务

持久化 LangGraph checkpoint，支持暂停/取消/恢复，并安全生成导出包。

### 直接发给 Codex 的提示词

```text
你是 FastAPI/MySQL 与导出服务负责人。请完成第 6 天图任务状态持久化、恢复、人工确认和双版本导出。直接实现迁移、测试和修复，我是新手。

先运行 git status，读取 AI graph 暴露的 state/checkpoint 接口和 contracts。主要修改非 ai 后端、migrations、测试、必要导出依赖，不自动 push。

请完成：
1. 建立 GraphRun/GraphNodeRun 或等价模型，保存 project_id、task_id、thread_id、current_node、state_snapshot/checkpoint 引用、status、attempt、issues、timestamps。敏感原文不重复无限存储。
2. API：启动图、查询图状态、取消、恢复、提交人工确认决定。状态转换需校验，重复确认幂等。
3. 服务重启后 running 任务不能永久卡住；根据 checkpoint 恢复或标记可重试失败。实现超时清理策略。
4. 建立 ExportJob，按选定 artifact version 生成教师包或学生包。使用临时目录，成功后原子移动；失败清理临时文件。
5. 教师包：教案、Slidev Markdown、可用的 HTML/PDF、讲稿、教师版练习、引用清单。学生包：课件/学生练习，不含讲稿、答案、解析。
6. ZIP 防 Zip Slip，文件名净化；不包含 .env、数据库文件、日志、API key。下载接口校验 job_id/project_id，开发版可不做复杂登录但不能任意读服务器路径。
7. 导出状态可轮询；设置过期清理但测试期间可取。生成文件使用 UTF-8 中文。
8. 迁移和测试覆盖重启恢复、取消、重复确认、版本选择、教师/学生内容边界、导出失败清理、路径安全。

实际运行测试和一个小导出。完成后报告表/API、恢复策略、ZIP 内容、测试结果、前端调用顺序、人工 Swagger 验收、建议 commit 信息。不要自动 push。
```

### 完成标志

- 图状态存入 MySQL；
- 取消/恢复/确认有明确结果；
- 导出失败不留下半成品；
- 学生包无答案和讲稿。

## 成员 4：LangGraph 多智能体和质量审校

### 当天任务

实现显式状态图、条件返修和人工确认，质量问题能够定位到具体目标/页面/练习。

### 直接发给 Codex 的提示词

```text
你是 AI/LangGraph 负责人。请完成第 6 天多智能体状态图、质量审校、条件返修和人工确认。直接修改 backend/app/ai/graph 等 AI 目录并运行测试，我是新手。

先运行 git status，读取最新图状态、artifact、issue contracts 和后端 checkpoint adapter。不得在 AI 内直接操作 Web UI，不重写 MySQL 模型，不自动 push。

请完成：
1. 定义可序列化 LessonState，至少包含 project/context、retrieval_summary、blueprint、四类 artifacts、citations、issues、current_node、attempts、warnings、human_decision、trace_id。
2. 节点：analyze_sources、design_lesson、generate_slides、generate_notes_exercises、review_quality、human_confirm、finalize。每节点输入输出明确，不依赖不可序列化全局对象。
3. 条件边：资料不足→human_confirm；课件问题→只返 generate_slides 并按需同步 notes；练习问题→只返 notes_exercises；全部通过→human_confirm；异常→有限重试/失败。
4. 每个返修目标最多两次，超过后人工确认，禁止无限循环。
5. 审校规则至少检查：核心目标是否有活动和评价、引用是否充分、课堂时间、年级语言、课件信息密度、slide_id/讲稿一致、练习答案/目标/难度。输出 issue_type、target_id、severity、suggestion。
6. 审校不能让同一模型只凭感觉给分；结合确定性规则和结构化 reviewer。无法确认的事实标 warn 而不是编造。
7. 接入 checkpoint 接口；节点执行前后发出可供后端/前端显示的状态事件；取消信号要在节点边界检查。
8. 建立至少 10 个流程测试：正常、资料不足、目标无评价、页面过密、讲稿缺页、练习过难、返修成功、返修超限、模型异常、用户取消。

运行测试并输出节点覆盖和是否有死循环。完成后报告状态结构、图和条件、10 测试结果、成员 3 的 checkpoint 接口、前端可展示事件、人工验收方法、建议 commit 信息。不要自动 push。
```

### 完成标志

- 10 个图流程测试通过；
- 问题可定位、只返修相关节点；
- 返修次数有限；
- 人工确认能暂停流程。

---

# 第 7 天：冻结功能、测试、性能和部署

## 成员 1：全流程测试、缺陷收敛和三轮演示

### 当天任务

停止增加功能，维护缺陷优先级，跑至少 25 个关键用例和 3 轮完整演示。

### 直接发给 Codex 的提示词

```text
你是第 7 天发布候选版本的集成测试负责人。今天禁止增加非必要功能。请检查整个仓库，建立并运行至少 25 个关键用例，修复阻断验收的问题。我是新手，请直接执行、提供证据和清楚的人工操作。

先运行 git status，保护未提交修改，不自动 push，不使用 git reset --hard。检查前端、后端、MySQL、Chroma、AI 和部署状态。

请完成：
1. 关键用例覆盖：创建项目、表单校验、上传四类型、非法文件、索引、检索来源、五类 Skill、真实生成、模型超时、任务重试/取消、刷新恢复、四类产物、局部修改、版本冲突/回滚、LangGraph 正常/返修/人工确认、教师/学生导出、服务重启。
2. 建立可重复的自动化测试入口和必要 E2E；不要只列清单。把依赖外部模型的测试标为 integration，并提供无密钥时的合理跳过。
3. 对每个失败先复现并定位归属，再做最小修复；修复后运行受影响单测和主链路回归。
4. 按 P0 阻断、P1 严重、P2 一般分类。P0/P1 必须清零；P2 只有不影响演示时可保留并明确限制。
5. 检查所有演示结果来自真实接口，不存在前端硬编码、手工改 MySQL、伪造 citation 或静态成功状态。
6. 用固定演示课题连续跑 3 轮完整流程并记录每轮耗时、是否成功、出现的警告。模型不可用时只允许明确标注的真实历史缓存/降级，不得冒充新生成。
7. 给出一条从干净 main 启动完整环境并运行测试的命令序列。

完成后报告 25+ 用例结果、P0/P1 修复、3 轮演示结果、修改文件、尚存 P2、成员 2/3/4 需处理事项、PR 合并顺序、我怎样复验。不要自动 push。
```

### 完成标志

- 至少 25 个关键用例达到可验收水平；
- P0/P1 为 0；
- 连续 3 轮演示无阻断；
- 主分支随时可发布。

## 成员 2：前端质量、异常状态和生产构建

### 当天任务

修复错位、重复点击、断网、长文本和构建问题，确保投影演示清楚。

### 直接发给 Codex 的提示词

```text
你是 Vue 3 前端质量负责人。第 7 天不增加新功能，请对 frontend/ 做完整质量审计，实施最小修复并通过生产构建。我是新手，请直接检查、运行、修复和说明验收方法。

先运行 git status，保护他人修改，只改 frontend/，不自动 push。

请完成：
1. 运行 lint、typecheck、unit/component tests、production build，修复所有本次范围内错误；不能用关闭类型检查或大量 eslint-disable 掩盖问题。
2. 检查项目列表、知识库、工作台、质量、导出五个页面在 1366×768 和 1920×1080；消除横向滚动、按钮遮挡、抽屉超屏和文字溢出。
3. 长文件名、长 citation、长 Markdown、12—18 页列表和大量任务状态要可用；必要时滚动/折叠，不截掉关键信息。
4. 所有异步按钮防重复提交；页面卸载停止轮询；断网/超时后可重试；401/404/409/500 和 AI 错误有可读提示。
5. 检查空项目、无资料、无产物、无引用、导出失败、Slidev 渲染失败；不能白屏或无限 loading。
6. 清理 console error、未使用依赖、硬编码 localhost（改环境变量）和演示假数据；保留必要可访问性标签。
7. 检查安全：Markdown/模型文本不执行 script；下载 URL 安全；不把密钥、完整 Prompt、学生敏感信息存 localStorage。
8. 优化明显性能问题，但不要大规模重构。路由懒加载和合理组件拆分即可。

完成后报告运行的命令和结果、修复列表、两种分辨率验收、仍有的真实限制、人工点击检查、建议 commit 信息。不要自动 push。
```

### 完成标志

- typecheck/test/build 通过；
- 控制台无明显错误；
- 异常和空状态可恢复；
- 投影分辨率下页面可用。

## 成员 3：后端测试、MySQL、安全与一键部署

### 当天任务

让项目可以从空 MySQL 启动，迁移可重复，接口、文件和日志达到演示安全水平。

### 直接发给 Codex 的提示词

```text
你是 FastAPI、MySQL 和部署质量负责人。第 7 天不增加业务功能，请完成后端测试、安全检查、数据库优化和 Docker 一键启动。直接实现并验证，我是新手。

先运行 git status，检查 backend/、deploy/、根环境配置，保护 AI 与前端修改，不自动 push。

请完成：
1. 运行后端单元/集成测试和 Alembic upgrade；在空 MySQL 数据库验证从零迁移，重复启动不重复建表；验证必要的 downgrade/失败恢复策略。
2. 检查常用查询并增加合理索引：project_id、source status、task status/created_at、artifact project/type/version、graph status。避免无依据的过度索引。
3. 验证事务：上传补偿、任务失败、产物保存、局部修改、导出失败；并发/幂等测试不能重复扣费或写坏版本。
4. 文件安全：扩展名/MIME/大小、路径穿越、危险文件名、下载任意路径、ZIP Slip；设置合理请求大小与超时。
5. CORS、错误响应和日志脱敏。生产/演示配置不得 debug 泄漏堆栈；日志不含 key、密码、完整敏感文档。
6. 完善 backend Dockerfile、frontend 构建/服务方式、deploy/docker-compose.yml：mysql 健康后运行迁移再启动 backend，前端访问正确 API；安装 base.txt 和 ai.txt。
7. 提供 Windows PowerShell 一键启动/停止命令；配置都来自 .env，镜像和仓库不含真实密钥。
8. 在可用环境实际 docker compose build/up，检查 health、db health、Swagger、前端；如果 Docker 不可用，完成静态配置检查并明确哪些未真实验证，不能伪造。

完成后报告测试/迁移/部署结果、索引、安全修复、启动命令、健康检查、真实未验证项、建议 commit 信息。不要自动 push。
```

### 完成标志

- 空 MySQL 可完成迁移和启动；
- 后端测试通过；
- 路径、上传、日志和密钥检查通过；
- Docker 环境可复现或明确真实阻塞。

## 成员 4：AI 质量评估、回归与降级

### 当天任务

用黄金数据测量检索、引用、结构和流程成功率，只修有证据的问题。

### 直接发给 Codex 的提示词

```text
你是 AI/RAG/LangGraph 质量负责人。第 7 天停止新增 AI 功能，请运行量化回归，修复最影响演示的检索、Prompt、结构化输出和降级问题。我是新手，请直接执行测试和修复。

先运行 git status，只主要修改 backend/app/ai/、AI 测试和 ai requirements，不自动 push，不通过降低断言或伪造引用让指标变好。

请完成：
1. 运行第 2 天 20 条黄金查询，输出 Top-3 来源命中率、空召回、跨项目污染和重复块；目标命中率 85% 左右。
2. 对五类 Skills 各准备代表性输入，统计路由正确率、结构校验通过率、citation 覆盖、warnings 合理性。
3. 对完整生成课例检查：目标—活动—评价覆盖、课件/讲稿 slide_id 对齐、练习目标覆盖、时间总和、年级语言、伪造引用为 0。
4. 运行 10 个 LangGraph 流程，确认无死循环、返修范围正确、人工确认可暂停。
5. 记录真实模型成功率、耗时和失败分类。只针对高频失败做最小 Prompt/阈值/重试修复，每次修复重跑相关基准，不能凭感觉大改。
6. 降级策略：超时/限流有限重试；无模型时返回明确错误或有标识的相同输入历史缓存；结构失败返回可重试；任何降级都不能冒充最新 AI 成功。
7. 缓存键必须包含项目/版本/输入/模型/Prompt 版本，不跨项目泄露。日志不含密钥和完整敏感内容。
8. 输出机器可读的测试摘要供成员 1 查看，但不要求额外人工写报告。

完成后报告各项指标、失败分类、修复前后变化、仍有风险、演示课题连续运行结果、成员 1 验收方法、建议 commit 信息。不要自动 push。
```

### 完成标志

- 检索、结构和图流程指标可量化；
- 无伪造引用；
- 模型异常不会拖垮服务；
- 固定演示课题连续成功。

---

# 第 8 天：发布、现场演示与答辩

## 成员 1：最终发布、主讲和总体验收

### 当天任务

合并最终版本，在干净目录启动，完成 6—8 分钟真实演示并分配答辩范围。

### 直接发给 Codex 的提示词

```text
你是最终发布经理和演示教练。请对当前 release candidate 做发布前检查，只修复阻断问题，不再新增功能或大重构。我是新手，请直接检查仓库、运行验证，并给出非常具体的发布/演示步骤。

开始前运行 git status、git branch 和最近提交，确认没有未提交成果、真实 .env、密钥、上传隐私文件或大文件进入版本库。禁止 git reset --hard，禁止自动 push/创建 release。

请完成：
1. 从一个新的临时目录按根 README 和 .env.example 启动完整项目，验证 MySQL 迁移、Chroma 目录、backend health、前端和 DeepSeek。不要依赖开发者机器绝对路径。
2. 运行关键自动测试、前端 build、后端测试和固定课题 smoke test。只修 P0/P1；任何修改后重跑受影响测试。
3. 检查最终版本标识、默认演示账号/项目输入、端口和环境变量。示例初始化只能创建账号、项目输入和公开测试资料，不能预置 AI 最终答案。
4. 设计并实际计时一条 6—8 分钟演示：痛点与项目→创建课例→上传/选资料→RAG 来源→多智能体生成→教案/Slidev/讲稿/练习→局部修改→质量审校→教师/学生导出。
5. 每一步准备失败时的真实应对：网络/模型超时可重试或展示明确标识的历史同输入结果；不得伪造当前运行成功。
6. 给四个人分配答辩：成员 1 架构/亮点/协作；成员 2 Vue 与交互；成员 3 FastAPI/MySQL/部署；成员 4 RAG/Skills/LangGraph/质量。
7. 给出 GitHub Desktop 的最终合并顺序、创建 tag 前检查和建议 tag 名；不要代替我 push/tag。

完成后报告：发布检查结果、干净环境启动命令、测试结果、逐分钟演示脚本、现场故障切换、四人答辩分工、最后人工确认清单、建议 commit/tag。不要自动 push。
```

### 完成标志

- 干净目录能按说明启动；
- 关键测试通过；
- 演示在 6—8 分钟内完成；
- 四个人知道自己的答辩范围。

## 成员 2：最终 UI、演示操作和前端答辩

### 当天任务

收敛操作路径、适配投影，保证演示输入可快速填写但不预置 AI 答案。

### 直接发给 Codex 的提示词

```text
你是最终前端发布和现场操作负责人。请对 frontend/ 做最后检查，只修演示阻断、构建失败和明显视觉问题，不改接口契约、不新增大功能。我是新手，请直接执行和验证。

先运行 git status，保护其他修改，不自动 push。

请完成：
1. 统一项目名称为“面向智慧教育的 AI 备课辅助系统”，检查导航、页面标题、空状态、按钮用词和中文标点。
2. 首页提供清晰“开始备课”入口；演示可以预填年级、学科、课题和教师要求，但绝不能预填 AI 生成的教案、课件或练习结果。
3. 收敛演示点击路径，确保从项目到工作台、来源、局部修改、质量和导出不迷路；关键按钮在 1366×768 投影可见。
4. 检查加载速度、进度、错误重试、来源抽屉、Slidev 预览、学生/教师切换、下载反馈；移除开发调试按钮和假数据入口。
5. 运行 lint、typecheck、test、build；检查 production 环境 API baseURL，不硬编码开发地址。
6. 如果可以启动浏览器，按成员 1 演示脚本操作并记录每一步点击位置；修复阻断问题。不能启动则明确说明并给人工检查清单。
7. 为前端答辩准备基于真实代码的简短回答：为什么 Vue3/Pinia、如何管理任务状态、如何防重复、如何安全展示 AI Markdown、如何刷新恢复。指出具体文件位置。

完成后报告最终修改、构建结果、两种分辨率、逐步操作台词、前端答辩问题与代码位置、人工验收、建议 commit 信息。不要自动 push。
```

### 完成标志

- 最终构建通过；
- 投影下关键按钮可见；
- 没有硬编码 AI 结果；
- 成员 2 能独立完成现场操作和前端答辩。

## 成员 3：干净环境、MySQL 与接口保障

### 当天任务

验证另一台机器可启动，数据库可持久化，健康检查能快速定位故障。

### 直接发给 Codex 的提示词

```text
你是最终环境、FastAPI 和 MySQL 保障负责人。请对后端与部署做 release candidate 最终检查，只修阻断问题，不大改架构。我是新手，请直接运行并给我逐步操作。

先运行 git status，检查 backend、deploy、.env.example、迁移和启动脚本；不自动 push，不提交真实密码。

请完成：
1. 在尽可能干净的环境执行 docker compose build/up 或项目标准启动，验证 MySQL 8 健康、Alembic 自动/手动迁移、FastAPI、Chroma 持久目录、前端访问。
2. 初始化脚本只创建表、演示账号、一个项目输入和公开样例资料；不能写入预生成 AI 答案。脚本重复执行应幂等。
3. 重启服务，确认 MySQL 项目/任务/版本仍在，Chroma 检索仍可用；检查 volume 和备份位置。
4. 检查端口冲突、上传/导出目录权限、磁盘空间、超时和日志轮转；所有路径相对仓库或来自环境变量。
5. 健康检查至少区分 API、MySQL，并提供 Chroma/AI 的诊断入口或 smoke 命令；失败时日志能通过 trace_id 定位但不泄密。
6. 运行后端测试与迁移检查；确认 Swagger 可用，生产演示时 docs 是否开放按项目要求决定。
7. 为现场准备精确的 PowerShell 命令：启动、查看状态、查看最近日志、重启单个服务、停止。不要提供会删除 volume 的默认命令。
8. 为后端答辩准备：为什么 MySQL+Chroma 分工、SQLAlchemy/Alembic、任务幂等、版本事务、安全上传、Docker 部署，并指出真实代码文件。

完成后报告干净环境结果、启动/诊断命令、数据持久化、真实未验证项、现场故障排查顺序、后端答辩与代码位置、建议 commit 信息。不要自动 push。
```

### 完成标志

- 空环境可启动和迁移；
- 服务重启后数据仍在；
- 健康检查能定位 API/MySQL/AI 问题；
- 成员 3 能回答后端和数据库问题。

## 成员 4：AI 最终回归、稳定性与亮点答辩

### 当天任务

锁定模型和 Prompt，复测演示课题，准备能对应真实代码与运行效果的 AI 答辩。

### 直接发给 Codex 的提示词

```text
你是最终 AI/RAG/LangGraph 稳定性和答辩负责人。请对 release candidate 的 AI 链路做最后回归，只修阻断问题，不再大改 Prompt/模型/图结构。我是新手，请直接运行并整理可验证的答辩依据。

先运行 git status，保护其他模块，不自动 push，不提交 key，不伪造来源或成功率。

请完成：
1. 锁定并记录 DeepSeek model、temperature、timeout、最大重试、Prompt 版本、chunk/top_k/阈值；配置来自环境变量或版本化安全配置，不含密钥。
2. 用最终演示资料重新索引，运行固定课题至少 2 次：检索→五类 Skills/生成链→四类产物→LangGraph 审校→局部修改。记录真实结果、耗时、warnings 和引用。
3. 检查每个关键引用可打开对应 source/location/quote；发现无法追溯必须修复或去掉引用，不能保留假引用。
4. 检查缓存与降级：缓存只用于相同项目/版本/输入/模型/Prompt，界面可标明；模型不可用时明确失败/重试，不把旧结果冒充新结果。
5. 运行 AI 单测、黄金检索和 10 个图流程；只修 P0/P1。确认日志无 API key、完整 Prompt 和敏感文档。
6. 准备 AI 答辩，必须对应真实代码文件和可见效果：RAG 为什么可追溯；MySQL 与 Chroma 的区别；五类 Skills 为什么比一个大 Prompt 好；LangGraph 节点/条件返修；结构化输出；局部修改如何保护无关内容；如何评价质量和处理幻觉。
7. 为每个问题给出 20—40 秒中文答案、相关文件路径和演示中可指给老师看的界面，不要编造尚未实现的能力。

完成后报告最终参数（不含密钥）、两次真实运行结果、引用检查、测试结果、仍有风险、AI 答辩题与答案/代码位置、现场模型故障处理、建议 commit 信息。不要自动 push。
```

### 完成标志

- 演示课题至少两次稳定运行；
- 引用都能追溯；
- AI 参数和 Prompt 已锁定；
- 成员 4 能用代码和界面解释项目亮点。

---

## 5. 每天晚上的共同合并顺序

为了减少冲突，建议每天按以下顺序合并 Pull Request：

1. 成员 4 的 AI/RAG 分支（只要没有依赖尚未合并的后端契约）；
2. 成员 3 的 FastAPI/MySQL 分支；
3. 成员 2 的 Vue 3 前端分支；
4. 成员 1 的契约、集成测试和修复分支最后合并。

如果成员 4 与成员 3 同时修改了依赖文件，应先分别保留 `base.txt` 和 `ai.txt`，由成员 1 检查 Docker 是否同时安装两者。任何人合并前都要先更新最新 `main`，解决冲突并重跑自己模块的测试。

---

## 6. 每个人每天交给组长的信息

不需要额外写形式主义文档，只需要在群里发下面六项：

```text
1. 我的分支和 PR 链接：
2. 今天已经能运行的功能：
3. Codex 实际运行并通过的测试/构建：
4. 我自己点页面或调接口的验收结果：
5. 其他成员接入时要使用的接口/字段：
6. 尚未解决、可能阻塞明天的问题：
```

---

## 7. 最终满分亮点检查

最终演示时至少要让老师真实看到以下亮点，而不是只在 PPT 中写：

- MySQL 保存项目、任务、产物与版本，Chroma 保存可检索向量，两者职责清楚；
- 上传教材/课标后，生成内容可以点开来源文件和页码/章节；
- 五类教学 Skills 可独立测试与组合，不是一个超长 Prompt；
- 教学目标、课堂活动、评价和练习能通过编号对应；
- Slidev 课件、逐页讲稿和分层练习由同一教学蓝图生成；
- 局部修改某页时，其他页面保持不变，且旧版本可以恢复；
- LangGraph 流程节点、质量问题、定向返修和人工确认可见；
- 教师包与学生包内容不同，学生包不含答案和讲稿；
- AI 超时、无资料、结构失败时系统能够解释和恢复；
- 所有关键能力都有实际测试或真实演示支撑，没有写死结果和伪造来源。
