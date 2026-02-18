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
    # Workflow modes
    workflow_detect_mode,
    workflow_set_mode,
    workflow_get_mode,
    workflow_is_phase_in_mode,
    # Effort levels
    workflow_get_effort_level,
    # Agent teams
    workflow_get_agent_team_config,
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
    # Worktree support
    workflow_create_worktree,
    workflow_get_worktree_info,
    workflow_cleanup_worktree,
    workflow_get_launch_command,
    _build_resume_prompt,
    _find_recyclable_worktree,
    _is_wsl,
    list_tasks,
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

    # Clean error patterns
    error_patterns_file = tasks_dir / ".error_patterns.jsonl"
    if error_patterns_file.exists():
        error_patterns_file.unlink()

    # Clean agent performance
    performance_file = tasks_dir / ".agent_performance.jsonl"
    if performance_file.exists():
        performance_file.unlink()

    yield tasks_dir

    # Clean up after
    for pattern in ["TASK_TEST_*", "TASK_CROSS_*"]:
        for d in tasks_dir.glob(pattern):
            if d.is_dir():
                shutil.rmtree(d)

    if resilience_file.exists():
        resilience_file.unlink()

    if error_patterns_file.exists():
        error_patterns_file.unlink()

    if performance_file.exists():
        performance_file.unlink()


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
            model="claude-opus-4-6",
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
        workflow_record_model_error("claude-opus-4-6", "rate_limit")

        result = workflow_get_available_model(preferred_model="claude-opus-4-6")

        assert result["available"] is True
        assert result["model"] == "claude-opus-4"  # Second in fallback chain
        assert result["is_fallback"] is True

    def test_all_models_in_cooldown(self, clean_tasks_dir):
        # Put all models in cooldown
        workflow_record_model_error("claude-opus-4-6", "rate_limit")
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
        workflow_record_model_error("claude-opus-4-6", "rate_limit")

        # Model should be in cooldown
        status_before = workflow_get_available_model(preferred_model="claude-opus-4-6")
        assert status_before["is_fallback"] is True

        # Clear cooldown
        workflow_clear_model_cooldown("claude-opus-4-6")

        # Model should be available again
        status_after = workflow_get_available_model(preferred_model="claude-opus-4-6")
        assert status_after["model"] == "claude-opus-4-6"
        assert status_after["is_fallback"] is False

    def test_resilience_status(self, clean_tasks_dir):
        workflow_record_model_error("claude-opus-4-6", "rate_limit")

        result = workflow_get_resilience_status()

        assert "models" in result
        assert "fallback_chain" in result
        assert "config" in result
        assert len([m for m in result["models"] if m["model"] == "claude-opus-4-6"]) == 1


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


class TestWorkflowModes:
    """Test workflow mode detection and management."""

    def test_detect_mode_minimal_typo(self, clean_tasks_dir):
        result = workflow_detect_mode("Fix typo in README")

        assert result["mode"] == "minimal"
        assert result["confidence"] >= 0.7
        assert "typo" in result["matched_keywords"]

    def test_detect_mode_full_security(self, clean_tasks_dir):
        result = workflow_detect_mode("Implement user authentication with JWT")

        assert result["mode"] == "full"
        assert result["confidence"] >= 0.8
        assert "authentication" in result["matched_keywords"]

    def test_detect_mode_fast_feature(self, clean_tasks_dir):
        # "Refactor" now detects as turbo (Opus 4.6 single-pass) since it matches turbo keywords
        result = workflow_detect_mode("Refactor the user profile component")

        assert result["mode"] == "turbo"
        assert "refactor" in [k.lower() for k in result["matched_keywords"]]

    def test_set_mode_explicit(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_100")

        result = workflow_set_mode("minimal", task_id="TASK_TEST_100")

        assert result["success"] is True
        assert result["workflow_mode"]["effective"] == "minimal"
        assert "developer" in result["workflow_mode"]["phases"]
        assert "architect" not in result["workflow_mode"]["phases"]

    def test_set_mode_auto(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_101", description="Fix typo in docs")

        result = workflow_set_mode("auto", task_id="TASK_TEST_101")

        assert result["success"] is True
        assert result["workflow_mode"]["requested"] == "auto"
        assert result["workflow_mode"]["effective"] == "minimal"

    def test_get_mode(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_102")
        workflow_set_mode("fast", task_id="TASK_TEST_102")

        result = workflow_get_mode(task_id="TASK_TEST_102")

        assert result["workflow_mode"]["effective"] == "fast"
        assert "available_modes" in result

    def test_is_phase_in_mode(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_103")
        workflow_set_mode("minimal", task_id="TASK_TEST_103")

        # Developer should be in minimal mode
        result1 = workflow_is_phase_in_mode("developer", task_id="TASK_TEST_103")
        assert result1["in_mode"] is True

        # Architect should NOT be in minimal mode
        result2 = workflow_is_phase_in_mode("architect", task_id="TASK_TEST_103")
        assert result2["in_mode"] is False

    def test_technical_writer_in_all_modes(self, clean_tasks_dir):
        for mode in ["full", "turbo", "fast", "minimal"]:
            task_id = f"TASK_TEST_TW_{mode}"
            workflow_initialize(task_id=task_id)
            workflow_set_mode(mode, task_id=task_id)

            result = workflow_is_phase_in_mode("technical_writer", task_id=task_id)
            assert result["in_mode"] is True, f"technical_writer should be in {mode} mode"


class TestCostTracking:
    """Test cost tracking and reporting."""

    def test_record_cost(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_110")

        result = workflow_record_cost(
            agent="architect",
            model="opus",
            input_tokens=10000,
            output_tokens=5000,
            duration_seconds=30.5,
            task_id="TASK_TEST_110"
        )

        assert result["success"] is True
        assert result["entry"]["input_tokens"] == 10000
        assert result["entry"]["output_tokens"] == 5000
        assert result["entry"]["total_cost"] > 0
        assert result["running_total"] > 0

    def test_cost_summary(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_111")

        workflow_record_cost("architect", "opus", 10000, 5000, task_id="TASK_TEST_111")
        workflow_record_cost("developer", "opus", 20000, 8000, task_id="TASK_TEST_111")
        workflow_record_cost("reviewer", "sonnet", 15000, 3000, task_id="TASK_TEST_111")

        result = workflow_get_cost_summary(task_id="TASK_TEST_111")

        assert result["entries_count"] == 3
        assert "architect" in result["by_agent"]
        assert "opus" in result["by_model"]
        assert result["totals"]["total_cost"] > 0
        assert "formatted_summary" in result


class TestParallelization:
    """Test parallel phase execution."""

    def test_start_parallel_phase(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_120")

        result = workflow_start_parallel_phase(
            phases=["reviewer", "skeptic"],
            task_id="TASK_TEST_120"
        )

        assert result["success"] is True
        assert result["parallel_phases"] == ["reviewer", "skeptic"]

    def test_complete_parallel_phases(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_121")
        workflow_start_parallel_phase(["reviewer", "skeptic"], task_id="TASK_TEST_121")

        # Complete reviewer
        result1 = workflow_complete_parallel_phase(
            phase="reviewer",
            result_summary="Found 2 issues",
            concerns=[{"description": "Missing validation"}],
            task_id="TASK_TEST_121"
        )

        assert result1["success"] is True
        assert result1["all_complete"] is False
        assert "skeptic" in result1["remaining"]

        # Complete skeptic
        result2 = workflow_complete_parallel_phase(
            phase="skeptic",
            result_summary="Found 1 edge case",
            concerns=[{"description": "Race condition possible"}],
            task_id="TASK_TEST_121"
        )

        assert result2["success"] is True
        assert result2["all_complete"] is True
        assert result2["remaining"] == []

    def test_merge_parallel_results_deduplicate(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_122")
        workflow_start_parallel_phase(["reviewer", "skeptic"], task_id="TASK_TEST_122")

        # Both agents find the same concern
        workflow_complete_parallel_phase(
            phase="reviewer",
            concerns=[{"description": "Missing input validation"}],
            task_id="TASK_TEST_122"
        )
        workflow_complete_parallel_phase(
            phase="skeptic",
            concerns=[{"description": "Missing input validation"}, {"description": "Race condition"}],
            task_id="TASK_TEST_122"
        )

        result = workflow_merge_parallel_results(
            task_id="TASK_TEST_122",
            merge_strategy="deduplicate"
        )

        assert result["success"] is True
        assert result["original_count"] == 3
        assert result["merged_count"] == 2  # Deduplicated


class TestAssertions:
    """Test structured assertions."""

    def test_add_assertion(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_130")

        result = workflow_add_assertion(
            assertion_type="file_exists",
            definition={"path": "src/auth.ts", "must_contain": "export"},
            step_id="1.2",
            task_id="TASK_TEST_130"
        )

        assert result["success"] is True
        assert result["assertion"]["id"] == "A001"
        assert result["assertion"]["status"] == "pending"

    def test_verify_assertion_pass(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_131")
        add_result = workflow_add_assertion(
            assertion_type="test_passes",
            definition={"command": "npm test"},
            task_id="TASK_TEST_131"
        )

        result = workflow_verify_assertion(
            assertion_id=add_result["assertion"]["id"],
            result=True,
            message="All tests passed",
            task_id="TASK_TEST_131"
        )

        assert result["success"] is True
        assert result["assertion"]["status"] == "passed"

    def test_verify_assertion_fail(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_132")
        add_result = workflow_add_assertion(
            assertion_type="lint_passes",
            definition={"command": "npm run lint"},
            task_id="TASK_TEST_132"
        )

        result = workflow_verify_assertion(
            assertion_id=add_result["assertion"]["id"],
            result=False,
            message="Lint errors found",
            task_id="TASK_TEST_132"
        )

        assert result["success"] is True
        assert result["assertion"]["status"] == "failed"

    def test_get_assertions_filtered(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_133")
        workflow_add_assertion("file_exists", {"path": "a.ts"}, "1.1", task_id="TASK_TEST_133")
        workflow_add_assertion("file_exists", {"path": "b.ts"}, "1.2", task_id="TASK_TEST_133")
        workflow_add_assertion("test_passes", {"command": "npm test"}, "2.1", task_id="TASK_TEST_133")

        result = workflow_get_assertions(step_id="1.1", task_id="TASK_TEST_133")

        assert result["count"] == 1
        assert result["assertions"][0]["definition"]["path"] == "a.ts"


class TestErrorPatterns:
    """Test error pattern learning."""

    def test_record_error_pattern(self, clean_tasks_dir):
        result = workflow_record_error_pattern(
            error_signature="Cannot find module '@/lib",
            error_type="compile",
            solution="Check tsconfig.json paths - @/ should map to src/",
            tags=["typescript", "path-alias"]
        )

        assert result["success"] is True
        assert result["action"] == "created"
        assert result["pattern"]["times_seen"] == 1

    def test_record_error_pattern_updates_existing(self, clean_tasks_dir):
        workflow_record_error_pattern(
            error_signature="Module not found",
            error_type="compile",
            solution="Check imports"
        )

        result = workflow_record_error_pattern(
            error_signature="Module not found",
            error_type="compile",
            solution="Check imports",
            tags=["imports"]
        )

        assert result["action"] == "updated"
        assert result["pattern"]["times_seen"] == 2

    def test_match_error(self, clean_tasks_dir):
        workflow_record_error_pattern(
            error_signature="Cannot find module '@/lib",
            error_type="compile",
            solution="Check tsconfig paths"
        )

        result = workflow_match_error(
            error_output="Error: Cannot find module '@/lib/utils'. Did you mean to import from 'src/lib/utils'?"
        )

        assert result["count"] >= 1
        assert result["matches"][0]["confidence"] >= 0.5
        assert "tsconfig" in result["matches"][0]["solution"]

    def test_match_error_no_match(self, clean_tasks_dir):
        result = workflow_match_error(
            error_output="Some completely unrelated error that doesn't match anything"
        )

        assert result["count"] == 0


class TestAgentPerformance:
    """Test agent performance tracking."""

    def test_record_concern_outcome(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_150")
        add_result = workflow_add_concern(
            source="skeptic",
            severity="high",
            description="Race condition in auth",
            task_id="TASK_TEST_150"
        )

        result = workflow_record_concern_outcome(
            concern_id=add_result["concern"]["id"],
            outcome="valid",
            notes="Added debounce to fix",
            task_id="TASK_TEST_150"
        )

        assert result["success"] is True
        assert result["concern"]["outcome"]["status"] == "valid"

    def test_record_concern_outcome_false_positive(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_151")
        add_result = workflow_add_concern(
            source="reviewer",
            severity="medium",
            description="Memory leak concern",
            task_id="TASK_TEST_151"
        )

        result = workflow_record_concern_outcome(
            concern_id=add_result["concern"]["id"],
            outcome="false_positive",
            notes="Framework handles cleanup",
            task_id="TASK_TEST_151"
        )

        assert result["success"] is True
        assert result["concern"]["outcome"]["status"] == "false_positive"

    def test_get_agent_performance(self, clean_tasks_dir):
        # Record some performance data
        workflow_initialize(task_id="TASK_TEST_152")
        c1 = workflow_add_concern("skeptic", "high", "Issue 1", task_id="TASK_TEST_152")
        c2 = workflow_add_concern("skeptic", "medium", "Issue 2", task_id="TASK_TEST_152")
        c3 = workflow_add_concern("reviewer", "high", "Issue 3", task_id="TASK_TEST_152")

        workflow_record_concern_outcome(c1["concern"]["id"], "valid", task_id="TASK_TEST_152")
        workflow_record_concern_outcome(c2["concern"]["id"], "false_positive", task_id="TASK_TEST_152")
        workflow_record_concern_outcome(c3["concern"]["id"], "valid", task_id="TASK_TEST_152")

        result = workflow_get_agent_performance()

        assert "agents" in result
        assert result["total_concerns"] == 3


class TestOptionalPhases:
    """Test optional specialized phases."""

    def test_enable_optional_phase(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_160")

        result = workflow_enable_optional_phase(
            phase="security_auditor",
            reason="Task involves authentication",
            task_id="TASK_TEST_160"
        )

        assert result["success"] is True
        assert "security_auditor" in result["optional_phases"]

    def test_enable_optional_phase_invalid(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_161")

        result = workflow_enable_optional_phase(
            phase="invalid_agent",
            task_id="TASK_TEST_161"
        )

        assert result["success"] is False
        assert "Unknown optional phase" in result["error"]

    def test_get_optional_phases(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_162")
        workflow_enable_optional_phase("security_auditor", "Auth task", task_id="TASK_TEST_162")
        workflow_enable_optional_phase("api_guardian", "API changes", task_id="TASK_TEST_162")

        result = workflow_get_optional_phases(task_id="TASK_TEST_162")

        assert "security_auditor" in result["optional_phases"]
        assert "api_guardian" in result["optional_phases"]
        assert "Auth task" in result["reasons"]["security_auditor"]["reason"]


class TestTurboMode:
    """Test turbo workflow mode detection and management."""

    def test_detect_mode_turbo(self, clean_tasks_dir):
        result = workflow_detect_mode("Implement a utility for date formatting")

        assert result["mode"] == "turbo"
        assert result["confidence"] >= 0.7

    def test_detect_mode_turbo_blocked_by_security(self, clean_tasks_dir):
        result = workflow_detect_mode("Implement authentication token refresh")

        assert result["mode"] == "full"
        assert result["confidence"] >= 0.8

    def test_set_mode_turbo(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_200")

        result = workflow_set_mode("turbo", task_id="TASK_TEST_200")

        assert result["success"] is True
        assert result["workflow_mode"]["effective"] == "turbo"
        assert "developer" in result["workflow_mode"]["phases"]
        assert "implementer" in result["workflow_mode"]["phases"]
        assert "technical_writer" in result["workflow_mode"]["phases"]
        assert "architect" not in result["workflow_mode"]["phases"]
        assert "reviewer" not in result["workflow_mode"]["phases"]


class TestCostLongContext:
    """Test long-context pricing for Opus."""

    def test_cost_long_context_pricing(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_210")

        result = workflow_record_cost(
            agent="architect",
            model="opus",
            input_tokens=250000,  # >200K triggers long-context pricing
            output_tokens=5000,
            task_id="TASK_TEST_210"
        )

        assert result["success"] is True
        # Long-context: $10/M input, $37.50/M output
        expected_input_cost = (250000 / 1_000_000) * 10.00  # $2.50
        expected_output_cost = (5000 / 1_000_000) * 37.50   # $0.1875
        assert abs(result["entry"]["input_cost"] - expected_input_cost) < 0.01
        assert abs(result["entry"]["output_cost"] - expected_output_cost) < 0.01

    def test_cost_normal_context_pricing(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_211")

        result = workflow_record_cost(
            agent="developer",
            model="opus",
            input_tokens=100000,  # <=200K uses standard pricing
            output_tokens=5000,
            task_id="TASK_TEST_211"
        )

        assert result["success"] is True
        # Standard: $5/M input, $25/M output
        expected_input_cost = (100000 / 1_000_000) * 5.00   # $0.50
        expected_output_cost = (5000 / 1_000_000) * 25.00   # $0.125
        assert abs(result["entry"]["input_cost"] - expected_input_cost) < 0.01
        assert abs(result["entry"]["output_cost"] - expected_output_cost) < 0.01


class TestEffortLevels:
    """Test effort level recommendations per mode."""

    def test_effort_full_mode_architect(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_220")
        workflow_set_mode("full", task_id="TASK_TEST_220")

        result = workflow_get_effort_level("architect", task_id="TASK_TEST_220")

        assert result["effort"] == "max"
        assert result["mode"] == "full"

    def test_effort_turbo_mode_developer(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_221")
        workflow_set_mode("turbo", task_id="TASK_TEST_221")

        result = workflow_get_effort_level("developer", task_id="TASK_TEST_221")

        assert result["effort"] == "max"
        assert result["mode"] == "turbo"

    def test_effort_minimal_mode_developer(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_222")
        workflow_set_mode("minimal", task_id="TASK_TEST_222")

        result = workflow_get_effort_level("developer", task_id="TASK_TEST_222")

        assert result["effort"] == "medium"
        assert result["mode"] == "minimal"

    def test_effort_fast_mode_technical_writer(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_223")
        workflow_set_mode("fast", task_id="TASK_TEST_223")

        result = workflow_get_effort_level("technical_writer", task_id="TASK_TEST_223")

        assert result["effort"] == "medium"
        assert result["mode"] == "fast"

    def test_effort_default_no_task(self, clean_tasks_dir):
        result = workflow_get_effort_level("architect", task_id="NONEXISTENT")

        assert result["effort"] == "high"


class TestCompactionCost:
    """Test compaction token cost tracking."""

    def test_cost_with_compaction_tokens(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_230")

        result = workflow_record_cost(
            agent="architect",
            model="opus",
            input_tokens=100000,
            output_tokens=5000,
            compaction_tokens=15000,
            task_id="TASK_TEST_230"
        )

        assert result["success"] is True
        assert result["entry"]["compaction_tokens"] == 15000
        # Compaction cost: haiku output rate ($4/M)
        expected_compaction_cost = (15000 / 1_000_000) * 4.00  # $0.06
        assert abs(result["entry"]["compaction_cost"] - expected_compaction_cost) < 0.001
        # Total should include compaction
        expected_input_cost = (100000 / 1_000_000) * 5.00
        expected_output_cost = (5000 / 1_000_000) * 25.00
        expected_total = expected_input_cost + expected_output_cost + expected_compaction_cost
        assert abs(result["entry"]["total_cost"] - expected_total) < 0.001

    def test_cost_without_compaction_tokens(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_231")

        result = workflow_record_cost(
            agent="developer",
            model="opus",
            input_tokens=50000,
            output_tokens=3000,
            task_id="TASK_TEST_231"
        )

        assert result["success"] is True
        assert result["entry"]["compaction_tokens"] == 0
        assert result["entry"]["compaction_cost"] == 0

    def test_compaction_tokens_in_totals(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_232")

        workflow_record_cost(
            agent="architect", model="opus",
            input_tokens=100000, output_tokens=5000,
            compaction_tokens=10000, task_id="TASK_TEST_232"
        )
        workflow_record_cost(
            agent="developer", model="opus",
            input_tokens=80000, output_tokens=4000,
            compaction_tokens=5000, task_id="TASK_TEST_232"
        )

        summary = workflow_get_cost_summary(task_id="TASK_TEST_232")
        assert summary["totals"]["compaction_tokens"] == 15000


class TestAgentTeamConfig:
    """Test agent team configuration retrieval."""

    def _mock_config(self, agent_teams=None):
        """Return a mock config_get_effective that returns the given agent_teams config."""
        from unittest.mock import patch
        config = {"agent_teams": agent_teams} if agent_teams else {}
        return patch(
            "agentic_workflow_server.config_tools.config_get_effective",
            return_value={"config": config}
        )

    def test_get_parallel_review_default_disabled(self, clean_tasks_dir):
        with self._mock_config():
            result = workflow_get_agent_team_config("parallel_review")

        assert result["enabled"] is False
        assert result["feature"] == "parallel_review"

    def test_get_parallel_implementation_default_disabled(self, clean_tasks_dir):
        with self._mock_config():
            result = workflow_get_agent_team_config("parallel_implementation")

        assert result["enabled"] is False
        assert result["feature"] == "parallel_implementation"

    def test_unknown_feature_returns_error(self, clean_tasks_dir):
        result = workflow_get_agent_team_config("nonexistent_feature")

        assert result["enabled"] is False
        assert "error" in result
        assert "Unknown agent team feature" in result["error"]

    def test_parallel_review_enabled(self, clean_tasks_dir):
        teams = {"enabled": True, "parallel_review": {"enabled": True, "delegate_mode": True}}
        with self._mock_config(teams):
            result = workflow_get_agent_team_config("parallel_review")

        assert result["enabled"] is True
        assert result["settings"]["delegate_mode"] is True


class TestWorktreeSupport:
    """Test git worktree state tracking."""

    def test_default_state_has_worktree_none(self, clean_tasks_dir):
        result = workflow_initialize(task_id="TASK_TEST_WT_001")
        assert result["success"] is True

        state_file = clean_tasks_dir / "TASK_TEST_WT_001" / "state.json"
        with open(state_file) as f:
            state = json.load(f)
        assert state["worktree"] is None

    def test_create_worktree_records_state(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_WT_002")
        result = workflow_create_worktree(task_id="TASK_TEST_WT_002")

        assert result["success"] is True
        assert result["worktree"]["status"] == "active"
        assert "crew/" in result["worktree"]["branch"]
        assert result["worktree"]["base_branch"] == "main"

    def test_create_worktree_returns_git_commands(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_WT_003")
        result = workflow_create_worktree(task_id="TASK_TEST_WT_003")

        assert "git_commands" in result
        assert len(result["git_commands"]) == 1
        assert "git worktree add" in result["git_commands"][0]

    def test_create_worktree_custom_base_path(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_WT_004")
        result = workflow_create_worktree(task_id="TASK_TEST_WT_004", base_path="/tmp/wt")

        assert result["success"] is True
        assert result["worktree"]["path"] == "/tmp/wt/TASK_TEST_WT_004"

    def test_create_worktree_rejects_duplicates(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_WT_005")
        workflow_create_worktree(task_id="TASK_TEST_WT_005")
        result = workflow_create_worktree(task_id="TASK_TEST_WT_005")

        assert result["success"] is False
        assert "already exists" in result["error"]

    def test_get_worktree_info_with_worktree(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_WT_006")
        workflow_create_worktree(task_id="TASK_TEST_WT_006")
        result = workflow_get_worktree_info(task_id="TASK_TEST_WT_006")

        assert result["has_worktree"] is True
        assert result["worktree"]["status"] == "active"

    def test_get_worktree_info_without_worktree(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_WT_007")
        result = workflow_get_worktree_info(task_id="TASK_TEST_WT_007")

        assert result["has_worktree"] is False
        assert result["worktree"] is None

    def test_cleanup_returns_script_command(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_WT_008")
        workflow_create_worktree(task_id="TASK_TEST_WT_008")
        result = workflow_cleanup_worktree(task_id="TASK_TEST_WT_008")

        assert result["success"] is True
        assert "cleanup_command" in result
        assert "cleanup-worktree.py" in result["cleanup_command"]
        assert "TASK_TEST_WT_008" in result["cleanup_command"]
        # Worktree state is NOT modified (validate-only)
        assert result["worktree"]["status"] == "active"

    def test_cleanup_with_branch_removal(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_WT_009")
        workflow_create_worktree(task_id="TASK_TEST_WT_009")
        result = workflow_cleanup_worktree(task_id="TASK_TEST_WT_009", remove_branch=True)

        assert "--remove-branch" in result["cleanup_command"]

    def test_cleanup_without_branch_removal(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_WT_010")
        workflow_create_worktree(task_id="TASK_TEST_WT_010")
        result = workflow_cleanup_worktree(task_id="TASK_TEST_WT_010", remove_branch=False)

        assert "--remove-branch" not in result["cleanup_command"]

    def test_cleanup_rejects_already_cleaned(self, clean_tasks_dir):
        """Manually mark as cleaned, then verify MCP rejects re-cleanup."""
        workflow_initialize(task_id="TASK_TEST_WT_011")
        workflow_create_worktree(task_id="TASK_TEST_WT_011")
        # Simulate the cleanup script having run (it updates state)
        state_file = clean_tasks_dir / "TASK_TEST_WT_011" / "state.json"
        with open(state_file) as f:
            state = json.load(f)
        state["worktree"]["status"] = "cleaned"
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        result = workflow_cleanup_worktree(task_id="TASK_TEST_WT_011")

        assert result["success"] is False
        assert "already cleaned" in result["error"]

    def test_cleanup_rejects_no_worktree(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_WT_012")
        result = workflow_cleanup_worktree(task_id="TASK_TEST_WT_012")

        assert result["success"] is False
        assert "No worktree configured" in result["error"]

    def test_create_worktree_returns_setup_commands(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_WT_013")
        result = workflow_create_worktree(task_id="TASK_TEST_WT_013")

        assert "setup_commands" in result
        assert len(result["setup_commands"]) >= 1
        # First command is always the .tasks/ symlink
        assert "ln -sfn" in result["setup_commands"][0]
        assert ".tasks" in result["setup_commands"][0]

    def test_create_worktree_claude_copies_settings(self, clean_tasks_dir, tmp_path):
        """When settings file exists, claude host includes python3 patch command."""
        workflow_initialize(task_id="TASK_TEST_WT_014")

        # Create a fake settings file in cwd
        import os
        settings_dir = os.path.join(os.getcwd(), ".claude")
        settings_file = os.path.join(settings_dir, "settings.local.json")
        os.makedirs(settings_dir, exist_ok=True)
        created_settings = False
        try:
            if not os.path.exists(settings_file):
                with open(settings_file, "w") as f:
                    f.write('{"test": true}')
                created_settings = True

            result = workflow_create_worktree(task_id="TASK_TEST_WT_014", ai_host="claude")

            # Should have symlink + python3 settings patch = 2 commands
            assert len(result["setup_commands"]) == 2
            settings_cmd = result["setup_commands"][1]
            assert "python3 -c" in settings_cmd
            assert "additionalDirectories" in settings_cmd
            assert ".tasks" in settings_cmd
        finally:
            if created_settings and os.path.exists(settings_file):
                os.remove(settings_file)

    def test_create_worktree_gemini_no_settings_copy(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_WT_015")
        result = workflow_create_worktree(task_id="TASK_TEST_WT_015", ai_host="gemini")

        # Only the .tasks/ symlink, no settings copy
        assert len(result["setup_commands"]) == 1
        assert "ln -sfn" in result["setup_commands"][0]

    def test_create_worktree_copilot_no_settings_copy(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_WT_016")
        result = workflow_create_worktree(task_id="TASK_TEST_WT_016", ai_host="copilot")

        # Only the .tasks/ symlink, no settings copy
        assert len(result["setup_commands"]) == 1
        assert "ln -sfn" in result["setup_commands"][0]

    def test_create_worktree_default_ai_host(self, clean_tasks_dir):
        """Backwards compat: no ai_host param defaults to claude."""
        workflow_initialize(task_id="TASK_TEST_WT_017")
        result = workflow_create_worktree(task_id="TASK_TEST_WT_017")

        assert result["success"] is True
        # setup_commands should exist regardless
        assert "setup_commands" in result


class TestAutoLaunch:
    """Test auto-launch terminal command generation for worktree sessions."""

    def _setup_worktree_task(self, clean_tasks_dir, task_id):
        """Helper: initialize a task and create a worktree."""
        workflow_initialize(task_id=task_id)
        workflow_create_worktree(task_id=task_id)

    def test_tmux_launch(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_AL_001")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_AL_001",
            terminal_env="tmux",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
        )

        assert result["success"] is True
        assert len(result["launch_commands"]) == 2
        assert "tmux new-window" in result["launch_commands"][0]
        assert "TASK_TEST_AL_001" in result["launch_commands"][0]
        assert "tmux set-option" in result["launch_commands"][1]
        assert "window-style" in result["launch_commands"][1]
        assert result["color_scheme"] is not None
        assert result["warnings"] == []

    def test_windows_terminal_launch(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_AL_002")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_AL_002",
            terminal_env="windows_terminal",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
        )

        assert result["success"] is True
        assert len(result["launch_commands"]) == 1
        cmd = result["launch_commands"][0]
        assert "wt.exe new-tab" in cmd
        assert "--tabColor" in cmd
        assert "--colorScheme" in cmd
        assert "wsl.exe --cd" in cmd
        assert "bash -lic" in cmd
        assert "--prompt" not in cmd
        assert result["color_scheme"] is not None
        assert result["warnings"] == []

    def test_macos_launch(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_AL_003")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_AL_003",
            terminal_env="macos",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
        )

        assert result["success"] is True
        assert len(result["launch_commands"]) == 1
        assert "osascript" in result["launch_commands"][0]
        assert "Terminal" in result["launch_commands"][0]
        assert result["warnings"] == []

    def test_linux_generic_returns_warning(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_AL_004")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_AL_004",
            terminal_env="linux_generic",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
        )

        assert result["success"] is True
        assert result["launch_commands"] == []
        assert len(result["warnings"]) == 1
        assert "Cannot reliably open" in result["warnings"][0]

    def test_gemini_host(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_AL_005")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_AL_005",
            terminal_env="tmux",
            ai_host="gemini",
            main_repo_path="/home/user/myrepo",
        )

        assert result["success"] is True
        cmd = result["launch_commands"][0]
        assert "gemini -i" in cmd
        assert result["warnings"] == []

    def test_copilot_host(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_AL_006")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_AL_006",
            terminal_env="tmux",
            ai_host="copilot",
            main_repo_path="/home/user/myrepo",
        )

        assert result["success"] is True
        cmd = result["launch_commands"][0]
        assert "copilot" in cmd
        assert "gh copilot" not in cmd
        # Copilot CLI doesn't support prompt args — prompt should not be in command
        assert result["resume_prompt"] not in cmd
        assert any("does not support auto-sending" in w for w in result["warnings"])

    def test_no_worktree_returns_error(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_AL_007")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_AL_007",
            terminal_env="tmux",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
        )

        assert result["success"] is False
        assert "No worktree configured" in result["error"]

    def test_launch_records_metadata(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_AL_008")
        workflow_get_launch_command(
            task_id="TASK_TEST_AL_008",
            terminal_env="tmux",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
        )

        # Verify metadata was saved to state
        info = workflow_get_worktree_info(task_id="TASK_TEST_AL_008")
        assert info["worktree"]["launch"] is not None
        assert info["worktree"]["launch"]["terminal_env"] == "tmux"
        assert info["worktree"]["launch"]["ai_host"] == "claude"
        assert "launched_at" in info["worktree"]["launch"]

    def test_resume_prompt_contains_task_id(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_AL_009")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_AL_009",
            terminal_env="tmux",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
        )

        assert "TASK_TEST_AL_009" in result["resume_prompt"]
        assert "/crew resume" in result["resume_prompt"]

    def test_cleaned_worktree_returns_error(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_AL_010")
        # Simulate cleanup script having run
        state_file = clean_tasks_dir / "TASK_TEST_AL_010" / "state.json"
        with open(state_file) as f:
            state = json.load(f)
        state["worktree"]["status"] = "cleaned"
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        result = workflow_get_launch_command(
            task_id="TASK_TEST_AL_010",
            terminal_env="tmux",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
        )

        assert result["success"] is False
        assert "not active" in result["error"]

    def test_nonexistent_task_returns_error(self, clean_tasks_dir):
        result = workflow_get_launch_command(
            task_id="TASK_NONEXISTENT",
            terminal_env="tmux",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
        )

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_resume_prompt_claude_slash_syntax(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_AL_011")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_AL_011",
            terminal_env="tmux",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
        )

        assert "/crew resume TASK_TEST_AL_011" in result["resume_prompt"]
        assert "@crew-resume" not in result["resume_prompt"]

    def test_resume_prompt_gemini_at_syntax(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_AL_012")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_AL_012",
            terminal_env="tmux",
            ai_host="gemini",
            main_repo_path="/home/user/myrepo",
        )

        assert "@crew-resume TASK_TEST_AL_012" in result["resume_prompt"]
        assert "/crew resume" not in result["resume_prompt"]

    def test_resume_prompt_copilot_at_syntax(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_AL_013")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_AL_013",
            terminal_env="tmux",
            ai_host="copilot",
            main_repo_path="/home/user/myrepo",
        )

        assert "@crew-resume TASK_TEST_AL_013" in result["resume_prompt"]
        assert "/crew resume" not in result["resume_prompt"]


class TestLaunchMode:
    """Test terminal_launch_mode setting (window vs tab)."""

    def _setup_worktree_task(self, clean_tasks_dir, task_id):
        workflow_initialize(task_id=task_id)
        workflow_create_worktree(task_id=task_id)

    def test_windows_terminal_window_mode(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_LM_001")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_LM_001",
            terminal_env="windows_terminal",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
            launch_mode="window",
        )

        assert result["success"] is True
        cmd = result["launch_commands"][0]
        assert "wt.exe new-window" in cmd
        assert "wt.exe new-tab" not in cmd
        assert "--tabColor" not in cmd
        assert "--colorScheme" in cmd

    def test_windows_terminal_tab_mode(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_LM_002")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_LM_002",
            terminal_env="windows_terminal",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
            launch_mode="tab",
        )

        assert result["success"] is True
        cmd = result["launch_commands"][0]
        assert "wt.exe new-tab" in cmd
        assert "--tabColor" in cmd

    def test_windows_terminal_auto_defaults_to_tab(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_LM_003")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_LM_003",
            terminal_env="windows_terminal",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
            launch_mode="auto",
        )

        assert result["success"] is True
        cmd = result["launch_commands"][0]
        assert "wt.exe new-tab" in cmd

    def test_tmux_ignores_tab_mode(self, clean_tasks_dir):
        """tmux always uses new-window regardless of launch_mode."""
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_LM_004")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_LM_004",
            terminal_env="tmux",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
            launch_mode="tab",
        )

        assert result["success"] is True
        assert "tmux new-window" in result["launch_commands"][0]

    def test_tmux_auto_defaults_to_window(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_LM_005")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_LM_005",
            terminal_env="tmux",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
            launch_mode="auto",
        )

        assert result["success"] is True
        assert "tmux new-window" in result["launch_commands"][0]

    def test_macos_ignores_tab_mode(self, clean_tasks_dir):
        """macOS Terminal always opens a window regardless of launch_mode."""
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_LM_006")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_LM_006",
            terminal_env="macos",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
            launch_mode="tab",
        )

        assert result["success"] is True
        assert "osascript" in result["launch_commands"][0]

    def test_launch_mode_recorded_in_metadata(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_LM_007")
        workflow_get_launch_command(
            task_id="TASK_TEST_LM_007",
            terminal_env="windows_terminal",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
            launch_mode="window",
        )

        info = workflow_get_worktree_info(task_id="TASK_TEST_LM_007")
        assert info["worktree"]["launch"]["launch_mode"] == "window"

    def test_invalid_launch_mode_falls_back_to_auto(self, clean_tasks_dir):
        self._setup_worktree_task(clean_tasks_dir, "TASK_TEST_LM_008")
        result = workflow_get_launch_command(
            task_id="TASK_TEST_LM_008",
            terminal_env="windows_terminal",
            ai_host="claude",
            main_repo_path="/home/user/myrepo",
            launch_mode="invalid",
        )

        assert result["success"] is True
        # Should fall back to auto → tab for windows_terminal
        cmd = result["launch_commands"][0]
        assert "wt.exe new-tab" in cmd


class TestBuildResumePrompt:
    """Unit tests for _build_resume_prompt helper."""

    def test_claude_uses_slash_syntax(self):
        prompt = _build_resume_prompt("TASK_001", "/repo/.tasks/TASK_001", "claude")
        assert "/crew resume TASK_001" in prompt

    def test_gemini_uses_at_syntax(self):
        prompt = _build_resume_prompt("TASK_001", "/repo/.tasks/TASK_001", "gemini")
        assert "@crew-resume TASK_001" in prompt

    def test_copilot_uses_at_syntax(self):
        prompt = _build_resume_prompt("TASK_001", "/repo/.tasks/TASK_001", "copilot")
        assert "@crew-resume TASK_001" in prompt

    def test_default_host_is_claude(self):
        prompt = _build_resume_prompt("TASK_001", "/repo/.tasks/TASK_001")
        assert "/crew resume TASK_001" in prompt

    def test_warns_against_creating_tasks_dir(self):
        prompt = _build_resume_prompt("TASK_001", "/repo/.tasks/TASK_001", "claude")
        assert "DO NOT create" in prompt
        assert ".tasks/" in prompt

    def test_includes_absolute_path(self):
        prompt = _build_resume_prompt("TASK_001", "/repo/.tasks/TASK_001", "claude")
        assert "/repo/.tasks/TASK_001" in prompt
        assert "absolute path" in prompt


class TestListTasksWorktree:
    """Test list_tasks() includes worktree metadata."""

    def test_list_tasks_without_worktree(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_LT_001")
        tasks = list_tasks()
        task = next(t for t in tasks if t["task_id"] == "TASK_TEST_LT_001")

        assert task["worktree"] is None

    def test_list_tasks_with_active_worktree(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_LT_002")
        workflow_create_worktree(task_id="TASK_TEST_LT_002")
        tasks = list_tasks()
        task = next(t for t in tasks if t["task_id"] == "TASK_TEST_LT_002")

        assert task["worktree"] is not None
        assert task["worktree"]["status"] == "active"
        assert task["worktree"]["branch"] is not None
        assert task["worktree"]["path"] is not None
        assert task["worktree"]["action"] == "resume"

    def test_list_tasks_complete_with_active_worktree_suggests_cleanup(self, clean_tasks_dir):
        """Completed task with active worktree should suggest cleanup."""
        workflow_initialize(task_id="TASK_TEST_LT_003")
        workflow_create_worktree(task_id="TASK_TEST_LT_003")

        # Complete all required phases to mark as complete
        for phase in PHASE_ORDER:
            workflow_transition(to_phase=phase, task_id="TASK_TEST_LT_003")
            workflow_complete_phase(task_id="TASK_TEST_LT_003")

        tasks = list_tasks()
        task = next(t for t in tasks if t["task_id"] == "TASK_TEST_LT_003")

        assert task["is_complete"] is True
        assert task["worktree"]["status"] == "active"
        assert task["worktree"]["action"] == "cleanup"

    def test_list_tasks_cleaned_worktree_shows_done(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_TEST_LT_004")
        workflow_create_worktree(task_id="TASK_TEST_LT_004")
        # Simulate cleanup script having run
        state_file = clean_tasks_dir / "TASK_TEST_LT_004" / "state.json"
        with open(state_file) as f:
            state = json.load(f)
        state["worktree"]["status"] = "cleaned"
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        tasks = list_tasks()
        task = next(t for t in tasks if t["task_id"] == "TASK_TEST_LT_004")

        assert task["worktree"]["status"] == "cleaned"
        assert task["worktree"]["action"] == "done"

    def test_list_tasks_multiple_with_mixed_worktree_states(self, clean_tasks_dir):
        """Multiple tasks with different worktree states."""
        # Task with no worktree
        workflow_initialize(task_id="TASK_TEST_LT_005")

        # Task with active worktree
        workflow_initialize(task_id="TASK_TEST_LT_006")
        workflow_create_worktree(task_id="TASK_TEST_LT_006")

        # Task with cleaned worktree
        workflow_initialize(task_id="TASK_TEST_LT_007")
        workflow_create_worktree(task_id="TASK_TEST_LT_007")
        # Simulate cleanup script having run
        state_file = clean_tasks_dir / "TASK_TEST_LT_007" / "state.json"
        with open(state_file) as f:
            state = json.load(f)
        state["worktree"]["status"] = "cleaned"
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        tasks = list_tasks()
        lt_tasks = {t["task_id"]: t for t in tasks if t["task_id"].startswith("TASK_TEST_LT_00")}

        assert lt_tasks["TASK_TEST_LT_005"]["worktree"] is None
        assert lt_tasks["TASK_TEST_LT_006"]["worktree"]["status"] == "active"
        assert lt_tasks["TASK_TEST_LT_007"]["worktree"]["status"] == "cleaned"


class TestWorktreeRecycling:
    """Test worktree recycling (keep_on_disk + recycle)."""

    def test_find_recyclable_worktree_found(self, clean_tasks_dir, tmp_path):
        """Recyclable worktree with existing directory is found."""
        workflow_initialize(task_id="TASK_TEST_RC_001")
        workflow_create_worktree(task_id="TASK_TEST_RC_001", base_path=str(tmp_path))
        # Create the worktree directory to simulate it existing on disk
        wt_dir = tmp_path / "TASK_TEST_RC_001"
        wt_dir.mkdir(exist_ok=True)
        # Simulate cleanup script marking as recyclable
        state_file = clean_tasks_dir / "TASK_TEST_RC_001" / "state.json"
        with open(state_file) as f:
            state = json.load(f)
        state["worktree"]["status"] = "recyclable"
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        result = _find_recyclable_worktree()
        assert result is not None
        task_dir, state = result
        assert state.get("task_id") == "TASK_TEST_RC_001"
        assert state["worktree"]["status"] == "recyclable"

    def test_find_recyclable_worktree_dir_missing(self, clean_tasks_dir):
        """Recyclable worktree whose directory was removed returns None."""
        workflow_initialize(task_id="TASK_TEST_RC_002")
        workflow_create_worktree(task_id="TASK_TEST_RC_002", base_path="/nonexistent/path")
        # Simulate cleanup script marking as recyclable
        state_file = clean_tasks_dir / "TASK_TEST_RC_002" / "state.json"
        with open(state_file) as f:
            state = json.load(f)
        state["worktree"]["status"] = "recyclable"
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        result = _find_recyclable_worktree()
        assert result is None

    def test_find_recyclable_worktree_none_available(self, clean_tasks_dir):
        """No recyclable worktrees available returns None."""
        workflow_initialize(task_id="TASK_TEST_RC_003")
        workflow_create_worktree(task_id="TASK_TEST_RC_003")
        # Simulate cleanup script marking as cleaned (not recyclable)
        state_file = clean_tasks_dir / "TASK_TEST_RC_003" / "state.json"
        with open(state_file) as f:
            state = json.load(f)
        state["worktree"]["status"] = "cleaned"
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        result = _find_recyclable_worktree()
        assert result is None

    def test_create_worktree_recycle_success(self, clean_tasks_dir, tmp_path):
        """recycle=True with a candidate returns move+checkout commands."""
        # Set up donor
        workflow_initialize(task_id="TASK_TEST_RC_004")
        workflow_create_worktree(task_id="TASK_TEST_RC_004", base_path=str(tmp_path))
        wt_dir = tmp_path / "TASK_TEST_RC_004"
        wt_dir.mkdir(exist_ok=True)
        # Simulate cleanup script marking as recyclable
        state_file = clean_tasks_dir / "TASK_TEST_RC_004" / "state.json"
        with open(state_file) as f:
            state = json.load(f)
        state["worktree"]["status"] = "recyclable"
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        # Create new task and recycle
        workflow_initialize(task_id="TASK_TEST_RC_005")
        result = workflow_create_worktree(
            task_id="TASK_TEST_RC_005",
            base_path=str(tmp_path),
            recycle=True
        )

        assert result["success"] is True
        assert result.get("recycled_from") == "TASK_TEST_RC_004"
        assert "git worktree move" in result["git_commands"][0]
        assert "checkout" in result["git_commands"][1]
        assert result["worktree"]["status"] == "active"
        assert result["worktree"].get("recycled_from") == "TASK_TEST_RC_004"

    def test_create_worktree_recycle_fallback(self, clean_tasks_dir):
        """recycle=True with no candidate falls back to normal creation."""
        workflow_initialize(task_id="TASK_TEST_RC_006")
        result = workflow_create_worktree(
            task_id="TASK_TEST_RC_006",
            recycle=True
        )

        assert result["success"] is True
        assert result.get("recycled_from") is None
        assert "git worktree add" in result["git_commands"][0]

    def test_create_worktree_recycle_updates_donor(self, clean_tasks_dir, tmp_path):
        """Donor state gets updated to 'recycled' after recycling."""
        workflow_initialize(task_id="TASK_TEST_RC_007")
        workflow_create_worktree(task_id="TASK_TEST_RC_007", base_path=str(tmp_path))
        wt_dir = tmp_path / "TASK_TEST_RC_007"
        wt_dir.mkdir(exist_ok=True)
        # Simulate cleanup script marking as recyclable
        state_file = clean_tasks_dir / "TASK_TEST_RC_007" / "state.json"
        with open(state_file) as f:
            state = json.load(f)
        state["worktree"]["status"] = "recyclable"
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        workflow_initialize(task_id="TASK_TEST_RC_008")
        workflow_create_worktree(
            task_id="TASK_TEST_RC_008",
            base_path=str(tmp_path),
            recycle=True
        )

        # Check donor state
        donor_info = workflow_get_worktree_info(task_id="TASK_TEST_RC_007")
        assert donor_info["worktree"]["status"] == "recycled"
        assert donor_info["worktree"].get("recycled_to") == "TASK_TEST_RC_008"

    def test_cleanup_worktree_keep_on_disk(self, clean_tasks_dir):
        """keep_on_disk=True returns script command with --keep-on-disk flag."""
        workflow_initialize(task_id="TASK_TEST_RC_009")
        workflow_create_worktree(task_id="TASK_TEST_RC_009")
        result = workflow_cleanup_worktree(task_id="TASK_TEST_RC_009", keep_on_disk=True)

        assert result["success"] is True
        assert "--keep-on-disk" in result["cleanup_command"]
        # Validate-only: state not modified
        assert result["worktree"]["status"] == "active"

    def test_cleanup_worktree_normal_unchanged(self, clean_tasks_dir):
        """Normal cleanup (keep_on_disk=False) returns script command without --keep-on-disk."""
        workflow_initialize(task_id="TASK_TEST_RC_010")
        workflow_create_worktree(task_id="TASK_TEST_RC_010")
        result = workflow_cleanup_worktree(task_id="TASK_TEST_RC_010", keep_on_disk=False)

        assert result["success"] is True
        assert "--keep-on-disk" not in result["cleanup_command"]
        assert "cleanup-worktree.py" in result["cleanup_command"]

    def test_cleanup_rejects_recyclable(self, clean_tasks_dir):
        """Can't clean up an already recyclable worktree."""
        workflow_initialize(task_id="TASK_TEST_RC_011")
        workflow_create_worktree(task_id="TASK_TEST_RC_011")
        # Simulate script having set status to recyclable
        state_file = clean_tasks_dir / "TASK_TEST_RC_011" / "state.json"
        with open(state_file) as f:
            state = json.load(f)
        state["worktree"]["status"] = "recyclable"
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        result = workflow_cleanup_worktree(task_id="TASK_TEST_RC_011")

        assert result["success"] is False
        assert "already cleaned" in result["error"]

    def test_list_tasks_recyclable_worktree(self, clean_tasks_dir):
        """list_tasks shows recyclable status and action."""
        workflow_initialize(task_id="TASK_TEST_RC_012")
        workflow_create_worktree(task_id="TASK_TEST_RC_012")
        # Simulate cleanup script marking as recyclable
        state_file = clean_tasks_dir / "TASK_TEST_RC_012" / "state.json"
        with open(state_file) as f:
            state = json.load(f)
        state["worktree"]["status"] = "recyclable"
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        tasks = list_tasks()
        task = next(t for t in tasks if t["task_id"] == "TASK_TEST_RC_012")
        assert task["worktree"]["status"] == "recyclable"
        assert task["worktree"]["action"] == "recyclable"


class TestWSLDetection:
    """Test WSL detection and worktree WSL-specific behavior."""

    def test_is_wsl_false_on_linux(self):
        """_is_wsl returns False when /proc/version has no 'microsoft'."""
        from unittest.mock import mock_open, patch
        m = mock_open(read_data="Linux version 5.15.0-generic (buildd@lgw01) (gcc 11.2.0)")
        with patch("builtins.open", m):
            assert _is_wsl() is False

    def test_is_wsl_true_on_wsl(self):
        """_is_wsl returns True when /proc/version contains 'microsoft'."""
        from unittest.mock import mock_open, patch
        m = mock_open(read_data="Linux version 5.15.90.1-microsoft-standard-WSL2")
        with patch("builtins.open", m):
            assert _is_wsl() is True

    def test_create_worktree_wsl_warning(self, clean_tasks_dir):
        """WSL + /mnt/ cwd produces a warning in the result."""
        from unittest.mock import patch
        workflow_initialize(task_id="TASK_TEST_WSL_001")
        with patch("agentic_workflow_server.state_tools._is_wsl", return_value=True), \
             patch("agentic_workflow_server.state_tools.Path") as mock_path:
            # Make cwd look like /mnt/c/git/repo
            mock_cwd = mock_path.cwd.return_value
            mock_cwd.name = "repo"
            mock_cwd.resolve.return_value = type("P", (), {"__str__": lambda s: "/mnt/c/git/repo"})()
            mock_cwd.__truediv__ = lambda s, k: clean_tasks_dir.parent / k if k == ".tasks" else type("P", (), {"__str__": lambda s2: f"/mnt/c/git/repo/{k}"})()
            result = workflow_create_worktree(task_id="TASK_TEST_WSL_001")
        assert result["success"] is True
        assert len(result["warnings"]) > 0
        assert "WSL" in result["warnings"][0]
        assert result["wsl_use_native_commands"] is True

    def test_create_worktree_no_warning_home_path(self, clean_tasks_dir):
        """WSL + /home/ base_path produces no WSL warnings."""
        from unittest.mock import patch
        workflow_initialize(task_id="TASK_TEST_WSL_002")
        with patch("agentic_workflow_server.state_tools._is_wsl", return_value=True), \
             patch("agentic_workflow_server.state_tools.Path") as mock_path:
            mock_cwd = mock_path.cwd.return_value
            mock_cwd.name = "repo"
            mock_cwd.resolve.return_value = type("P", (), {"__str__": lambda s: "/home/user/repo"})()
            mock_cwd.__truediv__ = lambda s, k: clean_tasks_dir.parent / k if k == ".tasks" else type("P", (), {"__str__": lambda s2: f"/home/user/repo/{k}"})()
            result = workflow_create_worktree(task_id="TASK_TEST_WSL_002", base_path="/home/user/worktrees")
        assert result["success"] is True
        assert result["warnings"] == []
        assert result["wsl_use_native_commands"] is False

    def test_create_worktree_wsl_use_native_commands_flag(self, clean_tasks_dir):
        """WSL + /mnt/ path sets wsl_use_native_commands to True."""
        from unittest.mock import patch
        workflow_initialize(task_id="TASK_TEST_WSL_003")
        with patch("agentic_workflow_server.state_tools._is_wsl", return_value=True), \
             patch("agentic_workflow_server.state_tools.Path") as mock_path:
            mock_cwd = mock_path.cwd.return_value
            mock_cwd.name = "repo"
            mock_cwd.resolve.return_value = type("P", (), {"__str__": lambda s: "/mnt/c/git/repo"})()
            mock_cwd.__truediv__ = lambda s, k: clean_tasks_dir.parent / k if k == ".tasks" else type("P", (), {"__str__": lambda s2: f"/mnt/c/git/repo/{k}"})()
            result = workflow_create_worktree(task_id="TASK_TEST_WSL_003")
        assert result["wsl_use_native_commands"] is True

    def test_create_worktree_wsl_native_path_override(self, clean_tasks_dir):
        """When wsl_native_path is configured, it overrides base_path."""
        from unittest.mock import patch
        workflow_initialize(task_id="TASK_TEST_WSL_004")
        mock_config = {
            "config": {
                "worktree": {"wsl_native_path": "/home/testuser/{repo_name}-worktrees"}
            }
        }
        with patch("agentic_workflow_server.state_tools._is_wsl", return_value=True), \
             patch("agentic_workflow_server.config_tools.config_get_effective", return_value=mock_config), \
             patch("agentic_workflow_server.state_tools.Path") as mock_path:
            mock_cwd = mock_path.cwd.return_value
            mock_cwd.name = "myrepo"
            mock_cwd.resolve.return_value = type("P", (), {"__str__": lambda s: "/home/testuser/myrepo"})()
            mock_cwd.__truediv__ = lambda s, k: clean_tasks_dir.parent / k if k == ".tasks" else type("P", (), {"__str__": lambda s2: f"/home/testuser/myrepo/{k}"})()
            result = workflow_create_worktree(task_id="TASK_TEST_WSL_004")
        assert result["success"] is True
        assert result["worktree"]["path"] == "/home/testuser/myrepo-worktrees/TASK_TEST_WSL_004"
        # Path is under /home/ so no WSL warning
        assert result["warnings"] == []
        assert result["wsl_use_native_commands"] is False


class TestFixPathsCommands:
    """Test fix_paths_commands generation for WSL worktrees."""

    def test_wsl_mnt_worktree_has_fix_paths_commands(self, clean_tasks_dir):
        """WSL + /mnt/ worktree returns fix_paths_commands with script invocation."""
        from unittest.mock import patch
        workflow_initialize(task_id="TASK_TEST_FP_001")
        with patch("agentic_workflow_server.state_tools._is_wsl", return_value=True), \
             patch("agentic_workflow_server.state_tools.Path") as mock_path:
            mock_cwd = mock_path.cwd.return_value
            mock_cwd.name = "repo"
            mock_cwd.resolve.return_value = type("P", (), {"__str__": lambda s: "/mnt/c/git/repo"})()
            mock_cwd.__truediv__ = lambda s, k: clean_tasks_dir.parent / k if k == ".tasks" else type("P", (), {"__str__": lambda s2: f"/mnt/c/git/repo/{k}"})()
            result = workflow_create_worktree(task_id="TASK_TEST_FP_001")
        assert result["success"] is True
        cmds = result["fix_paths_commands"]
        assert len(cmds) == 1
        assert "fix-worktree-paths.py" in cmds[0]
        assert "TASK_TEST_FP_001" in cmds[0]

    def test_wsl_mnt_fix_paths_uses_script(self, clean_tasks_dir):
        """WSL + /mnt/ worktree uses fix-worktree-paths.py script."""
        from unittest.mock import patch
        workflow_initialize(task_id="TASK_TEST_FP_002")
        with patch("agentic_workflow_server.state_tools._is_wsl", return_value=True), \
             patch("agentic_workflow_server.state_tools.Path") as mock_path:
            mock_cwd = mock_path.cwd.return_value
            mock_cwd.name = "repo"
            mock_cwd.resolve.return_value = type("P", (), {"__str__": lambda s: "/mnt/c/git/repo"})()
            mock_cwd.__truediv__ = lambda s, k: clean_tasks_dir.parent / k if k == ".tasks" else type("P", (), {"__str__": lambda s2: f"/mnt/c/git/repo/{k}"})()
            result = workflow_create_worktree(task_id="TASK_TEST_FP_002")
        cmds = result["fix_paths_commands"]
        assert len(cmds) == 1
        assert "fix-worktree-paths.py" in cmds[0]
        assert "TASK_TEST_FP_002" in cmds[0]
        # Script path should be absolute (works from any CWD)
        assert cmds[0].startswith("python3 /")

    def test_non_wsl_has_empty_fix_paths(self, clean_tasks_dir):
        """Non-WSL worktree returns empty fix_paths_commands."""
        from unittest.mock import patch
        workflow_initialize(task_id="TASK_TEST_FP_003")
        with patch("agentic_workflow_server.state_tools._is_wsl", return_value=False):
            result = workflow_create_worktree(task_id="TASK_TEST_FP_003")
        assert result["success"] is True
        assert result["fix_paths_commands"] == []

    def test_wsl_home_path_has_empty_fix_paths(self, clean_tasks_dir):
        """WSL + /home/ path returns empty fix_paths_commands (no Windows compat needed)."""
        from unittest.mock import patch
        workflow_initialize(task_id="TASK_TEST_FP_004")
        with patch("agentic_workflow_server.state_tools._is_wsl", return_value=True), \
             patch("agentic_workflow_server.state_tools.Path") as mock_path:
            mock_cwd = mock_path.cwd.return_value
            mock_cwd.name = "repo"
            mock_cwd.resolve.return_value = type("P", (), {"__str__": lambda s: "/home/user/repo"})()
            mock_cwd.__truediv__ = lambda s, k: clean_tasks_dir.parent / k if k == ".tasks" else type("P", (), {"__str__": lambda s2: f"/home/user/repo/{k}"})()
            result = workflow_create_worktree(task_id="TASK_TEST_FP_004", base_path="/home/user/worktrees")
        assert result["success"] is True
        assert result["fix_paths_commands"] == []

    def test_recycled_worktree_has_empty_fix_paths(self, clean_tasks_dir):
        """Recycled worktree returns empty fix_paths_commands."""
        from unittest.mock import patch
        import os
        # Create and mark a worktree as recyclable
        workflow_initialize(task_id="TASK_TEST_FP_005")
        workflow_create_worktree(task_id="TASK_TEST_FP_005")
        # Create the actual worktree directory so _find_recyclable_worktree finds it
        state_dir = clean_tasks_dir / "TASK_TEST_FP_005"
        state = json.load(open(state_dir / "state.json"))
        wt_rel = state["worktree"]["path"]
        wt_abs = os.path.normpath(os.path.join(str(clean_tasks_dir.parent), wt_rel))
        os.makedirs(wt_abs, exist_ok=True)
        # Simulate cleanup script marking as recyclable
        state["worktree"]["status"] = "recyclable"
        with open(state_dir / "state.json", "w") as f:
            json.dump(state, f, indent=2)

        # Now create a new task that recycles
        workflow_initialize(task_id="TASK_TEST_FP_006")
        result = workflow_create_worktree(task_id="TASK_TEST_FP_006", recycle=True)
        assert result["success"] is True
        if "recycled_from" in result:
            # Recycled path always returns empty fix_paths_commands
            assert result["fix_paths_commands"] == []
        else:
            # Recycling fell back to fresh — fix_paths depends on WSL detection
            assert "fix_paths_commands" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
