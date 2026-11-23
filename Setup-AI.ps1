$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Local-Paths.ps1')
if(-not (Test-Path -LiteralPath $python)){& (Join-Path $PSScriptRoot 'Setup.ps1')}
& (Join-Path $PSScriptRoot 'Stop.ps1')
Push-Location $PSScriptRoot
try {
    foreach($module in @('scripts.setup_local_llm','scripts.setup_nli','scripts.setup_reranker')){
        $ErrorActionPreference='Continue'
        & $python -m $module
        $commandExit=$LASTEXITCODE
        $ErrorActionPreference='Stop'
        if($commandExit -ne 0){throw "Model setup failed: $module. Retry Setup-AI.cmd."}
    }
} finally {Pop-Location}
Write-Host 'Local Qwen and evidence checks are ready. Run Start.cmd.'
