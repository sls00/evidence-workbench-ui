# WSL ↔ Windows browser (Cursor IDE)

## Symptom

| Check | Result |
| --- | --- |
| `curl http://127.0.0.1:8765` **inside WSL** | OK |
| Cursor IDE browser → `http://127.0.0.1:8765` | `chrome-error://` / blank |
| Public sites in Cursor browser | OK |

## Root cause

Cursor’s IDE browser runs on **Windows**. The Evidence Workbench process runs in **WSL2**. Those are different network namespaces under default NAT networking.

Even with `localhostForwarding=true`, Windows often cannot reach a WSL listener. This is **not** an SPA bug.

## Durable fix (persists across `wsl --shutdown` / reboot) — VERIFIED 2026-07-27

Use **mirrored networking** so Windows and WSL share localhost ([MS docs](https://learn.microsoft.com/en-us/windows/wsl/networking)).

**Verified on this machine:** with `evidence-workbench` running in a kept-open WSL terminal, Chrome and Edge load `http://127.0.0.1:8765/?home=generator` (uvicorn logs `200` from `127.0.0.1`). Connection refused only when the process is not running.

`%UserProfile%\.wslconfig` (already applied on this machine):

```ini
[wsl2]
memory=28GB
processors=14
swap=4GB
localhostForwarding=true
networkingMode=mirrored

[experimental]
autoMemoryReclaim=gradual
sparseVhd=true
hostAddressLoopback=true
```

**Activate once** (closes all WSL sessions):

```powershell
wsl --shutdown
```

**If you previously ran the portproxy script**, remove it under mirrored mode (shared port space — stale proxy causes `address already in use` / hangs). Elevated PowerShell:

```powershell
netsh interface portproxy delete v4tov4 listenport=8765 listenaddress=127.0.0.1
netsh interface portproxy show all
```

Then reopen the Fedora distro / Cursor terminal and start the workbench:

```bash
uv run evidence-workbench --home generator
# open http://127.0.0.1:8765/?home=generator in Cursor browser
```

## Cursor IDE browser MCP vs Windows browsers

| Client | Reaches `http://127.0.0.1:8765` after mirrored mode? |
| --- | --- |
| WSL `curl` | Yes |
| Windows `curl.exe` / Edge / Chrome | Yes — **verified** with server running in a kept-open WSL terminal |
| Cursor **agent** IDE browser MCP | **No** — sandboxed session cannot reach host/WSL loopback (public sites still work) |

For visual QA from the agent, use Playwright **inside WSL**, or open the URL in system Edge. Do not treat Cursor browser MCP failure as a WSL networking regression when Windows curl returns 200.

## Fallback — temporary port bridge

If mirrored mode is unavailable or blocked by VPN/corp policy, use the Admin script (must re-run after WSL IP changes):

```powershell
cd \\wsl$\FedoraLinux-43\home\sls00\portfolio\evid-wb-ui
powershell -ExecutionPolicy Bypass -File .\scripts\wsl-windows-portbridge.ps1
```

## CI / automation

Run Playwright **inside WSL** against `127.0.0.1` (Slice B). That path never depends on Windows↔WSL bridging.

## App behavior

On WSL, `evidence-workbench` defaults `--host` to `0.0.0.0` and prints `127.0.0.1` + eth0 URLs. Override with `--host 127.0.0.1` for loopback-only.
