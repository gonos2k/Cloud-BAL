#include <stdint.h>
#include <stdio.h>
#include <xmmintrin.h>

int pr76_apply_gradual(int *after, int *thread_id);

int main(void)
{
    const unsigned int mask = (1u << 15) | (1u << 6);
    unsigned int original = _mm_getcsr();
    unsigned int requested = (original | 0x3fu | 0x1f80u | mask);
    requested = (requested & ~(3u << 13)) | (2u << 13);
    _mm_setcsr(requested);

    int after = 0;
    int thread_id = 0;
    unsigned int before = (unsigned int)pr76_apply_gradual(&after, &thread_id);
    unsigned int expected = before & ~mask;
    unsigned int actual = (unsigned int)after;
    _mm_setcsr(original);

    if (before != requested || actual != expected || thread_id <= 0) {
        fprintf(stderr, "MXCSR before=%08x after=%08x expected=%08x tid=%d\n",
                before, actual, expected, thread_id);
        return 1;
    }
    printf("MXCSR_POLICY_OK before=%08x after=%08x preserved_mask=%08x tid=%d\n",
           before, actual, ~(mask), thread_id);
    return 0;
}
