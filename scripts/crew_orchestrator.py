#!/usr/bin/env python3
"""
Crew Orchestrator — CLI wrapper for deterministic workflow routing.

Batches multiple MCP tool calls into single instant decisions, replacing
LLM interpretation of procedural routing logic. Each subcommand returns
structured JSON that tells the crew.md orchestrator exactly what to do next.

Usage:
    python3 scripts/crew_orchestrator.py init --args "Fix typo in README --mode minimal"
    python3 scripts/crew_orchestrator.py next --task-id TASK_001
    python3 scripts/crew_orchestrator.py agent-done --task-id TASK_001 --agent architect --output-file .tasks/TASK_001/architect.md
    python3 scripts/crew_orchestrator.py checkpoint-done --task-id TASK_001 --decision approve
    python3 scripts/crew_orchestrator.py impl-action --task-id TASK_001
    python3 scripts/crew_orchestrator.py complete --task-id TASK_001
    python3 scripts/crew_orchestrator.py resume --task-id TASK_001
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add MCP server package to path so we can import directly
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
_MCP_PKG = _REPO_ROOT / "mcp" / "agentic-workflow-server"
if str(_MCP_PKG) not in sys.path:
    sys.path.insert(0, str(_MCP_PKG))

from agentic_workflow_server.orchestration_tools import (
    crew_parse_args,
    crew_init_task,
    crew_get_next_phase,
    crew_parse_agent_output,
    crew_get_implementation_action,
    crew_format_completion,
    crew_get_resume_state,
)
from agentic_workflow_server.state_tools import (
    workflow_complete_phase,
    workflow_add_human_decision,
    workflow_record_cost,
    workflow_transition,
    workflow_log_interaction,
    find_task_dir,
    _load_state,
    _save_state,
)
from agentic_workflow_server.config_tools import config_get_effective


def _output(data: dict) -> None:
    """Print JSON to stdout."""
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")


def cmd_init(args: argparse.Namespace) -> None:
    """Parse args, route action, init task, return first action.

    Batches: crew_parse_args → crew_init_task → crew_get_next_phase
    """
    parsed = crew_parse_args(args.args)

    if parsed.get("errors"):
        _output({"error": True, "errors": parsed["errors"], "action": parsed["action"]})
        return

    action = parsed["action"]

    # Non-start actions: return immediately with routing info
    if action in ("status", "config", "proceed"):
        _output({"action": action})
        return

    if action == "resume":
        task_id = parsed.get("task_id")
        if not task_id:
            _output({"error": True, "errors": ["No task ID provided for resume"]})
            return
        resume = crew_get_resume_state(task_id=task_id)
        if resume.get("error"):
            _output({"error": True, "errors": [resume["error"]]})
            return
        next_action = crew_get_next_phase(task_id=task_id)
        _output({
            "action": "resume",
            "resume_state": resume,
            "next": next_action,
        })
        return

    if action == "ask":
        _output({
            "action": "ask",
            "agent": parsed.get("agent"),
            "question": parsed.get("task_description", ""),
            "options": parsed.get("options", {}),
        })
        return

    # Action is "start" — full initialization
    task_description = parsed["task_description"]
    options = parsed.get("options", {})

    # Resolve task description from file if specified
    if options.get("task_file"):
        task_file = Path(options["task_file"])
        if task_file.exists():
            task_description = task_file.read_text().strip()
        else:
            _output({"error": True, "errors": [f"Task file not found: {options['task_file']}"]})
            return

    if not task_description:
        _output({"error": True, "errors": ["No task description provided"]})
        return

    init_result = crew_init_task(
        task_description=task_description,
        options=options,
    )

    if not init_result.get("success"):
        _output({"error": True, "errors": [init_result.get("error", "Initialization failed")]})
        return

    task_id = init_result["task_id"]

    # Get first phase action
    next_action = crew_get_next_phase(task_id=task_id)

    # Pre-transition to first phase if it differs from default
    if next_action.get("action") == "spawn_agent" and next_action.get("agent"):
        first_phase = next_action["agent"]
        task_dir_path = find_task_dir(task_id)
        if task_dir_path:
            current_state = _load_state(task_dir_path)
            if current_state.get("phase") != first_phase:
                workflow_transition(to_phase=first_phase, task_id=task_id)

    _output({
        "action": "start",
        "task_id": task_id,
        "task_dir": init_result["task_dir"],
        "mode": init_result["mode"],
        "optional_agents": init_result.get("optional_agents", []),
        "kb_inventory": init_result.get("kb_inventory", {}),
        "beads_issue": init_result.get("beads_issue"),
        "config": init_result.get("config", {}),
        "next": next_action,
    })


def cmd_next(args: argparse.Namespace) -> None:
    """Get next phase/action.

    Wraps: crew_get_next_phase
    """
    result = crew_get_next_phase(task_id=args.task_id)
    _output(result)


def cmd_agent_done(args: argparse.Namespace) -> None:
    """Parse output, complete phase, record cost, get next action.

    Batches: crew_parse_agent_output → workflow_complete_phase →
             workflow_record_cost → crew_get_next_phase
    """
    task_id = args.task_id
    agent = args.agent

    # Read output from file if provided
    output_text = ""
    if args.output_file:
        output_path = Path(args.output_file)
        if output_path.exists():
            output_text = output_path.read_text()

    # 1. Parse agent output
    parse_result = crew_parse_agent_output(
        agent=agent,
        output_text=output_text,
        task_id=task_id,
    )

    # 2. Complete phase
    complete_result = workflow_complete_phase(task_id=task_id)

    # 3. Record cost if provided
    cost_recorded = False
    if args.input_tokens and args.output_tokens:
        workflow_record_cost(
            agent=agent,
            model=args.model or "opus",
            input_tokens=args.input_tokens,
            output_tokens=args.output_tokens,
            duration_seconds=args.duration or 0,
            task_id=task_id,
        )
        cost_recorded = True

    # 4. Get next action
    next_action = crew_get_next_phase(task_id=task_id)

    # 5. Pre-transition to next phase if spawning an agent
    transition_result = None
    if next_action.get("action") == "spawn_agent" and next_action.get("agent"):
        transition_result = workflow_transition(
            to_phase=next_action["agent"],
            task_id=task_id,
        )

    _output({
        "action": "agent_done",
        "parse_result": parse_result,
        "phase_completed": complete_result.get("success", False),
        "cost_recorded": cost_recorded,
        "has_blocking_issues": parse_result.get("has_blocking_issues", False),
        "transitioned_to": transition_result.get("to_phase") if transition_result else None,
        "next": next_action,
    })


def cmd_checkpoint_done(args: argparse.Namespace) -> None:
    """Record decision, log interactions, get next action.

    Batches: log interactions → workflow_add_human_decision → crew_get_next_phase
    """
    task_id = args.task_id
    decision = args.decision

    # Determine checkpoint name from current state
    task_dir = find_task_dir(task_id)
    checkpoint_name = "checkpoint"
    phase = "unknown"
    if task_dir:
        state = _load_state(task_dir)
        phase = state.get("phase", "unknown")
        checkpoint_name = f"after_{phase}"

    # 0. Log checkpoint question and response to interactions.jsonl
    if args.question:
        workflow_log_interaction(
            role="agent",
            content=args.question,
            interaction_type="checkpoint_question",
            agent="orchestrator",
            phase=phase,
            task_id=task_id,
        )

    response_content = decision
    if args.notes:
        response_content = f"{decision}: {args.notes}"
    workflow_log_interaction(
        role="human",
        content=response_content,
        interaction_type="checkpoint_response",
        agent="orchestrator",
        phase=phase,
        task_id=task_id,
    )

    # 1. Record decision
    workflow_add_human_decision(
        checkpoint=checkpoint_name,
        decision=decision,
        notes=args.notes or "",
        task_id=task_id,
    )

    # 2. Ensure phase is marked complete for approve/skip
    if decision in ("approve", "skip"):
        workflow_complete_phase(task_id=task_id)

    # 3. Handle revise — transition back to developer
    if decision == "revise":
        workflow_transition(to_phase="developer", task_id=task_id)

    # 4. Handle restart — transition back to architect
    if decision == "restart":
        workflow_transition(to_phase="architect", task_id=task_id)

    # 5. Get next action
    next_action = crew_get_next_phase(task_id=task_id)

    # 6. Pre-transition to next phase if spawning an agent
    if next_action.get("action") == "spawn_agent" and next_action.get("agent"):
        workflow_transition(to_phase=next_action["agent"], task_id=task_id)

    _output({
        "action": "checkpoint_done",
        "decision": decision,
        "checkpoint": checkpoint_name,
        "next": next_action,
    })


def cmd_impl_action(args: argparse.Namespace) -> None:
    """Implementation loop step.

    Wraps: crew_get_implementation_action
    """
    verified = None
    if args.verified is not None:
        verified = args.verified.lower() in ("true", "1", "yes")

    result = crew_get_implementation_action(
        task_id=args.task_id,
        last_verification_passed=verified,
        last_error_output=args.error or None,
    )
    _output(result)


def cmd_complete(args: argparse.Namespace) -> None:
    """Format completion + Jira + beads.

    Batches: crew_format_completion + crew_jira_transition
    """
    task_id = args.task_id

    # Get files changed from git if not provided
    files_changed = []
    if args.files:
        files_changed = args.files.split(",")

    completion = crew_format_completion(
        task_id=task_id,
        files_changed=files_changed,
    )

    # Resolve Jira transitions if applicable
    jira_actions = []
    task_dir = find_task_dir(task_id)
    if task_dir:
        state = _load_state(task_dir)
        linked_issue = state.get("linked_issue") or state.get("jira_issue")
        if linked_issue:
            try:
                from agentic_workflow_server.orchestration_tools import crew_jira_transition
                for hook in ("on_complete", "on_cleanup"):
                    jira_result = crew_jira_transition(
                        task_id=task_id,
                        hook_name=hook,
                        issue_key=linked_issue,
                    )
                    if jira_result.get("action") != "skip":
                        jira_actions.append(jira_result)
            except (ImportError, Exception):
                pass  # Jira integration is non-blocking

    # Mark workflow as complete in state.json
    if task_dir:
        state = _load_state(task_dir)
        state["status"] = "completed"
        state["completed_at"] = datetime.now().isoformat()
        if files_changed:
            state["files_changed"] = files_changed
        _save_state(task_dir, state)

    completion["jira_actions"] = jira_actions
    _output(completion)


def cmd_log_interaction(args: argparse.Namespace) -> None:
    """Log an interaction entry.

    Wraps: workflow_log_interaction
    """
    result = workflow_log_interaction(
        role=args.role,
        content=args.content,
        interaction_type=args.type,
        agent=args.agent or "",
        phase=args.phase or "",
        task_id=args.task_id,
    )
    _output(result)


def cmd_resume(args: argparse.Namespace) -> None:
    """Load resume context.

    Batches: crew_get_resume_state → crew_get_next_phase
    """
    task_id = args.task_id

    resume = crew_get_resume_state(task_id=task_id)
    if resume.get("error"):
        _output({"error": True, "errors": [resume["error"]]})
        return

    next_action = crew_get_next_phase(task_id=task_id)

    _output({
        "action": "resume",
        "resume_state": resume,
        "next": next_action,
    })


def main():
    parser = argparse.ArgumentParser(
        description="Crew Orchestrator — instant routing decisions for /crew workflow"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Parse args, init task, get first action")
    p_init.add_argument("--args", required=True, help="Raw /crew arguments string")

    # next
    p_next = subparsers.add_parser("next", help="Get next phase/action")
    p_next.add_argument("--task-id", required=True, help="Task identifier")

    # agent-done
    p_agent = subparsers.add_parser("agent-done", help="Parse output, complete phase, get next")
    p_agent.add_argument("--task-id", required=True, help="Task identifier")
    p_agent.add_argument("--agent", required=True, help="Agent name")
    p_agent.add_argument("--output-file", help="Path to agent output file")
    p_agent.add_argument("--input-tokens", type=int, help="Input tokens used")
    p_agent.add_argument("--output-tokens", type=int, help="Output tokens used")
    p_agent.add_argument("--model", default="opus", help="Model used")
    p_agent.add_argument("--duration", type=float, help="Duration in seconds")

    # checkpoint-done
    p_ckpt = subparsers.add_parser("checkpoint-done", help="Record decision, get next")
    p_ckpt.add_argument("--task-id", required=True, help="Task identifier")
    p_ckpt.add_argument("--decision", required=True, choices=["approve", "revise", "restart", "skip"])
    p_ckpt.add_argument("--notes", help="Optional decision notes")
    p_ckpt.add_argument("--question", help="Checkpoint question that was presented to user")

    # impl-action
    p_impl = subparsers.add_parser("impl-action", help="Implementation loop step")
    p_impl.add_argument("--task-id", required=True, help="Task identifier")
    p_impl.add_argument("--verified", help="Last verification result (true/false)")
    p_impl.add_argument("--error", help="Last error output")

    # complete
    p_complete = subparsers.add_parser("complete", help="Format completion + Jira + beads")
    p_complete.add_argument("--task-id", required=True, help="Task identifier")
    p_complete.add_argument("--files", help="Comma-separated list of changed files")

    # log-interaction
    p_log = subparsers.add_parser("log-interaction", help="Log an interaction entry")
    p_log.add_argument("--task-id", required=True, help="Task identifier")
    p_log.add_argument("--role", required=True, choices=["human", "agent", "system"])
    p_log.add_argument("--content", required=True, help="Message content")
    p_log.add_argument("--type", default="message",
                       choices=["message", "checkpoint_question", "checkpoint_response",
                                "guidance", "escalation_question", "escalation_response"])
    p_log.add_argument("--agent", help="Agent context (e.g., orchestrator, architect)")
    p_log.add_argument("--phase", help="Current workflow phase")

    # resume
    p_resume = subparsers.add_parser("resume", help="Load resume context")
    p_resume.add_argument("--task-id", required=True, help="Task identifier")

    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "next": cmd_next,
        "agent-done": cmd_agent_done,
        "checkpoint-done": cmd_checkpoint_done,
        "impl-action": cmd_impl_action,
        "complete": cmd_complete,
        "log-interaction": cmd_log_interaction,
        "resume": cmd_resume,
    }

    try:
        commands[args.command](args)
    except Exception as e:
        _output({"error": True, "errors": [str(e)]})
        sys.exit(1)


if __name__ == "__main__":
    main()
