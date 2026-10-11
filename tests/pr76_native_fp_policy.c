#include <stdint.h>
#include <xmmintrin.h>
#include <sys/syscall.h>
#include <unistd.h>

#define PR76_FTZ_DAZ_MASK ((1u << 15) | (1u << 6))

int pr76_read_fp_state(int *thread_id)
{
    *thread_id = (int)syscall(SYS_gettid);
    return (int)_mm_getcsr();
}

int pr75_read_fp_state(int *thread_id)
{
    return pr76_read_fp_state(thread_id);
}

int pr76_apply_gradual(int *after, int *thread_id)
{
    unsigned int before = _mm_getcsr();
    *thread_id = (int)syscall(SYS_gettid);
    _mm_setcsr(before & ~PR76_FTZ_DAZ_MASK);
    *after = (int)_mm_getcsr();
    return (int)before;
}
