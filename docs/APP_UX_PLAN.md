# Local Compute App UX Plan

This document is written so another AI, planner, or developer can continue the product work without reverse-engineering the code.

## Product Direction

| Principle | Decision |
|---|---|
| Target user | Non-developer, 40-60 year-old office user |
| UX style | Mobile-app-like desktop shell |
| Visual language | Large cards, clear icons, short Korean labels, one purpose per screen |
| Default path | User should not see command lines or MCP first |
| Advanced path | MCP, command templates, SSH details remain available but secondary |

## Main Navigation

| Screen | Icon | Primary Job | Main CTA |
|---|---|---|---|
| Home | Home | Show setup progress and next step | Start setup |
| Device | Link | Register/connect PCs | Allow connection / Add by number |
| Folder | Folder | Create/manage A-PC shared folder | Make this PC storage |
| Process | Lightning | Process input files | Start processing |
| Sound | Speaker | Soundbar/mixer profile | Test speaker / Check tools |
| AI Assist | AI | Let trusted AI/main PC inspect this PC | Allow AI remote assist |
| Log | Clipboard | See running history | Refresh |
| Error | Warning | See failed jobs | Retry failed |
| MCP | Plug | AI tool connection info | Copy/use config |

## User Flow

```mermaid
flowchart TD
    A["Open Local Compute"] --> B["Home: see next step"]
    B --> C["Device Registration"]
    C --> D{"How to connect?"}
    D --> E["Same Wi-Fi scan"]
    D --> F["Allow connection: show 6-digit code"]
    D --> G["Manual add"]
    E --> H["Save device"]
    F --> H
    G --> H
    H --> I["Shared Folder Management"]
    I --> J["Make this PC shared storage"]
    J --> K["Put files in input folder"]
    K --> L["File Processing"]
    L --> M["Start processing"]
    M --> N["Running Log"]
    M --> O{"Failed jobs?"}
    O -->|Yes| P["Error Log: retry failed"]
    O -->|No| Q["Open outputs folder"]
```

## Sound Hub Flow

```mermaid
flowchart TD
    A["Open Sound Hub"] --> B{"Role"}
    B --> C["This PC receives audio"]
    B --> D["This PC sends audio"]
    C --> E["Master soundbar"]
    C --> F["Per-PC volume/mute"]
    D --> G["Install or open VBAN/Scream/SonoBus"]
    E --> H["Test speaker beep"]
    F --> I["Future: live level meter"]
```

## AI Remote Assist Flow

```mermaid
flowchart TD
    A["Open AI Remote Assist"] --> B["Click allow"]
    B --> C["App shows 6-digit code and screenshot URL"]
    C --> D["Main PC / AI opens URL with code"]
    D --> E["Approved PC returns current screenshot"]
    E --> F{"Need action?"}
    F -->|Yes| G["Future: request specific permission"]
    G --> H["User approves open Excel / click / type / command"]
    F -->|No| I["Stop by closing app"]
```

## AI Remote Assist Permission Model

| Permission | Current Status | Product Rule |
|---|---:|---|
| View current screen | Prototype | Only after user clicks allow and code matches |
| Save screenshot | Done | Saves locally to output folder |
| Open Excel | Prototype | Local-only launcher button |
| Remote click/type | Planned | Must be time-limited and user-visible |
| Run command | Planned | Must log command, target PC, output, and failure |

## Implementation Notes

| Concern | Current Implementation | Next Step |
|---|---|---|
| Icons | Built-in Segoe UI Emoji / symbol text | Replace with image/icon assets if packaging allows |
| Layout | Tkinter custom card shell | Can later migrate to Qt/Flet/Electron |
| Sound Hub | Mixer profile UI, tool checks | Add VBAN/Scream/SonoBus automation |
| AI Remote Assist | User-approved screenshot server | Add per-action remote agent permissions |
| Remote control | Planned only | Integrate RustDesk/VNC launcher or signed local agent rather than unsafe raw control |
| Worker execution | SSH-based | Add agent mode for non-developer pairing |

## Copy Guidelines

| Avoid | Use Instead |
|---|---|
| input/output | 처리할 파일 / 결과 폴더 |
| command | 고급 실행 방식 |
| SSH | 기기 연결 테스트 |
| worker | 연결된 PC |
| job | 파일 처리 |
