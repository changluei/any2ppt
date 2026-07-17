from pathlib import Path
from app.ai.ingestion import parse_document, split_blocks
from app.ai.graph import review_artifacts
from app.ai.skills import route_intent, registry
from app.ai.vector_store import ProjectVectorStore
from app.ai.ingestion import Chunk


def test_parse_and_stable_chunks(tmp_path: Path):
    file = tmp_path / "sample.md"
    file.write_text("# 标题\n\n水受热会蒸发。\n\n水蒸气遇冷会凝结。", "utf-8")
    chunks = split_blocks(parse_document(file), "source-1", 20, 3)
    again = split_blocks(parse_document(file), "source-1", 20, 3)
    assert chunks and [c.chunk_id for c in chunks] == [c.chunk_id for c in again]
    assert all(c.location for c in chunks)


def test_skill_registry_and_router():
    assert len(registry()) == 5
    assert route_intent("请设计课堂活动") == "teaching_activities"
    assert route_intent("帮我看看") is None


def test_quality_review_targets_missing_note():
    artifacts = {
        "lesson_plan": {"objectives": [{"id": "O1"}], "stages": [{"time_minutes": 40}]},
        "slide_deck": {"slides": [{"slide_id": "S1", "markdown": "短内容"}]},
        "speaker_notes": {"notes": []},
        "exercise_set": {"exercises": [{"objective_ids": ["O1"]}]},
    }
    issues = review_artifacts(artifacts)
    assert any(issue["target_id"] == "S1" for issue in issues)


def test_vector_store_isolates_projects(tmp_path: Path):
    store = ProjectVectorStore()
    store.root = tmp_path
    store.add_documents("project-a", "source-a", "a.md", [Chunk("ca", "水受热会蒸发", "段落 1")])
    store.add_documents("project-b", "source-b", "b.md", [Chunk("cb", "植物需要阳光", "段落 1")])
    result = store.similarity_search("project-a", "水受热", 3)
    assert result and result[0]["source_id"] == "source-a"
    assert all(row["project_id"] == "project-a" for row in result)
