import unittest, struct, pathlib
from video_stream import format_packet,packets
class WireTests(unittest.TestCase):
 def test_format_reference(self):
  self.assertEqual(format_packet(0x12345678).hex(),'040000001111810878563412803e0000803e0000085200000852000000000000')
 def test_chunk_boundaries_sequence_and_endianness(self):
  seq,out=packets([b'a'*1695,b'b',b'c',b'd',b'e'],0x12345678,1022,True,True)
  self.assertEqual(seq,4);self.assertEqual(len(out),6)
  self.assertEqual(out[0][1][:16].hex(),'f3fece9e123456788082008385060000')
  self.assertEqual(out[1][0],.0025)
  self.assertEqual(out[1][1][2],0xa8)
  self.assertEqual(out[-1][1][2],0xb8)
  self.assertEqual(out[2][1][:2],b'\xf0\0')
  self.assertEqual(max(len(p) for _,p in out),1710)
 def test_predictive_options(self):
  _,out=packets([b'x']*5,0,0,False,False)
  self.assertEqual(out[0][1][8:16].hex(),'8200838506000000')
  self.assertEqual(out[0][1][2],0x68)
if __name__=='__main__':unittest.main()
