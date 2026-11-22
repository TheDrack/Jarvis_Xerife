#!/data/data/com.termux/files/usr/bin/bash
set -u
export PREFIX="/data/data/com.termux/files/usr"
export HOME="/data/data/com.termux/files/home"
export PATH="$PREFIX/bin:$PATH"
exec "$PREFIX/bin/jarvis-worker" boot-start
