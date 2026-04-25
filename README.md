# Local Compute

Local Compute is a simple Windows app for using several PCs together.

It is designed for non-developers:

- register PCs
- create/manage a shared folder
- process files
- check running logs
- check error logs
- optionally connect MCP for Codex/Cursor/Claude

## Download

Run the installer:

```text
dist\LocalComputeMCP-Setup.exe
```

After install, open `Local Compute` from the Desktop or Start Menu.

## Easy App Flow

### 1. Register Devices

Open `기기등록`.

You have two easy choices:

```text
같은 Wi-Fi PC 찾기
```

This scans PCs on the same Wi-Fi/LAN.

Or:

```text
내 기기 연결 허용
```

This shows a 6-digit number. On another PC, click:

```text
번호로 연결
```

Then enter that number.

### 2. Shared Folder Management

Open `공유폴더관리`.

On the main A computer, click:

```text
이 PC를 공용 저장소로 만들기
```

It creates:

```text
C:\LocalComputeShare\input
C:\LocalComputeShare\outputs
C:\LocalComputeShare\logs
```

The shared network path looks like:

```text
\\A-PC\LocalComputeShare
```

### 3. Process Files

Open `파일처리`.

Put files into:

```text
input
```

Then click:

```text
파일 처리 시작
```

Results go to:

```text
outputs
```

Logs go to:

```text
logs
```

## What Can It Run?

For normal users, use the app screens only.

For advanced users, the processing command can run:

- Python scripts
- PowerShell scripts
- BAT/CMD files
- EXE tools
- Node.js scripts
- Excel automation scripts

Every connected PC must have the required program installed. For example, Python jobs need Python on every PC.

## Same Wi-Fi / Tailscale / ZeroTier

Same Wi-Fi is easiest.

Tailscale or ZeroTier also works, but automatic same-Wi-Fi scan may not find those devices. Add the Tailscale/ZeroTier IP manually or use the connection number feature when both PCs can reach each other.

## MCP

MCP is optional. Non-developers can ignore it.

Developers can connect the MCP server to Codex/Cursor/Claude using:

```json
{
  "mcpServers": {
    "local-compute": {
      "command": "python",
      "args": ["-m", "local_compute_mcp.server", "--config", "workers.yaml"]
    }
  }
}
```
