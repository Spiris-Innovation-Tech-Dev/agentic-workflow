"""
Tests for multi-platform config path detection.

Run with: pytest tests/test_config_tools.py -v
"""

import pytest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentic_workflow_server.config_tools import (
    _get_global_config_path,
    _get_project_config_path,
    config_get_effective,
    _load_yaml,
    _deep_merge,
    DEFAULT_CONFIG,
    PLATFORM_DIRS,
)


class TestMultiPlatformConfigPaths:
    """Test that config loads from .claude/ and .copilot/ directories."""

    def test_global_path_prefers_claude(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        copilot_dir = tmp_path / ".copilot"
        claude_dir.mkdir()
        copilot_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text("checkpoints: {}")
        (copilot_dir / "workflow-config.yaml").write_text("checkpoints: {}")

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path):
            result = _get_global_config_path()
            assert ".claude" in str(result)

    def test_global_path_falls_back_to_copilot(self, tmp_path):
        copilot_dir = tmp_path / ".copilot"
        copilot_dir.mkdir()
        (copilot_dir / "workflow-config.yaml").write_text("checkpoints: {}")

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path):
            result = _get_global_config_path()
            assert ".copilot" in str(result)

    def test_global_path_defaults_to_claude_when_neither_exists(self, tmp_path):
        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path):
            result = _get_global_config_path()
            assert ".claude" in str(result)
            assert not result.exists()

    def test_project_path_prefers_claude(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        copilot_dir = tmp_path / ".copilot"
        claude_dir.mkdir()
        copilot_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text("checkpoints: {}")
        (copilot_dir / "workflow-config.yaml").write_text("checkpoints: {}")

        result = _get_project_config_path(str(tmp_path))
        assert ".claude" in str(result)

    def test_project_path_falls_back_to_copilot(self, tmp_path):
        copilot_dir = tmp_path / ".copilot"
        copilot_dir.mkdir()
        (copilot_dir / "workflow-config.yaml").write_text("checkpoints: {}")

        result = _get_project_config_path(str(tmp_path))
        assert ".copilot" in str(result)

    def test_project_path_defaults_to_claude_when_neither_exists(self, tmp_path):
        result = _get_project_config_path(str(tmp_path))
        assert ".claude" in str(result)
        assert not result.exists()

    def test_project_path_uses_cwd_when_no_dir(self, tmp_path):
        copilot_dir = tmp_path / ".copilot"
        copilot_dir.mkdir()
        (copilot_dir / "workflow-config.yaml").write_text("checkpoints: {}")

        with patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path):
            result = _get_project_config_path()
            assert ".copilot" in str(result)


class TestEffectiveConfigMultiPlatform:
    """Test that config_get_effective works with .copilot/ directories."""

    def test_loads_global_from_copilot(self, tmp_path):
        copilot_dir = tmp_path / ".copilot"
        copilot_dir.mkdir()
        (copilot_dir / "workflow-config.yaml").write_text(
            "knowledge_base: docs/custom/\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "nonexistent"):
            result = config_get_effective()
            assert result["has_global"] is True
            assert result["config"]["knowledge_base"] == "docs/custom/"
            assert ".copilot" in result["sources"][0]

    def test_loads_project_from_copilot(self, tmp_path):
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        copilot_dir = project_dir / ".copilot"
        copilot_dir.mkdir()
        (copilot_dir / "workflow-config.yaml").write_text(
            "knowledge_base: docs/project/\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_effective(project_dir=str(project_dir))
            assert result["has_project"] is True
            assert result["config"]["knowledge_base"] == "docs/project/"

    def test_claude_global_takes_precedence_over_copilot_global(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        copilot_dir = tmp_path / ".copilot"
        claude_dir.mkdir()
        copilot_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text(
            "knowledge_base: docs/claude/\n"
        )
        (copilot_dir / "workflow-config.yaml").write_text(
            "knowledge_base: docs/copilot/\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "nonexistent"):
            result = config_get_effective()
            assert result["config"]["knowledge_base"] == "docs/claude/"

    def test_platform_dirs_constant(self):
        assert PLATFORM_DIRS == [".claude", ".copilot", ".gemini", ".opencode"]
        assert PLATFORM_DIRS[0] == ".claude"  # claude must be first (precedence)


class TestGeminiConfigPaths:
    """Test that config loads from .gemini/ directories as fallback."""

    def test_global_path_falls_back_to_gemini(self, tmp_path):
        gemini_dir = tmp_path / ".gemini"
        gemini_dir.mkdir()
        (gemini_dir / "workflow-config.yaml").write_text("checkpoints: {}")

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path):
            result = _get_global_config_path()
            assert ".gemini" in str(result)

    def test_project_path_falls_back_to_gemini(self, tmp_path):
        gemini_dir = tmp_path / ".gemini"
        gemini_dir.mkdir()
        (gemini_dir / "workflow-config.yaml").write_text("checkpoints: {}")

        result = _get_project_config_path(str(tmp_path))
        assert ".gemini" in str(result)

    def test_claude_preferred_over_gemini(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        gemini_dir = tmp_path / ".gemini"
        claude_dir.mkdir()
        gemini_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text("knowledge_base: docs/claude/")
        (gemini_dir / "workflow-config.yaml").write_text("knowledge_base: docs/gemini/")

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "nonexistent"):
            result = config_get_effective()
            assert result["config"]["knowledge_base"] == "docs/claude/"

    def test_copilot_preferred_over_gemini(self, tmp_path):
        copilot_dir = tmp_path / ".copilot"
        gemini_dir = tmp_path / ".gemini"
        copilot_dir.mkdir()
        gemini_dir.mkdir()
        (copilot_dir / "workflow-config.yaml").write_text("knowledge_base: docs/copilot/")
        (gemini_dir / "workflow-config.yaml").write_text("knowledge_base: docs/gemini/")

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "nonexistent"):
            result = config_get_effective()
            assert result["config"]["knowledge_base"] == "docs/copilot/"

    def test_loads_global_from_gemini(self, tmp_path):
        gemini_dir = tmp_path / ".gemini"
        gemini_dir.mkdir()
        (gemini_dir / "workflow-config.yaml").write_text(
            "knowledge_base: docs/gemini/\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "nonexistent"):
            result = config_get_effective()
            assert result["has_global"] is True
            assert result["config"]["knowledge_base"] == "docs/gemini/"
            assert ".gemini" in result["sources"][0]


class TestOpenCodeConfigPaths:
    """Test that config loads from .opencode/ directories as fallback."""

    def test_global_path_falls_back_to_opencode(self, tmp_path):
        opencode_dir = tmp_path / ".opencode"
        opencode_dir.mkdir()
        (opencode_dir / "workflow-config.yaml").write_text("checkpoints: {}")

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path):
            result = _get_global_config_path()
            assert ".opencode" in str(result)

    def test_project_path_falls_back_to_opencode(self, tmp_path):
        opencode_dir = tmp_path / ".opencode"
        opencode_dir.mkdir()
        (opencode_dir / "workflow-config.yaml").write_text("checkpoints: {}")

        result = _get_project_config_path(str(tmp_path))
        assert ".opencode" in str(result)

    def test_claude_preferred_over_opencode(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        opencode_dir = tmp_path / ".opencode"
        claude_dir.mkdir()
        opencode_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text("knowledge_base: docs/claude/")
        (opencode_dir / "workflow-config.yaml").write_text("knowledge_base: docs/opencode/")

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "nonexistent"):
            result = config_get_effective()
            assert result["config"]["knowledge_base"] == "docs/claude/"

    def test_gemini_preferred_over_opencode(self, tmp_path):
        gemini_dir = tmp_path / ".gemini"
        opencode_dir = tmp_path / ".opencode"
        gemini_dir.mkdir()
        opencode_dir.mkdir()
        (gemini_dir / "workflow-config.yaml").write_text("knowledge_base: docs/gemini/")
        (opencode_dir / "workflow-config.yaml").write_text("knowledge_base: docs/opencode/")

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "nonexistent"):
            result = config_get_effective()
            assert result["config"]["knowledge_base"] == "docs/gemini/"

    def test_loads_global_from_opencode(self, tmp_path):
        opencode_dir = tmp_path / ".opencode"
        opencode_dir.mkdir()
        (opencode_dir / "workflow-config.yaml").write_text(
            "knowledge_base: docs/opencode/\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "nonexistent"):
            result = config_get_effective()
            assert result["has_global"] is True
            assert result["config"]["knowledge_base"] == "docs/opencode/"
            assert ".opencode" in result["sources"][0]


class TestWorktreeExtensionConfig:
    """Test worktree Jira, post_setup_commands, install_deps, and copy_settings config keys."""

    def test_worktree_jira_in_defaults(self):
        """jira sub-dict exists in DEFAULT_CONFIG worktree with transitions."""
        worktree = DEFAULT_CONFIG["worktree"]
        assert "jira" in worktree
        assert worktree["jira"]["auto_assign"] == "never"
        transitions = worktree["jira"]["transitions"]
        assert "on_create" in transitions
        assert "on_complete" in transitions
        assert "on_cleanup" in transitions
        # All hooks default to empty (no transition)
        for hook in ["on_create", "on_complete", "on_cleanup"]:
            assert transitions[hook]["to"] == ""
            assert transitions[hook]["only_from"] == []
        # on_cleanup defaults to prompt mode
        assert transitions["on_cleanup"]["mode"] == "prompt"
        assert transitions["on_create"]["mode"] == "auto"
        assert transitions["on_complete"]["mode"] == "auto"

    def test_worktree_post_setup_commands_in_defaults(self):
        """post_setup_commands exists and defaults to empty list."""
        worktree = DEFAULT_CONFIG["worktree"]
        assert "post_setup_commands" in worktree
        assert worktree["post_setup_commands"] == []

    def test_worktree_install_deps_in_defaults(self):
        """install_deps exists and defaults to 'auto'."""
        worktree = DEFAULT_CONFIG["worktree"]
        assert "install_deps" in worktree
        assert worktree["install_deps"] == "auto"

    def test_worktree_copy_settings_in_defaults(self):
        """copy_settings exists in DEFAULT_CONFIG (was missing before — bug fix)."""
        worktree = DEFAULT_CONFIG["worktree"]
        assert "copy_settings" in worktree
        assert worktree["copy_settings"] is True

    def test_jira_auto_assign_override_merges(self, tmp_path):
        """Project-level worktree.jira.auto_assign overrides global default."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text(
            "worktree:\n  jira:\n    auto_assign: auto\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_effective(project_dir=str(project_dir))

        jira = result["config"]["worktree"]["jira"]
        assert jira["auto_assign"] == "auto"
        # transitions should still be default (deep merge preserves sibling keys)
        assert jira["transitions"]["on_create"]["to"] == ""

    def test_jira_transition_on_create_override(self, tmp_path):
        """Project-level worktree.jira.transitions.on_create.to overrides default."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text(
            "worktree:\n  jira:\n    transitions:\n      on_create:\n        to: In Progress\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_effective(project_dir=str(project_dir))

        jira = result["config"]["worktree"]["jira"]
        assert jira["transitions"]["on_create"]["to"] == "In Progress"
        assert jira["auto_assign"] == "never"
        # Other hooks should retain defaults
        assert jira["transitions"]["on_complete"]["to"] == ""
        assert jira["transitions"]["on_cleanup"]["to"] == ""

    def test_jira_transition_only_from_override(self, tmp_path):
        """Project-level only_from list overrides default empty list."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text(
            "worktree:\n  jira:\n    transitions:\n      on_cleanup:\n"
            "        to: Test\n        only_from:\n          - In Review\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_effective(project_dir=str(project_dir))

        cleanup = result["config"]["worktree"]["jira"]["transitions"]["on_cleanup"]
        assert cleanup["to"] == "Test"
        assert cleanup["only_from"] == ["In Review"]
        # mode should still be default prompt (deep merge)
        assert cleanup["mode"] == "prompt"

    def test_jira_all_transitions_configured(self, tmp_path):
        """Full enterprise config with all three lifecycle hooks."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text(
            "worktree:\n  jira:\n    auto_assign: auto\n    transitions:\n"
            "      on_create:\n        to: In Progress\n"
            "      on_complete:\n        to: In Review\n"
            "      on_cleanup:\n        to: Test\n        mode: prompt\n"
            "        only_from:\n          - In Review\n          - In Progress\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_effective(project_dir=str(project_dir))

        jira = result["config"]["worktree"]["jira"]
        assert jira["auto_assign"] == "auto"
        assert jira["transitions"]["on_create"]["to"] == "In Progress"
        assert jira["transitions"]["on_complete"]["to"] == "In Review"
        assert jira["transitions"]["on_cleanup"]["to"] == "Test"
        assert jira["transitions"]["on_cleanup"]["only_from"] == ["In Review", "In Progress"]

    def test_post_setup_commands_override(self, tmp_path):
        """Project-level post_setup_commands overrides empty default."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text(
            "worktree:\n  post_setup_commands:\n"
            "    - echo setup {task_id}\n"
            "    - npm run prepare\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_effective(project_dir=str(project_dir))

        cmds = result["config"]["worktree"]["post_setup_commands"]
        assert len(cmds) == 2
        assert "echo setup {task_id}" in cmds[0]

    def test_install_deps_never_override(self, tmp_path):
        """Project can set install_deps to 'never'."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text(
            "worktree:\n  install_deps: never\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_effective(project_dir=str(project_dir))

        assert result["config"]["worktree"]["install_deps"] == "never"

    def test_copy_settings_no_unknown_key_warning(self, tmp_path):
        """copy_settings should not trigger 'Unknown config key' warning."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "workflow-config.yaml").write_text(
            "worktree:\n  copy_settings: false\n"
        )

        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"):
            result = config_get_effective(project_dir=str(project_dir))

        assert result["config"]["worktree"]["copy_settings"] is False
        copy_warnings = [w for w in result["warnings"] if "copy_settings" in w]
        assert copy_warnings == []

    def test_effective_config_returns_all_new_worktree_keys(self, tmp_path):
        """config_get_effective returns all new worktree keys with defaults."""
        with patch("agentic_workflow_server.config_tools.Path.home", return_value=tmp_path / "nohome"), \
             patch("agentic_workflow_server.config_tools.Path.cwd", return_value=tmp_path / "noproject"):
            result = config_get_effective()

        wt = result["config"]["worktree"]
        assert wt["copy_settings"] is True
        assert wt["install_deps"] == "auto"
        assert wt["jira"]["auto_assign"] == "never"
        assert wt["jira"]["transitions"]["on_create"]["to"] == ""
        assert wt["jira"]["transitions"]["on_complete"]["to"] == ""
        assert wt["jira"]["transitions"]["on_cleanup"]["to"] == ""
        assert wt["post_setup_commands"] == []
