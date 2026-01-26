#!/usr/bin/env python3
"""
Agentic Workflow MCP Server

A unified MCP server that provides state management, configuration, and
validation tools for the agentic-workflow system.

This server replaces the shell-based hooks with structured MCP tools that
provide better error handling, discoverability, and reliability.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    Resource,
    ResourceTemplate,
)

from .state_tools import (
    workflow_initialize,
    workflow_transition,
    workflow_get_state,
    workflow_add_review_issue,
    workflow_mark_docs_needed,
    workflow_complete_phase,
    workflow_is_complete,
    workflow_can_transition,
    workflow_can_stop,
    list_tasks,
    get_active_task,
)
from .config_tools import (
    config_get_effective,
    config_get_checkpoint,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

server = Server("agentic-workflow-server")


TOOLS = [
    Tool(
        name="workflow_initialize",
        description="Initialize a new workflow task with initial state. Creates a .tasks/TASK_XXX directory and state.json.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier (e.g., 'TASK_001'). If not provided, auto-generates next available ID."
                },
                "description": {
                    "type": "string",
                    "description": "Optional description of the task"
                }
            },
            "required": []
        }
    ),
    Tool(
        name="workflow_transition",
        description="Validate and execute a phase transition. Returns success/failure with detailed reason.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                },
                "to_phase": {
                    "type": "string",
                    "description": "Target phase to transition to",
                    "enum": ["architect", "developer", "reviewer", "skeptic", "implementer", "technical_writer"]
                }
            },
            "required": ["to_phase"]
        }
    ),
    Tool(
        name="workflow_get_state",
        description="Read current workflow state for a task. Returns full state including phase, completed phases, iteration, review issues, etc.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                }
            },
            "required": []
        }
    ),
    Tool(
        name="workflow_add_review_issue",
        description="Add an issue found during review that may require looping back to developer phase.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                },
                "issue_type": {
                    "type": "string",
                    "description": "Type of issue (e.g., 'missing_test', 'security', 'performance')"
                },
                "description": {
                    "type": "string",
                    "description": "Description of the issue"
                },
                "step": {
                    "type": "string",
                    "description": "Optional step reference (e.g., '2.3')"
                },
                "severity": {
                    "type": "string",
                    "description": "Issue severity",
                    "enum": ["low", "medium", "high", "critical"]
                }
            },
            "required": ["issue_type", "description"]
        }
    ),
    Tool(
        name="workflow_mark_docs_needed",
        description="Flag files that need documentation by the Technical Writer phase.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file paths that need documentation"
                }
            },
            "required": ["files"]
        }
    ),
    Tool(
        name="workflow_complete_phase",
        description="Mark the current phase as complete. Called when agent finishes its work.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                }
            },
            "required": []
        }
    ),
    Tool(
        name="workflow_is_complete",
        description="Check if all required workflow phases have been completed.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                }
            },
            "required": []
        }
    ),
    Tool(
        name="workflow_can_transition",
        description="Check if a transition to a given phase is valid (dry-run). Use this to proactively check before attempting a transition.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                },
                "to_phase": {
                    "type": "string",
                    "description": "Target phase to check",
                    "enum": ["architect", "developer", "reviewer", "skeptic", "implementer", "technical_writer"]
                }
            },
            "required": ["to_phase"]
        }
    ),
    Tool(
        name="workflow_can_stop",
        description="Check if the workflow can be stopped (all required phases complete). Use this before ending the session.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                }
            },
            "required": []
        }
    ),
    Tool(
        name="config_get_effective",
        description="Get the fully merged effective configuration for the current context. Merges global, project, and task configs.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier for task-level config override"
                },
                "project_dir": {
                    "type": "string",
                    "description": "Project directory for project-level config. Defaults to current directory."
                }
            },
            "required": []
        }
    ),
    Tool(
        name="config_get_checkpoint",
        description="Check if a specific checkpoint is enabled in the effective config.",
        inputSchema={
            "type": "object",
            "properties": {
                "checkpoint": {
                    "type": "string",
                    "description": "Checkpoint name (e.g., 'after_architect', 'at_50_percent', 'before_commit')"
                },
                "category": {
                    "type": "string",
                    "description": "Checkpoint category",
                    "enum": ["planning", "implementation", "documentation", "feedback"]
                },
                "task_id": {
                    "type": "string",
                    "description": "Task identifier for task-level config override"
                }
            },
            "required": ["checkpoint", "category"]
        }
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "workflow_initialize":
            result = workflow_initialize(
                task_id=arguments.get("task_id"),
                description=arguments.get("description")
            )
        elif name == "workflow_transition":
            result = workflow_transition(
                to_phase=arguments["to_phase"],
                task_id=arguments.get("task_id")
            )
        elif name == "workflow_get_state":
            result = workflow_get_state(task_id=arguments.get("task_id"))
        elif name == "workflow_add_review_issue":
            result = workflow_add_review_issue(
                issue_type=arguments["issue_type"],
                description=arguments["description"],
                task_id=arguments.get("task_id"),
                step=arguments.get("step"),
                severity=arguments.get("severity", "medium")
            )
        elif name == "workflow_mark_docs_needed":
            result = workflow_mark_docs_needed(
                files=arguments["files"],
                task_id=arguments.get("task_id")
            )
        elif name == "workflow_complete_phase":
            result = workflow_complete_phase(task_id=arguments.get("task_id"))
        elif name == "workflow_is_complete":
            result = workflow_is_complete(task_id=arguments.get("task_id"))
        elif name == "workflow_can_transition":
            result = workflow_can_transition(
                to_phase=arguments["to_phase"],
                task_id=arguments.get("task_id")
            )
        elif name == "workflow_can_stop":
            result = workflow_can_stop(task_id=arguments.get("task_id"))
        elif name == "config_get_effective":
            result = config_get_effective(
                task_id=arguments.get("task_id"),
                project_dir=arguments.get("project_dir")
            )
        elif name == "config_get_checkpoint":
            result = config_get_checkpoint(
                checkpoint=arguments["checkpoint"],
                category=arguments["category"],
                task_id=arguments.get("task_id")
            )
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        logger.exception(f"Error executing tool {name}")
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e), "tool": name}, indent=2)
        )]


@server.list_resources()
async def list_resources() -> list[Resource]:
    resources = []

    tasks = list_tasks()
    for task in tasks:
        resources.append(Resource(
            uri=f"workflow://tasks/{task['task_id']}/state",
            name=f"Workflow state for {task['task_id']}",
            mimeType="application/json",
            description=f"Current workflow state for task {task['task_id']}"
        ))

    active = get_active_task()
    if active:
        resources.append(Resource(
            uri="workflow://active",
            name="Active workflow task",
            mimeType="application/json",
            description="Currently active workflow task"
        ))

    resources.append(Resource(
        uri="config://effective",
        name="Effective configuration",
        mimeType="application/json",
        description="Fully merged effective workflow configuration"
    ))

    return resources


@server.list_resource_templates()
async def list_resource_templates() -> list[ResourceTemplate]:
    return [
        ResourceTemplate(
            uriTemplate="workflow://tasks/{task_id}/state",
            name="Task workflow state",
            mimeType="application/json",
            description="Get workflow state for a specific task"
        ),
    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    if uri == "workflow://active":
        active = get_active_task()
        if active:
            state = workflow_get_state(task_id=active)
            return json.dumps(state, indent=2)
        return json.dumps({"error": "No active task"})

    if uri == "config://effective":
        config = config_get_effective()
        return json.dumps(config, indent=2)

    if uri.startswith("workflow://tasks/") and uri.endswith("/state"):
        task_id = uri.replace("workflow://tasks/", "").replace("/state", "")
        state = workflow_get_state(task_id=task_id)
        return json.dumps(state, indent=2)

    return json.dumps({"error": f"Unknown resource: {uri}"})


async def async_main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main():
    """Entry point for the MCP server."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
