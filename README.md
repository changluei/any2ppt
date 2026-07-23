# 面向智慧教育的 AI 备课辅助系统（LessonDeck）

面向小学教师的单课时备课工作台：上传教材/课标后建立可追溯知识库，由五类教学 Skills 和可见质量流程生成教学设计、12—18 页课件、逐页讲稿、分层练习，并支持局部修改、版本回滚、教师/学生双包导出。

## 目录

- `frontend/`：Vue 3、TypeScript、Vite、Pinia、Element Plus；五个主页面与三栏工作台。
- `backend/app/`：FastAPI、SQLAlchemy/MySQL、上传、任务、产物版本、图状态、导出。
- `backend/app/ai/`：DeepSeek 适配、可追溯检索、五类 Skills、完整生成、质量规则。
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

没有模型密钥时，系统会生成基于用户输入的“规则降级草案”，界面有醒目标识，绝不会冒充 DeepSeek 成功。上传 `samples/公开课例资料.md` 后可查看真实来源位置。需要在已配置密钥的环境中做无费用验收时，设置 `AI_FORCE_FALLBACK=true`。

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

首版聚焦小学单课时，不提供复杂权限、在线协作、拖拽式 PPT 编辑或扫描 PDF OCR。课件采用 Slidev 兼容 Markdown、安全 iframe 预览和离线 HTML 导出；PDF 可由导出的 HTML 通过浏览器打印生成。
