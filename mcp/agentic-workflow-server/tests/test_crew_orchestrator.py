"""
Tests for crew_orchestrator.py CLI script.

Tests the orchestrator's subcommands which batch multiple MCP tool calls
into single instant decisions.

Run with: pytest tests/test_crew_orchestrator.py -v
"""

import json
import shutil
import subprocess
import sys
import pytest
from pathlib import Path

# Path to the orchestrator script
SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
ORCHESTRATOR = SCRIPT_DIR / "crew_orchestrator.py"

# Also import MCP tools directly for setup
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentic_workflow_server.state_tools import (
    get_tasks_dir,
    workflow_initialize,
    workflow_transition,
    workflow_complete_phase,
    workflow_set_mode,
    workflow_set_implementation_progress,
    workflow_complete_step,
    find_task_dir,
    _load_state,
)


def run_orchestrator(*args: str) -> dict:
    """Run the orchestrator script and return parsed JSON output."""
    result = subprocess.run(
        [sys.executable, str(ORCHESTRATOR)] + list(args),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0 and not result.stdout:
        raise RuntimeError(f"Orchestrator failed: {result.stderr}")
    return json.loads(result.stdout)


@pytest.fixture
def clean_tasks_dir():
    """Clean up test task directories."""
    tasks_dir = get_tasks_dir()
    prefixes = ["TASK_CO_*", "TASK_ORCH_CO_*"]

    for pattern in prefixes:
        for d in tasks_dir.glob(pattern):
            if d.is_dir():
                shutil.rmtree(d)

    # Clean .active_task if leftover from previous test
    active_file = tasks_dir / ".active_task"
    if active_file.exists():
        active_file.unlink()

    yield tasks_dir

    for pattern in prefixes:
        for d in tasks_dir.glob(pattern):
            if d.is_dir():
                shutil.rmtree(d)

    if active_file.exists():
        active_file.unlink()


# ============================================================================
# init subcommand
# ============================================================================

class TestInitCommand:
    def test_init_start(self, clean_tasks_dir):
        result = run_orchestrator("init", "--args", '"Fix typo in README" --mode minimal')
        assert result["action"] == "start"
        assert result["task_id"]
        assert result["mode"] == "minimal"
        assert "next" in result

        # Clean up
        task_dir = clean_tasks_dir / result["task_id"]
        if task_dir.exists():
            shutil.rmtree(task_dir)

    def test_init_status(self):
        result = run_orchestrator("init", "--args", "status")
        assert result["action"] == "status"

    def test_init_config(self):
        result = run_orchestrator("init", "--args", "config")
        assert result["action"] == "config"

    def test_init_empty_args(self):
        result = run_orchestrator("init", "--args", "")
        assert result.get("error") is True

    def test_init_ask(self):
        result = run_orchestrator("init", "--args", 'ask architect "Should we use Redis?"')
        assert result["action"] == "ask"
        assert result["agent"] == "architect"

    def test_init_resume_missing_task(self):
        result = run_orchestrator("init", "--args", "resume TASK_NONEXISTENT")
        assert result.get("error") is True

    def test_init_with_beads(self, clean_tasks_dir):
        result = run_orchestrator("init", "--args", '--beads PROJ-99 "Add caching"')
        assert result["action"] == "start"
        assert result["beads_issue"] == "PROJ-99"

        task_dir = clean_tasks_dir / result["task_id"]
        if task_dir.exists():
            shutil.rmtree(task_dir)

    def test_init_no_description(self):
        result = run_orchestrator("init", "--args", "--mode fast")
        assert result.get("error") is True


# ============================================================================
# next subcommand
# ============================================================================

class TestNextCommand:
    def test_next_nonexistent(self):
        result = run_orchestrator("next", "--task-id", "TASK_NONEXISTENT")
        assert "error" in result

    def test_next_after_init(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_CO_001", description="Test task")
        workflow_set_mode(mode="minimal", task_id="TASK_CO_001")

        result = run_orchestrator("next", "--task-id", "TASK_CO_001")
        # Should suggest developer (first phase in minimal mode)
        assert result.get("action") in ("spawn_agent", "checkpoint", "process_output")


# ============================================================================
# agent-done subcommand
# ============================================================================

class TestAgentDoneCommand:
    def test_agent_done_basic(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_CO_002", description="Test task")
        workflow_set_mode(mode="minimal", task_id="TASK_CO_002")
        # Transition to developer (first phase in minimal)
        workflow_transition(to_phase="developer", task_id="TASK_CO_002")

        # Create a dummy output file
        task_dir = clean_tasks_dir / "TASK_CO_002"
        output_file = task_dir / "developer.md"
        output_file.write_text("# Developer Plan\nDo the thing.\n")

        result = run_orchestrator(
            "agent-done",
            "--task-id", "TASK_CO_002",
            "--agent", "developer",
            "--output-file", str(output_file),
        )
        assert result["action"] == "agent_done"
        assert result["phase_completed"] is True
        assert "next" in result

    def test_agent_done_with_cost(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_CO_003", description="Test task")
        workflow_set_mode(mode="minimal", task_id="TASK_CO_003")
        workflow_transition(to_phase="developer", task_id="TASK_CO_003")

        result = run_orchestrator(
            "agent-done",
            "--task-id", "TASK_CO_003",
            "--agent", "developer",
            "--input-tokens", "5000",
            "--output-tokens", "2000",
            "--model", "opus",
        )
        assert result["cost_recorded"] is True

    def test_agent_done_with_blocking_issues(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_CO_004", description="Test task")
        workflow_set_mode(mode="full", task_id="TASK_CO_004")
        workflow_complete_phase(task_id="TASK_CO_004")
        workflow_transition(to_phase="developer", task_id="TASK_CO_004")
        workflow_complete_phase(task_id="TASK_CO_004")
        workflow_transition(to_phase="reviewer", task_id="TASK_CO_004")

        # Create output file with blocking issues
        task_dir = clean_tasks_dir / "TASK_CO_004"
        output_file = task_dir / "reviewer.md"
        output_file.write_text(
            '# Review\n<review_issues>[{"description": "Missing tests", "severity": "high"}]</review_issues>\n'
            '<recommendation>REVISE</recommendation>\n'
        )

        result = run_orchestrator(
            "agent-done",
            "--task-id", "TASK_CO_004",
            "--agent", "reviewer",
            "--output-file", str(output_file),
        )
        assert result.get("has_blocking_issues") is True


# ============================================================================
# checkpoint-done subcommand
# ============================================================================

class TestCheckpointDoneCommand:
    def test_approve(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_CO_005", description="Test task")
        workflow_set_mode(mode="full", task_id="TASK_CO_005")

        result = run_orchestrator(
            "checkpoint-done",
            "--task-id", "TASK_CO_005",
            "--decision", "approve",
        )
        assert result["decision"] == "approve"
        assert "next" in result

    def test_revise(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_CO_006", description="Test task")
        workflow_set_mode(mode="full", task_id="TASK_CO_006")
        workflow_complete_phase(task_id="TASK_CO_006")
        workflow_transition(to_phase="developer", task_id="TASK_CO_006")
        workflow_complete_phase(task_id="TASK_CO_006")
        workflow_transition(to_phase="reviewer", task_id="TASK_CO_006")

        result = run_orchestrator(
            "checkpoint-done",
            "--task-id", "TASK_CO_006",
            "--decision", "revise",
            "--notes", "Need more error handling",
        )
        assert result["decision"] == "revise"


# ============================================================================
# impl-action subcommand
# ============================================================================

class TestImplActionCommand:
    def test_basic_implement(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_CO_007", description="Test task")
        workflow_set_implementation_progress(total_steps=3, task_id="TASK_CO_007")

        result = run_orchestrator("impl-action", "--task-id", "TASK_CO_007")
        assert result["action"] == "implement_step"
        assert result["step_id"] == "step_1"

    def test_verification_passed(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_CO_008", description="Test task")
        workflow_set_implementation_progress(total_steps=3, task_id="TASK_CO_008")

        result = run_orchestrator(
            "impl-action",
            "--task-id", "TASK_CO_008",
            "--verified", "true",
        )
        assert result["action"] == "next_step"

    def test_all_complete(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_CO_009", description="Test task")
        workflow_set_implementation_progress(total_steps=2, task_id="TASK_CO_009")
        workflow_complete_step(step_id="step_1", task_id="TASK_CO_009")
        workflow_complete_step(step_id="step_2", task_id="TASK_CO_009")

        result = run_orchestrator("impl-action", "--task-id", "TASK_CO_009")
        assert result["action"] in ("complete", "checkpoint")

    def test_nonexistent(self):
        result = run_orchestrator("impl-action", "--task-id", "TASK_NONEXISTENT")
        assert "error" in result


# ============================================================================
# complete subcommand
# ============================================================================

class TestCompleteCommand:
    def test_basic_completion(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_CO_010", description="Add caching")
        workflow_set_mode(mode="fast", task_id="TASK_CO_010")

        result = run_orchestrator(
            "complete",
            "--task-id", "TASK_CO_010",
            "--files", "src/cache.ts,src/api.ts",
        )
        assert result["task_id"] == "TASK_CO_010"
        assert "cost_summary" in result
        assert "commit_message" in result
        assert "jira_actions" in result

    def test_nonexistent(self):
        result = run_orchestrator("complete", "--task-id", "TASK_NONEXISTENT")
        assert "error" in result


# ============================================================================
# resume subcommand
# ============================================================================

class TestResumeCommand:
    def test_resume_basic(self, clean_tasks_dir):
        workflow_initialize(task_id="TASK_CO_011", description="Test resume")
        workflow_set_mode(mode="full", task_id="TASK_CO_011")

        result = run_orchestrator("resume", "--task-id", "TASK_CO_011")
        assert result["action"] == "resume"
        assert "resume_state" in result
        assert "next" in result

    def test_resume_nonexistent(self):
        result = run_orchestrator("resume", "--task-id", "TASK_NONEXISTENT")
        assert result.get("error") is True


# ============================================================================
# Full workflow sequence
# ============================================================================

class TestFullSequence:
    def test_minimal_workflow(self, clean_tasks_dir):
        """Test init → agent-done sequence for minimal mode reaches complete."""
        # Init
        init_result = run_orchestrator("init", "--args", '"Fix typo" --mode minimal')
        assert init_result["action"] == "start"
        task_id = init_result["task_id"]
        task_dir = clean_tasks_dir / task_id

        # Minimal mode: developer → implementer → technical_writer
        phases = ["developer", "implementer", "technical_writer"]
        output_files = {
            "developer": "developer.md",
            "implementer": "implementer.md",
            "technical_writer": "technical-writer.md",
        }

        for phase in phases:
            output_name = output_files[phase]
            (task_dir / output_name).write_text(f"# {phase}\nDone.\n")
            workflow_transition(to_phase=phase, task_id=task_id)
            agent_done = run_orchestrator(
                "agent-done", "--task-id", task_id,
                "--agent", phase,
                "--output-file", str(task_dir / output_name),
            )
            assert agent_done["phase_completed"] is True

        # After all phases, next should be complete
        final_next = agent_done["next"]
        assert final_next.get("action") in ("complete", "checkpoint")


# ============================================================================
# State update tests
# ============================================================================

class TestStateUpdates:
    """Tests for state.json updates that the orchestrator now owns."""

    def test_agent_done_transitions_to_next_phase(self, clean_tasks_dir):
        """After agent-done, state.json phase should reflect the next agent."""
        workflow_initialize(task_id="TASK_CO_SU_001", description="Test state update")
        workflow_set_mode(mode="full", task_id="TASK_CO_SU_001")
        # Start at architect phase
        workflow_transition(to_phase="architect", task_id="TASK_CO_SU_001")

        # Create dummy output
        task_dir = clean_tasks_dir / "TASK_CO_SU_001"
        output_file = task_dir / "architect.md"
        output_file.write_text("# Architecture\nDesign done.\n")

        result = run_orchestrator(
            "agent-done",
            "--task-id", "TASK_CO_SU_001",
            "--agent", "architect",
            "--output-file", str(output_file),
        )
        assert result["phase_completed"] is True

        # If the next action is spawn_agent, state.json should have transitioned
        if result["next"].get("action") == "spawn_agent":
            expected_phase = result["next"]["agent"]
            assert result.get("transitioned_to") == expected_phase
            # Verify state.json on disk
            state = _load_state(task_dir)
            assert state["phase"] == expected_phase

    def test_init_turbo_sets_correct_first_phase(self, clean_tasks_dir):
        """In turbo mode, state.json phase should be 'developer', not 'architect'."""
        result = run_orchestrator("init", "--args", '"Build feature" --mode turbo')
        assert result["action"] == "start"
        task_id = result["task_id"]
        task_dir = clean_tasks_dir / task_id

        # Turbo mode skips architect — first phase should be developer
        if result["next"].get("action") == "spawn_agent":
            first_agent = result["next"]["agent"]
            state = _load_state(task_dir)
            assert state["phase"] == first_agent
            # Turbo mode should start with developer, not architect
            assert first_agent == "developer"

    def test_complete_marks_state_done(self, clean_tasks_dir):
        """After complete, state.json should have status='completed' and completed_at."""
        workflow_initialize(task_id="TASK_CO_SU_003", description="Test completion")
        workflow_set_mode(mode="fast", task_id="TASK_CO_SU_003")

        result = run_orchestrator(
            "complete",
            "--task-id", "TASK_CO_SU_003",
            "--files", "src/main.py,src/utils.py",
        )
        assert result["task_id"] == "TASK_CO_SU_003"

        # Verify state.json has completion markers
        task_dir = clean_tasks_dir / "TASK_CO_SU_003"
        state = _load_state(task_dir)
        assert state["status"] == "completed"
        assert "completed_at" in state
        assert state["files_changed"] == ["src/main.py", "src/utils.py"]

    def test_checkpoint_approve_completes_phase(self, clean_tasks_dir):
        """Approving at checkpoint should mark phase complete in state.json."""
        workflow_initialize(task_id="TASK_CO_SU_004", description="Test checkpoint")
        workflow_set_mode(mode="full", task_id="TASK_CO_SU_004")
        workflow_transition(to_phase="architect", task_id="TASK_CO_SU_004")

        result = run_orchestrator(
            "checkpoint-done",
            "--task-id", "TASK_CO_SU_004",
            "--decision", "approve",
        )
        assert result["decision"] == "approve"

        # Verify phase is in phases_completed
        task_dir = clean_tasks_dir / "TASK_CO_SU_004"
        state = _load_state(task_dir)
        assert "architect" in state.get("phases_completed", [])


# ============================================================================
# .active_task session isolation
# ============================================================================

class TestActiveTaskLifecycle:
    """Tests for .tasks/.active_task file created on init/resume, removed on complete."""

    def test_init_creates_active_task(self, clean_tasks_dir):
        """cmd_init start writes .tasks/.active_task with the task ID."""
        active_file = clean_tasks_dir / ".active_task"
        if active_file.exists():
            active_file.unlink()

        result = run_orchestrator("init", "--args", '"Test active task" --mode minimal')
        assert result["action"] == "start"
        task_id = result["task_id"]

        assert active_file.exists(), ".active_task should be created on init"
        assert active_file.read_text().strip() == task_id

        # Clean up
        task_dir = clean_tasks_dir / task_id
        if task_dir.exists():
            shutil.rmtree(task_dir)
        if active_file.exists():
            active_file.unlink()

    def test_complete_removes_active_task(self, clean_tasks_dir):
        """cmd_complete removes .tasks/.active_task when it matches the task ID."""
        active_file = clean_tasks_dir / ".active_task"

        workflow_initialize(task_id="TASK_CO_AT_001", description="Test removal")
        workflow_set_mode(mode="minimal", task_id="TASK_CO_AT_001")

        # Simulate what init would do
        active_file.write_text("TASK_CO_AT_001\n")
        assert active_file.exists()

        run_orchestrator("complete", "--task-id", "TASK_CO_AT_001")

        assert not active_file.exists(), ".active_task should be removed on complete"

    def test_complete_preserves_other_active_task(self, clean_tasks_dir):
        """cmd_complete does NOT remove .active_task if it belongs to a different task."""
        active_file = clean_tasks_dir / ".active_task"

        workflow_initialize(task_id="TASK_CO_AT_002", description="Test preserve")
        workflow_set_mode(mode="minimal", task_id="TASK_CO_AT_002")

        # .active_task points to a different task
        active_file.write_text("TASK_CO_AT_OTHER\n")

        run_orchestrator("complete", "--task-id", "TASK_CO_AT_002")

        assert active_file.exists(), ".active_task should be preserved for other task"
        assert active_file.read_text().strip() == "TASK_CO_AT_OTHER"

        # Clean up
        if active_file.exists():
            active_file.unlink()

    def test_resume_creates_active_task(self, clean_tasks_dir):
        """cmd_resume writes .tasks/.active_task with the task ID."""
        active_file = clean_tasks_dir / ".active_task"
        if active_file.exists():
            active_file.unlink()

        workflow_initialize(task_id="TASK_CO_AT_003", description="Test resume")
        workflow_set_mode(mode="full", task_id="TASK_CO_AT_003")

        result = run_orchestrator("resume", "--task-id", "TASK_CO_AT_003")
        assert result["action"] == "resume"

        assert active_file.exists(), ".active_task should be created on resume"
        assert active_file.read_text().strip() == "TASK_CO_AT_003"

        # Clean up
        if active_file.exists():
            active_file.unlink()

    def test_init_resume_creates_active_task(self, clean_tasks_dir):
        """cmd_init with 'resume TASK_ID' also writes .active_task."""
        active_file = clean_tasks_dir / ".active_task"
        if active_file.exists():
            active_file.unlink()

        workflow_initialize(task_id="TASK_CO_AT_004", description="Test init resume")
        workflow_set_mode(mode="full", task_id="TASK_CO_AT_004")

        result = run_orchestrator("init", "--args", "resume TASK_CO_AT_004")
        assert result["action"] == "resume"

        assert active_file.exists(), ".active_task should be created on init resume"
        assert active_file.read_text().strip() == "TASK_CO_AT_004"

        # Clean up
        if active_file.exists():
            active_file.unlink()
