# Local Compute

Local Compute is a Windows app that helps non-developers connect multiple PCs, share one work folder, and process files across those PCs.

The app is intentionally menu-based:

```text
Home
Device Registration
Shared Folder Management
File Processing
Running Log
Error Log
MCP Connection
```

## Current Status

| Area | Status | Notes |
|---|---:|---|
| Windows GUI app | Done | Tkinter-based desktop app |
| Setup wizard | Done | `dist/LocalComputeMCP-Setup.exe` |
| Device registration menu | Done | Same-Wi-Fi scan, manual add, pairing-code flow |
| Pairing code flow | Prototype | Shows 6-digit code and discovers it on LAN |
| Shared folder setup | Done | Creates `C:\LocalComputeShare` on A/main PC |
| File processing engine | Done | Splits independent files across workers |
| Retry failed files | Done | Uses `logs/joblog.tsv` |
| MCP server | Done | Tools for list/test/run/retry |
| Sound hub | Prototype | App menu, master soundbar, per-PC mixer profile, tool checks |
| Remote screen sharing/control | Not built | Possible, but separate heavy feature |

## Important Concept

This app does **not** merge CPUs into one giant CPU.

It does this:

```text
file001.xlsx -> PC A
file002.xlsx -> PC B
file003.xlsx -> PC C
```

Each PC runs its own task, then writes results back to the shared folder.

## File Map For Other AI / Developers

| Path | Purpose |
|---|---|
| `src/local_compute_mcp/gui.py` | Main non-developer GUI app |
| `src/local_compute_mcp/runner.py` | Distributed job runner |
| `src/local_compute_mcp/config.py` | `workers.yaml` parser/writer |
| `src/local_compute_mcp/discovery.py` | Same-Wi-Fi/LAN PC discovery |
| `src/local_compute_mcp/pairing.py` | 6-digit pairing-code prototype |
| `src/local_compute_mcp/server.py` | MCP stdio server |
| `src/local_compute_mcp/cli.py` | CLI wrapper |
| `workers.yaml` | Registered PCs/workers |
| `scripts/setup_shared_disk_on_A.ps1` | Creates Windows shared folder on main PC |
| `setup_shared_disk_on_A_admin.bat` | Runs shared-folder setup as admin |
| `installer/installer.py` | Setup wizard source |
| `installer/app_entry.py` | PyInstaller entry for app |
| `build_installer.ps1` | Builds `LocalCompute.exe` and setup EXE |
| `dist/LocalComputeMCP-Setup.exe` | Installer output |
| `samples/` | Sample input and sample worker |

## Install / Build

### For Users

Download and run:

```text
dist/LocalComputeMCP-Setup.exe
```

If Windows blocks the unsigned EXE, run the app from source:

```powershell
cd C:\Users\rje28\local-compute-mcp
$env:PYTHONPATH="C:\Users\rje28\local-compute-mcp\src"
python -m local_compute_mcp.gui
```

### For Developers / AI Agents

Build the installer:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_installer.ps1
```

Run tests/smoke checks:

```powershell
python -m py_compile src\local_compute_mcp\gui.py src\local_compute_mcp\runner.py src\local_compute_mcp\server.py
.\run_cli.bat test
.\run_cli.bat run --input .\samples\input --pattern *.txt --command "python samples\sample_worker.py {input_q} {output_dir_q}"
```

## User Flow

| Step | Menu | User Action | Result |
|---:|---|---|---|
| 1 | Device Registration | Click `Find same Wi-Fi PC` | Finds possible PCs on LAN |
| 2 | Device Registration | Or click `Allow this device to connect` | Shows 6-digit code |
| 3 | Device Registration | Other PC clicks `Connect by number` | Adds device by pairing code |
| 4 | Shared Folder Management | Click `Make this PC shared storage` | Creates `C:\LocalComputeShare` |
| 5 | File Processing | Put files into `input` | Files are ready |
| 6 | File Processing | Click `Start file processing` | Work is split across PCs |
| 7 | Running Log | View job log | Shows progress/results |
| 8 | Error Log | View failed jobs | Shows only failures |

## Shared Folder Design

Main PC A owns the shared folder:

```text
C:\LocalComputeShare
  input\
  outputs\
  logs\
```

Network path:

```text
\\A-PC\LocalComputeShare
```

Recommended app paths:

```text
Input folder  = \\A-PC\LocalComputeShare\input
Output folder = \\A-PC\LocalComputeShare\outputs
Logs folder   = \\A-PC\LocalComputeShare\logs
```

## Worker / PC Requirements

| Requirement | Why |
|---|---|
| Same Wi-Fi, LAN, Tailscale, or ZeroTier | PCs must reach each other |
| SSH available for current worker mode | Remote commands currently use SSH |
| Shared folder accessible from B/C | Workers need to read input and write output |
| Same tools installed on every worker | Python/Node/Excel/etc. must exist where command runs |

## Supported Command Types

Advanced users can run almost anything that works in Windows command line:

| Type | Example |
|---|---|
| Python | `python check_excel.py {input_q} {output_dir_q}` |
| PowerShell | `powershell -ExecutionPolicy Bypass -File check.ps1 {input_q}` |
| Batch/CMD | `check_excel.bat {input_q} {output_dir_q}` |
| EXE | `mytool.exe {input_q} {output_dir_q}` |
| Node.js | `node check.js {input_q} {output_dir_q}` |

Template variables:

| Variable | Meaning |
|---|---|
| `{input}` | Input file path |
| `{input_q}` | Quoted input file path |
| `{input_name}` | File name |
| `{input_stem}` | File name without extension |
| `{output_dir}` | Output folder |
| `{output_dir_q}` | Quoted output folder |
| `{job_id}` | Stable job ID |
| `{worker}` | Worker name |

## MCP Configuration

The local MCP server is already compatible with Codex/Cursor style configs.

Recommended ASCII-safe path:

```text
C:\Users\rje28\local-compute-mcp
```

Example:

```json
{
  "mcpServers": {
    "local-compute": {
      "command": "python",
      "args": [
        "-m",
        "local_compute_mcp.server",
        "--config",
        "C:/Users/rje28/local-compute-mcp/workers.yaml"
      ],
      "env": {
        "PYTHONPATH": "C:/Users/rje28/local-compute-mcp/src"
      }
    }
  }
}
```

Available MCP tools:

| Tool | Purpose |
|---|---|
| `list_workers` | List enabled PCs |
| `test_workers` | Test local/SSH workers |
| `submit_jobs` | Run distributed file jobs |
| `retry_failed` | Retry failed jobs from `joblog.tsv` |

## Sound Hub Prototype

The user requested:

> Hear sound from all PCs through one speaker, with per-PC volume controls.

This is possible, but the first implementation is a **Sound Hub control screen**, not a full custom audio driver.

Implemented now:

| Menu | Purpose |
|---|---|
| Sound Hub | Main audio feature screen |
| Mode | Select whether this PC receives audio or sends audio |
| Soundbar | Master volume profile and speaker test beep |
| Per-PC mixer profile | Per-PC volume sliders and mute toggles |
| Check Audio Tools | Checks for Voicemeeter/VBAN, Scream, and SonoBus executables |
| Open Windows Volume Mixer | Opens native Windows volume mixer |
| Open VBAN/Scream/SonoBus | Opens official setup pages |

Not implemented yet:

| Missing Part | Why |
|---|---|
| Real system-audio capture | Needs a virtual audio device or audio-over-network tool |
| Real network audio streaming | Should use VBAN, Scream, or SonoBus first |
| Applying per-PC volume remotely | Needs worker agent/audio engine integration |
| Live activity meter | Needs real audio stream level data |

Recommended implementation path:

| Option | Recommendation | Notes |
|---|---:|---|
| Use VBAN/Voicemeeter integration | High | Mature Windows audio-over-network path |
| Use Scream virtual network sound card | Medium | Good for LAN audio capture |
| Use SonoBus | Medium | Better for internet/remote audio, more musician-style |
| Build custom audio driver | Low | Too heavy for MVP |

## Remote Screen Sharing / Remote Control

Remote screen sharing/control is **possible**, but it is not the same feature as file processing or audio mixing.

| Feature | Difficulty | Recommended Approach |
|---|---:|---|
| View remote screen | Medium | Integrate existing VNC/RustDesk/Parsec/AnyDesk style tool |
| Control remote mouse/keyboard | High | Needs permissions, security, input injection |
| Build custom remote desktop engine | Very high | Not recommended for this app MVP |
| Launch existing remote-control tool from this app | Reasonable | Best path if needed |

Short answer:

```text
It is not impossible.
But building safe, smooth remote control directly into this app is a large separate project.
For MVP, integrate or launch an existing remote desktop tool instead.
```

## Known Limitations

| Limitation | Details |
|---|---|
| Installer EXE is unsigned | Some Windows Application Control policies can block it |
| Pairing code is prototype | It helps register IP/name, but actual remote execution still uses SSH |
| Worker mode currently uses SSH | Future worker agent mode could remove SSH requirement |
| Same-Wi-Fi discovery is best-effort | Firewalls may hide PCs from ping/ARP |
| Non-developer UI still needs polish | Current layout is simpler, but not fully production-grade |

## Best Next Steps

| Priority | Task |
|---:|---|
| 1 | Add Worker Agent mode so B/C can connect without SSH |
| 2 | Improve UI visual design and first-run wizard |
| 3 | Add Sound Hub module using VBAN/Scream/SonoBus integration |
| 4 | Add code signing or MSI/Inno Setup installer |
| 5 | Add optional remote desktop launcher integration |
