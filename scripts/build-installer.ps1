param(
    [string]$Compiler = 'D:\AI\Tools\InnoSetup7\ISCC.exe',
    [string]$Bundle,
    [string]$OutputDirectory,
    [string]$Python
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ([string]::IsNullOrWhiteSpace($Bundle)) { $Bundle = Join-Path $projectRoot 'build\dist\MiraMediaDownloader' }
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) { $OutputDirectory = Join-Path $projectRoot 'build\installer' }
$Bundle = [IO.Path]::GetFullPath($Bundle)
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (-not (Test-Path -LiteralPath $Compiler)) { throw 'Install Inno Setup 7 and pass its ISCC.exe path with -Compiler.' }
if (-not (Test-Path -LiteralPath (Join-Path $Bundle 'manifest.sha256'))) { throw 'Build and verify the complete application bundle first.' }
$pythonPath = $Python
if ([string]::IsNullOrWhiteSpace($pythonPath)) {
    $pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = 'python' }
}
Push-Location -LiteralPath $projectRoot
try {
    $packageVersion = & $pythonPath (Join-Path $PSScriptRoot 'package_version.py')
    if ($LASTEXITCODE -ne 0) { throw 'Could not read the application version.' }
    & $Compiler "--define=AppVersion=$packageVersion" "--define=AppSource=$Bundle" "--define=SetupOutput=$OutputDirectory" (Join-Path $PSScriptRoot 'installer.iss')
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
    $installerPath = Join-Path $OutputDirectory ('MiraMediaDownloader-' + $packageVersion.Trim() + '-Setup-x64.exe')
    if (-not (Test-Path -LiteralPath $installerPath)) { throw 'Compiled installer was not found.' }
    Get-FileHash -LiteralPath $installerPath -Algorithm SHA256
}
finally { Pop-Location }
