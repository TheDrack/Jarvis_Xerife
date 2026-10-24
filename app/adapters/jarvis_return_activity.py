"""Windows interactive-session activity-return watcher for Jarvis.

Uses GetLastInputInfo (keyboard/mouse input for the current interactive
session), not process activity or network heartbeats. Run as the logged-in
user, never as a Session 0 service.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from app.application.return_activity_service import ReturnActivityDetector

LOG_DIR = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Jarvis_Xerife" / "logs"
LOG_FILE = LOG_DIR / "return_activity.log"
IDLE_THRESHOLD_SECONDS = max(30, int(os.getenv("JARVIS_RETURN_IDLE_SECONDS", "300")))
POLL_SECONDS = max(1, int(os.getenv("JARVIS_RETURN_POLL_SECONDS", "3")))


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.wintypes.UINT), ("dwTime", ctypes.wintypes.DWORD)]


def get_idle_seconds() -> float:
    """Return current-session idle seconds using the native Windows API."""
    if sys.platform != "win32":
        raise OSError("Jarvis return-activity watcher requires Windows")
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_last_input = user32.GetLastInputInfo
    get_last_input.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
    get_last_input.restype = ctypes.wintypes.BOOL
    if not get_last_input(ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    # DWORD subtraction is modulo 2**32; handles the ~49.7-day tick rollover.
    ticks = ctypes.windll.kernel32.GetTickCount()
    elapsed_ms = (int(ticks) - int(info.dwTime)) & 0xFFFFFFFF
    return elapsed_ms / 1000.0


def speak_welcome() -> None:
    """Speak through the Windows speech engine using the default audio output."""
    command = r'''$ErrorActionPreference = 'Stop'; Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; try { $v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'pt-BR' } | Select-Object -First 1; if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }; $s.Speak('Voce voltou. Estou ativo e pronto para continuar.'); } finally { $s.Dispose() }'''
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=45,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _acquire_single_instance() -> object:
    """Keep one watcher per interactive user session."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = ctypes.wintypes.HANDLE
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, True, "Local\\JarvisReturnActivityWatcher")
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        return None
    return handle


def main() -> int:
    if sys.platform != "win32":
        print("Jarvis return-activity watcher requires Windows.", file=sys.stderr)
        return 2
    mutex = _acquire_single_instance()
    if mutex is None:
        return 0
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    detector = ReturnActivityDetector(IDLE_THRESHOLD_SECONDS)
    logging.info("Watcher started; idle_threshold=%ss poll=%ss", IDLE_THRESHOLD_SECONDS, POLL_SECONDS)
    consecutive_errors = 0
    while True:
        try:
            idle_seconds = get_idle_seconds()
            if detector.observe(idle_seconds):
                logging.info("User returned after idle period (threshold=%ss)", IDLE_THRESHOLD_SECONDS)
                try:
                    speak_welcome()
                except Exception:
                    logging.exception("Welcome speech failed")
            consecutive_errors = 0
        except Exception:
            consecutive_errors += 1
            logging.exception("Activity poll failed")
            if consecutive_errors >= 10:
                time.sleep(min(60, POLL_SECONDS * 5))
                consecutive_errors = 0
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
