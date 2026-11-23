$machineRoot=Join-Path $env:LOCALAPPDATA 'PaperLens'
$python=Join-Path $machineRoot 'venv312\Scripts\python.exe'
$env:PAPERLENS_CACHE_DIR=Join-Path $machineRoot 'models'
$env:HF_HOME=Join-Path $env:PAPERLENS_CACHE_DIR 'huggingface'
$env:HF_HUB_DISABLE_XET='1'
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:PAPERLENS_LLM_KEY_FILE=Join-Path $env:PAPERLENS_CACHE_DIR 'local-llm\api-key.txt'
[IO.Directory]::CreateDirectory($machineRoot) | Out-Null

$env:PYTHONDONTWRITEBYTECODE='1'
$env:HF_HUB_DISABLE_PROGRESS_BARS='1'
$env:HF_HUB_DISABLE_SYMLINKS_WARNING='1'

