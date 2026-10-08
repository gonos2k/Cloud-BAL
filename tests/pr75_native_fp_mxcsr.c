#include <xmmintrin.h>
#include <sys/syscall.h>
#include <unistd.h>

int pr75_read_fp_state(int *thread_id)
{
    *thread_id = (int)syscall(SYS_gettid);
    return (int)_mm_getcsr();
}
