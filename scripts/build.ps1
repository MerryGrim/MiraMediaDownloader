param(
    [string]$Python,
    [string]$BuildToolsRoot,
    [string]$WindowsSdkRoot,
    [switch]$SkipInstall,
    [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

function Move-PreviousCollectedBundle {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)
    # Rename only this project's previous COLLECT result. PyInstaller otherwise
    # recursively deletes it with Python paths that can exceed MAX_PATH.
    $resolvedProject = Resolve-Path -LiteralPath $ProjectRoot
    if ($resolvedProject.Provider.Name -ne 'FileSystem') { throw 'The build project must be a filesystem directory.' }
    $projectDirectory = Get-Item -LiteralPath $resolvedProject.ProviderPath -Force
    if (-not $projectDirectory.PSIsContainer -or
        ($projectDirectory.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'The build project must be an ordinary directory, not a link.'
    }
    $checkedProject = [IO.Path]::GetFullPath($projectDirectory.FullName).TrimEnd('\')
    if ([string]::IsNullOrEmpty([IO.Path]::GetDirectoryName($checkedProject))) { throw 'A drive root cannot be a build project.' }
    $checkedBuild = [IO.Path]::GetFullPath((Join-Path $checkedProject 'build'))
    $checkedDist = [IO.Path]::GetFullPath((Join-Path $checkedBuild 'dist'))
    $checkedSource = [IO.Path]::GetFullPath((Join-Path $checkedDist 'MiraMediaDownloader'))
    foreach ($expectedDirectory in @($checkedBuild, $checkedDist, $checkedSource)) {
        if (-not (Test-Path -LiteralPath $expectedDirectory)) { return }
        $resolvedDirectory = Resolve-Path -LiteralPath $expectedDirectory
        $directory = Get-Item -LiteralPath $resolvedDirectory.ProviderPath -Force
        if ($resolvedDirectory.Provider.Name -ne 'FileSystem' -or
            -not $directory.PSIsContainer -or
            ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            -not [IO.Path]::GetFullPath($directory.FullName).TrimEnd('\').Equals($expectedDirectory, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Previous COLLECT path is not the expected ordinary project build directory.'
        }
    }
    $sourcePath = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $checkedSource).ProviderPath)
    $buildPath = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $checkedBuild).ProviderPath).TrimEnd('\')
    $archivePath = [IO.Path]::GetFullPath((Join-Path $buildPath ('previous-dist-' + [Guid]::NewGuid().ToString('N'))))
    if (-not $sourcePath.Equals($checkedSource, [StringComparison]::OrdinalIgnoreCase) -or
        -not $sourcePath.StartsWith($buildPath + '\', [StringComparison]::OrdinalIgnoreCase) -or
        -not [IO.Path]::GetDirectoryName($archivePath).Equals($buildPath, [StringComparison]::OrdinalIgnoreCase) -or
        (Test-Path -LiteralPath $archivePath)) {
        throw 'Previous COLLECT archive paths failed confinement checks.'
    }
    Move-Item -LiteralPath $sourcePath -Destination $archivePath -ErrorAction Stop
    if ((Test-Path -LiteralPath $sourcePath) -or
        -not (Test-Path -LiteralPath $archivePath -PathType Container)) {
        throw 'Previous COLLECT result was not archived successfully.'
    }
    Write-Output ('Archived previous collected build: ' + $archivePath)
}

function Move-CollectedRuntime {
    param([Parameter(Mandatory = $true)][string]$BundleRoot)
    # Resolve and validate every source/destination before moving the collected
    # directory. Never merge into an existing runtime or follow a root junction.
    $resolvedBundle = Resolve-Path -LiteralPath $BundleRoot
    if ($resolvedBundle.Provider.Name -ne 'FileSystem') { throw 'The application bundle must be a filesystem directory.' }
    $bundleDirectory = Get-Item -LiteralPath $resolvedBundle.ProviderPath -Force
    if (-not $bundleDirectory.PSIsContainer -or
        ($bundleDirectory.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'The application bundle must be an ordinary directory, not a link.'
    }
    $bundlePath = [IO.Path]::GetFullPath($bundleDirectory.FullName).TrimEnd('\')
    if ([string]::IsNullOrEmpty([IO.Path]::GetDirectoryName($bundlePath))) { throw 'A drive root cannot be an application bundle.' }
    $bundlePrefix = $bundlePath + '\'
    $bundleRuntime = [IO.Path]::GetFullPath((Join-Path $bundlePath 'runtime'))
    $coreSource = [IO.Path]::GetFullPath((Join-Path $bundlePath 'MiraMediaDownloaderCore.exe'))
    $dependenciesSource = [IO.Path]::GetFullPath((Join-Path $bundlePath '_internal'))
    $coreTarget = [IO.Path]::GetFullPath((Join-Path $bundleRuntime 'MiraMediaDownloaderCore.exe'))
    $dependenciesTarget = [IO.Path]::GetFullPath((Join-Path $bundleRuntime '_internal'))
    foreach ($checkedPath in @($bundleRuntime, $coreSource, $dependenciesSource, $coreTarget, $dependenciesTarget)) {
        if (-not $checkedPath.StartsWith($bundlePrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw ('Runtime relocation path escaped the application bundle: ' + $checkedPath)
        }
    }
    if (Test-Path -LiteralPath $bundleRuntime) { throw 'The collected bundle already has a runtime directory; rebuild into a fresh bundle.' }
    if (-not (Test-Path -LiteralPath $coreSource -PathType Leaf) -or
        -not (Test-Path -LiteralPath $dependenciesSource -PathType Container)) {
        throw 'The collected Core executable and _internal directory are both required before relocation.'
    }
    foreach ($sourcePath in @($coreSource, $dependenciesSource)) {
        if ((Get-Item -LiteralPath $sourcePath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw ('Refusing to move a linked runtime source: ' + $sourcePath)
        }
    }
    [void](New-Item -ItemType Directory -Path $bundleRuntime)
    Move-Item -LiteralPath $coreSource -Destination $coreTarget
    Move-Item -LiteralPath $dependenciesSource -Destination $dependenciesTarget
    if (-not (Test-Path -LiteralPath $coreTarget -PathType Leaf) -or
        -not (Test-Path -LiteralPath $dependenciesTarget -PathType Container) -or
        (Test-Path -LiteralPath $coreSource) -or (Test-Path -LiteralPath $dependenciesSource)) {
        throw 'Runtime relocation did not produce the required service-folder layout.'
    }
}

if ([string]::IsNullOrWhiteSpace($Python)) {
    $localPython = Join-Path $projectRoot '..\venv\Scripts\python.exe'
    $projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $projectPython) { $Python = $projectPython }
    elseif (Test-Path -LiteralPath $localPython) { $Python = $localPython }
    else { $Python = 'python' }
}
if (Test-Path -LiteralPath $Python) { $Python = [IO.Path]::GetFullPath($Python) }
Push-Location -LiteralPath $projectRoot
try {
    & $Python -c 'import sys,struct; assert (3,12) <= sys.version_info < (3,15); assert struct.calcsize(chr(80))==8; print(sys.version)'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12-3.14 x64 is required by the pinned Qt bindings.' }
    if (-not $SkipInstall) {
        & $Python -m pip install -r (Join-Path $projectRoot 'requirements.txt') 'pyinstaller==6.22.3' 'pyinstaller-hooks-contrib==2026.8' 'pytest==9.1.1'
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    }
    & $Python (Join-Path $PSScriptRoot 'collect_licenses.py')
    if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
    if (-not $SkipTests) {
        & $Python -m pytest
        if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    }
    $buildRoot = Join-Path $projectRoot 'build'
    $distRoot = Join-Path $buildRoot 'dist'
    Move-PreviousCollectedBundle -ProjectRoot $projectRoot
    $originalBuildPath = $env:PATH
    $runtimeRoot = & $Python -c 'import sys; print(sys.base_prefix)'
    $windowsRoot = [Environment]::GetFolderPath('Windows')
    try {
        # Native tools elsewhere on PATH can shadow Qt's Windows ICU or
        # Python's OpenSSL during dependency collection. Use known runtimes.
        $env:PATH = @((Split-Path -Parent $Python), $runtimeRoot,
            (Join-Path $runtimeRoot 'DLLs'), (Join-Path $windowsRoot 'System32'),
            $windowsRoot) -join ';'
        & $Python -m PyInstaller --noconfirm --clean --distpath $distRoot --workpath (Join-Path $buildRoot 'pyinstaller') (Join-Path $projectRoot 'MiraMediaDownloader.spec')
        if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
    }
    finally { $env:PATH = $originalBuildPath }
    $appRoot = Join-Path $distRoot 'MiraMediaDownloader'
    # Keep the PyInstaller Core's original sibling _internal relationship.
    # Only the small public native launcher remains executable at bundle root.
    Move-CollectedRuntime -BundleRoot $appRoot
    $nativeOptions = @{ OutputDirectory = $appRoot }
    if (-not [string]::IsNullOrWhiteSpace($BuildToolsRoot)) { $nativeOptions.BuildToolsRoot = $BuildToolsRoot }
    if (-not [string]::IsNullOrWhiteSpace($WindowsSdkRoot)) { $nativeOptions.WindowsSdkRoot = $WindowsSdkRoot }
    & (Join-Path $PSScriptRoot 'build-launcher.ps1') @nativeOptions
    if ($LASTEXITCODE -ne 0) { throw 'Native startup launcher build failed.' }
    foreach ($entryPoint in @('MiraMediaDownloader.exe','runtime\MiraMediaDownloaderCore.exe')) {
        if (-not (Test-Path -LiteralPath (Join-Path $appRoot $entryPoint) -PathType Leaf)) {
            throw ('Missing application entry point: ' + $entryPoint)
        }
    }
    $rootExecutables = @(Get-ChildItem -LiteralPath $appRoot -File -Filter '*.exe')
    if ($rootExecutables.Count -ne 1 -or $rootExecutables[0].Name -ne 'MiraMediaDownloader.exe') {
        throw 'The bundle root must contain only the public MiraMediaDownloader.exe executable.'
    }
    # Importing Python bindings is insufficient: the login window also needs
    # Qt's own renderer process, its native dependencies, ICU data and locales.
    foreach ($webEngineFile in @(
        'runtime\_internal\PySide6\QtWebEngineProcess.exe',
        'runtime\_internal\PySide6\Qt6WebEngineCore.dll',
        'runtime\_internal\PySide6\Qt6WebEngineWidgets.dll',
        'runtime\_internal\PySide6\Qt6Quick.dll',
        'runtime\_internal\PySide6\Qt6Qml.dll',
        'runtime\_internal\PySide6\Qt6WebChannel.dll',
        'runtime\_internal\PySide6\Qt6Positioning.dll',
        'runtime\_internal\PySide6\resources\icudtl.dat',
        'runtime\_internal\PySide6\resources\qtwebengine_resources.pak',
        'runtime\_internal\PySide6\resources\v8_context_snapshot.bin',
        'runtime\_internal\PySide6\translations\qtwebengine_locales\en-US.pak',
        'runtime\_internal\PySide6\translations\qtwebengine_locales\ru.pak',
        'runtime\_internal\PySide6\translations\qtwebengine_locales\zh-CN.pak',
        'runtime\_internal\PySide6\translations\qtbase_en.qm',
        'runtime\_internal\PySide6\translations\qtbase_ru.qm',
        'runtime\_internal\PySide6\translations\qtbase_zh_CN.qm'
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $appRoot $webEngineFile) -PathType Leaf)) {
            throw ('Missing Qt WebEngine runtime file: ' + $webEngineFile)
        }
    }
    foreach ($docName in @('README.md','README.txt','ARCHITECTURE.md','ROADMAP.md','GITHUB_PUBLISHING.md','LICENSE','COPYRIGHT','SOURCE_CODE.txt','THIRD_PARTY_NOTICES.md','requirements.txt')) {
        Copy-Item -LiteralPath (Join-Path $projectRoot $docName) -Destination $appRoot -Force
    }
    Copy-Item -LiteralPath (Join-Path $projectRoot 'licenses') -Destination $appRoot -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $projectRoot 'docs') -Destination $appRoot -Recurse -Force
    # Complete dependency sources are separate, checksum-verified release assets
    # referenced by SOURCE_CODE.txt; never package an untracked local cache.
    & $Python -m pip list --format=json | Set-Content -LiteralPath (Join-Path $appRoot 'dependency-versions.json') -Encoding utf8
    $manifestPath = Join-Path $appRoot 'manifest.sha256'
    $manifest = Get-ChildItem -LiteralPath $appRoot -Recurse -File |
        Where-Object { $_.FullName -ne $manifestPath } |
        Sort-Object FullName |
        ForEach-Object {
            $rootUri = [Uri]($appRoot.TrimEnd('\') + '\')
            $relative = [Uri]::UnescapeDataString($rootUri.MakeRelativeUri([Uri]$_.FullName).ToString())
            '{0}  {1}' -f (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(), $relative
        }
    $manifest | Set-Content -LiteralPath $manifestPath -Encoding utf8
    $packageVersion = & $Python (Join-Path $PSScriptRoot 'package_version.py')
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($packageVersion)) { throw 'Could not read package version.' }
    $zipPath = [IO.Path]::GetFullPath((Join-Path $distRoot ('MiraMediaDownloader-' + $packageVersion.Trim() + '-Windows-x64.zip')))
    if ([IO.Path]::GetDirectoryName($zipPath) -ne [IO.Path]::GetFullPath($distRoot)) { throw 'ZIP target escaped the build distribution directory.' }
    # The selected Python supports explicit extended paths even when the host
    # PowerShell/.NET runtime cannot enumerate deep attribution filenames.
    & $Python (Join-Path $PSScriptRoot 'archive_bundle.py') $appRoot $zipPath
    if ($LASTEXITCODE -ne 0) { throw 'Python ZIP compression failed.' }
    Write-Output ('Ready folder: ' + $appRoot)
    Write-Output ('Ready ZIP: ' + $zipPath)
    Get-FileHash -LiteralPath $zipPath -Algorithm SHA256 | Format-List
}
finally { Pop-Location }
