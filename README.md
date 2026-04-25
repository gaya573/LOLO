# Local Compute MCP

Local Compute MCP is a small Windows-friendly distributed job runner for Codex, Cursor, Claude, and other MCP clients.

It does not combine several PCs into one CPU. Instead, it splits independent file jobs across your local PC and remote PCs over SSH.

## What It Does

- Starts as a local MCP server over stdio.
- Reads workers from `workers.yaml`.
- Tests local and SSH workers.
- Splits files from an input folder across available workers.
- Runs a command template for each file.
- Writes logs to `logs/joblog.tsv`.
- Retries only failed jobs.

## Quick Start

### Download Installer

Download and run:

```text
dist\LocalComputeMCP-Setup.exe
```

The setup wizard installs `LocalCompute.exe`, creates shortcuts, and opens the app.

Default install location:

```text
%LOCALAPPDATA%\LocalComputeMCP
```

After install, open `Local Compute MCP` from the Desktop or Start Menu.

### Easiest: Double Click App

Double-click:

```text
start_app.bat
```

The app lets you:

- register another PC
- save `workers.yaml`
- test SSH connection
- choose an input folder
- run jobs
- retry failed jobs

For another PC on the same Wi-Fi, use its local IP such as:

```text
192.168.0.22
```

For Tailscale or ZeroTier, use the IP shown inside that app. The rest is the same.

Before running remote jobs, this command must work from the main PC:

```powershell
ssh user@192.168.0.22 "echo hello"
```

For Tailscale, it looks more like:

```powershell
ssh user@100.x.y.z "echo hello"
```

If SSH does not work yet, use only the `local` worker or install/enable SSH on the other PC first.

## Shared Disk: A Computer Stores Everything

For multiple PCs, this is the recommended beginner setup:

```text
A/main PC
  C:\LocalComputeShare
    input\
    outputs\
    logs\

B/C worker PCs
  read/write through \\A-PC\LocalComputeShare
```

Same Wi-Fi, Tailscale, and ZeroTier all work the same way. The only difference is which name/IP you use to reach A.

### Step 1: Create The Share On A

On the A/main computer, double-click:

```text
setup_shared_disk_on_A_admin.bat
```

Or open PowerShell as Administrator and run:

```powershell
.\scripts\setup_shared_disk_on_A.ps1
```

It creates:

```text
C:\LocalComputeShare\input
C:\LocalComputeShare\outputs
C:\LocalComputeShare\logs
```

And shares it as:

```text
\\A-COMPUTER-NAME\LocalComputeShare
```

### Step 2: Test From B/C

On B/C, test access:

```powershell
.\scripts\test_shared_disk_access.ps1 -SharePath "\\A-COMPUTER-NAME\LocalComputeShare"
```

Optional drive mapping:

```powershell
.\scripts\map_shared_disk_on_worker.ps1 -MainComputer "A-COMPUTER-NAME"
```

For SSH jobs, prefer the UNC path over a mapped drive:

```text
\\A-COMPUTER-NAME\LocalComputeShare\input
\\A-COMPUTER-NAME\LocalComputeShare\outputs
\\A-COMPUTER-NAME\LocalComputeShare\logs
```

### Step 3: Use These Paths In The App

Double-click `start_app.bat`, then set:

```text
Input 폴더 : \\A-COMPUTER-NAME\LocalComputeShare\input
Output 폴더: \\A-COMPUTER-NAME\LocalComputeShare\outputs
Logs 폴더  : \\A-COMPUTER-NAME\LocalComputeShare\logs
```

Put Excel/PDF/image files into `input`, then click `작업 실행`.

Important: B/C must be able to access the shared folder using the same Windows account permission. If remote SSH works but the shared disk fails, fix Windows sharing permission first.

1. Edit `workers.yaml`.
2. Test workers:

```powershell
.\run_cli.bat test
```

3. Run a sample distributed command:

```powershell
.\run_cli.bat run --input .\samples\input --pattern *.txt --command "python samples\sample_worker.py {input} {output_dir}"
```

4. Retry failed jobs:

```powershell
.\run_cli.bat retry --command "python samples\sample_worker.py {input} {output_dir}"
```

## MCP Client Config

Add this server to your MCP client config:

```json
{
  "mcpServers": {
    "local-compute": {
      "command": "python",
      "args": [
        "-m",
        "local_compute_mcp.server",
        "--config",
        "C:/Users/rje28/Downloads/ㄹㄹㄹ/local-compute-mcp/workers.yaml"
      ],
      "env": {
        "PYTHONPATH": "C:/Users/rje28/Downloads/ㄹㄹㄹ/local-compute-mcp/src"
      }
    }
  }
}
```

Then ask:

```text
input 폴더의 파일들을 local-compute MCP로 나눠서 처리해줘.
command는 python check_excel.py {input} {output_dir} 로 실행해줘.
```

## Command Template Variables

- `{input}`: input file path
- `{input_q}`: quoted input file path
- `{input_name}`: file name
- `{input_stem}`: file name without extension
- `{output_dir}`: output directory
- `{output_dir_q}`: quoted output directory
- `{job_id}`: stable job id
- `{worker}`: worker name

For real Excel jobs on Windows, prefer the quoted variables:

```powershell
.\run_cli.bat run --input .\input --pattern *.xlsx --command "python check_excel.py {input_q} {output_dir_q}"
```

## Worker Notes

For remote SSH workers, the simplest setup is:

- Each PC has the same repo cloned.
- Each PC can read the same input path, usually through a shared network path.
- Each PC can write to the same output path, or writes locally and you collect later.
- SSH key login is already configured.

Test manually from the main PC:

```powershell
ssh user@192.168.0.22 "echo hello"
```

## Double Click

Double-click `start_mcp_server.bat` to keep the MCP server running in a console window.

Most MCP clients start the server automatically from their config, so double-click is mainly useful for testing.
