<#
Installs the Claude Code starterkit on Windows: downloads the installer binary for this CPU from the
latest GitHub release, checks its SHA-256, and runs it. Safe to re-run.

  irm https://github.com/MatLomax/claude-starterkit/releases/latest/download/install.ps1 | iex

With options (| iex cannot pass arguments, so use the scriptblock form):

  & ([scriptblock]::Create((irm https://github.com/MatLomax/claude-starterkit/releases/latest/download/install.ps1))) -NoWorklog

  -NoWorklog      skip the worklog add-on (no prompt)
  -WithWorklog    install it without prompting
  -WithProjectMemory  keep each git repo's auto memory in <repo>\.claude\memory (no prompt)
  -NoProjectMemory    skip the project-memory add-on (no prompt; the default)
  -Plugins LIST   install these recommended plugins without prompting (comma-separated)
  -NoPlugins      install no recommended plugins (no prompt)
  -PluginHooks    also run each installed plugin's follow-up steps without prompting

$env:STARTERKIT_VERSION = "X.Y.Z" installs that release instead of the latest.
#>
# Under `irm | iex` this text runs in the caller's own scope, so it has no script-level param block
# and assigns no variable there: everything runs in the child scope below, which leaves none of its
# settings or variables behind in the user's session. The options are read from $args instead.
#
# The three arguments are evaluated here, in the caller's scope, and are StrictMode-safe:
#  - whether this text was parsed from a file: `{}.File` is that file, and is empty under `irm | iex`
#    and [scriptblock]::Create.
#  - $args, when the scope has one. The leading comma hands the array over whole, so a
#    `-Plugins a,b` array inside it stays one element.
#  - $MyInvocation, the invocation that owns this scope.
& {
  param([bool]$fromFile, [object[]]$rawArgs, $caller)

  # $args holds installer options only when this scope is this script's own: a file run, or the
  # scriptblock form. Under `irm | iex` the scope is the caller's (their prompt, script or function),
  # whose $args are theirs, so none are read. Their scope is ours when the invoked command's script
  # block is this text.
  $root = {}.Ast
  while ($null -ne $root.Parent) { $root = $root.Parent }
  $own = $fromFile
  if (-not $own -and $null -ne $caller -and $null -ne $caller.MyCommand -and $null -ne $caller.MyCommand.PSObject.Properties["ScriptBlock"]) {
    $sb = $caller.MyCommand.ScriptBlock
    $own = $null -ne $sb -and ([object]::ReferenceEquals($sb.Ast, $root) -or $sb.Ast.Extent.Text -ceq $root.Extent.Text)
  }
  if (-not $own -or $null -eq $rawArgs) { $rawArgs = @() }
  # Run as a file, the installer's exit code is the script's; otherwise `exit` would end the
  # caller's session or script.
  $asFile = $fromFile -and $null -ne $caller -and $null -ne $caller.MyCommand -and $caller.MyCommand.CommandType -eq "ExternalScript"

  $ErrorActionPreference = "Stop"
  $Repo = "MatLomax/claude-starterkit"

  # Options, matched like PowerShell parameters: case-insensitive, any unambiguous prefix, and
  # `-Name:value` (which reaches $args as "-Name:" followed by the value).
  $switches = @{ WithWorklog = "--with-worklog"; NoWorklog = "--no-worklog"; WithProjectMemory = "--with-project-memory"; NoProjectMemory = "--no-project-memory"; NoPlugins = "--no-plugins"; PluginHooks = "--plugin-hooks" }
  $names = @($switches.Keys) + "Plugins"
  $usage = "expected -WithWorklog, -NoWorklog, -WithProjectMemory, -NoProjectMemory, -Plugins LIST, -NoPlugins, -PluginHooks"
  $argv = @()
  $i = 0
  while ($i -lt $rawArgs.Count) {
    $arg = $rawArgs[$i]
    $i++
    if (-not ($arg -is [string] -and $arg -match '^-([A-Za-z]+)(:(.*))?$')) {
      throw "install.ps1: unexpected argument '$arg' ($usage)"
    }
    $given = $Matches[1]
    $colon = [bool]$Matches[2]
    $inline = [string]$Matches[3]
    $name = @($names | Where-Object { $_ -eq $given })
    if ($name.Count -eq 0) { $name = @($names | Where-Object { $_.StartsWith($given, [StringComparison]::OrdinalIgnoreCase) }) }
    if ($name.Count -eq 0) { throw "install.ps1: unknown option '-$given' ($usage)" }
    if ($name.Count -gt 1) { throw "install.ps1: ambiguous option '-$given' (matches -$($name -join ', -'))" }
    $name = $name[0]

    # The value of -Plugins, or of a switch written `-Switch:$false`: after the colon in the same
    # argument, else the next argument.
    $hasValue = $false
    $value = $null
    if ($colon -and $inline -ne "") {
      $hasValue = $true
      $value = $inline
    } elseif ($colon -or $name -eq "Plugins") {
      if ($i -ge $rawArgs.Count) { throw "install.ps1: -$name needs a value" }
      $hasValue = $true
      $value = $rawArgs[$i]
      $i++
    }

    if ($name -eq "Plugins") {
      $argv += "--plugins=" + ((@($value) | ForEach-Object { "$_" }) -join ",")
    } else {
      $on = $true
      if ($hasValue) {
        if ($value -is [bool]) {
          $on = $value
        } elseif ("$value" -in "true", "1") {
          $on = $true
        } elseif ("$value" -in "false", "0") {
          $on = $false
        } else {
          throw "install.ps1: -$name takes no value, or `$true / `$false (got '$value')"
        }
      }
      if ($on) { $argv += $switches[$name] }
    }
  }

  # The machine's CPU: a 32-bit PowerShell on 64-bit Windows sees PROCESSOR_ARCHITECTURE=x86 and
  # the real one in PROCESSOR_ARCHITEW6432.
  $cpu = $env:PROCESSOR_ARCHITEW6432
  if (-not $cpu) { $cpu = $env:PROCESSOR_ARCHITECTURE }
  switch ($cpu) {
    "AMD64" { $arch = "x64" }
    "ARM64" { $arch = "arm64" }
    default { throw "install.ps1: no prebuilt installer for Windows/$cpu" }
  }
  $asset = "starterkit-install-windows-$arch.exe"

  if ($env:STARTERKIT_VERSION) {
    $base = "https://github.com/$Repo/releases/download/v$($env:STARTERKIT_VERSION.TrimStart('v'))"
  } else {
    $base = "https://github.com/$Repo/releases/latest/download"
  }
  # STARTERKIT_BASE_URL points at another copy of the release assets (e.g. a test server).
  if ($env:STARTERKIT_BASE_URL) { $base = $env:STARTERKIT_BASE_URL }

  # Windows PowerShell 5.1 on an older .NET Framework may not offer TLS 1.2, which GitHub requires.
  # Add it for these downloads and put the session's setting back afterwards. (A setting of 0,
  # SystemDefault, already lets the OS pick TLS 1.2 or later.)
  $tls = [Net.ServicePointManager]::SecurityProtocol
  $tls12 = [Net.SecurityProtocolType]::Tls12
  $addTls12 = [int]$tls -ne 0 -and ([int]$tls -band [int]$tls12) -eq 0

  $tmp = Join-Path ([IO.Path]::GetTempPath()) ("starterkit-" + [Guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Path $tmp | Out-Null
  try {
    if ($addTls12) { [Net.ServicePointManager]::SecurityProtocol = $tls -bor $tls12 }
    $exe = Join-Path $tmp $asset
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest -UseBasicParsing -Uri "$base/$asset" -OutFile $exe
    Invoke-WebRequest -UseBasicParsing -Uri "$base/$asset.sha256" -OutFile "$exe.sha256"
    $want = ((Get-Content "$exe.sha256" -Raw).Trim() -split '\s+')[0].ToLower()
    $got = (Get-FileHash -Algorithm SHA256 -Path $exe).Hash.ToLower()
    if (-not $want -or $want -ne $got) { throw "install.ps1: checksum mismatch for $asset (expected $want, got $got)" }

    & $exe @argv
    $status = $LASTEXITCODE
  } finally {
    if ($addTls12) { [Net.ServicePointManager]::SecurityProtocol = $tls }
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
  }
  # Run as a file, pass the installer's exit code on. Under `irm | iex` this script runs inside the
  # caller's own session, where `exit` would close their window, so leave the code in $LASTEXITCODE.
  if ($asFile) { exit $status }
  $global:LASTEXITCODE = $status
} ([bool]({}.File)) $(if (Test-Path variable:args) { , $args } else { , @() }) $(if (Test-Path variable:MyInvocation) { $MyInvocation })
