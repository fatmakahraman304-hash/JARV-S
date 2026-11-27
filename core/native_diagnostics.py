"""Read-only local diagnostics. No user-provided shell commands are executed."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess

_CIM_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$os = Get-CimInstance -ClassName Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber
$cpu = @(Get-CimInstance -ClassName Win32_Processor | Select-Object -Property Name, NumberOfCores, NumberOfLogicalProcessors -First 4)
$gpu = @(Get-CimInstance -ClassName Win32_VideoController | Select-Object -Property Name, AdapterRAM, DriverVersion -First 8)
$bios = @(Get-CimInstance -ClassName Win32_BIOS | Select-Object -Property Manufacturer, SMBIOSBIOSVersion -First 1)
[ordered]@{ operating_system = $os; processors = $cpu; graphics = $gpu; bios = $bios } | ConvertTo-Json -Compress -Depth 4
'''


def _windows_cim(timeout=15):
    root = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
    exe = Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not exe.is_file():
        raise RuntimeError("Windows PowerShell 5.1 bulunamadı")
    cmd = [str(exe), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", _CIM_SCRIPT]
    proc = subprocess.run(cmd, shell=False, stdin=subprocess.DEVNULL, capture_output=True,
                          timeout=timeout, encoding="utf-8", errors="replace",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if proc.returncode:
        detail = " ".join((proc.stderr or "").split())[:200]
        raise RuntimeError(f"CIM sorgusu başarısız (çıkış kodu {proc.returncode}): {detail}")
    if len(proc.stdout.encode("utf-8")) > 200_000:
        raise RuntimeError("CIM yanıtı sınırı aştı")
    result = json.loads(proc.stdout.lstrip("\ufeff"))
    if not isinstance(result, dict) or not isinstance(result.get("operating_system"), dict):
        raise ValueError("CIM yanıt biçimi doğrulanamadı")
    return result


def collect():
    """Observed values only; each missing source has an explicit error.

    Network interface state is local link state, not proof of internet access.
    No files, process lists, network addresses, credentials or commands are read.
    """
    result = {"observed_at": datetime.now(timezone.utc).isoformat(),
              "platform": platform.system(), "metrics": {}, "windows_cim": None, "errors": []}
    try:
        import psutil
    except ImportError:
        result["errors"].append("Sistem ölçüm kütüphanesi kullanılamıyor.")
        psutil = None
    if psutil is not None:
        def sample(name, fn):
            try:
                result["metrics"][name] = fn()
            except Exception as exc:
                result["metrics"][name] = None
                result["errors"].append(f"{name}: {type(exc).__name__}")
        sample("cpu_percent", lambda: psutil.cpu_percent(interval=0.2))
        def memory():
            value = psutil.virtual_memory()
            return {"percent": value.percent, "available_bytes": value.available, "total_bytes": value.total}
        sample("memory", memory)
        def disk():
            value = psutil.disk_usage(Path.home().anchor or "/")
            return {"percent": value.percent, "free_bytes": value.free, "total_bytes": value.total}
        sample("system_disk", disk)
        def battery():
            value = psutil.sensors_battery()
            if value is None:
                return None
            return {"percent": value.percent, "plugged_in": value.power_plugged}
        sample("battery", battery)
        sample("network_interfaces", lambda: [{"name": name, "up": stats.isup,
                                                "speed_mbps": stats.speed if stats.speed > 0 else None}
                                               for name, stats in list(psutil.net_if_stats().items())[:32]])
    if result["platform"] == "Windows":
        try:
            result["windows_cim"] = _windows_cim()
        except (OSError, subprocess.SubprocessError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            result["errors"].append(f"Windows CIM: {type(exc).__name__}: {str(exc)[:120]}")
    return result
