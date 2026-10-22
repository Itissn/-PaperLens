$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$folder=Join-Path $root '.cache/ollama'
if(-not (Test-Path -LiteralPath (Join-Path $folder 'provenance.json'))){throw 'Run scripts/setup_ollama_portable.py first.'}
try{$health=Invoke-RestMethod 'http://127.0.0.1:11435/api/version' -TimeoutSec 2}catch{$health=$null}
if($health.version){Write-Output 'Project Ollama already running on localhost:11435.';exit}
$env:OLLAMA_HOST='127.0.0.1:11435'
$env:OLLAMA_MODELS=Join-Path $folder 'models'
$env:OLLAMA_TMPDIR=Join-Path $folder 'tmp'
$env:OLLAMA_MAX_LOADED_MODELS='1'
$env:OLLAMA_NUM_PARALLEL='1'
[IO.Directory]::CreateDirectory($env:OLLAMA_MODELS) | Out-Null
[IO.Directory]::CreateDirectory($env:OLLAMA_TMPDIR) | Out-Null
$exe=Join-Path $folder 'bin/ollama.exe'
$process=Start-Process -FilePath $exe -ArgumentList 'serve' -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'reports/ollama.log') -RedirectStandardError (Join-Path $root 'reports/ollama-error.log') -PassThru
[IO.File]::WriteAllText((Join-Path $root 'reports/ollama.pid'),[string]$process.Id)
for($attempt=0;$attempt -lt 40;$attempt++){
    Start-Sleep -Milliseconds 300
    try{$health=Invoke-RestMethod 'http://127.0.0.1:11435/api/version' -TimeoutSec 2;if($health.version){Write-Output ('Portable Ollama ready: '+$health.version);exit}}catch{}
}
throw 'Portable Ollama did not start. See reports/ollama-error.log.'
