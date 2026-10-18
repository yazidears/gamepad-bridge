"""Read-only Wii U GamePad report decoder, following Barista's GPL-2.0 parser.

Does not inject mouse/keyboard events. Default factory touch calibration is
used until physical calibration is checked; no EEPROM payload is persisted.
"""
import struct
def decode(report):
 if len(report)!=128:raise ValueError('expected 128-byte input report')
 button_bits=(report[80]<<16)|(report[2]<<8)|report[3]
 sticks=struct.unpack_from('<4H',report,6)
 raw_x=sum(((report[37+i*4]&15)<<8)|report[36+i*4] for i in range(10))//10
 raw_y=sum(((report[39+i*4]&15)<<8)|report[38+i*4] for i in range(10))//10
 pressure=sum(((report[37+i*4]>>4)&7)<<(i*3) for i in range(4))
 x=max(0,min(853,20+(raw_x-195)*814/3682))
 y=max(0,min(479,20+(raw_y-3818)*440/-3445))
 return {'sequence':int.from_bytes(report[:2],'big'),'buttons':button_bits,'sticks':sticks,'touch':{'pressed':bool(pressure),'x':round(x,2),'y':round(y,2)},'waiting':bool(report[83]&1)}
