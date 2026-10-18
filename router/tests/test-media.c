#include "media.h"
#include <assert.h>
#include <stdio.h>
static media_state m;
static unsigned formats,packets,acks;static uint8_t first[32];static uint32_t ack_id;
static void emit(void *c,const uint8_t *b,size_t n,uint16_t port){
 (void)c;if(port==50121){assert(n==32);formats++;assert(b[0]==4);}
 else {assert(port==50120);assert(n>=17&&n<=1710);if(!packets)memcpy(first,b,n<32?n:32);packets++;}
}
static void ack(void *c,uint32_t id){(void)c;acks++;ack_id=id;}
int main(void){
 m.emit=emit;m.ack=ack;m.clock_at=1000000;m.clock_tsf=2000000;
 uint8_t frame[30]={'G','P','F','1',1};for(int i=0;i<5;i++){media_put32(frame+5+i*5,1);frame[9+i*5]='a'+i;}
 assert(!media_accept(&m,frame,29,7,1000000));assert(!m.pending_valid);
 assert(media_accept(&m,frame,30,7,1000000));media_tick(&m,1000000);
 assert(formats==1&&acks==1&&ack_id==7);assert(m.count==1&&!m.pending_valid);
 assert(media_next(&m,1000000)==1005000);
 media_tick(&m,1004999);assert(!packets);
 media_tick(&m,1005000);assert(packets==1&&first[0]==0xf0&&first[1]==0&&first[2]==0xe8);
 assert(first[4]==0&&first[5]==0x1e&&first[6]==0x7f&&first[7]==0x9e);
 assert(first[8]==0x80&&first[9]==0x82&&first[16]=='a');
 assert(media_accept(&m,frame,30,7,1005100));assert(acks==2&&!m.pending_valid);
 frame[4]=0;assert(media_accept(&m,frame,30,8,1005100));media_tick(&m,1016000);assert(packets==5&&m.count==0);
 media_tick(&m,1016683);assert(formats==2&&m.pending_valid&&acks==2);
 media_tick(&m,1033366);assert(formats==3&&!m.pending_valid&&acks==3&&ack_id==8);
 uint8_t invalid[30];memcpy(invalid,frame,30);memset(invalid+5,255,4);assert(!media_accept(&m,invalid,30,9,1033367));
 m.pending_valid=0;assert(!media_fragment(&m,frame,30,9,30,1,1033367));assert(media_fragment(&m,frame,30,9,30,0,1033367));assert(m.pending_valid);
 assert(media_next(&m,3000001)==3200001);
 /* Every recovery IDR resets decoder row state, matching upstream policy. */
 m.clock_at=4000000;m.clock_tsf=5000000;m.count=0;m.head=0;m.pending_valid=0;m.gap=0;m.active=0;m.initialized=1;
 frame[4]=1;assert(media_accept(&m,frame,30,20,4000000));media_tick(&m,4000000);
 assert(m.jobs[m.head].idr&&m.jobs[m.head].init);
 packets=0;media_tick(&m,4005000);assert((first[2]&0x80)!=0);
 media_tick(&m,4018000);
 m.count=0;m.pending_valid=0;m.gap=0;m.active=0;
 frame[4]=0;assert(media_accept(&m,frame,30,21,4100000));media_tick(&m,4100000);
 assert(!m.jobs[m.head].idr&&!m.jobs[m.head].init);
 /* A long scheduler pause skips old slots without moving the slot grid or
  * emitting a burst. Existing encoded video remains queued, never dropped. */
 m.clock_at=5000000;m.clock_tsf=6000000;m.count=0;m.pending_valid=0;m.active=1;m.next_format=5000000;
 unsigned before=formats;media_tick(&m,5040000);
 assert(formats==before+1&&m.next_format==5050049&&m.format_skips==2);
 before=formats;media_tick(&m,5050048);assert(formats==before);
 media_tick(&m,5050049);assert(formats==before+1&&m.next_format==5066732);
 puts("Native media bounds, packet flags, clock, deadlines, duplicate ACK and IDR gap PASS");
}
