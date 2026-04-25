from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkDevice:
    ip: str
    name: str = ""
    source: str = "same-wifi"


def find_local_ipv4s() -> list[str]:
    ips: set[str] = set()
    hostname = socket.gethostname()
    for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
        ip = info[4][0]
        address = ipaddress.ip_address(ip)
        if address.is_private and not address.is_loopback:
            ips.add(ip)
    return sorted(ips)


def discover_same_wifi(timeout_ms: int = 350) -> list[NetworkDevice]:
    candidates: set[str] = set()
    for ip in find_local_ipv4s():
        network = ipaddress.ip_network(f"{ip}/24", strict=False)
        hosts = [str(host) for host in network.hosts()]
        with ThreadPoolExecutor(max_workers=64) as executor:
            futures = [executor.submit(_ping, host, timeout_ms) for host in hosts]
            for future in as_completed(futures):
                result = future.result()
                if result:
                    candidates.add(result)

    candidates.update(_arp_ips())
    sorted_ips = sorted(candidates, key=lambda value: tuple(int(part) for part in value.split(".")))
    return [_device(ip) for ip in sorted_ips]


def _ping(ip: str, timeout_ms: int) -> str | None:
    completed = subprocess.run(
        ["ping", "-n", "1", "-w", str(timeout_ms), ip],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    return ip if completed.returncode == 0 else None


def _arp_ips() -> set[str]:
    completed = subprocess.run(["arp", "-a"], capture_output=True, text=True, encoding="utf-8", errors="ignore")
    ips: set[str] = set()
    for match in re.finditer(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", completed.stdout):
        ip = match.group(0)
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if address.is_private and not address.is_loopback:
            ips.add(ip)
    return ips


def _device(ip: str) -> NetworkDevice:
    name = ""
    try:
        name = socket.gethostbyaddr(ip)[0]
    except OSError:
        pass
    return NetworkDevice(ip=ip, name=name)
