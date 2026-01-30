"""
Tests for Agentic Workflow MCP Server State Tools

Run with: pytest tests/test_state_tools.py -v
"""

import json
import shutil
import pytest
from pathlib import Path
from datetime import datetime, timedelta

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentic_workflow_server.state_tools import (
    # Core workflow
    workflow_initialize,
    workflow_transition,
    workflow_get_state,
    workflow_complete_phase,
    workflow_is_complete,
    workflow_can_transition,
    workflow_can_stop,
    # Review
    workflow_add_review_issue,
    workflow_mark_docs_needed,
    # Implementation progress
    workflow_set_implementation_progress,
    workflow_complete_step,
    # Human decisions
    workflow_add_human_decision,
    # Knowledge base
    workflow_set_kb_inventory,
    # Concerns
    workflow_add_concern,
    workflow_address_concern,
    workflow_get_concerns,
    # Memory preservation
    workflow_save_discovery,
    workflow_get_discoveries,
    workflow_flush_context,
    # Context management
    workflow_get_context_usage,
    workflow_prune_old_outputs,
    # Cross-task memory
    workflow_search_memories,
    workflow_link_tasks,
    workflow_get_linked_tasks,
    # Resilience
    workflow_record_model_error,
    workflow_record_model_success,
    workflow_get_available_model,
    workflow_get_resilience_status,
    workflow_clear_model_cooldown,
    # Helpers
    get_tasks_dir,
    DISCOVERY_CATEGORIES,
    PHASE_ORDER,
)


@pytest.fixture
def clean_tasks_dir():
    """Clean up .tasks directory before and after tests."""
    tasks_dir = get_tasks_dir()

    # Clean up any test tasks before
    for pattern in ["TASK_TEST_*", "TASK_CROSS_*"]:
        for d in tasks_dir.glob(pattern):
            if d.is_dir():
                shutil.rmtree(d)

    # Clean resilience state
    resilience_file = tasks_dir / ".resilience_state.json"
    if resilience_file.exists():
        resilience_file.unlink()

    yield tasks_dir

    # Clean up after
    for pattern in ["TASK_TEST_*", "TASK_CROSS_*"]:
        for d in tasks_dir.glob(pattern):
            if d.is_dir():
                shutil.rmtree(d)

    if resilience_file.exists():
        resilience_file.unlink()


class TestWorkflowInitialization:
    """Test workflow initialization and basic state management."""

    def test_initialize_creates_task(self, clean_tasks_dir):
        result = workflow_initialize(task_id="TASK_TEST_001")

        assert result["success"] is True
        assert result["task_id"] == "TASK_TEST_001"
        assert result["phase"] == "architect"
        assert (clean_tasks_dir / "TASK_TEST_001" / "state.json").exists()

    def test_initialize_with_description(self, clean_tasks_dir):
        result = workflow_initialize(
            task_id="TASK_TEST_002",
            description="Add user authentication"
        )

        assert result["success"] is True
        state = workflow_get_state(task_id="TASK_TEST_002")
        assert state["description"] == "Add user authentication"

    def test_initialize_fails_if_exists(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_003")
        result = workflow_initialize(task_id="TASK_TEST_003")

        assert result["success"] is False
        assert "already exists" in result["error"]


class TestWorkflowTransitions:
    """Test phase transitions and workflow progression."""

    def test_valid_forward_transition(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_010")

        result = workflow_transition("developer", task_id="TASK_TEST_010")

        assert result["success"] is True
        assert result["from_phase"] == "architect"
        assert result["to_phase"] == "developer"

    def test_invalid_skip_transition(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_011")

        # Try to skip from architect to implementer
        result = workflow_transition("implementer", task_id="TASK_TEST_011")

        assert result["success"] is False
        assert "Cannot skip" in result["error"]

    def test_loopback_to_developer(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_012")
        workflow_transition("developer", task_id="TASK_TEST_012")
        workflow_transition("reviewer", task_id="TASK_TEST_012")

        # Add a review issue to trigger loopback condition
        workflow_add_review_issue(
            issue_type="missing_test",
            description="Need more tests",
            task_id="TASK_TEST_012"
        )

        # Loopback should work when there are review issues
        result = workflow_transition("developer", task_id="TASK_TEST_012")

        assert result["success"] is True
        assert result["iteration"] == 2  # Incremented


class TestDiscoveries:
    """Test memory preservation with discoveries."""

    def test_save_discovery(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_020")

        result = workflow_save_discovery(
            category="pattern",
            content="Use factory pattern for handlers",
            task_id="TASK_TEST_020"
        )

        assert result["success"] is True
        assert result["discovery"]["category"] == "pattern"

    def test_save_discovery_invalid_category(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_021")

        result = workflow_save_discovery(
            category="invalid",
            content="Test",
            task_id="TASK_TEST_021"
        )

        assert result["success"] is False
        assert "Invalid category" in result["error"]

    def test_get_discoveries_filtered(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_022")
        workflow_save_discovery("pattern", "Pattern 1", task_id="TASK_TEST_022")
        workflow_save_discovery("gotcha", "Gotcha 1", task_id="TASK_TEST_022")
        workflow_save_discovery("pattern", "Pattern 2", task_id="TASK_TEST_022")

        result = workflow_get_discoveries(category="pattern", task_id="TASK_TEST_022")

        assert result["count"] == 2
        assert all(d["category"] == "pattern" for d in result["discoveries"])

    def test_flush_context(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_023")
        workflow_save_discovery("decision", "Decision 1", task_id="TASK_TEST_023")
        workflow_save_discovery("pattern", "Pattern 1", task_id="TASK_TEST_023")
        workflow_save_discovery("pattern", "Pattern 2", task_id="TASK_TEST_023")

        result = workflow_flush_context(task_id="TASK_TEST_023")

        assert result["count"] == 3
        assert result["by_category"]["decision"] == 1
        assert result["by_category"]["pattern"] == 2


class TestContextManagement:
    """Test context usage and pruning."""

    def test_get_context_usage(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_030")

        result = workflow_get_context_usage(task_id="TASK_TEST_030")

        assert "total_size_kb" in result
        assert "context_usage_percent" in result
        assert "recommendation" in result
        assert result["file_count"] >= 1  # At least state.json

    def test_prune_preserves_important_files(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_031")
        task_dir = clean_tasks_dir / "TASK_TEST_031"

        # Create a large file that matches prunable pattern
        (task_dir / "repomix-output.txt").write_text("x" * 60000)
        # Create important file that should be preserved
        (task_dir / "plan.md").write_text("# Important Plan")

        result = workflow_prune_old_outputs(task_id="TASK_TEST_031", keep_last_n=0)

        assert result["success"] is True
        assert "plan.md" in result["preserved_files"]
        assert (task_dir / "plan.md").exists()

    def test_prune_creates_summaries(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_032")
        task_dir = clean_tasks_dir / "TASK_TEST_032"

        # Create large file with content
        lines = [f"Line {i}" for i in range(100)]
        (task_dir / "repomix-output.txt").write_text("\n".join(lines))

        workflow_prune_old_outputs(task_id="TASK_TEST_032", keep_last_n=0)

        summary_file = task_dir / "pruned" / "repomix-output_summary.json"
        assert summary_file.exists()

        summary = json.loads(summary_file.read_text())
        assert "original_size_bytes" in summary
        assert "total_lines" in summary


class TestCrossTaskMemory:
    """Test cross-task memory search and linking."""

    def test_search_memories_across_tasks(self, clean_tasks_dir):
        # Create two tasks with discoveries
        workflow_initialize(task_id="TASK_CROSS_001")
        workflow_initialize(task_id="TASK_CROSS_002")

        workflow_save_discovery("pattern", "Factory pattern for handlers", task_id="TASK_CROSS_001")
        workflow_save_discovery("pattern", "Factory pattern for validators", task_id="TASK_CROSS_002")

        result = workflow_search_memories("factory")

        assert result["count"] == 2
        assert result["tasks_searched"] >= 2

    def test_search_memories_with_category_filter(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_CROSS_003")
        workflow_save_discovery("pattern", "Factory pattern", task_id="TASK_CROSS_003")
        workflow_save_discovery("gotcha", "Factory gotcha", task_id="TASK_CROSS_003")

        result = workflow_search_memories("factory", category="pattern")

        assert result["count"] == 1
        assert result["results"][0]["category"] == "pattern"

    def test_link_tasks_bidirectional(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_CROSS_010")
        workflow_initialize(task_id="TASK_CROSS_011")

        result = workflow_link_tasks(
            task_id="TASK_CROSS_011",
            related_task_ids=["TASK_CROSS_010"],
            relationship="builds_on"
        )

        assert result["success"] is True
        assert "TASK_CROSS_010" in result["new_links"]

        # Check reverse link
        linked = workflow_get_linked_tasks(task_id="TASK_CROSS_010")
        assert "built_upon_by" in linked["linked_tasks"]
        assert "TASK_CROSS_011" in linked["linked_tasks"]["built_upon_by"]

    def test_get_linked_tasks_with_memories(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_CROSS_020")
        workflow_initialize(task_id="TASK_CROSS_021")

        workflow_save_discovery("pattern", "Shared pattern", task_id="TASK_CROSS_020")
        workflow_link_tasks("TASK_CROSS_021", ["TASK_CROSS_020"], "related")

        result = workflow_get_linked_tasks(
            task_id="TASK_CROSS_021",
            include_memories=True
        )

        assert "linked_memories" in result
        assert "TASK_CROSS_020" in result["linked_memories"]


class TestModelResilience:
    """Test model failover and resilience features."""

    def test_record_model_error(self, clean_tasks_dir):
        result = workflow_record_model_error(
            model="claude-opus-4",
            error_type="rate_limit",
            error_message="429 Too Many Requests"
        )

        assert result["success"] is True
        assert result["consecutive_errors"] == 1
        assert result["cooldown_seconds"] == 60  # First error: 1 minute

    def test_exponential_backoff(self, clean_tasks_dir):
        # Record multiple consecutive errors
        workflow_record_model_error("claude-sonnet-4", "rate_limit")
        result1 = workflow_record_model_error("claude-sonnet-4", "rate_limit")
        result2 = workflow_record_model_error("claude-sonnet-4", "rate_limit")

        # Backoff should increase: 60 -> 300 -> 1500
        assert result1["cooldown_seconds"] == 300  # 5 minutes
        assert result2["cooldown_seconds"] == 1500  # 25 minutes

    def test_success_resets_consecutive(self, clean_tasks_dir):
        workflow_record_model_error("gemini", "rate_limit")
        workflow_record_model_error("gemini", "rate_limit")

        workflow_record_model_success("gemini")
        workflow_clear_model_cooldown("gemini")  # Clear cooldown for test

        # Next error should start at base cooldown again
        result = workflow_record_model_error("gemini", "rate_limit")
        assert result["consecutive_errors"] == 1
        assert result["cooldown_seconds"] == 60

    def test_get_available_model_fallback(self, clean_tasks_dir):
        # Put primary model in cooldown
        workflow_record_model_error("claude-opus-4", "rate_limit")

        result = workflow_get_available_model(preferred_model="claude-opus-4")

        assert result["available"] is True
        assert result["model"] == "claude-sonnet-4"  # Fallback
        assert result["is_fallback"] is True

    def test_all_models_in_cooldown(self, clean_tasks_dir):
        # Put all models in cooldown
        workflow_record_model_error("claude-opus-4", "rate_limit")
        workflow_record_model_error("claude-sonnet-4", "rate_limit")
        workflow_record_model_error("gemini", "rate_limit")

        result = workflow_get_available_model()

        assert result["available"] is False
        assert "wait_seconds" in result
        assert "next_available" in result

    def test_billing_error_long_cooldown(self, clean_tasks_dir):
        result = workflow_record_model_error("gemini", "billing", "Quota exceeded")

        assert result["cooldown_seconds"] == 18000  # 5 hours

    def test_clear_model_cooldown(self, clean_tasks_dir):
        workflow_record_model_error("claude-opus-4", "rate_limit")

        # Model should be in cooldown
        status_before = workflow_get_available_model(preferred_model="claude-opus-4")
        assert status_before["is_fallback"] is True

        # Clear cooldown
        workflow_clear_model_cooldown("claude-opus-4")

        # Model should be available again
        status_after = workflow_get_available_model(preferred_model="claude-opus-4")
        assert status_after["model"] == "claude-opus-4"
        assert status_after["is_fallback"] is False

    def test_resilience_status(self, clean_tasks_dir):
        workflow_record_model_error("claude-opus-4", "rate_limit")

        result = workflow_get_resilience_status()

        assert "models" in result
        assert "fallback_chain" in result
        assert "config" in result
        assert len([m for m in result["models"] if m["model"] == "claude-opus-4"]) == 1


class TestConcerns:
    """Test concern tracking across agents."""

    def test_add_and_address_concern(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_040")

        # Add concern
        add_result = workflow_add_concern(
            source="skeptic",
            severity="high",
            description="Race condition in auth flow",
            task_id="TASK_TEST_040"
        )

        assert add_result["success"] is True
        concern_id = add_result["concern"]["id"]

        # Address concern
        addr_result = workflow_address_concern(
            concern_id=concern_id,
            addressed_by="step 3.2",
            task_id="TASK_TEST_040"
        )

        assert addr_result["success"] is True
        assert "step 3.2" in addr_result["concern"]["addressed_by"]

    def test_get_unaddressed_concerns(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_041")

        workflow_add_concern("reviewer", "medium", "Missing tests", task_id="TASK_TEST_041")
        result = workflow_add_concern("skeptic", "low", "Edge case", task_id="TASK_TEST_041")

        # Address one
        workflow_address_concern(result["concern"]["id"], "step 2.1", task_id="TASK_TEST_041")

        # Get unaddressed only
        concerns = workflow_get_concerns(task_id="TASK_TEST_041", unaddressed_only=True)

        assert concerns["total"] == 1
        assert concerns["unaddressed_count"] == 1


class TestImplementationProgress:
    """Test implementation progress tracking."""

    def test_set_and_complete_steps(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_050")

        # Set total steps
        workflow_set_implementation_progress(total_steps=10, task_id="TASK_TEST_050")

        # Complete some steps
        workflow_complete_step("1.1", task_id="TASK_TEST_050")
        workflow_complete_step("1.2", task_id="TASK_TEST_050")
        result = workflow_complete_step("2.1", task_id="TASK_TEST_050")

        assert result["success"] is True
        assert result["implementation_progress"]["current_step"] == 3
        assert "1.1" in result["implementation_progress"]["steps_completed"]


class TestHumanDecisions:
    """Test human decision recording."""

    def test_record_human_decision(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_060")

        result = workflow_add_human_decision(
            checkpoint="after_architect",
            decision="approve",
            notes="Looks good, proceed",
            task_id="TASK_TEST_060"
        )

        assert result["success"] is True
        assert result["decision"]["decision"] == "approve"
        assert result["total_decisions"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
