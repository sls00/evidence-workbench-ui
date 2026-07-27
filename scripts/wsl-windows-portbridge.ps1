#Requires -Version 5.1
<#
.SYNOPSIS
  Bridge a Windows localhost port to a WSL2 listener (Cursor IDE browser / Edge).

.DESCRIPTION
  Cursor's IDE browser runs on Windows. WSL services are often unreachable from
  Windows even with localhostForwarding=true (NAT + Hyper-V firewall).

  This script:
    1. Resolves the current WSL eth0 IPv4 (no awk / hostname — PowerShell parses `ip`)
    2. Adds netsh portproxy: 127.0.0.1:<Port> -> <WSL_IP>:<Port>
    3. Allows inbound TCP <Port> in Windows Firewall (rule name tagged)

  Run from an elevated PowerShell (Admin), then start evidence-workbench in WSL
  with --host 0.0.0.0 (default on WSL after netutil change).

.PARAMETER Port
  TCP port (default 8765).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/wsl-windows-portbridge.ps1
#>
param(
  [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

function Test-IsAdmin {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $p = New-Object Security.Principal.WindowsPrincipal($id)
  return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-WslIpv4 {
  # Prefer absolute paths — WSL non-login shells often lack /usr/bin on PATH.
  $candidates = @(
    @("-e", "/sbin/ip", "-4", "-o", "addr", "show", "eth0"),
    @("-e", "/usr/sbin/ip", "-4", "-o", "addr", "show", "eth0"),
    @("-e", "/bin/sh", "-c", "/sbin/ip -4 -o addr show eth0 2>/dev/null || /usr/sbin/ip -4 -o addr show eth0")
  )
  foreach ($args in $candidates) {
    try {
      $raw = & wsl.exe @args 2>$null
      if (-not $raw) { continue }
      $text = if ($raw -is [array]) { $raw -join "`n" } else { [string]$raw }
      # Example: "2: eth0    inet 172.23.134.191/20 brd 172.23.143.255 scope global eth0"
      if ($text -match 'inet\s+(\d{1,3}(?:\.\d{1,3}){3})/') {
        return $Matches[1]
      }
    } catch {
      continue
    }
  }
  return $null
}

if (-not (Test-IsAdmin)) {
  Write-Error "Run this script in an elevated PowerShell (Run as Administrator)."
  exit 1
}

$wslIp = Get-WslIpv4
if (-not $wslIp) {
  Write-Error @"
Could not resolve WSL eth0 IPv4.

From WSL, run:  /sbin/ip -4 -o addr show eth0
Then re-run this script, or set networkingMode=mirrored in %UserProfile%\.wslconfig and wsl --shutdown.
"@
  exit 1
}

Write-Host "WSL IP: $wslIp"
Write-Host "Bridging Windows 127.0.0.1:$Port -> ${wslIp}:$Port"

netsh interface portproxy delete v4tov4 listenport=$Port listenaddress=127.0.0.1 2>$null | Out-Null
netsh interface portproxy add v4tov4 listenport=$Port listenaddress=127.0.0.1 connectport=$Port connectaddress=$wslIp
if ($LASTEXITCODE -ne 0) {
  Write-Error "netsh portproxy add failed (exit $LASTEXITCODE)."
  exit 1
}
netsh interface portproxy show all

$ruleName = "WSL Evidence Workbench $Port"
Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -LocalPort $Port -Protocol TCP -Action Allow | Out-Null
Write-Host "Firewall rule: $ruleName (Inbound TCP $Port Allow)"

Write-Host ""
Write-Host "Verify from this Admin PowerShell:"
Write-Host "  curl.exe http://127.0.0.1:$Port/api/health"
Write-Host ""
Write-Host "Next:"
Write-Host "  1) In WSL: uv run evidence-workbench --home generator   # binds 0.0.0.0 on WSL"
Write-Host "  2) Open in Cursor browser / Edge: http://127.0.0.1:$Port/?home=generator"
Write-Host ""
Write-Host "Re-run this script after wsl --shutdown / reboot only if you are NOT using networkingMode=mirrored."
Write-Host "Durable fix (preferred): networkingMode=mirrored + hostAddressLoopback=true in %UserProfile%\.wslconfig, then wsl --shutdown."
Write-Host "See docs/wsl-cursor-browser.md"
