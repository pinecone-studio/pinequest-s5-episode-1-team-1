# Installs BEKHI on this computer as an app: its Python packages, its window (the web app built to
# talk to this PC's API) and a "BEKHI" shortcut on the desktop. Run it again after pulling new code.
# Nothing starts with Windows: BEKHI runs while its window is open.
$ErrorActionPreference = 'Stop'
$api = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $api '..\..')).Path

Write-Host '1/4 Python packages'
$env:UV_LINK_MODE = 'copy'
uv sync --frozen --no-dev --inexact --project $api
if ($LASTEXITCODE -ne 0) { throw 'uv sync failed' }
if (-not (Test-Path (Join-Path $api '.env'))) {
  Write-Warning 'apps/api/.env is missing: copy .env.example and put in the API keys, or BEKHI cannot talk.'
}

Write-Host '2/4 The window (web app)'
Push-Location $repo
if (-not (Test-Path 'node_modules')) { npm install; if ($LASTEXITCODE -ne 0) { throw 'npm install failed' } }
Pop-Location
Push-Location (Join-Path $repo 'apps\mobile')
# The window talks to the API that serves it, on this PC (an empty value would let .env's cloud address in).
$env:EXPO_PUBLIC_API_URL = 'http://127.0.0.1:8000'
$env:CI = '1'
npx expo export -p web --output-dir (Join-Path $api 'web')
if ($LASTEXITCODE -ne 0) { throw 'expo export failed' }
Pop-Location

Write-Host '3/4 Icon'
Add-Type -AssemblyName System.Drawing
$png = [System.Drawing.Image]::FromFile((Join-Path $repo 'apps\mobile\assets\icon.png'))
$small = New-Object System.Drawing.Bitmap 256, 256
$g = [System.Drawing.Graphics]::FromImage($small)
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.DrawImage($png, 0, 0, 256, 256)
$g.Dispose(); $png.Dispose()
$bytes = New-Object System.IO.MemoryStream
$small.Save($bytes, [System.Drawing.Imaging.ImageFormat]::Png)
$small.Dispose()
$data = $bytes.ToArray()
# An .ico holding one 256x256 PNG: 6-byte header, one 16-byte directory entry, then the PNG.
$ico = New-Object System.IO.MemoryStream
$w = New-Object System.IO.BinaryWriter $ico
$w.Write([UInt16]0); $w.Write([UInt16]1); $w.Write([UInt16]1)
$w.Write([Byte]0); $w.Write([Byte]0); $w.Write([Byte]0); $w.Write([Byte]0)
$w.Write([UInt16]1); $w.Write([UInt16]32); $w.Write([UInt32]$data.Length); $w.Write([UInt32]22)
$w.Write($data)
# Kept outside web/, which every build replaces.
$iconDir = Join-Path $env:LOCALAPPDATA 'BEKHI'
New-Item -ItemType Directory -Force $iconDir | Out-Null
$iconPath = Join-Path $iconDir 'bekhi.ico'
[System.IO.File]::WriteAllBytes($iconPath, $ico.ToArray())

Write-Host '4/4 Desktop shortcut'
$python = (uv python find --system 3.12).Trim()
# pythonw: no console window. uv's own Python, since Windows Smart App Control may block .venv's launchers.
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'BEKHI.lnk'))
$link.TargetPath = $pythonw
$link.Arguments = '"' + (Join-Path $api 'bekhi_desktop.pyw') + '"'
$link.WorkingDirectory = $api
$link.IconLocation = $iconPath
$link.Description = 'BEKHI: Mongolian voice assistant'
$link.Save()
Write-Host 'Done. Open BEKHI from the desktop icon.'
