import unittest,struct
from input_report import decode
class InputTests(unittest.TestCase):
 def test_buttons_sticks(self):
  b=bytearray(128);b[:4]=bytes.fromhex('12348001');b[80]=2;struct.pack_into('<4H',b,6,2000,2100,1900,2200)
  d=decode(b);self.assertEqual(d['sequence'],0x1234);self.assertEqual(d['buttons'],0x028001);self.assertEqual(d['sticks'],(2000,2100,1900,2200));self.assertFalse(d['touch']['pressed'])
 def test_touch_default_calibration(self):
  b=bytearray(128)
  for i in range(10):struct.pack_into('<HH',b,36+i*4,195,3818)
  b[37]|=0x10
  d=decode(b);self.assertTrue(d['touch']['pressed']);self.assertEqual((d['touch']['x'],d['touch']['y']),(20,20))
 def test_invalid_length(self):
  with self.assertRaises(ValueError):decode(b'')
