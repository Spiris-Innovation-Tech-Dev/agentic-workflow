#!/usr/bin/env python3
"""
PreToolUse Hook: Validate Workflow Transitions

This hook runs before Task tool calls to ensure agents are spawned in the
correct order according to the workflow state.

The hook:
- Reads the Task tool input from stdin (JSON)
- Checks the agent being spawned against current workflow state
- Blocks invalid transitions (exit 2)
- Allows valid transitions (exit 0)

Usage in .claude/settings.json:
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Task",
      "hooks": [{
        "type": "command",
        "command": "python scripts/validate-transition.py"
      }]
    }]
  }
}
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from workflow_state import WorkflowState, find_active_task, PHASE_ORDER


AGENT_TO_PHASE = {
    "architect": "architect",
    "developer": "developer",
    "reviewer": "reviewer",
    "skeptic": "skeptic",
    "implementer": "implementer",
    "technical-writer": "technical_writer",
    "technical_writer": "technical_writer",
}


def extract_agent_from_prompt(prompt: str) -> str | None:
    """
    Extract the agent type from a Task prompt.

    Looks for patterns like:
    - "agents/architect.md" in the prompt
    - "# Architect Agent" header
    - Explicit agent type mention
    """
    prompt_lower = prompt.lower()

    for agent_name in AGENT_TO_PHASE.keys():
        patterns = [
            rf"agents/{agent_name}\.md",
            rf"# {agent_name} agent",
            rf"\b{agent_name}\s+agent\b",
        ]
        for pattern in patterns:
            if re.search(pattern, prompt_lower):
                return agent_name

    return None


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    prompt = tool_input.get("prompt", "")
    subagent_type = tool_input.get("subagent_type", "")

    if subagent_type not in ("general-purpose", "Plan"):
        sys.exit(0)

    if "crew" not in prompt.lower() and "workflow" not in prompt.lower():
        is_workflow_agent = False
        for agent_name in AGENT_TO_PHASE.keys():
            if agent_name.replace("-", "_") in prompt.lower() or agent_name.replace("_", "-") in prompt.lower():
                is_workflow_agent = True
                break
        if not is_workflow_agent:
            sys.exit(0)

    task_dir = find_active_task()
    if not task_dir:
        sys.exit(0)

    state = WorkflowState(task_dir)

    agent_name = extract_agent_from_prompt(prompt)
    if not agent_name:
        sys.exit(0)

    target_phase = AGENT_TO_PHASE.get(agent_name)
    if not target_phase:
        sys.exit(0)

    can_transition, reason = state.can_transition(target_phase)

    if can_transition:
        sys.exit(0)
    else:
        response = {
            "decision": "block",
            "reason": f"Workflow violation: {reason}. Current phase: {state.phase}, completed: {state.phases_completed}"
        }
        print(json.dumps(response))
        sys.exit(2)


if __name__ == "__main__":
    main()
