# Member 4 AI 模块

本目录负责 DeepSeek、可追溯 RAG、五类教学 Skills、统一教学蓝图、四类产物和 LangGraph 质量流程。

## 稳定入口

- `ProjectVectorStore.add_documents/similarity_search/delete_by_source`：成员 3 的资料服务调用。
- `run_skill(skill_id, SkillRequest(...))`：独立调用五类 Skill。
- `generate_lesson_bundle(LessonContext(...), trace_id=...)`：生成教案、课件、逐页讲稿和分层练习。
- `revise_block(...)`：只修改指定页面、讲稿或练习。
- `build_langgraph()`、`review_artifacts(...)`：七节点条件返修和确定性质量检查。
- `app.services.graph_service`：生产执行器；将每个节点的开始/完成事件、完整状态和
  返修次数写入 `GraphRun`，在 `human_confirm` 暂停，并从数据库 checkpoint
  执行接受、取消或定向返修。

未配置 `DEEPSEEK_API_KEY` 时会返回带明确 warning 的规则草案，不会冒充真实模型成功。引用只来自 Chroma 检索结果。
普通自动测试默认禁用真实模型；只有显式给测试进程提供密钥时才运行 DeepSeek 集成测试。

在仓库的 `backend` 目录运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```
