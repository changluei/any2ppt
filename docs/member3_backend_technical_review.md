# 成员 3 后端开发技术详解与答辩复习

更新日期：2026-07-21  
适用范围：成员 3 负责的后端工程、数据库、接口、测试、部署和验收内容。

本文档用于答辩复习，重点说明“为什么这样设计、关键代码在哪里、如何证明已经完成”。接口使用方法和前端调用示例见 `docs/member3_backend_usage.md`。

## 1. 后端总体架构

本项目后端采用 FastAPI + SQLAlchemy + Alembic + MySQL 的典型分层结构：

```text
backend/app/
  main.py                 FastAPI 应用入口、中间件、统一异常、健康检查
  core/
    config.py             环境变量与配置
    database.py           SQLAlchemy engine/session
  models/
    entities.py           ORM 数据模型
  schemas/
    api.py                Pydantic 请求/响应模型
  repositories/
    projects.py           项目相关数据库读写封装
  services/
    source_service.py     上传、索引、搜索、删除资料
    artifact_service.py   AI 任务、产物版本、图状态
    export_service.py     教师包/学生包导出
  api/routes/
    projects.py           项目接口
    sources.py            资料接口
    tasks.py              任务接口
    artifacts.py          产物和版本接口
    workflow.py           图状态与导出接口
```

分层的目的：

- `routes` 只处理 HTTP 参数、依赖注入和响应，不写复杂业务。
- `schemas` 统一前后端数据契约，避免接口返回随意变化。
- `services` 承担核心业务流程，例如上传校验、任务生成、版本回滚、导出打包。
- `repositories` 封装复用查询逻辑，降低 route/service 对 SQL 细节的耦合。
- `models` 只表达数据库结构和关系。
- `core` 放应用基础能力，例如配置、数据库连接。

答辩时可以说明：这样做的好处是后续替换 AI 服务、替换存储、增加权限系统时，不需要大面积修改接口层。

## 2. 配置与环境变量

关键文件：

- `backend/app/core/config.py`
- `.env.example`
- `.env`

配置通过 Pydantic Settings 读取，支持根目录 `.env` 和 `backend/.env`。生产或演示时可以用环境变量覆盖默认配置。

核心配置项：

- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_DATABASE`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `DATABASE_URL`
- `DEEPSEEK_API_KEY`
- `BACKEND_CORS_ORIGINS`

数据库 URL 构造规则：

- 如果显式设置 `DATABASE_URL`，优先使用它。
- 否则根据 MySQL 配置组装 `mysql+pymysql://.../lessondeck?charset=utf8mb4`。

安全点：

- `.env` 已被 `.gitignore` 忽略，不提交真实密码和 API Key。
- `.env.example` 只保留示例值，方便其他成员复制。
- 本机 3306 已被 `MySQL80` 占用，所以项目 Docker MySQL 使用 `3307`，避免破坏已有服务。

## 3. 数据库与迁移

关键文件：

- `backend/app/core/database.py`
- `backend/app/models/entities.py`
- `backend/migrations/versions/0001_initial.py`
- `backend/migrations/versions/0002_task_result_snapshot.py`

数据库选型为 MySQL 8，原因：

- 满足 md 要求的 MySQL 持久化。
- 项目、资料、任务、版本、图状态和导出任务都需要稳定事务。
- JSON 字段可保存任务 payload、产物内容、错误摘要、版本选择等半结构化数据。

迁移使用 Alembic，不在启动时用 `Base.metadata.create_all()` 自动建表。这样可以保证表结构可追踪、可回滚、可在答辩时说明数据库演进过程。

当前主要表：

| 表 | 作用 |
| --- | --- |
| `projects` | 备课项目，保存学情和教师要求 |
| `source_documents` | 上传资料元数据、索引状态、文件 hash |
| `ai_tasks` | AI 任务状态、阶段、进度、错误摘要 |
| `lesson_artifacts` | 教案、课件大纲、练习、讲稿等当前产物 |
| `artifact_versions` | 产物不可变版本、父版本、修改范围 |
| `graph_runs` | LangGraph/流程图运行状态，可恢复 |
| `export_jobs` | 导出任务、包类型、文件路径、版本选择 |

答辩重点：

- MySQL 存元数据和业务状态。
- 文件系统存原始上传文件和导出 zip。
- Chroma/向量数据以可重建索引形式存在，不能替代 MySQL 事务库。

## 4. API 设计

关键文件：

- `backend/app/main.py`
- `backend/app/api/routes/*.py`
- `backend/app/schemas/api.py`

接口统一挂载在 `/api` 下。前端推荐从环境变量读取：

```ts
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
```

接口响应采用 Pydantic 模型，核心对象包括：

- `ProjectOut`
- `SourceDocumentOut`
- `AITaskOut`
- `ArtifactOut`
- `ArtifactVersionOut`
- `GraphRunOut`
- `ExportJobOut`

错误统一格式：

```json
{
  "error": {
    "code": "not_found",
    "message": "Project not found",
    "details": {},
    "trace_id": "..."
  }
}
```

这样前端可以用 `error.code` 做用户提示，用 `trace_id` 对照后端日志排查问题。

## 5. 资料上传与索引

关键文件：

- `backend/app/services/source_service.py`
- `backend/app/api/routes/sources.py`

上传流程：

1. 前端使用 `multipart/form-data` 提交文件。
2. 后端校验项目是否存在。
3. 校验扩展名和 MIME 类型，只允许 PDF、DOCX、TXT、Markdown。
4. 计算文件 hash，阻止同项目重复上传。
5. 清洗文件名，避免路径穿越。
6. 文件写入 `backend/data/uploads/{project_id}/`。
7. MySQL 保存 `source_documents` 元数据。
8. 索引状态从 `pending` 变为 `indexed` 或 `failed`。

安全点：

- 不相信浏览器传来的原始文件名。
- 不允许 `../` 这类路径逃逸。
- 删除资料时同时清理元数据、上传文件和可重建索引。
- 生成数据目录已加入 `.gitignore`，防止把用户资料提交到仓库。

## 6. AI 任务与执行状态

关键文件：

- `backend/app/services/artifact_service.py`
- `backend/app/api/routes/tasks.py`

任务模型 `AITask` 记录：

- `status`：pending/running/succeeded/failed/cancelled
- `stage`：资料准备、生成、保存等阶段
- `progress`：0 到 100
- `trace_id`：端到端排查标识
- `request_payload`：任务输入
- `result_payload`：任务结果摘要
- `error_summary`：失败原因

任务创建有幂等逻辑：同一项目、同一技能和同一资料组合重复提交时，会复用已有任务，避免重复生成和重复扣费。

没有真实 `DEEPSEEK_API_KEY` 时，后端生成带有明确降级标记的规则草案，用于保证演示流程可跑通；答辩时要说明这不是冒充真实 AI，而是可观测的 fallback。

## 7. 产物版本与局部修改

关键文件：

- `backend/app/services/artifact_service.py`
- `backend/app/api/routes/artifacts.py`
- `backend/app/models/entities.py`

四类产物：

- lesson_plan：教案
- slide_deck：课件
- exercise_set：练习题
- speaker_notes：讲稿

版本设计：

- `lesson_artifacts` 保存某类产物的当前版本号。
- `artifact_versions` 保存每次生成、修改、回滚形成的不可变快照。
- `parent_version_id` 记录从哪个版本派生。
- `change_type` 标识 full_generation、partial_revision、rollback 等。
- `changed_ids` 记录局部修改影响的段落、题目或模块。
- `base_version_no` 做乐观锁，防止两个前端页面同时修改覆盖彼此结果。

答辩重点：

- “不可变版本”让回滚和审计更可靠。
- “当前产物”提升查询效率。
- “乐观锁”解决并发编辑冲突。

## 8. 图状态与人机协同

关键文件：

- `backend/app/services/artifact_service.py`
- `backend/app/api/routes/workflow.py`

`GraphRun` 用于持久化流程图运行状态：

- `status`
- `current_node`
- `state`
- `last_error`

支持接口：

- 启动图运行
- 查询当前节点和状态
- 人工确认
- 取消运行
- 恢复运行

这样即使服务重启或前端刷新，也能通过 MySQL 找回流程状态。答辩时可以把它解释为 LangGraph 或类 LangGraph 工作流的后端状态基座。

## 9. 导出服务

关键文件：

- `backend/app/services/export_service.py`
- `backend/app/api/routes/workflow.py`

导出类型：

- teacher：教师包，包含教案、课件大纲、练习答案、讲稿。
- student：学生包，隐藏答案、解析和讲稿，只保留学生可见内容。

导出安全设计：

- 临时文件只写入受控临时目录。
- 打包完成后原子移动到正式目录。
- 下载时只允许访问导出目录内的文件，防止任意路径下载。
- `ExportJob` 保存状态、包类型、文件路径和选择的版本。
- 支持传入 `artifact_version_ids`，前端可以导出指定版本组合。

答辩重点：学生包不能泄露答案和教师讲稿，这是智慧教育场景里非常具体的业务安全要求。

## 10. 健康检查与可观测性

关键文件：

- `backend/app/main.py`

健康接口：

- `GET /health`：服务进程是否可用。
- `GET /health/db`：数据库连接是否可用。
- `GET /health/ai`：AI 配置是否存在；没有 Key 时返回 degraded。
- `GET /health/chroma`：向量数据目录是否可用。

所有请求响应头包含 `X-Trace-ID`。异常响应体也包含 `trace_id`。答辩时可以说明：这让前端报错截图、后端日志和数据库任务记录能串起来。

## 11. 测试与验收

关键文件：

- `backend/tests/test_backend_api.py`
- `tests/e2e/member3_day1_acceptance.py`
- `tests/e2e/member3_days2_8_acceptance.py`
- `conftest.py`
- `pytest.ini`

测试分三层：

- 单元/接口测试：`python -m pytest -q`
- 第一天专项验收：`python tests\e2e\member3_day1_acceptance.py`
- 第 2-8 天综合验收：`python tests\e2e\member3_days2_8_acceptance.py`

当前验收覆盖：

- 工程结构、配置、MySQL、Alembic、`.env` 安全。
- 上传、索引、搜索、删除、项目隔离。
- 技能列表、任务幂等、任务轮询、四类产物。
- trace_id、统一错误、任务阶段和进度。
- 局部修改、版本冲突、回滚。
- 图运行查询、确认、取消、恢复。
- 教师包/学生包导出和答案隐藏。
- 全量 pytest、compose 配置、生成数据不跟踪。
- 健康检查和本机 MySQL 可用性。

## 12. 每日技术复习提纲

### 第 1 天

主题：工程结构、配置、MySQL、迁移。

必须会讲：

- 为什么不用 SQLite 作为正式库。
- `.env` 和 `.env.example` 的区别。
- 为什么用 Alembic，而不是启动时自动建表。
- `config.py` 如何生成 MySQL URL。
- Docker MySQL 为什么使用 3307。

### 第 2 天

主题：资料上传、索引、搜索和删除。

必须会讲：

- 文件内容为什么不直接存 MySQL。
- 如何防止重复上传。
- 如何防止路径穿越。
- 删除资料时为什么要同时处理文件、元数据和索引。
- 项目隔离如何保证搜索不串数据。

### 第 3 天

主题：项目、任务、产物和版本基础。

必须会讲：

- `Project`、`AITask`、`LessonArtifact`、`ArtifactVersion` 的关系。
- 为什么任务要幂等。
- 四类产物为什么分类型存储。
- 第一版产物如何写入版本表。

### 第 4 天

主题：任务执行器、错误处理、trace_id。

必须会讲：

- trace_id 对排查问题的作用。
- 统一错误 envelope 如何方便前端。
- 任务 stage/progress 如何展示进度。
- 任务失败为什么要保存 error_summary。

### 第 5 天

主题：局部修改、版本树和回滚。

必须会讲：

- 不可变版本和当前产物的区别。
- `base_version_no` 乐观锁解决什么问题。
- 回滚为什么也创建一个新版本，而不是直接删除历史。
- `changed_ids` 如何支持局部修改展示。

### 第 6 天

主题：GraphRun、人机确认和导出。

必须会讲：

- 图状态为什么要落库。
- 人工确认节点如何恢复。
- 教师包和学生包的差异。
- 为什么学生包必须隐藏答案和讲稿。
- 原子移动和安全下载路径的意义。

### 第 7 天

主题：测试、安全和部署。

必须会讲：

- pytest 覆盖哪些核心流程。
- docker compose 如何连接 MySQL。
- `.gitignore` 为什么要排除生成数据。
- 数据迁移 current/head 如何验证。

### 第 8 天

主题：干净环境验证和健康检查。

必须会讲：

- `/health/db` 验证什么。
- `/health/ai` degraded 状态代表什么。
- `/health/chroma` 验证什么。
- 为什么 Docker 状态检查可能需要提升权限。

## 13. 答辩常见问答

**问：为什么 MySQL 和 Chroma 都需要？**  
答：MySQL 保存强一致业务状态，例如项目、任务、版本和导出记录；Chroma/向量索引用于资料检索，可从上传资料重建，不能替代事务数据库。

**问：如果 AI 生成失败怎么办？**  
答：任务状态会变成 `failed`，保存 `error_summary` 和 `trace_id`，前端可以展示失败原因，后端可以按 trace_id 排查。

**问：如何防止用户上传危险文件？**  
答：后端限制扩展名和 MIME 类型，清洗文件名，按项目目录保存，不信任客户端路径，并把生成数据排除在 Git 之外。

**问：多人同时编辑同一个产物怎么办？**  
答：局部修改接口要求 `base_version_no`，如果前端基于旧版本提交，会返回版本冲突，避免覆盖别人的修改。

**问：为什么回滚还要生成新版本？**  
答：历史版本不可变，回滚是一种新的变更记录。这样能保留完整审计链，也可以继续从回滚后的版本向前修改。

**问：学生包如何保证不泄露答案？**  
答：导出服务根据 `package_type=student` 过滤练习答案、解析和教师讲稿，验收脚本会检查学生包内容不包含答案字段。

**问：后端如何支持前端？**  
答：接口以项目为核心，前端先建项目，再上传资料，创建任务，轮询任务，读取产物，提交局部修改，最后导出教师包或学生包。详细调用顺序见使用说明文档。

**问：现在是否能在没有真实 AI Key 的情况下演示？**  
答：可以。没有 Key 时 `/health/ai` 返回 degraded，生成服务返回明确标识的降级草案，保证教学流程能演示，但不会伪装成真实模型输出。

## 14. 当前可改进方向

- 引入 Celery/RQ/Redis 承载更长时间的 AI 任务。
- 增加用户登录、角色权限和项目共享。
- 将文件存储替换为对象存储，例如 MinIO 或 OSS。
- 将向量索引从本地 JSON 演示形态替换为正式 Chroma 服务。
- 增加 OpenAPI 客户端生成，减少前端手写接口类型。
