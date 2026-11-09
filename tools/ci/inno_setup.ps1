# Return the path of the hash-pinned Inno compiler. Build tools stay in TEMP.
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$pin = Get-Content "$root/packaging/inno-setup.json" -Raw | ConvertFrom-Json
$temporary = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
$tools = Join-Path $temporary "krose-inno-$($pin.version)"
New-Item -ItemType Directory -Force $tools | Out-Null
$download = Join-Path $tools 'compiler-setup.exe'
if (!(Test-Path $download)) {
    Invoke-WebRequest -Uri $pin.url -OutFile $download
}
if ((Get-FileHash $download -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pin.sha256) {
    throw 'Inno Setup compiler checksum mismatch'
}
$compiler = Join-Path $tools 'compiler/ISCC.exe'
if (!(Test-Path $compiler)) {
    $destination = Join-Path $tools 'compiler'
    $process = Start-Process $download -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', "/DIR=`"$destination`"" -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw 'Inno Setup compiler installation failed' }
}
if (!(Test-Path $compiler)) { throw 'Inno Setup compiler is missing' }
return $compiler
