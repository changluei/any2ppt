"""HTTP API 的请求与响应契约。

ORM 实体不会直接暴露给前端：本模块用 Pydantic 限制字段长度、枚举值和
跨字段条件，同时把数据库对象转换为稳定的 JSON。修改这里的字段时应同步
检查 ``frontend/src/types.ts`` 与 ``contracts/schemas.json``。
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ORMModel(BaseModel):
    """允许响应模型直接读取 SQLAlchemy 对象属性。"""
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    """创建/更新项目时由前端提交的完整表单。"""
    name: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=1, max_length=40)
    grade: str = Field(min_length=1, max_length=40)
    textbook_version: str = Field(default="", max_length=80)
    lesson_topic: str = Field(min_length=1, max_length=160)
    lesson_count: int = Field(default=1, ge=1, le=8)
    student_profile: str = Field(default="", max_length=2000)
    teacher_requirements: str = Field(default="", max_length=3000)
    theme_id: str = Field(default="default", min_length=1, max_length=64)
    knowledge_base_ids: list[str] = Field(default_factory=list, max_length=4)


class ProjectOut(ProjectCreate, ORMModel):
    """项目详情响应，附加后端维护的标识、状态与时间。"""
    id: str
    status: str
    theme_status: str
    created_at: datetime
    updated_at: datetime


class ThemeRecommendationRequest(BaseModel):
    """主题推荐所需的轻量课程上下文。"""
    subject: str = Field(default="", max_length=40)
    grade: str = Field(default="", max_length=40)
    lesson_topic: str = Field(default="", max_length=160)
    student_profile: str = Field(default="", max_length=2000)
    teacher_requirements: str = Field(default="", max_length=3000)


class SourceOut(ORMModel):
    """资料文件元数据；不返回服务端真实 storage_path。"""
    id: str
    project_id: Optional[str]
    knowledge_base_id: str
    original_name: str
    media_type: str
    size: int
    status: str
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


class ProjectImageOut(ORMModel):
    """可在工作台使用的图片元数据与受控内容 URL。"""
    id: str
    project_id: str
    original_name: str
    media_type: str
    size: int
    width: int
    height: int
    content_url: str
    created_at: datetime


class SearchRequest(BaseModel):
    """跨资料/知识库检索参数；top_k 设上限以控制延迟和上下文长度。"""
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    source_ids: Optional[list[str]] = None
    knowledge_base_ids: list[str] = Field(default_factory=list, max_length=4)


class SearchResult(BaseModel):
    """一个可追溯文本片段，location 用于回到原资料位置。"""
    content: str
    source_id: str
    chunk_id: str
    filename: str
    location: str
    score: float
    knowledge_base_id: Optional[str] = None


class KnowledgeBaseOut(ORMModel):
    """知识库目录统计，不包含具体 chunk 与向量。"""
    id: str
    name: str
    kind: Literal["official", "personal"]
    subject: str
    description: str
    status: str
    read_only: bool
    document_count: int
    chunk_count: int
    size_bytes: int
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    """启动生成任务时冻结的输入选择与幂等键。"""
    type: str = Field(min_length=1, max_length=64)
    selected_source_ids: list[str] = Field(default_factory=list)
    selected_knowledge_base_ids: list[str] = Field(default_factory=list, max_length=4)
    teacher_requirements: str = Field(default="", max_length=3000)
    idempotency_key: str = Field(min_length=3, max_length=100)


class TaskOut(ORMModel):
    """供生成锁定页轮询的任务进度和最终结果摘要。"""
    id: str
    project_id: str
    type: str
    status: Literal["pending", "running", "succeeded", "failed", "cancelled"]
    stage: str
    progress: int
    trace_id: str
    result_snapshot: Optional[dict[str, Any]]
    result_artifact_id: Optional[str]
    error_code: Optional[str]
    error_message: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ArtifactOut(BaseModel):
    """一个确定版本的制品及其引用、告警和差异信息。"""
    artifact_id: str
    version_id: str
    project_id: str
    type: str
    version_no: int
    parent_version_id: Optional[str]
    change_type: str
    changed_ids: list[str]
    unchanged_hashes: list[dict[str, str]]
    content: dict[str, Any]
    citations: list[dict[str, Any]]
    warnings: list[str]
    created_at: datetime


class RevisionRequest(BaseModel):
    """传统局部修订接口；base_version_no 用于乐观并发控制。"""
    base_version_no: int = Field(ge=1)
    target_type: str
    target_id: str
    instruction: str = Field(min_length=2, max_length=1000)
    sync_related: bool = False


class SlideMarkdownUpdate(BaseModel):
    """Markdown 编辑器自动保存一页幻灯片的请求。"""
    base_version_no: int = Field(ge=1)
    slide_id: str = Field(min_length=1, max_length=100)
    markdown: str = Field(min_length=1, max_length=20000)


class SlideImagePlacementCreate(BaseModel):
    """把已上传图片绑定到指定幻灯片和预设位置。"""
    base_version_no: int = Field(ge=1)
    slide_id: str = Field(min_length=1, max_length=100)
    image_id: str = Field(min_length=1, max_length=36)
    position: Literal["left", "right", "center", "wide", "background"] = "right"
    caption: str = Field(default="", max_length=300)


class EditorAgentChatRequest(BaseModel):
    """ReAct 编辑请求；允许纯文本、纯图片或文本与图片组合。"""
    message: str = Field(default="", max_length=1200)
    current_slide_id: str = Field(min_length=1, max_length=100)
    base_version_no: int = Field(ge=1)
    image_id: Optional[str] = Field(default=None, max_length=36)

    @model_validator(mode="after")
    def require_content(self):
        """拒绝没有任何可执行意图的空消息。"""
        if not self.message.strip() and not self.image_id:
            raise ValueError("消息和图片不能同时为空")
        return self


class EditorAgentMessageOut(ORMModel):
    """持久化对话消息的安全输出视图。"""
    id: str
    project_id: str
    role: Literal["user", "assistant"]
    content: str
    image_id: Optional[str]
    image_name: Optional[str]
    artifact_version_no: Optional[int]
    created_at: datetime


class EditorAgentChatOut(BaseModel):
    """Agent 回复、可选新制品版本、动作摘要与降级状态。"""
    message: EditorAgentMessageOut
    artifact: Optional[ArtifactOut]
    actions: list[str]
    trace_id: str
    degraded: bool = False


class HumanDecision(BaseModel):
    """生成图暂停后由用户给出的接受、返工或取消决定。"""
    decision: Literal["accept", "revise", "cancel"]


class ExportCreate(BaseModel):
    """导出类型和可选的显式版本集合。"""
    package_type: Literal["teacher", "student", "pptx"]
    artifact_version_ids: list[str] = Field(default_factory=list, max_length=20)


class GraphStartRequest(BaseModel):
    """启动或从检查点恢复生成图的参数。"""
    task_id: Optional[str] = None
    thread_id: Optional[str] = None
    checkpoint_ref: Optional[str] = None


class GraphRunOut(ORMModel):
    """生成图的可观测状态，用于前端进度页和故障诊断。"""
    id: str
    project_id: str
    task_id: str
    thread_id: str
    checkpoint_ref: Optional[str]
    attempt: int
    status: str
    current_node: str
    nodes: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    state_snapshot: dict[str, Any]
    human_decision: Optional[str]
    created_at: datetime
    updated_at: datetime
