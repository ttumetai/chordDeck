$ErrorActionPreference = 'Stop'

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot '.')).Path
$ToolsDir = Join-Path $RootDir '.tools'
$NodeVersion = if ($env:NODE_VERSION) { $env:NODE_VERSION } else { '22.14.0' }
$PythonVersion = if ($env:PYTHON_VERSION) { $env:PYTHON_VERSION } else { '3.12' }
$BackendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { '8000' }
$FrontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { '5173' }
$BackendProcess = $null
$FrontendProcess = $null

New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

function Info([string]$Message) {
  Write-Host "[Chord Deck] $Message" -ForegroundColor Cyan
}

function Download([string]$Url, [string]$Destination) {
  Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
}

function Get-LocalTool([string]$Name) {
  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }
  return $null
}

function Setup-Uv {
  $script:UvBin = Get-LocalTool 'uv'
  if ($script:UvBin) { return }

  $script:UvBin = Join-Path $ToolsDir 'uv.exe'
  if (-not (Test-Path $script:UvBin)) {
    $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
    if ($arch -eq 'amd64') { $uvArch = 'x86_64' }
    elseif ($arch -eq 'arm64') { $uvArch = 'aarch64' }
    else { throw "不支持的 Windows CPU 架构：$arch" }
    $archive = Join-Path $ToolsDir "uv-$uvArch.zip"
    Info '未检测到 uv，正在下载项目本地副本…'
    Download "https://github.com/astral-sh/uv/releases/latest/download/uv-$uvArch-pc-windows-msvc.zip" $archive
    $extractDir = Join-Path $ToolsDir 'uv-extract'
    if (Test-Path $extractDir) { Remove-Item -Recurse -Force $extractDir }
    Expand-Archive -Path $archive -DestinationPath $extractDir -Force
    $uvExe = Get-ChildItem -Path $extractDir -Filter 'uv.exe' -Recurse | Select-Object -First 1
    if (-not $uvExe) { throw 'uv 自动安装失败。' }
    Copy-Item $uvExe.FullName $script:UvBin -Force
    Remove-Item $archive -Force
    Remove-Item $extractDir -Recurse -Force
  }
  if (-not (Test-Path $script:UvBin)) { throw 'uv 自动安装失败。' }
}

function Setup-Node {
  $node = Get-LocalTool 'node'
  $npm = Get-LocalTool 'npm'
  if ($node -and $npm) { return }

  $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
  if ($arch -eq 'amd64') { $nodeArch = 'x64' }
  elseif ($arch -eq 'arm64') { $nodeArch = 'arm64' }
  else { throw "不支持的 Windows CPU 架构：$arch" }
  $nodeDir = Join-Path $ToolsDir "node-v$NodeVersion-win-$nodeArch"
  $nodeExe = Join-Path $nodeDir 'node.exe'
  $npmCmd = Join-Path $nodeDir 'npm.cmd'
  if (-not (Test-Path $nodeExe) -or -not (Test-Path $npmCmd)) {
    $archive = Join-Path $ToolsDir "node-v$NodeVersion-win-$nodeArch.zip"
    Info "未检测到 Node.js/npm，正在下载项目本地 Node.js v$NodeVersion…"
    Download "https://nodejs.org/dist/v$NodeVersion/node-v$NodeVersion-win-$nodeArch.zip" $archive
    Expand-Archive -Path $archive -DestinationPath $ToolsDir -Force
    Remove-Item $archive -Force
  }
  if (-not (Test-Path $nodeExe) -or -not (Test-Path $npmCmd)) { throw 'Node.js 自动安装失败。' }
  $env:Path = "$nodeDir;$env:Path"
}

function Ensure-Environments {
  Info '同步主 Python 环境…'
  & $UvBin sync --locked --managed-python
  if (-not (Test-Path (Join-Path $RootDir 'frontend/node_modules'))) {
    Info '安装前端依赖…'
    Push-Location (Join-Path $RootDir 'frontend')
    try { & npm.cmd ci --no-audit --no-fund }
    finally { Pop-Location }
  }
  $lvPython = Join-Path $RootDir '.venv-lv/Scripts/python.exe'
  $lvReady = $false
  if (Test-Path $lvPython) {
    & $lvPython -c 'import torch, lv_chordia' 2>$null
    $lvReady = ($LASTEXITCODE -eq 0)
  }
  if (-not $lvReady) {
    Info '安装 LV-Chordia 独立环境（首次可能需要较长时间和较多磁盘空间）…'
    & $UvBin venv (Join-Path $RootDir '.venv-lv') --python $PythonVersion
    & $UvBin pip install --python $lvPython lv-chordia
  }
}

function Wait-ForUrl([string]$Url) {
  for ($i = 0; $i -lt 60; $i++) {
    try {
      Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 1 | Out-Null
      return
    } catch { Start-Sleep -Milliseconds 500 }
  }
  throw "服务未能在规定时间内启动：$Url"
}

function Stop-Processes {
  if ($BackendProcess -and -not $BackendProcess.HasExited) { Stop-Process -Id $BackendProcess.Id -Force -ErrorAction SilentlyContinue }
  if ($FrontendProcess -and -not $FrontendProcess.HasExited) { Stop-Process -Id $FrontendProcess.Id -Force -ErrorAction SilentlyContinue }
}

try {
  Set-Location $RootDir
  Setup-Uv
  Setup-Node
  Ensure-Environments
  $PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { Join-Path $RootDir '.venv/Scripts/python.exe' }
  if (-not (Test-Path $PythonBin)) { throw "主 Python 环境创建失败：$PythonBin" }
  Info '检查运行环境…'
  & $PythonBin (Join-Path $RootDir 'scripts/check_env.py')
  Info '启动后端和前端…'
  $BackendProcess = Start-Process -FilePath $PythonBin -ArgumentList "-m uvicorn backend.main:app --host 127.0.0.1 --port $BackendPort" -WorkingDirectory $RootDir -PassThru -NoNewWindow
  $FrontendProcess = Start-Process -FilePath 'npm.cmd' -ArgumentList "run dev -- --host 127.0.0.1 --port $FrontendPort" -WorkingDirectory (Join-Path $RootDir 'frontend') -PassThru -NoNewWindow
  Wait-ForUrl "http://127.0.0.1:$FrontendPort/"
  Info "Frontend: http://127.0.0.1:$FrontendPort/"
  Info "Backend: http://127.0.0.1:$BackendPort/"
  Start-Process "http://127.0.0.1:$FrontendPort/"
  Wait-Process -Id $BackendProcess.Id, $FrontendProcess.Id
} finally {
  Stop-Processes
}
