param(
    [Parameter(Mandatory=$true)][string]$InputDirectory,
    [Parameter(Mandatory=$true)][string]$Version,
    [string]$OutputDirectory = 'dist',
    [string]$Compiler = ''
)
$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid product version' }
$payload = (Resolve-Path $InputDirectory).Path
foreach ($file in 'Krose.exe', 'Resources/Factory.samples', 'Resources/SEGrand.samples', 'Krose.vst3') {
    if (!(Test-Path (Join-Path $payload $file))) { throw "Missing installer payload: $file" }
}
New-Item -ItemType Directory -Force $OutputDirectory | Out-Null
$output = (Resolve-Path $OutputDirectory).Path
if (!$Compiler) { $Compiler = & "$PSScriptRoot/../ci/inno_setup.ps1" }
$script = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'packaging/windows.iss'
& $Compiler "/DAppVersion=$Version" "/DPayload=$payload" "/O$output" $script
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed' }
$installer = Join-Path $output "Krose-$Version-windows-x64-setup.exe"
if (!(Test-Path $installer)) { throw 'Inno Setup did not produce the installer' }
Write-Host $installer
