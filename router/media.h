/* DRC wire layouts and scheduling follow Barista (GPL-2.0). */
#ifndef GAMEPAD_MEDIA_H
#define GAMEPAD_MEDIA_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define MEDIA_MAX 65000
typedef struct {
 uint8_t bytes[MEDIA_MAX];size_t size,offset[5],length[5];uint32_t id,stamp;
 unsigned chunk,part;int idr,init;uint64_t start;
} media_frame;
typedef void (*media_emit_fn)(void*,const uint8_t*,size_t,uint16_t);
typedef void (*media_ack_fn)(void*,uint32_t);
typedef struct {
 media_frame pending,jobs[2];int pending_valid,head,count,active,gap,initialized;
 uint16_t sequence;uint64_t next_format,clock_at,clock_tsf;uint32_t last_id;int have_last;
 unsigned long formats,frames,packets,late,format_skips;uint64_t max_late,format_max_late;
 media_emit_fn emit;media_ack_fn ack;void *context;
 uint8_t assembly[MEDIA_MAX];uint32_t assembly_id;size_t assembly_size;uint64_t assembly_mask;
} media_state;
static uint32_t media_le32(const uint8_t *p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void media_put32(uint8_t *p,uint32_t v){for(int i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static int media_accept(media_state *m,const uint8_t *data,size_t n,uint32_t id,uint64_t now){
 if(m->have_last&&id==m->last_id){m->ack(m->context,id);return 1;}
 if(m->pending_valid)return id==m->pending.id;
 if(n<25||n>MEDIA_MAX||memcmp(data,"GPF1",4)||data[4]>1)return 0;
 size_t p=5,offsets[5],lengths[5];
 for(int i=0;i<5;i++){
  if(p+4>n)return 0;size_t len=media_le32(data+p);p+=4;
  if(!len||len>n-p)return 0;offsets[i]=p;lengths[i]=len;p+=len;
 }
 if(p!=n)return 0;
 media_frame *f=&m->pending;memcpy(f->bytes,data,n);f->size=n;f->id=id;f->idr=data[4];
 memcpy(f->offset,offsets,sizeof(offsets));memcpy(f->length,lengths,sizeof(lengths));
 f->chunk=f->part=0;m->pending_valid=1;
 if(!m->active){m->active=1;m->next_format=now;}
 return 1;
}
static int media_fragment(media_state *m,const uint8_t *data,size_t n,uint32_t id,size_t total,size_t offset,uint64_t now){
 if(total<30||total>MEDIA_MAX||offset>=total||offset%1200||n!=(total-offset>1200?1200:total-offset))return 0;
 if(m->have_last&&id==m->last_id){m->ack(m->context,id);return 1;}
 if(m->assembly_id!=id||m->assembly_size!=total){m->assembly_id=id;m->assembly_size=total;m->assembly_mask=0;}
 memcpy(m->assembly+offset,data,n);m->assembly_mask|=1ULL<<(offset/1200);
 uint64_t expected=(1ULL<<((total+1199)/1200))-1;
 if(m->assembly_mask==expected)return media_accept(m,m->assembly,total,id,now);
 return 1;
}
static uint64_t media_packet_due(const media_frame *f){
 static const int starts[5]={0,3000,6000,9000,11000},ends[5]={2500,5000,7500,10000,13000};
 size_t count=(f->length[f->chunk]+1693)/1694;
 return f->start+starts[f->chunk]+(count>1?(uint64_t)(ends[f->chunk]-starts[f->chunk])*f->part/(count-1):0);
}
static uint64_t media_next(const media_state *m,uint64_t now){
 if(!m->active||!m->clock_at||now<m->clock_at||now-m->clock_at>1000000)return now+200000;
 uint64_t next=m->next_format;
 if(m->count){uint64_t packet=media_packet_due(&m->jobs[m->head]);if(packet<next)next=packet;}
 return next;
}
static void media_tick(media_state *m,uint64_t now){
 if(!m->active||!m->clock_at||now<m->clock_at||now-m->clock_at>1000000)return;
 if(now>=m->next_format){
  uint64_t format_late=now-m->next_format;
  if(format_late>m->format_max_late)m->format_max_late=format_late;
  uint32_t stamp=(uint32_t)(m->clock_tsf+(now-m->clock_at)-1250);
  uint8_t format[32]={4,0,0,0,0x11,0x11,0x81,8,0,0,0,0,0x80,0x3e,0,0,0x80,0x3e,0,0,8,0x52,0,0,8,0x52,0,0,0,0,0,0};
  media_put32(format+8,stamp);m->emit(m->context,format,32,50121);m->formats++;
  int video=m->pending_valid&&!m->gap&&m->count<2;
  if(video){
   media_frame *f=&m->jobs[(m->head+m->count)%2];*f=m->pending;f->start=now+5000;f->stamp=stamp;f->init=!m->initialized||f->idr;
   m->count++;m->pending_valid=0;m->initialized=1;m->last_id=f->id;m->have_last=1;
   m->ack(m->context,f->id);m->gap=f->idr;m->frames++;
  }else m->gap=0;
  /* Keep the display's original slot grid through an overdue wakeup. Do not
   * move every later display slot to a new phase when one deadline is missed.
   * Emit once and advance past missed slots; never burst catch-up formats. */
  uint64_t steps=1+(now-m->next_format)/16683;
  m->format_skips+=steps-1;m->next_format+=steps*16683;
 }
 while(m->count){
  media_frame *f=&m->jobs[m->head];uint64_t due=media_packet_due(f);if(now<due)break;
  uint64_t late=now-due;if(late>1000)m->late++;if(late>m->max_late)m->max_late=late;
  size_t offset=(size_t)f->part*1694,n=f->length[f->chunk]-offset;if(n>1694)n=1694;
  int end=offset+n==f->length[f->chunk],first=f->chunk==0&&f->part==0;
  uint16_t seq=m->sequence++&1023;uint8_t packet[1710]={0};
  packet[0]=0xf0|((seq>>8)&3);packet[1]=seq&255;
  packet[2]=8|(f->init?128:0)|(first?64:0)|(end?32:0)|(end&&f->chunk==4?16:0)|(n>>8);packet[3]=n&255;
  packet[4]=f->stamp>>24;packet[5]=f->stamp>>16;packet[6]=f->stamp>>8;packet[7]=f->stamp;
  unsigned o=8;if(f->idr)packet[o++]=128;packet[o++]=130;packet[o++]=0;packet[o++]=131;packet[o++]=133;packet[o]=6;
  memcpy(packet+16,f->bytes+f->offset[f->chunk]+offset,n);m->emit(m->context,packet,16+n,50120);m->packets++;
  if(end){f->chunk++;f->part=0;}else f->part++;
  if(f->chunk==5){m->head=(m->head+1)%2;m->count--;}
 }
}
#endif
