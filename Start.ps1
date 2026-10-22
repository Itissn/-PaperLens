$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$settingsPath=Join-Path $root '.cache/app-settings.json'
if(Test-Path -LiteralPath $settingsPath){
    $settings=Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
    if($settings.auth_required){$env:PAPERLENS_AUTH_REQUIRED='1'}else{$env:PAPERLENS_AUTH_REQUIRED='0'}
    if($settings.ollama_model){$env:PAPERLENS_OLLAMA_MODEL=[string]$settings.ollama_model}
    if($settings.ollama_url){$env:PAPERLENS_OLLAMA_URL=[string]$settings.ollama_url}
}

if($env:PAPERLENS_OLLAMA_MODEL -and (Test-Path -LiteralPath (Join-Path $root '.cache/ollama/provenance.json'))){ & (Join-Path $root 'Start-Ollama.ps1') }
if(Test-Path -LiteralPath (Join-Path $root '.cache/local-llm/provenance.json')){ & (Join-Path $root 'Start-Local-LLM.ps1') }
$python=Join-Path $root '.runtime\python.exe'
if(-not (Test-Path -LiteralPath $python)){ $python=Join-Path $root '.venv\Scripts\python.exe' }
if(-not (Test-Path -LiteralPath $python)){ throw 'Install Python dependencies first; see README.md.' }
try { $existing=Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2 } catch { $existing=$null }
if($existing -and $existing.version -eq '0.3.0'){
    if([bool]$existing.authentication_required -ne ($env:PAPERLENS_AUTH_REQUIRED -eq '1')){throw 'Authentication settings changed. Run Stop.ps1 before restarting.'}
    Start-Process 'http://127.0.0.1:8765'
    Write-Output 'PaperLens already running: http://127.0.0.1:8765'
    exit
}
[IO.Directory]::CreateDirectory((Join-Path $root 'reports')) | Out-Null
$server=Start-Process -FilePath $python -ArgumentList @((('"' + (Join-Path $root 'manage.py') + '"')),'serve') -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'reports/server.log') -RedirectStandardError (Join-Path $root 'reports/server-error.log') -PassThru
[IO.File]::WriteAllText((Join-Path $root 'reports/server.pid'),[string]$server.Id)
$ready=$false
for($attempt=0;$attempt -lt 25;$attempt++){
    Start-Sleep -Milliseconds 400
    try { $status=Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2; $ready=$true; break } catch {}
}
if(-not $ready){throw 'PaperLens did not start. See reports/server-error.log.'}
Start-Process 'http://127.0.0.1:8765'
Write-Output 'PaperLens ready: http://127.0.0.1:8765'
