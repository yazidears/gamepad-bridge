import struct
import unittest
from audio_stream import packet, PCM_BYTES


class AudioTests(unittest.TestCase):
    def test_known_stereo_wire_header_and_sample_integrity(self):
        pcm = struct.pack('<hh', -16384, 16384) * 240
        wire = packet(pcm, 1023, 0x12345678)
        self.assertEqual(wire[:8], bytes.fromhex('23ff03c078563412'))
        self.assertEqual(wire[8:], pcm)
        self.assertEqual(len(wire), 968)  # Relay envelope fits Ethernet MTU.

    def test_sequence_and_clock_wrap_without_corrupting_format(self):
        wire = packet(bytes(PCM_BYTES), 1024, 0x100000001)
        self.assertEqual(wire[:8], bytes.fromhex('200003c001000000'))

    def test_partial_pcm_is_rejected(self):
        with self.assertRaises(ValueError): packet(bytes(PCM_BYTES-1), 0, 0)
