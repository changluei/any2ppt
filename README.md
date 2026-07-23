# 面向智慧教育的 AI 备课辅助系统

面向小学教师的单课时备课工作台：创建项目时先预览并选择 Slidev 模板，上传教材或课标建立可追溯知识库，系统自动完成教学设计、课堂活动、逐页讲解提示、分层练习和质量检查，最终统一生成并导出一份可直接使用的 PPT。

## 目录

- `frontend/`：Vue 3、TypeScript、Vite、Pinia、Element Plus；仅保留“备课项目”和“知识库”两级主导航，项目工作台从具体项目进入。
- `backend/app/`：FastAPI、SQLAlchemy/MySQL、上传、任务、产物版本、图状态、导出。
- `backend/app/ai/`：DeepSeek 适配、可追溯检索、内部生成能力与自动质量规则。
- `backend/app/theme_catalog.json`：只保存经过兼容验证的主题描述、固定版本、预览地址、适用场景和实际版式清单，不保存主题源码。
- `renderer/`：用户确认创建项目后才从 NPM 下载所选主题并按项目缓存；生成时 AI 遵循该主题的实际版式清单，导出时由 Slidev 渲染 PPTX。
- `contracts/`：跨模块 JSON Schema 与固定字段。
- `deploy/`：MySQL 8、后端、前端一键编排。
- `samples/`：无版权风险的自编演示资料；不包含预生成 AI 答案。
- `tests/`：契约与端到端 smoke。

## 一键启动

1. 将 `.env.example` 复制为 `.env`，至少修改 MySQL 密码；要使用真实模型时填写 `DEEPSEEK_API_KEY`。
2. 执行：

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up --build
```

3. 打开前端 <http://localhost:5173>，Swagger 为 <http://localhost:8000/docs>，API/数据库诊断为 `/health` 和 `/health/db`。

没有模型密钥时，系统会生成基于用户输入的规则降级草案，绝不会冒充 DeepSeek 成功。上传 `samples/公开课例资料.md` 后即可测试完整流程。需要在已配置密钥的环境中做无费用验收时，设置 `AI_FORCE_FALLBACK=true`。

停止服务（保留 MySQL 与 Chroma 数据）：

```bash
docker compose --env-file .env -f deploy/docker-compose.yml down
```

## 本地开发

后端：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements/base.txt -r requirements/ai.txt -r requirements/dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

前端：

```bash
cd frontend
cp .env.example .env
pnpm install
pnpm dev
```

Windows PowerShell 将复制命令改为 `Copy-Item .env.example .env`。演示课题按钮只填课程输入，不包含任何预生成的 AI 结果。

验证：`pnpm lint && pnpm typecheck && pnpm test && pnpm build`、`pytest backend/tests tests/contract`、`python tests/e2e/smoke.py`。发布前按 [发布验收清单](docs/release_acceptance.md) 执行。

## Windows PowerShell

首次创建后端虚拟环境并安装依赖：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements/base.txt -r requirements/ai.txt -r requirements/dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q
cd ..
```

如果系统没有全局 `python` 命令，可使用已安装 Python 的完整路径执行 `-m venv backend\.venv`。后续所有后端命令均使用 `backend\.venv\Scripts\python.exe`，避免污染系统环境。

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f deploy/docker-compose.yml config
docker compose --env-file .env -f deploy/docker-compose.yml up --build
docker compose --env-file .env -f deploy/docker-compose.yml ps
docker compose --env-file .env -f deploy/docker-compose.yml logs --tail 100 backend
docker compose --env-file .env -f deploy/docker-compose.yml restart backend
docker compose --env-file .env -f deploy/docker-compose.yml down
```

不使用 `down -v`，因此停止服务不会删除数据库卷。密钥、上传文件、导出包、MySQL 和检索持久化目录均已从 Git 排除。

## 当前边界

首版聚焦小学单课时，不提供复杂权限、在线协作或扫描 PDF OCR。工作台支持逐页预览、Markdown 源码直接编辑、实时编译预览和定向调整；保存源码会创建新的课件版本。教师可上传 PNG/JPG/WEBP 图片，并按左侧、右侧、居中、宽图或背景位置放入指定页面。所有教学内容统一汇入 `.pptx` 文件，不再向教师提供独立教案、讲稿、练习包或其他导出产物。
