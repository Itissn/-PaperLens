$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$assets=Join-Path $root '.cache\local-llm'
$exe=Join-Path $assets 'bin\llama-server.exe'
$model=Join-Path $assets 'qwen2.5-1.5b-instruct-q4_k_m.gguf'
$selection=Join-Path $assets 'active-model.json'
if(Test-Path -LiteralPath $selection){
    $selected=Get-Content -LiteralPath $selection -Raw | ConvertFrom-Json
    if($selected.file -notmatch '^[a-zA-Z0-9_.-]+[.]gguf$'){throw 'Invalid selected model filename.'}
    $model=Join-Path $assets $selected.file
    if(-not (Test-Path -LiteralPath $model)){throw 'Selected model file is missing.'}
}
if(-not (Test-Path -LiteralPath (Join-Path $assets 'provenance.json'))){throw 'Local model not verified. Run scripts/setup_local_llm.py first.'}
try{$health=Invoke-RestMethod 'http://127.0.0.1:8766/health' -TimeoutSec 2}catch{$health=$null}
if($health.status -eq 'ok'){Write-Output 'Local LLM already running.';exit}
[IO.Directory]::CreateDirectory((Join-Path $root 'reports')) | Out-Null
$keyFile=Join-Path $assets 'api-key.txt'
if(-not (Test-Path -LiteralPath $keyFile)){
    $randomBytes=New-Object byte[] 32
    $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($randomBytes)
    $rng.Dispose()
    [IO.File]::WriteAllText($keyFile,[Convert]::ToBase64String($randomBytes),[Text.Encoding]::ASCII)
}
$arguments=@('--api-key-file',('"' + $keyFile + '"'),'--cors-origins','http://127.0.0.1:8765','--no-webui','-m',('"' + $model + '"'),'--host','127.0.0.1','--port','8766','--jinja','--ctx-size','8192','--threads','6','--threads-batch','6','--n-gpu-layers','0','--parallel','1','--alias','paperlens-qwen')
$llm=Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'reports/llm.log') -RedirectStandardError (Join-Path $root 'reports/llm-error.log') -PassThru
[IO.File]::WriteAllText((Join-Path $root 'reports/llm.pid'),[string]$llm.Id)
$ready=$false
for($attempt=0;$attempt -lt 50;$attempt++){
    Start-Sleep -Milliseconds 400
    try{$health=Invoke-RestMethod 'http://127.0.0.1:8766/health' -TimeoutSec 2;if($health.status -eq 'ok'){$ready=$true;break}}catch{}
    if($llm.HasExited){break}
}
if(-not $ready){throw 'Local LLM did not start. See reports/llm-error.log.'}
Write-Output 'Local Qwen ready on 127.0.0.1:8766.'
