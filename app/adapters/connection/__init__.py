"""Conexões de dispositivo independentes de MCP, túnel e banco de dados."""

from app.adapters.connection.adb_connection import AdbConnection, AdbError

__all__ = ["AdbConnection", "AdbError"]
