"""Local energy-based turn detection for explicitly enabled Realtime capture.

No network, device access or wake word. Accepts mono PCM16LE at 16 kHz;
the application must stop capture and reset this state when muted/asleep.
"""
from __future__ import annotations

from collections import deque
import math
import struct

FRAME_BYTES = 640  # 20 ms
START_FRAMES = 12  # 240 ms consecutive speech
END_FRAMES = 35    # 700 ms trailing silence
MAX_FRAMES = 1500  # 30 seconds
PRE_FRAMES = 15    # 300 ms before speech is confirmed


class LocalTurns:
    def __init__(self):
        self.reset()

    def reset(self):
        self._tail = bytearray()
        self._pre = deque(maxlen=PRE_FRAMES)
        self._frames = []
        self._voice = 0
        self._quiet = 0
        self._drop = False

    @staticmethod
    def _voiced(frame):
        samples = struct.unpack("<320h", frame)
        rms = math.sqrt(sum(s * s for s in samples) / len(samples))
        return rms >= 500

    def feed(self, data: bytes):
        """Yield complete utterances; discard overlong capture until silence."""
        self._tail.extend(data)
        offset = 0
        while len(self._tail) - offset >= FRAME_BYTES:
            frame = bytes(self._tail[offset:offset + FRAME_BYTES])
            offset += FRAME_BYTES
            voice = self._voiced(frame)
            if self._drop:
                self._quiet = 0 if voice else self._quiet + 1
                if self._quiet >= END_FRAMES:
                    self._drop = False
                    self._quiet = 0
                continue
            if not self._frames:
                self._pre.append(frame)
                self._voice = self._voice + 1 if voice else 0
                if self._voice >= START_FRAMES:
                    self._frames = list(self._pre)
                    self._pre.clear()
                    self._quiet = 0
                continue
            self._frames.append(frame)
            self._quiet = 0 if voice else self._quiet + 1
            if self._quiet >= END_FRAMES:
                clip = b"".join(self._frames)
                self._frames = []
                self._voice = self._quiet = 0
                yield clip
            elif len(self._frames) >= MAX_FRAMES:
                self._frames = []
                self._pre.clear()
                self._voice = self._quiet = 0
                self._drop = True
        del self._tail[:offset]
