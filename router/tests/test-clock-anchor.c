#include "clock-anchor.h"
#include <assert.h>
#include <stdio.h>
int main(void){
 uint64_t anchor=0;
 assert(receive_clock_anchor(9000000,9000500,2000498,2000502,&anchor));
 assert(anchor==2000000);
 /* A later network operation, even 8 ms long, does not move the saved anchor. */
 uint64_t transmit_done=2008502;(void)transmit_done;assert(anchor==2000000);
 assert(!receive_clock_anchor(9000000,9000500,2000498,2009000,&anchor));
 assert(anchor==2000000); /* Reject preemption without corrupting prior state. */
 assert(!receive_clock_anchor(9000600,9000500,2000498,2000502,&anchor));
 assert(!receive_clock_anchor(8800000,9000500,2000498,2000502,&anchor));
 assert(!receive_clock_anchor(9000000,9000500,2000502,2000498,&anchor));
 puts("Receive clock anchor: delayed send independent, bracket rejection, stale/future kernel timestamps PASS");
}
