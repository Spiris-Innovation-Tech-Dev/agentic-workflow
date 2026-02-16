"""
Tests for resources.py — URI-based resource resolution and data accessors.

Run with: pytest tests/test_resources.py -v
"""

import json
import shutil
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentic_workflow_server.resources import (
    get_tasks_list,
    get_task_state,
    get_active_task_state,
    get_effective_config,
    resolve_resource,
    RESOURCE_DESCRIPTIONS,
    RESOURCE_TEMPLATES,
)
from agentic_workflow_server.state_tools import (
    workflow_initialize,
    workflow_transition,
    workflow_complete_phase,
    workflow_get_state,
    get_tasks_dir,
    PHASE_ORDER,
)


@pytest.fixture
def clean_tasks_dir():
    """Clean up .tasks directory before and after tests."""
    tasks_dir = get_tasks_dir()

    for d in tasks_dir.glob("TASK_RES_*"):
        if d.is_dir():
            shutil.rmtree(d)

    yield tasks_dir

    for d in tasks_dir.glob("TASK_RES_*"):
        if d.is_dir():
            shutil.rmtree(d)


# ============================================================================
# get_tasks_list
# ============================================================================

class TestGetTasksList:
    def test_empty_tasks_dir(self, clean_tasks_dir):
        """When no TASK_RES_ tasks exist, list may be empty or contain others."""
        result = get_tasks_list()
        assert "tasks" in result
        assert "count" in result
        assert isinstance(result["tasks"], list)
        assert result["count"] == len(result["tasks"])

    def test_multiple_tasks_with_mixed_states(self, clean_tasks_dir):
        # Create incomplete task
        workflow_initialize(task_id="TASK_RES_001")

        # Create complete task
        workflow_initialize(task_id="TASK_RES_002")
        for phase in PHASE_ORDER:
            workflow_transition(phase, task_id="TASK_RES_002")
            workflow_complete_phase(task_id="TASK_RES_002")

        result = get_tasks_list()
        res_tasks = [t for t in result["tasks"] if t["task_id"].startswith("TASK_RES_")]

        assert len(res_tasks) == 2
        incomplete = next(t for t in res_tasks if t["task_id"] == "TASK_RES_001")
        complete = next(t for t in res_tasks if t["task_id"] == "TASK_RES_002")
        assert incomplete["is_complete"] is False
        assert complete["is_complete"] is True

    def test_counts_correct(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_RES_003")
        workflow_initialize(task_id="TASK_RES_004")
        for phase in PHASE_ORDER:
            workflow_transition(phase, task_id="TASK_RES_004")
            workflow_complete_phase(task_id="TASK_RES_004")

        result = get_tasks_list()
        # At least our 2 tasks
        assert result["active_count"] >= 1
        assert result["completed_count"] >= 1
        assert result["count"] >= 2


# ============================================================================
# get_task_state
# ============================================================================

class TestGetTaskState:
    def test_existing_task_returns_state(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_RES_010")
        result = get_task_state("TASK_RES_010")
        assert result["task_id"] == "TASK_RES_010"
        assert result["phase"] == "architect"

    def test_nonexistent_task_returns_error(self, clean_tasks_dir):
        result = get_task_state("TASK_NONEXISTENT_RES")
        assert "error" in result


# ============================================================================
# get_active_task_state
# ============================================================================

class TestGetActiveTaskState:
    def test_with_active_task(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_RES_020")
        result = get_active_task_state()
        # There should be at least one active task
        # Due to other tasks in .tasks/, we just check structure
        if result.get("has_active"):
            assert "task_id" in result
            assert "phase" in result
        else:
            # If no active task found (e.g., all complete), that's valid too
            assert result["has_active"] is False

    def test_no_active_task(self, clean_tasks_dir):
        """When all tasks are complete, returns has_active=false."""
        # Complete the only task we create
        workflow_initialize(task_id="TASK_RES_021")
        for phase in PHASE_ORDER:
            workflow_transition(phase, task_id="TASK_RES_021")
            workflow_complete_phase(task_id="TASK_RES_021")

        # There might still be other active tasks from other test suites,
        # so we just verify the function doesn't crash
        result = get_active_task_state()
        assert "has_active" in result


# ============================================================================
# get_effective_config
# ============================================================================

class TestGetEffectiveConfig:
    def test_returns_config_dict(self, clean_tasks_dir):
        result = get_effective_config()
        assert "config" in result
        assert "sources" in result
        assert "checkpoints" in result["config"]


# ============================================================================
# resolve_resource
# ============================================================================

class TestResolveResource:
    def test_workflow_tasks_uri(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_RES_030")
        result_str = resolve_resource("workflow://tasks")
        result = json.loads(result_str)
        assert "tasks" in result
        assert "count" in result

    def test_workflow_active_uri(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_RES_031")
        result_str = resolve_resource("workflow://active")
        result = json.loads(result_str)
        assert "has_active" in result

    def test_config_effective_uri(self, clean_tasks_dir):
        result_str = resolve_resource("config://effective")
        result = json.loads(result_str)
        assert "config" in result

    def test_task_state_uri(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_RES_032")
        result_str = resolve_resource("workflow://tasks/TASK_RES_032/state")
        result = json.loads(result_str)
        assert result["task_id"] == "TASK_RES_032"

    def test_unknown_uri_returns_error(self, clean_tasks_dir):
        result_str = resolve_resource("unknown://something")
        result = json.loads(result_str)
        assert "error" in result
        assert "Unknown resource URI" in result["error"]


# ============================================================================
# Constants
# ============================================================================

class TestResourceConstants:
    def test_resource_descriptions_has_all_uris(self):
        expected_uris = {"workflow://tasks", "workflow://active", "config://effective"}
        assert expected_uris == set(RESOURCE_DESCRIPTIONS.keys())

    def test_resource_descriptions_have_required_fields(self):
        for uri, desc in RESOURCE_DESCRIPTIONS.items():
            assert "name" in desc, f"Missing 'name' in {uri}"
            assert "description" in desc, f"Missing 'description' in {uri}"
            assert "mimeType" in desc, f"Missing 'mimeType' in {uri}"

    def test_resource_templates_has_task_state(self):
        assert "workflow://tasks/{task_id}/state" in RESOURCE_TEMPLATES

    def test_resource_templates_have_required_fields(self):
        for uri, tmpl in RESOURCE_TEMPLATES.items():
            assert "name" in tmpl, f"Missing 'name' in {uri}"
            assert "description" in tmpl, f"Missing 'description' in {uri}"
            assert "mimeType" in tmpl, f"Missing 'mimeType' in {uri}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
