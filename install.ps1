<#
Installs the Claude Code starterkit on Windows: downloads the installer binary for this CPU from the
latest GitHub release, checks its SHA-256, and runs it. Safe to re-run.

  irm https://github.com/MatLomax/claude-starterkit/releases/latest/download/install.ps1 | iex

With options (| iex cannot pass arguments, so use the scriptblock form):

  & ([scriptblock]::Create((irm https://github.com/MatLomax/claude-starterkit/releases/latest/download/install.ps1))) -NoWorklog

  -NoWorklog      skip the worklog add-on (no prompt)
  -WithWorklog    install it without prompting
  -Plugins LIST   install these recommended plugins without prompting (comma-separated)
  -NoPlugins      install no recommended plugins (no prompt)
  -PluginHooks    also run each installed plugin's follow-up steps without prompting

$env:STARTERKIT_VERSION = "X.Y.Z" installs that release instead of the latest.
#>
param(
  [switch]$WithWorklog,
  [switch]$NoWorklog,
  [string]$Plugins,
  [switch]$NoPlugins,
  [switch]$PluginHooks
)
# Under `irm | iex` this script runs in the caller's own scope. The body runs in a child scope so
# none of its settings or variables are left behind in the user's session.
& {
  param([bool]$asFile, [bool]$pluginsGiven)
  $ErrorActionPreference = "Stop"
  $Repo = "MatLomax/claude-starterkit"

  switch ($env:PROCESSOR_ARCHITECTURE) {
    "AMD64" { $arch = "x64" }
    "ARM64" { $arch = "arm64" }
    default { throw "install.ps1: no prebuilt installer for Windows/$($env:PROCESSOR_ARCHITECTURE)" }
  }
  $asset = "starterkit-install-windows-$arch.exe"

  if ($env:STARTERKIT_VERSION) {
    $base = "https://github.com/$Repo/releases/download/v$($env:STARTERKIT_VERSION.TrimStart('v'))"
  } else {
    $base = "https://github.com/$Repo/releases/latest/download"
  }
  # STARTERKIT_BASE_URL points at another copy of the release assets (e.g. a test server).
  if ($env:STARTERKIT_BASE_URL) { $base = $env:STARTERKIT_BASE_URL }

  $tmp = Join-Path ([IO.Path]::GetTempPath()) ("starterkit-" + [Guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Path $tmp | Out-Null
  try {
    $exe = Join-Path $tmp $asset
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest -UseBasicParsing -Uri "$base/$asset" -OutFile $exe
    Invoke-WebRequest -UseBasicParsing -Uri "$base/$asset.sha256" -OutFile "$exe.sha256"
    $want = ((Get-Content "$exe.sha256" -Raw).Trim() -split '\s+')[0].ToLower()
    $got = (Get-FileHash -Algorithm SHA256 -Path $exe).Hash.ToLower()
    if (-not $want -or $want -ne $got) { throw "install.ps1: checksum mismatch for $asset (expected $want, got $got)" }

    $argv = @()
    if ($WithWorklog) { $argv += "--with-worklog" }
    if ($NoWorklog) { $argv += "--no-worklog" }
    if ($pluginsGiven) { $argv += "--plugins=$Plugins" }
    if ($NoPlugins) { $argv += "--no-plugins" }
    if ($PluginHooks) { $argv += "--plugin-hooks" }

    & $exe @argv
    $status = $LASTEXITCODE
  } finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
  }
  # Run as a file, pass the installer's exit code on. Under `irm | iex` this script runs inside the
  # caller's own session, where `exit` would close their window, so leave the code in $LASTEXITCODE.
  if ($asFile) { exit $status }
  $global:LASTEXITCODE = $status
} ([bool]$MyInvocation.MyCommand.Path) ($PSBoundParameters.ContainsKey("Plugins"))
