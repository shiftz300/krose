# Import the installed VS x64 environment without a Node-based setup action.
$ErrorActionPreference = 'Stop'
$vswhere = "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe"
if (!(Test-Path $vswhere)) { throw 'Visual Studio Installer/vswhere.exe is missing' }
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if ($LASTEXITCODE -ne 0 -or !$installation) { throw 'No Visual Studio C++ x64 toolchain found' }
$devcmd = Join-Path $installation 'Common7/Tools/VsDevCmd.bat'
if (!(Test-Path $devcmd)) { throw 'Visual Studio VsDevCmd.bat is missing' }
$before = @{}
Get-ChildItem Env: | ForEach-Object { $before[$_.Name] = $_.Value }
$command = 'call "' + $devcmd + '" -no_logo -arch=x64 -host_arch=x64 >nul && set'
$environment = & $env:ComSpec /d /s /c $command
if ($LASTEXITCODE -ne 0) { throw 'VsDevCmd.bat failed' }
foreach ($line in $environment) {
    if ($line -match '^([^=]+)=(.*)$') {
        $name, $value = $Matches[1], $Matches[2]
        if ($name -match '^(GITHUB_|RUNNER_|ACTIONS_)' -or $name -eq 'NODE_OPTIONS') { continue }
        if (!$before.ContainsKey($name) -or $before[$name] -ne $value) {
            "$name=$value" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
        }
    }
}
Write-Host 'Configured Visual Studio x64 toolchain'
