#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <linux/if_packet.h>
#include <linux/filter.h>
#include <net/ethernet.h>
#include <net/if.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
#include "media.h"
#include "clock-filter.h"
#include "clock-anchor.h"
static volatile sig_atomic_t running=1;
static void stop(int s){(void)s;running=0;}
static int parse_mac(const char *s,uint8_t m[6]){unsigned x[6];int consumed=0;if(strlen(s)!=17||sscanf(s,"%2x:%2x:%2x:%2x:%2x:%2x%n",x,x+1,x+2,x+3,x+4,x+5,&consumed)!=6||consumed!=17)return -1;for(int i=0;i<6;i++)m[i]=(uint8_t)x[i];return 0;}
static int eth_allowed(const uint8_t *b,size_t n){return n>=14&&((b[12]==8&&b[13]==0)||(b[12]==8&&b[13]==6));}
static uint64_t micros(clockid_t clock){struct timespec t;clock_gettime(clock,&t);return (uint64_t)t.tv_sec*1000000+t.tv_nsec/1000;}
static void le64(uint8_t *p,uint64_t v){for(int i=0;i<8;i++)p[i]=(uint8_t)(v>>(i*8));}
static uint32_t rd32(const uint8_t *p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
typedef struct {int raw,udp;unsigned idx;struct sockaddr_in *peer;uint8_t *envelope;uint8_t gm[6],am[6];} emit_context;
static media_state media;
static void emit_media(void *context,const uint8_t *data,size_t n,uint16_t port){
 emit_context *c=context;uint8_t frame[1800]={0};const uint8_t *gp=c->gm,*ap=c->am;
 memcpy(frame,gp,6);memcpy(frame+6,ap,6);frame[12]=8;
 uint8_t *ip=frame+14;size_t len=n+28;ip[0]=0x45;ip[1]=0xa0;ip[2]=len>>8;ip[3]=len;ip[8]=64;ip[9]=17;
 ip[12]=ip[16]=192;ip[13]=ip[17]=168;ip[14]=ip[18]=1;ip[15]=10;ip[19]=11;
 unsigned sum=0;for(int i=0;i<20;i+=2)sum+=(ip[i]<<8)|ip[i+1];while(sum>>16)sum=(sum&65535)+(sum>>16);sum=~sum;ip[10]=sum>>8;ip[11]=sum;
 uint16_t source=port-100;uint8_t *udp=ip+20;udp[0]=source>>8;udp[1]=source;udp[2]=port>>8;udp[3]=port;udp[4]=(n+8)>>8;udp[5]=n+8;memcpy(udp+8,data,n);
 struct sockaddr_ll dest={.sll_family=AF_PACKET,.sll_ifindex=(int)c->idx,.sll_halen=6};memcpy(dest.sll_addr,gp,6);
 if(sendto(c->raw,frame,n+42,0,(struct sockaddr*)&dest,sizeof(dest))<0){perror("native media send");running=0;}
}
static void ack_media(void *context,uint32_t id){emit_context *c=context;c->envelope[4]=7;media_put32(c->envelope+37,id);sendto(c->udp,c->envelope,41,0,(struct sockaddr*)c->peer,sizeof(*c->peer));}
int main(int argc,char **argv){
 if(argc<6||argc>9){fprintf(stderr,"Usage: %s IFACE TOKEN_FILE GAMEPAD_MAC AP_MAC CLIENT_IP [LIFETIME_SECONDS] [CLOCK_IFACE] [BEACON_BSSID]\n",argv[0]);return 2;}
 unsigned long lifetime=1800;
 if(argc>=7){char *end;errno=0;lifetime=strtoul(argv[6],&end,10);if(errno||*end||lifetime>86400)return 2;}
 uint8_t token[32],gm[6],am[6];
 FILE *f=fopen(argv[2],"rb");if(!f||fread(token,1,32,f)!=32)return 3;fclose(f);if(parse_mac(argv[3],gm)||parse_mac(argv[4],am))return 4;
 struct in_addr allowed;if(inet_pton(AF_INET,argv[5],&allowed)!=1)return 4;
 struct sock_filter clock_filter[CLOCK_FILTER_LENGTH];uint8_t beacon[6];memcpy(beacon,am,6);if(argc==9&&parse_mac(argv[8],beacon))return 4;make_clock_filter(clock_filter,beacon);
 unsigned idx=if_nametoindex(argv[1]);if(!idx)return 5;
 int raw=socket(AF_PACKET,SOCK_RAW,htons(ETH_P_ALL));if(raw<0)return 6;
 struct sockaddr_ll link={.sll_family=AF_PACKET,.sll_protocol=htons(ETH_P_ALL),.sll_ifindex=(int)idx};
 if(bind(raw,(struct sockaddr*)&link,sizeof(link)))return 7;
 unsigned mi=if_nametoindex(argc>=8?argv[7]:"gp-clock0");int mon=-1;
 if(mi){mon=socket(AF_PACKET,SOCK_RAW,htons(ETH_P_ALL));struct sockaddr_ll ml={.sll_family=AF_PACKET,.sll_protocol=htons(ETH_P_ALL),.sll_ifindex=(int)mi};if(bind(mon,(struct sockaddr*)&ml,sizeof(ml))){close(mon);mon=-1;}else{int on=1;setsockopt(mon,SOL_SOCKET,SO_TIMESTAMPNS,&on,sizeof(on));struct sock_fprog filter={.len=sizeof(clock_filter)/sizeof(clock_filter[0]),.filter=(struct sock_filter*)clock_filter};if(setsockopt(mon,SOL_SOCKET,SO_ATTACH_FILTER,&filter,sizeof(filter))){perror("clock filter");return 9;}}}
 int udp=socket(AF_INET,SOCK_DGRAM,0);struct sockaddr_in local={.sin_family=AF_INET,.sin_port=htons(55560)};
 if(bind(udp,(struct sockaddr*)&local,sizeof(local)))return 8;
 int buffer=262144;setsockopt(raw,SOL_SOCKET,SO_RCVBUF,&buffer,sizeof(buffer));setsockopt(udp,SOL_SOCKET,SO_RCVBUF,&buffer,sizeof(buffer));
 struct sockaddr_in peer={0};time_t last=0,start=time(NULL),report=start;
 signal(SIGTERM,stop);signal(SIGINT,stop);setvbuf(stdout,NULL,_IOLBF,0);puts("RAW_PROXY_READY");
 unsigned long rx=0,tx=0,rejected=0;uint8_t b[65536],packet[4133];
 memcpy(packet,"GPR1",4);memcpy(packet+5,token,32);
 emit_context output={.raw=raw,.udp=udp,.idx=idx,.peer=&peer,.envelope=packet};memcpy(output.gm,gm,6);memcpy(output.am,am,6);media.emit=emit_media;media.ack=ack_media;media.context=&output;
 uint64_t last_clock=0;
 while(running&&(!lifetime||(unsigned long)(time(NULL)-start)<lifetime)){
  uint64_t mono=micros(CLOCK_MONOTONIC);if(time(NULL)-last<10)media_tick(&media,mono);
  mono=micros(CLOCK_MONOTONIC);uint64_t due=time(NULL)-last<10?media_next(&media,mono):mono+200000,delay=due>mono?due-mono:0;if(delay>200000)delay=200000;
  struct timespec timeout={.tv_sec=delay/1000000,.tv_nsec=(delay%1000000)*1000};
  struct pollfd p[3]={{raw,POLLIN,0},{udp,POLLIN,0},{mon,POLLIN,0}};int ready=ppoll(p,3,&timeout,NULL);if(ready<0){if(errno==EINTR)continue;break;}
  if(p[1].revents&POLLIN){struct sockaddr_in from;socklen_t fl=sizeof(from);ssize_t n=recvfrom(udp,b,sizeof(b),0,(struct sockaddr*)&from,&fl);
   if(n<37||memcmp(b,"GPR1",4)||memcmp(b+5,token,32)||from.sin_addr.s_addr!=allowed.s_addr){rejected++;continue;}
   peer=from;last=time(NULL);
   if(b[4]==1){packet[4]=2;le64(packet+37,micros(CLOCK_REALTIME));sendto(udp,packet,45,0,(struct sockaddr*)&peer,sizeof(peer));}
   else if(b[4]==6&&n>=45){size_t total=b[41]|(b[42]<<8),offset=b[43]|(b[44]<<8);if(!media_fragment(&media,b+45,(size_t)n-45,rd32(b+37),total,offset,micros(CLOCK_MONOTONIC)))rejected++;}
   else if(b[4]==4&&eth_allowed(b+37,(size_t)n-37)&&!memcmp(b+43,am,6)&&(!memcmp(b+37,gm,6)||!memcmp(b+37,"\xff\xff\xff\xff\xff\xff",6))){
    struct sockaddr_ll dest={.sll_family=AF_PACKET,.sll_ifindex=(int)idx,.sll_halen=6};memcpy(dest.sll_addr,b+37,6);
    if(sendto(raw,b+37,(size_t)n-37,0,(struct sockaddr*)&dest,sizeof(dest))>=0)tx++;else rejected++;
   }
  }
  if(p[0].revents&POLLIN){struct sockaddr_ll from;socklen_t fl=sizeof(from);ssize_t n=recvfrom(raw,b,sizeof(b),0,(struct sockaddr*)&from,&fl);
   if(n>=14&&n<=2048&&from.sll_pkttype!=PACKET_OUTGOING&&eth_allowed(b,(size_t)n)&&!memcmp(b+6,gm,6)&&peer.sin_port&&time(NULL)-last<10){packet[4]=3;memcpy(packet+37,b,(size_t)n);sendto(udp,packet,(size_t)n+37,0,(struct sockaddr*)&peer,sizeof(peer));rx++;}
  }
  if(mon>=0&&(p[2].revents&POLLIN)){
   uint8_t control[128];struct iovec io={b,sizeof(b)};struct msghdr msg={.msg_iov=&io,.msg_iovlen=1,.msg_control=control,.msg_controllen=sizeof(control)};
   ssize_t n=recvmsg(mon,&msg,0);
   uint64_t mono_before=micros(CLOCK_MONOTONIC),now=micros(CLOCK_REALTIME),mono_after=micros(CLOCK_MONOTONIC),received=now;
   for(struct cmsghdr *c=CMSG_FIRSTHDR(&msg);c;c=CMSG_NXTHDR(&msg,c))if(c->cmsg_level==SOL_SOCKET&&c->cmsg_type==SCM_TIMESTAMPNS){struct timespec *t=(void*)CMSG_DATA(c);received=(uint64_t)t->tv_sec*1000000+t->tv_nsec/1000;}
   if(n>=16&&b[0]==0&&(rd32(b+4)&1)&&now-last_clock>50000&&peer.sin_port&&time(NULL)-last<10){
    unsigned off=4;uint32_t present;do{if(off+4>(unsigned)n)break;present=rd32(b+off);off+=4;}while(present&0x80000000);off=(off+7)&~7;
    unsigned h=b[2]|(b[3]<<8);
    if(off+8<=h&&h<=(unsigned)n){packet[4]=5;memcpy(packet+37,b+off,8);le64(packet+45,received);sendto(udp,packet,53,0,(struct sockaddr*)&peer,sizeof(peer));last_clock=now;
     uint64_t tsf=0;for(int j=7;j>=0;j--)tsf=(tsf<<8)|b[off+j];
     uint64_t anchor;
     if(receive_clock_anchor(received,now,mono_before,mono_after,&anchor)){media.clock_tsf=tsf;media.clock_at=anchor;}
    }
   }
  }
  if(time(NULL)-report>=5){printf("frames_from_gamepad=%lu frames_to_gamepad=%lu rejected=%lu native_formats=%lu native_frames=%lu late_packets=%lu max_late_us=%llu format_skips=%lu format_max_late_us=%llu\n",rx,tx,rejected,media.formats,media.frames,media.late,(unsigned long long)media.max_late,media.format_skips,(unsigned long long)media.format_max_late);report=time(NULL);}
 }
 if(mon>=0)close(mon);close(raw);close(udp);return 0;
}
