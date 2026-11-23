$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Local-Paths.ps1')
Push-Location $PSScriptRoot
try {
    if(-not (Test-Path -LiteralPath $python)){
        $base=Join-Path $machineRoot 'python312\python.exe'
        if(-not (Test-Path -LiteralPath $base)){
            Write-Host 'Preparing independent Python 3.12 (first run only)...'
            $installer=Join-Path $machineRoot 'python-3.12.10-amd64.exe'
            Invoke-WebRequest -UseBasicParsing 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $installer
            $signature=Get-AuthenticodeSignature -LiteralPath $installer
            if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Python Software Foundation*'){throw 'Python installer signature verification failed.'}
            $target=Join-Path $machineRoot 'python312'
            $installerProcess=Start-Process -FilePath $installer -ArgumentList @('/quiet','InstallAllUsers=0',('TargetDir="'+$target+'"'),'PrependPath=0','Include_launcher=0','Include_test=0','Shortcuts=0','AssociateFiles=0','Include_pip=1') -WindowStyle Hidden -Wait -PassThru
            if($installerProcess.ExitCode -notin @(0,3010)){throw 'Python setup failed. Run Start.cmd again after checking the installer.'}
        }
        & $base -m venv (Join-Path $machineRoot 'venv312')
        $commandExit=$LASTEXITCODE
        if($commandExit -ne 0){throw 'Could not create the Python environment.'}
    }
    Write-Host 'Installing PaperLens dependencies (first run only)...'
    $ErrorActionPreference='Continue'
    & $python -m pip install --disable-pip-version-check --progress-bar off -r (Join-Path $PSScriptRoot 'requirements.txt')
    $commandExit=$LASTEXITCODE
    $ErrorActionPreference='Stop'
    if($commandExit -ne 0){throw 'Dependency installation failed. Check your connection and retry Start.cmd.'}
    Write-Host 'Preparing the search model...'
    $ErrorActionPreference='Continue'
    & $python -m scripts.setup_search
    $commandExit=$LASTEXITCODE
    $ErrorActionPreference='Stop'
    if($commandExit -ne 0){throw 'Search model setup failed. Retry when the network is available.'}
    (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'requirements.txt') -Algorithm SHA256).Hash | Set-Content -LiteralPath (Join-Path $machineRoot 'requirements.sha256')
    Write-Host 'PaperLens search is ready.'
} finally {Pop-Location}
