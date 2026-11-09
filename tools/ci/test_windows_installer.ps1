param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$Version
)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true') { throw 'This installation smoke test is for clean CI runners only' }
$installerPath = (Resolve-Path $Installer).Path
$legacy = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Krose'
$current = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Krose_is1'
$directory = Join-Path $env:ProgramFiles 'Krose test 音色'
$samples = Join-Path $env:CommonProgramFiles "Krose/Samples/$Version"
$plugin = Join-Path $env:CommonProgramFiles 'VST3/Krose.vst3'
if ((Test-Path $legacy) -or (Test-Path $current) -or (Test-Path $directory)) {
    throw 'Installer test requires an empty Krose installation'
}

# Simulate the previous NSIS ownership record and obsolete uninstaller. This
# tests migration metadata; the fixture is not a claim of binary compatibility.
New-Item -ItemType Directory -Force $directory | Out-Null
[IO.File]::WriteAllText((Join-Path $directory 'Krose.exe'), 'legacy app fixture')
[IO.File]::WriteAllText((Join-Path $directory 'Uninstall.exe'), 'legacy uninstaller fixture')
$sentinel = Join-Path $directory 'installer-preservation-test.txt'
[IO.File]::WriteAllText($sentinel, 'Keep unowned files during update and uninstall')
New-Item -Path $legacy -Force | Out-Null
New-ItemProperty -Path $legacy -Name DisplayName -Value Krose -PropertyType String | Out-Null
New-ItemProperty -Path $legacy -Name InstallLocation -Value $directory -PropertyType String | Out-Null

for ($pass = 0; $pass -lt 2; ++$pass) {
    $log = Join-Path $env:RUNNER_TEMP "krose-install-$pass.log"
    $p = Start-Process $installerPath -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', "/LOG=`"$log`"" -Wait -PassThru
    if ($p.ExitCode -ne 0) { Get-Content $log -ErrorAction SilentlyContinue; throw "Install failed: $($p.ExitCode)" }
    $info = Get-ItemProperty $current
    if ($info.Publisher -ne 'maincore' -or $info.DisplayVersion -ne $Version) { throw 'Incorrect installation identity' }
    if ($info.InstallLocation.TrimEnd('\') -ne $directory) { throw 'Legacy Unicode installation directory was not retained' }
    foreach ($file in @((Join-Path $directory 'Krose.exe'), (Join-Path $samples 'Factory.samples'), (Join-Path $samples 'SEGrand.samples'), $plugin)) {
        if (!(Test-Path $file)) { throw "Missing installed payload: $file" }
    }
    if ((Test-Path $legacy) -or (Test-Path (Join-Path $directory 'Uninstall.exe'))) { throw 'Legacy uninstall entry was not retired' }
    if (!(Test-Path $sentinel)) { throw 'Update removed an unowned file' }
}

$match = [regex]::Match($info.UninstallString, '^"([^"]+)"')
if (!$match.Success) { throw 'Missing registered Inno uninstaller' }
$p = Start-Process $match.Groups[1].Value -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait -PassThru
if ($p.ExitCode -ne 0) { throw 'Uninstall failed' }
foreach ($file in @((Join-Path $directory 'Krose.exe'), $plugin, (Join-Path $samples 'Factory.samples'), (Join-Path $samples 'SEGrand.samples'), $current)) {
    if (Test-Path $file) { throw "Uninstall left installed payload: $file" }
}
if (!(Test-Path $sentinel)) { throw 'Uninstall removed an unowned file' }
Remove-Item $sentinel
if (!(Get-ChildItem $directory -Force)) { Remove-Item $directory }
Write-Host 'PASS Inno install/reinstall/uninstall, NSIS metadata migration and Unicode paths'
