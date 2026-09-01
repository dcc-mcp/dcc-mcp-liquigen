[CmdletBinding()]
param(
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$bundleRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$wheel = @(Get-ChildItem -LiteralPath (Join-Path $bundleRoot "payload") -Filter "*.whl" -File)
if ($wheel.Count -ne 1) {
    throw "Expected exactly one adapter wheel in payload/."
}

$checksumLines = @(Get-Content -LiteralPath (Join-Path $bundleRoot "SHA256SUMS"))
if ($checksumLines.Count -eq 0) {
    throw "SHA256SUMS is empty."
}
foreach ($checksumLine in $checksumLines) {
    $parts = @($checksumLine.Trim() -split "\s+", 2)
    if ($parts.Count -ne 2 -or $parts[0] -notmatch "^[0-9A-Fa-f]{64}$") {
        throw "SHA256SUMS contains an invalid entry."
    }
    $relativePath = $parts[1].Trim().Replace("/", [IO.Path]::DirectorySeparatorChar)
    if ([IO.Path]::IsPathRooted($relativePath) -or $relativePath -split "[\\/]" -contains "..") {
        throw "SHA256SUMS contains an unsafe path."
    }
    $payloadPath = Join-Path $bundleRoot $relativePath
    if (-not (Test-Path -LiteralPath $payloadPath -PathType Leaf)) {
        throw "SHA256SUMS references a missing payload: $relativePath"
    }
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $payloadPath).Hash
    if ($actualHash -ne $parts[0].ToUpperInvariant()) {
        throw "Payload SHA256 does not match SHA256SUMS: $relativePath"
    }
}

$vx = Get-Command vx -ErrorAction Stop
$arguments = @("uv", "tool", "install")
if ($Force) {
    $arguments += "--force"
}
$arguments += $wheel[0].FullName

$maxInstallAttempts = 3
$installSucceeded = $false
$lastInstallExitCode = 0
for ($installAttempt = 1; $installAttempt -le $maxInstallAttempts; $installAttempt++) {
    & $vx.Source @arguments
    $lastInstallExitCode = $LASTEXITCODE
    if ($lastInstallExitCode -eq 0) {
        $installSucceeded = $true
        break
    }
    if ($installAttempt -lt $maxInstallAttempts) {
        Write-Warning "Install attempt $installAttempt failed; retrying after a bounded delay."
        Start-Sleep -Milliseconds (250 * $installAttempt)
    }
}
if (-not $installSucceeded) {
    throw "vx uv tool install failed after $maxInstallAttempts attempts with exit code $lastInstallExitCode."
}

Write-Host "Installed dcc-mcp-liquigen from the verified local wheel."
${nativeSource} = Join-Path $bundleRoot "native"
if (Test-Path -LiteralPath ${nativeSource} -PathType Container) {
    ${nativeRoot} = Join-Path $env:LOCALAPPDATA "dcc-mcp-liquigen\native"
    ${hookSource} = Join-Path ${nativeSource} "dcc_mcp_liquigen_command_hook.dll"
    ${bridgeGeneration} = (Get-FileHash -Algorithm SHA256 -LiteralPath ${hookSource}).Hash.Substring(0, 16).ToLowerInvariant()
    ${nativeDestination} = Join-Path ${nativeRoot} ${bridgeGeneration}
    New-Item -ItemType Directory -Path ${nativeDestination} -Force | Out-Null
    foreach ($nativeName in @(
        "dcc_mcp_liquigen_command_client.exe",
        "dcc_mcp_liquigen_command_hook.dll"
    )) {
        $sourcePath = Join-Path ${nativeSource} $nativeName
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            throw "The local-native bundle is incomplete: $nativeName"
        }
        Copy-Item -LiteralPath $sourcePath -Destination (Join-Path ${nativeDestination} $nativeName) -Force
    }
    Set-Content -LiteralPath (Join-Path ${nativeRoot} "current.txt") -Value ${bridgeGeneration} -NoNewline -Encoding ascii
    Write-Host "Installed the verified local semantic command bridge in ${nativeDestination}."
}
Write-Host "LiquiGen compatibility uses executable name and interface probes, not a host EXE hash."
