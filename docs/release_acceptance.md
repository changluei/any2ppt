# LessonDeck 发布验收清单

更新日期：2026-07-23

## 1. 冻结范围

- 单课时小学备课；四类产物固定为 `lesson_plan`、`slide_deck`、`speaker_notes`、`exercise_set`。
- 五个 Skill 可独立运行；完整生成任务串联四类产物并实际进入 LangGraph。
- AI 参数以环境变量锁定，默认温度 `0.2`、结构修复 1 次、业务返修最多 2 轮。
- 资料支持 PDF、DOCX、TXT、Markdown；引用必须包含来源、分块、文件、位置与原文摘录。
- 教师确认前禁止导出；学生包不得包含讲稿、答案或解析。

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

每组完整执行“建项目 → 上传 → 检索 → 五 Skill 任一独立运行 → 完整生成 → 质量确认 → 教师/学生包导出”：

1. 科学三年级《水的三态变化》，资料使用 `samples/公开课例资料.md`。
2. 语文四年级阅读课，使用自编 TXT，重点检查引用定位和逐页讲稿。
3. 数学五年级应用题，使用自编 DOCX，重点检查三级练习、答案隔离和局部难度调整。

通过标准：

- 课件 12—18 页，页 ID 唯一，每页有讲稿。
- 单课时 35—50 分钟，核心目标均有活动与评价/练习。
- 基础、巩固、提高均存在；原创题标记“需教师确认”。
- 局部修改只改变目标块；409 返回当前版本；回滚创建新版本。
- GraphRun 可见节点、轮次、问题与人工确认状态；服务重启后没有永久 `running`。
- ZIP 含版本清单和 Slidev 兼容 `slides.md`；学生包隐私断言通过。

## 4. 人工与视觉验收

分别在 1366×768 和 1920×1080 检查项目页、知识库、工作台、质量页、导出页：

- 无横向遮挡，主要按钮无需滚动即可到达。
- 课件缩略页、预览、讲稿同步；Markdown 源码可切换。
- 错误、空状态、加载态、降级提示和 trace_id 可见。
- 质量问题点击后定位到对应页、讲稿、练习或教学设计。
- 版本选择、历史查看、回滚、导出版本选择清晰。

P0/P1 缺陷必须为 0；P2 需记录负责人和规避方式。

## 5. 干净环境与交付证据

在临时目录复制仓库（不复制 `.env`、数据目录、`node_modules`），从 `.env.example` 新建配置，执行 Docker 一键启动。确认 Alembic 从空 MySQL 升级到 `0002_task_result_snapshot`，三个服务均健康。

交付证据包括：

- `git rev-parse HEAD` 与 `git status --short`
- Docker `ps`、健康检查、测试汇总
- 三组固定课例的项目 ID、任务 trace_id、GraphRun 状态
- 教师/学生 ZIP 文件清单与隐私检查
- 两种分辨率截图
- 两次经授权真实模型调用记录，或明确写明“未授权费用，未执行”
