#!/usr/bin/env python3
"""Experimental, isolated GamePad DHCP/ARP and DRC startup over a private L2 relay.
Wire layouts follow Barista's GPL-2.0 runtime_transport/backend_linux implementation.
No system route, address, DHCP configuration, or packet payload log is created.
"""
import socket,struct,pathlib,time,collections,json,os,sys,fcntl
AP=bytes.fromhex('020000000001'); GP=bytes.fromhex('020000000002'); BCAST=b'\xff'*6
SERVER=socket.inet_aton('192.168.1.10'); CLIENT=socket.inet_aton('192.168.1.11'); BROAD=socket.inet_aton('192.168.1.255')
def checksum(b):
 if len(b)%2:b+=b'\0'
 s=sum(struct.unpack('!%dH'%(len(b)//2),b))
 while s>>16:s=(s&65535)+(s>>16)
 return (~s)&65535
def udp_frame(payload,sport,dport,dip=CLIENT,dmac=None):
 if dmac is None:dmac=GP
 udp=struct.pack('!HHHH',sport,dport,8+len(payload),0)+payload
 ip=bytearray(struct.pack('!BBHHHBBH4s4s',0x45,0xa0,20+len(udp),0,0,64,17,0,SERVER,dip));struct.pack_into('!H',ip,10,checksum(ip))
 return dmac+AP+b'\x08\x00'+ip+udp
def parse_udp(frame):
 if len(frame)<42 or frame[6:12]!=GP or frame[12:14]!=b'\x08\x00':return None
 ip=frame[14:];ihl=(ip[0]&15)*4
 if ip[0]>>4!=4 or ihl<20 or len(ip)<ihl+8 or ip[9]!=17:return None
 total=struct.unpack_from('!H',ip,2)[0]
 if total<ihl+8 or len(ip)<total or checksum(ip[:ihl])!=0:return None
 if struct.unpack_from('!H',ip,6)[0]&0x3fff:return None
 sport,dport,n,_=struct.unpack_from('!HHHH',ip,ihl)
 if n<8 or ihl+n>total:return None
 return sport,dport,ip[ihl+8:ihl+n]
def dhcp_reply(data):
 if len(data)<240 or data[:3]!=b'\1\1\6' or data[236:240]!=b'\x63\x82\x53\x63' or data[28:34]!=GP:return None
 mt=None;i=240
 while i<len(data):
  code=data[i];i+=1
  if code==255:break
  if code==0:continue
  if i>=len(data):return None
  n=data[i];i+=1
  if i+n>len(data):return None
  if code==53 and n==1:mt=data[i]
  i+=n
 if mt not in (1,3):return None
 kind=2 if mt==1 else 5
 out=bytearray(240);out[:3]=b'\2\1\6';out[4:12]=data[4:12];out[16:20]=CLIENT;out[20:24]=SERVER;out[28:44]=data[28:44];out[236:240]=data[236:240]
 opts=[(53,bytes([kind])),(54,SERVER),(51,struct.pack('!I',3600)),(1,b'\xff\xff\xff\0'),(3,SERVER),(28,BROAD),(26,struct.pack('!H',1800))]
 for c,b in opts:out.extend(bytes([c,len(b)])+b)
 out.append(255)
 return kind,udp_frame(out,67,68,BROAD,BCAST)
def arp_reply(frame):
 if len(frame)<42 or frame[6:12]!=GP or frame[12:14]!=b'\x08\x06':return None
 b=frame[14:42]
 if b[:8]!=b'\0\1\x08\0\6\4\0\1' or b[8:14]!=GP or b[24:28]!=SERVER:return None
 return (GP+AP+b'\x08\x06'+b'\0\1\x08\0\6\4\0\2'+AP+SERVER+GP+b[14:18]).ljust(60,b'\0')
def command(kind,query,seq,payload=b''):return struct.pack('<4H',kind,query,len(payload),seq)+payload
class Service:
 def __init__(self,send):
  self.send=send;self.count=collections.Counter();self.uic=False;self.uvc=False;self.input=False;self.waiting=None;self.last_input=0;self.resync=None;self.input_callback=None;self.seq=2;self.qseq=1;self.last=0;self.uac=bytearray(48);struct.pack_into('<H',self.uac,12,16000)
 def receive(self,frame):
  a=arp_reply(frame)
  if a:self.send(a);self.count['arp_replies']+=1;return
  p=parse_udp(frame)
  if not p:return
  sport,dport,data=p;self.count['udp_to_'+str(dport)]+=1
  if sport==68 and dport==67:
   reply=dhcp_reply(data)
   if reply:
    kind,b=reply;self.send(b);self.count['dhcp_offer' if kind==2 else 'dhcp_ack']+=1;print('DHCP OFFER sent' if kind==2 else 'DHCP ACK sent',flush=True)
  elif dport==50022 and len(data)==128:
   self.count['gamepad_volume_byte']=data[14]
   if self.input_callback:self.input_callback(data)
   if not self.input:print('GamePad input received',flush=True)
   self.input=True;self.last_input=time.monotonic()
   waiting=bool(data[83]&1)
   if waiting!=self.waiting:print('GamePad waiting for stream: '+str(waiting),flush=True);self.waiting=waiting
  elif dport==50010 and data==b'\1\0\0\0':
   self.count['idr_requests']+=1
   if self.resync:self.resync()
  elif dport==50023 and len(data)>=8:
   kind,q,n,seq=struct.unpack_from('<4H',data)
   if len(data)!=8+n or kind>3 or q>2:return
   if kind==2:
    self.send(udp_frame(command(3,q,seq),50023,50123));reply=data[8:]
    if q==0 and n==784 and reply[:2]==b'\x7e\1':
     if not self.uic:print('UIC configuration reply received (payload not logged)',flush=True)
     self.uic=True
    if q==1 and n==16:
     if not self.uvc:print('UVC/UAC startup reply received',flush=True)
     self.uvc=True;self.uac[0]=1;self.uac[4]=bool(reply[12]);self.uac[6:10]=reply[:4];self.uac[16]=reply[13];self.uac[17]=bool(reply[14]);self.qseq=self.seq;self.seq=(self.seq+1)&65535
 def tick(self,now):
  if now-self.last<1:return
  self.last=now
  if not self.uic:self.send(udp_frame(command(0,0,0,bytes.fromhex('7e0100080040050600000000')),50023,50123))
  self.send(udp_frame(command(0,1,self.qseq,self.uac),50023,50123))
def main():
 import argparse
 parser=argparse.ArgumentParser(description='Stream the Mac desktop to a paired Wii U GamePad.')
 parser.add_argument('--router',required=True,help='Router IP address (relay UDP port 55560)')
 parser.add_argument('--token',type=pathlib.Path,required=True,help='32-byte local relay token file')
 parser.add_argument('--ap-mac',required=True)
 parser.add_argument('--gamepad-mac',required=True)
 parser.add_argument('--bind',default='0.0.0.0',help='Local address reachable by the router')
 parser.add_argument('--state-dir',type=pathlib.Path,default=pathlib.Path.home()/'.local/state/gamepad-bridge')
 parser.add_argument('--input-json',action='store_true',help='Print decoded input reports; no keyboard/mouse injection')
 args=parser.parse_args()
 def mac(value):
  raw=bytes.fromhex(value.replace(':',''))
  if len(raw)!=6:parser.error('MAC addresses must contain six bytes')
  return raw
 global AP,GP
 AP=mac(args.ap_mac);GP=mac(args.gamepad_mac)
 os.umask(0o077)
 base=pathlib.Path(__file__).resolve().parent
 state=args.state_dir.expanduser();state.mkdir(parents=True,mode=0o700,exist_ok=True)
 token=args.token.expanduser().read_bytes()
 if len(token)!=32:parser.error('Token must be exactly 32 bytes')
 lock=(state/'session.lock').open('a')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:parser.error('A session already owns this state directory')
 os.environ['GAMEPAD_STATE_DIR']=str(state)
 s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind((args.bind,0));s.connect((args.router,55560));s.settimeout(.02)
 def send(frame):s.send(b'GPR1\4'+token+frame)
 from video_stream import Video
 video=Video(send,udp_frame,base)
 from audio_stream import Audio
 audio=Audio(send,udp_frame,lambda:video.radio_clock,state)
 video.desktop=True
 video.router_send=lambda frame:s.send(b'GPR1\6'+token+frame)
 service=Service(send);hello=0;report=0;start=time.monotonic();linked=False;hello_wall=0;best_rtt=1e9;offset=None;radio_clock=None;video_started=False;relay_last=start
 if args.input_json:
  from input_report import decode
  service.input_callback=lambda report:print(json.dumps({'input':decode(report)}),flush=True)
 service.resync=video.recover.set
 audio_capture=None;audio_log=None
 print('Mac startup service ready; waiting for authenticated L2 relay',flush=True)
 try:
  if (base/'audio-capture').is_file():
   import subprocess
   audio_log=(state/'audio-capture.log').open('w');os.chmod(state/'audio-capture.log',0o600)
   audio_capture=subprocess.Popen([str(base/'audio-capture'),str(state)],stdin=subprocess.DEVNULL,stdout=audio_log,stderr=subprocess.STDOUT)
  lifetime=int(os.environ.get('GAMEPAD_SESSION_SECONDS','0'))
  while not lifetime or time.monotonic()-start<lifetime:
   now=time.monotonic()
   if now-start>12 and now-relay_last>8:
    print('Authenticated relay heartbeat lost; requesting session recovery.',flush=True);break
   if video_started and video.thread and not video.thread.is_alive():
    print('Capture sender stopped; closing the managed session.',flush=True);break
   if now-hello>1:s.send(b'GPR1\1'+token);hello=now;hello_wall=time.time()
   if linked:service.tick(now)
   try:b=s.recv(4096)
   except (socket.timeout,ConnectionRefusedError):continue
   if len(b)<37 or b[:4]!=b'GPR1' or b[5:37]!=token:continue
   relay_last=time.monotonic()
   if b[4]==2:
    if not linked:print('Authenticated router relay connected',flush=True)
    linked=True
    if len(b)==45:
     rtt=time.monotonic()-hello
     if rtt<best_rtt:best_rtt=rtt;offset=(hello_wall+time.time())/2-struct.unpack_from('<Q',b,37)[0]/1e6
   elif b[4]==3:service.receive(b[37:])
   elif b[4]==5 and len(b)==53 and offset is not None:
    tsf,remote=struct.unpack_from('<QQ',b,37);age=time.time()-(remote/1e6+offset)
    if tsf and -.05<age<.1:radio_clock=(time.monotonic()-age,tsf);video.radio_clock=radio_clock
   elif b[4]==7 and len(b)==41:video.acknowledge(struct.unpack_from('<I',b,37)[0])
   if not video_started and radio_clock and service.uvc and now-service.last_input<1 and best_rtt<.05:
    print(json.dumps({'clock_calibration_rtt_ms':round(best_rtt*1000,2)}),flush=True)
    video.start(radio_clock);video_started=True
   if now-report>5:
    print(json.dumps({'counts':dict(service.count),'input':service.input,'uic':service.uic,'uvc':service.uvc}),flush=True);report=now
 finally:
  if audio_capture and audio_capture.poll() is None:
   audio_capture.terminate()
   try:audio_capture.wait(timeout=2)
   except subprocess.TimeoutExpired:audio_capture.kill();audio_capture.wait()
  if audio_log:audio_log.close()
  video.stop.set()
  if video.thread:video.thread.join(timeout=5)
  audio.close();s.close()
if __name__=='__main__':
 try:main()
 except KeyboardInterrupt:pass
