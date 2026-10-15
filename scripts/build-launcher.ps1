param(
    [string]$OutputDirectory,
    [string]$BuildToolsRoot,
    [string]$WindowsSdkRoot = 'C:\Program Files (x86)\Windows Kits\10'
)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($BuildToolsRoot)) {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path -LiteralPath $vswhere) {
        $BuildToolsRoot = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    }
    if ([string]::IsNullOrWhiteSpace($BuildToolsRoot) -and (Test-Path -LiteralPath 'D:\AI\Tools\BuildTools\VC\Tools\MSVC')) {
        $BuildToolsRoot = 'D:\AI\Tools\BuildTools'
    }
    if ([string]::IsNullOrWhiteSpace($BuildToolsRoot)) { throw 'Install Visual Studio C++ x64 Build Tools or pass -BuildToolsRoot.' }
}
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$nativeRoot = Join-Path $projectRoot 'native'
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) { $OutputDirectory = Join-Path $projectRoot 'build\launcher' }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$versions = Get-ChildItem -LiteralPath (Join-Path $BuildToolsRoot 'VC\Tools\MSVC') -Directory | Sort-Object Name
if (-not $versions) { throw 'MSVC C++ x64 build tools were not found.' }
$msvc = $versions[-1].FullName
$sdkVersions = Get-ChildItem -LiteralPath (Join-Path $WindowsSdkRoot 'Include') -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'um\windows.h') } | Sort-Object Name
if (-not $sdkVersions) { throw 'Windows SDK headers were not found.' }
$sdkVersion = $sdkVersions[-1].Name
$compilerDirectory = Join-Path $msvc 'bin\Hostx64\x64'
$compiler = Join-Path $compilerDirectory 'cl.exe'
$resources = Join-Path $WindowsSdkRoot ('bin\' + $sdkVersion + '\x64\rc.exe')
if (-not (Test-Path -LiteralPath $compiler) -or -not (Test-Path -LiteralPath $resources)) { throw 'MSVC compiler or Windows resource compiler is missing.' }
$includePaths = @((Join-Path $msvc 'include'))
foreach ($part in @('ucrt','shared','um','winrt')) { $includePaths += Join-Path $WindowsSdkRoot ('Include\' + $sdkVersion + '\' + $part) }
$libraryPaths = @((Join-Path $msvc 'lib\x64'),
    (Join-Path $WindowsSdkRoot ('Lib\' + $sdkVersion + '\ucrt\x64')),
    (Join-Path $WindowsSdkRoot ('Lib\' + $sdkVersion + '\um\x64')))
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$intermediateDirectory = Join-Path $projectRoot 'build\native-launcher'
New-Item -ItemType Directory -Path $intermediateDirectory -Force | Out-Null
$versionText = Get-Content -LiteralPath (Join-Path $projectRoot 'pyproject.toml') -Raw
$versionMatch = [regex]::Match($versionText, '(?m)^version\s*=\s*"([0-9]+)\.([0-9]+)\.([0-9]+)[^"]*"')
if (-not $versionMatch.Success) { throw 'A numeric application version was not found.' }
$version = $versionMatch.Groups[1].Value + '.' + $versionMatch.Groups[2].Value + '.' + $versionMatch.Groups[3].Value
$numericVersion = $versionMatch.Groups[1].Value + ',' + $versionMatch.Groups[2].Value + ',' + $versionMatch.Groups[3].Value + ',0'
$header = '#define MIRA_VERSION_NUM ' + $numericVersion + "`n" + '#define MIRA_VERSION_STR "' + $version + '\0"' + "`n"
$header | Set-Content -LiteralPath (Join-Path $intermediateDirectory 'launcher_version.h') -Encoding utf8
$originalPath = $env:PATH
$originalInclude = $env:INCLUDE
$originalLib = $env:LIB
Push-Location -LiteralPath $nativeRoot
try {
    $env:PATH = $compilerDirectory + ';' + (Join-Path $WindowsSdkRoot ('bin\' + $sdkVersion + '\x64')) + ';' + $env:SystemRoot + '\System32;' + $env:SystemRoot
    $env:INCLUDE = $includePaths -join ';'
    $env:LIB = $libraryPaths -join ';'
    $resourceFile = Join-Path $intermediateDirectory 'launcher.res'
    & $resources /nologo /I $intermediateDirectory /fo $resourceFile (Join-Path $nativeRoot 'launcher.rc')
    if ($LASTEXITCODE -ne 0) { throw 'Native launcher resources failed to compile.' }
    $executable = Join-Path $OutputDirectory 'MiraMediaDownloader.exe'
    $objectFile = Join-Path $intermediateDirectory 'launcher.obj'
    & $compiler /nologo /std:c++17 /O1 /MT /EHsc /utf-8 /W4 /guard:cf /DUNICODE /D_UNICODE /DWIN32_LEAN_AND_MEAN /DNOMINMAX /D_WIN32_WINNT=0x0A00 /Fo:$objectFile /Fe:$executable (Join-Path $nativeRoot 'launcher.cpp') $resourceFile /link /SUBSYSTEM:WINDOWS /MANIFEST:NO /DYNAMICBASE /NXCOMPAT /HIGHENTROPYVA /CETCOMPAT user32.lib gdi32.lib shell32.lib advapi32.lib bcrypt.lib dwmapi.lib gdiplus.lib ole32.lib
    if ($LASTEXITCODE -ne 0) { throw 'Native launcher compilation failed.' }
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) { throw 'Native launcher executable was not produced.' }
    Get-Item -LiteralPath $executable | Select-Object FullName,Length
    Get-FileHash -LiteralPath $executable -Algorithm SHA256
}
finally {
    Pop-Location
    $env:PATH = $originalPath
    $env:INCLUDE = $originalInclude
    $env:LIB = $originalLib
}
