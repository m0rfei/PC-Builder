param([switch]$ReplaceExisting)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path $PSScriptRoot).Path
$distFolder = Join-Path $projectRoot 'dist\PC-Builder'
$releaseRoot = Join-Path $projectRoot 'release'
$buildDate = Get-Date -Format 'yyyyMMdd'
$releaseName = "PC-Builder-1.0-Beta-Windows-$buildDate"
$releaseFolder = Join-Path $releaseRoot $releaseName
$zipFile = Join-Path $releaseRoot "$releaseName.zip"

if (-not (Test-Path (Join-Path $distFolder 'PC-Builder.exe'))) {
    throw 'Сначала выполните build_windows.bat. Не найден dist\PC-Builder\PC-Builder.exe.'
}
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

if ((Test-Path $releaseFolder) -or (Test-Path $zipFile)) {
    if (-not $ReplaceExisting) {
        throw 'Папка или ZIP этой версии уже существует. Для явной замены запустите: .\package_release.ps1 -ReplaceExisting'
    }
    foreach ($target in @($releaseFolder, $zipFile)) {
        if (Test-Path $target) {
            $resolvedTarget = (Resolve-Path $target).Path
            if (-not $resolvedTarget.StartsWith($releaseRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Отказ от удаления пути вне папки релизов: $resolvedTarget"
            }
            Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
        }
    }
}

$stagingFolder = Join-Path $releaseRoot ('.staging-' + [guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory -Path $stagingFolder | Out-Null
    Get-ChildItem -LiteralPath $distFolder -Force | Copy-Item -Destination $stagingFolder -Recurse
    Copy-Item -LiteralPath (Join-Path $projectRoot 'README_RELEASE.txt') -Destination (Join-Path $stagingFolder 'README.txt')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'Create-Desktop-Shortcut.vbs') -Destination $stagingFolder
    Copy-Item -LiteralPath (Join-Path $projectRoot 'Backup-Database.bat') -Destination $stagingFolder
    Copy-Item -LiteralPath (Join-Path $projectRoot 'THIRD-PARTY-NOTICES.txt') -Destination $stagingFolder
    $pyInstallerInfo = Get-ChildItem -LiteralPath (Join-Path $projectRoot '.venv\Lib\site-packages') -Directory -Filter 'pyinstaller-*.dist-info' | Select-Object -First 1
    if (-not $pyInstallerInfo) {
        throw 'Не найдены метаданные PyInstaller для включения лицензии.'
    }
    $pyInstallerLicense = Join-Path $pyInstallerInfo.FullName 'licenses\COPYING.txt'
    if (-not (Test-Path -LiteralPath $pyInstallerLicense)) {
        throw 'Не найден файл лицензии PyInstaller.'
    }
    $thirdPartyLicenses = Join-Path $stagingFolder 'THIRD-PARTY-LICENSES'
    New-Item -ItemType Directory -Path $thirdPartyLicenses | Out-Null
    Copy-Item -LiteralPath $pyInstallerLicense -Destination (Join-Path $thirdPartyLicenses 'PyInstaller-COPYING.txt')
    $schemaText = Get-Content -LiteralPath (Join-Path $projectRoot 'src\pc_builder\database.py') -Raw
    if ($schemaText -notmatch '(?m)^SCHEMA_VERSION\s*=\s*(\d+)') {
        throw 'Не удалось определить версию схемы из src\pc_builder\database.py.'
    }
    $schemaVersion = $Matches[1]
    Set-Content -LiteralPath (Join-Path $stagingFolder 'VERSION.txt') -Encoding UTF8 -Value @(
        'PC-Builder 1.0 — предварительная бета для Windows'
        "Схема базы данных: $schemaVersion"
        'Сборка: onedir, автономный пакет'
    )
    Move-Item -LiteralPath $stagingFolder -Destination $releaseFolder
    Compress-Archive -LiteralPath $releaseFolder -DestinationPath $zipFile -CompressionLevel Optimal
} catch {
    if (Test-Path $stagingFolder) {
        $resolvedStaging = (Resolve-Path $stagingFolder).Path
        if ($resolvedStaging.StartsWith($releaseRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
        }
    }
    throw
}

Write-Output "Папка релиза: $releaseFolder"
Write-Output "ZIP-архив: $zipFile"
