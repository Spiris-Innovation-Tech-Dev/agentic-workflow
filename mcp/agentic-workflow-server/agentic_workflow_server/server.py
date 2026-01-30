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
    workflow_set_implementation_progress,
    workflow_complete_step,
    workflow_add_human_decision,
    workflow_set_kb_inventory,
    workflow_add_concern,
    workflow_address_concern,
    workflow_get_concerns,
    workflow_save_discovery,
    workflow_get_discoveries,
    workflow_flush_context,
    workflow_get_context_usage,
    workflow_prune_old_outputs,
    workflow_search_memories,
    workflow_link_tasks,
    workflow_get_linked_tasks,
    workflow_record_model_error,
    workflow_record_model_success,
    workflow_get_available_model,
    workflow_get_resilience_status,
    workflow_clear_model_cooldown,
)
from .config_tools import (
    config_get_effective,
    config_get_checkpoint,
    config_get_beads,
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
    Tool(
        name="config_get_beads",
        description="Get beads configuration with auto-detection. If enabled is 'auto', checks if beads is installed and initialized.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier for task-level config override"
                },
                "project_dir": {
                    "type": "string",
                    "description": "Project directory. Defaults to current directory."
                }
            },
            "required": []
        }
    ),
    Tool(
        name="workflow_set_implementation_progress",
        description="Set the total number of implementation steps and optionally current step.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                },
                "total_steps": {
                    "type": "integer",
                    "description": "Total number of implementation steps"
                },
                "current_step": {
                    "type": "integer",
                    "description": "Current step number (0-indexed)"
                }
            },
            "required": ["total_steps"]
        }
    ),
    Tool(
        name="workflow_complete_step",
        description="Mark an implementation step as completed.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                },
                "step_id": {
                    "type": "string",
                    "description": "Step identifier (e.g., '1.1', '2.3')"
                }
            },
            "required": ["step_id"]
        }
    ),
    Tool(
        name="workflow_add_human_decision",
        description="Record a human decision at a checkpoint for audit trail.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                },
                "checkpoint": {
                    "type": "string",
                    "description": "Checkpoint name (e.g., 'after_architect', 'before_commit')"
                },
                "decision": {
                    "type": "string",
                    "description": "Decision made",
                    "enum": ["approve", "revise", "restart", "skip"]
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes about the decision"
                }
            },
            "required": ["checkpoint", "decision"]
        }
    ),
    Tool(
        name="workflow_set_kb_inventory",
        description="Store knowledge base path and file inventory in state.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                },
                "path": {
                    "type": "string",
                    "description": "Path to knowledge base directory"
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of files in the knowledge base"
                }
            },
            "required": ["path", "files"]
        }
    ),
    Tool(
        name="workflow_add_concern",
        description="Add a concern from an agent (Architect, Reviewer, Skeptic) for cross-agent tracking.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                },
                "source": {
                    "type": "string",
                    "description": "Agent that raised the concern",
                    "enum": ["architect", "developer", "reviewer", "skeptic", "feedback"]
                },
                "severity": {
                    "type": "string",
                    "description": "Severity level",
                    "enum": ["critical", "high", "medium", "low"]
                },
                "description": {
                    "type": "string",
                    "description": "Description of the concern"
                },
                "concern_id": {
                    "type": "string",
                    "description": "Optional custom ID. If not provided, auto-generates."
                }
            },
            "required": ["source", "severity", "description"]
        }
    ),
    Tool(
        name="workflow_address_concern",
        description="Mark a concern as addressed by a step or action.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                },
                "concern_id": {
                    "type": "string",
                    "description": "ID of the concern to address"
                },
                "addressed_by": {
                    "type": "string",
                    "description": "Step or action that addresses the concern (e.g., 'step 2.3')"
                }
            },
            "required": ["concern_id", "addressed_by"]
        }
    ),
    Tool(
        name="workflow_get_concerns",
        description="Get all concerns, optionally filtering to unaddressed only.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                },
                "unaddressed_only": {
                    "type": "boolean",
                    "description": "If true, only return unaddressed concerns"
                }
            },
            "required": []
        }
    ),
    Tool(
        name="workflow_save_discovery",
        description="Save a discovery (decision, pattern, gotcha, blocker, preference) to persistent memory. Use this to preserve critical learnings that should survive context compaction.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                },
                "category": {
                    "type": "string",
                    "description": "Type of discovery",
                    "enum": ["decision", "pattern", "gotcha", "blocker", "preference"]
                },
                "content": {
                    "type": "string",
                    "description": "The discovery content to save"
                }
            },
            "required": ["category", "content"]
        }
    ),
    Tool(
        name="workflow_get_discoveries",
        description="Retrieve saved discoveries from persistent memory, optionally filtered by category.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                },
                "category": {
                    "type": "string",
                    "description": "Filter to specific category",
                    "enum": ["decision", "pattern", "gotcha", "blocker", "preference"]
                }
            },
            "required": []
        }
    ),
    Tool(
        name="workflow_flush_context",
        description="Return all discoveries for the task, grouped by category. Use before context compaction to capture what should be reloaded.",
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
        name="workflow_get_context_usage",
        description="Estimate context usage for the task based on files in the task directory. Returns file sizes, token estimates, and recommendations for managing context pressure.",
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
        name="workflow_prune_old_outputs",
        description="Prune old, large tool outputs to reduce context pressure. Creates summaries of pruned files and removes originals. Use when context usage is high.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                },
                "keep_last_n": {
                    "type": "integer",
                    "description": "Number of recent outputs to keep intact (default: 5)",
                    "default": 5
                }
            },
            "required": []
        }
    ),
    Tool(
        name="workflow_search_memories",
        description="Search across task memories using keyword matching. Find patterns, decisions, and gotchas from previous tasks to avoid re-learning.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (case-insensitive keyword matching)"
                },
                "task_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of task IDs to search. If not provided, searches all tasks."
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter",
                    "enum": ["decision", "pattern", "gotcha", "blocker", "preference"]
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 20)",
                    "default": 20
                }
            },
            "required": ["query"]
        }
    ),
    Tool(
        name="workflow_link_tasks",
        description="Link related tasks for context inheritance. Creates bidirectional links so agents can reference prior related work.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task to add links to"
                },
                "related_task_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of related task IDs to link"
                },
                "relationship": {
                    "type": "string",
                    "description": "Type of relationship",
                    "enum": ["related", "builds_on", "supersedes", "blocked_by"],
                    "default": "related"
                }
            },
            "required": ["task_id", "related_task_ids"]
        }
    ),
    Tool(
        name="workflow_get_linked_tasks",
        description="Get all tasks linked to the specified task, optionally including their recent discoveries.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task identifier. If not provided, uses active task."
                },
                "include_memories": {
                    "type": "boolean",
                    "description": "If true, include recent discoveries from linked tasks",
                    "default": False
                }
            },
            "required": []
        }
    ),
    Tool(
        name="workflow_record_model_error",
        description="Record a model API error for cooldown tracking. Enables intelligent failover with exponential backoff.",
        inputSchema={
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": "Model identifier (e.g., 'claude-opus-4', 'claude-sonnet-4', 'gemini')"
                },
                "error_type": {
                    "type": "string",
                    "description": "Type of error encountered",
                    "enum": ["rate_limit", "overloaded", "timeout", "server_error", "billing", "auth", "unknown"]
                },
                "error_message": {
                    "type": "string",
                    "description": "Optional error message for debugging"
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task context"
                }
            },
            "required": ["model", "error_type"]
        }
    ),
    Tool(
        name="workflow_record_model_success",
        description="Record a successful model call, resetting consecutive error count and cooldown.",
        inputSchema={
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": "Model identifier"
                }
            },
            "required": ["model"]
        }
    ),
    Tool(
        name="workflow_get_available_model",
        description="Get the next available model considering cooldowns. Returns the first model in the fallback chain not in cooldown.",
        inputSchema={
            "type": "object",
            "properties": {
                "preferred_model": {
                    "type": "string",
                    "description": "Optional preferred model to try first before fallback chain"
                }
            },
            "required": []
        }
    ),
    Tool(
        name="workflow_get_resilience_status",
        description="Get current resilience status for all models including cooldowns, error counts, and health overview.",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": []
        }
    ),
    Tool(
        name="workflow_clear_model_cooldown",
        description="Manually clear a model's cooldown state. Use when you know a model has recovered.",
        inputSchema={
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": "Model identifier to clear cooldown for"
                }
            },
            "required": ["model"]
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
        elif name == "config_get_beads":
            result = config_get_beads(
                task_id=arguments.get("task_id"),
                project_dir=arguments.get("project_dir")
            )
        elif name == "workflow_set_implementation_progress":
            result = workflow_set_implementation_progress(
                total_steps=arguments["total_steps"],
                current_step=arguments.get("current_step", 0),
                task_id=arguments.get("task_id")
            )
        elif name == "workflow_complete_step":
            result = workflow_complete_step(
                step_id=arguments["step_id"],
                task_id=arguments.get("task_id")
            )
        elif name == "workflow_add_human_decision":
            result = workflow_add_human_decision(
                checkpoint=arguments["checkpoint"],
                decision=arguments["decision"],
                notes=arguments.get("notes", ""),
                task_id=arguments.get("task_id")
            )
        elif name == "workflow_set_kb_inventory":
            result = workflow_set_kb_inventory(
                path=arguments["path"],
                files=arguments["files"],
                task_id=arguments.get("task_id")
            )
        elif name == "workflow_add_concern":
            result = workflow_add_concern(
                source=arguments["source"],
                severity=arguments["severity"],
                description=arguments["description"],
                concern_id=arguments.get("concern_id"),
                task_id=arguments.get("task_id")
            )
        elif name == "workflow_address_concern":
            result = workflow_address_concern(
                concern_id=arguments["concern_id"],
                addressed_by=arguments["addressed_by"],
                task_id=arguments.get("task_id")
            )
        elif name == "workflow_get_concerns":
            result = workflow_get_concerns(
                task_id=arguments.get("task_id"),
                unaddressed_only=arguments.get("unaddressed_only", False)
            )
        elif name == "workflow_save_discovery":
            result = workflow_save_discovery(
                category=arguments["category"],
                content=arguments["content"],
                task_id=arguments.get("task_id")
            )
        elif name == "workflow_get_discoveries":
            result = workflow_get_discoveries(
                category=arguments.get("category"),
                task_id=arguments.get("task_id")
            )
        elif name == "workflow_flush_context":
            result = workflow_flush_context(
                task_id=arguments.get("task_id")
            )
        elif name == "workflow_get_context_usage":
            result = workflow_get_context_usage(
                task_id=arguments.get("task_id")
            )
        elif name == "workflow_prune_old_outputs":
            result = workflow_prune_old_outputs(
                keep_last_n=arguments.get("keep_last_n", 5),
                task_id=arguments.get("task_id")
            )
        elif name == "workflow_search_memories":
            result = workflow_search_memories(
                query=arguments["query"],
                task_ids=arguments.get("task_ids"),
                category=arguments.get("category"),
                max_results=arguments.get("max_results", 20)
            )
        elif name == "workflow_link_tasks":
            result = workflow_link_tasks(
                task_id=arguments["task_id"],
                related_task_ids=arguments["related_task_ids"],
                relationship=arguments.get("relationship", "related")
            )
        elif name == "workflow_get_linked_tasks":
            result = workflow_get_linked_tasks(
                task_id=arguments.get("task_id"),
                include_memories=arguments.get("include_memories", False)
            )
        elif name == "workflow_record_model_error":
            result = workflow_record_model_error(
                model=arguments["model"],
                error_type=arguments["error_type"],
                error_message=arguments.get("error_message", ""),
                task_id=arguments.get("task_id")
            )
        elif name == "workflow_record_model_success":
            result = workflow_record_model_success(
                model=arguments["model"]
            )
        elif name == "workflow_get_available_model":
            result = workflow_get_available_model(
                preferred_model=arguments.get("preferred_model")
            )
        elif name == "workflow_get_resilience_status":
            result = workflow_get_resilience_status()
        elif name == "workflow_clear_model_cooldown":
            result = workflow_clear_model_cooldown(
                model=arguments["model"]
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
