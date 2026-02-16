"""
Extended tests for state_tools.py — covers helpers, edge cases, and
every function not fully covered by test_state_tools.py.

Run with: pytest tests/test_state_tools_extended.py -v
"""

import json
import shutil
import pytest
from pathlib import Path
from datetime import datetime, timedelta

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentic_workflow_server.state_tools import (
    # Helpers
    _normalize_phase,
    _get_next_task_id,
    _create_default_state,
    _get_context_recommendation,
    _can_transition,
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
    # Workflow modes
    workflow_detect_mode,
    workflow_set_mode,
    workflow_get_mode,
    workflow_is_phase_in_mode,
    # Cost tracking
    workflow_record_cost,
    workflow_get_cost_summary,
    # Parallelization
    workflow_start_parallel_phase,
    workflow_complete_parallel_phase,
    workflow_merge_parallel_results,
    # Assertions
    workflow_add_assertion,
    workflow_verify_assertion,
    workflow_get_assertions,
    # Error patterns
    workflow_record_error_pattern,
    workflow_match_error,
    # Agent performance
    workflow_record_concern_outcome,
    workflow_get_agent_performance,
    # Optional phases
    workflow_enable_optional_phase,
    workflow_get_optional_phases,
    # Constants
    get_tasks_dir,
    DISCOVERY_CATEGORIES,
    PHASE_ORDER,
    REQUIRED_PHASES,
)


@pytest.fixture
def clean_tasks_dir():
    """Clean up .tasks directory before and after tests."""
    tasks_dir = get_tasks_dir()

    for pattern in ["TASK_EXT_*", "TASK_EHELP_*"]:
        for d in tasks_dir.glob(pattern):
            if d.is_dir():
                shutil.rmtree(d)

    resilience_file = tasks_dir / ".resilience_state.json"
    if resilience_file.exists():
        resilience_file.unlink()

    error_patterns_file = tasks_dir / ".error_patterns.jsonl"
    if error_patterns_file.exists():
        error_patterns_file.unlink()

    performance_file = tasks_dir / ".agent_performance.jsonl"
    if performance_file.exists():
        performance_file.unlink()

    yield tasks_dir

    for pattern in ["TASK_EXT_*", "TASK_EHELP_*"]:
        for d in tasks_dir.glob(pattern):
            if d.is_dir():
                shutil.rmtree(d)

    if resilience_file.exists():
        resilience_file.unlink()
    if error_patterns_file.exists():
        error_patterns_file.unlink()
    if performance_file.exists():
        performance_file.unlink()


# ============================================================================
# Helper functions
# ============================================================================

class TestNormalizePhase:
    def test_spaces_stripped(self):
        assert _normalize_phase("  architect  ") == "architect"

    def test_hyphens_to_underscores(self):
        assert _normalize_phase("technical-writer") == "technical_writer"

    def test_mixed_case(self):
        assert _normalize_phase("Developer") == "developer"

    def test_already_normalized(self):
        assert _normalize_phase("reviewer") == "reviewer"

    def test_combined_transforms(self):
        assert _normalize_phase("  Technical-Writer  ") == "technical_writer"


class TestGetNextTaskId:
    def test_empty_dir_returns_task_001(self, tmp_path):
        """When no existing tasks, returns TASK_001."""
        from unittest.mock import patch
        with patch("agentic_workflow_server.state_tools.get_tasks_dir", return_value=tmp_path):
            result = _get_next_task_id()
        assert result == "TASK_001"

    def test_gaps_in_numbering(self, tmp_path):
        """Picks next after max, ignoring gaps."""
        from unittest.mock import patch
        (tmp_path / "TASK_001").mkdir()
        (tmp_path / "TASK_005").mkdir()
        with patch("agentic_workflow_server.state_tools.get_tasks_dir", return_value=tmp_path):
            result = _get_next_task_id()
        assert result == "TASK_006"

    def test_non_task_dirs_ignored(self, tmp_path):
        """Non-TASK_ directories are skipped."""
        from unittest.mock import patch
        (tmp_path / "TASK_003").mkdir()
        (tmp_path / "random_dir").mkdir()
        (tmp_path / ".resilience_state.json").touch()
        with patch("agentic_workflow_server.state_tools.get_tasks_dir", return_value=tmp_path):
            result = _get_next_task_id()
        assert result == "TASK_004"


class TestCreateDefaultState:
    def test_all_expected_keys(self):
        state = _create_default_state("TASK_001")
        expected_keys = {
            "task_id", "phase", "phases_completed", "review_issues",
            "iteration", "docs_needed", "implementation_progress",
            "human_decisions", "knowledge_base_inventory", "concerns",
            "worktree", "created_at", "updated_at"
        }
        assert expected_keys.issubset(set(state.keys()))

    def test_worktree_is_none(self):
        state = _create_default_state("TASK_001")
        assert state["worktree"] is None

    def test_task_id_set(self):
        state = _create_default_state("TASK_XYZ")
        assert state["task_id"] == "TASK_XYZ"


class TestGetContextRecommendation:
    def test_low_usage(self):
        result = _get_context_recommendation(10)
        assert "low" in result.lower() or "no action" in result.lower()

    def test_moderate_usage(self):
        result = _get_context_recommendation(45)
        assert "moderate" in result.lower()

    def test_high_usage(self):
        result = _get_context_recommendation(70)
        assert "high" in result.lower()

    def test_critical_usage(self):
        result = _get_context_recommendation(90)
        assert "critical" in result.lower()


# ============================================================================
# Initialization edge cases
# ============================================================================

class TestInitializationEdgeCases:
    def test_auto_generate_task_id(self, clean_tasks_dir):
        result = workflow_initialize()
        assert result["success"] is True
        assert result["task_id"].startswith("TASK_")
        # Clean up
        task_dir = clean_tasks_dir / result["task_id"]
        if task_dir.exists():
            shutil.rmtree(task_dir)

    def test_initialize_creates_task_dir(self, clean_tasks_dir):
        result = workflow_initialize(task_id="TASK_EXT_001")
        assert result["success"] is True
        assert (clean_tasks_dir / "TASK_EXT_001").is_dir()
        assert (clean_tasks_dir / "TASK_EXT_001" / "state.json").exists()

    def test_state_file_has_correct_structure(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_002")
        state_file = clean_tasks_dir / "TASK_EXT_002" / "state.json"
        with open(state_file) as f:
            state = json.load(f)
        assert state["phase"] == "architect"
        assert state["iteration"] == 1
        assert state["phases_completed"] == []


# ============================================================================
# Transition edge cases
# ============================================================================

class TestTransitionEdgeCases:
    def test_rerun_current_phase(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_010")
        result = workflow_transition("architect", task_id="TASK_EXT_010")
        assert result["success"] is True
        assert "Re-running" in result["reason"]

    def test_invalid_phase_name(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_011")
        result = workflow_transition("nonexistent_phase", task_id="TASK_EXT_011")
        assert result["success"] is False
        assert "Invalid phase" in result["error"]

    def test_already_completed_phase_rejected(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_012")
        workflow_transition("developer", task_id="TASK_EXT_012")
        workflow_transition("reviewer", task_id="TASK_EXT_012")
        # Try going back to architect (completed, not developer)
        result = workflow_transition("architect", task_id="TASK_EXT_012")
        assert result["success"] is False
        assert "already completed" in result["error"]

    def test_forward_through_full_chain(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_013")
        for phase in PHASE_ORDER[1:]:
            result = workflow_transition(phase, task_id="TASK_EXT_013")
            assert result["success"] is True, f"Failed transitioning to {phase}"

    def test_transition_nonexistent_task(self, clean_tasks_dir):
        result = workflow_transition("developer", task_id="TASK_NONEXISTENT")
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_loopback_from_skeptic_to_developer(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_014")
        workflow_transition("developer", task_id="TASK_EXT_014")
        workflow_transition("reviewer", task_id="TASK_EXT_014")
        workflow_transition("skeptic", task_id="TASK_EXT_014")
        workflow_add_review_issue("bug", "Found bug", task_id="TASK_EXT_014")
        result = workflow_transition("developer", task_id="TASK_EXT_014")
        assert result["success"] is True
        assert result["iteration"] == 2

    def test_transition_clears_review_issues_on_loopback(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_015")
        workflow_transition("developer", task_id="TASK_EXT_015")
        workflow_transition("reviewer", task_id="TASK_EXT_015")
        workflow_add_review_issue("bug", "Found bug", task_id="TASK_EXT_015")
        workflow_transition("developer", task_id="TASK_EXT_015")
        state = workflow_get_state(task_id="TASK_EXT_015")
        assert state["review_issues"] == []


# ============================================================================
# workflow_get_state edge cases
# ============================================================================

class TestGetStateEdgeCases:
    def test_partial_incomplete(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_020")
        state = workflow_get_state(task_id="TASK_EXT_020")
        assert state["is_complete"] is False
        assert len(state["missing_phases"]) > 0

    def test_all_phases_done(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_021")
        for phase in PHASE_ORDER:
            workflow_transition(phase, task_id="TASK_EXT_021")
            workflow_complete_phase(task_id="TASK_EXT_021")
        state = workflow_get_state(task_id="TASK_EXT_021")
        assert state["is_complete"] is True

    def test_nonexistent_task_returns_error(self, clean_tasks_dir):
        result = workflow_get_state(task_id="TASK_NONEXISTENT_999")
        assert "error" in result


# ============================================================================
# workflow_add_review_issue edge cases
# ============================================================================

class TestAddReviewIssueEdgeCases:
    def test_with_step_parameter(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_030")
        result = workflow_add_review_issue(
            "missing_test", "Need test", step="3.1", task_id="TASK_EXT_030"
        )
        assert result["success"] is True
        assert result["issue"]["step"] == "3.1"

    def test_severity_default_is_medium(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_031")
        result = workflow_add_review_issue(
            "bug", "Bug found", task_id="TASK_EXT_031"
        )
        assert result["issue"]["severity"] == "medium"

    def test_multiple_issues_accumulate(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_032")
        workflow_add_review_issue("bug", "Bug 1", task_id="TASK_EXT_032")
        workflow_add_review_issue("bug", "Bug 2", task_id="TASK_EXT_032")
        result = workflow_add_review_issue("bug", "Bug 3", task_id="TASK_EXT_032")
        assert result["total_issues"] == 3


# ============================================================================
# workflow_mark_docs_needed edge cases
# ============================================================================

class TestMarkDocsNeededEdgeCases:
    def test_add_new_files(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_040")
        result = workflow_mark_docs_needed(["README.md", "API.md"], task_id="TASK_EXT_040")
        assert result["success"] is True
        assert result["total"] == 2

    def test_deduplicates_existing(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_041")
        workflow_mark_docs_needed(["README.md"], task_id="TASK_EXT_041")
        result = workflow_mark_docs_needed(["README.md", "NEW.md"], task_id="TASK_EXT_041")
        assert result["total"] == 2
        assert "README.md" in result["all_files"]
        assert "NEW.md" in result["all_files"]

    def test_empty_list(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_042")
        result = workflow_mark_docs_needed([], task_id="TASK_EXT_042")
        assert result["success"] is True
        assert result["total"] == 0

    def test_nonexistent_task(self, clean_tasks_dir):
        result = workflow_mark_docs_needed(["file.md"], task_id="TASK_NONEXISTENT")
        assert result["success"] is False


# ============================================================================
# workflow_complete_phase edge cases
# ============================================================================

class TestCompletePhaseEdgeCases:
    def test_no_current_phase_returns_error(self, clean_tasks_dir):
        task_dir = clean_tasks_dir / "TASK_EXT_050"
        task_dir.mkdir(parents=True)
        state = _create_default_state("TASK_EXT_050")
        state["phase"] = None
        with open(task_dir / "state.json", "w") as f:
            json.dump(state, f)
        result = workflow_complete_phase(task_id="TASK_EXT_050")
        assert result["success"] is False
        assert "No current phase" in result["error"]

    def test_complete_already_completed_is_idempotent(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_051")
        workflow_complete_phase(task_id="TASK_EXT_051")
        result = workflow_complete_phase(task_id="TASK_EXT_051")
        assert result["success"] is True
        # Should not duplicate in phases_completed
        state = workflow_get_state(task_id="TASK_EXT_051")
        assert state["phases_completed"].count("architect") == 1

    def test_returns_remaining_phases(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_052")
        result = workflow_complete_phase(task_id="TASK_EXT_052")
        assert "remaining_phases" in result
        assert len(result["remaining_phases"]) > 0


# ============================================================================
# workflow_is_complete edge cases
# ============================================================================

class TestIsCompleteEdgeCases:
    def test_partial_completion(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_060")
        result = workflow_is_complete(task_id="TASK_EXT_060")
        assert result["is_complete"] is False
        assert len(result["missing_phases"]) > 0

    def test_full_completion(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_061")
        for phase in PHASE_ORDER:
            workflow_transition(phase, task_id="TASK_EXT_061")
            workflow_complete_phase(task_id="TASK_EXT_061")
        result = workflow_is_complete(task_id="TASK_EXT_061")
        assert result["is_complete"] is True

    def test_nonexistent_task(self, clean_tasks_dir):
        result = workflow_is_complete(task_id="TASK_NONEXISTENT")
        assert "error" in result


# ============================================================================
# workflow_can_transition edge cases
# ============================================================================

class TestCanTransitionEdgeCases:
    def test_valid_transition(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_070")
        result = workflow_can_transition("developer", task_id="TASK_EXT_070")
        assert result["can_transition"] is True

    def test_invalid_transition(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_071")
        result = workflow_can_transition("implementer", task_id="TASK_EXT_071")
        assert result["can_transition"] is False

    def test_nonexistent_task(self, clean_tasks_dir):
        result = workflow_can_transition("developer", task_id="TASK_NONEXISTENT")
        assert result["can_transition"] is False
        assert "error" in result


# ============================================================================
# workflow_can_stop edge cases
# ============================================================================

class TestCanStopEdgeCases:
    def test_no_active_task(self, clean_tasks_dir):
        result = workflow_can_stop(task_id="TASK_NONEXISTENT")
        assert result["can_stop"] is True
        assert "No active" in result["reason"]

    def test_workflow_not_started(self, clean_tasks_dir):
        task_dir = clean_tasks_dir / "TASK_EXT_080"
        task_dir.mkdir(parents=True)
        state = _create_default_state("TASK_EXT_080")
        state["phase"] = None
        with open(task_dir / "state.json", "w") as f:
            json.dump(state, f)
        result = workflow_can_stop(task_id="TASK_EXT_080")
        assert result["can_stop"] is True

    def test_all_complete(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_081")
        for phase in PHASE_ORDER:
            workflow_transition(phase, task_id="TASK_EXT_081")
            workflow_complete_phase(task_id="TASK_EXT_081")
        result = workflow_can_stop(task_id="TASK_EXT_081")
        assert result["can_stop"] is True

    def test_incomplete_with_missing_phases(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_082")
        result = workflow_can_stop(task_id="TASK_EXT_082")
        assert result["can_stop"] is False
        assert "missing_phases" in result

    def test_worktree_active_no_phases(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_083")
        # Manually set worktree active without completing phases
        task_dir = clean_tasks_dir / "TASK_EXT_083"
        with open(task_dir / "state.json") as f:
            state = json.load(f)
        state["worktree"] = {"status": "active", "path": "/tmp/wt"}
        state["phases_completed"] = []
        with open(task_dir / "state.json", "w") as f:
            json.dump(state, f)
        result = workflow_can_stop(task_id="TASK_EXT_083")
        assert result["can_stop"] is True
        assert "worktree" in result["reason"].lower()


# ============================================================================
# workflow_set_kb_inventory edge cases
# ============================================================================

class TestSetKbInventoryEdgeCases:
    def test_set_inventory(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_090")
        result = workflow_set_kb_inventory(
            "docs/ai-context/", ["file1.md", "file2.md"], task_id="TASK_EXT_090"
        )
        assert result["success"] is True
        assert result["knowledge_base_inventory"]["path"] == "docs/ai-context/"

    def test_overwrite_inventory(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_091")
        workflow_set_kb_inventory("docs/old/", ["old.md"], task_id="TASK_EXT_091")
        result = workflow_set_kb_inventory("docs/new/", ["new.md"], task_id="TASK_EXT_091")
        assert result["knowledge_base_inventory"]["path"] == "docs/new/"

    def test_nonexistent_task(self, clean_tasks_dir):
        result = workflow_set_kb_inventory("docs/", [], task_id="TASK_NONEXISTENT")
        assert result["success"] is False


# ============================================================================
# Implementation progress edge cases
# ============================================================================

class TestImplementationProgressEdgeCases:
    def test_duplicate_step_is_idempotent(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_100")
        workflow_set_implementation_progress(total_steps=5, task_id="TASK_EXT_100")
        workflow_complete_step("1.1", task_id="TASK_EXT_100")
        result = workflow_complete_step("1.1", task_id="TASK_EXT_100")
        # Step should appear only once
        assert result["implementation_progress"]["steps_completed"].count("1.1") == 1
        assert result["implementation_progress"]["current_step"] == 1

    def test_progress_percentage(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_101")
        workflow_set_implementation_progress(total_steps=4, task_id="TASK_EXT_101")
        workflow_complete_step("s1", task_id="TASK_EXT_101")
        result = workflow_complete_step("s2", task_id="TASK_EXT_101")
        assert result["implementation_progress"]["current_step"] == 2
        assert result["implementation_progress"]["total_steps"] == 4

    def test_nonexistent_task(self, clean_tasks_dir):
        result = workflow_set_implementation_progress(total_steps=5, task_id="TASK_NONEXISTENT")
        assert result["success"] is False


# ============================================================================
# Human decisions edge cases
# ============================================================================

class TestHumanDecisionsEdgeCases:
    def test_multiple_decisions_accumulate(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_110")
        workflow_add_human_decision("after_architect", "approve", task_id="TASK_EXT_110")
        result = workflow_add_human_decision("after_reviewer", "reject", task_id="TASK_EXT_110")
        assert result["total_decisions"] == 2

    def test_nonexistent_task(self, clean_tasks_dir):
        result = workflow_add_human_decision("cp", "approve", task_id="TASK_NONEXISTENT")
        assert result["success"] is False


# ============================================================================
# Concerns edge cases
# ============================================================================

class TestConcernsEdgeCases:
    def test_custom_concern_id(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_120")
        result = workflow_add_concern(
            "skeptic", "high", "Custom ID concern",
            concern_id="CUSTOM_001", task_id="TASK_EXT_120"
        )
        assert result["concern"]["id"] == "CUSTOM_001"

    def test_address_nonexistent_concern(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_121")
        result = workflow_address_concern("NONEXISTENT", "step 1", task_id="TASK_EXT_121")
        assert result["success"] is False

    def test_get_all_concerns(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_122")
        workflow_add_concern("reviewer", "high", "Issue 1", task_id="TASK_EXT_122")
        workflow_add_concern("skeptic", "low", "Issue 2", task_id="TASK_EXT_122")
        result = workflow_get_concerns(task_id="TASK_EXT_122")
        assert result["total"] == 2

    def test_concern_severity_levels(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_123")
        for severity in ["low", "medium", "high", "critical"]:
            result = workflow_add_concern(
                "reviewer", severity, f"{severity} concern", task_id="TASK_EXT_123"
            )
            assert result["concern"]["severity"] == severity


# ============================================================================
# Discoveries edge cases
# ============================================================================

class TestDiscoveriesEdgeCases:
    def test_get_discoveries_empty_file(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_130")
        result = workflow_get_discoveries(task_id="TASK_EXT_130")
        assert result["count"] == 0
        assert result["discoveries"] == []

    def test_flush_context_empty(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_131")
        result = workflow_flush_context(task_id="TASK_EXT_131")
        assert result["count"] == 0

    def test_malformed_jsonl_line_skipped(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_132")
        # Save valid + invalid entries
        memory_dir = clean_tasks_dir / "TASK_EXT_132" / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        discoveries_file = memory_dir / "discoveries.jsonl"
        with open(discoveries_file, "w") as f:
            f.write(json.dumps({"category": "pattern", "content": "Valid", "timestamp": "2024-01-01"}) + "\n")
            f.write("THIS IS NOT JSON\n")
            f.write(json.dumps({"category": "gotcha", "content": "Also valid", "timestamp": "2024-01-02"}) + "\n")

        result = workflow_get_discoveries(task_id="TASK_EXT_132")
        assert result["count"] == 2

    def test_all_categories_valid(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_133")
        for cat in DISCOVERY_CATEGORIES:
            result = workflow_save_discovery(cat, f"Test {cat}", task_id="TASK_EXT_133")
            assert result["success"] is True


# ============================================================================
# Context management edge cases
# ============================================================================

class TestContextManagementEdgeCases:
    def test_all_4_recommendation_levels(self):
        assert "low" in _get_context_recommendation(10).lower() or "no action" in _get_context_recommendation(10).lower()
        assert "moderate" in _get_context_recommendation(45).lower()
        assert "high" in _get_context_recommendation(70).lower()
        assert "critical" in _get_context_recommendation(90).lower()

    def test_prune_with_no_prunable_files(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_140")
        result = workflow_prune_old_outputs(task_id="TASK_EXT_140", keep_last_n=0)
        assert result["success"] is True
        assert result["pruned_count"] == 0

    def test_prune_large_non_pattern_file(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_141")
        task_dir = clean_tasks_dir / "TASK_EXT_141"
        # Create a large file (>50KB) that isn't in preserve list
        (task_dir / "large_output.txt").write_text("x" * 60000)
        result = workflow_prune_old_outputs(task_id="TASK_EXT_141", keep_last_n=0)
        assert result["pruned_count"] >= 1

    def test_context_usage_with_nested_files(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_142")
        task_dir = clean_tasks_dir / "TASK_EXT_142"
        sub = task_dir / "subdir"
        sub.mkdir()
        (sub / "nested.txt").write_text("nested content")
        result = workflow_get_context_usage(task_id="TASK_EXT_142")
        assert result["file_count"] >= 2  # state.json + nested.txt


# ============================================================================
# Cross-task memory edge cases
# ============================================================================

class TestCrossTaskMemoryEdgeCases:
    def test_search_with_max_results(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_150")
        for i in range(5):
            workflow_save_discovery("pattern", f"Factory item {i}", task_id="TASK_EXT_150")
        result = workflow_search_memories("factory", max_results=2)
        assert len(result["results"]) <= 2

    def test_search_specific_task_ids(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_151")
        workflow_initialize(task_id="TASK_EXT_152")
        workflow_save_discovery("pattern", "Specific pattern", task_id="TASK_EXT_151")
        workflow_save_discovery("pattern", "Specific pattern", task_id="TASK_EXT_152")

        result = workflow_search_memories(
            "specific", task_ids=["TASK_EXT_151"]
        )
        assert result["count"] == 1
        assert result["results"][0]["task_id"] == "TASK_EXT_151"

    def test_search_nonexistent_tasks_dir(self, clean_tasks_dir):
        """When task_ids list contains nonexistent tasks, they're skipped."""
        result = workflow_search_memories("anything", task_ids=["TASK_NONEXISTENT_999"])
        assert result["count"] == 0

    def test_link_invalid_relationship(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_155")
        result = workflow_link_tasks("TASK_EXT_155", ["TASK_EXT_155"], "invalid_rel")
        assert result["success"] is False
        assert "Invalid relationship" in result["error"]

    def test_link_with_mix_of_valid_invalid(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_156")
        workflow_initialize(task_id="TASK_EXT_157")
        result = workflow_link_tasks(
            "TASK_EXT_156",
            ["TASK_EXT_157", "TASK_NONEXISTENT"],
            "related"
        )
        assert result["success"] is True
        assert "TASK_EXT_157" in result["new_links"]
        assert "TASK_NONEXISTENT" in result["invalid_tasks"]

    def test_get_linked_tasks_without_include_memories(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_158")
        result = workflow_get_linked_tasks(task_id="TASK_EXT_158", include_memories=False)
        assert "linked_memories" not in result


# ============================================================================
# Resilience edge cases
# ============================================================================

class TestResilienceEdgeCases:
    def test_overloaded_cooldown_scales(self, clean_tasks_dir):
        result1 = workflow_record_model_error("test-model-ol", "overloaded")
        result2 = workflow_record_model_error("test-model-ol", "overloaded")
        assert result1["cooldown_seconds"] == 60  # 60 * 1
        assert result2["cooldown_seconds"] == 120  # 60 * 2

    def test_timeout_cooldown(self, clean_tasks_dir):
        result = workflow_record_model_error("test-model-to", "timeout")
        assert result["cooldown_seconds"] == 300  # error_seconds * 1

    def test_server_error_cooldown(self, clean_tasks_dir):
        result = workflow_record_model_error("test-model-se", "server_error")
        assert result["cooldown_seconds"] == 300

    def test_auth_error_max_cooldown(self, clean_tasks_dir):
        result = workflow_record_model_error("test-model-auth", "auth")
        assert result["cooldown_seconds"] == 3600  # max_cooldown_seconds

    def test_invalid_error_type(self, clean_tasks_dir):
        result = workflow_record_model_error("test-model", "invalid_type")
        assert result["success"] is False

    def test_success_on_model_with_no_errors(self, clean_tasks_dir):
        result = workflow_record_model_success("fresh-model")
        assert result["success"] is True
        assert "No error history" in result["message"]

    def test_resilience_status_with_multiple_models(self, clean_tasks_dir):
        workflow_record_model_error("model-a", "rate_limit")
        workflow_record_model_error("model-b", "timeout")
        result = workflow_get_resilience_status()
        model_names = [m["model"] for m in result["models"]]
        assert "model-a" in model_names
        assert "model-b" in model_names


# ============================================================================
# Mode detection edge cases
# ============================================================================

class TestModeDetectionEdgeCases:
    def test_database_keywords_full(self):
        result = workflow_detect_mode("Add database migration for users table")
        assert result["mode"] == "full"
        assert "database" in result["matched_keywords"]

    def test_api_breaking_full(self):
        result = workflow_detect_mode("Breaking API change for v2")
        assert result["mode"] == "full"

    def test_unknown_description_defaults_to_full(self):
        result = workflow_detect_mode("Do something completely generic with no keywords")
        assert result["mode"] == "full"
        assert result["confidence"] == 0.5

    def test_turbo_blocked_by_database(self):
        result = workflow_detect_mode("Implement database connection pooling")
        assert result["mode"] == "full"

    def test_case_insensitive(self):
        result = workflow_detect_mode("FIX TYPO in README")
        assert result["mode"] == "minimal"


# ============================================================================
# Cost tracking edge cases
# ============================================================================

class TestCostTrackingEdgeCases:
    def test_summary_with_no_entries(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_200")
        result = workflow_get_cost_summary(task_id="TASK_EXT_200")
        assert result["entries_count"] == 0
        assert result["totals"]["total_cost"] == 0

    def test_sonnet_pricing(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_201")
        result = workflow_record_cost(
            "developer", "sonnet", 100000, 10000, task_id="TASK_EXT_201"
        )
        assert result["success"] is True
        # Sonnet: $3/M input, $15/M output
        expected_input = (100000 / 1_000_000) * 3.00
        expected_output = (10000 / 1_000_000) * 15.00
        assert abs(result["entry"]["input_cost"] - expected_input) < 0.01
        assert abs(result["entry"]["output_cost"] - expected_output) < 0.01

    def test_haiku_pricing(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_202")
        result = workflow_record_cost(
            "developer", "haiku", 100000, 10000, task_id="TASK_EXT_202"
        )
        assert result["success"] is True
        # Haiku: $0.80/M input, $4/M output
        expected_input = (100000 / 1_000_000) * 0.80
        expected_output = (10000 / 1_000_000) * 4.00
        assert abs(result["entry"]["input_cost"] - expected_input) < 0.01
        assert abs(result["entry"]["output_cost"] - expected_output) < 0.01

    def test_zero_tokens(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_203")
        result = workflow_record_cost(
            "developer", "opus", 0, 0, task_id="TASK_EXT_203"
        )
        assert result["success"] is True
        assert result["entry"]["total_cost"] == 0

    def test_duration_seconds_recorded(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_204")
        result = workflow_record_cost(
            "architect", "opus", 1000, 500,
            duration_seconds=45.2, task_id="TASK_EXT_204"
        )
        assert result["entry"]["duration_seconds"] == 45.2


# ============================================================================
# Parallelization edge cases
# ============================================================================

class TestParallelizationEdgeCases:
    def test_complete_phase_not_in_parallel_set(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_210")
        workflow_start_parallel_phase(["reviewer", "skeptic"], task_id="TASK_EXT_210")
        result = workflow_complete_parallel_phase(
            phase="architect", result_summary="Not parallel", task_id="TASK_EXT_210"
        )
        assert result["success"] is False
        assert "not part of" in result["error"]

    def test_start_parallel_single_phase(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_211")
        result = workflow_start_parallel_phase(["reviewer"], task_id="TASK_EXT_211")
        assert result["success"] is True
        assert result["parallel_phases"] == ["reviewer"]

    def test_merge_with_no_concerns(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_212")
        workflow_start_parallel_phase(["reviewer", "skeptic"], task_id="TASK_EXT_212")
        workflow_complete_parallel_phase("reviewer", concerns=[], task_id="TASK_EXT_212")
        workflow_complete_parallel_phase("skeptic", concerns=[], task_id="TASK_EXT_212")
        result = workflow_merge_parallel_results(task_id="TASK_EXT_212")
        assert result["success"] is True
        assert result["original_count"] == 0
        assert result["merged_count"] == 0

    def test_start_parallel_twice_overwrites(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_213")
        workflow_start_parallel_phase(["reviewer"], task_id="TASK_EXT_213")
        result = workflow_start_parallel_phase(["skeptic", "reviewer"], task_id="TASK_EXT_213")
        assert result["success"] is True
        assert result["parallel_phases"] == ["skeptic", "reviewer"]


# ============================================================================
# Assertions edge cases
# ============================================================================

class TestAssertionsEdgeCases:
    def test_multiple_assertions_same_step(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_220")
        r1 = workflow_add_assertion("file_exists", {"path": "a.ts"}, "1.1", task_id="TASK_EXT_220")
        r2 = workflow_add_assertion("test_passes", {"cmd": "npm test"}, "1.1", task_id="TASK_EXT_220")
        assert r1["assertion"]["id"] == "A001"
        assert r2["assertion"]["id"] == "A002"

    def test_get_all_assertions_no_filter(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_221")
        workflow_add_assertion("file_exists", {"path": "a.ts"}, "1.1", task_id="TASK_EXT_221")
        workflow_add_assertion("test_passes", {"cmd": "test"}, "2.1", task_id="TASK_EXT_221")
        result = workflow_get_assertions(task_id="TASK_EXT_221")
        assert result["count"] == 2

    def test_verify_nonexistent_assertion(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_222")
        result = workflow_verify_assertion("NONEXISTENT", True, task_id="TASK_EXT_222")
        assert result["success"] is False

    def test_assertion_ids_auto_increment(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_223")
        ids = []
        for i in range(5):
            r = workflow_add_assertion("file_exists", {"path": f"f{i}.ts"}, task_id="TASK_EXT_223")
            ids.append(r["assertion"]["id"])
        assert ids == ["A001", "A002", "A003", "A004", "A005"]


# ============================================================================
# Error patterns edge cases
# ============================================================================

class TestErrorPatternsEdgeCases:
    def test_match_with_tags(self, clean_tasks_dir):
        workflow_record_error_pattern(
            "ImportError: no module", "runtime",
            "Install missing module", tags=["python", "import"]
        )
        result = workflow_match_error("ImportError: no module named 'foo'")
        assert result["count"] >= 1

    def test_low_confidence_excluded(self, clean_tasks_dir):
        workflow_record_error_pattern("x", "test", "Fix x")
        # "x" is very short, confidence = len("x")/50 + 0.5 = 0.52
        result = workflow_match_error("Something with x in it", min_confidence=0.9)
        assert result["count"] == 0

    def test_multiple_patterns_ranked(self, clean_tasks_dir):
        workflow_record_error_pattern(
            "Cannot find module", "compile", "Check imports"
        )
        workflow_record_error_pattern(
            "Cannot find module '@/lib", "compile", "Check tsconfig paths"
        )
        result = workflow_match_error("Error: Cannot find module '@/lib/utils'")
        assert result["count"] >= 2
        # More specific match should rank higher
        assert result["matches"][0]["confidence"] >= result["matches"][1]["confidence"]


# ============================================================================
# Agent performance edge cases
# ============================================================================

class TestAgentPerformanceEdgeCases:
    def test_performance_with_no_data(self, clean_tasks_dir):
        result = workflow_get_agent_performance()
        assert result["total_concerns"] == 0
        assert result["agents"] == {}

    def test_wont_fix_outcome_rejected(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_250")
        c = workflow_add_concern("reviewer", "high", "Issue", task_id="TASK_EXT_250")
        result = workflow_record_concern_outcome(
            c["concern"]["id"], "wont_fix", task_id="TASK_EXT_250"
        )
        assert result["success"] is False
        assert "Invalid outcome" in result["error"]

    def test_multiple_agents_aggregated(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_251")
        c1 = workflow_add_concern("skeptic", "high", "S issue", task_id="TASK_EXT_251")
        c2 = workflow_add_concern("reviewer", "medium", "R issue", task_id="TASK_EXT_251")
        workflow_record_concern_outcome(c1["concern"]["id"], "valid", task_id="TASK_EXT_251")
        workflow_record_concern_outcome(c2["concern"]["id"], "false_positive", task_id="TASK_EXT_251")

        result = workflow_get_agent_performance()
        assert "skeptic" in result["agents"]
        assert "reviewer" in result["agents"]
        assert result["agents"]["skeptic"]["valid"] == 1
        assert result["agents"]["reviewer"]["false_positive"] == 1


# ============================================================================
# Optional phases edge cases
# ============================================================================

class TestOptionalPhasesEdgeCases:
    def test_duplicate_enable_is_idempotent(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_260")
        workflow_enable_optional_phase("security_auditor", "Auth", task_id="TASK_EXT_260")
        result = workflow_enable_optional_phase("security_auditor", "Auth again", task_id="TASK_EXT_260")
        assert result["success"] is True
        assert result["optional_phases"].count("security_auditor") == 1

    def test_get_optional_phases_none_enabled(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_261")
        result = workflow_get_optional_phases(task_id="TASK_EXT_261")
        assert result["optional_phases"] == []

    def test_all_4_valid_phases(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_EXT_262")
        valid = ["security_auditor", "performance_analyst", "api_guardian", "accessibility_reviewer"]
        for phase in valid:
            result = workflow_enable_optional_phase(phase, f"Testing {phase}", task_id="TASK_EXT_262")
            assert result["success"] is True
        result = workflow_get_optional_phases(task_id="TASK_EXT_262")
        assert set(result["optional_phases"]) == set(valid)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
