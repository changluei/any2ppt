# Any2PPT 功能代码查询手册

> 本文档用于从“产品功能”反查前端页面、HTTP 接口、核心实现和数据位置。  
> 链接均为仓库相对路径并带 `#L行号`，在 GitHub 或支持行号片段的 IDE 中
> 点击即可跳转。

## 1. 怎么使用

1. 在“功能总索引”找到用户看到的功能。
2. 打开“前端入口”，确认请求参数和页面状态。
3. 打开“后端接口”，确认 HTTP 校验与错误码。
4. 进入“核心实现”，查看事务、AI、RAG、渲染或文件操作。
5. 涉及数据丢失、缓存或迁移时，再看“数据存储地图”。

## 2. 系统结构总览

| 层级 | 职责 | 总入口 |
| --- | --- | --- |
| Vue 前端 | 页面交互、生成锁、轮询、工作台即时状态 | [main.ts](../frontend/src/main.ts#L1)、[router.ts](../frontend/src/router.ts#L9) |
| 前端 API | 拼接请求、校验响应结构、统一错误 | [api/index.ts](../frontend/src/api/index.ts#L10)、[api/http.ts](../frontend/src/api/http.ts#L1) |
| FastAPI | 参数校验、资源边界、路由分发、统一错误信封 | [main.py](../backend/app/main.py#L1) |
| Service | 数据库事务、版本、文件、工作流和业务规则 | [services/](../backend/app/services/) |
| AI / RAG | DeepSeek、教学技能、LangGraph、ReAct、向量检索 | [ai/](../backend/app/ai/) |
| Renderer | Slidev 主题安装缓存、布局扫描、预览和 PPTX | [server.mjs](../renderer/server.mjs#L1) |
| 持久化 | MySQL 保存业务事实；Chroma 保存 chunk 与向量 | [entities.py](../backend/app/models/entities.py#L1)、[vector_store.py](../backend/app/ai/vector_store.py#L1) |
| 部署 | Docker 服务拓扑、共享卷和健康检查 | [docker-compose.yml](../deploy/docker-compose.yml#L3) |

主调用方向：

```text
Vue 页面
  → frontend/src/api
  → FastAPI route
  → service（事务与业务规则）
  → AI/RAG、MySQL、Chroma、文件系统或 Slidev renderer
  → Pydantic 响应
  → Vue 页面同步状态
```

## 3. 功能总索引

### 3.1 首页、主题与创建

| 功能 | 前端入口 | 后端接口 | 核心实现 / 数据 |
| --- | --- | --- | --- |
| 首页加载主题和知识库 | [CreatePage.load](../frontend/src/pages/CreatePage.vue#L72) | [GET `/api/themes`](../backend/app/main.py#L176)、[知识库列表](../backend/app/api/routes/knowledge_bases.py#L38) | [主题目录](../backend/app/services/theme_service.py#L19)、[theme_catalog.json](../backend/app/theme_catalog.json) |
| 主题分类、搜索与预览 | [CreatePage.vue](../frontend/src/pages/CreatePage.vue#L1)、[ThemePreview.vue](../frontend/src/components/ThemePreview.vue#L1) | 无下载请求 | 静态预览在 [theme-previews/](../frontend/public/theme-previews/) |
| 选择主题后展开表单 | [chooseTheme](../frontend/src/pages/CreatePage.vue#L108) | 此时不安装 | 真正安装在 [prepare_project_theme](../backend/app/services/theme_service.py#L162) |
| 标题与描述分离 | [saveAndGenerate](../frontend/src/pages/CreatePage.vue#L148) | [ProjectCreate](../backend/app/schemas/api.py#L19) | 标题为 `Project.name`，描述为 `teacher_requirements`，实体见 [Project](../backend/app/models/entities.py#L31) |
| 多选语数英/个人库 | [CreatePage.vue](../frontend/src/pages/CreatePage.vue#L1) | [创建项目](../backend/app/api/routes/projects.py#L39) | [知识库选择校验](../backend/app/services/knowledge_base_service.py#L95) |
| 可选上传资料 | [CreatePage.addFiles](../frontend/src/pages/CreatePage.vue#L115) | 上传由生成页接管 | [validateSourceFile](../frontend/src/utils/files.ts#L8) |
| 创建项目 | [saveAndGenerate](../frontend/src/pages/CreatePage.vue#L148) | [POST `/api/projects`](../backend/app/api/routes/projects.py#L39) | [Project](../backend/app/models/entities.py#L31)、[主题准备](../backend/app/services/theme_service.py#L162) |
| 主题推荐 | [api.recommendTheme](../frontend/src/api/index.ts#L10) | [recommend_theme](../backend/app/main.py#L182) | [select_theme](../backend/app/services/theme_service.py#L125) |

### 3.2 主题下载、缓存与布局能力

| 功能 | API / 入口 | 核心实现 | 关键说明 |
| --- | --- | --- | --- |
| 选中模板后才下载 | [创建项目 API](../backend/app/api/routes/projects.py#L39) | [prepare_project_theme](../backend/app/services/theme_service.py#L162) | 首页只读元数据 |
| 已用模板直接复用 | Renderer [prepare](../renderer/server.mjs#L348) | [ensureThemePackage](../renderer/server.mjs#L303) | 合并并发下载，磁盘缓存跨项目复用 |
| 主题安装白名单 | Renderer 常量 | [allowedThemes](../renderer/server.mjs#L24) | 只允许固定包名和版本 |
| 扫描模板布局 | [get_theme_capabilities](../backend/app/services/theme_service.py#L92) | [buildCapabilities](../renderer/server.mjs#L165) | 扫描 layout 的 props、slots、图片能力 |
| 告诉 AI 布局如何用 | [生成上下文](../backend/app/services/graph_service.py#L48) | [布局语义选择](../backend/app/ai/generation.py#L73) | 用途、slot 和 Markdown pattern 进入生成上下文 |
| 真实主题预览 | [preview API](../backend/app/api/routes/artifacts.py#L51) | [preview service](../backend/app/services/preview_service.py#L62)、[renderer](../renderer/server.mjs#L405) | PNG 按制品版本与主题缓存 |
| 主题化 PPTX | [导出 API](../backend/app/api/routes/workflow.py#L239) | [renderer render](../renderer/server.mjs#L362) | 使用真实 Slidev 主题 |

### 3.3 强制生成链路

| 功能 | 前端入口 | 后端入口 | 核心实现 |
| --- | --- | --- | --- |
| 建立生成会话 | [beginGenerationSession](../frontend/src/services/generationSession.ts#L46) | 无 | ID/幂等键写 sessionStorage，File 留内存 |
| 生成期禁止导航 | [router.beforeEach](../frontend/src/router.ts#L18) | 无 | 活动 session 只能进入 `/generating` |
| 生成锁定页 | [runGeneration](../frontend/src/pages/GenerationPage.vue#L114) | 多接口串联 | 创建/更新 → 上传 → 等待索引 → 创建任务 → 轮询 |
| 上传本轮资料 | [uploadSources](../frontend/src/pages/GenerationPage.vue#L54) | [资料 API](../backend/app/api/routes/sources.py#L29) | [save_upload](../backend/app/services/source_service.py#L38)、[index_source](../backend/app/services/source_service.py#L89) |
| 自动归档个人库 | 同上 | [个人库上传](../backend/app/api/routes/knowledge_bases.py#L68) | [SourceDocument](../backend/app/models/entities.py#L82) |
| 幂等创建任务 | [api.createTask](../frontend/src/api/index.ts#L10) | [create_task](../backend/app/api/routes/projects.py#L168) | 唯一约束见 [AITask](../backend/app/models/entities.py#L159) |
| 轮询并跳工作台 | [pollTask](../frontend/src/pages/GenerationPage.vue#L90) | [任务查询](../backend/app/api/routes/tasks.py#L15) | 完成后清 session 才解除导航锁 |
| 失败重试 | [GenerationPage.retry](../frontend/src/pages/GenerationPage.vue#L181) | [retry_task](../backend/app/api/routes/tasks.py#L38) | 沿用输入快照 |
| 完整生成转图 | [run_generation_task](../backend/app/services/artifact_service.py#L269) | — | 转入 [start_task_graph](../backend/app/services/graph_service.py#L550) |

### 3.4 AI 生成与质量控制

| 功能 | 入口 | 核心代码 | 结果 |
| --- | --- | --- | --- |
| 创建 GraphRun | [start_graph API](../backend/app/api/routes/workflow.py#L117) | [create_graph_run](../backend/app/services/graph_service.py#L205) | 保存 thread、节点、state 和 checkpoint |
| 构建生成图 | — | [build_langgraph](../backend/app/ai/graph.py#L307) | 节点和条件边 |
| 执行与进度同步 | — | [execute_graph_run](../backend/app/services/graph_service.py#L496) | 同步 GraphRun 与 AITask |
| RAG 检索 | 技能内部 | [retrieve_evidence](../backend/app/ai/retriever.py#L60) | 引用、冲突提示、降级状态 |
| 教学生成技能 | [run_skill](../backend/app/ai/skills.py#L352) | [TeachingSkill](../backend/app/ai/skills.py#L84) | DeepSeek 结构或规则 fallback |
| 教学蓝图 | — | [design_lesson_blueprint](../backend/app/ai/generation.py#L467) | 目标、活动、评价、引用 |
| 页面提纲 | — | [generate_slide_outlines](../backend/app/ai/generation.py#L522) | 使用真实 layout 与 slot |
| 分层练习 | — | [generate_exercises](../backend/app/ai/generation.py#L541) | 与目标 ID 对齐 |
| 四类制品 | — | [materialize_lesson_artifacts](../backend/app/ai/generation.py#L565) | 教案、课件、讲稿、练习 |
| 质量审查 | — | [review_quality](../backend/app/ai/graph.py#L184) | 规则 + 可选模型复核 |
| 人工确认 | 工作流 API | [confirm_graph](../backend/app/api/routes/workflow.py#L217) | 接受、返工或取消 |
| 保存生成结果 | — | [_persist_graph_result](../backend/app/services/graph_service.py#L406) | 不可变 ArtifactVersion |
| 兼容生成入口 | — | [generate_lesson_bundle](../backend/app/ai/generation.py#L612) | GenerationBundle 与 trace |

### 3.5 工作台、预览与 Markdown

| 功能 | 前端入口 | 后端入口 | 核心实现 |
| --- | --- | --- | --- |
| 恢复工作台状态 | [WorkbenchPage.load](../frontend/src/pages/WorkbenchPage.vue#L92) | 项目/任务/制品/版本/对话接口 | [API 门面](../frontend/src/api/index.ts#L10) |
| 左侧页面与版本 | [WorkbenchPage.vue](../frontend/src/pages/WorkbenchPage.vue#L1) | [版本列表](../backend/app/api/routes/artifacts.py#L42) | 当前版本是编辑基线 |
| 浏览器即时预览 | [SlidevPreview.vue](../frontend/src/components/SlidevPreview.vue#L1) | 无 | MarkdownIt + DOMPurify + iframe |
| 真实 Slidev 预览 | [api.previewUrl](../frontend/src/api/index.ts#L10) | [preview](../backend/app/api/routes/artifacts.py#L51) | [render_slide_preview](../backend/app/services/preview_service.py#L62) |
| 浅色 Markdown 编辑 | [changeMarkdown](../frontend/src/pages/WorkbenchPage.vue#L239) | — | 工作台 scoped CSS |
| 防抖自动保存 | [flushMarkdownAutosave](../frontend/src/pages/WorkbenchPage.vue#L255) | [save_markdown](../backend/app/api/routes/artifacts.py#L84) | [update_slide_markdown](../backend/app/services/artifact_service.py#L441) |
| 同步预览与源码 | [updateArtifact](../frontend/src/pages/WorkbenchPage.vue#L232) | 响应直接带新 Artifact | 不必刷新页面 |
| 乐观并发 | `base_version_no` | 冲突返回 409 | 写服务比较 `current_version_no` |
| 切页前保存 | [selectSlide](../frontend/src/pages/WorkbenchPage.vue#L403) | Markdown 保存 API | 使用稳定 slide_id |
| 历史回滚 | 版本选择器 | [rollback](../backend/app/api/routes/artifacts.py#L163) | 复制历史内容为新版本 |

### 3.6 ReAct AI 对话编辑

| 功能 | 前端入口 | 后端入口 | Agent / 工具 |
| --- | --- | --- | --- |
| 恢复聊天 | [WorkbenchPage.load](../frontend/src/pages/WorkbenchPage.vue#L92) | [messages](../backend/app/api/routes/editor_agent.py#L27) | [EditorAgentMessage](../backend/app/models/entities.py#L132) |
| 发送修改要求 | [sendChat](../frontend/src/pages/WorkbenchPage.vue#L324) | [chat](../backend/app/api/routes/editor_agent.py#L41) | [run_editor_chat](../backend/app/services/editor_agent_service.py#L419) |
| 行为规范与工具 | — | — | [SYSTEM_PROMPT](../backend/app/ai/editor_agent.py#L62) |
| 动作—观察循环 | — | — | [run_editor_react_agent](../backend/app/ai/editor_agent.py#L194) |
| inspect/search/rewrite/validate | — | — | [ProjectEditorToolbox](../backend/app/services/editor_agent_service.py#L57) |
| 重写页面 | — | — | [rewrite_slide_from_agent](../backend/app/services/artifact_service.py#L493) |
| 根据动作生成回复 | — | — | [specific_agent_response](../backend/app/ai/editor_agent.py#L102) |
| 模型不可用降级 | — | — | [_fallback_chat](../backend/app/services/editor_agent_service.py#L369) |
| 右栏聊天独立滚动 | [WorkbenchPage.vue](../frontend/src/pages/WorkbenchPage.vue#L1) | 无 | 输入框固定，线程内部滚动 |

一次请求的真实顺序：

```text
消息 + current_slide_id + base_version_no + 可选 image_id
  → 保存 user 消息
  → DeepSeek 选择 action
  → Toolbox 执行并返回 observation
  → observation 回填模型
  → 最多 7 步、最多 3 次 mutation
  → 保存 assistant 回复和精简工具轨迹
  → 发生 mutation 时响应携带新 Artifact
  → 前端 updateArtifact 同步预览和 Markdown
```

### 3.7 图片

| 功能 | 前端入口 | 后端入口 | 核心实现 |
| --- | --- | --- | --- |
| 对话附件上传 | [imagesApi.upload](../frontend/src/api/images.ts#L5) | [upload_image](../backend/app/api/routes/images.py#L29) | [save_image](../backend/app/services/image_service.py#L51) |
| 图片内容地址 | [imagesApi.url](../frontend/src/api/images.ts#L5) | [image_content](../backend/app/api/routes/images.py#L65) | 不暴露磁盘路径 |
| Agent 放图 | [sendChat](../frontend/src/pages/WorkbenchPage.vue#L324) | ReAct chat | [add_slide_image](../backend/app/services/artifact_service.py#L615) |
| 手动放图 | 工作台 | [place_image](../backend/app/api/routes/artifacts.py#L109) | 五种位置预设 |
| 移除图片引用 | [removeImage](../frontend/src/pages/WorkbenchPage.vue#L383) | [unplace_image](../backend/app/api/routes/artifacts.py#L139) | [remove_slide_image](../backend/app/services/artifact_service.py#L666) |
| 图片理解边界 | 文件名、尺寸、用户描述 | Agent context 标记无视觉 | DeepSeek 文本 API 不读取图片像素 |

### 3.8 知识库与 RAG

| 功能 | 前端入口 | 后端入口 | 数据 / 实现 |
| --- | --- | --- | --- |
| 四库初始化 | 应用启动 | [lifespan](../backend/app/main.py#L33) | [ensure_knowledge_bases](../backend/app/services/knowledge_base_service.py#L54) |
| 查看库统计 | [KnowledgePage.load](../frontend/src/pages/KnowledgePage.vue#L37) | [list_knowledge_bases](../backend/app/api/routes/knowledge_bases.py#L38) | [KnowledgeBase](../backend/app/models/entities.py#L59) |
| 查看原始资料 | [loadSources](../frontend/src/pages/KnowledgePage.vue#L50) | [list_sources](../backend/app/api/routes/knowledge_bases.py#L57) | [SourceDocument](../backend/app/models/entities.py#L82) |
| 上传个人资料 | [knowledgeBasesApi.upload](../frontend/src/api/knowledgeBases.ts#L5) | [upload_personal_source](../backend/app/api/routes/knowledge_bases.py#L68) | [save_upload](../backend/app/services/source_service.py#L38) |
| 解析文件 | 后台索引 | — | [parse_document](../backend/app/ai/ingestion.py#L110) |
| 重叠切片 | 后台索引 | — | [split_blocks](../backend/app/ai/ingestion.py#L182) |
| embedding | 入库和查询 | — | [create_embedding_provider](../backend/app/ai/embeddings.py#L95) |
| chunk 与向量 | 后台索引 | — | [ProjectVectorStore](../backend/app/ai/vector_store.py#L39) |
| 多库检索 | 创建页多选库 | [search API](../backend/app/api/routes/knowledge_bases.py#L44) | [search_knowledge_bases](../backend/app/services/knowledge_base_service.py#L119) |
| 删除个人资料 | [knowledgeBasesApi.remove](../frontend/src/api/knowledgeBases.ts#L5) | [remove_personal_source](../backend/app/api/routes/knowledge_bases.py#L111) | 同删文件、MySQL 和向量 |
| 导入官方资料 | 运维脚本 | — | [import_official_knowledge_bases.py](../backend/scripts/import_official_knowledge_bases.py#L53) |
| Chroma 健康 | 诊断 | [health_chroma](../backend/app/main.py#L159) | Chroma 或测试 JSON fallback |

### 3.9 我的演示、版本与删除

| 功能 | 前端入口 | 后端入口 | 数据 |
| --- | --- | --- | --- |
| 我的演示 | [ProjectsPage.load](../frontend/src/pages/ProjectsPage.vue#L40) | [list_projects_route](../backend/app/api/routes/projects.py#L33) | [Project](../backend/app/models/entities.py#L31) |
| 本地搜索 | [ProjectsPage.vue](../frontend/src/pages/ProjectsPage.vue#L27) | 无 | 名称、课题、学科、年级 |
| 继续编辑 | [openProject](../frontend/src/pages/ProjectsPage.vue#L52) | 工作台接口 | [workbenchPath](../frontend/src/utils/workbench.ts#L16) |
| 删除演示 | [deleteProject](../frontend/src/pages/ProjectsPage.vue#L57) | [delete_project](../backend/app/api/routes/projects.py#L101) | 非 force 先给关联统计 |
| 制品/版本 | 工作台 | [list_artifacts](../backend/app/api/routes/projects.py#L229) | [LessonArtifact](../backend/app/models/entities.py#L185)、[ArtifactVersion](../backend/app/models/entities.py#L205) |
| 版本差异响应 | 工作台/API | [artifact_out](../backend/app/services/artifact_service.py#L179) | changed_ids + unchanged_hashes |
| 统一保存版本 | 所有写入口 | — | [save_version](../backend/app/services/artifact_service.py#L244) |
| 内容校验 | 保存前 | — | [validate_artifact_content](../backend/app/services/artifact_service.py#L222) |

### 3.10 导出

| 功能 | 前端入口 | 后端入口 | 实现 |
| --- | --- | --- | --- |
| 发起 PPTX | [downloadPpt](../frontend/src/pages/WorkbenchPage.vue#L202) | [export_project](../backend/app/api/routes/workflow.py#L239) | 创建 [ExportJob](../backend/app/models/entities.py#L253) |
| 冻结版本 | 当前版本 ID | [resolve_export_versions](../backend/app/api/routes/workflow.py#L32) | 编辑不会改变正在导出的内容 |
| 后台导出 | BackgroundTasks | — | [create_export](../backend/app/services/export_service.py#L377) |
| Slidev PPTX | 导出服务调用 | — | [renderer render](../renderer/server.mjs#L362) |
| 状态 | 工作台轮询 | [export_status](../backend/app/api/routes/workflow.py#L260) | succeeded 后下载 |
| 下载 | 浏览器 URL | [download_export](../backend/app/api/routes/workflow.py#L277) | 校验状态、归属、文件 |
| 教师/学生包 | package_type | 同上 | 要求集合在 [workflow.py](../backend/app/api/routes/workflow.py#L22) |

## 4. 数据存储地图

| 数据 | 保存位置 | 定义 | 备份要求 |
| --- | --- | --- | --- |
| 项目、知识库目录、文件元数据 | MySQL | [entities.py](../backend/app/models/entities.py#L31) | 必须导出 |
| AI 任务 | MySQL `ai_tasks` | [AITask](../backend/app/models/entities.py#L159) | 与项目一起 |
| Graph 状态/checkpoint | MySQL `graph_runs` | [GraphRun](../backend/app/models/entities.py#L229) | 恢复生成需要 |
| 课件版本快照 | MySQL `artifact_versions` | [ArtifactVersion](../backend/app/models/entities.py#L205) | 编辑历史需要 |
| ReAct 对话 | MySQL `editor_agent_messages` | [EditorAgentMessage](../backend/app/models/entities.py#L132) | 刷新恢复需要 |
| 上传原文 | `app_data:/app/data/uploads` | [source_service.py](../backend/app/services/source_service.py#L38) | 与数据库同步 |
| chunk、向量、定位 | `app_data:/app/data/chroma` | [vector_store.py](../backend/app/ai/vector_store.py#L39) | 与 embedding 配置一致 |
| 图片 | `uploads/<project>/images` | [image_service.py](../backend/app/services/image_service.py#L51) | 与图片记录同步 |
| 主题缓存 | `app_data:/app/data/themes` | [renderer](../renderer/server.mjs#L303) | 可重建，保留更快 |
| 临时渲染 | `app_data:/app/data/render_jobs` | [renderer](../renderer/server.mjs#L362) | 无需长期备份 |
| 导出文件 | `app_data:/app/data/exports` | [export_service](../backend/app/services/export_service.py#L377) | 可重新导出 |
| 浏览器生成会话 | sessionStorage + 内存 | [generationSession](../frontend/src/services/generationSession.ts#L1) | 不是业务事实 |

知识库不是只存在 MySQL：MySQL 保存目录，Chroma 保存文本片段和向量，
`uploads` 保存原文件；迁移时三者必须配套。

## 5. 知识库打包迁移

| 操作 | 代码 |
| --- | --- |
| 生成 bundle、manifest、SHA-256 | [export_knowledge_bundle.py](../backend/scripts/export_knowledge_bundle.py#L103) |
| 校验 tar 路径 | [safe_extract](../backend/scripts/import_knowledge_bundle.py#L55) |
| 恢复数据库、Chroma、上传目录 | [import_bundle](../backend/scripts/import_knowledge_bundle.py#L124) |
| 给同学的操作说明 | [data/README.md](../data/README.md) |
| 已生成传输包 | [data/transfer/](../data/transfer/) |

不要只复制 MySQL volume 或 `data/chroma`。接收方的 embedding
provider/model/dimensions 也应保持一致。

## 6. 配置与部署

| 配置 / 服务 | 位置 | 说明 |
| --- | --- | --- |
| 环境变量 | [.env.example](../.env.example) | MySQL、DeepSeek、embedding、路径、API |
| 配置读取 | [config.py](../backend/app/core/config.py#L1) | 根目录和 backend `.env` |
| MySQL | [compose](../deploy/docker-compose.yml#L4) | 业务元数据 |
| Backend | [compose](../deploy/docker-compose.yml#L19) | 启动时 Alembic |
| Renderer | [compose](../deploy/docker-compose.yml#L47) | 仅供 backend |
| Frontend | [compose](../deploy/docker-compose.yml#L60) | API 地址是构建时变量 |
| SQLAlchemy | [database.py](../backend/app/core/database.py#L1) | 生产 MySQL，测试 SQLite |
| 数据迁移 | [migrations/versions/](../backend/migrations/versions/) | ORM 修改需新增迁移 |

健康检查：

- 后端：[health](../backend/app/main.py#L125)
- 数据库：[health_db](../backend/app/main.py#L131)
- DeepSeek：[health_ai](../backend/app/main.py#L146)
- Chroma：[health_chroma](../backend/app/main.py#L159)
- Renderer 请求分发：[server.mjs](../renderer/server.mjs#L456)

## 7. API 契约与错误

| 内容 | 代码 |
| --- | --- |
| 后端 Pydantic 契约 | [schemas/api.py](../backend/app/schemas/api.py#L1) |
| 前端 TypeScript 类型 | [types.ts](../frontend/src/types.ts#L1) |
| HTTP 异常信封 | [http_error](../backend/app/main.py#L72) |
| 参数错误 | [validation_error](../backend/app/main.py#L93) |
| 前端响应结构检查 | [api/http.ts](../frontend/src/api/http.ts#L1) |
| 错误码文案 | [utils/workbench.ts](../frontend/src/utils/workbench.ts#L20) |
| trace_id | [trace_middleware](../backend/app/main.py#L62) |

“接口响应格式异常，请检查 VITE_API_BASE_URL 配置”通常表示请求返回了前端
HTML 而非后端 JSON。先检查 [api/http.ts](../frontend/src/api/http.ts#L1) 和
[frontend/Dockerfile](../frontend/Dockerfile#L1) 的构建参数。

## 8. 测试位置

| 范围 | 测试 |
| --- | --- |
| 后端 API 与完整业务 | [test_backend_api.py](../backend/tests/test_backend_api.py) |
| ReAct Agent | [test_editor_agent.py](../backend/tests/ai/test_editor_agent.py) |
| 入库与检索 | [test_ingestion_retrieval.py](../backend/tests/ai/test_ingestion_retrieval.py) |
| LangGraph/质量 | [test_graph_evaluation.py](../backend/tests/ai/test_graph_evaluation.py) |
| DeepSeek 客户端 | [test_llm_client.py](../backend/tests/ai/test_llm_client.py) |
| 知识库 bundle | [test_knowledge_bundle.py](../backend/tests/test_knowledge_bundle.py) |
| 前端 store | [app.test.ts](../frontend/src/stores/app.test.ts) |
| 工作台纯函数 | [workbench.test.ts](../frontend/src/utils/workbench.test.ts) |
| 文件校验 | [files.test.ts](../frontend/src/utils/files.test.ts) |
| 跨语言契约 | [test_contracts.py](../tests/contract/test_contracts.py) |
| 端到端 | [tests/e2e/](../tests/e2e/) |

## 9. 修改功能时的同步检查

- 改 API 字段：同步 [Pydantic schema](../backend/app/schemas/api.py#L1)、
  [TypeScript type](../frontend/src/types.ts#L1) 和契约测试。
- 改 embedding：必须重建 Chroma，不能混用不同模型或维度。
- 改主题目录：同步 [allowedThemes](../renderer/server.mjs#L24)、
  [theme_catalog.json](../backend/app/theme_catalog.json) 和预览图。
- 改课件结构：同步生成、内容校验、预览、导出和前端类型。
- 新增 Agent mutation：同步工具白名单、service、版本保存、前端 artifact
  更新与 Agent 单测。
- 改长任务状态：同步 AITask、GraphRun、GenerationPage 和错误文案。
- 改持久化表：新增 Alembic 迁移，不要只改 ORM。
