import unittest,importlib.util,pathlib,struct
p=pathlib.Path(__file__).with_name('startup-service.py');sp=importlib.util.spec_from_file_location('startup',p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
class ProtocolTests(unittest.TestCase):
 def request(self,kind=1):
  b=bytearray(240);b[:3]=b'\1\1\6';b[4:8]=bytes.fromhex('01020304');b[28:34]=m.GP;b[236:]=bytes.fromhex('63825363');return b+bytes([53,1,kind,255])
 def test_dhcp_discover_and_request(self):
  for req,reply in [(1,2),(3,5)]:
   kind,frame=m.dhcp_reply(self.request(req));self.assertEqual(kind,reply);self.assertEqual(m.checksum(frame[14:34]),0);self.assertEqual(frame[46:50],bytes.fromhex('01020304'));self.assertIn(bytes([53,1,reply]),frame);self.assertIn(bytes([26,2,7,8]),frame)
 def test_truncated_options_rejected(self):self.assertIsNone(m.dhcp_reply(self.request()[:-2]))
 def test_unknown_client_rejected(self):
  b=self.request();b[28]^=1;self.assertIsNone(m.dhcp_reply(b))
 def test_arp_reply_uses_isolated_addresses(self):
  request=m.BCAST+m.GP+b'\x08\x06'+b'\0\1\x08\0\6\4\0\1'+m.GP+m.CLIENT+b'\0'*6+m.SERVER
  response=m.arp_reply(request);self.assertIsNotNone(response);self.assertEqual(response[20:22],b'\0\2');self.assertEqual(response[28:32],m.SERVER);self.assertEqual(response[38:42],m.CLIENT)
 def test_command_header_little_endian(self):self.assertEqual(m.command(3,1,0x1234),bytes.fromhex('0300010000003412'))
if __name__=='__main__':unittest.main()
