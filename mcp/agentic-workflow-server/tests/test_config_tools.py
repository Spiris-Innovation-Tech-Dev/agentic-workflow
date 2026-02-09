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
        assert PLATFORM_DIRS == [".claude", ".copilot", ".gemini"]
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
