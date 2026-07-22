# Member 4 AI 模块

本目录负责 DeepSeek、可追溯 RAG、五类教学 Skills、统一教学蓝图、四类产物和 LangGraph 质量流程。

## 稳定入口

- `ProjectVectorStore.add_documents/similarity_search/delete_by_source`：成员 3 的资料服务调用。
- `run_skill(skill_id, SkillRequest(...))`：独立调用五类 Skill。
- `generate_lesson_bundle(LessonContext(...), trace_id=...)`：生成教案、课件、逐页讲稿和分层练习。
- `revise_block(...)`：只修改指定页面、讲稿或练习。
- `build_langgraph()`、`review_artifacts(...)`：条件返修和确定性质量检查。

未配置 `DEEPSEEK_API_KEY` 时会返回带明确 warning 的规则草案，不会冒充真实模型成功。引用只来自 Chroma 检索结果。

在仓库的 `backend` 目录运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```
