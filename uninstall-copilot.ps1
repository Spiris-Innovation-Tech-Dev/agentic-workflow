# Copilot CLI Uninstaller for Agentic Workflow
# This script removes the agentic-workflow system from GitHub Copilot CLI

$ErrorActionPreference = "Stop"

$COPILOT_DIR = "$env:USERPROFILE\.copilot"

Write-Host "========================================"  -ForegroundColor Cyan
Write-Host "  Agentic Workflow Copilot Uninstaller"   -ForegroundColor Cyan
Write-Host "========================================"  -ForegroundColor Cyan
Write-Host ""

Write-Host "Removing custom agents..." -ForegroundColor Yellow
$removed = 0
# Remove both old format (crew-*.md) and new format (crew*.agent.md)
$agentFiles = @()
$agentFiles += Get-ChildItem "$COPILOT_DIR\agents\crew-*.md" -ErrorAction SilentlyContinue
$agentFiles += Get-ChildItem "$COPILOT_DIR\agents\crew*.agent.md" -ErrorAction SilentlyContinue
$agentFiles = $agentFiles | Select-Object -Unique

foreach ($agentFile in $agentFiles) {
    Remove-Item $agentFile.FullName -Force
    Write-Host "  + Removed $($agentFile.Name)" -ForegroundColor Green
    $removed++
}

if ($removed -eq 0) {
    Write-Host "  No agents found to remove" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Removing config..." -ForegroundColor Yellow
if (Test-Path "$COPILOT_DIR\workflow-config.yaml") {
    Remove-Item "$COPILOT_DIR\workflow-config.yaml" -Force
    Write-Host "  + Removed workflow-config.yaml" -ForegroundColor Green
} else {
    Write-Host "  Config file not found" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Removing MCP server registration..." -ForegroundColor Yellow
$mcpConfigPath = "$COPILOT_DIR\mcp-config.json"

if (Test-Path $mcpConfigPath) {
    $mcpConfig = Get-Content $mcpConfigPath | ConvertFrom-Json
    
    if ($mcpConfig.mcpServers -and $mcpConfig.mcpServers."agentic-workflow") {
        $mcpConfig.mcpServers.PSObject.Properties.Remove("agentic-workflow")
        $mcpConfig | ConvertTo-Json -Depth 10 | Out-File $mcpConfigPath -Encoding utf8
        Write-Host "  ✓ Removed agentic-workflow from MCP config" -ForegroundColor Green
    } else {
        Write-Host "  No agentic-workflow MCP server found in config" -ForegroundColor Gray
    }
} else {
    Write-Host "  MCP config file not found" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Uninstalling Python package..." -ForegroundColor Yellow
try {
    $output = pip uninstall -y agentic-workflow-server 2>&1
    Write-Host "  ✓ Python package uninstalled" -ForegroundColor Green
} catch {
    Write-Host "  Package not found or already uninstalled" -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================"  -ForegroundColor Cyan
Write-Host "  Uninstallation Complete!"               -ForegroundColor Green
Write-Host "========================================"  -ForegroundColor Cyan
Write-Host ""

Write-Host "Note: Repository-level files preserved:" -ForegroundColor Yellow
Write-Host "  * .github/copilot-instructions.md" -ForegroundColor Gray
Write-Host "  * .tasks/ (workflow state)" -ForegroundColor Gray
Write-Host ""

Write-Host "To reinstall, run: .\install-copilot.ps1" -ForegroundColor Gray
Write-Host ""
