import pytest

from app.core.migrations import BASELINE_TABLES, legacy_revision_to_stamp


def test_complete_unversioned_legacy_schema_is_stamped():
    assert legacy_revision_to_stamp(BASELINE_TABLES, None) == "0001_initial"


def test_empty_or_versioned_schema_is_not_stamped():
    assert legacy_revision_to_stamp(set(), None) is None
    assert legacy_revision_to_stamp(BASELINE_TABLES | {"alembic_version"}, "0002_task_result_snapshot") is None


def test_partial_legacy_schema_is_rejected():
    with pytest.raises(RuntimeError, match="缺少表"):
        legacy_revision_to_stamp({"projects", "ai_tasks"}, None)
