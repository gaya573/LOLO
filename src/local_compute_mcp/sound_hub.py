from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_SOUND_MODE = "This PC receives audio"
AUDIO_TOOLS = {
    "Voicemeeter/VBAN": ["voicemeeter.exe", "voicemeeter8.exe", "voicemeeterpro.exe"],
    "Scream Receiver": ["scream.exe"],
    "SonoBus": ["SonoBus.exe", "sonobus.exe"],
}


@dataclass
class SoundHubConfig:
    master_volume: int = 80
    mode: str = DEFAULT_SOUND_MODE
    devices: dict[str, dict[str, object]] = field(default_factory=dict)


def load_sound_config(path: Path, default_volume: int = 80, default_mode: str = DEFAULT_SOUND_MODE) -> SoundHubConfig:
    if not path.exists():
        return SoundHubConfig(master_volume=default_volume, mode=default_mode)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return SoundHubConfig(master_volume=default_volume, mode=default_mode)

    devices = data.get("devices", {})
    if not isinstance(devices, dict):
        devices = {}
    return SoundHubConfig(
        master_volume=int(data.get("master_volume", default_volume)),
        mode=str(data.get("mode", default_mode)),
        devices=devices,
    )


def save_sound_config(path: Path, config: SoundHubConfig) -> None:
    path.write_text(
        json.dumps(
            {
                "master_volume": config.master_volume,
                "mode": config.mode,
                "devices": config.devices,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def check_audio_tools() -> dict[str, bool]:
    return {
        label: any(shutil.which(executable) for executable in executables)
        for label, executables in AUDIO_TOOLS.items()
    }


def test_speaker_beep() -> None:
    import winsound

    winsound.MessageBeep(winsound.MB_ICONASTERISK)


def open_windows_volume_mixer() -> None:
    subprocess.Popen(["sndvol.exe"])
