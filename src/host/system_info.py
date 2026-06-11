"""System information for Settings > System (macOS and Windows)."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from host import IS_DARWIN, IS_WINDOWS

if IS_WINDOWS:
    import ctypes
    import winreg


def processor_name() -> str:
    if IS_DARWIN:
        for args in (
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            ["sysctl", "-n", "hw.model"],
        ):
            try:
                out = subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
                if out:
                    return out
            except (subprocess.SubprocessError, OSError):
                continue
        proc = platform.processor().strip()
        return proc or "Unknown"

    if IS_WINDOWS:
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                model, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                model_str = str(model).strip()
                if model_str:
                    return model_str
        except OSError:
            pass
        try:
            output = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name) -join ', '",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            name = output.strip()
            if name:
                return name
        except (subprocess.SubprocessError, OSError):
            pass
        proc = platform.processor().strip()
        if proc:
            return proc
        return os.environ.get("PROCESSOR_IDENTIFIER", "Unknown")

    return platform.processor().strip() or "Unknown"


def graphics_name() -> str:
    if IS_DARWIN:
        try:
            out = subprocess.check_output(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
            data = json.loads(out)
            names: list[str] = []
            for item in data.get("SPDisplaysDataType", []):
                if not isinstance(item, dict):
                    continue
                name = str(item.get("_name") or item.get("sppci_model") or "").strip()
                if name:
                    names.append(name)
            if names:
                return _join_gpus(names)
        except (subprocess.SubprocessError, OSError, json.JSONDecodeError, ValueError):
            pass
        return "Unknown"

    if IS_WINDOWS:
        gpu_names: list[str] = []
        commands = [
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name",
            ],
            ["wmic", "path", "win32_VideoController", "get", "name"],
        ]
        for command in commands:
            try:
                output = subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL)
            except (subprocess.SubprocessError, OSError):
                continue
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            if not lines:
                continue
            if lines[0].lower() == "name":
                lines = lines[1:]
            gpu_names.extend(lines)
            if gpu_names:
                break
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in gpu_names:
            parts = [part.strip() for part in raw.split(",") if part.strip()]
            for part in parts:
                key = part.casefold()
                if key in seen:
                    continue
                seen.add(key)
                cleaned.append(part)
        if cleaned:
            return _join_gpus(cleaned)
    return "Unknown"


def _join_gpus(names: list[str]) -> str:
    def _gpu_sort_key(name: str) -> tuple[int, int, str]:
        lowered = name.casefold()
        vendor_order = {"nvidia": 0, "intel": 1, "amd": 2, "radeon": 2, "apple": 0}
        for vendor, order in vendor_order.items():
            if vendor in lowered:
                return (0, order, lowered)
        return (1, 99, lowered)

    ordered = sorted(names, key=_gpu_sort_key)
    return ", ".join(ordered)


def total_ram_label() -> str:
    if IS_DARWIN:
        try:
            out = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            bytes_total = int(out)
            return f"{bytes_total / (1024 ** 3):.1f} GB"
        except (subprocess.SubprocessError, OSError, ValueError):
            return "Unknown"

    if IS_WINDOWS:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        memory_status = MEMORYSTATUSEX()
        memory_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        try:
            success = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory_status))
        except AttributeError:
            success = 0
        if not success:
            return "Unknown"
        gib = memory_status.ullTotalPhys / (1024 ** 3)
        return f"{gib:.1f} GB"

    return "Unknown"


def os_label() -> str:
    system = platform.system() or "Unknown OS"
    release = platform.release().strip()
    version = platform.version().strip()
    if IS_DARWIN:
        try:
            out = subprocess.check_output(
                ["sw_vers", "-productVersion"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if out:
                return f"macOS {out}"
        except (subprocess.SubprocessError, OSError):
            pass
    if release and version:
        return f"{system} {release} ({version})"
    if release:
        return f"{system} {release}"
    return system


def storage_rows() -> list[tuple[str, str]]:
    if IS_DARWIN:
        rows: list[tuple[str, str]] = []
        for mount in (Path("/"), Path.home()):
            try:
                usage = shutil.disk_usage(mount)
            except OSError:
                continue
            total_gb = usage.total / (1024 ** 3)
            free_gb = usage.free / (1024 ** 3)
            label = "Storage (Macintosh HD)" if mount == Path("/") else f"Storage ({mount})"
            rows.append((label, f"{total_gb:.1f} GB total ({free_gb:.1f} GB free)"))
        return rows or [("Storage", "Unknown")]

    if IS_WINDOWS:
        try:
            output = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_LogicalDisk | "
                    "Where-Object {$_.DriveType -eq 3 -and $_.Size} | "
                    "ForEach-Object {"
                    "$t=$_.Size/1GB; $f=$_.FreeSpace/1GB; "
                    "'{0}|{1:N1} GB total ({2:N1} GB free)' -f $_.DeviceID,$t,$f"
                    "}",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.SubprocessError, OSError):
            return [("Storage", "Unknown")]

        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if not lines:
            return [("Storage", "Unknown")]

        rows = []
        for line in lines:
            if "|" not in line:
                continue
            drive, details = line.split("|", 1)
            rows.append((f"Storage ({drive})", details.strip()))
        return rows or [("Storage", "Unknown")]

    return [("Storage", "Unknown")]


def collect_system_info_rows() -> list[tuple[str, str]]:
    return [
        ("Processor", processor_name()),
        ("Graphics Card", graphics_name()),
        ("RAM", total_ram_label()),
        ("OS", os_label()),
        ("Machine", platform.machine() or "Unknown"),
        *storage_rows(),
    ]


def apply_power_action(action_name: str) -> None:
    lowered = action_name.casefold()
    if IS_DARWIN:
        if lowered == "shutdown":
            subprocess.Popen(
                ["osascript", "-e", 'tell application "System Events" to shut down'],
            )
            return
        if lowered == "restart":
            subprocess.Popen(
                ["osascript", "-e", 'tell application "System Events" to restart'],
            )
            return
        if lowered == "sleep":
            subprocess.Popen(["pmset", "sleepnow"])
            return
        if lowered == "lock":
            subprocess.Popen(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to keystroke "q" using {control down, command down}',
                ],
            )
            return
        return

    if IS_WINDOWS:
        if lowered == "shutdown":
            subprocess.Popen(["shutdown", "/s", "/t", "0"])
            return
        if lowered == "restart":
            subprocess.Popen(["shutdown", "/r", "/t", "0"])
            return
        if lowered == "sleep":
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            return
        if lowered == "lock":
            try:
                ctypes.windll.user32.LockWorkStation()
            except AttributeError:
                pass
