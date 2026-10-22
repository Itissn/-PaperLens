$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$targets=@(
    @{PidFile='reports/server.pid'; Executable=@((Join-Path $root '.runtime/python.exe'),(Join-Path $root '.venv/Scripts/python.exe')); Marker=(Join-Path $root 'manage.py')},
    @{PidFile='reports/llm.pid'; Executable=(Join-Path $root '.cache/local-llm/bin/llama-server.exe'); Marker=(Join-Path $root '.cache/local-llm')},
    @{PidFile='reports/ollama.pid'; Executable=(Join-Path $root '.cache/ollama/bin/ollama.exe'); Marker=(Join-Path $root '.cache/ollama')}
)
foreach($target in $targets){
    $file=Join-Path $root $target.PidFile
    if(-not (Test-Path -LiteralPath $file)){continue}
    $taskProcessId=[int](Get-Content -LiteralPath $file)
    $process=Get-CimInstance Win32_Process -Filter "ProcessId=$taskProcessId"
    if($process){
        $expectedPaths=@($target.Executable | ForEach-Object { [IO.Path]::GetFullPath($_) })
        $marker=[IO.Path]::GetFullPath($target.Marker)
        if($process.ExecutablePath -notin $expectedPaths -or -not $process.CommandLine.Contains($marker)){
            throw 'Saved PID belongs to a different command; nothing stopped for that PID.'
        }
        Stop-Process -Id $taskProcessId
    }
    Remove-Item -LiteralPath $file
}
Write-Output 'PaperLens task-owned processes stopped.'
