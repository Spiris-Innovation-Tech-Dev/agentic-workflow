#!/usr/bin/env python3
"""
Context Preparation for Agentic Workflow

Handles Gemini + Repomix integration for large-context codebase analysis.
This script prepares context for agents by:
1. Checking prerequisites (repomix, gemini CLI)
2. Discovering relevant files based on task description
3. Running repomix to aggregate files
4. Running Gemini analysis with structured prompts

Usage:
    from context_preparation import ContextPreparation

    prep = ContextPreparation(task_dir=".tasks/TASK_001", task_description="Add auth")
    result = prep.prepare()
"""

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class ContextPreparationResult:
    """Result of context preparation."""
    status: str  # "complete", "failed", "skipped"
    gemini_analysis_path: Optional[str] = None
    repomix_output_path: Optional[str] = None
    files_discovered: int = 0
    fallback_used: bool = False
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


class ContextPreparation:
    """Handles context preparation for agentic workflows."""

    GEMINI_ANALYSIS_PROMPT = """Analyze this codebase context for the following task.

Task: {task_description}

Provide your analysis in the following sections. Each section should be comprehensive and actionable.

## ARCHITECTURAL_CONTEXT
Analyze the codebase architecture relevant to this task:
- Key modules, services, and their relationships
- Design patterns in use
- Integration points that will be affected
- Existing conventions to follow
- Potential architectural concerns or constraints

## IMPLEMENTATION_PATTERNS
Document patterns the developer should follow:
- Code style and naming conventions
- Error handling patterns
- Logging and monitoring patterns
- Testing patterns (unit, integration)
- File organization conventions
- Import conventions

## REVIEW_CHECKLIST
Provide a checklist for the reviewer:
- Security considerations specific to this task
- Performance considerations
- Code quality checks
- Patterns that must be followed
- Common mistakes to avoid

## FAILURE_MODES
Analyze potential failure scenarios:
- Edge cases to consider
- Error scenarios and how they should be handled
- Concurrency/race condition risks
- External dependency failure modes
- Data integrity risks

## DOCUMENTATION_CONTEXT
Note documentation needs:
- Existing documentation that may need updates
- Undocumented patterns the technical writer should document
- API documentation requirements
- Architecture documentation updates
"""

    def __init__(
        self,
        task_dir: str,
        task_description: str,
        config: Optional[dict] = None,
        knowledge_base: str = "docs/ai-context/"
    ):
        self.task_dir = Path(task_dir)
        self.task_description = task_description
        self.config = config or {}
        self.knowledge_base = knowledge_base
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def check_prerequisites(self) -> tuple[bool, bool]:
        """
        Check if repomix and gemini CLI are available.

        Returns:
            Tuple of (repomix_available, gemini_available)
        """
        repomix_available = shutil.which("repomix") is not None
        gemini_available = shutil.which("gemini") is not None

        if not repomix_available:
            self.warnings.append("repomix CLI not found in PATH")
        if not gemini_available:
            self.warnings.append("gemini CLI not found in PATH")

        return repomix_available, gemini_available

    def discover_relevant_files(self) -> dict[str, list[str]]:
        """
        Discover files relevant to the task.

        Returns:
            Dict with categories: core, base_classes, referenced, examples, docs
        """
        discovered = {
            "core": [],
            "base_classes": [],
            "referenced": [],
            "examples": [],
            "docs": []
        }

        # Extract keywords from task description
        keywords = self._extract_keywords(self.task_description)

        # Search for files matching keywords
        for keyword in keywords:
            files = self._search_files(keyword)
            for f in files[:5]:  # Limit per keyword
                if f not in discovered["core"]:
                    discovered["core"].append(f)

        # Find base classes and interfaces
        for core_file in discovered["core"]:
            base_classes = self._find_base_classes(core_file)
            for bc in base_classes:
                if bc not in discovered["base_classes"]:
                    discovered["base_classes"].append(bc)

        # Find test files as examples
        test_patterns = ["test_*.py", "*_test.py", "*.test.ts", "*.spec.ts", "*_test.go"]
        for pattern in test_patterns:
            for test_file in Path(".").rglob(pattern):
                if self._is_relevant_test(test_file, keywords):
                    if str(test_file) not in discovered["examples"]:
                        discovered["examples"].append(str(test_file))

        # Add knowledge base docs
        kb_path = Path(self.knowledge_base)
        if kb_path.exists():
            for doc in kb_path.rglob("*.md"):
                discovered["docs"].append(str(doc))

        # Add root-level docs
        for doc in ["README.md", "CONTRIBUTING.md", "ARCHITECTURE.md"]:
            if Path(doc).exists():
                discovered["docs"].append(doc)

        return discovered

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract meaningful keywords from task description."""
        # Remove common words
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
            "be", "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "must", "shall", "can", "need",
            "add", "create", "implement", "update", "fix", "change", "modify"
        }

        # Extract words, convert to lowercase
        words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_]*\b', text.lower())

        # Filter and deduplicate
        keywords = []
        for word in words:
            if word not in stop_words and len(word) > 2:
                if word not in keywords:
                    keywords.append(word)

        return keywords[:10]  # Limit to top 10

    def _search_files(self, keyword: str) -> list[str]:
        """Search for files containing keyword using ag or grep."""
        try:
            # Try ag (silver searcher) first
            result = subprocess.run(
                ["ag", "-l", keyword, "--ignore", "node_modules", "--ignore", "dist"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return result.stdout.strip().split("\n")[:20]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        try:
            # Fall back to grep
            result = subprocess.run(
                ["grep", "-rl", keyword, ".", "--include=*.py", "--include=*.ts",
                 "--include=*.js", "--include=*.go", "--include=*.rs"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return result.stdout.strip().split("\n")[:20]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return []

    def _find_base_classes(self, file_path: str) -> list[str]:
        """Find base classes/interfaces imported by a file."""
        base_classes = []
        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Python: from x import Base, Interface
            for match in re.finditer(r'from\s+(\S+)\s+import\s+([^;\n]+)', content):
                module = match.group(1)
                imports = match.group(2)
                if any(word in imports for word in ["Base", "Abstract", "Interface", "Protocol"]):
                    base_file = module.replace(".", "/") + ".py"
                    if Path(base_file).exists():
                        base_classes.append(base_file)

            # TypeScript/JS: extends/implements
            for match in re.finditer(r'(?:extends|implements)\s+(\w+)', content):
                class_name = match.group(1)
                # Search for class definition
                found = self._search_files(f"class {class_name}")
                base_classes.extend(found[:2])

        except Exception:
            pass

        return base_classes

    def _is_relevant_test(self, test_file: Path, keywords: list[str]) -> bool:
        """Check if a test file is relevant to the task."""
        try:
            content = test_file.read_text().lower()
            return any(kw in content for kw in keywords)
        except Exception:
            return False

    def generate_repomix_config(self, discovered_files: dict[str, list[str]]) -> str:
        """
        Generate repomix configuration file.

        Returns:
            Path to the generated config file
        """
        all_files = []
        for category_files in discovered_files.values():
            all_files.extend(category_files)

        # Remove duplicates and filter non-existent
        all_files = list(set(f for f in all_files if f and Path(f).exists()))

        config = {
            "include": all_files,
            "ignore": [
                "**/*.test.ts",
                "**/node_modules/**",
                "**/*.d.ts",
                "**/dist/**",
                "**/__pycache__/**",
                "**/.git/**"
            ],
            "output": {
                "filePath": str(self.task_dir / "repomix-output.txt"),
                "style": "xml",
                "showLineNumbers": True
            }
        }

        config_path = self.task_dir / "repomix-context.json"
        self.task_dir.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        return str(config_path)

    def run_repomix(self, config_path: str) -> Optional[str]:
        """
        Run repomix to aggregate files.

        Returns:
            Path to output file, or None if failed
        """
        try:
            result = subprocess.run(
                ["repomix", "-c", config_path],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode != 0:
                self.errors.append(f"repomix failed: {result.stderr}")
                return None

            output_path = self.task_dir / "repomix-output.txt"
            if output_path.exists():
                return str(output_path)
            else:
                self.errors.append("repomix did not create output file")
                return None

        except subprocess.TimeoutExpired:
            self.errors.append("repomix timed out after 120 seconds")
            return None
        except FileNotFoundError:
            self.errors.append("repomix not found")
            return None

    def run_gemini_analysis(self, context_path: str) -> Optional[str]:
        """
        Run Gemini analysis on the aggregated context.

        Returns:
            Path to analysis file, or None if failed
        """
        prompt = self.GEMINI_ANALYSIS_PROMPT.format(
            task_description=self.task_description
        )

        analysis_path = self.task_dir / "gemini-analysis.md"

        try:
            # Run gemini with the context file
            result = subprocess.run(
                ["gemini", "-p", f"@{context_path}\n\n{prompt}"],
                capture_output=True,
                text=True,
                timeout=self.config.get("gemini_timeout", 120)
            )

            if result.returncode != 0:
                self.errors.append(f"gemini failed: {result.stderr}")
                return None

            # Write analysis output
            with open(analysis_path, "w") as f:
                f.write(result.stdout)

            return str(analysis_path)

        except subprocess.TimeoutExpired:
            self.errors.append(f"gemini timed out")
            # Check for partial output
            if analysis_path.exists() and analysis_path.stat().st_size > 0:
                self.warnings.append("gemini timed out but partial output available")
                return str(analysis_path)
            return None
        except FileNotFoundError:
            self.errors.append("gemini not found")
            return None

    def update_state(self, result: ContextPreparationResult) -> None:
        """Update task state with context preparation results."""
        state_file = self.task_dir / "state.json"

        state = {}
        if state_file.exists():
            with open(state_file) as f:
                state = json.load(f)

        state["context_preparation"] = {
            "status": result.status,
            "started_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat() if result.status == "complete" else None,
            "gemini_analysis_path": result.gemini_analysis_path,
            "repomix_output_path": result.repomix_output_path,
            "files_discovered": result.files_discovered,
            "fallback_used": result.fallback_used,
            "errors": result.errors,
            "warnings": result.warnings
        }

        state["updated_at"] = datetime.now().isoformat()

        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

    def prepare(self) -> ContextPreparationResult:
        """
        Run the full context preparation pipeline.

        Returns:
            ContextPreparationResult with status and paths
        """
        result = ContextPreparationResult(status="pending")

        # Check prerequisites
        repomix_ok, gemini_ok = self.check_prerequisites()

        fallback_mode = self.config.get("fallback_to_opus", True)

        if not repomix_ok or not gemini_ok:
            if fallback_mode:
                result.status = "skipped"
                result.fallback_used = True
                result.warnings = self.warnings
                self.update_state(result)
                return result
            else:
                result.status = "failed"
                result.errors = ["Prerequisites not met: " + ", ".join(self.warnings)]
                self.update_state(result)
                return result

        # Discover relevant files
        discovered = self.discover_relevant_files()
        result.files_discovered = sum(len(files) for files in discovered.values())

        if result.files_discovered == 0:
            result.warnings.append("No relevant files discovered")

        # Generate repomix config
        config_path = self.generate_repomix_config(discovered)

        # Run repomix
        repomix_output = self.run_repomix(config_path)
        if not repomix_output:
            if fallback_mode:
                result.status = "skipped"
                result.fallback_used = True
                result.errors = self.errors
                result.warnings = self.warnings
                self.update_state(result)
                return result
            else:
                result.status = "failed"
                result.errors = self.errors
                self.update_state(result)
                return result

        result.repomix_output_path = repomix_output

        # Check if native context is preferred and output fits within threshold
        prefer_native = self.config.get("prefer_native_context", False)
        threshold_kb = self.config.get("native_context_threshold_kb", 800)
        if prefer_native:
            repomix_size_kb = Path(repomix_output).stat().st_size / 1024
            if repomix_size_kb <= threshold_kb:
                result.status = "skipped"
                result.warnings.append(
                    f"Repomix output ({repomix_size_kb:.0f}KB) fits within native context "
                    f"threshold ({threshold_kb}KB). Skipping Gemini analysis — pass "
                    f"repomix output directly to Opus 4.6's 1M token context."
                )
                self.update_state(result)
                return result

        # Run Gemini analysis
        analysis_path = self.run_gemini_analysis(repomix_output)
        if not analysis_path:
            if fallback_mode:
                result.status = "skipped"
                result.fallback_used = True
                result.errors = self.errors
                result.warnings = self.warnings
                self.update_state(result)
                return result
            else:
                result.status = "failed"
                result.errors = self.errors
                self.update_state(result)
                return result

        result.gemini_analysis_path = analysis_path
        result.status = "complete"
        result.errors = self.errors
        result.warnings = self.warnings

        self.update_state(result)
        return result


def extract_section(analysis_path: str, agent_type: str) -> Optional[str]:
    """
    Extract a specific section from Gemini analysis for an agent.

    Args:
        analysis_path: Path to gemini-analysis.md
        agent_type: One of 'architect', 'developer', 'reviewer', 'skeptic'

    Returns:
        The extracted section content, or None if not found
    """
    section_markers = {
        "architect": "## ARCHITECTURAL_CONTEXT",
        "developer": "## IMPLEMENTATION_PATTERNS",
        "reviewer": "## REVIEW_CHECKLIST",
        "skeptic": "## FAILURE_MODES",
        "technical_writer": "## DOCUMENTATION_CONTEXT"
    }

    if agent_type not in section_markers:
        return None

    try:
        with open(analysis_path, "r") as f:
            content = f.read()
    except Exception:
        return None

    marker = section_markers[agent_type]
    start_idx = content.find(marker)

    if start_idx == -1:
        return None

    # Find the next section (next ##)
    search_start = start_idx + len(marker)
    end_idx = content.find("\n## ", search_start)

    if end_idx == -1:
        # Last section in file
        return content[start_idx:]
    else:
        return content[start_idx:end_idx]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Prepare context for agentic workflow")
    parser.add_argument("--task-dir", "-d", required=True, help="Task directory path")
    parser.add_argument("--description", "-t", required=True, help="Task description")
    parser.add_argument("--knowledge-base", "-k", default="docs/ai-context/",
                        help="Knowledge base directory")
    parser.add_argument("--no-fallback", action="store_true",
                        help="Fail instead of falling back if tools unavailable")
    parser.add_argument("--extract-section", "-e",
                        choices=["architect", "developer", "reviewer", "skeptic", "technical_writer"],
                        help="Extract a specific section from existing analysis")

    args = parser.parse_args()

    if args.extract_section:
        analysis_path = Path(args.task_dir) / "gemini-analysis.md"
        if analysis_path.exists():
            section = extract_section(str(analysis_path), args.extract_section)
            if section:
                print(section)
            else:
                print(f"Section for {args.extract_section} not found", file=sys.stderr)
                sys.exit(1)
        else:
            print("No gemini-analysis.md found", file=sys.stderr)
            sys.exit(1)
    else:
        config = {"fallback_to_opus": not args.no_fallback}

        prep = ContextPreparation(
            task_dir=args.task_dir,
            task_description=args.description,
            config=config,
            knowledge_base=args.knowledge_base
        )

        result = prep.prepare()

        print(json.dumps({
            "status": result.status,
            "gemini_analysis_path": result.gemini_analysis_path,
            "repomix_output_path": result.repomix_output_path,
            "files_discovered": result.files_discovered,
            "fallback_used": result.fallback_used,
            "errors": result.errors,
            "warnings": result.warnings
        }, indent=2))

        sys.exit(0 if result.status in ("complete", "skipped") else 1)
