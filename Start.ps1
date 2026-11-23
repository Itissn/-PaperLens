param([switch]$NoBrowser)
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
. (Join-Path $root 'Local-Paths.ps1')
$stamp=Join-Path $machineRoot 'requirements.sha256'
$expected=(Get-FileHash -LiteralPath (Join-Path $root 'requirements.txt') -Algorithm SHA256).Hash
if(-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $stamp) -or (Get-Content -LiteralPath $stamp -Raw).Trim() -ne $expected){
    & (Join-Path $root 'Setup.ps1')
}
if(Test-Path -LiteralPath (Join-Path $env:PAPERLENS_CACHE_DIR 'local-llm/provenance.json')){
    & (Join-Path $root 'Start-Local-LLM.ps1')
}
try {$existing=Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2} catch {$existing=$null}
if($existing){
    $pidFile=Join-Path $root 'reports/server.pid'
    $owned=$false
    if(Test-Path -LiteralPath $pidFile){
        $taskProcessId=[int](Get-Content -LiteralPath $pidFile)
        $proc=Get-CimInstance Win32_Process -Filter "ProcessId=$taskProcessId"
        $owned=$proc -and $proc.CommandLine.Contains((Join-Path $root 'manage.py'))
    }
    if(-not $owned){throw 'Port 8765 is occupied by another application or PaperLens copy.'}
} else {
    [IO.Directory]::CreateDirectory((Join-Path $root 'reports')) | Out-Null
    $server=Start-Process -FilePath $python -ArgumentList @(('"'+(Join-Path $root 'manage.py')+'"'),'serve') -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'reports/server.log') -RedirectStandardError (Join-Path $root 'reports/server-error.log') -PassThru
    [IO.File]::WriteAllText((Join-Path $root 'reports/server.pid'),[string]$server.Id)
    $ready=$false
    for($attempt=0;$attempt -lt 90;$attempt++){
        Start-Sleep -Milliseconds 500
        try {$status=Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 1; $ready=$true; break} catch {}
        if($server.HasExited){break}
    }
    if(-not $ready){throw 'PaperLens did not start. See reports/server-error.log.'}
}
if(-not $NoBrowser){Start-Process 'http://127.0.0.1:8765'}
Write-Host 'PaperLens ready: http://127.0.0.1:8765'
