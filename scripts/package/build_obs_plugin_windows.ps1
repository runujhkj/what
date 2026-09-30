# Build the What OBS plugin for Windows into an OBS plugin-folder layout:
#   <OutDir>\what_overlay_plugin\bin\64bit\what_overlay_plugin.dll
#   <OutDir>\what_overlay_plugin\data\locale\en-US.ini
# which the installer copies to %ProgramData%\obs-studio\plugins\ (OBS 30+).
#
# OBS ships obs.dll but no import library, so obs.lib is generated from the DLL's exports.
# Headers come from the pinned obs-studio source; the plugin then loads on that OBS
# version and newer. Needs the VS 2022 C++ Build Tools and CMake (build_windows.ps1
# installs them: build_windows.ps1 -ToolchainOnly). Usually called by build_windows.ps1.
# From a source checkout, build it and install it into OBS (close OBS first) with:
#   powershell -ExecutionPolicy Bypass -File scripts\package\build_obs_plugin_windows.ps1 -Install
param(
    $Pins,
    [string]$BuildDir,
    [string]$OutDir,
    [switch]$Install
)

function Fail($msg) { Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }

$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
if (-not $Pins) { $Pins = Get-Content (Join-Path $PSScriptRoot "windows_pins.json") -Raw | ConvertFrom-Json }
if (-not $BuildDir) { $BuildDir = Join-Path $Root "gui\build" }
if (-not $OutDir) { $OutDir = Join-Path $BuildDir "obs-plugin" }
$work = Join-Path $BuildDir "obs-work"
$downloads = Join-Path $BuildDir "downloads"
New-Item -ItemType Directory -Force $work, $downloads | Out-Null
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"

function Get-File($url, $dest) {
    if (Test-Path $dest) { return }
    Write-Host "Downloading $url"
    Invoke-WebRequest -Uri $url -OutFile "$dest.part" -UseBasicParsing
    Move-Item -Force "$dest.part" $dest
}

# MSVC environment (cl, link, lib, dumpbin) for this session.
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere)) { Fail "Visual Studio Build Tools not found (run build_windows.ps1 -ToolchainOnly)." }
$vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { Fail "The Visual Studio C++ tools are not installed." }
foreach ($line in (cmd /c "`"$vs\Common7\Tools\VsDevCmd.bat`" -arch=x64 -host_arch=x64 -no_logo && set")) {
    if ($line -match "^([^=]+)=(.*)$") { Set-Item -Path "env:$($Matches[1])" -Value $Matches[2] }
}
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) { Fail "CMake is not on PATH." }

# --- libobs headers ----------------------------------------------------------------------
$ver = $Pins.obs.version
$srcRoot = Join-Path $work "obs-studio-$ver"
if (-not (Test-Path (Join-Path $srcRoot "libobs\obs-module.h"))) {
    $tarball = Join-Path $downloads "obs-studio-$ver.tar.gz"
    Get-File $Pins.obs.source_url $tarball
    tar -xzf $tarball -C $work "obs-studio-$ver/libobs"
    if ($LASTEXITCODE -ne 0) { Fail "could not extract libobs headers" }
}

# --- obs.lib from obs.dll exports ----------------------------------------------------------
$libDir = Join-Path $work "lib"
$obsLib = Join-Path $libDir "obs.lib"
if (-not (Test-Path $obsLib)) {
    New-Item -ItemType Directory -Force $libDir | Out-Null
    $obsDll = Join-Path $work "obs.dll"
    if (-not (Test-Path $obsDll)) {
        $zip = Join-Path $downloads "OBS-Studio-$ver-Windows.zip"
        Get-File $Pins.obs.binary_url $zip
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $archive = [IO.Compression.ZipFile]::OpenRead($zip)
        try {
            $entry = $archive.Entries | Where-Object { $_.FullName -match "(^|/)bin/64bit/obs\.dll$" } | Select-Object -First 1
            if (-not $entry) { Fail "obs.dll not found in $zip" }
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $obsDll, $true)
        } finally { $archive.Dispose() }
    }
    $names = dumpbin /nologo /exports $obsDll | ForEach-Object {
        if ($_ -match "^\s+\d+\s+[0-9A-Fa-f]+\s+[0-9A-Fa-f]+\s+(\S+)") { $Matches[1] }
    }
    if (-not $names) { Fail "no exports read from obs.dll" }
    $def = Join-Path $libDir "obs.def"
    @("LIBRARY obs", "EXPORTS") + $names | Set-Content -Encoding ascii $def
    lib /nologo /def:$def /machine:x64 /out:$obsLib | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "could not generate obs.lib" }
}

# --- Build ---------------------------------------------------------------------------------
$cmakeBuild = Join-Path $work "build"
cmake -S (Join-Path $Root "obs-plugin") -B $cmakeBuild -G "Visual Studio 17 2022" -A x64 `
    "-DOBS_INCLUDE_DIR=$srcRoot\libobs" "-DOBS_LIB_DIR=$libDir" `
    "-DOBS_CONFIG_DIR=$Root\obs-plugin\obsconfig" `
    -DWHAT_OVERLAY_ENABLE_FRONTEND_PANEL=OFF -DWHAT_OVERLAY_BUILD_UNIT_TESTS=OFF
if ($LASTEXITCODE -ne 0) { Fail "CMake configure failed" }
cmake --build $cmakeBuild --config Release --target what_overlay_plugin
if ($LASTEXITCODE -ne 0) { Fail "plugin compile failed" }

$dll = Get-ChildItem $cmakeBuild -Recurse -Filter "what_overlay_plugin.dll" | Select-Object -First 1
if (-not $dll) { Fail "what_overlay_plugin.dll was not produced" }
$pluginRoot = Join-Path $OutDir "what_overlay_plugin"
if (Test-Path $pluginRoot) { Remove-Item -Recurse -Force $pluginRoot }
New-Item -ItemType Directory -Force "$pluginRoot\bin\64bit", "$pluginRoot\data\locale" | Out-Null
Copy-Item $dll.FullName "$pluginRoot\bin\64bit\"
# OBS_MODULE_USE_DEFAULT_LOCALE loads data\locale\en-US.ini; the plugin's strings are inline.
Set-Content -Encoding ascii "$pluginRoot\data\locale\en-US.ini" ""
Write-Host "OBS plugin staged at $pluginRoot"
if ($Install) {
    # Same destination the installer uses: OBS 30+ per-machine plugins, user-writable.
    $dest = Join-Path $env:ProgramData "obs-studio\plugins"
    New-Item -ItemType Directory -Force $dest | Out-Null
    Copy-Item -Recurse -Force $pluginRoot $dest
    if (-not $?) { Fail "could not copy the plugin to $dest (is OBS running?)" }
    Write-Host "Installed to $dest\what_overlay_plugin. Restart OBS and add a 'What Caption Box' source."
}
exit 0
