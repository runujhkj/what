# Set up a Windows source checkout: Python venv, GUI dependencies, and prerequisite checks.
#
# If PowerShell refuses to run scripts, launch it with a one-off bypass instead of changing
# the machine policy:
#   powershell -ExecutionPolicy Bypass -File scripts\setup\setup_windows.ps1
#
# Missing prerequisites are installed (pass -NoInstall to only report what is missing):
# Python 3.12 via the Python install manager or the official python.org installer, and
# Node.js / FFmpeg via winget.
param(
    [ValidateSet("all","client","service")]
    [string]$Role = "all",
    [switch]$NoInstall
)

# Not "Stop": Windows PowerShell 5.1 turns a native command's redirected stderr into a
# terminating error, which would abort the version probes below. Failures exit via Fail.
function Fail($msg) { Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }
Set-Location (Resolve-Path "$PSScriptRoot\..\..")

switch ($Role) {
    "all" { $req = "requirements.txt" }
    "client" { $req = "requirements-client.txt" }
    "service" { $req = "requirements-service.txt" }
}

# Python releases with prebuilt wheels for every dependency (webrtcvad-wheels stops at 3.13).
$SupportedPython = @("3.12", "3.13", "3.11")

function Test-Command($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

function Update-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Install-WithWinget($id, $label) {
    if ($NoInstall) { return $false }
    if (-not (Test-Command winget)) {
        Write-Warning "winget is unavailable; install $label manually."
        return $false
    }
    Write-Host "Installing $label with winget ($id)..."
    winget install --exact --id $id --silent --accept-package-agreements --accept-source-agreements
    Update-SessionPath
    return $true
}

function Find-Python {
    # The py launcher can select a specific version; a bare `python` may be 3.14 or the
    # Microsoft Store alias, so it is only used when it reports a supported version.
    if (Test-Command py) {
        foreach ($v in $SupportedPython) {
            & py "-$v" -c "import sys" 2>$null
            if ($LASTEXITCODE -eq 0) { return @("py", "-$v") }
        }
    }
    if (Test-Command python) {
        $ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $SupportedPython -contains "$ver") { return @("python") }
    }
    return $null
}

# Not winget: it maps Pythons installed by the Python install manager (python.org's default
# on Windows) to the Python.Python.3.12 package and then reports 3.12 as already installed.
function Install-Python312 {
    if ($NoInstall) { return }
    if (Test-Command pymanager) {
        Write-Host "Installing Python 3.12 with the Python install manager..."
        pymanager install --yes 3.12
        return
    }
    # 3.12.10 is the last 3.12 release with a Windows installer. Per-user, no PATH change;
    # the py launcher finds it.
    $ver = "3.12.10"
    $url = "https://www.python.org/ftp/python/$ver/python-$ver-amd64.exe"
    $exe = Join-Path $env:TEMP "python-$ver-amd64.exe"
    Write-Host "Downloading $url"
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing
    Write-Host "Installing Python $ver for the current user..."
    Start-Process $exe -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_test=0", "Include_launcher=1" -Wait
    Remove-Item $exe -ErrorAction SilentlyContinue
    Update-SessionPath
}

# --- Python --------------------------------------------------------------------------------
$py = Find-Python
if (-not $py) {
    Install-Python312
    $py = Find-Python
}
if (-not $py) {
    Fail ("Python 3.12 (or 3.11/3.13) is required. Install it from https://www.python.org/downloads/ " +
                 "and re-run this script. Python 3.14 is not supported yet: some dependencies have no wheels for it.")
}
$pyExe = $py[0]
$pyArgs = @($py | Select-Object -Skip 1)
Write-Host "Using Python: $(& $pyExe @pyArgs -c 'import sys; print(sys.executable, sys.version.split()[0])')"

# An existing .venv built by an unsupported interpreter (e.g. 3.14) cannot install the
# dependencies, so rebuild it rather than failing halfway through pip.
$venvPy = ".\.venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $venvVer = & $venvPy -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($SupportedPython -notcontains "$venvVer") {
        Write-Host "Existing .venv uses Python $venvVer; recreating it."
        Remove-Item -Recurse -Force .venv
    }
}
if (-not (Test-Path $venvPy)) {
    & $pyExe @pyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "Could not create .venv" }
}

& $venvPy -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Fail "pip upgrade failed" }
& $venvPy -m pip install -r $req
if ($LASTEXITCODE -ne 0) { Fail "Installing $req failed; see the pip output above." }

# --- FFmpeg (mic/desktop capture) ----------------------------------------------------------
if ($Role -ne "service" -and -not (Test-Command ffmpeg)) {
    Install-WithWinget "Gyan.FFmpeg" "FFmpeg" | Out-Null
    if (-not (Test-Command ffmpeg)) {
        Write-Warning "FFmpeg is not on PATH. Install it (winget install Gyan.FFmpeg) and open a new terminal."
    }
}

# --- Node.js + GUI dependencies ------------------------------------------------------------
if ($Role -eq "all") {
    if (-not (Test-Command npm)) {
        Install-WithWinget "OpenJS.NodeJS.LTS" "Node.js LTS" | Out-Null
    }
    if (Test-Command npm) {
        npm --prefix gui ci
        if ($LASTEXITCODE -ne 0) { Fail "npm ci failed in gui/" }
    } else {
        Write-Warning "Node.js/npm is not on PATH; the GUI cannot start until it is installed."
    }
}

Write-Host ""
Write-Host "Setup complete. Start the app with:"
Write-Host "  .\.venv\Scripts\python -m what gui"
Write-Host "If ffmpeg/npm were just installed, open a new terminal first so PATH is refreshed."
