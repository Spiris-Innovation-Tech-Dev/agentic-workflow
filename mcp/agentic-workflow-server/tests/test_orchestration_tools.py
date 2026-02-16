"""
Tests for Orchestration Tools

Run with: pytest tests/test_orchestration_tools.py -v
"""

import json
import shutil
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentic_workflow_server.orchestration_tools import (
    crew_parse_args,
    crew_init_task,
    crew_apply_config_overrides,
    crew_detect_optional_agents,
    crew_get_next_phase,
    crew_parse_agent_output,
    crew_get_implementation_action,
    crew_format_completion,
    crew_get_resume_state,
    _slugify,
    _generate_branch_name,
    _tokenize,
)
from agentic_workflow_server.state_tools import (
    get_tasks_dir,
    workflow_initialize,
    workflow_transition,
    workflow_complete_phase,
    workflow_set_mode,
    workflow_set_implementation_progress,
    workflow_complete_step,
    _slugify as state_slugify,
    _generate_branch_name as state_generate_branch_name,
)


@pytest.fixture
def clean_tasks_dir():
    """Clean up .tasks directory before and after tests."""
    tasks_dir = get_tasks_dir()

    for pattern in ["TASK_TEST_*", "TASK_ORCH_*"]:
        for d in tasks_dir.glob(pattern):
            if d.is_dir():
                shutil.rmtree(d)

    yield tasks_dir

    for pattern in ["TASK_TEST_*", "TASK_ORCH_*"]:
        for d in tasks_dir.glob(pattern):
            if d.is_dir():
                shutil.rmtree(d)


# ============================================================================
# crew_parse_args tests
# ============================================================================

class TestCrewParseArgs:
    def test_simple_task(self):
        result = crew_parse_args('"Fix typo in README"')
        assert result["action"] == "start"
        assert result["task_description"] == "Fix typo in README"
        assert result["errors"] == []

    def test_task_with_mode(self):
        result = crew_parse_args('--mode turbo "Add logout button"')
        assert result["action"] == "start"
        assert result["options"]["mode"] == "turbo"
        assert result["task_description"] == "Add logout button"

    def test_task_with_loop_mode(self):
        result = crew_parse_args('--loop-mode "Fix all failing tests"')
        assert result["options"]["loop_mode"] is True

    def test_task_with_no_loop(self):
        result = crew_parse_args('--no-loop "Simple task"')
        assert result["options"]["loop_mode"] is False

    def test_task_with_max_iterations(self):
        result = crew_parse_args('--max-iterations 50 "Big refactor"')
        assert result["options"]["max_iterations"] == 50

    def test_task_with_verify(self):
        result = crew_parse_args('--verify tests "Fix tests"')
        assert result["options"]["verify"] == "tests"

    def test_task_with_no_checkpoints(self):
        result = crew_parse_args('--no-checkpoints "Overnight task"')
        assert result["options"]["no_checkpoints"] is True

    def test_task_with_parallel(self):
        result = crew_parse_args('--parallel "Add caching"')
        assert result["options"]["parallel"] is True

    def test_task_with_beads(self):
        result = crew_parse_args('--beads PROJ-42 "Add caching"')
        assert result["options"]["beads"] == "PROJ-42"

    def test_task_with_task_file(self):
        result = crew_parse_args('--task ./tasks/implement-caching.md')
        assert result["options"]["task_file"] == "./tasks/implement-caching.md"

    def test_task_with_config_file(self):
        result = crew_parse_args('--config ./my-config.yaml "Simple task"')
        assert result["options"]["config_file"] == "./my-config.yaml"

    def test_multiple_options(self):
        result = crew_parse_args('--mode fast --loop-mode --no-checkpoints --beads API-42 "Add caching layer"')
        assert result["options"]["mode"] == "fast"
        assert result["options"]["loop_mode"] is True
        assert result["options"]["no_checkpoints"] is True
        assert result["options"]["beads"] == "API-42"
        assert result["task_description"] == "Add caching layer"

    def test_resume_action(self):
        result = crew_parse_args('resume TASK_042')
        assert result["action"] == "resume"
        assert result["task_id"] == "TASK_042"

    def test_status_action(self):
        result = crew_parse_args('status')
        assert result["action"] == "status"

    def test_proceed_action(self):
        result = crew_parse_args('proceed')
        assert result["action"] == "proceed"

    def test_config_action(self):
        result = crew_parse_args('config')
        assert result["action"] == "config"

    def test_ask_action(self):
        result = crew_parse_args('ask architect "Should we use Redis or Memcached?"')
        assert result["action"] == "ask"
        assert result["agent"] == "architect"
        assert result["task_description"] == "Should we use Redis or Memcached?"

    def test_ask_with_context(self):
        result = crew_parse_args('ask reviewer "Review this" --context src/auth/')
        assert result["action"] == "ask"
        assert result["agent"] == "reviewer"
        assert result["options"]["context"] == "src/auth/"

    def test_ask_with_diff(self):
        result = crew_parse_args('ask developer "How to structure?" --diff')
        assert result["options"]["diff"] is True

    def test_invalid_mode(self):
        result = crew_parse_args('--mode invalid "Task"')
        assert len(result["errors"]) > 0
        assert "Invalid mode" in result["errors"][0]

    def test_empty_args(self):
        result = crew_parse_args('')
        assert len(result["errors"]) > 0

    def test_start_prefix(self):
        result = crew_parse_args('start "Add feature"')
        assert result["action"] == "start"
        assert result["task_description"] == "Add feature"

    def test_unknown_option(self):
        result = crew_parse_args('--unknown-flag "Task"')
        assert len(result["errors"]) > 0
        assert "Unknown option" in result["errors"][0]

    def test_options_after_description(self):
        result = crew_parse_args('Add caching --mode fast')
        assert result["task_description"] == "Add caching"
        assert result["options"]["mode"] == "fast"


# ============================================================================
# crew_apply_config_overrides tests
# ============================================================================

class TestCrewApplyConfigOverrides:
    def test_loop_mode_enable(self):
        result = crew_apply_config_overrides({"loop_mode": True})
        assert result["overrides"]["loop_mode"]["enabled"] is True
        assert len(result["applied"]) == 1

    def test_loop_mode_disable(self):
        result = crew_apply_config_overrides({"loop_mode": False})
        assert result["overrides"]["loop_mode"]["enabled"] is False

    def test_max_iterations(self):
        result = crew_apply_config_overrides({"max_iterations": 50})
        assert result["overrides"]["loop_mode"]["max_iterations"]["per_step"] == 50

    def test_verify_method(self):
        result = crew_apply_config_overrides({"verify": "all"})
        assert result["overrides"]["loop_mode"]["verification"]["method"] == "all"

    def test_no_checkpoints(self):
        result = crew_apply_config_overrides({"no_checkpoints": True})
        checkpoints = result["overrides"]["checkpoints"]
        assert checkpoints["planning"]["after_architect"] is False
        assert checkpoints["implementation"]["at_50_percent"] is False
        assert checkpoints["documentation"]["after_technical_writer"] is False

    def test_parallel(self):
        result = crew_apply_config_overrides({"parallel": True})
        assert result["overrides"]["parallelization"]["reviewer_skeptic"]["enabled"] is True

    def test_beads(self):
        result = crew_apply_config_overrides({"beads": "PROJ-42"})
        assert result["overrides"]["beads"]["enabled"] is True
        assert result["overrides"]["beads"]["linked_issue"] == "PROJ-42"

    def test_empty_options(self):
        result = crew_apply_config_overrides({})
        assert result["overrides"] == {}
        assert result["applied"] == []

    def test_multiple_overrides(self):
        result = crew_apply_config_overrides({
            "loop_mode": True,
            "max_iterations": 20,
            "no_checkpoints": True
        })
        assert len(result["applied"]) == 3


# ============================================================================
# crew_detect_optional_agents tests
# ============================================================================

class TestCrewDetectOptionalAgents:
    def test_security_keywords(self):
        result = crew_detect_optional_agents("Add JWT authentication with password hashing")
        assert "security_auditor" in result["enabled"]
        assert "security_auditor" in result["reasons"]

    def test_performance_keywords(self):
        result = crew_detect_optional_agents("Optimize database cache performance")
        assert "performance_analyst" in result["enabled"]

    def test_api_keywords(self):
        result = crew_detect_optional_agents("Add new REST API endpoint")
        assert "api_guardian" in result["enabled"]

    def test_accessibility_keywords(self):
        result = crew_detect_optional_agents("Build new UI component with form validation")
        assert "accessibility_reviewer" in result["enabled"]

    def test_no_matches(self):
        result = crew_detect_optional_agents("Fix typo in README")
        assert result["enabled"] == []
        assert len(result["skipped"]) == 4

    def test_multiple_matches(self):
        result = crew_detect_optional_agents("Add authentication API endpoint with UI form")
        assert "security_auditor" in result["enabled"]
        assert "api_guardian" in result["enabled"]
        assert "accessibility_reviewer" in result["enabled"]


# ============================================================================
# crew_parse_agent_output tests
# ============================================================================

class TestCrewParseAgentOutput:
    def test_parse_docs_needed(self):
        output = '''
        Analysis complete.
        <docs_needed>["docs/api.md", "docs/auth.md"]</docs_needed>
        '''
        result = crew_parse_agent_output("architect", output)
        assert result["extracted"]["docs_needed"] == ["docs/api.md", "docs/auth.md"]
        assert result["has_blocking_issues"] is False

    def test_parse_review_issues(self):
        output = '''
        <review_issues>[{"description": "Missing error handling", "severity": "high"}]</review_issues>
        <recommendation>REVISE</recommendation>
        '''
        result = crew_parse_agent_output("reviewer", output)
        assert len(result["extracted"]["review_issues"]) == 1
        assert result["extracted"]["recommendation"] == "REVISE"
        assert result["has_blocking_issues"] is True

    def test_parse_approve_recommendation(self):
        output = '''
        <recommendation>APPROVE</recommendation>
        '''
        result = crew_parse_agent_output("reviewer", output)
        assert result["extracted"]["recommendation"] == "APPROVE"
        assert result["has_blocking_issues"] is False

    def test_parse_concerns(self):
        output = '''
        <concerns>[{"description": "Race condition possible", "severity": "high"}]</concerns>
        '''
        result = crew_parse_agent_output("skeptic", output)
        assert len(result["extracted"]["concerns"]) == 1
        assert result["has_blocking_issues"] is False

    def test_no_structured_output(self):
        output = "Just some plain text analysis."
        result = crew_parse_agent_output("architect", output)
        assert result["extracted"] == {}
        assert result["has_blocking_issues"] is False

    def test_invalid_json_in_tags(self):
        output = '<docs_needed>[invalid json]</docs_needed>'
        result = crew_parse_agent_output("architect", output)
        assert "docs_needed_parse_error" in result["extracted"]

    def test_string_concerns(self):
        output = '<concerns>["Race condition", "Memory leak"]</concerns>'
        result = crew_parse_agent_output("skeptic", output)
        assert len(result["extracted"]["concerns"]) == 2


# ============================================================================
# Slugify and branch naming tests
# ============================================================================

class TestSlugify:
    def test_basic(self):
        assert _slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        assert _slugify("Add JWT auth!") == "add-jwt-auth"

    def test_underscores(self):
        assert _slugify("my_function_name") == "my-function-name"

    def test_multiple_spaces(self):
        assert _slugify("too   many   spaces") == "too-many-spaces"

    def test_leading_trailing(self):
        assert _slugify("  -hello- ") == "hello"

    def test_empty(self):
        assert _slugify("") == ""


class TestGenerateBranchName:
    def test_linked_issue(self):
        state = {"linked_issue": "PROJ-42"}
        assert _generate_branch_name("TASK_001", state) == "crew/proj-42"

    def test_beads_issue(self):
        state = {"beads_issue": "CACHE-12"}
        assert _generate_branch_name("TASK_001", state) == "crew/cache-12"

    def test_description(self):
        state = {"description": "Add JWT authentication"}
        result = _generate_branch_name("TASK_001", state)
        assert result == "crew/add-jwt-authentication"

    def test_long_description_truncated(self):
        state = {"description": "A" * 100}
        result = _generate_branch_name("TASK_001", state)
        branch_part = result.replace("crew/", "")
        assert len(branch_part) <= 50

    def test_fallback_task_id(self):
        state = {}
        result = _generate_branch_name("TASK_001", state)
        assert result == "crew/task-001"

    def test_linked_issue_priority_over_description(self):
        state = {"linked_issue": "PROJ-42", "description": "Some task"}
        assert _generate_branch_name("TASK_001", state) == "crew/proj-42"


class TestStatToolsSlugifyAndBranch:
    """Test the _slugify and _generate_branch_name added to state_tools.py."""

    def test_slugify(self):
        assert state_slugify("Hello World!") == "hello-world"

    def test_generate_branch_from_linked_issue(self):
        state = {"linked_issue": "API-42"}
        assert state_generate_branch_name("TASK_001", state) == "crew/api-42"

    def test_generate_branch_from_description(self):
        state = {"description": "Add caching layer"}
        assert state_generate_branch_name("TASK_001", state) == "crew/add-caching-layer"

    def test_generate_branch_fallback(self):
        state = {}
        assert state_generate_branch_name("TASK_001", state) == "crew/task-001"


# ============================================================================
# Tokenizer tests
# ============================================================================

class TestTokenize:
    def test_basic(self):
        assert _tokenize("hello world") == ["hello", "world"]

    def test_quoted(self):
        assert _tokenize('"hello world" foo') == ["hello world", "foo"]

    def test_single_quoted(self):
        assert _tokenize("'hello world' foo") == ["hello world", "foo"]

    def test_mixed(self):
        assert _tokenize('--mode fast "Add feature"') == ["--mode", "fast", "Add feature"]

    def test_empty(self):
        assert _tokenize("") == []


# ============================================================================
# crew_init_task tests (requires filesystem)
# ============================================================================

class TestCrewInitTask:
    def test_basic_init(self, clean_tasks_dir):
        result = crew_init_task(
            task_description="Fix typo in README",
            options={"mode": "minimal"}
        )
        assert result["success"] is True
        assert result["task_id"]
        assert result["mode"] == "minimal"

        # Clean up
        task_dir = clean_tasks_dir / result["task_id"]
        if task_dir.exists():
            shutil.rmtree(task_dir)

    def test_init_with_beads(self, clean_tasks_dir):
        result = crew_init_task(
            task_description="Add caching",
            options={"beads": "CACHE-42", "mode": "fast"}
        )
        assert result["success"] is True
        assert result["beads_issue"] == "CACHE-42"

        # Clean up
        task_dir = clean_tasks_dir / result["task_id"]
        if task_dir.exists():
            shutil.rmtree(task_dir)

    def test_init_saves_task_md(self, clean_tasks_dir):
        result = crew_init_task(
            task_description="Add feature X",
            options={"mode": "turbo"}
        )
        task_dir = clean_tasks_dir / result["task_id"]
        assert (task_dir / "task.md").exists()

        # Clean up
        if task_dir.exists():
            shutil.rmtree(task_dir)


# ============================================================================
# crew_get_next_phase tests (requires filesystem)
# ============================================================================

class TestCrewGetNextPhase:
    def test_first_phase_full_mode(self, clean_tasks_dir):
        init = workflow_initialize(task_id="TASK_ORCH_001", description="Test task")
        workflow_set_mode(mode="full", task_id="TASK_ORCH_001")

        result = crew_get_next_phase(task_id="TASK_ORCH_001")
        # Phase is architect (set by initialize), not yet completed
        # Default config has after_architect checkpoint enabled, so this returns checkpoint
        assert result.get("action") in ("spawn_agent", "process_output", "checkpoint")
        # The phase should be architect
        assert result.get("phase") == "architect" or result.get("agent") == "architect"

    def test_next_after_architect(self, clean_tasks_dir):
        init = workflow_initialize(task_id="TASK_ORCH_001B", description="Test task")
        workflow_set_mode(mode="full", task_id="TASK_ORCH_001B")
        workflow_complete_phase(task_id="TASK_ORCH_001B")
        workflow_transition(to_phase="developer", task_id="TASK_ORCH_001B")
        workflow_complete_phase(task_id="TASK_ORCH_001B")

        result = crew_get_next_phase(task_id="TASK_ORCH_001B")
        # Should suggest reviewer next in full mode
        assert result.get("action") in ("spawn_agent", "process_output", "checkpoint")

    def test_complete_when_all_done(self, clean_tasks_dir):
        init = workflow_initialize(task_id="TASK_ORCH_002", description="Test task")
        workflow_set_mode(mode="full", task_id="TASK_ORCH_002")

        # Complete all full mode phases sequentially
        # architect is already set by initialize
        workflow_complete_phase(task_id="TASK_ORCH_002")
        for phase in ["developer", "reviewer", "skeptic", "implementer", "feedback", "technical_writer"]:
            workflow_transition(to_phase=phase, task_id="TASK_ORCH_002")
            workflow_complete_phase(task_id="TASK_ORCH_002")

        result = crew_get_next_phase(task_id="TASK_ORCH_002")
        assert result["action"] == "complete"

    def test_nonexistent_task(self):
        result = crew_get_next_phase(task_id="TASK_NONEXISTENT")
        assert "error" in result


# ============================================================================
# crew_get_implementation_action tests (requires filesystem)
# ============================================================================

class TestCrewGetImplementationAction:
    def test_basic_implement_step(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_ORCH_003", description="Test")
        workflow_set_implementation_progress(total_steps=3, task_id="TASK_ORCH_003")

        result = crew_get_implementation_action(task_id="TASK_ORCH_003")
        assert result["action"] == "implement_step"
        assert result["step_id"] == "step_1"
        assert result["progress_percent"] == 0

    def test_all_steps_complete(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_ORCH_004", description="Test")
        workflow_set_implementation_progress(total_steps=2, task_id="TASK_ORCH_004")
        workflow_complete_step(step_id="step_1", task_id="TASK_ORCH_004")
        workflow_complete_step(step_id="step_2", task_id="TASK_ORCH_004")

        result = crew_get_implementation_action(task_id="TASK_ORCH_004")
        assert result["action"] in ("complete", "checkpoint")

    def test_verification_passed(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_ORCH_005", description="Test")
        workflow_set_implementation_progress(total_steps=3, task_id="TASK_ORCH_005")

        result = crew_get_implementation_action(
            task_id="TASK_ORCH_005",
            last_verification_passed=True
        )
        assert result["action"] == "next_step"

    def test_nonexistent_task(self):
        result = crew_get_implementation_action(task_id="TASK_NONEXISTENT")
        assert "error" in result


# ============================================================================
# crew_format_completion tests (requires filesystem)
# ============================================================================

class TestCrewFormatCompletion:
    def test_basic_completion(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_ORCH_006", description="Add caching layer")
        workflow_set_mode(mode="fast", task_id="TASK_ORCH_006")

        result = crew_format_completion(
            task_id="TASK_ORCH_006",
            files_changed=["src/cache.ts", "src/api.ts"]
        )
        assert result["task_id"] == "TASK_ORCH_006"
        assert "cost_summary" in result
        assert "commit_message" in result
        assert "caching" in result["commit_message"].lower() or "Add caching layer" in result["commit_message"]
        assert result["mode"] == "fast"

    def test_nonexistent_task(self):
        result = crew_format_completion(task_id="TASK_NONEXISTENT")
        assert "error" in result


# ============================================================================
# crew_get_resume_state tests (requires filesystem)
# ============================================================================

class TestCrewGetResumeState:
    def test_basic_resume(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_ORCH_007", description="Test task for resume")
        workflow_set_mode(mode="full", task_id="TASK_ORCH_007")

        result = crew_get_resume_state(task_id="TASK_ORCH_007")
        assert result["task_id"] == "TASK_ORCH_007"
        assert "display_summary" in result
        assert "Test task for resume" in result["display_summary"]
        assert result["mode"] == "full"

    def test_resume_with_progress(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_ORCH_008", description="Implementation task")
        workflow_set_mode(mode="full", task_id="TASK_ORCH_008")
        # Complete architect (set by initialize) and transition through to implementer
        workflow_complete_phase(task_id="TASK_ORCH_008")
        workflow_transition(to_phase="developer", task_id="TASK_ORCH_008")
        workflow_complete_phase(task_id="TASK_ORCH_008")
        workflow_transition(to_phase="reviewer", task_id="TASK_ORCH_008")
        workflow_complete_phase(task_id="TASK_ORCH_008")
        workflow_transition(to_phase="skeptic", task_id="TASK_ORCH_008")
        workflow_complete_phase(task_id="TASK_ORCH_008")
        workflow_transition(to_phase="implementer", task_id="TASK_ORCH_008")
        workflow_set_implementation_progress(total_steps=5, current_step=2, task_id="TASK_ORCH_008")

        result = crew_get_resume_state(task_id="TASK_ORCH_008")
        assert "implementation step" in result["resume_point"]
        assert result["progress_summary"]["total_steps"] == 5

    def test_nonexistent_task(self):
        result = crew_get_resume_state(task_id="TASK_NONEXISTENT")
        assert "error" in result
