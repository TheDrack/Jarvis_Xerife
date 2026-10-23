# -*- coding: utf-8 -*-
"""Non-activating status overlay for Jarvis desktop-agent operations.

The overlay is click-through and never intentionally takes keyboard focus.
It reports agent activity; it does not isolate Windows input or sessions.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import functools
import asyncio
import contextvars
import inspect
from pathlib import Path
from typing import Any

STATUS_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Jarvis_Xerife"
STATUS_FILE = STATUS_DIR / "agent_activity.json"
_LOCK = threading.Lock()
_OVERLAY_PROCESS: subprocess.Popen[Any] | None = None
_ACTION_DEPTH = contextvars.ContextVar("jarvis_action_depth", default=0)


def _status_file_lock():
    """Serialize status-file updates across threads and separate Jarvis processes."""
    import contextlib

    @contextlib.contextmanager
    def _locked():
        STATUS_DIR.mkdir(parents=True, exist_ok=True)
        handle = open(STATUS_DIR / "agent_activity.write.lock", "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
    return _locked()


def _replace_status(payload: dict[str, Any]) -> None:
    """Atomically publish status using a unique temp file while holding a process lock."""
    with _LOCK:
        with _status_file_lock():
            tmp = STATUS_DIR / f"agent_activity.{os.getpid()}.{threading.get_ident()}.tmp"
            try:
                tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                last_error = None
                for attempt in range(30):
                    try:
                        os.replace(tmp, STATUS_FILE)
                        last_error = None
                        break
                    except PermissionError as exc:
                        last_error = exc
                        time.sleep(0.02)
                if last_error is not None:
                    raise last_error
            finally:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass


def _write_status(phase: str, action: str, message: str = "") -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": phase,
        "action": str(action)[:100],
        "message": str(message)[:180],
        "updated_at": time.time(),
        "pid": os.getpid(),
    }
    _replace_status(payload)


def begin_action(action: str) -> None:
    """Publish activity and start the optional overlay without blocking MCP."""
    _write_status("working", action)
    ensure_overlay_started()


def set_agent_cursor_target(x: int, y: int, event: str = "target") -> None:
    """Publish a screen-space target for the visual-only Jarvis reticle."""
    data = _read_status()
    if data.get("phase") != "working":
        return
    data.update({"cursor_target": [int(x), int(y)], "cursor_event": str(event)[:24], "updated_at": time.time()})
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    _replace_status(data)


def end_action(action: str, success: bool, message: str = "") -> None:
    _write_status("success" if success else "attention", action, message)


def _overlay_python() -> str:
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate if candidate.exists() else Path(sys.executable))


def ensure_overlay_started() -> bool:
    """Start a single lightweight overlay process if the current user session allows it."""
    global _OVERLAY_PROCESS
    if os.name != "nt":
        return False
    with _LOCK:
        if _OVERLAY_PROCESS is not None and _OVERLAY_PROCESS.poll() is None:
            return True
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            script = str(Path(__file__).resolve())
            _OVERLAY_PROCESS = subprocess.Popen(
                [_overlay_python(), script, "--overlay"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
                close_fds=True,
            )
            return True
        except Exception:
            _OVERLAY_PROCESS = None
            return False


def _read_status() -> dict[str, Any]:
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, ValueError, TypeError):
        return {}


def run_overlay() -> int:
    """Show one compact topmost, no-activate, click-through status window per logon session."""
    overlay_lock_file = None
    if os.name == "nt":
        try:
            import msvcrt
            STATUS_DIR.mkdir(parents=True, exist_ok=True)
            overlay_lock_file = open(STATUS_DIR / "agent_overlay.lock", "a+b")
            overlay_lock_file.seek(0, os.SEEK_END)
            if overlay_lock_file.tell() == 0:
                overlay_lock_file.write(b"0")
                overlay_lock_file.flush()
            overlay_lock_file.seek(0)
            msvcrt.locking(overlay_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except (OSError, ImportError):
            if overlay_lock_file:
                overlay_lock_file.close()
            return 0
    try:
        import tkinter as tk
    except Exception:
        return 2

    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg="#18212b")
    x = max(8, root.winfo_screenwidth() - 350)
    y = max(8, root.winfo_screenheight() - 120)
    root.geometry(f"330x82+{x}+{y}")
    frame = tk.Frame(root, bg="#18212b", padx=12, pady=9)
    frame.pack(fill="both", expand=True)
    title = tk.Label(frame, text="JARVIS · AGENTE", bg="#18212b", fg="#8bd5ff",
                     font=("Segoe UI", 9, "bold"), anchor="w")
    title.pack(fill="x")
    status = tk.Label(frame, text="Aguardando atividade", bg="#18212b", fg="#ffffff",
                      font=("Segoe UI", 10), anchor="w", justify="left", wraplength=300)
    status.pack(fill="x", pady=(3, 0))
    shown_phase = ""
    shown_since = 0.0

    # Ghost cursor: visual-only ring following the real pointer while Jarvis is active.
    # It does not move the pointer, synthesize clicks, or intercept input.
    ghost = tk.Toplevel(root)
    ghost.withdraw()
    ghost.overrideredirect(True)
    ghost.attributes("-topmost", True)
    ghost.configure(bg="#010203")
    try:
        ghost.wm_attributes("-transparentcolor", "#010203")
    except tk.TclError:
        pass
    # Compact animated "photon" cursor: glow, bright core, and a small trailing particle.
    # It deliberately avoids crosshair/target imagery and never captures mouse input.
    ghost_canvas = tk.Canvas(ghost, width=22, height=22, bg="#010203",
                             highlightthickness=0, bd=0)
    ghost_canvas.pack()
    ghost_canvas.create_oval(2, 2, 20, 20, fill="#151515", outline="#FF3B30", width=1)
    ghost_canvas.create_oval(4, 4, 18, 18, fill="#FF3B30", outline="#FFFFFF", width=1)
    ghost_canvas.create_oval(7, 7, 15, 15, fill="#FFFFFF", outline="#151515", width=1)
    ghost_canvas.create_oval(9, 9, 13, 13, fill="#151515", outline="")
    ghost_canvas.create_oval(0, 15, 5, 20, fill="#FFFFFF", outline="")
    cursor_x = [0.0]
    cursor_y = [0.0]
    pulse_phase = [0]

    def apply_ghost_no_activate() -> None:
        try:
            hwnd = ctypes.windll.user32.GetParent(ghost.winfo_id()) or ghost.winfo_id()
            GWL_EXSTYLE = -20
            flags = 0x00000080 | 0x08000000 | 0x00000020 | 0x00080000
            current = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, current | flags)
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except Exception:
            pass

    def apply_no_activate() -> None:
        try:
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            if not hwnd:
                hwnd = root.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_LAYERED = 0x00080000
            current = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                current | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT | WS_EX_LAYERED
            )
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except Exception:
            pass

    def poll() -> None:
        nonlocal shown_phase, shown_since
        data = _read_status()
        phase = str(data.get("phase", "idle"))
        updated = float(data.get("updated_at", 0) or 0)
        action = str(data.get("action", ""))
        message = str(data.get("message", ""))
        if phase != shown_phase or updated > shown_since:
            shown_phase = phase
            shown_since = updated
        now = time.time()
        active = phase == "working"
        recent_result = phase in {"success", "attention"} and now - updated < 4.0
        if active:
            try:
                target = data.get("cursor_target")
                if isinstance(target, list) and len(target) == 2:
                    target_x, target_y = float(target[0]), float(target[1])
                else:
                    point = ctypes.wintypes.POINT()
                    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
                    target_x, target_y = float(point.x), float(point.y)
                # Poll at animation-frame cadence and use time-based easing for smooth travel.
                now_tick = time.perf_counter()
                last_tick = getattr(poll, "_last_tick", now_tick)
                dt = min(max(now_tick - last_tick, 0.001), 0.05)
                poll._last_tick = now_tick
                if cursor_x[0] == 0.0 and cursor_y[0] == 0.0:
                    cursor_x[0], cursor_y[0] = target_x, target_y
                else:
                    # Exponential easing is frame-rate independent and glides across long distances.
                    blend = 1.0 - (0.001 ** dt)
                    cursor_x[0] += (target_x - cursor_x[0]) * blend
                    cursor_y[0] += (target_y - cursor_y[0]) * blend
                ghost.geometry(f"22x22+{int(cursor_x[0] - 11)}+{int(cursor_y[0] - 11)}")
                event = str(data.get("cursor_event", "target"))
                pulse_phase[0] = (pulse_phase[0] + 1) % 60
                # A gentle breathing glow; brief white flash only on click events.
                glow = "#FFFFFF" if event == "click" and pulse_phase[0] < 8 else (
                    "#FF3B30" if pulse_phase[0] < 30 else "#FF786F"
                )
                ghost_canvas.itemconfigure(1, outline=glow)
                ghost_canvas.itemconfigure(2, fill=glow)
                if not ghost.winfo_viewable():
                    ghost.deiconify()
                    ghost.update_idletasks()
                apply_ghost_no_activate()
            except Exception:
                pass
        elif ghost.winfo_viewable():
            ghost.withdraw()
            cursor_x[0] = cursor_y[0] = 0.0
        if active or recent_result:
            if phase == "working":
                status.configure(text=f"Trabalhando: {action}", fg="#ffffff")
            elif phase == "success":
                status.configure(text=f"Concluído: {action}", fg="#9be7a5")
            else:
                detail = f"\n{message}" if message else ""
                status.configure(text=f"Atenção: {action}{detail}", fg="#ffd28a")
            if not root.winfo_viewable():
                root.deiconify()
                root.update_idletasks()
                apply_no_activate()
            else:
                apply_no_activate()
        else:
            if root.winfo_viewable():
                root.withdraw()
        root.after(16, poll)

    poll()
    root.mainloop()
    return 0


def tracked_action(action: str):
    """Instrument sync and async calls centrally; nested calls share one activity lifecycle."""
    def _result_state(result: Any) -> tuple[bool, str]:
        success = True
        message = ""
        try:
            if isinstance(result, dict):
                success = result.get("success", True) is not False
                message = str(result.get("message", result.get("status", "")))
            elif isinstance(result, list) and result and getattr(result[0], "text", None):
                first = json.loads(result[0].text)
                if isinstance(first, dict):
                    success = first.get("success", True) is not False
                    message = str(first.get("message", first.get("status", "")))
        except Exception:
            pass
        return success, message

    def decorate(function):
        if inspect.iscoroutinefunction(function):
            @functools.wraps(function)
            async def async_wrapped(*args, **kwargs):
                depth = _ACTION_DEPTH.get()
                token = _ACTION_DEPTH.set(depth + 1)
                outermost = depth == 0
                if outermost:
                    begin_action(action)
                try:
                    result = await function(*args, **kwargs)
                    success, message = _result_state(result)
                    if outermost:
                        end_action(action, success, message if not success else "")
                    return result
                except Exception as exc:
                    if outermost:
                        end_action(action, False, str(exc))
                    raise
                finally:
                    _ACTION_DEPTH.reset(token)
            return async_wrapped

        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            depth = _ACTION_DEPTH.get()
            token = _ACTION_DEPTH.set(depth + 1)
            outermost = depth == 0
            if outermost:
                begin_action(action)
            try:
                result = function(*args, **kwargs)
                # If a sync wrapper returns an awaitable, keep the indicator active until it resolves.
                if inspect.isawaitable(result):
                    async def await_result():
                        try:
                            resolved = await result
                            success, message = _result_state(resolved)
                            if outermost:
                                end_action(action, success, message if not success else "")
                            return resolved
                        except Exception as exc:
                            if outermost:
                                end_action(action, False, str(exc))
                            raise
                        finally:
                            _ACTION_DEPTH.reset(token)
                    return await_result()
                success, message = _result_state(result)
                if outermost:
                    end_action(action, success, message if not success else "")
                return result
            except Exception as exc:
                if outermost:
                    end_action(action, False, str(exc))
                raise
            finally:
                if not inspect.isawaitable(locals().get("result", None)):
                    _ACTION_DEPTH.reset(token)
        return wrapped
    return decorate


def agent_activity(action: str):
    """Context manager: mostra a atividade do agente durante um bloco (mouse, teclado ou captura).

    Usa o mesmo contador de profundidade de tracked_action: dentro de uma ação já rastreada,
    não cria um segundo ciclo de vida. Falhas são marcadas como atenção e propagadas.
    """
    import contextlib

    @contextlib.contextmanager
    def _scope():
        depth = _ACTION_DEPTH.get()
        token = _ACTION_DEPTH.set(depth + 1)
        outermost = depth == 0
        if outermost:
            begin_action(action)
        success, message = True, ""
        try:
            yield
        except Exception as exc:
            success, message = False, str(exc)
            raise
        finally:
            if outermost:
                end_action(action, success, message)
            _ACTION_DEPTH.reset(token)

    return _scope()


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--overlay":
    raise SystemExit(run_overlay())


