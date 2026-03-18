/*
 * allocator.c — Unified Memory Allocator
 * Implements: buddy, slab, arena, free-list, pool with TLC, mark-sweep GC,
 * mmap abstraction, reference counting, debug instrumentation, aligned alloc.
 * Copyright (c) 2025. MIT License.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>
#include <errno.h>
#include <stdbool.h>

#ifdef _WIN32
#include <windows.h>
#else
#include <sys/mman.h>
#include <unistd.h>
#include <pthread.h>
#endif

/* ---- Configuration ---- */
#define BUDDY_MIN_ORDER      4
#define BUDDY_MAX_ORDER      24
#define BUDDY_NUM_ORDERS     (BUDDY_MAX_ORDER - BUDDY_MIN_ORDER + 1)
#define SLAB_SIZES_COUNT     8
#define SLAB_OBJECTS_PER_PAGE 64
#define SLAB_MAX_OBJ_SIZE    2048
#define ARENA_DEFAULT_CHUNK  (64 * 1024)
#define ARENA_MAX_CHUNKS     1024
#define FREELIST_MIN_BLOCK   32
#define POOL_THREAD_CACHE_SZ 256
#define POOL_MAX_THREADS     64
#define POOL_BATCH_REFILL    32
#define GC_INITIAL_ROOTS     128
#define GC_MARK_STACK_SIZE   4096
#define MMAP_ALIGN           4096
#define MMAP_MAX_MAPPINGS    256
#define REDZONE_SIZE         16
#define REDZONE_FILL         0xFD
#define POISON_ALLOC         0xCD
#define POISON_FREE          0xDD
#define REFCOUNT_MAX         UINT32_MAX
#define DEBUG_MAX_RECORDS    8192

#define ALIGN_UP(x, a)       (((x) + ((a) - 1)) & ~((a) - 1))
#define IS_POW2(x)           ((x) && !((x) & ((x) - 1)))
#define MIN(a, b)            ((a) < (b) ? (a) : (b))
#define MAX(a, b)            ((a) > (b) ? (a) : (b))
#define LOG2_FLOOR(x)        (31 - __builtin_clz((unsigned)(x)))

#ifndef NDEBUG
#define ALLOC_DEBUG 1
#else
#define ALLOC_DEBUG 0
#endif

#define ALLOC_ASSERT(c, m) do { if (!(c)) { \
    fprintf(stderr, "ASSERT: %s at %s:%d\n", (m), __FILE__, __LINE__); abort(); } } while(0)

#if ALLOC_DEBUG
#define DBG(fmt, ...) fprintf(stderr, "[alloc] " fmt "\n", ##__VA_ARGS__)
#else
#define DBG(...) ((void)0)
#endif

/* ---- Common Types ---- */
typedef enum {
    ALLOC_OK = 0, ALLOC_ERR_NOMEM, ALLOC_ERR_INVALID, ALLOC_ERR_DOUBLE_FREE,
    ALLOC_ERR_OVERFLOW, ALLOC_ERR_ALIGNMENT, ALLOC_ERR_CORRUPTED,
    ALLOC_ERR_MMAP_FAIL, ALLOC_ERR_NOT_FOUND, ALLOC_ERR_FULL,
} alloc_error_t;

typedef enum { FIT_FIRST, FIT_BEST, FIT_NEXT } fit_strategy_t;
typedef enum { GC_WHITE = 0, GC_GRAY = 1, GC_BLACK = 2 } gc_color_t;

typedef struct alloc_stats {
    uint64_t total_allocated, total_freed, current_usage, peak_usage;
    uint64_t alloc_count, free_count, realloc_count, failed_allocs;
    uint64_t coalesce_count, split_count;
    double   fragmentation_ratio;
} alloc_stats_t;

static inline void stats_track_alloc(alloc_stats_t *s, size_t sz) {
    s->total_allocated += sz; s->current_usage += sz; s->alloc_count++;
    if (s->current_usage > s->peak_usage) s->peak_usage = s->current_usage;
}
static inline void stats_track_free(alloc_stats_t *s, size_t sz) {
    s->total_freed += sz; s->current_usage -= sz; s->free_count++;
}

/* =========================================================================
 * Buddy Allocator
 * ========================================================================= */
typedef struct buddy_block {
    struct buddy_block *next, *prev;
    uint32_t order, is_free, magic;
} buddy_block_t;

#define BUDDY_MAGIC_FREE  0xBDD1F1EE
#define BUDDY_MAGIC_USED  0xBDD10CED

typedef struct buddy_allocator {
    void *base;
    size_t total_size;
    uint32_t max_order;
    buddy_block_t *free_lists[BUDDY_NUM_ORDERS];
    uint8_t *split_map;
    size_t split_map_size;
    alloc_stats_t stats;
} buddy_allocator_t;

static size_t buddy_order_sz(uint32_t order) { return (size_t)1 << order; }

static uint32_t buddy_sz_to_order(size_t size) {
    if (size <= (1u << BUDDY_MIN_ORDER)) return BUDDY_MIN_ORDER;
    uint32_t o = BUDDY_MIN_ORDER;
    size_t bs = 1u << BUDDY_MIN_ORDER;
    while (bs < size && o < BUDDY_MAX_ORDER) { o++; bs <<= 1; }
    return o;
}

static void bl_insert(buddy_block_t **head, buddy_block_t *b) {
    b->prev = NULL; b->next = *head;
    if (*head) (*head)->prev = b;
    *head = b;
}

static void bl_remove(buddy_block_t **head, buddy_block_t *b) {
    if (b->prev) b->prev->next = b->next; else *head = b->next;
    if (b->next) b->next->prev = b->prev;
    b->next = b->prev = NULL;
}

static buddy_block_t *buddy_get_buddy(buddy_allocator_t *ba, buddy_block_t *blk) {
    uintptr_t off = (uintptr_t)blk - (uintptr_t)ba->base;
    uintptr_t buddy_off = off ^ buddy_order_sz(blk->order);
    if (buddy_off >= ba->total_size) return NULL;
    return (buddy_block_t *)((uintptr_t)ba->base + buddy_off);
}

static void buddy_set_split(buddy_allocator_t *ba, uintptr_t off, uint32_t order, int v) {
    size_t idx = (off / buddy_order_sz(BUDDY_MIN_ORDER)) + order;
    if (idx < ba->split_map_size) {
        if (v) ba->split_map[idx/8] |= (1 << (idx%8));
        else   ba->split_map[idx/8] &= ~(1 << (idx%8));
    }
}

alloc_error_t buddy_init(buddy_allocator_t *ba, void *base, size_t total_size) {
    if (!ba || !base || total_size < (1u << BUDDY_MIN_ORDER)) return ALLOC_ERR_INVALID;
    uint32_t mo = LOG2_FLOOR((unsigned)total_size);
    if (mo > BUDDY_MAX_ORDER) mo = BUDDY_MAX_ORDER;
    ba->base = base; ba->total_size = buddy_order_sz(mo); ba->max_order = mo;
    memset(ba->free_lists, 0, sizeof(ba->free_lists));
    memset(&ba->stats, 0, sizeof(ba->stats));
    ba->split_map_size = (ba->total_size / buddy_order_sz(BUDDY_MIN_ORDER)) * BUDDY_NUM_ORDERS;
    ba->split_map = (uint8_t *)calloc(1, (ba->split_map_size + 7) / 8);
    if (!ba->split_map) return ALLOC_ERR_NOMEM;
    buddy_block_t *root = (buddy_block_t *)base;
    root->order = mo; root->is_free = 1; root->magic = BUDDY_MAGIC_FREE;
    root->next = root->prev = NULL;
    uint32_t li = mo - BUDDY_MIN_ORDER;
    if (li < BUDDY_NUM_ORDERS) ba->free_lists[li] = root;
    return ALLOC_OK;
}

void *buddy_alloc(buddy_allocator_t *ba, size_t size) {
    if (!ba || size == 0) return NULL;
    uint32_t order = buddy_sz_to_order(size + sizeof(buddy_block_t));
    if (order > ba->max_order) { ba->stats.failed_allocs++; return NULL; }
    uint32_t fo = order;
    while (fo <= ba->max_order) {
        uint32_t i = fo - BUDDY_MIN_ORDER;
        if (i < BUDDY_NUM_ORDERS && ba->free_lists[i]) break;
        fo++;
    }
    if (fo > ba->max_order) { ba->stats.failed_allocs++; return NULL; }
    uint32_t idx = fo - BUDDY_MIN_ORDER;
    buddy_block_t *blk = ba->free_lists[idx];
    bl_remove(&ba->free_lists[idx], blk);
    while (fo > order) {
        fo--; idx = fo - BUDDY_MIN_ORDER;
        buddy_block_t *buddy = (buddy_block_t *)((uintptr_t)blk + buddy_order_sz(fo));
        buddy->order = fo; buddy->is_free = 1; buddy->magic = BUDDY_MAGIC_FREE;
        if (idx < BUDDY_NUM_ORDERS) bl_insert(&ba->free_lists[idx], buddy);
        buddy_set_split(ba, (uintptr_t)blk - (uintptr_t)ba->base, fo + 1, 1);
        ba->stats.split_count++;
    }
    blk->order = order; blk->is_free = 0; blk->magic = BUDDY_MAGIC_USED;
    size_t bsz = buddy_order_sz(order);
    stats_track_alloc(&ba->stats, bsz);
    void *ptr = (void *)((uintptr_t)blk + sizeof(buddy_block_t));
    if (ALLOC_DEBUG) memset(ptr, POISON_ALLOC, bsz - sizeof(buddy_block_t));
    return ptr;
}

alloc_error_t buddy_free(buddy_allocator_t *ba, void *ptr) {
    if (!ba || !ptr) return ALLOC_ERR_INVALID;
    buddy_block_t *blk = (buddy_block_t *)((uintptr_t)ptr - sizeof(buddy_block_t));
    if (blk->magic == BUDDY_MAGIC_FREE) return ALLOC_ERR_DOUBLE_FREE;
    if (blk->magic != BUDDY_MAGIC_USED) return ALLOC_ERR_CORRUPTED;
    size_t bsz = buddy_order_sz(blk->order);
    stats_track_free(&ba->stats, bsz);
    if (ALLOC_DEBUG) memset(ptr, POISON_FREE, bsz - sizeof(buddy_block_t));
    blk->is_free = 1; blk->magic = BUDDY_MAGIC_FREE;
    while (blk->order < ba->max_order) {
        buddy_block_t *buddy = buddy_get_buddy(ba, blk);
        if (!buddy || !buddy->is_free || buddy->order != blk->order) break;
        uint32_t i = buddy->order - BUDDY_MIN_ORDER;
        if (i < BUDDY_NUM_ORDERS) bl_remove(&ba->free_lists[i], buddy);
        buddy_set_split(ba, (uintptr_t)blk - (uintptr_t)ba->base, blk->order + 1, 0);
        if ((uintptr_t)buddy < (uintptr_t)blk) blk = buddy;
        blk->order++;
        ba->stats.coalesce_count++;
    }
    uint32_t i = blk->order - BUDDY_MIN_ORDER;
    if (i < BUDDY_NUM_ORDERS) bl_insert(&ba->free_lists[i], blk);
    return ALLOC_OK;
}

void buddy_destroy(buddy_allocator_t *ba) {
    if (ba && ba->split_map) { free(ba->split_map); ba->split_map = NULL; }
}

/* =========================================================================
 * Slab Allocator
 * ========================================================================= */
static const size_t slab_classes[SLAB_SIZES_COUNT] = {16,32,64,128,256,512,1024,2048};

typedef struct slab_obj { struct slab_obj *next_free; } slab_obj_t;

typedef struct slab_page {
    struct slab_page *next, *prev;
    void *memory;
    slab_obj_t *free_list;
    uint32_t obj_size, total_objects, free_count;
} slab_page_t;

typedef struct slab_cache {
    const char *name;
    uint32_t obj_size, alignment;
    slab_page_t *partial, *full, *empty;
    uint32_t pages_allocated;
    alloc_stats_t stats;
    void (*ctor)(void *, size_t);
    void (*dtor)(void *, size_t);
} slab_cache_t;

typedef struct slab_allocator {
    slab_cache_t caches[SLAB_SIZES_COUNT];
    size_t page_size;
    alloc_stats_t stats;
} slab_allocator_t;

static int slab_find_cache(size_t sz) {
    for (int i = 0; i < SLAB_SIZES_COUNT; i++)
        if (sz <= slab_classes[i]) return i;
    return -1;
}

static void spl_insert(slab_page_t **h, slab_page_t *p) {
    p->prev = NULL; p->next = *h; if (*h) (*h)->prev = p; *h = p;
}
static void spl_remove(slab_page_t **h, slab_page_t *p) {
    if (p->prev) p->prev->next = p->next; else *h = p->next;
    if (p->next) p->next->prev = p->prev;
    p->next = p->prev = NULL;
}

static slab_page_t *slab_page_create(slab_cache_t *c, size_t pgsz) {
    slab_page_t *pg = (slab_page_t *)calloc(1, sizeof(slab_page_t));
    if (!pg) return NULL;
    pg->memory = calloc(1, pgsz);
    if (!pg->memory) { free(pg); return NULL; }
    pg->obj_size = c->obj_size;
    size_t eff = MAX(c->obj_size, sizeof(slab_obj_t));
    if (c->alignment > 1) eff = ALIGN_UP(eff, c->alignment);
    pg->total_objects = (uint32_t)(pgsz / eff);
    if (pg->total_objects > SLAB_OBJECTS_PER_PAGE) pg->total_objects = SLAB_OBJECTS_PER_PAGE;
    pg->free_count = pg->total_objects;
    pg->free_list = NULL;
    for (uint32_t i = 0; i < pg->total_objects; i++) {
        slab_obj_t *obj = (slab_obj_t *)((uintptr_t)pg->memory + i * eff);
        obj->next_free = pg->free_list; pg->free_list = obj;
        if (c->ctor) c->ctor((void *)obj, c->obj_size);
    }
    c->pages_allocated++;
    return pg;
}

alloc_error_t slab_init(slab_allocator_t *sa) {
    if (!sa) return ALLOC_ERR_INVALID;
    sa->page_size = 4096;
    memset(&sa->stats, 0, sizeof(sa->stats));
    for (int i = 0; i < SLAB_SIZES_COUNT; i++) {
        slab_cache_t *c = &sa->caches[i];
        c->name = "generic"; c->obj_size = (uint32_t)slab_classes[i];
        c->alignment = 8;
        c->partial = c->full = c->empty = NULL;
        c->pages_allocated = 0; c->ctor = c->dtor = NULL;
        memset(&c->stats, 0, sizeof(c->stats));
    }
    return ALLOC_OK;
}

void *slab_alloc(slab_allocator_t *sa, size_t size) {
    if (!sa || size == 0 || size > SLAB_MAX_OBJ_SIZE) return NULL;
    int idx = slab_find_cache(size);
    if (idx < 0) return NULL;
    slab_cache_t *c = &sa->caches[idx];
    slab_page_t *pg = c->partial;
    if (!pg) {
        pg = c->empty;
        if (pg) { spl_remove(&c->empty, pg); spl_insert(&c->partial, pg); }
        else {
            pg = slab_page_create(c, sa->page_size);
            if (!pg) { sa->stats.failed_allocs++; return NULL; }
            spl_insert(&c->partial, pg);
        }
    }
    slab_obj_t *obj = pg->free_list;
    pg->free_list = obj->next_free;
    pg->free_count--;
    if (pg->free_count == 0) { spl_remove(&c->partial, pg); spl_insert(&c->full, pg); }
    stats_track_alloc(&c->stats, c->obj_size);
    stats_track_alloc(&sa->stats, c->obj_size);
    if (ALLOC_DEBUG) memset(obj, POISON_ALLOC, c->obj_size);
    return (void *)obj;
}

alloc_error_t slab_free(slab_allocator_t *sa, void *ptr, size_t size) {
    if (!sa || !ptr) return ALLOC_ERR_INVALID;
    int idx = slab_find_cache(size);
    if (idx < 0) return ALLOC_ERR_INVALID;
    slab_cache_t *c = &sa->caches[idx];
    /* Find page containing ptr */
    slab_page_t *pg = NULL;
    slab_page_t *lists[] = { c->partial, c->full, c->empty };
    for (int j = 0; j < 3 && !pg; j++) {
        slab_page_t *p = lists[j];
        while (p) {
            uintptr_t s = (uintptr_t)p->memory;
            uintptr_t e = s + (p->total_objects * p->obj_size);
            if ((uintptr_t)ptr >= s && (uintptr_t)ptr < e) { pg = p; break; }
            p = p->next;
        }
    }
    if (!pg) return ALLOC_ERR_NOT_FOUND;
    if (c->dtor) c->dtor(ptr, c->obj_size);
    if (ALLOC_DEBUG) memset(ptr, POISON_FREE, c->obj_size);
    slab_obj_t *obj = (slab_obj_t *)ptr;
    obj->next_free = pg->free_list; pg->free_list = obj;
    int was_full = (pg->free_count == 0);
    pg->free_count++;
    if (was_full) { spl_remove(&c->full, pg); spl_insert(&c->partial, pg); }
    else if (pg->free_count == pg->total_objects) {
        spl_remove(&c->partial, pg); spl_insert(&c->empty, pg);
    }
    stats_track_free(&c->stats, c->obj_size);
    stats_track_free(&sa->stats, c->obj_size);
    return ALLOC_OK;
}

void slab_destroy(slab_allocator_t *sa) {
    if (!sa) return;
    for (int i = 0; i < SLAB_SIZES_COUNT; i++) {
        slab_cache_t *c = &sa->caches[i];
        slab_page_t *lists[] = { c->partial, c->full, c->empty };
        for (int j = 0; j < 3; j++) {
            slab_page_t *p = lists[j];
            while (p) { slab_page_t *n = p->next; free(p->memory); free(p); p = n; }
        }
        c->partial = c->full = c->empty = NULL;
    }
}

/* =========================================================================
 * Arena Allocator
 * ========================================================================= */
typedef struct arena_chunk {
    struct arena_chunk *next;
    void *memory;
    size_t capacity, used;
} arena_chunk_t;

typedef struct arena_allocator {
    arena_chunk_t *current, *chunks;
    size_t default_chunk_size;
    uint32_t chunk_count, default_alignment;
    alloc_stats_t stats;
} arena_allocator_t;

static arena_chunk_t *arena_chunk_new(size_t cap) {
    arena_chunk_t *ch = (arena_chunk_t *)calloc(1, sizeof(arena_chunk_t));
    if (!ch) return NULL;
    ch->memory = malloc(cap);
    if (!ch->memory) { free(ch); return NULL; }
    ch->capacity = cap; ch->used = 0; ch->next = NULL;
    return ch;
}

alloc_error_t arena_init(arena_allocator_t *a, size_t chunk_size) {
    if (!a) return ALLOC_ERR_INVALID;
    a->default_chunk_size = chunk_size > 0 ? chunk_size : ARENA_DEFAULT_CHUNK;
    a->default_alignment = 8; a->chunk_count = 0;
    memset(&a->stats, 0, sizeof(a->stats));
    arena_chunk_t *first = arena_chunk_new(a->default_chunk_size);
    if (!first) return ALLOC_ERR_NOMEM;
    a->current = a->chunks = first; a->chunk_count = 1;
    return ALLOC_OK;
}

void *arena_alloc(arena_allocator_t *a, size_t size) {
    if (!a || size == 0) return NULL;
    size_t aligned = ALIGN_UP(size, a->default_alignment);
    arena_chunk_t *ch = a->current;
    if (ch->used + aligned > ch->capacity) {
        /* search existing chunks */
        arena_chunk_t *c = a->chunks;
        ch = NULL;
        while (c) { if (c->used + aligned <= c->capacity) { ch = c; break; } c = c->next; }
        if (!ch) {
            if (a->chunk_count >= ARENA_MAX_CHUNKS) { a->stats.failed_allocs++; return NULL; }
            size_t nc = MAX(a->default_chunk_size, aligned * 2);
            arena_chunk_t *nch = arena_chunk_new(nc);
            if (!nch) { a->stats.failed_allocs++; return NULL; }
            nch->next = a->chunks; a->chunks = nch; a->current = nch;
            a->chunk_count++; ch = nch;
        }
    }
    void *ptr = (void *)((uintptr_t)ch->memory + ch->used);
    ch->used += aligned;
    stats_track_alloc(&a->stats, aligned);
    return ptr;
}

void *arena_alloc_aligned(arena_allocator_t *a, size_t size, size_t alignment) {
    if (!a || size == 0 || !IS_POW2(alignment)) return NULL;
    arena_chunk_t *ch = a->current;
    uintptr_t cur = (uintptr_t)ch->memory + ch->used;
    uintptr_t al = ALIGN_UP(cur, alignment);
    size_t total = (al - cur) + size;
    if (ch->used + total > ch->capacity) {
        size_t nc = MAX(a->default_chunk_size, total + alignment);
        arena_chunk_t *nch = arena_chunk_new(nc);
        if (!nch) return NULL;
        nch->next = a->chunks; a->chunks = nch; a->current = nch; a->chunk_count++;
        ch = nch;
        cur = (uintptr_t)ch->memory; al = ALIGN_UP(cur, alignment);
        total = (al - cur) + size;
    }
    ch->used += total;
    stats_track_alloc(&a->stats, total);
    return (void *)al;
}

void arena_reset(arena_allocator_t *a) {
    if (!a) return;
    arena_chunk_t *ch = a->chunks;
    while (ch) {
        if (ALLOC_DEBUG) memset(ch->memory, POISON_FREE, ch->used);
        ch->used = 0; ch = ch->next;
    }
    a->current = a->chunks;
    a->stats.current_usage = 0; a->stats.free_count++;
}

void arena_destroy(arena_allocator_t *a) {
    if (!a) return;
    arena_chunk_t *ch = a->chunks;
    while (ch) { arena_chunk_t *n = ch->next; free(ch->memory); free(ch); ch = n; }
    a->chunks = a->current = NULL; a->chunk_count = 0;
}

/* =========================================================================
 * Free List Allocator (first-fit / best-fit / next-fit)
 * ========================================================================= */
typedef struct fl_block {
    struct fl_block *next;
    size_t size;
    uint32_t is_free, magic;
#if ALLOC_DEBUG
    const char *alloc_file;
    int alloc_line;
    uint8_t redzone_pre[REDZONE_SIZE];
#endif
} fl_block_t;

#define FL_MAGIC_FREE 0xF1EEF1EE
#define FL_MAGIC_USED 0xA110CA7D

typedef struct freelist_allocator {
    void *base;
    size_t total_size;
    fl_block_t *head, *last_fit;
    fit_strategy_t strategy;
    uint32_t block_count;
    alloc_stats_t stats;
} freelist_allocator_t;

alloc_error_t freelist_init(freelist_allocator_t *fl, void *base,
                            size_t size, fit_strategy_t strat) {
    if (!fl || !base || size < sizeof(fl_block_t) + FREELIST_MIN_BLOCK)
        return ALLOC_ERR_INVALID;
    fl->base = base; fl->total_size = size; fl->strategy = strat;
    fl->block_count = 1;
    memset(&fl->stats, 0, sizeof(fl->stats));
    fl_block_t *init = (fl_block_t *)base;
    init->size = size - sizeof(fl_block_t);
    init->is_free = 1; init->magic = FL_MAGIC_FREE; init->next = NULL;
#if ALLOC_DEBUG
    memset(init->redzone_pre, REDZONE_FILL, REDZONE_SIZE);
#endif
    fl->head = fl->last_fit = init;
    return ALLOC_OK;
}

static fl_block_t *fl_find_first(freelist_allocator_t *fl, size_t sz) {
    fl_block_t *b = fl->head;
    while (b) { if (b->is_free && b->size >= sz) return b; b = b->next; }
    return NULL;
}

static fl_block_t *fl_find_best(freelist_allocator_t *fl, size_t sz) {
    fl_block_t *best = NULL; size_t bdiff = SIZE_MAX;
    fl_block_t *b = fl->head;
    while (b) {
        if (b->is_free && b->size >= sz) {
            size_t d = b->size - sz;
            if (d < bdiff) { best = b; bdiff = d; if (d == 0) break; }
        }
        b = b->next;
    }
    return best;
}

static fl_block_t *fl_find_next(freelist_allocator_t *fl, size_t sz) {
    fl_block_t *start = fl->last_fit ? fl->last_fit : fl->head;
    fl_block_t *b = start;
    while (b) { if (b->is_free && b->size >= sz) { fl->last_fit = b; return b; } b = b->next; }
    b = fl->head;
    while (b && b != start) {
        if (b->is_free && b->size >= sz) { fl->last_fit = b; return b; } b = b->next;
    }
    return NULL;
}

static void fl_split(freelist_allocator_t *fl, fl_block_t *blk, size_t sz) {
    size_t rem = blk->size - sz - sizeof(fl_block_t);
    if (rem < FREELIST_MIN_BLOCK) return;
    fl_block_t *nb = (fl_block_t *)((uintptr_t)blk + sizeof(fl_block_t) + sz);
    nb->size = rem; nb->is_free = 1; nb->magic = FL_MAGIC_FREE; nb->next = blk->next;
#if ALLOC_DEBUG
    memset(nb->redzone_pre, REDZONE_FILL, REDZONE_SIZE);
#endif
    blk->size = sz; blk->next = nb;
    fl->block_count++; fl->stats.split_count++;
}

void *freelist_alloc(freelist_allocator_t *fl, size_t size) {
    if (!fl || size == 0) return NULL;
    size_t asz = ALIGN_UP(size, 8);
#if ALLOC_DEBUG
    asz += REDZONE_SIZE;
#endif
    fl_block_t *blk = NULL;
    switch (fl->strategy) {
    case FIT_FIRST: blk = fl_find_first(fl, asz); break;
    case FIT_BEST:  blk = fl_find_best(fl, asz);  break;
    case FIT_NEXT:  blk = fl_find_next(fl, asz);  break;
    }
    if (!blk) { fl->stats.failed_allocs++; return NULL; }
    fl_split(fl, blk, asz);
    blk->is_free = 0; blk->magic = FL_MAGIC_USED;
    stats_track_alloc(&fl->stats, blk->size);
    void *ptr = (void *)((uintptr_t)blk + sizeof(fl_block_t));
#if ALLOC_DEBUG
    memset(ptr, POISON_ALLOC, size);
    memset((uint8_t *)ptr + size, REDZONE_FILL, REDZONE_SIZE);
    blk->alloc_file = NULL; blk->alloc_line = 0;
#endif
    return ptr;
}

void *freelist_alloc_traced(freelist_allocator_t *fl, size_t size,
                            const char *file, int line) {
    void *ptr = freelist_alloc(fl, size);
#if ALLOC_DEBUG
    if (ptr) {
        fl_block_t *b = (fl_block_t *)((uintptr_t)ptr - sizeof(fl_block_t));
        b->alloc_file = file; b->alloc_line = line;
    }
#else
    (void)file; (void)line;
#endif
    return ptr;
}

static void fl_coalesce(freelist_allocator_t *fl) {
    fl_block_t *b = fl->head;
    while (b && b->next) {
        if (b->is_free && b->next->is_free) {
            fl_block_t *absorbed = b->next;
            b->size += sizeof(fl_block_t) + absorbed->size;
            b->next = absorbed->next;
            fl->block_count--; fl->stats.coalesce_count++;
            if (fl->last_fit == absorbed) fl->last_fit = b;
        } else b = b->next;
    }
}

alloc_error_t freelist_free(freelist_allocator_t *fl, void *ptr) {
    if (!fl || !ptr) return ALLOC_ERR_INVALID;
    fl_block_t *blk = (fl_block_t *)((uintptr_t)ptr - sizeof(fl_block_t));
    if (blk->magic == FL_MAGIC_FREE) return ALLOC_ERR_DOUBLE_FREE;
    if (blk->magic != FL_MAGIC_USED) return ALLOC_ERR_CORRUPTED;
#if ALLOC_DEBUG
    for (int i = 0; i < REDZONE_SIZE; i++)
        if (blk->redzone_pre[i] != REDZONE_FILL) return ALLOC_ERR_CORRUPTED;
#endif
    blk->is_free = 1; blk->magic = FL_MAGIC_FREE;
    stats_track_free(&fl->stats, blk->size);
    if (ALLOC_DEBUG) memset(ptr, POISON_FREE, blk->size);
    fl_coalesce(fl);
    return ALLOC_OK;
}

double freelist_fragmentation(freelist_allocator_t *fl) {
    if (!fl) return 0.0;
    size_t total_free = 0, largest = 0;
    fl_block_t *b = fl->head;
    while (b) {
        if (b->is_free) { total_free += b->size; if (b->size > largest) largest = b->size; }
        b = b->next;
    }
    if (total_free == 0) return 0.0;
    fl->stats.fragmentation_ratio = 1.0 - ((double)largest / (double)total_free);
    return fl->stats.fragmentation_ratio;
}

/* =========================================================================
 * Memory Pool with Thread-Local Cache
 * ========================================================================= */
typedef struct pool_slot { struct pool_slot *next; } pool_slot_t;

typedef struct pool_tcache {
    pool_slot_t *free_list;
    uint32_t count, max_count;
    uint64_t thread_id;
    uint32_t allocs, frees, refills, drains;
} pool_tcache_t;

typedef struct pool_central {
    pool_slot_t *free_list;
    uint32_t free_count, total_slots;
    size_t slot_size;
    void *backing;
    size_t backing_size;
#ifdef _WIN32
    CRITICAL_SECTION lock;
#else
    pthread_mutex_t lock;
#endif
} pool_central_t;

typedef struct pool_allocator {
    pool_central_t central;
    pool_tcache_t caches[POOL_MAX_THREADS];
    uint32_t num_caches;
    size_t obj_size;
    alloc_stats_t stats;
} pool_allocator_t;

static void pool_lock(pool_central_t *c) {
#ifdef _WIN32
    EnterCriticalSection(&c->lock);
#else
    pthread_mutex_lock(&c->lock);
#endif
}
static void pool_unlock(pool_central_t *c) {
#ifdef _WIN32
    LeaveCriticalSection(&c->lock);
#else
    pthread_mutex_unlock(&c->lock);
#endif
}
static uint64_t pool_tid(void) {
#ifdef _WIN32
    return (uint64_t)GetCurrentThreadId();
#else
    return (uint64_t)pthread_self();
#endif
}

alloc_error_t pool_init(pool_allocator_t *p, size_t obj_size, uint32_t count) {
    if (!p || obj_size == 0 || count == 0) return ALLOC_ERR_INVALID;
    size_t ss = MAX(ALIGN_UP(obj_size, 8), sizeof(pool_slot_t));
    p->obj_size = obj_size; memset(&p->stats, 0, sizeof(p->stats)); p->num_caches = 0;
    pool_central_t *c = &p->central;
    c->slot_size = ss; c->total_slots = count;
    c->backing_size = ss * count;
    c->backing = calloc(count, ss);
    if (!c->backing) return ALLOC_ERR_NOMEM;
#ifdef _WIN32
    InitializeCriticalSection(&c->lock);
#else
    pthread_mutex_init(&c->lock, NULL);
#endif
    c->free_list = NULL; c->free_count = count;
    for (uint32_t i = 0; i < count; i++) {
        pool_slot_t *s = (pool_slot_t *)((uintptr_t)c->backing + i * ss);
        s->next = c->free_list; c->free_list = s;
    }
    memset(p->caches, 0, sizeof(p->caches));
    return ALLOC_OK;
}

static pool_tcache_t *pool_get_cache(pool_allocator_t *p) {
    uint64_t tid = pool_tid();
    for (uint32_t i = 0; i < p->num_caches; i++)
        if (p->caches[i].thread_id == tid) return &p->caches[i];
    if (p->num_caches >= POOL_MAX_THREADS) return NULL;
    pool_tcache_t *tc = &p->caches[p->num_caches++];
    tc->thread_id = tid; tc->free_list = NULL; tc->count = 0;
    tc->max_count = POOL_THREAD_CACHE_SZ;
    tc->allocs = tc->frees = tc->refills = tc->drains = 0;
    return tc;
}

static void pool_refill(pool_allocator_t *p, pool_tcache_t *tc) {
    pool_central_t *c = &p->central;
    pool_lock(c);
    uint32_t batch = MIN(POOL_BATCH_REFILL, c->free_count);
    for (uint32_t i = 0; i < batch; i++) {
        pool_slot_t *s = c->free_list;
        if (!s) break;
        c->free_list = s->next; c->free_count--;
        s->next = tc->free_list; tc->free_list = s; tc->count++;
    }
    pool_unlock(c);
    tc->refills++;
}

static void pool_drain(pool_allocator_t *p, pool_tcache_t *tc) {
    pool_central_t *c = &p->central;
    pool_lock(c);
    uint32_t n = tc->count / 2;
    for (uint32_t i = 0; i < n; i++) {
        pool_slot_t *s = tc->free_list;
        if (!s) break;
        tc->free_list = s->next; tc->count--;
        s->next = c->free_list; c->free_list = s; c->free_count++;
    }
    pool_unlock(c);
    tc->drains++;
}

void *pool_alloc(pool_allocator_t *p) {
    if (!p) return NULL;
    pool_tcache_t *tc = pool_get_cache(p);
    if (!tc) {
        pool_lock(&p->central);
        pool_slot_t *s = p->central.free_list;
        if (s) { p->central.free_list = s->next; p->central.free_count--; }
        pool_unlock(&p->central);
        if (!s) { p->stats.failed_allocs++; return NULL; }
        p->stats.alloc_count++;
        return (void *)s;
    }
    if (tc->count == 0) {
        pool_refill(p, tc);
        if (tc->count == 0) { p->stats.failed_allocs++; return NULL; }
    }
    pool_slot_t *s = tc->free_list;
    tc->free_list = s->next; tc->count--; tc->allocs++;
    stats_track_alloc(&p->stats, p->obj_size);
    if (ALLOC_DEBUG) memset(s, POISON_ALLOC, p->obj_size);
    return (void *)s;
}

alloc_error_t pool_free(pool_allocator_t *p, void *ptr) {
    if (!p || !ptr) return ALLOC_ERR_INVALID;
    uintptr_t start = (uintptr_t)p->central.backing;
    uintptr_t end = start + p->central.backing_size;
    if ((uintptr_t)ptr < start || (uintptr_t)ptr >= end) return ALLOC_ERR_INVALID;
    if (ALLOC_DEBUG) memset(ptr, POISON_FREE, p->obj_size);
    pool_tcache_t *tc = pool_get_cache(p);
    pool_slot_t *s = (pool_slot_t *)ptr;
    if (tc) {
        s->next = tc->free_list; tc->free_list = s; tc->count++; tc->frees++;
        if (tc->count > tc->max_count) pool_drain(p, tc);
    } else {
        pool_lock(&p->central);
        s->next = p->central.free_list; p->central.free_list = s; p->central.free_count++;
        pool_unlock(&p->central);
    }
    stats_track_free(&p->stats, p->obj_size);
    return ALLOC_OK;
}

void pool_destroy(pool_allocator_t *p) {
    if (!p) return;
#ifdef _WIN32
    DeleteCriticalSection(&p->central.lock);
#else
    pthread_mutex_destroy(&p->central.lock);
#endif
    free(p->central.backing); p->central.backing = NULL;
}

/* =========================================================================
 * Mark and Sweep Garbage Collector
 * ========================================================================= */
typedef void (*gc_trace_fn)(void *obj, void (*mark)(void *child));

typedef struct gc_header {
    struct gc_header *gc_next;
    gc_trace_fn trace;
    gc_color_t color;
    uint32_t size, generation, magic;
} gc_header_t;

#define GC_MAGIC 0x6C6C6F43

typedef struct gc_root { void **ptr; const char *name; } gc_root_t;

typedef struct gc_collector {
    gc_header_t *all_objects;
    gc_root_t *roots;
    uint32_t root_count, root_capacity;
    gc_header_t **mark_stack;
    uint32_t mark_top, mark_cap;
    uint32_t object_count, live_count, sweep_count, collection_count, generation;
    size_t total_managed, threshold;
    alloc_stats_t stats;
} gc_collector_t;

alloc_error_t gc_init(gc_collector_t *gc, size_t threshold) {
    if (!gc) return ALLOC_ERR_INVALID;
    memset(gc, 0, sizeof(*gc));
    gc->threshold = threshold > 0 ? threshold : 65536;
    gc->root_capacity = GC_INITIAL_ROOTS;
    gc->roots = (gc_root_t *)calloc(gc->root_capacity, sizeof(gc_root_t));
    if (!gc->roots) return ALLOC_ERR_NOMEM;
    gc->mark_cap = GC_MARK_STACK_SIZE;
    gc->mark_stack = (gc_header_t **)calloc(gc->mark_cap, sizeof(gc_header_t *));
    if (!gc->mark_stack) { free(gc->roots); return ALLOC_ERR_NOMEM; }
    return ALLOC_OK;
}

alloc_error_t gc_add_root(gc_collector_t *gc, void **root, const char *name) {
    if (!gc || !root) return ALLOC_ERR_INVALID;
    if (gc->root_count >= gc->root_capacity) {
        uint32_t nc = gc->root_capacity * 2;
        gc_root_t *nr = (gc_root_t *)realloc(gc->roots, nc * sizeof(gc_root_t));
        if (!nr) return ALLOC_ERR_NOMEM;
        gc->roots = nr; gc->root_capacity = nc;
    }
    gc->roots[gc->root_count].ptr = root;
    gc->roots[gc->root_count].name = name;
    gc->root_count++;
    return ALLOC_OK;
}

alloc_error_t gc_remove_root(gc_collector_t *gc, void **root) {
    if (!gc || !root) return ALLOC_ERR_INVALID;
    for (uint32_t i = 0; i < gc->root_count; i++) {
        if (gc->roots[i].ptr == root) {
            gc->roots[i] = gc->roots[--gc->root_count];
            return ALLOC_OK;
        }
    }
    return ALLOC_ERR_NOT_FOUND;
}

void *gc_alloc(gc_collector_t *gc, size_t size, gc_trace_fn trace) {
    if (!gc || size == 0) return NULL;
    size_t total = sizeof(gc_header_t) + size;
    gc_header_t *h = (gc_header_t *)calloc(1, total);
    if (!h) { gc->stats.failed_allocs++; return NULL; }
    h->trace = trace; h->color = GC_WHITE; h->size = (uint32_t)size;
    h->generation = gc->generation; h->magic = GC_MAGIC;
    h->gc_next = gc->all_objects; gc->all_objects = h;
    gc->object_count++; gc->total_managed += total;
    stats_track_alloc(&gc->stats, size);
    void *obj = (void *)((uintptr_t)h + sizeof(gc_header_t));
    if (ALLOC_DEBUG) memset(obj, POISON_ALLOC, size);
    return obj;
}

static gc_header_t *gc_to_header(void *obj) {
    if (!obj) return NULL;
    gc_header_t *h = (gc_header_t *)((uintptr_t)obj - sizeof(gc_header_t));
    return (h->magic == GC_MAGIC) ? h : NULL;
}

static void gc_mark_obj(gc_collector_t *gc, void *obj) {
    if (!obj) return;
    gc_header_t *h = gc_to_header(obj);
    if (!h || h->color != GC_WHITE) return;
    h->color = GC_GRAY;
    if (gc->mark_top < gc->mark_cap) {
        gc->mark_stack[gc->mark_top++] = h;
    } else {
        uint32_t nc = gc->mark_cap * 2;
        gc_header_t **ns = (gc_header_t **)realloc(gc->mark_stack, nc * sizeof(gc_header_t *));
        if (ns) { gc->mark_stack = ns; gc->mark_cap = nc; gc->mark_stack[gc->mark_top++] = h; }
    }
}

static void gc_mark_phase(gc_collector_t *gc) {
    gc_header_t *o = gc->all_objects;
    while (o) { o->color = GC_WHITE; o = o->gc_next; }
    gc->mark_top = 0;
    for (uint32_t i = 0; i < gc->root_count; i++) {
        void *rv = *(gc->roots[i].ptr);
        if (rv) gc_mark_obj(gc, rv);
    }
    while (gc->mark_top > 0) {
        gc_header_t *h = gc->mark_stack[--gc->mark_top];
        h->color = GC_BLACK;
        if (h->trace) {
            void *data = (void *)((uintptr_t)h + sizeof(gc_header_t));
            h->trace(data, gc_mark_obj);
        }
    }
}

static void gc_sweep_phase(gc_collector_t *gc) {
    gc_header_t **prev = &gc->all_objects;
    gc_header_t *o = gc->all_objects;
    while (o) {
        gc_header_t *next = o->gc_next;
        if (o->color == GC_WHITE) {
            *prev = next;
            size_t total = sizeof(gc_header_t) + o->size;
            gc->total_managed -= total; gc->object_count--;
            stats_track_free(&gc->stats, o->size);
            if (ALLOC_DEBUG) memset((void *)((uintptr_t)o + sizeof(gc_header_t)), POISON_FREE, o->size);
            o->magic = 0; free(o);
            gc->sweep_count++;
        } else {
            prev = &o->gc_next;
        }
        o = next;
    }
}

uint32_t gc_collect(gc_collector_t *gc) {
    if (!gc) return 0;
    uint32_t before = gc->object_count;
    gc_mark_phase(gc); gc_sweep_phase(gc);
    uint32_t collected = before - gc->object_count;
    gc->collection_count++; gc->live_count = gc->object_count; gc->generation++;
    gc->threshold = gc->total_managed * 3 / 2;
    if (gc->threshold < 65536) gc->threshold = 65536;
    return collected;
}

void gc_destroy(gc_collector_t *gc) {
    if (!gc) return;
    gc_header_t *o = gc->all_objects;
    while (o) { gc_header_t *n = o->gc_next; o->magic = 0; free(o); o = n; }
    gc->all_objects = NULL; gc->object_count = 0;
    free(gc->roots); gc->roots = NULL;
    free(gc->mark_stack); gc->mark_stack = NULL;
}

/* =========================================================================
 * Memory-Mapped File Support
 * ========================================================================= */
typedef enum {
    MMAP_READ = 0x01, MMAP_WRITE = 0x02, MMAP_EXEC = 0x04,
    MMAP_PRIVATE = 0x08, MMAP_SHARED = 0x10, MMAP_ANONYMOUS = 0x20,
} mmap_flags_t;

typedef struct mmap_region {
    void *addr; size_t length, offset;
    uint32_t flags; int fd; bool is_active; const char *tag;
} mmap_region_t;

typedef struct mmap_manager {
    mmap_region_t regions[MMAP_MAX_MAPPINGS];
    uint32_t active_count;
    size_t total_mapped;
    alloc_stats_t stats;
} mmap_manager_t;

alloc_error_t mmap_mgr_init(mmap_manager_t *m) {
    if (!m) return ALLOC_ERR_INVALID;
    memset(m, 0, sizeof(*m));
    return ALLOC_OK;
}

void *mmap_mgr_map(mmap_manager_t *m, size_t length, uint32_t flags,
                   int fd, size_t offset, const char *tag) {
    if (!m || length == 0) return NULL;
    if (m->active_count >= MMAP_MAX_MAPPINGS) { m->stats.failed_allocs++; return NULL; }
    size_t alen = ALIGN_UP(length, MMAP_ALIGN);
    void *addr = NULL;
#ifdef _WIN32
    DWORD protect = (flags & MMAP_WRITE) ?
        ((flags & MMAP_PRIVATE) ? PAGE_WRITECOPY : PAGE_READWRITE) : PAGE_READONLY;
    DWORD access = (flags & MMAP_WRITE) ?
        ((flags & MMAP_PRIVATE) ? FILE_MAP_COPY : FILE_MAP_WRITE) : FILE_MAP_READ;
    HANDLE fh = (fd >= 0) ? (HANDLE)(intptr_t)fd : INVALID_HANDLE_VALUE;
    HANDLE mapping;
    if (flags & MMAP_ANONYMOUS)
        mapping = CreateFileMapping(INVALID_HANDLE_VALUE, NULL, protect,
                    (DWORD)(alen >> 32), (DWORD)alen, NULL);
    else
        mapping = CreateFileMapping(fh, NULL, protect, 0, 0, NULL);
    if (!mapping) { m->stats.failed_allocs++; return NULL; }
    addr = MapViewOfFile(mapping, access, (DWORD)(offset >> 32), (DWORD)offset, alen);
    CloseHandle(mapping);
    if (!addr) { m->stats.failed_allocs++; return NULL; }
#else
    int prot = 0;
    if (flags & MMAP_READ)  prot |= PROT_READ;
    if (flags & MMAP_WRITE) prot |= PROT_WRITE;
    if (flags & MMAP_EXEC)  prot |= PROT_EXEC;
    int mf = 0;
    if (flags & MMAP_PRIVATE)   mf |= MAP_PRIVATE;
    if (flags & MMAP_SHARED)    mf |= MAP_SHARED;
    if (flags & MMAP_ANONYMOUS) mf |= MAP_ANONYMOUS;
    if (!mf) mf = MAP_PRIVATE;
    addr = mmap(NULL, alen, prot, mf, fd, (off_t)offset);
    if (addr == MAP_FAILED) { m->stats.failed_allocs++; return NULL; }
#endif
    int slot = -1;
    for (int i = 0; i < MMAP_MAX_MAPPINGS; i++)
        if (!m->regions[i].is_active) { slot = i; break; }
    ALLOC_ASSERT(slot >= 0, "no free mmap slot");
    m->regions[slot] = (mmap_region_t){ addr, alen, offset, flags, fd, true, tag };
    m->active_count++; m->total_mapped += alen;
    stats_track_alloc(&m->stats, alen);
    return addr;
}

alloc_error_t mmap_mgr_unmap(mmap_manager_t *m, void *addr) {
    if (!m || !addr) return ALLOC_ERR_INVALID;
    for (int i = 0; i < MMAP_MAX_MAPPINGS; i++) {
        if (m->regions[i].is_active && m->regions[i].addr == addr) {
            size_t len = m->regions[i].length;
#ifdef _WIN32
            UnmapViewOfFile(addr);
#else
            munmap(addr, len);
#endif
            m->regions[i].is_active = false;
            m->active_count--; m->total_mapped -= len;
            stats_track_free(&m->stats, len);
            return ALLOC_OK;
        }
    }
    return ALLOC_ERR_NOT_FOUND;
}

alloc_error_t mmap_mgr_sync(mmap_manager_t *m, void *addr, size_t length) {
    if (!m || !addr) return ALLOC_ERR_INVALID;
    for (int i = 0; i < MMAP_MAX_MAPPINGS; i++) {
        if (m->regions[i].is_active && m->regions[i].addr == addr) {
            size_t sl = length > 0 ? length : m->regions[i].length;
#ifdef _WIN32
            FlushViewOfFile(addr, sl);
#else
            msync(addr, sl, MS_SYNC);
#endif
            return ALLOC_OK;
        }
    }
    return ALLOC_ERR_NOT_FOUND;
}

void mmap_mgr_destroy(mmap_manager_t *m) {
    if (!m) return;
    for (int i = 0; i < MMAP_MAX_MAPPINGS; i++) {
        if (m->regions[i].is_active) {
#ifdef _WIN32
            UnmapViewOfFile(m->regions[i].addr);
#else
            munmap(m->regions[i].addr, m->regions[i].length);
#endif
            m->regions[i].is_active = false;
        }
    }
    m->active_count = 0; m->total_mapped = 0;
}

/* =========================================================================
 * Debug Allocator — red zones, poison bytes, double-free detection
 * ========================================================================= */
typedef struct debug_record {
    void *ptr; size_t size;
    const char *file, *func;
    int line; bool is_active;
} debug_record_t;

typedef struct debug_block_hdr {
    uint32_t magic;
    size_t user_size;
    uint32_t record_idx;
    uint8_t redzone_pre[REDZONE_SIZE];
} debug_block_hdr_t;

#define DBG_MAGIC_ALLOC 0xDB9A110C
#define DBG_MAGIC_FREE  0xDB9F1EED

typedef struct debug_allocator {
    debug_record_t records[DEBUG_MAX_RECORDS];
    uint32_t record_count, active_count;
    uint32_t double_free_count, overflow_count, corruption_count;
    bool poison_on_alloc, poison_on_free, check_redzones;
    alloc_stats_t stats;
} debug_allocator_t;

alloc_error_t debug_init(debug_allocator_t *da) {
    if (!da) return ALLOC_ERR_INVALID;
    memset(da, 0, sizeof(*da));
    da->poison_on_alloc = da->poison_on_free = da->check_redzones = true;
    return ALLOC_OK;
}

void *debug_alloc(debug_allocator_t *da, size_t size,
                  const char *file, int line, const char *func) {
    if (!da || size == 0) return NULL;
    size_t total = sizeof(debug_block_hdr_t) + size + REDZONE_SIZE;
    void *raw = malloc(total);
    if (!raw) { da->stats.failed_allocs++; return NULL; }
    debug_block_hdr_t *h = (debug_block_hdr_t *)raw;
    h->magic = DBG_MAGIC_ALLOC; h->user_size = size;
    memset(h->redzone_pre, REDZONE_FILL, REDZONE_SIZE);
    void *uptr = (void *)((uintptr_t)raw + sizeof(debug_block_hdr_t));
    memset((uint8_t *)uptr + size, REDZONE_FILL, REDZONE_SIZE);
    if (da->poison_on_alloc) memset(uptr, POISON_ALLOC, size);
    /* find free record slot */
    int idx = -1;
    for (uint32_t i = 0; i < DEBUG_MAX_RECORDS; i++)
        if (!da->records[i].is_active) { idx = (int)i; break; }
    if (idx >= 0) {
        h->record_idx = (uint32_t)idx;
        da->records[idx] = (debug_record_t){ uptr, size, file, func, line, true };
        da->active_count++;
    }
    da->record_count++;
    stats_track_alloc(&da->stats, size);
    return uptr;
}

alloc_error_t debug_check_block(debug_allocator_t *da, void *ptr) {
    if (!da || !ptr) return ALLOC_ERR_INVALID;
    debug_block_hdr_t *h = (debug_block_hdr_t *)((uintptr_t)ptr - sizeof(debug_block_hdr_t));
    if (h->magic == DBG_MAGIC_FREE) { da->double_free_count++; return ALLOC_ERR_DOUBLE_FREE; }
    if (h->magic != DBG_MAGIC_ALLOC) { da->corruption_count++; return ALLOC_ERR_CORRUPTED; }
    if (da->check_redzones) {
        for (int i = 0; i < REDZONE_SIZE; i++)
            if (h->redzone_pre[i] != REDZONE_FILL) { da->overflow_count++; return ALLOC_ERR_OVERFLOW; }
        uint8_t *post = (uint8_t *)ptr + h->user_size;
        for (int i = 0; i < REDZONE_SIZE; i++)
            if (post[i] != REDZONE_FILL) { da->overflow_count++; return ALLOC_ERR_OVERFLOW; }
    }
    return ALLOC_OK;
}

alloc_error_t debug_free(debug_allocator_t *da, void *ptr) {
    if (!da || !ptr) return ALLOC_ERR_INVALID;
    alloc_error_t err = debug_check_block(da, ptr);
    if (err != ALLOC_OK) return err;
    debug_block_hdr_t *h = (debug_block_hdr_t *)((uintptr_t)ptr - sizeof(debug_block_hdr_t));
    size_t usz = h->user_size; uint32_t ri = h->record_idx;
    h->magic = DBG_MAGIC_FREE;
    if (da->poison_on_free) memset(ptr, POISON_FREE, usz);
    if (ri < DEBUG_MAX_RECORDS && da->records[ri].is_active) {
        da->records[ri].is_active = false; da->active_count--;
    }
    stats_track_free(&da->stats, usz);
    return ALLOC_OK;
}

void debug_dump_leaks(debug_allocator_t *da, FILE *out) {
    if (!da || !out) return;
    uint32_t lc = 0; size_t lb = 0;
    fprintf(out, "\n=== MEMORY LEAK REPORT ===\n");
    for (uint32_t i = 0; i < DEBUG_MAX_RECORDS; i++) {
        if (da->records[i].is_active) {
            lc++; lb += da->records[i].size;
            fprintf(out, "  LEAK: %zu bytes at %p (%s:%d %s)\n",
                    da->records[i].size, da->records[i].ptr,
                    da->records[i].file ? da->records[i].file : "?",
                    da->records[i].line,
                    da->records[i].func ? da->records[i].func : "?");
        }
    }
    fprintf(out, "--- %u leak(s), %zu bytes | %u dbl-free, %u overflow, %u corrupt ---\n",
            lc, lb, da->double_free_count, da->overflow_count, da->corruption_count);
}

/* =========================================================================
 * Aligned Allocation
 * ========================================================================= */
typedef struct aligned_hdr {
    void *original; size_t total_size, user_size, alignment; uint32_t magic;
} aligned_hdr_t;

#define ALIGNED_MAGIC 0xA119ED00

void *aligned_alloc_impl(size_t size, size_t alignment) {
    if (size == 0 || !IS_POW2(alignment)) return NULL;
    if (alignment < sizeof(void *)) alignment = sizeof(void *);
    size_t total = size + alignment + sizeof(aligned_hdr_t);
    void *raw = malloc(total);
    if (!raw) return NULL;
    uintptr_t ra = (uintptr_t)raw + sizeof(aligned_hdr_t);
    uintptr_t aa = ALIGN_UP(ra, alignment);
    aligned_hdr_t *h = (aligned_hdr_t *)(aa - sizeof(aligned_hdr_t));
    h->original = raw; h->total_size = total;
    h->user_size = size; h->alignment = alignment; h->magic = ALIGNED_MAGIC;
    return (void *)aa;
}

void aligned_free_impl(void *ptr) {
    if (!ptr) return;
    aligned_hdr_t *h = (aligned_hdr_t *)((uintptr_t)ptr - sizeof(aligned_hdr_t));
    ALLOC_ASSERT(h->magic == ALIGNED_MAGIC, "aligned_free: bad pointer");
    h->magic = 0; free(h->original);
}

void *aligned_realloc_impl(void *ptr, size_t new_size, size_t alignment) {
    if (!ptr) return aligned_alloc_impl(new_size, alignment);
    if (new_size == 0) { aligned_free_impl(ptr); return NULL; }
    aligned_hdr_t *h = (aligned_hdr_t *)((uintptr_t)ptr - sizeof(aligned_hdr_t));
    if (h->magic != ALIGNED_MAGIC) return NULL;
    size_t old = h->user_size;
    size_t avail = h->total_size - ((uintptr_t)ptr - (uintptr_t)h->original);
    if (new_size <= avail) { h->user_size = new_size; return ptr; }
    void *np = aligned_alloc_impl(new_size, alignment);
    if (!np) return NULL;
    memcpy(np, ptr, MIN(old, new_size));
    aligned_free_impl(ptr);
    return np;
}

/* =========================================================================
 * Realloc with In-Place Expansion
 * ========================================================================= */
typedef struct realloc_hdr {
    size_t capacity, user_size;
    uint32_t magic, flags;
} realloc_hdr_t;

#define REALLOC_MAGIC 0xBEA110C8

typedef struct realloc_ctx {
    alloc_stats_t stats;
    size_t inplace_ok, inplace_fail;
    double growth_factor;
} realloc_ctx_t;

alloc_error_t realloc_ctx_init(realloc_ctx_t *c) {
    if (!c) return ALLOC_ERR_INVALID;
    memset(&c->stats, 0, sizeof(c->stats));
    c->inplace_ok = c->inplace_fail = 0;
    c->growth_factor = 1.5;
    return ALLOC_OK;
}

void *smart_malloc(realloc_ctx_t *c, size_t size) {
    if (!c || size == 0) return NULL;
    size_t cap = (size_t)(size * c->growth_factor);
    if (cap < size + 64) cap = size + 64;
    size_t total = sizeof(realloc_hdr_t) + cap;
    void *raw = malloc(total);
    if (!raw) { c->stats.failed_allocs++; return NULL; }
    realloc_hdr_t *h = (realloc_hdr_t *)raw;
    h->capacity = cap; h->user_size = size; h->magic = REALLOC_MAGIC; h->flags = 0;
    void *uptr = (void *)((uintptr_t)raw + sizeof(realloc_hdr_t));
    stats_track_alloc(&c->stats, size);
    return uptr;
}

void *smart_realloc(realloc_ctx_t *c, void *ptr, size_t new_size) {
    if (!c) return NULL;
    if (!ptr) return smart_malloc(c, new_size);
    realloc_hdr_t *h = (realloc_hdr_t *)((uintptr_t)ptr - sizeof(realloc_hdr_t));
    if (h->magic != REALLOC_MAGIC) return NULL;
    if (new_size == 0) {
        c->stats.current_usage -= h->user_size; c->stats.free_count++;
        h->magic = 0; free(h); return NULL;
    }
    c->stats.realloc_count++;
    size_t old = h->user_size;
    if (new_size <= h->capacity) {
        h->user_size = new_size; h->flags |= 1; c->inplace_ok++;
        if (new_size > old) c->stats.current_usage += (new_size - old);
        else c->stats.current_usage -= (old - new_size);
        if (c->stats.current_usage > c->stats.peak_usage) c->stats.peak_usage = c->stats.current_usage;
        return ptr;
    }
    c->inplace_fail++;
    void *np = smart_malloc(c, new_size);
    if (!np) return NULL;
    memcpy(np, ptr, MIN(old, new_size));
    c->stats.current_usage -= old; c->stats.free_count++;
    h->magic = 0; free(h);
    return np;
}

void smart_free(realloc_ctx_t *c, void *ptr) {
    if (!c || !ptr) return;
    realloc_hdr_t *h = (realloc_hdr_t *)((uintptr_t)ptr - sizeof(realloc_hdr_t));
    if (h->magic != REALLOC_MAGIC) return;
    stats_track_free(&c->stats, h->user_size);
    h->magic = 0; free(h);
}

/* =========================================================================
 * Reference Counting
 * ========================================================================= */
typedef void (*rc_dtor_fn)(void *obj);

typedef struct rc_header {
    uint32_t ref_count, weak_count, magic;
    size_t obj_size;
    rc_dtor_fn destructor;
    const char *type_name;
} rc_header_t;

#define RC_MAGIC 0x1EFC0017

typedef struct rc_weak_ref {
    rc_header_t *header;
    uint32_t generation;
} rc_weak_ref_t;

void *refcount_alloc(size_t size, rc_dtor_fn dtor, const char *type_name) {
    if (size == 0) return NULL;
    void *raw = calloc(1, sizeof(rc_header_t) + size);
    if (!raw) return NULL;
    rc_header_t *h = (rc_header_t *)raw;
    h->ref_count = 1; h->weak_count = 0; h->magic = RC_MAGIC;
    h->obj_size = size; h->destructor = dtor; h->type_name = type_name;
    return (void *)((uintptr_t)raw + sizeof(rc_header_t));
}

static rc_header_t *rc_hdr(void *obj) {
    if (!obj) return NULL;
    rc_header_t *h = (rc_header_t *)((uintptr_t)obj - sizeof(rc_header_t));
    return (h->magic == RC_MAGIC) ? h : NULL;
}

void *refcount_retain(void *obj) {
    if (!obj) return NULL;
    rc_header_t *h = rc_hdr(obj);
    if (!h) return NULL;
    if (h->ref_count < REFCOUNT_MAX) h->ref_count++;
    return obj;
}

void refcount_release(void *obj) {
    if (!obj) return;
    rc_header_t *h = rc_hdr(obj);
    if (!h) return;
    ALLOC_ASSERT(h->ref_count > 0, "refcount underflow");
    h->ref_count--;
    if (h->ref_count == 0) {
        if (h->destructor) h->destructor(obj);
        if (h->weak_count == 0) {
            if (ALLOC_DEBUG) memset(obj, POISON_FREE, h->obj_size);
            h->magic = 0; free(h);
        }
    }
}

uint32_t refcount_get(void *obj) {
    rc_header_t *h = rc_hdr(obj);
    return h ? h->ref_count : 0;
}

rc_weak_ref_t refcount_weak_create(void *obj) {
    rc_weak_ref_t w = { NULL, 0 };
    if (!obj) return w;
    rc_header_t *h = rc_hdr(obj);
    if (!h) return w;
    h->weak_count++;
    w.header = h; w.generation = h->ref_count;
    return w;
}

void *refcount_weak_lock(rc_weak_ref_t *w) {
    if (!w || !w->header) return NULL;
    if (w->header->magic != RC_MAGIC || w->header->ref_count == 0) return NULL;
    void *obj = (void *)((uintptr_t)w->header + sizeof(rc_header_t));
    refcount_retain(obj);
    return obj;
}

void refcount_weak_release(rc_weak_ref_t *w) {
    if (!w || !w->header) return;
    if (w->header->weak_count > 0) {
        w->header->weak_count--;
        if (w->header->ref_count == 0 && w->header->weak_count == 0) {
            w->header->magic = 0; free(w->header);
        }
    }
    w->header = NULL;
}

/* =========================================================================
 * Statistics Reporting
 * ========================================================================= */
typedef struct global_stats {
    alloc_stats_t buddy, slab, arena, freelist, pool, gc, mmap_s, debug_s, combined;
} global_stats_t;

static void stats_merge(alloc_stats_t *d, const alloc_stats_t *s) {
    d->total_allocated += s->total_allocated; d->total_freed += s->total_freed;
    d->current_usage += s->current_usage;
    if (s->peak_usage > d->peak_usage) d->peak_usage = s->peak_usage;
    d->alloc_count += s->alloc_count; d->free_count += s->free_count;
    d->realloc_count += s->realloc_count; d->failed_allocs += s->failed_allocs;
    d->coalesce_count += s->coalesce_count; d->split_count += s->split_count;
}

void stats_print(const alloc_stats_t *s, const char *label, FILE *out) {
    if (!s || !out) return;
    fprintf(out, "--- %s ---\n", label ? label : "Stats");
    fprintf(out, "  alloc=%llu free=%llu cur=%llu peak=%llu fail=%llu coal=%llu split=%llu frag=%.1f%%\n",
            (unsigned long long)s->alloc_count, (unsigned long long)s->free_count,
            (unsigned long long)s->current_usage, (unsigned long long)s->peak_usage,
            (unsigned long long)s->failed_allocs,
            (unsigned long long)s->coalesce_count, (unsigned long long)s->split_count,
            s->fragmentation_ratio * 100.0);
}

void stats_report(global_stats_t *gs, FILE *out) {
    if (!gs || !out) return;
    memset(&gs->combined, 0, sizeof(alloc_stats_t));
    stats_merge(&gs->combined, &gs->buddy); stats_merge(&gs->combined, &gs->slab);
    stats_merge(&gs->combined, &gs->arena); stats_merge(&gs->combined, &gs->freelist);
    stats_merge(&gs->combined, &gs->pool);  stats_merge(&gs->combined, &gs->gc);
    stats_merge(&gs->combined, &gs->mmap_s);
    fprintf(out, "\n====== ALLOCATOR REPORT ======\n");
    stats_print(&gs->buddy, "Buddy", out);     stats_print(&gs->slab, "Slab", out);
    stats_print(&gs->arena, "Arena", out);      stats_print(&gs->freelist, "FreeList", out);
    stats_print(&gs->pool, "Pool", out);        stats_print(&gs->gc, "GC", out);
    stats_print(&gs->mmap_s, "Mmap", out);
    stats_print(&gs->combined, "COMBINED", out);
    fprintf(out, "==============================\n\n");
}

/* =========================================================================
 * Unified Allocator Interface
 * ========================================================================= */
typedef enum {
    BACKEND_BUDDY, BACKEND_SLAB, BACKEND_ARENA, BACKEND_FREELIST,
    BACKEND_POOL, BACKEND_GC, BACKEND_SYSTEM,
} alloc_backend_t;

typedef struct unified_allocator {
    alloc_backend_t default_backend;
    buddy_allocator_t *buddy;
    slab_allocator_t *slab;
    arena_allocator_t *arena;
    freelist_allocator_t *freelist;
    pool_allocator_t *pool;
    gc_collector_t *gc;
    mmap_manager_t *mmap_mgr;
    debug_allocator_t *debug;
    realloc_ctx_t *realloc_ctx;
    global_stats_t gstats;
    bool debug_enabled, initialized;
} unified_allocator_t;

static unified_allocator_t g_allocator = { 0 };

alloc_error_t unified_init(unified_allocator_t *u, alloc_backend_t be) {
    if (!u) return ALLOC_ERR_INVALID;
    memset(u, 0, sizeof(*u));
    u->default_backend = be; u->debug_enabled = ALLOC_DEBUG; u->initialized = true;
    return ALLOC_OK;
}

void *unified_alloc(unified_allocator_t *u, size_t size) {
    if (!u || !u->initialized || size == 0) return NULL;
    if (u->debug_enabled && u->debug)
        return debug_alloc(u->debug, size, __FILE__, __LINE__, __func__);
    switch (u->default_backend) {
    case BACKEND_BUDDY:   return u->buddy ? buddy_alloc(u->buddy, size) : NULL;
    case BACKEND_SLAB:    return (u->slab && size <= SLAB_MAX_OBJ_SIZE) ? slab_alloc(u->slab, size) : NULL;
    case BACKEND_ARENA:   return u->arena ? arena_alloc(u->arena, size) : NULL;
    case BACKEND_FREELIST:return u->freelist ? freelist_alloc(u->freelist, size) : NULL;
    case BACKEND_POOL:    return (u->pool && size <= u->pool->obj_size) ? pool_alloc(u->pool) : NULL;
    case BACKEND_GC:      return u->gc ? gc_alloc(u->gc, size, NULL) : NULL;
    case BACKEND_SYSTEM:  return malloc(size);
    }
    return NULL;
}

alloc_error_t unified_free(unified_allocator_t *u, void *ptr) {
    if (!u || !u->initialized) return ALLOC_ERR_INVALID;
    if (!ptr) return ALLOC_OK;
    if (u->debug_enabled && u->debug) return debug_free(u->debug, ptr);
    switch (u->default_backend) {
    case BACKEND_BUDDY:    return u->buddy ? buddy_free(u->buddy, ptr) : ALLOC_ERR_INVALID;
    case BACKEND_SLAB:     free(ptr); return ALLOC_OK;
    case BACKEND_ARENA:    return ALLOC_OK; /* arena: bulk free only */
    case BACKEND_FREELIST: return u->freelist ? freelist_free(u->freelist, ptr) : ALLOC_ERR_INVALID;
    case BACKEND_POOL:     return u->pool ? pool_free(u->pool, ptr) : ALLOC_ERR_INVALID;
    case BACKEND_GC:       return ALLOC_OK;
    case BACKEND_SYSTEM:   free(ptr); return ALLOC_OK;
    }
    return ALLOC_ERR_INVALID;
}

void unified_destroy(unified_allocator_t *u) {
    if (!u) return;
    if (u->debug && u->debug_enabled) debug_dump_leaks(u->debug, stderr);
    if (u->buddy) buddy_destroy(u->buddy);
    if (u->slab) slab_destroy(u->slab);
    if (u->arena) arena_destroy(u->arena);
    if (u->pool) pool_destroy(u->pool);
    if (u->gc) gc_destroy(u->gc);
    if (u->mmap_mgr) mmap_mgr_destroy(u->mmap_mgr);
    u->initialized = false;
}

/* ---- Convenience Macros ---- */
#define ALLOC(sz)         unified_alloc(&g_allocator, (sz))
#define FREE(p)           unified_free(&g_allocator, (p))
#define ALLOC_T(T)        ((T *)unified_alloc(&g_allocator, sizeof(T)))
#define ALLOC_N(T, n)     ((T *)unified_alloc(&g_allocator, sizeof(T) * (n)))
#define RC_ALLOC(T, d)    ((T *)refcount_alloc(sizeof(T), (d), #T))
#define RC_RETAIN(p)      refcount_retain((p))
#define RC_RELEASE(p)     refcount_release((p))
#define RC_COUNT(p)       refcount_get((p))
#define DALLOC(da, sz)    debug_alloc((da), (sz), __FILE__, __LINE__, __func__)
#define DFREE(da, p)      debug_free((da), (p))
#define AL_ALLOC(sz, al)  aligned_alloc_impl((sz), (al))
#define AL_FREE(p)        aligned_free_impl((p))

/* =========================================================================
 * Introspection and Heap Walking
 * ========================================================================= */
typedef bool (*heap_walk_fn)(void *block, size_t size, bool is_free, void *ctx);

uint32_t freelist_walk(freelist_allocator_t *fl, heap_walk_fn cb, void *ctx) {
    if (!fl || !cb) return 0;
    uint32_t n = 0; fl_block_t *b = fl->head;
    while (b) {
        void *up = (void *)((uintptr_t)b + sizeof(fl_block_t));
        if (!cb(up, b->size, b->is_free, ctx)) break;
        n++; b = b->next;
    }
    return n;
}

uint32_t buddy_count_free(buddy_allocator_t *ba) {
    if (!ba) return 0;
    uint32_t t = 0;
    for (int i = 0; i < BUDDY_NUM_ORDERS; i++) {
        buddy_block_t *b = ba->free_lists[i];
        while (b) { t++; b = b->next; }
    }
    return t;
}

size_t buddy_largest_free(buddy_allocator_t *ba) {
    if (!ba) return 0;
    for (int i = BUDDY_NUM_ORDERS - 1; i >= 0; i--)
        if (ba->free_lists[i]) return buddy_order_sz(i + BUDDY_MIN_ORDER);
    return 0;
}

size_t arena_available(arena_allocator_t *a) {
    if (!a || !a->current) return 0;
    return a->current->capacity - a->current->used;
}

double pool_utilization(pool_allocator_t *p) {
    if (!p || p->central.total_slots == 0) return 0.0;
    uint32_t used = p->central.total_slots - p->central.free_count;
    for (uint32_t i = 0; i < p->num_caches; i++)
        if (p->caches[i].count <= used) used -= p->caches[i].count;
    return (double)used / (double)p->central.total_slots;
}

/* =========================================================================
 * Allocation Policy Engine
 * ========================================================================= */
typedef enum { POLICY_SPEED, POLICY_MEMORY, POLICY_BALANCED, POLICY_DEBUG } alloc_policy_t;

typedef struct policy_config {
    alloc_policy_t policy;
    size_t small_threshold, large_threshold;
    bool enable_pooling, enable_coalescing, enable_stats;
    double fragmentation_limit;
    uint32_t gc_threshold_factor;
} policy_config_t;

void policy_default(policy_config_t *cfg, alloc_policy_t pol) {
    if (!cfg) return;
    cfg->policy = pol; cfg->enable_stats = true;
    switch (pol) {
    case POLICY_SPEED:
        cfg->small_threshold = 256; cfg->large_threshold = 4096;
        cfg->enable_pooling = true; cfg->enable_coalescing = false;
        cfg->fragmentation_limit = 0.5; cfg->gc_threshold_factor = 4; break;
    case POLICY_MEMORY:
        cfg->small_threshold = 64; cfg->large_threshold = 1024;
        cfg->enable_pooling = false; cfg->enable_coalescing = true;
        cfg->fragmentation_limit = 0.1; cfg->gc_threshold_factor = 1; break;
    case POLICY_BALANCED:
        cfg->small_threshold = 128; cfg->large_threshold = 2048;
        cfg->enable_pooling = true; cfg->enable_coalescing = true;
        cfg->fragmentation_limit = 0.3; cfg->gc_threshold_factor = 2; break;
    case POLICY_DEBUG:
        cfg->small_threshold = 128; cfg->large_threshold = 2048;
        cfg->enable_pooling = false; cfg->enable_coalescing = true;
        cfg->fragmentation_limit = 0.3; cfg->gc_threshold_factor = 1; break;
    }
}

alloc_backend_t policy_select_backend(const policy_config_t *cfg, size_t size) {
    if (!cfg || cfg->policy == POLICY_DEBUG) return BACKEND_SYSTEM;
    if (size <= cfg->small_threshold) return cfg->enable_pooling ? BACKEND_POOL : BACKEND_SLAB;
    if (size <= cfg->large_threshold) return BACKEND_BUDDY;
    return BACKEND_FREELIST;
}

void *policy_alloc(unified_allocator_t *u, const policy_config_t *cfg, size_t size) {
    if (!u || !cfg || size == 0) return NULL;
    alloc_backend_t saved = u->default_backend;
    u->default_backend = policy_select_backend(cfg, size);
    void *ptr = unified_alloc(u, size);
    u->default_backend = saved;
    return ptr;
}

/* =========================================================================
 * Compaction and Defragmentation
 * ========================================================================= */
typedef struct compact_handle {
    void **user_ptr; void *current; size_t size; uint32_t flags;
} compact_handle_t;

typedef struct compact_state {
    compact_handle_t *handles;
    uint32_t count, capacity;
    size_t bytes_moved; uint32_t objects_moved;
} compact_state_t;

alloc_error_t compact_init(compact_state_t *cs, uint32_t cap) {
    if (!cs || cap == 0) return ALLOC_ERR_INVALID;
    cs->handles = (compact_handle_t *)calloc(cap, sizeof(compact_handle_t));
    if (!cs->handles) return ALLOC_ERR_NOMEM;
    cs->count = 0; cs->capacity = cap; cs->bytes_moved = 0; cs->objects_moved = 0;
    return ALLOC_OK;
}

alloc_error_t compact_register(compact_state_t *cs, void **uptr, size_t size) {
    if (!cs || !uptr || !*uptr) return ALLOC_ERR_INVALID;
    if (cs->count >= cs->capacity) return ALLOC_ERR_FULL;
    cs->handles[cs->count++] = (compact_handle_t){ uptr, *uptr, size, 0 };
    return ALLOC_OK;
}

static int compact_cmp(const void *a, const void *b) {
    const compact_handle_t *ha = (const compact_handle_t *)a;
    const compact_handle_t *hb = (const compact_handle_t *)b;
    if ((uintptr_t)ha->current < (uintptr_t)hb->current) return -1;
    if ((uintptr_t)ha->current > (uintptr_t)hb->current) return 1;
    return 0;
}

uint32_t compact_run(compact_state_t *cs, arena_allocator_t *dest) {
    if (!cs || !dest || cs->count == 0) return 0;
    qsort(cs->handles, cs->count, sizeof(compact_handle_t), compact_cmp);
    uint32_t moved = 0;
    for (uint32_t i = 0; i < cs->count; i++) {
        compact_handle_t *h = &cs->handles[i];
        void *nl = arena_alloc(dest, h->size);
        if (!nl) continue;
        memcpy(nl, h->current, h->size);
        *(h->user_ptr) = nl; h->current = nl;
        cs->bytes_moved += h->size; moved++;
    }
    cs->objects_moved += moved;
    return moved;
}

void compact_destroy(compact_state_t *cs) {
    if (cs && cs->handles) { free(cs->handles); cs->handles = NULL; cs->count = 0; }
}

/* =========================================================================
 * Batch Operations
 * ========================================================================= */
typedef struct batch_result {
    void **ptrs;
    uint32_t count, capacity, failed;
} batch_result_t;

alloc_error_t batch_init(batch_result_t *b, uint32_t cap) {
    if (!b || cap == 0) return ALLOC_ERR_INVALID;
    b->ptrs = (void **)calloc(cap, sizeof(void *));
    if (!b->ptrs) return ALLOC_ERR_NOMEM;
    b->count = 0; b->capacity = cap; b->failed = 0;
    return ALLOC_OK;
}

uint32_t batch_buddy_alloc(buddy_allocator_t *ba, batch_result_t *b,
                           size_t size, uint32_t count) {
    if (!ba || !b) return 0;
    uint32_t ok = 0;
    for (uint32_t i = 0; i < count && b->count < b->capacity; i++) {
        void *p = buddy_alloc(ba, size);
        if (p) { b->ptrs[b->count++] = p; ok++; } else b->failed++;
    }
    return ok;
}

uint32_t batch_buddy_free(buddy_allocator_t *ba, batch_result_t *b) {
    if (!ba || !b) return 0;
    uint32_t freed = 0;
    for (uint32_t i = 0; i < b->count; i++) {
        if (b->ptrs[i] && buddy_free(ba, b->ptrs[i]) == ALLOC_OK) freed++;
        b->ptrs[i] = NULL;
    }
    b->count = 0;
    return freed;
}

uint32_t batch_slab_alloc(slab_allocator_t *sa, batch_result_t *b,
                          size_t size, uint32_t count) {
    if (!sa || !b) return 0;
    uint32_t ok = 0;
    for (uint32_t i = 0; i < count && b->count < b->capacity; i++) {
        void *p = slab_alloc(sa, size);
        if (p) { b->ptrs[b->count++] = p; ok++; } else b->failed++;
    }
    return ok;
}

uint32_t batch_pool_alloc(pool_allocator_t *pool, batch_result_t *b, uint32_t count) {
    if (!pool || !b) return 0;
    uint32_t ok = 0;
    for (uint32_t i = 0; i < count && b->count < b->capacity; i++) {
        void *p = pool_alloc(pool);
        if (p) { b->ptrs[b->count++] = p; ok++; } else b->failed++;
    }
    return ok;
}

void batch_destroy(batch_result_t *b) {
    if (b && b->ptrs) { free(b->ptrs); b->ptrs = NULL; b->count = b->capacity = 0; }
}

/* =========================================================================
 * Memory Diagnostic Utilities
 * ========================================================================= */

/* Hex dump of memory region */
void mem_hexdump(const void *addr, size_t len, FILE *out) {
    if (!addr || !out || len == 0) return;
    const uint8_t *p = (const uint8_t *)addr;
    for (size_t i = 0; i < len; i += 16) {
        fprintf(out, "  %08zx: ", i);
        for (size_t j = 0; j < 16; j++) {
            if (i + j < len) fprintf(out, "%02x ", p[i + j]);
            else fprintf(out, "   ");
            if (j == 7) fprintf(out, " ");
        }
        fprintf(out, " |");
        for (size_t j = 0; j < 16 && i + j < len; j++) {
            uint8_t c = p[i + j];
            fprintf(out, "%c", (c >= 0x20 && c < 0x7f) ? c : '.');
        }
        fprintf(out, "|\n");
    }
}

/* Check if memory region is filled with a specific byte */
bool mem_check_fill(const void *addr, size_t len, uint8_t expected) {
    if (!addr) return false;
    const uint8_t *p = (const uint8_t *)addr;
    for (size_t i = 0; i < len; i++) {
        if (p[i] != expected) return false;
    }
    return true;
}

/* Calculate memory overhead for each allocator type */
typedef struct overhead_report {
    size_t buddy_overhead;    /* per-alloc header + split map */
    size_t slab_overhead;     /* page headers + free list pointers */
    size_t freelist_overhead; /* per-block header + redzones */
    size_t pool_overhead;     /* central + thread cache structs */
    size_t gc_overhead;       /* gc_header per object + roots + mark stack */
    size_t debug_overhead;    /* debug header + 2x redzone + records */
    size_t aligned_overhead;  /* alignment padding + header */
    size_t realloc_overhead;  /* growth factor headroom */
} overhead_report_t;

void calc_overhead(overhead_report_t *r) {
    if (!r) return;
    r->buddy_overhead = sizeof(buddy_block_t);
    r->slab_overhead = sizeof(slab_page_t) + sizeof(slab_obj_t);
    r->freelist_overhead = sizeof(fl_block_t);
#if ALLOC_DEBUG
    r->freelist_overhead += REDZONE_SIZE;
#endif
    r->pool_overhead = sizeof(pool_central_t) + sizeof(pool_tcache_t);
    r->gc_overhead = sizeof(gc_header_t);
    r->debug_overhead = sizeof(debug_block_hdr_t) + REDZONE_SIZE;
    r->aligned_overhead = sizeof(aligned_hdr_t);
    r->realloc_overhead = sizeof(realloc_hdr_t);
}

void print_overhead(const overhead_report_t *r, FILE *out) {
    if (!r || !out) return;
    fprintf(out, "\n=== Per-Allocation Overhead ===\n");
    fprintf(out, "  Buddy:    %zu bytes\n", r->buddy_overhead);
    fprintf(out, "  Slab:     %zu bytes\n", r->slab_overhead);
    fprintf(out, "  FreeList: %zu bytes\n", r->freelist_overhead);
    fprintf(out, "  Pool:     %zu bytes (central+tcache)\n", r->pool_overhead);
    fprintf(out, "  GC:       %zu bytes\n", r->gc_overhead);
    fprintf(out, "  Debug:    %zu bytes\n", r->debug_overhead);
    fprintf(out, "  Aligned:  %zu bytes\n", r->aligned_overhead);
    fprintf(out, "  Realloc:  %zu bytes\n", r->realloc_overhead);
    fprintf(out, "==============================\n\n");
}

/* =========================================================================
 * Version and Feature Query
 * ========================================================================= */
#define ALLOC_VERSION_MAJOR  1
#define ALLOC_VERSION_MINOR  4
#define ALLOC_VERSION_PATCH  0

typedef struct alloc_features {
    bool has_buddy;
    bool has_slab;
    bool has_arena;
    bool has_freelist;
    bool has_pool;
    bool has_gc;
    bool has_mmap;
    bool has_refcount;
    bool has_debug;
    bool has_aligned;
    bool has_realloc;
    bool has_compaction;
    bool has_policy;
    int  version_major;
    int  version_minor;
    int  version_patch;
} alloc_features_t;

alloc_features_t alloc_query_features(void) {
    alloc_features_t f;
    f.has_buddy = true;
    f.has_slab = true;
    f.has_arena = true;
    f.has_freelist = true;
    f.has_pool = true;
    f.has_gc = true;
    f.has_mmap = true;
    f.has_refcount = true;
    f.has_debug = ALLOC_DEBUG;
    f.has_aligned = true;
    f.has_realloc = true;
    f.has_compaction = true;
    f.has_policy = true;
    f.version_major = ALLOC_VERSION_MAJOR;
    f.version_minor = ALLOC_VERSION_MINOR;
    f.version_patch = ALLOC_VERSION_PATCH;
    return f;
}

void alloc_print_features(FILE *out) {
    if (!out) return;
    alloc_features_t f = alloc_query_features();
    fprintf(out, "Unified Allocator v%d.%d.%d\n", f.version_major, f.version_minor, f.version_patch);
    fprintf(out, "Features: buddy=%d slab=%d arena=%d freelist=%d pool=%d\n",
            f.has_buddy, f.has_slab, f.has_arena, f.has_freelist, f.has_pool);
    fprintf(out, "          gc=%d mmap=%d refcount=%d debug=%d aligned=%d\n",
            f.has_gc, f.has_mmap, f.has_refcount, f.has_debug, f.has_aligned);
    fprintf(out, "          realloc=%d compact=%d policy=%d\n",
            f.has_realloc, f.has_compaction, f.has_policy);
}

/* =========================================================================
 * Self-Test Suite (compile with -DALLOC_SELF_TEST)
 * ========================================================================= */
#ifdef ALLOC_SELF_TEST

typedef struct tree_node {
    int value;
    struct tree_node *left, *right;
} tree_node_t;

static void tree_trace(void *obj, void (*mark)(void *)) {
    tree_node_t *n = (tree_node_t *)obj;
    if (n->left) mark(n->left);
    if (n->right) mark(n->right);
}

typedef struct rc_buffer {
    char *data; size_t len, cap;
} rc_buffer_t;

static void rc_buf_dtor(void *obj) {
    rc_buffer_t *b = (rc_buffer_t *)obj;
    if (b->data) { free(b->data); b->data = NULL; }
}

static int test_buddy(void) {
    printf("Test: Buddy ... ");
    size_t sz = 1 << 20;
    void *heap = calloc(1, sz); if (!heap) return 1;
    buddy_allocator_t ba;
    assert(buddy_init(&ba, heap, sz) == ALLOC_OK);
    void *a = buddy_alloc(&ba, 100), *b = buddy_alloc(&ba, 200), *c = buddy_alloc(&ba, 50);
    assert(a && b && c);
    assert(buddy_free(&ba, b) == ALLOC_OK);
    assert(buddy_free(&ba, a) == ALLOC_OK);
    assert(buddy_free(&ba, c) == ALLOC_OK);
    assert(buddy_free(&ba, a) == ALLOC_ERR_DOUBLE_FREE);
    buddy_destroy(&ba); free(heap);
    printf("OK (allocs=%llu coal=%llu)\n",
           (unsigned long long)ba.stats.alloc_count, (unsigned long long)ba.stats.coalesce_count);
    return 0;
}

static int test_slab(void) {
    printf("Test: Slab ... ");
    slab_allocator_t sa; assert(slab_init(&sa) == ALLOC_OK);
    void *objs[100];
    for (int i = 0; i < 100; i++) { objs[i] = slab_alloc(&sa, 64); assert(objs[i]); }
    for (int i = 0; i < 100; i++) assert(slab_free(&sa, objs[i], 64) == ALLOC_OK);
    slab_destroy(&sa);
    printf("OK\n");
    return 0;
}

static int test_arena(void) {
    printf("Test: Arena ... ");
    arena_allocator_t ar; assert(arena_init(&ar, 4096) == ALLOC_OK);
    for (int i = 0; i < 500; i++) assert(arena_alloc(&ar, 32 + (i % 128)));
    void *al = arena_alloc_aligned(&ar, 256, 64);
    assert(al && ((uintptr_t)al % 64) == 0);
    arena_reset(&ar); assert(ar.stats.current_usage == 0);
    assert(arena_alloc(&ar, 100));
    arena_destroy(&ar);
    printf("OK (chunks=%u)\n", ar.chunk_count);
    return 0;
}

static int test_freelist(void) {
    printf("Test: FreeList ... ");
    size_t sz = 64 * 1024;
    void *heap = calloc(1, sz); if (!heap) return 1;
    fit_strategy_t strats[] = { FIT_FIRST, FIT_BEST, FIT_NEXT };
    const char *names[] = { "first", "best", "next" };
    for (int s = 0; s < 3; s++) {
        freelist_allocator_t fl;
        assert(freelist_init(&fl, heap, sz, strats[s]) == ALLOC_OK);
        void *a = freelist_alloc(&fl, 128), *b = freelist_alloc(&fl, 256);
        void *c = freelist_alloc(&fl, 64);
        assert(a && b && c);
        assert(freelist_free(&fl, b) == ALLOC_OK);
        assert(freelist_free(&fl, a) == ALLOC_OK);
        assert(freelist_free(&fl, c) == ALLOC_OK);
        double frag = freelist_fragmentation(&fl);
        printf("%s(frag=%.0f%%) ", names[s], frag * 100);
        memset(heap, 0, sz);
    }
    free(heap);
    printf("OK\n");
    return 0;
}

static int test_pool(void) {
    printf("Test: Pool ... ");
    pool_allocator_t pool;
    assert(pool_init(&pool, 48, 1024) == ALLOC_OK);
    void *slots[200];
    for (int i = 0; i < 200; i++) { slots[i] = pool_alloc(&pool); assert(slots[i]); }
    for (int i = 0; i < 200; i++) assert(pool_free(&pool, slots[i]) == ALLOC_OK);
    pool_destroy(&pool);
    printf("OK\n");
    return 0;
}

static int test_gc(void) {
    printf("Test: GC ... ");
    gc_collector_t gc; assert(gc_init(&gc, 1024) == ALLOC_OK);
    tree_node_t *root = NULL;
    gc_add_root(&gc, (void **)&root, "root");
    root = (tree_node_t *)gc_alloc(&gc, sizeof(tree_node_t), tree_trace);
    root->value = 1;
    root->left = (tree_node_t *)gc_alloc(&gc, sizeof(tree_node_t), tree_trace);
    root->left->value = 2; root->left->left = root->left->right = NULL;
    root->right = (tree_node_t *)gc_alloc(&gc, sizeof(tree_node_t), tree_trace);
    root->right->value = 3; root->right->left = root->right->right = NULL;
    for (int i = 0; i < 10; i++) gc_alloc(&gc, 64, NULL); /* garbage */
    uint32_t c1 = gc_collect(&gc);
    assert(gc.object_count == 3);
    root = NULL;
    uint32_t c2 = gc_collect(&gc);
    assert(gc.object_count == 0);
    gc_destroy(&gc);
    printf("OK (collected %u+%u)\n", c1, c2);
    return 0;
}

static int test_refcount(void) {
    printf("Test: Refcount ... ");
    rc_buffer_t *buf = RC_ALLOC(rc_buffer_t, rc_buf_dtor);
    assert(buf && RC_COUNT(buf) == 1);
    buf->cap = 256; buf->data = (char *)malloc(buf->cap);
    buf->len = snprintf(buf->data, buf->cap, "hello refcount");
    RC_RETAIN(buf); assert(RC_COUNT(buf) == 2);
    rc_weak_ref_t weak = refcount_weak_create(buf);
    void *locked = refcount_weak_lock(&weak);
    assert(locked == buf && RC_COUNT(buf) == 3);
    RC_RELEASE(locked);
    RC_RELEASE(buf); assert(RC_COUNT(buf) == 1);
    RC_RELEASE(buf);
    assert(refcount_weak_lock(&weak) == NULL);
    refcount_weak_release(&weak);
    printf("OK\n");
    return 0;
}

static int test_aligned(void) {
    printf("Test: Aligned ... ");
    size_t aligns[] = { 16, 32, 64, 128, 256, 512, 1024, 4096 };
    for (int i = 0; i < 8; i++) {
        void *p = AL_ALLOC(1000, aligns[i]);
        assert(p && ((uintptr_t)p % aligns[i]) == 0);
        void *q = aligned_realloc_impl(p, 2000, aligns[i]);
        assert(q && ((uintptr_t)q % aligns[i]) == 0);
        AL_FREE(q);
    }
    printf("OK\n");
    return 0;
}

static int test_realloc(void) {
    printf("Test: Realloc ... ");
    realloc_ctx_t ctx; realloc_ctx_init(&ctx);
    void *p = smart_malloc(&ctx, 100); assert(p);
    void *q = smart_realloc(&ctx, p, 120); assert(q);
    void *r = smart_realloc(&ctx, q, 10000); assert(r);
    printf("inplace=%zu relocated=%zu ", ctx.inplace_ok, ctx.inplace_fail);
    smart_free(&ctx, r);
    printf("OK\n");
    return 0;
}

static int test_debug(void) {
    printf("Test: Debug ... ");
    debug_allocator_t da; debug_init(&da);
    void *a = DALLOC(&da, 100), *b = DALLOC(&da, 200), *c = DALLOC(&da, 50);
    assert(a && b && c);
    assert(debug_check_block(&da, a) == ALLOC_OK);
    assert(debug_free(&da, b) == ALLOC_OK);
    assert(debug_free(&da, b) == ALLOC_ERR_DOUBLE_FREE);
    debug_free(&da, a); debug_free(&da, c);
    printf("OK (dbl_free=%u)\n", da.double_free_count);
    return 0;
}

static int test_mmap(void) {
    printf("Test: Mmap ... ");
    mmap_manager_t mgr; mmap_mgr_init(&mgr);
    void *region = mmap_mgr_map(&mgr, 8192,
        MMAP_READ | MMAP_WRITE | MMAP_PRIVATE | MMAP_ANONYMOUS, -1, 0, "test");
    if (region) {
        memset(region, 0x42, 4096);
        assert(mmap_mgr_unmap(&mgr, region) == ALLOC_OK);
        printf("OK\n");
    } else {
        printf("SKIP (platform)\n");
    }
    mmap_mgr_destroy(&mgr);
    return 0;
}

static int test_batch(void) {
    printf("Test: Batch ... ");
    size_t sz = 1 << 20;
    void *heap = calloc(1, sz); if (!heap) return 1;
    buddy_allocator_t ba;
    assert(buddy_init(&ba, heap, sz) == ALLOC_OK);
    batch_result_t batch;
    assert(batch_init(&batch, 100) == ALLOC_OK);
    uint32_t n = batch_buddy_alloc(&ba, &batch, 64, 50);
    assert(n == 50 && batch.count == 50);
    uint32_t f = batch_buddy_free(&ba, &batch);
    assert(f == 50 && batch.count == 0);
    batch_destroy(&batch);
    buddy_destroy(&ba); free(heap);
    printf("OK\n");
    return 0;
}

static int test_policy(void) {
    printf("Test: Policy ... ");
    policy_config_t cfg;
    policy_default(&cfg, POLICY_SPEED);
    assert(policy_select_backend(&cfg, 32) == BACKEND_POOL);
    assert(policy_select_backend(&cfg, 1024) == BACKEND_BUDDY);
    assert(policy_select_backend(&cfg, 8192) == BACKEND_FREELIST);
    policy_default(&cfg, POLICY_DEBUG);
    assert(policy_select_backend(&cfg, 100) == BACKEND_SYSTEM);
    printf("OK\n");
    return 0;
}

static int test_overhead(void) {
    printf("Test: Overhead ... ");
    overhead_report_t r;
    calc_overhead(&r);
    assert(r.buddy_overhead > 0);
    assert(r.gc_overhead > 0);
    print_overhead(&r, stdout);
    return 0;
}

int main(void) {
    printf("\n========================================\n");
    printf("  Unified Allocator v%d.%d.%d — Self-Test\n",
           ALLOC_VERSION_MAJOR, ALLOC_VERSION_MINOR, ALLOC_VERSION_PATCH);
    printf("========================================\n\n");

    alloc_print_features(stdout);
    printf("\n");

    int fail = 0;
    fail += test_buddy();
    fail += test_slab();
    fail += test_arena();
    fail += test_freelist();
    fail += test_pool();
    fail += test_gc();
    fail += test_refcount();
    fail += test_aligned();
    fail += test_realloc();
    fail += test_debug();
    fail += test_mmap();
    fail += test_batch();
    fail += test_policy();
    fail += test_overhead();

    global_stats_t gs = { 0 };
    stats_report(&gs, stdout);

    printf("\n========================================\n");
    printf("  %s\n", fail == 0 ? "ALL TESTS PASSED" : "SOME TESTS FAILED");
    printf("========================================\n\n");
    return fail;
}

#endif /* ALLOC_SELF_TEST */
