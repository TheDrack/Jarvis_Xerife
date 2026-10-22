# -*- coding: utf-8 -*-
"""Janela-scoped background mouse input for compatible Win32 applications.

This backend posts mouse messages to a uniquely matched window. It never calls
SetCursorPos, SendInput, mouse_event, or PyAutoGUI. Some applications ignore
posted input; success means messages were queued, not that the UI action worked.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001
CWP_SKIPINVISIBLE = 0x0001
CWP_SKIPDISABLED = 0x0002
CWP_SKIPTRANSPARENT = 0x0004


def pack_point(x: int, y: int) -> int:
    """Pack non-negative client coordinates into the Win32 LPARAM format."""
    if not (0 <= int(x) <= 0x7FFF and 0 <= int(y) <= 0x7FFF):
        raise ValueError("Coordenadas de cliente fora do intervalo Win32 suportado.")
    return (int(y) << 16) | int(x)


def click_window_background(
    window_title_contains: str,
    x: int,
    y: int,
    *,
    coordinates_are_screen: bool = False,
    user32: Any = None,
) -> dict[str, Any]:
    """Post one left click at client coordinates to one unique visible window."""
    needle = str(window_title_contains or "").strip().casefold()
    if not needle:
        return {"success": False, "status": "invalid_target", "message": "Informe parte do título da janela-alvo."}
    try:
        x, y = int(x), int(y)
        lparam = None if coordinates_are_screen else pack_point(x, y)
    except (TypeError, ValueError) as exc:
        return {"success": False, "status": "invalid_coordinates", "message": str(exc)}

    if user32 is None:
        if not hasattr(ctypes, "windll"):
            return {"success": False, "status": "unsupported_platform", "message": "Entrada em segundo plano disponível somente no Windows."}
        user32 = ctypes.WinDLL("user32", use_last_error=True)

    handles: list[tuple[int, str]] = []
    enum_callback_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )
    # Explicit pointer-sized signatures prevent HWND truncation on 64-bit Windows.
    if hasattr(user32, "EnumWindows") and hasattr(user32.EnumWindows, "argtypes"):
        user32.EnumWindows.argtypes = [enum_callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetClientRect.restype = wintypes.BOOL
        user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        user32.ClientToScreen.restype = wintypes.BOOL
        user32.ChildWindowFromPointEx.argtypes = [wintypes.HWND, wintypes.POINT, wintypes.UINT]
        user32.ChildWindowFromPointEx.restype = wintypes.HWND
        user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        user32.ScreenToClient.restype = wintypes.BOOL
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL

    @enum_callback_type
    def enum_callback(hwnd: int, _lparam: int) -> bool:
        try:
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value
            if needle in title.casefold():
                handles.append((int(hwnd), title))
        except Exception:
            pass
        return True

    user32.EnumWindows(enum_callback, 0)
    if not handles:
        return {"success": False, "status": "window_not_found", "message": "Nenhuma janela visível corresponde ao título informado."}
    if len(handles) != 1:
        return {"success": False, "status": "ambiguous_window", "matches": [{"hwnd": h, "title": t} for h, t in handles[:10]], "message": "O título corresponde a mais de uma janela; nenhuma mensagem foi enviada."}

    hwnd, title = handles[0]
    if coordinates_are_screen:
        point = wintypes.POINT(x, y)
        if not user32.ScreenToClient(hwnd, ctypes.byref(point)):
            return {"success": False, "status": "coordinate_mapping_failed", "hwnd": hwnd}
        x, y = point.x, point.y
        try:
            lparam = pack_point(x, y)
        except ValueError as exc:
            return {"success": False, "status": "invalid_coordinates", "message": str(exc)}
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return {"success": False, "status": "window_geometry_unavailable", "hwnd": hwnd, "message": "Não foi possível ler a área cliente da janela."}
    if x < 0 or y < 0 or x >= rect.right or y >= rect.bottom:
        return {"success": False, "status": "coordinates_out_of_bounds", "hwnd": hwnd, "client_size": [rect.right, rect.bottom], "message": "As coordenadas estão fora da área cliente da janela."}

    # Map the target client point to screen coordinates, then select the deepest
    # child HWND under it and remap coordinates into that child client space.
    client_point = wintypes.POINT(x, y)
    child = user32.ChildWindowFromPointEx(hwnd, client_point, CWP_SKIPINVISIBLE | CWP_SKIPDISABLED | CWP_SKIPTRANSPARENT)
    target = int(child or hwnd)
    point = wintypes.POINT(x, y)
    if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
        return {"success": False, "status": "coordinate_mapping_failed", "hwnd": hwnd}
    child_point = wintypes.POINT(point.x, point.y)
    if not user32.ScreenToClient(target, ctypes.byref(child_point)):
        return {"success": False, "status": "coordinate_mapping_failed", "hwnd": hwnd}
    child_lparam = pack_point(child_point.x, child_point.y)

    # These are window messages, not physical input. A target app may ignore them.
    messages = [
        (WM_MOUSEMOVE, 0, child_lparam),
        (WM_LBUTTONDOWN, MK_LBUTTON, child_lparam),
        (WM_LBUTTONUP, 0, child_lparam),
    ]
    for message, wparam, message_lparam in messages:
        if not user32.PostMessageW(target, message, wparam, message_lparam):
            error = ctypes.get_last_error()
            return {
                "success": False, "status": "background_input_failed",
                "hwnd": hwnd, "target_hwnd": target, "window_title": title,
                "posted_messages": messages.index((message, wparam, message_lparam)),
                "winerror": error,
                "message": "O Windows recusou uma mensagem de entrada em segundo plano.",
            }
    return {
        "success": True,
        "status": "background_messages_posted",
        "input_mode": "win32_postmessage_background",
        "hwnd": hwnd, "target_hwnd": target, "window_title": title,
        "client_coordinates": [x, y],
        "physical_cursor_touched": False,
        "action_verified": False,
        "message": "Mensagens de clique enfileiradas sem mover o cursor físico; verifique a pós-condição visual/semântica.",
    }
