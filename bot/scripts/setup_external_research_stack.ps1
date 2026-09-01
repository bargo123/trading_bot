[CmdletBinding()]
param(
    [string]$ProjectRoot = "C:\Users\Zaid barghouthi\Desktop\trading_bot",
    [switch]$SkipInstalls,
    [switch]$SkipUpstreamTests,
    [switch]$SkipPrerequisites,
    [switch]$SkipRepositoryClone,
    [switch]$InstallDocker,
    [int]$CloneTimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

$projectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$externalRoot = Join-Path $projectRoot ".external"
$sourceRoot = Join-Path $externalRoot "src"
$venvRoot = Join-Path $externalRoot "venvs"
$reportRoot = Join-Path $projectRoot "bot\reports\research"

New-Item -ItemType Directory -Force -Path $externalRoot, $sourceRoot, $venvRoot, $reportRoot | Out-Null

$repositories = @(
    @{ name = "OpenAlice"; url = "https://github.com/TraderAlice/OpenAlice.git"; path = "OpenAlice"; role = "read-only control-plane reference"; license = "AGPL-3.0" },
    @{ name = "awesome-systematic-trading"; url = "https://github.com/paperswithbacktest/awesome-systematic-trading.git"; path = "awesome-systematic-trading"; role = "source catalog"; license = "inspect repository" },
    @{ name = "qlib"; url = "https://github.com/microsoft/qlib.git"; path = "qlib"; role = "isolated offline research"; license = "MIT" },
    @{ name = "ordersim"; url = "https://github.com/tradingexpert/ordersim.git"; path = "ordersim"; role = "isolated execution replay"; license = "MIT" },
    @{ name = "hftbacktest"; url = "https://github.com/nkaz001/hftbacktest.git"; path = "hftbacktest"; role = "isolated tick and latency replay"; license = "MIT" },
    @{ name = "oos-lab"; url = "https://github.com/OutOfSampleLab/oos-lab.git"; path = "oos-lab"; role = "isolated validation"; license = "MIT" },
    @{ name = "Keystone"; url = "https://github.com/pancakes9798/Keystone.git"; path = "Keystone"; role = "methodology reference"; license = "proprietary; do not redistribute" },
    @{ name = "algorithmic-trading-research-framework"; url = "https://github.com/WenhuangL/algorithmic-trading-research-framework.git"; path = "algorithmic-trading-research-framework"; role = "research integrity reference"; license = "MIT" },
    @{ name = "samvid-trading-core"; url = "https://github.com/AshishTalpada/samvid-trading-core.git"; path = "samvid-trading-core"; role = "event and reconciliation reference"; license = "MIT" },
    @{ name = "Vibe-Trading"; url = "https://github.com/HKUDS/Vibe-Trading.git"; path = "Vibe-Trading"; role = "MT5 preflight reference; PR 481"; license = "inspect repository" },
    @{ name = "metatrader5-mcp-server"; url = "https://github.com/wwplay1978/metatrader5-mcp-server.git"; path = "metatrader5-mcp-server"; role = "read-only MT5 diagnostics reference"; license = "inspect repository" },
    @{ name = "nautilus_trader"; url = "https://github.com/nautechsystems/nautilus_trader.git"; path = "nautilus_trader"; role = "isolated event-engine parity reference"; license = "inspect repository" },
    @{ name = "Lean"; url = "https://github.com/QuantConnect/Lean.git"; path = "Lean"; role = "isolated replay reference"; license = "inspect repository" },
    @{ name = "abides"; url = "https://github.com/abides-sim/abides.git"; path = "abides"; role = "synthetic stress reference"; license = "inspect repository" }
)

$toolResults = [ordered]@{}
$repositoryResults = [System.Collections.Generic.List[object]]::new()
$environmentResults = [System.Collections.Generic.List[object]]::new()

function Add-Result {
    param([hashtable]$Target, [string]$Name, [object]$Value)
    $Target[$Name] = $Value
}

function Get-CommandVersion {
    param([string]$Name, [string[]]$Arguments = @("--version"))
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        return [ordered]@{ status = "MISSING"; version = $null }
    }
    try {
        $raw = (& $command.Source @Arguments 2>&1 | Out-String).Trim()
        return [ordered]@{ status = "AVAILABLE"; version = $raw }
    } catch {
        return [ordered]@{ status = "ERROR"; version = $null; error = $_.Exception.Message }
    }
}

function Invoke-BestEffort {
    param(
        [string]$Name,
        [scriptblock]$Action,
        [string]$WorkingDirectory = $projectRoot
    )
    $oldLocation = Get-Location
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Native tools such as uv and pnpm legitimately write progress to
        # stderr on success.  Classify their explicit process exit code,
        # while scriptblock ``throw`` statements remain terminating errors.
        $ErrorActionPreference = "Continue"
        Set-Location -LiteralPath $WorkingDirectory
        $output = & $Action 2>&1 | Out-String
        $code = $LASTEXITCODE
        return [ordered]@{
            name = $Name
            status = if ($code -eq 0) { "COMPLETED" } else { "BLOCKED" }
            exit_code = $code
            output_tail = (($output -split "`r?`n") | Where-Object { $_ -ne "" } | Select-Object -Last 20)
        }
    } catch {
        return [ordered]@{
            name = $Name
            status = "BLOCKED"
            exit_code = $null
            output_tail = @($_.Exception.Message)
        }
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
        Set-Location $oldLocation
    }
}

function Ensure-Prerequisite {
    param(
        [string]$Name,
        [string]$CommandName,
        [string]$WingetId,
        [string[]]$VersionArguments = @("--version")
    )
    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return [ordered]@{
            name = $Name
            command = $CommandName
            status = "AVAILABLE"
            version = (Get-CommandVersion -Name $CommandName -Arguments $VersionArguments).version
        }
    }
    if ($SkipPrerequisites) {
        return [ordered]@{ name = $Name; command = $CommandName; status = "SKIPPED"; reason = "SkipPrerequisites was requested" }
    }
    if ([string]::IsNullOrWhiteSpace($WingetId)) {
        return [ordered]@{ name = $Name; command = $CommandName; status = "BLOCKED_MISSING_PROVIDER"; reason = "no safe provider configured" }
    }
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($null -eq $winget) {
        return [ordered]@{ name = $Name; command = $CommandName; status = "BLOCKED_WINGET_MISSING"; winget_id = $WingetId }
    }
    try {
        # User-scoped, non-interactive installation avoids changing credentials
        # and makes an administrator/reboot requirement an explicit result.
        $output = (& $winget.Source install --id $WingetId --exact --scope user --accept-package-agreements --accept-source-agreements --silent 2>&1 | Out-String).Trim()
        $code = $LASTEXITCODE
        $after = Get-Command $CommandName -ErrorAction SilentlyContinue
        return [ordered]@{
            name = $Name
            command = $CommandName
            winget_id = $WingetId
            status = if ($null -ne $after -and $code -eq 0) { "INSTALLED" } elseif ($code -eq 0) { "INSTALLED_RESTART_REQUIRED" } else { "BLOCKED_INSTALL" }
            exit_code = $code
            version = if ($null -ne $after) { (Get-CommandVersion -Name $CommandName -Arguments $VersionArguments).version } else { $null }
            output_tail = (($output -split "`r?`n") | Where-Object { $_ -ne "" } | Select-Object -Last 10)
        }
    } catch {
        return [ordered]@{ name = $Name; command = $CommandName; winget_id = $WingetId; status = "BLOCKED_INSTALL"; error = $_.Exception.Message }
    }
}

function Ensure-WingetPackage {
    param(
        [string]$Name,
        [string]$WingetId,
        [string]$Override = ""
    )
    if ($SkipPrerequisites) {
        return [ordered]@{ name = $Name; winget_id = $WingetId; status = "SKIPPED" }
    }
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($null -eq $winget) {
        return [ordered]@{ name = $Name; winget_id = $WingetId; status = "BLOCKED_WINGET_MISSING" }
    }
    $listed = (& $winget.Source list --id $WingetId --exact --accept-source-agreements 2>&1 | Out-String)
    if ($LASTEXITCODE -eq 0 -and $listed -match [regex]::Escape($WingetId)) {
        return [ordered]@{ name = $Name; winget_id = $WingetId; status = "AVAILABLE" }
    }
    $arguments = @(
        "install", "--id", $WingetId, "--exact", "--silent",
        "--accept-package-agreements", "--accept-source-agreements",
        "--disable-interactivity"
    )
    if (-not [string]::IsNullOrWhiteSpace($Override)) {
        $arguments += @("--override", $Override)
    }
    $output = (& $winget.Source @arguments 2>&1 | Out-String)
    $code = $LASTEXITCODE
    return [ordered]@{
        name = $Name
        winget_id = $WingetId
        status = if ($code -eq 0) { "INSTALLED" } else { "BLOCKED_INSTALL" }
        exit_code = $code
        output_tail = (($output -split "`r?`n") | Where-Object { $_ -ne "" } | Select-Object -Last 10)
    }
}

function Invoke-NoSpaceJunction {
    param([string]$Source, [string]$Name)
    if ($Source -notmatch '\s') {
        return [ordered]@{ path = $Source; created = $false }
    }
    $safeRoot = Join-Path $env:SystemDrive "AEGISExternalLinks"
    New-Item -ItemType Directory -Force -Path $safeRoot | Out-Null
    $link = Join-Path $safeRoot $Name
    if (Test-Path -LiteralPath $link) {
        $item = Get-Item -LiteralPath $link -Force
        $targets = @($item.Target | ForEach-Object { [System.IO.Path]::GetFullPath([string]$_) })
        if ($item.LinkType -ne "Junction" -or [System.IO.Path]::GetFullPath($Source) -notin $targets) {
            throw "safe junction path is already occupied: $link"
        }
        return [ordered]@{ path = $link; created = $false }
    }
    New-Item -ItemType Junction -Path $link -Target $Source | Out-Null
    return [ordered]@{ path = $link; created = $true }
}

function Ensure-NoSpaceCommandShim {
    param([string]$CommandName)
    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "$CommandName is not available"
    }
    $toolRoot = Join-Path $externalRoot "tools"
    New-Item -ItemType Directory -Force -Path $toolRoot | Out-Null
    $wrapper = Join-Path $toolRoot ($CommandName + ".cmd")
    $content = "@echo off`r`ncall `"$($command.Source)`" %*`r`n"
    [System.IO.File]::WriteAllText($wrapper, $content, [System.Text.UTF8Encoding]::new($false))
    return (Invoke-NoSpaceJunction -Source $toolRoot -Name "Tools").path
}

function Invoke-GitCloneBounded {
    param(
        [string]$Url,
        [string]$Destination,
        [int]$TimeoutSeconds = 120
    )
    $git = Get-Command git -ErrorAction SilentlyContinue
    # Bounded equivalent of: git clone --depth 1 <url> <destination>.
    if ($null -eq $git) {
        return [ordered]@{
            name = "clone"
            status = "BLOCKED"
            exit_code = $null
            output_tail = @("git is not available")
        }
    }
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $git.Source
    $start.WorkingDirectory = $projectRoot
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    # All arguments are generated paths/URLs from this script.  Quote them so
    # the fixed Windows workspace path remains a single argument.
    $quoted = @("clone", "--depth", "1", $Url, $Destination) |
        ForEach-Object { '"' + ([string]$_).Replace('"', '\"') + '"' }
    $start.Arguments = $quoted -join " "
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $start
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $timeoutMs = [Math]::Max(1, $TimeoutSeconds) * 1000
        if (-not $process.WaitForExit($timeoutMs)) {
            try { $process.Kill($true) } catch { try { $process.Kill() } catch {} }
            $process.WaitForExit()
            return [ordered]@{
                name = "clone"
                status = "BLOCKED_TIMEOUT"
                exit_code = $null
                output_tail = @("clone exceeded $TimeoutSeconds seconds; checkout was preserved")
            }
        }
        $output = (($stdout.Result + "`n" + $stderr.Result) -split "`r?`n") |
            Where-Object { $_ -ne "" } | Select-Object -Last 20
        return [ordered]@{
            name = "clone"
            status = if ($process.ExitCode -eq 0) { "COMPLETED" } else { "BLOCKED" }
            exit_code = $process.ExitCode
            output_tail = @($output)
        }
    } catch {
        return [ordered]@{
            name = "clone"
            status = "BLOCKED"
            exit_code = $null
            output_tail = @($_.Exception.Message)
        }
    } finally {
        $process.Dispose()
    }
}

function Invoke-BoundedSmoke {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory = $projectRoot,
        [int]$TimeoutSeconds = 15,
        [switch]$SuccessOnTimeout
    )
    $command = Get-Command $FilePath -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        return [ordered]@{
            name = $Name
            status = "BLOCKED_MISSING_COMMAND"
            exit_code = $null
            output_tail = @("$FilePath is not available")
        }
    }
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $command.Source
    $start.WorkingDirectory = $WorkingDirectory
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.Arguments = ($Arguments | ForEach-Object {
        '"' + ([string]$_).Replace('"', '\"') + '"'
    }) -join " "
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $start
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $timeoutMs = [Math]::Max(1, $TimeoutSeconds) * 1000
        if (-not $process.WaitForExit($timeoutMs)) {
            $taskkill = Get-Command taskkill.exe -ErrorAction SilentlyContinue
            if ($taskkill) {
                & $taskkill.Source /PID $process.Id /T /F 2>$null | Out-Null
            } else {
                try { $process.Kill() } catch {}
            }
            try { $process.WaitForExit() } catch {}
            $output = (($stdout.Result + "`n" + $stderr.Result) -split "`r?`n") |
                Where-Object { $_ -ne "" } | Select-Object -Last 20
            return [ordered]@{
                name = $Name
                status = if ($SuccessOnTimeout) { "COMPLETED_BOUNDED_SMOKE" } else { "BLOCKED_TIMEOUT" }
                exit_code = $null
                ran_for_seconds = $TimeoutSeconds
                process_tree_stopped = $true
                output_tail = @($output)
            }
        }
        $output = (($stdout.Result + "`n" + $stderr.Result) -split "`r?`n") |
            Where-Object { $_ -ne "" } | Select-Object -Last 20
        return [ordered]@{
            name = $Name
            status = if ($process.ExitCode -eq 0) { "COMPLETED" } else { "BLOCKED" }
            exit_code = $process.ExitCode
            output_tail = @($output)
        }
    } catch {
        return [ordered]@{
            name = $Name
            status = "BLOCKED"
            exit_code = $null
            output_tail = @($_.Exception.Message)
        }
    } finally {
        $process.Dispose()
    }
}

function Ensure-Repository {
    param([hashtable]$Repository)
    $destination = Join-Path $sourceRoot $Repository.path
    $result = [ordered]@{
        name = $Repository.name
        url = $Repository.url
        path = $destination
        role = $Repository.role
        declared_license = $Repository.license
        status = $null
        commit = $null
        branch = $null
        dirty = $null
        license_file = $null
        package_version = $null
        upstream_test_paths = @()
    }
    try {
        $gitRoot = Join-Path $destination ".git"
        $indexLock = Join-Path $gitRoot "index.lock"
        if (Test-Path $indexLock) {
            # A terminated/partial clone is evidence, not a healthy checkout.
            # Preserve it for operator inspection and never try to repair it
            # by deleting files or stealing the lock.
            $result.status = "BLOCKED_PARTIAL_CHECKOUT"
            $result.reason = "git index.lock is present; checkout preserved"
            return $result
        }
        if (Test-Path $gitRoot) {
            $result.status = "EXISTING_PRESERVED"
        } elseif ($SkipRepositoryClone) {
            $result.status = "SKIPPED_NOT_PRESENT"
            $result.reason = "SkipRepositoryClone was requested"
            return $result
        } else {
            $clone = Invoke-GitCloneBounded -Url $Repository.url -Destination $destination -TimeoutSeconds $CloneTimeoutSeconds
            if ($clone.status -ne "COMPLETED") {
                $result.status = if ($clone.status -eq "BLOCKED_TIMEOUT") {
                    "BLOCKED_CLONE_TIMEOUT"
                } else { "BLOCKED_CLONE" }
                $result.clone = $clone
                return $result
            }
            $result.status = "CLONED"
        }
        # Commit verification is intentionally based on the repository's
        # ``git rev-parse HEAD`` result; existing clones are never rewritten.
        $result.commit = (& git -C $destination rev-parse HEAD 2>$null).Trim()
        $result.branch = (& git -C $destination branch --show-current 2>$null).Trim()
        if (-not $result.commit) {
            $result.status = "BLOCKED_INCOMPLETE_CHECKOUT"
            $result.reason = "repository has no readable HEAD"
            return $result
        }
        $result.dirty = [bool]((& git -C $destination status --porcelain 2>$null | Out-String).Trim())
        $license = Get-ChildItem -LiteralPath $destination -File -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match "^(LICENSE|LICENCE)(\..*)?$" } |
            Select-Object -First 1
        if ($license) { $result.license_file = $license.Name }
        $packageJson = Join-Path $destination "package.json"
        if (Test-Path $packageJson) {
            try { $result.package_version = (Get-Content $packageJson -Raw | ConvertFrom-Json).version } catch {}
        }
        $pyproject = Join-Path $destination "pyproject.toml"
        if (-not $result.package_version -and (Test-Path $pyproject)) {
            $versionPattern = '^\s*version\s*=\s*"([^"]+)"'
            $versionLine = Get-Content $pyproject -ErrorAction SilentlyContinue |
                Where-Object { $_ -match $versionPattern } |
                Select-Object -First 1
            if ($versionLine -match $versionPattern) {
                $result.package_version = $Matches[1]
            }
        }
        $testPaths = @("tests", "test", "pytest.ini", "tox.ini", ".github\workflows") |
            Where-Object { Test-Path (Join-Path $destination $_) }
        $result.upstream_test_paths = @($testPaths)
    } catch {
        $result.status = "BLOCKED_INSPECTION"
        $result.error = $_.Exception.Message
    }
    return $result
}

function Ensure-IsolatedEnvironment {
    param(
        [string]$Name,
        [string]$PythonVersion = "3.12",
        [string]$PathName = $Name
    )
    $destination = Join-Path $venvRoot $PathName
    $python = Join-Path $destination "Scripts\python.exe"
    if (Test-Path $python) {
        $pipAvailable = $false
        try {
            & $python -m pip --version 2>$null | Out-Null
            $pipAvailable = ($LASTEXITCODE -eq 0)
        } catch {
            $pipAvailable = $false
        }
        if (-not $pipAvailable -and -not $SkipInstalls) {
            $uv = Get-Command uv -ErrorAction SilentlyContinue
            if ($null -eq $uv) {
                return [ordered]@{
                    name = $Name; path = $destination
                    status = "BLOCKED_PYTHON_RUNTIME"; python = $python
                }
            }
            # equivalent to: uv pip install --python <env-python> pip
            & $uv.Source pip install --python $python pip
            if ($LASTEXITCODE -ne 0) {
                return [ordered]@{
                    name = $Name; path = $destination
                    status = "BLOCKED_PYTHON_RUNTIME"; python = $python
                }
            }
            return [ordered]@{
                name = $Name; path = $destination
                status = "EXISTING_REPAIRED"; python = $python
            }
        }
        return [ordered]@{ name = $Name; path = $destination; status = "EXISTING_PRESERVED"; python = $python }
    }
    if ($SkipInstalls) {
        return [ordered]@{ name = $Name; path = $destination; status = "SKIPPED_INSTALL"; python = $python }
    }
    $result = Invoke-BestEffort -Name ("venv:" + $Name) -Action {
        $created = $false
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if ($null -ne $launcher) {
            & $launcher.Source ("-" + $PythonVersion) -m venv $destination
            $created = $LASTEXITCODE -eq 0 -and (Test-Path $python)
        }
        if (-not $created) {
            $uv = Get-Command uv -ErrorAction SilentlyContinue
            if ($null -eq $uv) {
                throw "BLOCKED_PYTHON_RUNTIME: Python $PythonVersion is unavailable and uv cannot provide an isolated runtime"
            }
            # uv venv --python may download a managed interpreter without
            # changing the machine-wide Python installation.
            & $uv.Source venv --seed --python $PythonVersion $destination
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path $python)) {
                throw "BLOCKED_PYTHON_RUNTIME: uv could not create Python $PythonVersion environment"
            }
        }
    }
    return [ordered]@{
        name = $Name
        path = $destination
        status = $result.status
        python = $python
        result = $result
    }
}

if (-not $SkipPrerequisites) {
    $toolResults["git"] = Ensure-Prerequisite -Name "Git" -CommandName "git" -WingetId "Git.Git"
    $toolResults["gh"] = Ensure-Prerequisite -Name "GitHub CLI" -CommandName "gh" -WingetId "GitHub.cli"
    $toolResults["python"] = Ensure-Prerequisite -Name "Python 3.12" -CommandName "python" -WingetId "Python.Python.3.12"
    $toolResults["uv"] = Ensure-Prerequisite -Name "uv" -CommandName "uv" -WingetId "astral-sh.uv"
    $toolResults["node"] = Ensure-Prerequisite -Name "Node.js LTS" -CommandName "node" -WingetId "OpenJS.NodeJS.LTS"
    $toolResults["ffmpeg"] = Ensure-Prerequisite -Name "FFmpeg" -CommandName "ffmpeg" -WingetId "Gyan.FFmpeg"
    $toolResults["vcredist_x64"] = Ensure-WingetPackage -Name "Microsoft VC++ runtime" -WingetId "Microsoft.VCRedist.2015+.x64"
    $toolResults["vc_build_tools"] = Ensure-WingetPackage -Name "Visual Studio C++ Build Tools" -WingetId "Microsoft.VisualStudio.2022.BuildTools" -Override "--wait --passive --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
    foreach ($tool in @("pip", "npm", "pnpm")) {
        $toolResults[$tool] = Get-CommandVersion -Name $tool
    }
    if ($InstallDocker) {
        $toolResults["docker"] = Ensure-Prerequisite -Name "Docker Desktop" -CommandName "docker" -WingetId "Docker.DockerDesktop"
    } else {
        $toolResults["docker"] = [ordered]@{ status = "NOT_REQUIRED"; reason = "no isolated Docker workflow selected" }
    }
} else {
    $toolResults["prerequisites"] = [ordered]@{ status = "SKIPPED" }
}

foreach ($repository in $repositories) {
    $repositoryResults.Add((Ensure-Repository -Repository $repository))
}

foreach ($environment in @(
    @{ name = "qlib" },
    @{ name = "ordersim" },
    @{ name = "hftbacktest" },
    @{ name = "oos-lab" },
    @{ name = "keystone" },
    @{ name = "research-framework" },
    @{ name = "samvid" },
    @{ name = "mt5-mcp" },
    @{ name = "nautilus" },
    @{ name = "lean" },
    @{ name = "abides"; python = "3.11"; path = "abides-py311" }
)) {
    $pythonVersion = if ($environment.python) { $environment.python } else { "3.12" }
    $pathName = if ($environment.path) { $environment.path } else { $environment.name }
    $environmentResults.Add((Ensure-IsolatedEnvironment -Name $environment.name -PythonVersion $pythonVersion -PathName $pathName))
}

$installChecks = [System.Collections.Generic.List[object]]::new()
$requiredInstallCheckNames = @(
    "OpenAlice pnpm install",
    "OpenAlice tests",
    "OpenAlice dev smoke",
    "awesome-systematic-trading catalog inspection",
    "Qlib install",
    "Qlib import",
    "Qlib pip check",
    "ordersim install",
    "ordersim tests",
    "hftbacktest install",
    "hftbacktest import",
    "hftbacktest synthetic example",
    "oos-lab install",
    "oos-lab tests",
    "oos-lab pip check",
    "Keystone sync",
    "Keystone tests",
    "research-framework install",
    "research-framework tests",
    "research-framework public release check",
    "samvid sync",
    "samvid tests",
    "samvid ruff",
    "samvid compile",
    "Vibe-Trading PR 481 inspection",
    "mt5-mcp install",
    "mt5-mcp tests",
    "NautilusTrader install",
    "NautilusTrader import",
    "NautilusTrader pip check",
    "LEAN install",
    "LEAN help",
    "ABIDES install",
    "ABIDES synthetic simulation"
)
if ($SkipInstalls) {
    foreach ($checkName in $requiredInstallCheckNames) {
        $installChecks.Add([ordered]@{
            name = $checkName
            status = "SKIPPED_INSTALL"
            exit_code = $null
            output_tail = @("SkipInstalls was requested")
        })
    }
}
if (-not $SkipInstalls) {
    $openAlice = Join-Path $sourceRoot "OpenAlice"
    if (Test-Path (Join-Path $openAlice "package.json")) {
        $openAliceRun = (Invoke-NoSpaceJunction -Source $openAlice -Name "OpenAlice").path
        $openAliceToolPath = Ensure-NoSpaceCommandShim -CommandName "pnpm"
        $previousPath = $env:PATH
        try {
            $env:PATH = $openAliceToolPath + ";" + $previousPath
            $installChecks.Add((Invoke-BestEffort -Name "OpenAlice pnpm install" -WorkingDirectory $openAliceRun -Action {
                pnpm install --frozen-lockfile
            }))
            if ($SkipUpstreamTests) {
                $installChecks.Add([ordered]@{ name = "OpenAlice tests"; status = "SKIPPED_UPSTREAM_TESTS" })
                $installChecks.Add([ordered]@{ name = "OpenAlice dev smoke"; status = "SKIPPED_UPSTREAM_TESTS" })
            } else {
                $installChecks.Add((Invoke-BestEffort -Name "OpenAlice tests" -WorkingDirectory $openAliceRun -Action {
                    pnpm run test:smoke
                }))
                $installChecks.Add((Invoke-BoundedSmoke -Name "OpenAlice dev smoke" -FilePath "pnpm" -Arguments @("dev") -WorkingDirectory $openAliceRun -TimeoutSeconds 15 -SuccessOnTimeout))
            }
        } finally {
            $env:PATH = $previousPath
        }
    }

    $catalogPath = Join-Path $sourceRoot "awesome-systematic-trading"
    if (Test-Path (Join-Path $catalogPath "README.md")) {
        $installChecks.Add((Invoke-BestEffort -Name "awesome-systematic-trading catalog inspection" -WorkingDirectory $catalogPath -Action {
            $linkCount = (Select-String -Path "README.md" -Pattern 'https?://' -AllMatches).Matches.Count
            if ($linkCount -le 0) { throw "catalog contains no source links" }
            Write-Output "SOURCE_LINKS=$linkCount"
            & git -C $catalogPath rev-parse HEAD
        }))
    }

    $qlibPython = Join-Path $venvRoot "qlib\Scripts\python.exe"
    if (Test-Path $qlibPython) {
        $installChecks.Add((Invoke-BestEffort -Name "Qlib install" -Action {
            & $qlibPython -m pip install --upgrade pip
            if ($LASTEXITCODE -ne 0) { throw "Qlib pip upgrade failed" }
            & $qlibPython -m pip install pyqlib setuptools-scm
        }))
        $installChecks.Add((Invoke-BestEffort -Name "Qlib import" -Action {
            & $qlibPython -c "import qlib; print(getattr(qlib, '__version__', 'imported'))"
        }))
        $installChecks.Add((Invoke-BestEffort -Name "Qlib pip check" -Action {
            & $qlibPython -m pip check
        }))
    }

    $ordersimPython = Join-Path $venvRoot "ordersim\Scripts\python.exe"
    if (Test-Path $ordersimPython) {
        $ordersimPath = Join-Path $sourceRoot "ordersim"
        $installChecks.Add((Invoke-BestEffort -Name "ordersim install" -WorkingDirectory $ordersimPath -Action {
            & $ordersimPython -m pip install --upgrade pip
            if ($LASTEXITCODE -ne 0) { throw "ordersim pip upgrade failed" }
            & $ordersimPython -m pip install -e ".[dev]"
        }))
        if (-not $SkipUpstreamTests) {
            $installChecks.Add((Invoke-BestEffort -Name "ordersim tests" -WorkingDirectory $ordersimPath -Action {
                & $ordersimPython -m pytest -q
            }))
        } else {
            $installChecks.Add([ordered]@{ name = "ordersim tests"; status = "SKIPPED_UPSTREAM_TESTS" })
        }
    }

    $hftPython = Join-Path $venvRoot "hftbacktest\Scripts\python.exe"
    if (Test-Path $hftPython) {
        $installChecks.Add((Invoke-BestEffort -Name "hftbacktest install" -Action {
            & $hftPython -m pip install --upgrade pip
            if ($LASTEXITCODE -ne 0) { throw "hftbacktest pip upgrade failed" }
            & $hftPython -m pip install hftbacktest
        }))
        $installChecks.Add((Invoke-BestEffort -Name "hftbacktest import" -Action {
            & $hftPython -c "import hftbacktest; print('imported')"
        }))
        $installChecks.Add((Invoke-BestEffort -Name "hftbacktest synthetic example" -Action {
            & $hftPython -c "from hftbacktest import BacktestAsset; a=BacktestAsset(); print(type(a).__name__)"
        }))
    }

    $frameworkPython = Join-Path $venvRoot "research-framework\Scripts\python.exe"
    $frameworkPath = Join-Path $sourceRoot "algorithmic-trading-research-framework"
    if ((Test-Path $frameworkPython) -and (Test-Path $frameworkPath)) {
        $lock = Join-Path $frameworkPath "requirements-lock.txt"
        $dev = Join-Path $frameworkPath "requirements-dev.txt"
        if ((Test-Path $lock) -and (Test-Path $dev)) {
            $installChecks.Add((Invoke-BestEffort -Name "research-framework install" -WorkingDirectory $frameworkPath -Action {
                & $frameworkPython -m pip install -r $lock -r $dev
            }))
        } else {
            $installChecks.Add([ordered]@{ name = "research-framework install"; status = "BLOCKED_MISSING_MANIFEST" })
        }
        if (-not $SkipUpstreamTests) {
            $installChecks.Add((Invoke-BestEffort -Name "research-framework tests" -WorkingDirectory $frameworkPath -Action {
                & $frameworkPython -m pytest -q
            }))
            $releaseCheck = Join-Path $frameworkPath "tools\check_public_release.py"
            if (Test-Path $releaseCheck) {
                $installChecks.Add((Invoke-BestEffort -Name "research-framework public release check" -WorkingDirectory $frameworkPath -Action {
                    & $frameworkPython $releaseCheck
                }))
            }
        } else {
            $installChecks.Add([ordered]@{ name = "research-framework tests"; status = "SKIPPED_UPSTREAM_TESTS" })
            $installChecks.Add([ordered]@{ name = "research-framework public release check"; status = "SKIPPED_UPSTREAM_TESTS" })
        }
    }

    $oosPython = Join-Path $venvRoot "oos-lab\Scripts\python.exe"
    $oosPath = Join-Path $sourceRoot "oos-lab"
    if ((Test-Path $oosPython) -and (Test-Path $oosPath)) {
        $installChecks.Add((Invoke-BestEffort -Name "oos-lab install" -WorkingDirectory $oosPath -Action {
            & $oosPython -m pip install --upgrade pip
            if ($LASTEXITCODE -ne 0) { throw "oos-lab pip upgrade failed" }
            & $oosPython -m pip install oos-lab
        }))
        if ($SkipUpstreamTests) {
            $installChecks.Add([ordered]@{ name = "oos-lab tests"; status = "SKIPPED_UPSTREAM_TESTS" })
        } else {
            $installChecks.Add((Invoke-BestEffort -Name "oos-lab tests" -WorkingDirectory $oosPath -Action {
                & $oosPython -m pip install pytest
                if ($LASTEXITCODE -ne 0) { throw "oos-lab pytest install failed" }
                & $oosPython -m pytest -q
            }))
        }
        $installChecks.Add((Invoke-BestEffort -Name "oos-lab pip check" -Action {
            & $oosPython -m pip check
        }))
    }

    $keystonePath = Join-Path $sourceRoot "Keystone"
    $keystoneEnvironment = Join-Path $venvRoot "keystone"
    if (Test-Path (Join-Path $keystonePath "pyproject.toml")) {
        $installChecks.Add((Invoke-BestEffort -Name "Keystone sync" -WorkingDirectory $keystonePath -Action {
            $prior = $env:UV_PROJECT_ENVIRONMENT
            try {
                $env:UV_PROJECT_ENVIRONMENT = $keystoneEnvironment
                uv sync --locked
            } finally {
                if ($null -eq $prior) { Remove-Item Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue }
                else { $env:UV_PROJECT_ENVIRONMENT = $prior }
            }
        }))
        if ($SkipUpstreamTests) {
            $installChecks.Add([ordered]@{ name = "Keystone tests"; status = "SKIPPED_UPSTREAM_TESTS" })
        } else {
            $installChecks.Add((Invoke-BestEffort -Name "Keystone tests" -WorkingDirectory $keystonePath -Action {
                $keystonePython = Join-Path $keystoneEnvironment "Scripts\python.exe"
                # On Windows, preload Torch before NumPy/OpenMP-linked modules.
                & $keystonePython -c "import torch,pytest,sys; print('TORCH_PRELOAD', torch.__version__); sys.exit(pytest.main(['-q']))"
            }))
        }
    }

    $samvidPath = Join-Path $sourceRoot "samvid-trading-core"
    $samvidEnvironment = Join-Path $venvRoot "samvid"
    if (Test-Path (Join-Path $samvidPath "pyproject.toml")) {
        $installChecks.Add((Invoke-BestEffort -Name "samvid sync" -WorkingDirectory $samvidPath -Action {
            $prior = $env:UV_PROJECT_ENVIRONMENT
            try {
                $env:UV_PROJECT_ENVIRONMENT = $samvidEnvironment
                uv sync --locked
            } finally {
                if ($null -eq $prior) { Remove-Item Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue }
                else { $env:UV_PROJECT_ENVIRONMENT = $prior }
            }
        }))
        foreach ($samvidCheck in @(
            @{ name = "samvid tests"; args = @("run", "python", "-m", "pytest", "tests", "-q", "--tb=short") },
            @{ name = "samvid ruff"; args = @("run", "ruff", "check", "src", "tests", "scripts") },
            @{ name = "samvid compile"; args = @("run", "python", "-m", "compileall", "-q", "src", "tests", "scripts") }
        )) {
            if ($SkipUpstreamTests) {
                $installChecks.Add([ordered]@{ name = $samvidCheck.name; status = "SKIPPED_UPSTREAM_TESTS" })
            } else {
                $installChecks.Add((Invoke-BestEffort -Name $samvidCheck.name -WorkingDirectory $samvidPath -Action {
                    $prior = $env:UV_PROJECT_ENVIRONMENT
                    try {
                        $env:UV_PROJECT_ENVIRONMENT = $samvidEnvironment
                        & uv @($samvidCheck.args)
                    } finally {
                        if ($null -eq $prior) { Remove-Item Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue }
                        else { $env:UV_PROJECT_ENVIRONMENT = $prior }
                    }
                }))
            }
        }
    }

    $vibePath = Join-Path $sourceRoot "Vibe-Trading"
    if (Test-Path (Join-Path $vibePath ".git")) {
        $installChecks.Add((Invoke-BestEffort -Name "Vibe-Trading PR 481 inspection" -WorkingDirectory $vibePath -Action {
            $branch = (& git -C $vibePath branch --show-current 2>$null).Trim()
            if ($branch -ne "pr-481") { throw "expected pr-481, found $branch" }
            & git -C $vibePath rev-parse HEAD
        }))
    }

    $mt5McpPython = Join-Path $venvRoot "mt5-mcp\Scripts\python.exe"
    $mt5McpPath = Join-Path $sourceRoot "metatrader5-mcp-server"
    if ((Test-Path $mt5McpPython) -and (Test-Path $mt5McpPath)) {
        $installChecks.Add((Invoke-BestEffort -Name "mt5-mcp install" -WorkingDirectory $mt5McpPath -Action {
            & $mt5McpPython -m pip install --upgrade pip
            if ($LASTEXITCODE -ne 0) { throw "mt5-mcp pip upgrade failed" }
            & $mt5McpPython -m pip install -e .
        }))
        if ($SkipUpstreamTests) {
            $installChecks.Add([ordered]@{ name = "mt5-mcp tests"; status = "SKIPPED_UPSTREAM_TESTS" })
        } else {
            $installChecks.Add((Invoke-BestEffort -Name "mt5-mcp tests" -WorkingDirectory $mt5McpPath -Action {
                & $mt5McpPython -m pip install pytest
                if ($LASTEXITCODE -ne 0) { throw "mt5-mcp pytest install failed" }
                & $mt5McpPython -m pytest -q
            }))
        }
    }

    $nautilusPython = Join-Path $venvRoot "nautilus\Scripts\python.exe"
    if (Test-Path $nautilusPython) {
        $installChecks.Add((Invoke-BestEffort -Name "NautilusTrader install" -Action {
            & $nautilusPython -m pip install --upgrade pip
            if ($LASTEXITCODE -ne 0) { throw "NautilusTrader pip upgrade failed" }
            & $nautilusPython -m pip install --upgrade nautilus_trader
        }))
        $installChecks.Add((Invoke-BestEffort -Name "NautilusTrader import" -Action {
            & $nautilusPython -c "import nautilus_trader; print(getattr(nautilus_trader, '__version__', 'imported'))"
        }))
        $installChecks.Add((Invoke-BestEffort -Name "NautilusTrader pip check" -Action {
            & $nautilusPython -m pip check
        }))
    }

    $leanPython = Join-Path $venvRoot "lean\Scripts\python.exe"
    $leanExe = Join-Path $venvRoot "lean\Scripts\lean.exe"
    if (Test-Path $leanPython) {
        $installChecks.Add((Invoke-BestEffort -Name "LEAN install" -Action {
            & $leanPython -m pip install --upgrade pip
            if ($LASTEXITCODE -ne 0) { throw "LEAN pip upgrade failed" }
            & $leanPython -m pip install lean
        }))
        $installChecks.Add((Invoke-BestEffort -Name "LEAN help" -Action {
            if (-not (Test-Path $leanExe)) { throw "lean.exe was not installed" }
            & $leanExe --help
        }))
    }

    $abidesPython = Join-Path $venvRoot "abides-py311\Scripts\python.exe"
    $abidesPath = Join-Path $sourceRoot "abides"
    if ((Test-Path $abidesPython) -and (Test-Path $abidesPath)) {
        $abidesRequirements = Join-Path $abidesPath "requirements.txt"
        $installChecks.Add((Invoke-BestEffort -Name "ABIDES install" -WorkingDirectory $abidesPath -Action {
            & $abidesPython -m pip install --upgrade pip
            if ($LASTEXITCODE -ne 0) { throw "ABIDES pip upgrade failed" }
            Write-Output "ABIDES legacy requirements are incompatible with supported Python; installing the closest wheel-backed compatibility set"
            & $abidesPython -m pip install "numpy==1.23.5" "pandas==1.5.3" "scipy==1.10.1" "matplotlib==3.7.5"
            if ($LASTEXITCODE -ne 0) { throw "ABIDES compatibility dependencies failed" }
            & $abidesPython -m pip install -e .
        }))
        if ($SkipUpstreamTests) {
            $installChecks.Add([ordered]@{ name = "ABIDES synthetic simulation"; status = "SKIPPED_UPSTREAM_TESTS" })
        } else {
            $abidesLatencyStress = "import numpy as np; from model.LatencyModel import LatencyModel; base=np.array([[0,1000],[2000,0]]); model=LatencyModel('cubic',random_state=np.random.RandomState(7),min_latency=base,jitter=0.5,jitter_clip=0.25,jitter_unit=10.0); samples=[model.get_latency(0,1) for _ in range(1000)]; assert min(samples)>=1000 and len(set(samples))>1; disconnected=LatencyModel('cubic',random_state=np.random.RandomState(7),min_latency=base,connected=np.array([[True,False],[True,True]])); assert disconnected.get_latency(0,1)==-1; print('ABIDES_LATENCY_STRESS_OK samples=1000 min_ns=%d max_ns=%d disconnect=-1' % (min(samples),max(samples)))"
            $installChecks.Add((Invoke-BoundedSmoke -Name "ABIDES synthetic simulation" -FilePath $abidesPython -Arguments @("-c", $abidesLatencyStress) -WorkingDirectory $abidesPath -TimeoutSeconds 30))
        }
    }

    $existingCheckNames = @($installChecks | ForEach-Object { [string]$_.name })
    foreach ($requiredCheckName in $requiredInstallCheckNames) {
        if ($requiredCheckName -notin $existingCheckNames) {
            $installChecks.Add([ordered]@{
                name = $requiredCheckName
                status = "BLOCKED_INSTALLER_GAP"
                exit_code = $null
                output_tail = @("required source, command, or environment was unavailable")
            })
        }
    }
}

$report = [ordered]@{
    report = "external_dependency_manifest"
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    status = "COMPLETED_WITH_EXPLICIT_RESULTS"
    root = ".external"
    source_root = ".external/src"
    venv_root = ".external/venvs"
    execution_policy = "External repositories are read-only research/reference inputs and cannot mutate broker state."
    tools = $toolResults
    repositories = @($repositoryResults)
    environments = @($environmentResults)
    install_checks = @($installChecks)
    test_results = @($installChecks | Where-Object { $_.name -match "test|import|check" })
    install_policy = [ordered]@{
        rerunnable = $true
        existing_directories_preserved = $true
        credentials_modified = $false
        external_trading_runtimes_started = $false
        skipped_installs = [bool]$SkipInstalls
        skipped_upstream_tests = [bool]$SkipUpstreamTests
        skipped_repository_clone = [bool]$SkipRepositoryClone
        install_docker_requested = [bool]$InstallDocker
    }
}

$jsonPath = Join-Path $reportRoot "external_dependency_manifest.json"
$mdPath = Join-Path $reportRoot "external_dependency_manifest.md"
$report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add("# External Research Stack Manifest")
$lines.Add("")
$lines.Add("Generated: ``$($report.generated_at_utc)``")
$lines.Add("")
$lines.Add("External repositories are read-only research/reference inputs. No external trading runtime was started.")
$lines.Add("")
$lines.Add("## Repositories")
$lines.Add("")
$lines.Add("| Name | Status | Commit | Role | License |")
$lines.Add("|---|---|---|---|---|")
foreach ($item in $repositoryResults) {
    $lines.Add("| $($item.name) | $($item.status) | $($item.commit) | $($item.role) | $($item.declared_license) |")
}
$lines.Add("")
$lines.Add("## Install and test results")
$lines.Add("")
foreach ($item in $installChecks) {
    $lines.Add("- $($item.name): **$($item.status)**")
}
$lines.Add("")
$lines.Add("Blocked or skipped items are recorded above and are not represented as successful installations.")
$lines -join "`r`n" | Set-Content -LiteralPath $mdPath -Encoding UTF8

Write-Output "EXTERNAL_STACK_MANIFEST_JSON=$jsonPath"
Write-Output "EXTERNAL_STACK_MANIFEST_MD=$mdPath"
Write-Output "REPOSITORIES=$($repositoryResults.Count)"
Write-Output "INSTALL_CHECKS=$($installChecks.Count)"
