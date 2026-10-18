/* Parent includes Linux filter.h, or pcap/bpf.h for offline verification. */
static const struct sock_filter template_filter[]={
 BPF_STMT(BPF_LD|BPF_B|BPF_ABS,3),
 BPF_STMT(BPF_ALU|BPF_LSH|BPF_K,8),
 BPF_STMT(BPF_MISC|BPF_TAX,0),
 BPF_STMT(BPF_LD|BPF_B|BPF_ABS,2),
 BPF_STMT(BPF_ALU|BPF_OR|BPF_X,0),
 BPF_STMT(BPF_MISC|BPF_TAX,0),
 BPF_STMT(BPF_LD|BPF_B|BPF_IND,0),
 BPF_STMT(BPF_ALU|BPF_AND|BPF_K,0xfc),
 BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,0x80,0,5),
 BPF_STMT(BPF_LD|BPF_W|BPF_IND,10),
 BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,0,0,3),
 BPF_STMT(BPF_LD|BPF_H|BPF_IND,14),
 BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,0,0,1),
 BPF_STMT(BPF_RET|BPF_K,96),
 BPF_STMT(BPF_RET|BPF_K,0),
};

#define CLOCK_FILTER_LENGTH (sizeof(template_filter)/sizeof(template_filter[0]))
static void make_clock_filter(struct sock_filter *filter,const uint8_t mac[6]){
 memcpy(filter,template_filter,sizeof(template_filter));
 filter[10].k=((uint32_t)mac[0]<<24)|((uint32_t)mac[1]<<16)|((uint32_t)mac[2]<<8)|mac[3];
 filter[12].k=((uint32_t)mac[4]<<8)|mac[5];
}
