"""Desktop GamePad transport using the router media scheduler (GPL-2.0)."""
import struct, pathlib, time, threading, json, subprocess, os, select

class LiveSource:
 def __init__(self,base,stop):
  self.stop=stop
  self.log=(pathlib.Path(os.environ['GAMEPAD_STATE_DIR'])/'capture.log').open('w')
  binary='mac-capture'
  self.proc=subprocess.Popen([str(base/binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,bufsize=0)
  self.request(True)
 def request(self,idr):self.proc.stdin.write(b'I' if idr else b'P');self.proc.stdin.flush()
 def exact(self,n):
  b=bytearray();end=time.monotonic()+10
  while len(b)<n:
   if self.stop.is_set():raise RuntimeError('Capture stopped')
   if time.monotonic()>end:raise RuntimeError('display encoder timed out; see live-capture.log')
   ready,_,_=select.select([self.proc.stdout],[],[],.1)
   if not ready:continue
   part=os.read(self.proc.stdout.fileno(),n-len(b))
   if not part:raise RuntimeError('display encoder exited; see live-capture.log')
   b.extend(part)
  return bytes(b)
 def receive(self):
  h=self.exact(5)
  if h[:4]!=b'GPF1':raise RuntimeError('invalid encoder stream')
  chunks=[]
  for _ in range(5):
   n=struct.unpack('<I',self.exact(4))[0]
   if not 0<n<1000000:raise RuntimeError('invalid encoder chunk size')
   chunks.append(self.exact(n))
  return bool(h[4]),chunks
 def close(self):
  self.proc.terminate()
  try:self.proc.wait(timeout=3)
  except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()
  self.log.close()

def format_packet(stamp):
 b=bytearray.fromhex('040000001111810800000000803e0000803e0000085200000852000000000000')
 struct.pack_into('<I',b,8,stamp&0xffffffff);return b

def packets(chunks,stamp,seq,idr,init):
 starts=[0,3000,6000,9000,11000];ends=[2500,5000,7500,10000,13000];out=[]
 for ci,chunk in enumerate(chunks):
  pieces=[chunk[p:p+1694] for p in range(0,len(chunk),1694)]
  for pi,data in enumerate(pieces):
   first=ci==0 and pi==0;last=pi==len(pieces)-1
   flags=8|(128 if init else 0)|(64 if first else 0)|(32 if last else 0)|(16 if last and ci==4 else 0)|(len(data)>>8)
   head=bytes([0xf0|((seq>>8)&3),seq&255,flags,len(data)&255])+struct.pack('!I',stamp&0xffffffff)
   options=bytes.fromhex('8082008385060000' if idr else '8200838506000000')
   offset=starts[ci]+(ends[ci]-starts[ci])*pi/max(1,len(pieces)-1)
   out.append((offset/1e6,head+options+data));seq=(seq+1)&1023
 return seq,out

class Video:
 def __init__(self,send,wrap,base):
  self.send=send;self.wrap=wrap;self.base=base;self.stop=threading.Event();self.recover=threading.Event();self.thread=None;self.desktop=False;self.radio_clock=None;self.router_send=None;self.router_ack=threading.Event();self.router_id=0;self.router_last_ack=None
 def start(self,radio_clock=None):
  if self.thread and self.thread.is_alive():return
  if radio_clock:self.radio_clock=radio_clock
  self.thread=threading.Thread(target=self.run_router,daemon=True);self.thread.start()
 def acknowledge(self,frame_id):
  self.router_last_ack=frame_id
  if frame_id==self.router_id:self.router_ack.set()
 def run_router(self):
  source=None;number=0;started=time.monotonic();report=started;recovering=True
  try:
   source=LiveSource(self.base,self.stop)
   lifetime=int(os.environ.get('GAMEPAD_SESSION_SECONDS','0'))
   while not self.stop.is_set() and (not lifetime or time.monotonic()-started<lifetime):
    idr,chunks=source.receive()
    request_idr=number%60==59 or (self.recover.is_set() and not recovering)
    if request_idr:self.recover.clear();recovering=True
    source.request(request_idr)
    self.router_id=(self.router_id+1)&0xffffffff;self.router_ack.clear()
    payload=b'GPF1'+bytes([idr])+b''.join(struct.pack('<I',len(c))+c for c in chunks)
    if len(payload)>65000:raise RuntimeError('Encoded frame exceeds native relay limit')
    accepted=False
    for _ in range(3):
     for off in range(0,len(payload),1200):self.router_send(struct.pack('<IHH',self.router_id,len(payload),off)+payload[off:off+1200])
     if self.router_ack.wait(1):accepted=True;break
     if self.stop.is_set():break
    if not accepted:raise RuntimeError('Native router media acknowledgement timed out')
    if not idr and recovering:self.recover.clear();recovering=False
    number+=1
    if time.monotonic()-report>5:
     print(json.dumps({'native_router_frames':number,'seconds':round(time.monotonic()-started,1)}),flush=True);report=time.monotonic()
  except (OSError,RuntimeError) as error:print('Video sender stopped: '+str(error),flush=True)
  finally:
   if source:source.close()
