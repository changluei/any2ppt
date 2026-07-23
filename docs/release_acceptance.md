# AI 备课辅助系统发布验收清单

更新日期：2026-07-23

## 1. 冻结范围

- 单课时小学备课；教学设计、讲解提示和分层练习均自动汇入最终 PPT。
- 生成能力与质量流程由后台自动串联，不在前端暴露 Skill、图节点或质量检查页面。
- AI 参数以环境变量锁定，默认温度 `0.2`、结构修复 1 次、业务返修最多 2 轮。
- 资料支持 PDF、DOCX、TXT、Markdown；引用必须包含来源、分块、文件、位置与原文摘录。
- 导出结果固定为 `.pptx`，不提供教案、讲稿、习题或 ZIP 等独立产物。
- 本地只保存经过兼容验证的主题描述和预览图；创建项目前只预览，确认后下载所选固定版本并按项目缓存，删除项目时同步清理。
- 项目图片支持 PNG/JPG/WEBP，图片放置与删除均创建新的课件版本。

## 2. 自动验收

在项目根目录执行：

```bash
AI_FORCE_FALLBACK=true docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
docker compose --env-file .env -f deploy/docker-compose.yml ps
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/health/db
curl -fsS http://localhost:8000/health/chroma

cd frontend
pnpm lint
pnpm typecheck
pnpm test
pnpm build
cd ..

pytest backend/tests tests/contract -q
python tests/e2e/smoke.py
```

无密钥或不希望产生模型费用时必须启用 `AI_FORCE_FALLBACK=true`。真实模型验收仅在负责人明确允许费用后执行：

```bash
RUN_REAL_AI_TESTS=1 pytest backend/tests/ai/test_deepseek_integration.py -q
```

连续运行两次并保存 trace_id、模型名、耗时和用量。不得把密钥或完整提示词写入验收记录。

## 3. 三组固定课例

每组完整执行“建项目 → 上传 → 生成 PPT → 自动质量检查 → 工作台预览 → 导出 PPT”：

1. 科学三年级《水的三态变化》，资料使用 `samples/公开课例资料.md`。
2. 语文四年级阅读课，使用自编 TXT，重点检查逐页讲解提示是否随 PPT 保存。
3. 数学五年级应用题，使用自编 DOCX，重点检查三级练习、答案解析和局部难度调整是否进入 PPT。

通过标准：

- 课件 12—18 页，页 ID 唯一，每页有讲稿。
- 单课时 35—50 分钟，核心目标均有活动与评价/练习。
- 基础、巩固、提高均存在；原创题标记“需教师确认”。
- 局部修改只改变目标块；409 返回当前版本；回滚创建新版本。
- GraphRun 在后台完成自动检查；服务重启后没有永久 `running`。
- 下载文件扩展名为 `.pptx`，可由 PowerPoint/WPS 正常打开，练习、答案、解析和讲解提示均在文件中。

## 4. 人工与视觉验收

分别在 1366×768 和 1920×1080 检查项目页、知识库和项目工作台：

- 无横向遮挡，主要按钮无需滚动即可到达。
- 左侧浅色导航可以随时展开和收起，只出现“备课项目”和“知识库”。
- 工作台只能从具体项目进入，不出现在全局导航。
- 课件缩略页与预览同步；Markdown 源码可以直接编辑并实时编译，保存后创建新版本并可以导出当前 PPT。
- 创建项目必须先经过模板预览与确认；确认前没有主题源码下载，确认后项目记录所选主题和下载状态。
- 生成设置展示项目模板；生成后的页面 layout 必须属于该模板登记的实际版式清单。
- 上传本地图片后，可将图片放在指定页的左侧、右侧、中央、下方宽图或背景位置；预览与导出一致。
- 前端不出现连接状态、Skill 卡片、质量检查栏目或单独导出中心。
- 错误、空状态和加载状态清晰，不暴露内部技术流程。

P0/P1 缺陷必须为 0；P2 需记录负责人和规避方式。

## 5. 干净环境与交付证据

在临时目录复制仓库（不复制 `.env`、数据目录、`node_modules`），从 `.env.example` 新建配置，执行 Docker 一键启动。确认 Alembic 从空 MySQL 升级到 `0004_project_theme`，MySQL、后端、前端和渲染器均健康。

交付证据包括：

- `git rev-parse HEAD` 与 `git status --short`
- Docker `ps`、健康检查、测试汇总
- 三组固定课例的项目 ID、任务 trace_id、GraphRun 状态
- PPTX 文件结构检查与 PowerPoint/WPS 打开验证
- 两种分辨率截图
- 两次经授权真实模型调用记录，或明确写明“未授权费用，未执行”
