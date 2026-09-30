# Build the Windows installer (gui\dist\what-<version>-x64-setup.exe).
#
#   powershell -ExecutionPolicy Bypass -File scripts\package\build_windows.ps1
#
# Steps (each can be skipped once its output exists; -Clean rebuilds everything):
#   1. Toolchain: Node.js, CMake and the Visual Studio 2022 C++ Build Tools. Anything
#      missing is installed with winget after asking (-Yes answers yes; -NoInstall only
#      reports). The C++ tools are needed only for the OBS plugin (-SkipObsPlugin).
#   2. Python runtime: a relocatable CPython (python-build-standalone) with the app's
#      dependencies preinstalled, so users need no Python of their own.
#   3. FFmpeg: a static ffmpeg.exe for microphone capture.
#   4. OBS plugin: built against libobs headers; the installer places it in OBS's
#      per-machine plugin folder when OBS is installed.
#   5. electron-builder NSIS installer (-Target dir: just gui\dist\win-unpacked, for testing).
#
# Smart App Control (Windows 11) blocks the unsigned helper executable electron-builder
# compiles and runs to produce the NSIS uninstaller, so on a machine with it enabled use
# -Target dir locally and build the installer in CI (GitHub-hosted runners don't enable it).
param(
    [ValidateSet("nsis", "dir")]
    [string]$Target = "nsis",
    [switch]$Yes,
    [switch]$NoInstall,
    [switch]$SkipObsPlugin,
    [switch]$ToolchainOnly,
    [switch]$Clean
)

function Fail($msg) { Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }
function Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Test-Command($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function Update-SessionPath {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
$Gui = Join-Path $Root "gui"
$Build = Join-Path $Gui "build"
$Pins = Get-Content (Join-Path $PSScriptRoot "windows_pins.json") -Raw | ConvertFrom-Json
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest is very slow with a progress bar

function Confirm-Install($what) {
    if ($NoInstall) { return $false }
    if ($Yes) { return $true }
    $reply = Read-Host "$what is required but not installed. Install it now with winget? [Y/n]"
    return ($reply -eq "" -or $reply -match "^[Yy]")
}

function Install-Winget($id, $label, [string[]]$extra = @()) {
    if (-not (Test-Command winget)) { Fail "winget is unavailable; install $label manually and re-run." }
    Write-Host "Installing $label ($id)..."
    winget install --exact --id $id --accept-package-agreements --accept-source-agreements @extra
    Update-SessionPath
}

function Find-VsDevCmd {
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) { return $null }
    $install = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $install) { return $null }
    $cmd = Join-Path $install "Common7\Tools\VsDevCmd.bat"
    if (Test-Path $cmd) { return $cmd } else { return $null }
}

# Import the MSVC x64 environment (cl, link, lib, dumpbin) into this PowerShell session.
function Enter-VsDevShell {
    $devcmd = Find-VsDevCmd
    if (-not $devcmd) { Fail "Visual Studio C++ Build Tools not found." }
    $lines = cmd /c "`"$devcmd`" -arch=x64 -host_arch=x64 -no_logo && set"
    foreach ($line in $lines) {
        if ($line -match "^([^=]+)=(.*)$") { Set-Item -Path "env:$($Matches[1])" -Value $Matches[2] }
    }
}

function Get-File($url, $dest) {
    if (Test-Path $dest) { return }
    Write-Host "Downloading $url"
    $tmp = "$dest.part"
    Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
    Move-Item -Force $tmp $dest
}

# --- 1. Toolchain ----------------------------------------------------------------------
Step "Checking build toolchain"
Update-SessionPath
if (-not (Test-Command npm)) {
    if (Confirm-Install "Node.js") { Install-Winget "OpenJS.NodeJS.LTS" "Node.js LTS" }
    if (-not (Test-Command npm)) { Fail "Node.js/npm is required." }
}
if (-not $SkipObsPlugin) {
    if (-not (Test-Command cmake)) {
        if (Confirm-Install "CMake") { Install-Winget "Kitware.CMake" "CMake" }
        if (-not (Test-Command cmake)) { Fail "CMake is required for the OBS plugin (or pass -SkipObsPlugin)." }
    }
    if (-not (Find-VsDevCmd)) {
        if (Confirm-Install "Visual Studio 2022 C++ Build Tools (~5 GB; shows a UAC prompt)") {
            Install-Winget "Microsoft.VisualStudio.2022.BuildTools" "VS 2022 Build Tools" @(
                "--override", "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended")
        }
        if (-not (Find-VsDevCmd)) { Fail "The C++ Build Tools are required for the OBS plugin (or pass -SkipObsPlugin)." }
    }
}
Write-Host "Toolchain ready."
if ($ToolchainOnly) { exit 0 }

if ($Clean -and (Test-Path $Build)) { Remove-Item -Recurse -Force $Build }
New-Item -ItemType Directory -Force $Build, "$Build\downloads" | Out-Null

# --- 2. Python runtime -----------------------------------------------------------------
Step "Staging Python runtime"
$pyRuntime = Join-Path $Build "pyruntime"
if (Test-Path $pyRuntime) { Remove-Item -Recurse -Force $pyRuntime }
New-Item -ItemType Directory -Force $pyRuntime | Out-Null
Copy-Item -Recurse (Join-Path $Root "what") (Join-Path $pyRuntime "what")
Copy-Item -Recurse (Join-Path $Root "config") (Join-Path $pyRuntime "config")
Copy-Item (Join-Path $Root "pyproject.toml") $pyRuntime
Get-ChildItem $pyRuntime -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

$python = Join-Path $Build "python"
$pythonExe = Join-Path $python "python.exe"
if (-not (Test-Path (Join-Path $python ".what-deps"))) {
    $archive = Join-Path "$Build\downloads" (Split-Path $Pins.python.url -Leaf)
    Get-File $Pins.python.url $archive
    if (Test-Path $python) { Remove-Item -Recurse -Force $python }
    $extract = Join-Path $Build "python-extract"
    if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
    New-Item -ItemType Directory -Force $extract | Out-Null
    tar -xzf $archive -C $extract
    if ($LASTEXITCODE -ne 0) { Fail "could not extract $archive" }
    Move-Item (Join-Path $extract "python") $python
    Remove-Item -Recurse -Force $extract

    # The app's dependency list lives in gui/lib/python_runtime.js (shared with Linux).
    $deps = node -e "console.log(JSON.stringify(require(process.argv[1]).DEPENDENCIES))" (Join-Path $Gui "lib\python_runtime.js") | ConvertFrom-Json
    & $pythonExe -m pip install --no-warn-script-location --disable-pip-version-check @deps
    if ($LASTEXITCODE -ne 0) { Fail "installing Python dependencies failed" }
    & $pythonExe -c "import faster_whisper, ctranslate2, webrtcvad, soundcard, fastapi, uvicorn, websockets, zeroconf; print('python deps ok')"
    if ($LASTEXITCODE -ne 0) { Fail "the bundled Python cannot import its dependencies" }
    # Bytecode caches and tests are dead weight in the installer.
    Get-ChildItem $python -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
    Set-Content (Join-Path $python ".what-deps") (Get-Date -Format o)
}

# --- 3. FFmpeg -------------------------------------------------------------------------
Step "Staging FFmpeg"
$bin = Join-Path $Build "bin"
New-Item -ItemType Directory -Force $bin | Out-Null
if (-not (Test-Path (Join-Path $bin "ffmpeg.exe"))) {
    $zip = Join-Path "$Build\downloads" (Split-Path $Pins.ffmpeg.url -Leaf)
    Get-File $Pins.ffmpeg.url $zip
    $extract = Join-Path $Build "ffmpeg-extract"
    if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
    Expand-Archive -Path $zip -DestinationPath $extract
    $exe = Get-ChildItem $extract -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
    if (-not $exe) { Fail "ffmpeg.exe not found in $zip" }
    Copy-Item $exe.FullName $bin
    $license = Get-ChildItem $extract -Recurse -Filter "LICENSE*" | Select-Object -First 1
    if ($license) { Copy-Item $license.FullName (Join-Path $bin "FFMPEG-LICENSE.txt") }
    Remove-Item -Recurse -Force $extract
}

# --- 4. OBS plugin ---------------------------------------------------------------------
$obsOut = Join-Path $Build "obs-plugin"
if (-not $SkipObsPlugin) {
    Step "Building the OBS plugin"
    & (Join-Path $PSScriptRoot "build_obs_plugin_windows.ps1") -Pins $Pins -BuildDir $Build -OutDir $obsOut
    if ($LASTEXITCODE -ne 0) { Fail "OBS plugin build failed (re-run with -SkipObsPlugin to build without it)" }
} elseif (-not (Test-Path $obsOut)) {
    New-Item -ItemType Directory -Force $obsOut | Out-Null
}

# --- 5. Installer ----------------------------------------------------------------------
Step "Building the installer"
Push-Location $Gui
try {
    # Reinstall only when node_modules doesn't match the lockfile: `npm ci` deletes the
    # folder first, which fails halfway (leaving it broken) while a dev GUI runs from it.
    npm ls --depth=0 --silent *> $null
    if ($Clean -or $LASTEXITCODE -ne 0) {
        $running = Get-CimInstance Win32_Process -Filter "Name='electron.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.ExecutablePath -like "$Gui\node_modules\*" }
        if ($running) { Fail "close the running dev GUI (it locks gui\node_modules), then re-run." }
        npm ci
        if ($LASTEXITCODE -ne 0) { Fail "npm ci failed" }
    }
    # electron-builder's winCodeSign tools archive contains macOS symlinks, which Windows
    # cannot create without Developer Mode or admin rights, so its own extraction fails.
    # Pre-extract it into electron-builder's cache without the darwin part.
    $wcs = "winCodeSign-2.6.0"
    $cacheRoot = if ($env:ELECTRON_BUILDER_CACHE) { $env:ELECTRON_BUILDER_CACHE } else { Join-Path $env:LOCALAPPDATA "electron-builder\Cache" }
    $wcsDir = Join-Path $cacheRoot "winCodeSign\$wcs"
    if (-not (Test-Path (Join-Path $wcsDir "rcedit-x64.exe"))) {
        $wcsArchive = Join-Path "$Build\downloads" "$wcs.7z"
        Get-File "https://github.com/electron-userland/electron-builder-binaries/releases/download/$wcs/$wcs.7z" $wcsArchive
        & (Join-Path $Gui "node_modules\7zip-bin\win\x64\7za.exe") x -bd -y "-x!darwin" $wcsArchive "-o$wcsDir" | Out-Null
        if ($LASTEXITCODE -ne 0) { Fail "could not extract $wcs" }
    }
    npx electron-builder --win $Target --x64 --publish never
    if ($LASTEXITCODE -ne 0) {
        $sac = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy" -ErrorAction SilentlyContinue).VerifiedAndReputablePolicyState
        if ($Target -eq "nsis" -and $sac -eq 1) {
            Fail ("electron-builder failed; Smart App Control is on and blocks the unsigned uninstaller stub " +
                  "it must run. Use -Target dir to test locally and build the installer in CI.")
        }
        Fail "electron-builder failed"
    }
} finally {
    Pop-Location
}
if ($Target -eq "dir") {
    Write-Host "Built $(Join-Path $Gui 'dist\win-unpacked\What.exe')"
} else {
    Get-ChildItem (Join-Path $Gui "dist") -Filter "*-setup.exe" | ForEach-Object { Write-Host "Built $($_.FullName)" }
}
