"""
Extended tests for config_tools.py — covers every public/private function
with edge cases, validation warnings, and config cascade.

Run with: pytest tests/test_config_tools_extended.py -v
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentic_workflow_server.config_tools import (
    _deep_merge,
    _validate_config,
    _load_yaml,
    _get_valid_keys,
    _get_task_config_path,
    _is_beads_installed,
    _is_beads_initialized,
    config_get_effective,
    config_get_checkpoint,
    config_get_model,
    config_get_auto_action,
    config_get_loop_mode,
    config_get_beads,
    DEFAULT_CONFIG,
    PLATFORM_DIRS,
)


# ============================================================================
# _deep_merge
# ============================================================================

class TestDeepMerge:
    def test_merge_flat_dicts(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_merge_nested_dicts(self):
        base = {"x": {"a": 1, "b": 2}}
        override = {"x": {"b": 3, "c": 4}}
        result = _deep_merge(base, override)
        assert result == {"x": {"a": 1, "b": 3, "c": 4}}

    def test_override_scalar_in_nested(self):
        base = {"x": {"a": {"deep": True}}}
        override = {"x": {"a": "replaced"}}
        result = _deep_merge(base, override)
        assert result["x"]["a"] == "replaced"

    def test_add_new_key(self):
        base = {"a": 1}
        override = {"b": 2}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 2}

    def test_empty_override(self):
        base = {"a": 1, "b": {"c": 2}}
        result = _deep_merge(base, {})
        assert result == base

    def test_base_not_mutated(self):
        base = {"a": {"b": 1}}
        override = {"a": {"b": 2}}
        _deep_merge(base, override)
        assert base["a"]["b"] == 1


# ============================================================================
# _validate_config
# ============================================================================

class TestValidateConfig:
    def test_valid_config_no_warnings(self):
        config = {"knowledge_base": "docs/ai-context/"}
        warnings = _validate_config(config, DEFAULT_CONFIG)
        assert warnings == []

    def test_unknown_top_level_key(self):
        config = {"nonexistent_key": True}
        warnings = _validate_config(config, DEFAULT_CONFIG)
        assert len(warnings) == 1
        assert "Unknown config key" in warnings[0]
        assert "nonexistent_key" in warnings[0]

    def test_unknown_nested_key(self):
        config = {"checkpoints": {"planning": {"unknown_checkpoint": True}}}
        warnings = _validate_config(config, DEFAULT_CONFIG)
        assert len(warnings) == 1
        assert "checkpoints.planning.unknown_checkpoint" in warnings[0]

    def test_wrong_type_warning(self):
        config = {"knowledge_base": 123}
        warnings = _validate_config(config, DEFAULT_CONFIG)
        assert len(warnings) == 1
        assert "Invalid type" in warnings[0]
        assert "expected str" in warnings[0]

    def test_bool_vs_int_no_warning(self):
        """bool is subclass of int, so bool where int expected should not warn."""
        config = {"max_iterations": {"planning": True}}
        warnings = _validate_config(config, DEFAULT_CONFIG)
        # bool -> int is allowed; however int -> bool is not
        assert warnings == []

    def test_deeply_nested_unknown_key(self):
        config = {"loop_mode": {"phases": {"nonexistent_phase": True}}}
        warnings = _validate_config(config, DEFAULT_CONFIG)
        assert any("loop_mode.phases.nonexistent_phase" in w for w in warnings)

    def test_none_value_no_warning(self):
        config = {"knowledge_base": None}
        warnings = _validate_config(config, DEFAULT_CONFIG)
        assert warnings == []


# ============================================================================
# _load_yaml
# ============================================================================

class TestLoadYaml:
    def test_load_valid_yaml(self, tmp_path):
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("knowledge_base: docs/custom/\nmax_iterations:\n  planning: 5\n")
        result = _load_yaml(yaml_file)
        assert result is not None
        assert result["knowledge_base"] == "docs/custom/"

    def test_nonexistent_file_returns_none(self, tmp_path):
        result = _load_yaml(tmp_path / "nonexistent.yaml")
        assert result is None

    def test_malformed_yaml_returns_none(self, tmp_path):
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(":\n  :\n  - [invalid")
        result = _load_yaml(yaml_file)
        # May be None or empty depending on parser
        # The function catches exceptions and returns None
        assert result is None or result == {}

    def test_empty_file_returns_none(self, tmp_path):
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")
        result = _load_yaml(yaml_file)
        assert result is None

    def test_fallback_parser_without_yaml(self, tmp_path):
        """Test simple key:value parsing when yaml module unavailable."""
        yaml_file = tmp_path / "simple.yaml"
        yaml_file.write_text("knowledge_base: docs/\nenabled: true\ncount: 5\n")

        with patch("agentic_workflow_server.config_tools.yaml", None):
            result = _load_yaml(yaml_file)

        assert result is not None
        assert result["knowledge_base"] == "docs/"
        assert result["enabled"] is True
        assert result["count"] == 5

    def test_fallback_parser_false_value(self, tmp_path):
        yaml_file = tmp_path / "bools.yaml"
        yaml_file.write_text("enabled: false\n")

        with patch("agentic_workflow_server.config_tools.yaml", None):
            result = _load_yaml(yaml_file)

        assert result is not None
        assert result["enabled"] is False


# ============================================================================
# _get_task_config_path
# ============================================================================

class TestGetTaskConfigPath:
    def test_with_explicit_project_dir(self, tmp_path):
        result = _get_task_config_path("TASK_001", str(tmp_path))
        assert result == tmp_path / ".tasks" / "TASK_001" / "config.yaml"

    def test_with_default_cwd(self):
        result = _get_task_config_path("TASK_001")
        assert result == Path.cwd() / ".tasks" / "TASK_001" / "config.yaml"


# ============================================================================
# config_get_effective with task-level override
# ============================================================================

class TestConfigGetEffectiveTaskOverride:
    def test_task_config_overrides_project(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Project config
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text("knowledge_base: docs/project/\n")

        # Task config
        task_dir = project_dir / ".tasks" / "TASK_001"
        task_dir.mkdir(parents=True)
        (task_dir / "config.yaml").write_text("knowledge_base: docs/task/\n")

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_effective(task_id="TASK_001", project_dir=str(project_dir))

        assert result["config"]["knowledge_base"] == "docs/task/"
        assert result["has_task"] is True

    def test_task_config_merges_with_global(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Task config only overrides one key
        task_dir = project_dir / ".tasks" / "TASK_002"
        task_dir.mkdir(parents=True)
        (task_dir / "config.yaml").write_text("knowledge_base: docs/task-only/\n")

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_effective(task_id="TASK_002", project_dir=str(project_dir))

        # Task config applied
        assert result["config"]["knowledge_base"] == "docs/task-only/"
        # Default values still present
        assert "checkpoints" in result["config"]

    def test_nonexistent_task_config_ignored(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_effective(task_id="NONEXISTENT", project_dir=str(project_dir))

        assert result["has_task"] is False
        assert result["config"]["knowledge_base"] == DEFAULT_CONFIG["knowledge_base"]


# ============================================================================
# config_get_effective warnings
# ============================================================================

class TestConfigGetEffectiveWarnings:
    def test_returns_warnings_for_unknown_keys(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text("bad_key: value\n")

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_effective(project_dir=str(project_dir))

        assert len(result["warnings"]) >= 1
        assert any("bad_key" in w for w in result["warnings"])

    def test_returns_warnings_for_type_mismatch(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text("knowledge_base: 42\n")

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_effective(project_dir=str(project_dir))

        assert any("Invalid type" in w for w in result["warnings"])


# ============================================================================
# config_get_checkpoint
# ============================================================================

class TestConfigGetCheckpoint:
    def test_valid_checkpoint(self, tmp_path):
        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "noproject"):
            result = config_get_checkpoint("after_architect", "planning")

        assert result["checkpoint"] == "after_architect"
        assert result["enabled"] is True

    def test_unknown_checkpoint(self, tmp_path):
        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "noproject"):
            result = config_get_checkpoint("nonexistent", "planning")

        assert "error" in result
        assert "available_checkpoints" in result

    def test_unknown_category(self, tmp_path):
        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "noproject"):
            result = config_get_checkpoint("after_architect", "nonexistent_category")

        assert "error" in result
        # Category doesn't exist so available_checkpoints will be empty
        assert result["available_checkpoints"] == []

    def test_all_checkpoint_categories(self, tmp_path):
        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "noproject"):
            for category in ["planning", "implementation", "documentation", "feedback"]:
                checkpoints = DEFAULT_CONFIG["checkpoints"][category]
                for cp_name in checkpoints:
                    result = config_get_checkpoint(cp_name, category)
                    assert "enabled" in result, f"Failed for {category}.{cp_name}"


# ============================================================================
# config_get_model
# ============================================================================

class TestConfigGetModel:
    def test_known_agent(self, tmp_path):
        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "noproject"):
            result = config_get_model("architect")

        assert result["agent"] == "architect"
        assert result["model"] == "opus"

    def test_unknown_agent(self, tmp_path):
        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "noproject"):
            result = config_get_model("nonexistent_agent")

        assert "error" in result
        assert "available_agents" in result
        assert "architect" in result["available_agents"]

    def test_model_override_from_project_config(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text(
            "models:\n  architect: sonnet\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_model("architect", project_dir=str(project_dir))

        assert result["model"] == "sonnet"


# ============================================================================
# config_get_auto_action
# ============================================================================

class TestConfigGetAutoAction:
    def test_known_action(self, tmp_path):
        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "noproject"):
            result = config_get_auto_action("run_tests")

        assert result["action"] == "run_tests"
        assert result["allowed"] is True

    def test_unknown_action(self, tmp_path):
        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "noproject"):
            result = config_get_auto_action("nonexistent_action")

        assert "error" in result
        assert "available_actions" in result

    def test_action_override_from_project(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text(
            "auto_actions:\n  git_push: true\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_auto_action("git_push", project_dir=str(project_dir))

        assert result["allowed"] is True


# ============================================================================
# config_get_loop_mode
# ============================================================================

class TestConfigGetLoopMode:
    def test_returns_default_config(self, tmp_path):
        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "noproject"):
            result = config_get_loop_mode()

        assert result["enabled"] is False
        assert "phases" in result
        assert "max_iterations" in result
        assert "verification" in result

    def test_override_from_project(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text(
            "loop_mode:\n  enabled: true\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_loop_mode(project_dir=str(project_dir))

        assert result["enabled"] is True

    def test_all_fields_present(self, tmp_path):
        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "noproject"):
            result = config_get_loop_mode()

        assert "enabled" in result
        assert "phases" in result
        assert "max_iterations" in result
        assert "verification" in result
        assert "sources" in result


# ============================================================================
# config_get_beads
# ============================================================================

class TestConfigGetBeads:
    def test_auto_mode_installed_and_initialized(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text(
            "beads:\n  enabled: auto\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"), \
             patch("agentic_workflow_server.config_tools._is_beads_installed", return_value=True), \
             patch("agentic_workflow_server.config_tools._is_beads_initialized", return_value=True):
            result = config_get_beads(project_dir=str(project_dir))

        assert result["enabled"] is True
        assert result["detection"]["mode"] == "auto"
        assert result["detection"]["resolved_to"] is True

    def test_auto_mode_not_installed(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text(
            "beads:\n  enabled: auto\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"), \
             patch("agentic_workflow_server.config_tools._is_beads_installed", return_value=False), \
             patch("agentic_workflow_server.config_tools._is_beads_initialized", return_value=False):
            result = config_get_beads(project_dir=str(project_dir))

        assert result["enabled"] is False
        assert result["detection"]["mode"] == "auto"
        assert result["detection"]["resolved_to"] is False

    def test_manual_true(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text(
            "beads:\n  enabled: true\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_beads(project_dir=str(project_dir))

        assert result["enabled"] is True
        assert result["detection"]["mode"] == "manual"

    def test_manual_false(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text(
            "beads:\n  enabled: false\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_beads(project_dir=str(project_dir))

        assert result["enabled"] is False

    def test_default_values(self, tmp_path):
        """When no beads config, defaults should be applied."""
        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "noproject"):
            result = config_get_beads()

        assert result["enabled"] is False
        assert result["auto_link"] is True
        assert result["sync_status"] is True
        assert result["add_comments"] is True
        assert result["auto_create_issue"] is False

    def test_auto_installed_not_initialized(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text(
            "beads:\n  enabled: auto\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"), \
             patch("agentic_workflow_server.config_tools._is_beads_installed", return_value=True), \
             patch("agentic_workflow_server.config_tools._is_beads_initialized", return_value=False):
            result = config_get_beads(project_dir=str(project_dir))

        assert result["enabled"] is False
        assert result["detection"]["beads_installed"] is True
        assert result["detection"]["beads_initialized"] is False


# ============================================================================
# DEFAULT_CONFIG structure
# ============================================================================

class TestDefaultConfig:
    def test_all_expected_top_level_keys(self):
        expected = {
            "checkpoints", "knowledge_base", "task_directory",
            "max_iterations", "models", "worktree", "auto_actions", "loop_mode"
        }
        assert expected.issubset(set(DEFAULT_CONFIG.keys()))

    def test_models_has_all_agents(self):
        expected_agents = {
            "orchestrator", "architect", "developer", "reviewer",
            "skeptic", "implementer", "feedback", "technical-writer"
        }
        assert expected_agents == set(DEFAULT_CONFIG["models"].keys())

    def test_checkpoints_has_all_categories(self):
        expected = {"planning", "implementation", "documentation", "feedback"}
        assert expected == set(DEFAULT_CONFIG["checkpoints"].keys())


# ============================================================================
# _get_valid_keys
# ============================================================================

class TestGetValidKeys:
    def test_flat_dict(self):
        keys = _get_valid_keys({"a": 1, "b": 2})
        assert keys == {"a", "b"}

    def test_nested_dict_produces_dotted_keys(self):
        keys = _get_valid_keys({"x": {"y": {"z": 1}, "w": 2}})
        assert "x" in keys
        assert "x.y" in keys
        assert "x.y.z" in keys
        assert "x.w" in keys

    def test_default_config_valid_keys(self):
        keys = _get_valid_keys(DEFAULT_CONFIG)
        assert "checkpoints" in keys
        assert "checkpoints.planning" in keys
        assert "checkpoints.planning.after_architect" in keys
        assert "models.architect" in keys


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
