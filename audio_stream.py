"""Bounded, live-only PCM transport over the existing authenticated GamePad relay.

Wire layout: https://garyodernichts.github.io/libdrc/docs/re/sc-astrm.html
48 kHz stereo signed little-endian 16-bit PCM. No audio is saved to disk.
"""
import collections
import json
import os
import pathlib
import socket
import struct
import threading
import time

FRAMES = 240
PCM_BYTES = FRAMES * 4
INTERVAL = FRAMES / 48000


def packet(pcm, sequence, stamp):
    if len(pcm) != PCM_BYTES:
        raise ValueError('Expected one 5 ms stereo PCM block')
    return bytes([0x20 | ((sequence >> 8) & 3), sequence & 255]) + struct.pack('>H', len(pcm)) + struct.pack('<I', stamp & 0xffffffff) + pcm


class Audio:
    def __init__(self, send, wrap, clock, directory):
        self.send, self.wrap, self.clock = send, wrap, clock
        self.directory = pathlib.Path(directory)
        self.path = self.directory / 'audio-input.sock'
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.path.unlink(missing_ok=True)
        self.sock.bind(str(self.path)); os.chmod(self.path, 0o600)
        self.sock.setblocking(False)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        pending = collections.deque(maxlen=12)  # At most 60 ms; never replay stale sound.
        sequence = sent = nonzero = dropped = 0
        last_input = 0
        due = report = time.monotonic()
        while not self.stop.is_set():
            while True:
                try:
                    pcm = self.sock.recv(PCM_BYTES + 1)
                except BlockingIOError:
                    break
                except OSError:
                    return
                if len(pcm) == PCM_BYTES:
                    if len(pending) == pending.maxlen: dropped += 1
                    pending.append(pcm); last_input = time.monotonic()
            now = time.monotonic()
            anchor = self.clock()
            if anchor and now-last_input < .5:
                pcm = pending.popleft() if pending else bytes(PCM_BYTES)
                host, tsf = anchor
                stamp = tsf + int((now-host)*1e6)
                try:
                    self.send(self.wrap(packet(pcm, sequence, stamp), 50021, 50121))
                except OSError:
                    return
                sequence = (sequence+1) & 1023
                sent += 1
                if any(pcm): nonzero += 1
            else:
                pending.clear()
            if now-report > 2:
                path = self.directory / 'audio-status.json'
                path.write_text(json.dumps({'packets':sent,'nonzeroPackets':nonzero,'droppedBlocks':dropped,'clockReady':anchor is not None,'sourceActive':now-last_input < .5}))
                os.chmod(path, 0o600); report = now
            due += INTERVAL
            if due < now-INTERVAL:
                # A late worker discards elapsed slots instead of sending an audible burst.
                due = now+INTERVAL
            self.stop.wait(max(0, due-time.monotonic()))

    def close(self):
        self.stop.set(); self.thread.join(timeout=1)
        self.sock.close(); self.path.unlink(missing_ok=True)
