#!/usr/bin/env python3
"""WebSocket framing checks for mempool_listener.py."""

from __future__ import annotations

from mempool_listener import ws_frame


def main() -> int:
    text = ws_frame(b"{}")
    pong = ws_frame(b"ping", opcode=0xA)
    assert text[0] & 0x0F == 0x1, text[0]
    assert pong[0] & 0x0F == 0xA, pong[0]
    assert text[1] & 0x80 and pong[1] & 0x80
    print("mempool_listener_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
