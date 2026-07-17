# 公共契约

所有模块统一使用 `project_id`、`source_id`、`chunk_id`、`task_id`、`artifact_id`、`version_id`、`slide_id`、`trace_id`。任务状态仅允许 `pending`、`running`、`succeeded`、`failed`、`cancelled`。

资料状态为 `uploaded → parsing → indexing → ready`，失败为 `failed`。引用必须指向真实检索分块；没有证据时返回 warning，禁止构造来源。

机器可读契约见 [schemas.json](./schemas.json)。

