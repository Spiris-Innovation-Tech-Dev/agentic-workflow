# Copilot CLI Installer for Agentic Workflow
# This script installs the agentic-workflow system for GitHub Copilot CLI

param(
    [switch]$Force,
    [switch]$SkipMcp
)

$ErrorActionPreference = "Stop"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$COPILOT_DIR = "$env:USERPROFILE\.copilot"
$VERSION = Get-Content "$SCRIPT_DIR\VERSION" -ErrorAction SilentlyContinue
if (-not $VERSION) { $VERSION = "unknown" }

Write-Host "========================================"  -ForegroundColor Cyan
Write-Host "  Agentic Workflow Copilot Installer"     -ForegroundColor Cyan
Write-Host "  Version: $VERSION"                       -ForegroundColor Cyan
Write-Host "========================================"  -ForegroundColor Cyan
Write-Host ""

# Check prerequisites
Write-Host "Checking prerequisites..." -ForegroundColor Yellow

# Check Python 3 (try python3 first, then python)
$pythonCmd = $null
if (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pythonCmd = "python3"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
}

if (-not $pythonCmd) {
    Write-Host "  X Python 3 not found" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Python 3 and re-run this script." -ForegroundColor Red
    exit 1
}
$pythonVersion = & $pythonCmd --version 2>&1
Write-Host "  + Python found: $pythonVersion" -ForegroundColor Green

# Check Copilot CLI
if (-not (Get-Command copilot -ErrorAction SilentlyContinue)) {
    Write-Host "  ! Copilot CLI not found" -ForegroundColor Yellow
    Write-Host "    Install with: winget install GitHub.Copilot" -ForegroundColor Yellow
} else {
    Write-Host "  + Copilot CLI found" -ForegroundColor Green
}

Write-Host ""

# Build platform-specific agents using build script
Write-Host ""
Write-Host "Building agents for Copilot..." -ForegroundColor Yellow
& $pythonCmd "$SCRIPT_DIR\scripts\build-agents.py" copilot --output .
if ($LASTEXITCODE -ne 0) {
    Write-Host "  X Failed to build agents" -ForegroundColor Red
    exit 1
}

# Install agents to user config dir for /agent discovery
Write-Host ""
Write-Host "Installing agents to user config..." -ForegroundColor Yellow
New-Item -ItemType Directory -Path "$COPILOT_DIR\agents" -Force | Out-Null

# Remove old-format files from previous installs (crew-*.md without .agent.md extension)
$oldFiles = Get-ChildItem "$COPILOT_DIR\agents\crew-*.md" -ErrorAction SilentlyContinue | Where-Object { $_.Name -notlike "*.agent.md" }
foreach ($old in $oldFiles) {
    Remove-Item $old.FullName -Force
    Write-Host "  - Removed old format: $($old.Name)" -ForegroundColor Yellow
}

Copy-Item ".github\agents\*.agent.md" -Destination "$COPILOT_DIR\agents\" -Force
Write-Host "  + Copied agents to $COPILOT_DIR\agents" -ForegroundColor Green

# Copy repository instructions
Write-Host ""
Write-Host "Installing repository instructions..." -ForegroundColor Yellow
if (Test-Path "$SCRIPT_DIR\.github\copilot-instructions.md") {
    # Instructions stay in repo, not copied to user dir
    Write-Host "  + copilot-instructions.md (in repository .github/)" -ForegroundColor Green
} else {
    Write-Host "  ! copilot-instructions.md not found" -ForegroundColor Yellow
}

# Copy config (backup existing if present)
Write-Host ""
Write-Host "Installing config..." -ForegroundColor Yellow
if (Test-Path "$COPILOT_DIR\workflow-config.yaml") {
    $timestamp = Get-Date -Format "yyyyMMddHHmmss"
    Copy-Item "$COPILOT_DIR\workflow-config.yaml" "$COPILOT_DIR\workflow-config.yaml.backup.$timestamp"
    Write-Host "  ! Existing config backed up" -ForegroundColor Yellow
}
Copy-Item "$SCRIPT_DIR\config\workflow-config.yaml" "$COPILOT_DIR\"
Write-Host "  + workflow-config.yaml" -ForegroundColor Green

# Install MCP server
if (-not $SkipMcp) {
    Write-Host ""
    Write-Host "Installing MCP server..." -ForegroundColor Yellow
    $MCP_SERVER_DIR = "$SCRIPT_DIR\mcp\agentic-workflow-server"

    if (Test-Path $MCP_SERVER_DIR) {
        try {
            Write-Host "  Installing Python package..." -ForegroundColor Gray
            Push-Location $MCP_SERVER_DIR
            $output = & $pythonCmd -m pip install -q -e . 2>&1
            Pop-Location
            Write-Host "  + MCP server package installed" -ForegroundColor Green
        } catch {
            Write-Host "  ! Failed to install MCP server package" -ForegroundColor Yellow
            Write-Host "    Try manually: pip install -e $MCP_SERVER_DIR" -ForegroundColor Yellow
        }

        # Register MCP server with Copilot
        Write-Host "  Registering MCP server with Copilot..." -ForegroundColor Gray
        $mcpConfigPath = "$COPILOT_DIR\mcp-config.json"

        # Read existing config or create new
        if (Test-Path $mcpConfigPath) {
            $mcpConfig = Get-Content $mcpConfigPath | ConvertFrom-Json
        } else {
            $mcpConfig = @{ mcpServers = @{} }
        }

        # Add agentic-workflow server
        if (-not $mcpConfig.mcpServers) {
            $mcpConfig | Add-Member -NotePropertyName mcpServers -NotePropertyValue @{} -Force
        }

        $mcpConfig.mcpServers | Add-Member -NotePropertyName "agentic-workflow" -NotePropertyValue @{
            command = $pythonCmd
            args = @("-m", "agentic_workflow_server.server")
            env = @{}
        } -Force

        # Ensure GitHub server is also present (Copilot default)
        if (-not $mcpConfig.mcpServers."github-mcp-server") {
            $mcpConfig.mcpServers | Add-Member -NotePropertyName "github-mcp-server" -NotePropertyValue @{
                command = "npx"
                args = @("-y", "@modelcontextprotocol/server-github")
                env = @{}
            } -Force
        }

        # Save config
        $mcpConfig | ConvertTo-Json -Depth 10 | Out-File $mcpConfigPath -Encoding utf8
        Write-Host "  + MCP server registered in $mcpConfigPath" -ForegroundColor Green
    } else {
        Write-Host "  ! MCP server directory not found: $MCP_SERVER_DIR" -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "Skipping MCP server installation (--SkipMcp flag)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================"  -ForegroundColor Cyan
Write-Host "  Installation Complete!"                 -ForegroundColor Green
Write-Host "========================================"  -ForegroundColor Cyan
Write-Host ""

Write-Host "Installed components:" -ForegroundColor Yellow
Write-Host "  * Custom agents: $COPILOT_DIR\agents\" -ForegroundColor Gray
Write-Host "  * Config: $COPILOT_DIR\workflow-config.yaml" -ForegroundColor Gray
Write-Host "  * MCP server: agentic-workflow-server (Python package)" -ForegroundColor Gray
Write-Host "  * MCP config: $COPILOT_DIR\mcp-config.json" -ForegroundColor Gray
Write-Host "  * Repository instructions: .github/copilot-instructions.md" -ForegroundColor Gray
Write-Host ""

Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Start Copilot CLI in this repository: copilot" -ForegroundColor White
Write-Host "  2. Try: 'Use crew-architect to analyze adding a caching layer'" -ForegroundColor White
Write-Host "  3. Or use: /agent to browse available agents" -ForegroundColor White
Write-Host "  4. Check MCP tools: /mcp show" -ForegroundColor White
Write-Host ""

Write-Host "Documentation:" -ForegroundColor Yellow
Write-Host "  * Usage guide: .github/copilot-instructions.md" -ForegroundColor White
Write-Host "  * README: README.md" -ForegroundColor White
Write-Host ""

Write-Host "To uninstall, run: .\uninstall-copilot.ps1" -ForegroundColor Gray
Write-Host ""
