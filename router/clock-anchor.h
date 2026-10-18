/* Convert the kernel realtime receive timestamp into the scheduling clock.
 * Bracket the clock sample BEFORE any send: network service time is unrelated
 * to the radio beacon's receive time. Reject preempted cross-clock samples. */
#ifndef GAMEPAD_CLOCK_ANCHOR_H
#define GAMEPAD_CLOCK_ANCHOR_H
#include <stdint.h>
static int receive_clock_anchor(uint64_t received_real,uint64_t sample_real,
 uint64_t mono_before,uint64_t mono_after,uint64_t *anchor){
 if(sample_real<received_real||sample_real-received_real>=100000||
    mono_after<mono_before||mono_after-mono_before>100)return 0;
 uint64_t middle=mono_before+(mono_after-mono_before)/2;
 uint64_t age=sample_real-received_real;
 if(middle<age)return 0;
 *anchor=middle-age;return 1;
}
#endif
