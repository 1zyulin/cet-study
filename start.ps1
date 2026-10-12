param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$VenvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

function Find-UsablePython {
    $Candidates = @(
        @{ Name = 'py'; Arguments = @('-3') },
        @{ Name = 'python'; Arguments = @() }
    )
    foreach ($Candidate in $Candidates) {
        $Command = Get-Command -Name $Candidate.Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $Command) { continue }
        # Do not invoke the Windows Store placeholder when Python is not installed.
        if ($Candidate.Name -eq 'python' -and $Command.Source -match '\\WindowsApps\\') { continue }
        $CandidateArguments = @($Candidate.Arguments)
        $PreviousAutoInstall = [Environment]::GetEnvironmentVariable('PYTHON_MANAGER_AUTOMATIC_INSTALL', 'Process')
        try {
            # The launcher prepares the project environment; it does not install Python itself.
            [Environment]::SetEnvironmentVariable('PYTHON_MANAGER_AUTOMATIC_INSTALL', 'false', 'Process')
            & $Command.Source @CandidateArguments -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                return @{ Executable = $Command.Source; Arguments = $CandidateArguments }
            }
        } catch {
            continue
        } finally {
            [Environment]::SetEnvironmentVariable('PYTHON_MANAGER_AUTOMATIC_INSTALL', $PreviousAutoInstall, 'Process')
        }
    }
    return $null
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host '正在准备项目独立环境，需要 Python 3.10 或以上版本。'
    $PythonCommand = Find-UsablePython
    if (-not $PythonCommand) {
        throw '未找到可用的 Python。请先安装 Python 3.10 或以上版本，然后重新打开终端。详见 docs/Windows上手指南.md。'
    }
    $CreationArguments = @($PythonCommand.Arguments) + @('-m', 'venv', (Join-Path $PSScriptRoot '.venv'))
    & $PythonCommand.Executable @CreationArguments
    if ($LASTEXITCODE -ne 0) { throw '创建项目环境失败。请确认使用完整的 Python 安装，并查看 docs/Windows上手指南.md。' }
}

& $VenvPython -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
if ($LASTEXITCODE -ne 0) { throw '项目环境的 Python 版本低于 3.10。请在保留 data 目录后，重建 .venv 环境。' }

& $VenvPython -c 'import importlib.util; raise SystemExit(0 if all(importlib.util.find_spec(name) for name in ("flask", "requests", "waitress")) else 1)'
if ($LASTEXITCODE -ne 0) {
    & $VenvPython -c 'import importlib.util; raise SystemExit(0 if importlib.util.find_spec("pip") else 1)'
    if ($LASTEXITCODE -ne 0) {
        & $VenvPython -m ensurepip --upgrade
        if ($LASTEXITCODE -ne 0) { throw '无法在项目环境中准备 pip。请使用完整的 Python 安装重新创建 .venv。' }
    }
    Write-Host '首次安装项目依赖需要联网，依赖只安装在本项目 .venv 中。'
    & $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请检查网络后再次启动。' }
}

Write-Host '正在启动 CET Study。请保持此窗口打开；按 Ctrl+C 停止。'
$RunArguments = @((Join-Path $PSScriptRoot 'run.py'))
if ($NoBrowser) { $RunArguments += '--no-browser' }
& $VenvPython @RunArguments
if ($LASTEXITCODE -ne 0) { throw '应用启动失败，请查看上面的提示或 docs/Windows上手指南.md。' }
