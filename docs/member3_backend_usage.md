# 成员 3 后端使用说明与接口文档

更新日期：2026-07-21  
适用范围：`backend/app/` 非 `ai/` 目录、`backend/migrations/`、`backend/tests/`、部署与后端验收脚本。

本文档按《面向智慧教育的 AI 备课辅助系统_四人8天分工与 Codex 提示词》成员 3 每日任务维护。每完成一天验收，就同步更新“每日验收记录”。

## 1. 当前后端状态

后端已经具备以下能力：

- FastAPI 分层工程：`main.py`、`api/routes/`、`core/`、`models/`、`schemas/`、`services/`、`repositories/`。
- MySQL 8 持久化：项目、资料、任务、产物版本、图状态、导出任务均落库。
- Alembic 正式迁移：当前 head 为 `0001_initial`，启动时不使用 `create_all` 代替迁移。
- 文件上传与资料索引：支持 PDF、DOCX、TXT、Markdown，文件落本地目录，MySQL 只存元数据。
- 任务与产物闭环：创建任务、幂等、轮询、保存四类产物、局部修改、版本冲突、回滚。
- 图状态与导出：GraphRun 持久化，支持查询、取消、恢复、人工确认；支持教师包和学生包导出。
- 统一错误与追踪：响应头和错误体带 `trace_id`，错误码可供前端展示。

## 2. 本机 MySQL 配置

本机已有 `MySQL80` 服务占用 `3306`。为了不影响已有 MySQL，当前项目使用 Docker 单独启动了一个 MySQL 8.4 容器：

- 容器名：`lessondeck-mysql`
- 镜像：`mysql:8.4`
- 本机端口：`3307`
- 容器端口：`3306`
- 数据库：`lessondeck`
- 用户：`lessondeck`
- 密码：`change_me`
- root 密码：`root_change_me`
- 持久化卷：`lessondeck_mysql_data`

本地 `.env` 已配置为：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
MYSQL_DATABASE=lessondeck
MYSQL_USER=lessondeck
MYSQL_PASSWORD=change_me
MYSQL_ROOT_PASSWORD=root_change_me
MYSQL_HOST_PORT=3308
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
AI_TIMEOUT_SECONDS=60
AI_TEMPERATURE=0.2
VITE_API_BASE_URL=http://localhost:8000
```

`.env` 已被 `.gitignore` 忽略，不能提交。`.env.example` 只保留安全示例值。

Docker Desktop 的 CLI 在本机 per-user 路径：

```powershell
$docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
```

常用命令：

```powershell
& $docker ps --filter name=lessondeck-mysql
& $docker stop lessondeck-mysql
& $docker start lessondeck-mysql
```

## 3. 后端启动

安装依赖：

```powershell
cd C:\Users\梁靖泽\Desktop\any2ppt-main\any2ppt
pip install -r backend\requirements\base.txt -r backend\requirements\ai.txt -r backend\requirements\dev.txt
```

启动 MySQL 容器：

```powershell
$docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
& $docker start lessondeck-mysql
```

执行迁移：

```powershell
cd backend
python -m alembic -c alembic.ini upgrade head
```

启动后端：

```powershell
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

访问地址：

- Swagger：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`
- 数据库检查：`http://127.0.0.1:8000/health/db`
- AI 检查：`http://127.0.0.1:8000/health/ai`
- Chroma 检查：`http://127.0.0.1:8000/health/chroma`

## 4. 前端调用总流程

前端所有请求应从 `VITE_API_BASE_URL` 读取 baseURL，开发默认：

```env
VITE_API_BASE_URL=http://localhost:8000
```

建议调用顺序：

1. 调 `GET /health` 和 `GET /health/db`，显示后端和数据库状态。
2. 调 `GET /api/projects` 拉项目列表。
3. 调 `POST /api/projects` 创建备课项目。
4. 调 `POST /api/projects/{project_id}/sources` 上传资料。
5. 上传后轮询 `GET /api/projects/{project_id}/sources/{source_id}`，直到 `ready` 或 `failed`。
6. 调 `POST /api/projects/{project_id}/search` 做检索测试并展示来源。
7. 调 `POST /api/projects/{project_id}/tasks` 发起生成任务。
8. 轮询 `GET /api/tasks/{task_id}`，直到 `succeeded`、`failed` 或 `cancelled`。
9. 成功后调 `GET /api/projects/{project_id}/artifacts` 拉四类产物。
10. 需要修改时调 `POST /api/artifacts/{artifact_id}/revise`。
11. 需要版本面板时调 `GET /api/artifacts/{artifact_id}/versions` 和 `POST /api/artifacts/{artifact_id}/rollback/{version_no}`。
12. 调 `GET /api/projects/{project_id}/graph` 展示流程节点。
13. 教师确认后调 `POST /api/graphs/{graph_id}/confirm`。
14. 调 `POST /api/projects/{project_id}/exports` 创建导出任务。
15. 轮询 `GET /api/exports/{job_id}`，成功后用 `download_url` 下载 ZIP。

## 5. 统一错误格式

后端错误统一为：

```json
{
  "error": {
    "code": "PROJECT_NOT_FOUND",
    "message": "项目不存在",
    "trace_id": "..."
  }
}
```

前端应优先显示 `error.message`，并允许复制 `error.trace_id`。如果请求头带 `X-Trace-ID`，后端会透传到响应头和错误体。

常见错误码：

- `PROJECT_NOT_FOUND`
- `SOURCE_NOT_FOUND`
- `SOURCE_NOT_READY`
- `TASK_NOT_FOUND`
- `TASK_CONFLICT`
- `VERSION_NOT_FOUND`
- `VERSION_CONFLICT`
- `GRAPH_NOT_FOUND`
- `GRAPH_NOT_READY`
- `EXPORT_NOT_FOUND`
- `EXPORT_NOT_READY`
- `EXPORT_ARTIFACTS_MISSING`
- `VALIDATION_ERROR`
- `DATABASE_ERROR`
- `INTERNAL_ERROR`

## 6. 接口清单

### 6.1 健康与技能

`GET /health`

返回后端存活状态。

`GET /health/db`

执行 `SELECT 1`，当前应返回：

```json
{"status": "ok", "database": "mysql"}
```

`GET /health/ai`

返回 DeepSeek 是否配置。没有 `DEEPSEEK_API_KEY` 时是 `degraded`，表示可以降级生成草案，但不能冒充真实模型成功。

`GET /health/chroma`

返回向量存储路径和后端类型。

`GET /api/skills`

返回五类教学 Skill 注册信息，供前端展示 Skill 卡片。

### 6.2 项目

`GET /api/projects`

返回项目列表。

`POST /api/projects`

请求体：

```json
{
  "name": "三年级科学备课",
  "subject": "科学",
  "grade": "三年级",
  "textbook_version": "自编",
  "lesson_topic": "水的三态变化",
  "lesson_count": 1,
  "student_profile": "学生能观察简单现象",
  "teacher_requirements": "强调实验安全"
}
```

`GET /api/projects/{project_id}`

查询单个项目。

`PUT /api/projects/{project_id}`

更新项目。字段同创建接口。

`DELETE /api/projects/{project_id}`

只允许删除空项目。如果已有资料、任务或产物，会返回 `PROJECT_NOT_EMPTY` 和 blockers。

### 6.3 资料与检索

`POST /api/projects/{project_id}/sources`

multipart 上传文件，字段名为 `file`。支持：

- `.pdf` / `application/pdf`
- `.docx`
- `.txt`
- `.md`

后端校验：

- 文件名净化，防路径穿越。
- UUID 存储名，按项目隔离目录保存。
- 扩展名、MIME、大小、空文件校验。
- 同项目 `project_id + sha256` 防重复。
- 数据库写入失败时删除已保存文件。

`GET /api/projects/{project_id}/sources`

列出项目资料。

`GET /api/projects/{project_id}/sources/{source_id}`

查询单个资料状态。状态流：

```text
uploaded -> parsing -> indexing -> ready
failed
```

`POST /api/projects/{project_id}/sources/{source_id}/index`

重新触发索引。

`DELETE /api/projects/{project_id}/sources/{source_id}`

删除资料，并调用向量删除。向量或文件删除失败时会记录错误，不静默不一致。

`POST /api/projects/{project_id}/search`

请求体：

```json
{
  "query": "水蒸气遇冷会发生什么",
  "top_k": 3,
  "source_ids": ["可选 source_id"]
}
```

返回字段：

```json
[
  {
    "content": "检索原文",
    "source_id": "...",
    "chunk_id": "...",
    "filename": "unsafe-name.md",
    "location": "line:1-3",
    "score": 0.92
  }
]
```

### 6.4 任务

`POST /api/projects/{project_id}/tasks`

请求体：

```json
{
  "type": "full_lesson",
  "selected_source_ids": ["source_id"],
  "teacher_requirements": "突出科学观察",
  "idempotency_key": "frontend-click-uuid"
}
```

说明：

- `idempotency_key` 必填，用于防重复点击。
- 选中的资料必须属于当前项目且状态为 `ready`。
- 后端以 BackgroundTasks 执行生成，不引入 Redis/Celery。

`GET /api/projects/{project_id}/tasks`

返回项目最近 20 个任务，供刷新恢复。

`GET /api/tasks/{task_id}`

轮询任务状态。状态：

```text
pending
running
succeeded
failed
cancelled
```

关键字段：

- `stage`：如 `资料检索`、`模型生成`、`结构校验与保存`、`已完成`
- `progress`：0-100
- `trace_id`
- `error_code`
- `error_message`

`POST /api/tasks/{task_id}/cancel`

取消未完成任务。

`POST /api/tasks/{task_id}/retry`

失败或取消任务可以重试，创建新任务尝试，不覆盖旧任务。

### 6.5 产物与版本

四类产物：

- `lesson_plan`
- `slide_deck`
- `speaker_notes`
- `exercise_set`

`GET /api/projects/{project_id}/artifacts`

返回项目当前最新版四类产物。

`GET /api/artifacts/{artifact_id}`

查询产物最新版。

`GET /api/artifacts/{artifact_id}?version=1`

查询指定版本。

`GET /api/artifacts/{artifact_id}/versions`

列出历史版本，新版本在前。

`POST /api/artifacts/{artifact_id}/revise`

请求体：

```json
{
  "base_version_no": 1,
  "target_type": "stages",
  "target_id": "STAGE-1",
  "instruction": "把导入活动写得更贴近生活",
  "sync_related": false
}
```

规则：

- 使用 `base_version_no` 做乐观锁。
- 当前版本不等于 `base_version_no` 时返回 `409 VERSION_CONFLICT`。
- 每次局部修改都会创建新版本。
- 旧版本不会删除。

`POST /api/artifacts/{artifact_id}/rollback/{version_no}`

回滚也创建新版本，不删除历史版本。

### 6.6 图状态

`POST /api/projects/{project_id}/graph/runs`

启动或手动创建图运行记录。

请求体：

```json
{
  "task_id": "可选 task_id",
  "thread_id": "可选 thread_id",
  "checkpoint_ref": "可选 checkpoint 引用"
}
```

`GET /api/projects/{project_id}/graph`

查询项目最新图状态。返回 `nodes`、`issues`、`current_node`、`attempt`、`state_snapshot`。

`POST /api/graphs/{graph_id}/cancel`

取消图流程。

`POST /api/graphs/{graph_id}/resume`

恢复 `cancelled`、`failed`、`needs_revision`、`awaiting_confirmation` 状态的流程。

`POST /api/graphs/{graph_id}/confirm`

请求体：

```json
{"decision": "accept"}
```

`decision` 可取：

- `accept`：流程进入 `succeeded`
- `revise`：流程进入 `needs_revision`
- `cancel`：流程进入 `cancelled`

重复确认幂等。

### 6.7 导出

`POST /api/projects/{project_id}/exports`

请求体：

```json
{
  "package_type": "teacher",
  "artifact_version_ids": []
}
```

说明：

- `package_type=teacher` 需要 `lesson_plan`、`slide_deck`、`speaker_notes`、`exercise_set`。
- `package_type=student` 需要 `slide_deck`、`exercise_set`。
- `artifact_version_ids` 为空时导出当前最新版本。
- 传入版本 ID 时会校验版本属于当前项目，且同一产物类型只能选一个版本。

`GET /api/exports/{job_id}`

轮询导出状态。成功后返回 `download_url`。

`GET /api/exports/{job_id}/download?project_id=...`

下载 ZIP。下载接口会校验路径必须在 `EXPORT_DIR` 下，防止任意读服务器路径。

教师包包含：

- `README.txt`
- `slides.md`
- `slides.html`
- `教学设计.json`
- `逐页讲稿.json`
- `教师版练习.json`
- `引用清单.json`

学生包包含：

- `README.txt`
- `slides.md`
- `slides.html`
- `学生练习.json`

学生包不包含讲稿、答案和解析。

## 7. 验收脚本

第 1 天：

```powershell
python tests\e2e\member3_day1_acceptance.py
```

最新结果：

```text
通过 14，失败 0，未验证 0
```

第 2-8 天：

```powershell
python tests\e2e\member3_days2_8_acceptance.py
```

最新结果：

```text
第2天  资料元数据、上传、索引与检索          通过
第3天  项目任务、产物与版本基础接口          通过
第4天  任务执行、统一错误和 trace_id       通过
第5天  产物版本、局部更新与回滚             通过
第6天  图状态持久化、人工确认与双包导出       通过
第7天  后端测试、MySQL、安全与一键部署静态验收 通过
第8天  干净环境、MySQL 与健康诊断           通过
汇总：通过 7，失败 0，未验证 0
```

全量 pytest：

```powershell
python -m pytest -q
```

最新结果：

```text
7 passed
```

## 8. 每日验收记录

### 第 1 天：FastAPI 与 MySQL 工程骨架

完成内容：

- 后端分层目录。
- pydantic-settings 配置。
- SQLAlchemy 2.x + PyMySQL + MySQL utf8mb4。
- Alembic `0001_initial`。
- `Project` 模型和基础项目接口。
- `/health` 和 `/health/db`。
- CORS 开发配置。
- 第 1 天自动验收脚本。

验收结果：通过 14，失败 0，未验证 0。

### 第 2 天：资料元数据、上传和任务接口

完成内容：

- `SourceDocument` 模型。
- 安全文件保存、MIME/扩展名/大小/空文件/重复校验。
- 上传、列表、单项、删除、重新索引接口。
- 搜索代理接口。
- 删除资料时同步处理向量和文件。

验收结果：上传、索引、重复文件、非法类型、路径清洗、搜索来源、删除、项目隔离均通过。

### 第 3 天：项目、任务、产物与版本基础接口

完成内容：

- `Project` 支持 `student_profile` 和 `teacher_requirements`。
- `AITask`、`LessonArtifact`、`ArtifactVersion`。
- `GET /api/skills`。
- 任务创建、幂等、轮询、取消、重试。
- 四类产物第一版保存。

验收结果：Skill 列表、任务幂等、状态轮询、任务列表和四类第一版产物均通过。

### 第 4 天：任务执行器、统一错误和 trace_id

完成内容：

- HTTP 请求和 AI 任务 trace_id。
- 统一错误 envelope。
- 任务阶段和 progress。
- 失败摘要与错误码。
- 成功后事务保存产物版本。

验收结果：trace_id 响应头/错误体、统一错误码、任务阶段和进度均通过。

### 第 5 天：产物版本、局部更新和回滚接口

完成内容：

- 不可变版本。
- `parent_version_id`、`change_type`、`changed_ids`。
- 局部修改接口。
- `base_version_no` 乐观锁。
- 版本列表和回滚。

验收结果：局部修改、版本列表、版本冲突和回滚创建新版本均通过。

### 第 6 天：图状态持久化、恢复和导出服务

完成内容：

- `GraphRun`。
- 图启动、查询、取消、恢复、人工确认。
- `ExportJob`。
- 教师包和学生包导出。
- 受控临时目录、原子移动、安全下载路径。
- 学生包隐藏答案和讲稿。

验收结果：图查询/确认/取消/恢复、教师包、学生包答案隐藏和安全下载均通过。

### 第 7 天：后端测试、MySQL、安全与一键部署

完成内容：

- 全量后端测试。
- MySQL 迁移当前版本检查。
- Docker Compose 配置解析。
- `.gitignore` 防止 `.env`、上传文件、导出包、Chroma 数据入库。
- `deploy/docker-compose.yml` 支持 `MYSQL_HOST_PORT` 避让本机 3306 冲突。

验收结果：pytest 全量通过、MySQL 迁移当前版本正确、compose 可解析、生成数据未跟踪。

### 第 8 天：干净环境、MySQL 与接口保障

完成内容：

- 本机项目专用 MySQL 容器。
- `.env` 指向 `127.0.0.1:3307`。
- `/health`、`/health/db`、`/health/ai`、`/health/chroma`。
- Docker 状态诊断命令。

验收结果：API/MySQL/AI/Chroma 健康检查可用；普通权限查看 Docker 状态可能需要提升权限。

## 9. 当前真实限制

- 没有 `DEEPSEEK_API_KEY` 时，AI 生成使用明确标识的规则降级草案，不冒充真实模型成功。
- 当前任务 runner 使用 FastAPI BackgroundTasks，适合演示和轻量场景；生产级长任务可后续接 Redis/Celery。
- 当前没有复杂用户权限系统，演示版以项目隔离和路径安全为主。
- Docker Desktop 在本机是 per-user 安装，CLI 不在默认 PATH，脚本已兼容该路径。
