// Concurrent LRU cache with TTL, sharding, and eviction policies.
// Production-grade implementation with atomic operations and lock striping.

use std::collections::HashMap;
use std::hash::{Hash, Hasher};
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::{Arc, RwLock, Mutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use std::fmt;
use std::thread;

// ─── Configuration ─────────────────────────────────────────────────

const DEFAULT_SHARD_COUNT: usize = 16;
const DEFAULT_MAX_ENTRIES: usize = 10_000;
const DEFAULT_TTL_SECONDS: u64 = 300;
const CLEANUP_INTERVAL_SECONDS: u64 = 30;
const MAX_KEY_SIZE: usize = 256;
const MAX_VALUE_SIZE: usize = 1_048_576; // 1MB
const EVICTION_BATCH_SIZE: usize = 100;

// ─── Error Types ───────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub enum CacheError {
    KeyTooLarge(usize),
    ValueTooLarge(usize),
    KeyNotFound,
    ShardLockPoisoned,
    CapacityExceeded,
    SerializationError(String),
}

impl fmt::Display for CacheError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CacheError::KeyTooLarge(size) => write!(f, "key too large: {} bytes (max: {})", size, MAX_KEY_SIZE),
            CacheError::ValueTooLarge(size) => write!(f, "value too large: {} bytes (max: {})", size, MAX_VALUE_SIZE),
            CacheError::KeyNotFound => write!(f, "key not found"),
            CacheError::ShardLockPoisoned => write!(f, "shard lock poisoned"),
            CacheError::CapacityExceeded => write!(f, "cache capacity exceeded"),
            CacheError::SerializationError(msg) => write!(f, "serialization error: {}", msg),
        }
    }
}

impl std::error::Error for CacheError {}

// ─── Eviction Policy ──────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum EvictionPolicy {
    LRU,       // Least Recently Used
    LFU,       // Least Frequently Used
    FIFO,      // First In First Out
    Random,    // Random eviction
    TTL,       // Time-based only (no capacity eviction)
}

impl Default for EvictionPolicy {
    fn default() -> Self {
        EvictionPolicy::LRU
    }
}

// ─── Cache Entry ───────────────────────────────────────────────────

#[derive(Debug, Clone)]
struct CacheEntry<V: Clone> {
    value: V,
    created_at: Instant,
    last_accessed: Instant,
    access_count: u64,
    ttl: Duration,
    size_bytes: usize,
    version: u64,
}

impl<V: Clone> CacheEntry<V> {
    fn new(value: V, ttl: Duration, size_bytes: usize) -> Self {
        let now = Instant::now();
        CacheEntry {
            value,
            created_at: now,
            last_accessed: now,
            access_count: 1,
            ttl,
            size_bytes,
            version: 1,
        }
    }

    fn is_expired(&self) -> bool {
        self.created_at.elapsed() > self.ttl
    }

    fn touch(&mut self) {
        self.last_accessed = Instant::now();
        self.access_count += 1;
    }

    fn age(&self) -> Duration {
        self.created_at.elapsed()
    }

    fn idle_time(&self) -> Duration {
        self.last_accessed.elapsed()
    }
}

// ─── Shard ─────────────────────────────────────────────────────────

struct Shard<K: Hash + Eq + Clone, V: Clone> {
    entries: HashMap<K, CacheEntry<V>>,
    max_entries: usize,
    policy: EvictionPolicy,
    total_size: usize,
    max_size: usize,
    hit_count: AtomicU64,
    miss_count: AtomicU64,
    eviction_count: AtomicU64,
}

impl<K: Hash + Eq + Clone + fmt::Debug, V: Clone> Shard<K, V> {
    fn new(max_entries: usize, policy: EvictionPolicy, max_size: usize) -> Self {
        Shard {
            entries: HashMap::with_capacity(max_entries / 4),
            max_entries,
            policy,
            total_size: 0,
            max_size,
            hit_count: AtomicU64::new(0),
            miss_count: AtomicU64::new(0),
            eviction_count: AtomicU64::new(0),
        }
    }

    fn get(&mut self, key: &K) -> Option<&V> {
        if let Some(entry) = self.entries.get_mut(key) {
            if entry.is_expired() {
                self.total_size -= entry.size_bytes;
                self.entries.remove(key);
                self.miss_count.fetch_add(1, Ordering::Relaxed);
                return None;
            }
            entry.touch();
            self.hit_count.fetch_add(1, Ordering::Relaxed);
            Some(&entry.value)
        } else {
            self.miss_count.fetch_add(1, Ordering::Relaxed);
            None
        }
    }

    fn insert(&mut self, key: K, value: V, ttl: Duration, size: usize) -> Result<(), CacheError> {
        // Remove old entry if exists
        if let Some(old) = self.entries.remove(&key) {
            self.total_size -= old.size_bytes;
        }

        // Check capacity and evict if needed
        while self.entries.len() >= self.max_entries || self.total_size + size > self.max_size {
            if !self.evict_one() {
                return Err(CacheError::CapacityExceeded);
            }
        }

        let entry = CacheEntry::new(value, ttl, size);
        self.total_size += size;
        self.entries.insert(key, entry);
        Ok(())
    }

    fn remove(&mut self, key: &K) -> Option<V> {
        if let Some(entry) = self.entries.remove(key) {
            self.total_size -= entry.size_bytes;
            Some(entry.value)
        } else {
            None
        }
    }

    fn evict_one(&mut self) -> bool {
        if self.entries.is_empty() {
            return false;
        }

        let victim_key = match self.policy {
            EvictionPolicy::LRU => {
                self.entries.iter()
                    .min_by_key(|(_, e)| e.last_accessed)
                    .map(|(k, _)| k.clone())
            }
            EvictionPolicy::LFU => {
                self.entries.iter()
                    .min_by_key(|(_, e)| e.access_count)
                    .map(|(k, _)| k.clone())
            }
            EvictionPolicy::FIFO => {
                self.entries.iter()
                    .min_by_key(|(_, e)| e.created_at)
                    .map(|(k, _)| k.clone())
            }
            EvictionPolicy::Random => {
                // Deterministic "random" using entry count as seed
                let idx = self.eviction_count.load(Ordering::Relaxed) as usize % self.entries.len();
                self.entries.keys().nth(idx).cloned()
            }
            EvictionPolicy::TTL => {
                // Only evict expired entries
                self.entries.iter()
                    .filter(|(_, e)| e.is_expired())
                    .min_by_key(|(_, e)| e.created_at)
                    .map(|(k, _)| k.clone())
            }
        };

        if let Some(key) = victim_key {
            if let Some(entry) = self.entries.remove(&key) {
                self.total_size -= entry.size_bytes;
                self.eviction_count.fetch_add(1, Ordering::Relaxed);
                return true;
            }
        }
        false
    }

    fn cleanup_expired(&mut self) -> usize {
        let expired: Vec<K> = self.entries.iter()
            .filter(|(_, e)| e.is_expired())
            .map(|(k, _)| k.clone())
            .collect();

        let count = expired.len();
        for key in expired {
            if let Some(entry) = self.entries.remove(&key) {
                self.total_size -= entry.size_bytes;
            }
        }
        count
    }

    fn len(&self) -> usize {
        self.entries.len()
    }

    fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    fn clear(&mut self) {
        self.entries.clear();
        self.total_size = 0;
    }
}

// ─── Cache Stats ───────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct CacheStats {
    pub total_entries: usize,
    pub total_size_bytes: usize,
    pub hit_count: u64,
    pub miss_count: u64,
    pub eviction_count: u64,
    pub hit_rate: f64,
    pub shard_distribution: Vec<usize>,
    pub avg_entry_age_ms: u64,
    pub max_entry_age_ms: u64,
}

impl fmt::Display for CacheStats {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Cache[entries={}, size={}KB, hit_rate={:.1}%, evictions={}]",
            self.total_entries,
            self.total_size_bytes / 1024,
            self.hit_rate * 100.0,
            self.eviction_count
        )
    }
}

// ─── Sharded Cache ─────────────────────────────────────────────────

pub struct ShardedCache<K: Hash + Eq + Clone + fmt::Debug + Send + Sync + 'static,
                        V: Clone + Send + Sync + 'static> {
    shards: Vec<RwLock<Shard<K, V>>>,
    shard_count: usize,
    default_ttl: Duration,
    max_key_size: usize,
    max_value_size: usize,
    created_at: Instant,
    operation_count: AtomicU64,
    cleanup_handle: Option<thread::JoinHandle<()>>,
    shutdown: Arc<AtomicUsize>,
}

impl<K: Hash + Eq + Clone + fmt::Debug + Send + Sync + 'static,
     V: Clone + Send + Sync + 'static> ShardedCache<K, V> {

    pub fn new(config: CacheConfig) -> Self {
        let shard_count = config.shard_count;
        let max_per_shard = config.max_entries / shard_count;
        let max_size_per_shard = config.max_total_size / shard_count;

        let shards: Vec<RwLock<Shard<K, V>>> = (0..shard_count)
            .map(|_| RwLock::new(Shard::new(max_per_shard, config.policy, max_size_per_shard)))
            .collect();

        let shutdown = Arc::new(AtomicUsize::new(0));

        ShardedCache {
            shards,
            shard_count,
            default_ttl: Duration::from_secs(config.ttl_seconds),
            max_key_size: config.max_key_size,
            max_value_size: config.max_value_size,
            created_at: Instant::now(),
            operation_count: AtomicU64::new(0),
            cleanup_handle: None,
            shutdown,
        }
    }

    fn shard_index(&self, key: &K) -> usize {
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        key.hash(&mut hasher);
        hasher.finish() as usize % self.shard_count
    }

    pub fn get(&self, key: &K) -> Option<V> {
        self.operation_count.fetch_add(1, Ordering::Relaxed);
        let idx = self.shard_index(key);

        match self.shards[idx].write() {
            Ok(mut shard) => shard.get(key).cloned(),
            Err(_) => None,
        }
    }

    pub fn insert(&self, key: K, value: V) -> Result<(), CacheError> {
        self.insert_with_ttl(key, value, self.default_ttl, 0)
    }

    pub fn insert_with_ttl(&self, key: K, value: V, ttl: Duration, size: usize) -> Result<(), CacheError> {
        self.operation_count.fetch_add(1, Ordering::Relaxed);
        let idx = self.shard_index(&key);

        match self.shards[idx].write() {
            Ok(mut shard) => shard.insert(key, value, ttl, size),
            Err(_) => Err(CacheError::ShardLockPoisoned),
        }
    }

    pub fn remove(&self, key: &K) -> Option<V> {
        self.operation_count.fetch_add(1, Ordering::Relaxed);
        let idx = self.shard_index(key);

        match self.shards[idx].write() {
            Ok(mut shard) => shard.remove(key),
            Err(_) => None,
        }
    }

    pub fn contains(&self, key: &K) -> bool {
        let idx = self.shard_index(key);
        match self.shards[idx].read() {
            Ok(shard) => shard.entries.contains_key(key) && !shard.entries[key].is_expired(),
            Err(_) => false,
        }
    }

    pub fn len(&self) -> usize {
        self.shards.iter()
            .filter_map(|s| s.read().ok())
            .map(|s| s.len())
            .sum()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    pub fn clear(&self) {
        for shard in &self.shards {
            if let Ok(mut s) = shard.write() {
                s.clear();
            }
        }
    }

    pub fn cleanup_expired(&self) -> usize {
        let mut total = 0;
        for shard in &self.shards {
            if let Ok(mut s) = shard.write() {
                total += s.cleanup_expired();
            }
        }
        total
    }

    pub fn stats(&self) -> CacheStats {
        let mut total_entries = 0;
        let mut total_size = 0;
        let mut total_hits: u64 = 0;
        let mut total_misses: u64 = 0;
        let mut total_evictions: u64 = 0;
        let mut shard_distribution = Vec::with_capacity(self.shard_count);
        let mut max_age = Duration::from_secs(0);
        let mut total_age = Duration::from_secs(0);
        let mut entry_count_for_age: u64 = 0;

        for shard_lock in &self.shards {
            if let Ok(shard) = shard_lock.read() {
                let count = shard.len();
                total_entries += count;
                total_size += shard.total_size;
                total_hits += shard.hit_count.load(Ordering::Relaxed);
                total_misses += shard.miss_count.load(Ordering::Relaxed);
                total_evictions += shard.eviction_count.load(Ordering::Relaxed);
                shard_distribution.push(count);

                for entry in shard.entries.values() {
                    let age = entry.age();
                    total_age += age;
                    entry_count_for_age += 1;
                    if age > max_age {
                        max_age = age;
                    }
                }
            }
        }

        let total_requests = total_hits + total_misses;
        let hit_rate = if total_requests > 0 {
            total_hits as f64 / total_requests as f64
        } else {
            0.0
        };

        let avg_age_ms = if entry_count_for_age > 0 {
            total_age.as_millis() as u64 / entry_count_for_age
        } else {
            0
        };

        CacheStats {
            total_entries,
            total_size_bytes: total_size,
            hit_count: total_hits,
            miss_count: total_misses,
            eviction_count: total_evictions,
            hit_rate,
            shard_distribution,
            avg_entry_age_ms: avg_age_ms,
            max_entry_age_ms: max_age.as_millis() as u64,
        }
    }

    pub fn get_or_insert<F>(&self, key: K, factory: F) -> Result<V, CacheError>
    where
        F: FnOnce() -> V,
    {
        if let Some(value) = self.get(&key) {
            return Ok(value);
        }

        let value = factory();
        self.insert(key, value.clone())?;
        Ok(value)
    }

    pub fn get_many(&self, keys: &[K]) -> Vec<(K, Option<V>)> {
        keys.iter()
            .map(|k| (k.clone(), self.get(k)))
            .collect()
    }

    pub fn insert_many(&self, entries: Vec<(K, V)>) -> Vec<Result<(), CacheError>> {
        entries.into_iter()
            .map(|(k, v)| self.insert(k, v))
            .collect()
    }

    pub fn uptime(&self) -> Duration {
        self.created_at.elapsed()
    }
}

impl<K: Hash + Eq + Clone + fmt::Debug + Send + Sync + 'static,
     V: Clone + Send + Sync + 'static> Drop for ShardedCache<K, V> {
    fn drop(&mut self) {
        self.shutdown.store(1, Ordering::SeqCst);
        if let Some(handle) = self.cleanup_handle.take() {
            let _ = handle.join();
        }
    }
}

// ─── Cache Configuration ──────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct CacheConfig {
    pub shard_count: usize,
    pub max_entries: usize,
    pub ttl_seconds: u64,
    pub policy: EvictionPolicy,
    pub max_key_size: usize,
    pub max_value_size: usize,
    pub max_total_size: usize,
    pub cleanup_interval: Duration,
    pub enable_stats: bool,
}

impl Default for CacheConfig {
    fn default() -> Self {
        CacheConfig {
            shard_count: DEFAULT_SHARD_COUNT,
            max_entries: DEFAULT_MAX_ENTRIES,
            ttl_seconds: DEFAULT_TTL_SECONDS,
            policy: EvictionPolicy::LRU,
            max_key_size: MAX_KEY_SIZE,
            max_value_size: MAX_VALUE_SIZE,
            max_total_size: 100 * 1024 * 1024, // 100MB
            cleanup_interval: Duration::from_secs(CLEANUP_INTERVAL_SECONDS),
            enable_stats: true,
        }
    }
}

impl CacheConfig {
    pub fn builder() -> CacheConfigBuilder {
        CacheConfigBuilder::new()
    }
}

pub struct CacheConfigBuilder {
    config: CacheConfig,
}

impl CacheConfigBuilder {
    pub fn new() -> Self {
        CacheConfigBuilder {
            config: CacheConfig::default(),
        }
    }

    pub fn shard_count(mut self, count: usize) -> Self {
        self.config.shard_count = count.max(1);
        self
    }

    pub fn max_entries(mut self, max: usize) -> Self {
        self.config.max_entries = max;
        self
    }

    pub fn ttl(mut self, seconds: u64) -> Self {
        self.config.ttl_seconds = seconds;
        self
    }

    pub fn policy(mut self, policy: EvictionPolicy) -> Self {
        self.config.policy = policy;
        self
    }

    pub fn max_total_size(mut self, bytes: usize) -> Self {
        self.config.max_total_size = bytes;
        self
    }

    pub fn build(self) -> CacheConfig {
        self.config
    }
}

// ─── Write-Through Wrapper ────────────────────────────────────────

pub struct WriteThroughCache<K, V, S>
where
    K: Hash + Eq + Clone + fmt::Debug + Send + Sync + 'static,
    V: Clone + Send + Sync + 'static,
    S: CacheStore<K, V>,
{
    cache: ShardedCache<K, V>,
    store: Arc<Mutex<S>>,
}

pub trait CacheStore<K, V>: Send + Sync {
    fn load(&self, key: &K) -> Result<Option<V>, CacheError>;
    fn save(&self, key: &K, value: &V) -> Result<(), CacheError>;
    fn delete(&self, key: &K) -> Result<(), CacheError>;
}

impl<K, V, S> WriteThroughCache<K, V, S>
where
    K: Hash + Eq + Clone + fmt::Debug + Send + Sync + 'static,
    V: Clone + Send + Sync + 'static,
    S: CacheStore<K, V>,
{
    pub fn new(config: CacheConfig, store: S) -> Self {
        WriteThroughCache {
            cache: ShardedCache::new(config),
            store: Arc::new(Mutex::new(store)),
        }
    }

    pub fn get(&self, key: &K) -> Result<Option<V>, CacheError> {
        // Try cache first
        if let Some(value) = self.cache.get(key) {
            return Ok(Some(value));
        }

        // Cache miss — load from store
        let store = self.store.lock().map_err(|_| CacheError::ShardLockPoisoned)?;
        if let Some(value) = store.load(key)? {
            drop(store);
            let _ = self.cache.insert(key.clone(), value.clone());
            return Ok(Some(value));
        }

        Ok(None)
    }

    pub fn set(&self, key: K, value: V) -> Result<(), CacheError> {
        // Write to store first (write-through)
        let store = self.store.lock().map_err(|_| CacheError::ShardLockPoisoned)?;
        store.save(&key, &value)?;
        drop(store);

        // Then update cache
        self.cache.insert(key, value)
    }

    pub fn delete(&self, key: &K) -> Result<(), CacheError> {
        let store = self.store.lock().map_err(|_| CacheError::ShardLockPoisoned)?;
        store.delete(key)?;
        drop(store);

        self.cache.remove(key);
        Ok(())
    }

    pub fn stats(&self) -> CacheStats {
        self.cache.stats()
    }
}

// ─── Tests ─────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn make_cache() -> ShardedCache<String, String> {
        let config = CacheConfig::builder()
            .shard_count(4)
            .max_entries(100)
            .ttl(60)
            .build();
        ShardedCache::new(config)
    }

    #[test]
    fn test_insert_and_get() {
        let cache = make_cache();
        cache.insert("key1".to_string(), "value1".to_string()).unwrap();
        assert_eq!(cache.get(&"key1".to_string()), Some("value1".to_string()));
    }

    #[test]
    fn test_missing_key() {
        let cache = make_cache();
        assert_eq!(cache.get(&"missing".to_string()), None);
    }

    #[test]
    fn test_overwrite() {
        let cache = make_cache();
        cache.insert("k".to_string(), "v1".to_string()).unwrap();
        cache.insert("k".to_string(), "v2".to_string()).unwrap();
        assert_eq!(cache.get(&"k".to_string()), Some("v2".to_string()));
    }

    #[test]
    fn test_remove() {
        let cache = make_cache();
        cache.insert("k".to_string(), "v".to_string()).unwrap();
        assert_eq!(cache.remove(&"k".to_string()), Some("v".to_string()));
        assert_eq!(cache.get(&"k".to_string()), None);
    }

    #[test]
    fn test_contains() {
        let cache = make_cache();
        cache.insert("k".to_string(), "v".to_string()).unwrap();
        assert!(cache.contains(&"k".to_string()));
        assert!(!cache.contains(&"missing".to_string()));
    }

    #[test]
    fn test_clear() {
        let cache = make_cache();
        for i in 0..50 {
            cache.insert(format!("k{}", i), format!("v{}", i)).unwrap();
        }
        assert_eq!(cache.len(), 50);
        cache.clear();
        assert!(cache.is_empty());
    }

    #[test]
    fn test_stats() {
        let cache = make_cache();
        for i in 0..10 {
            cache.insert(format!("k{}", i), format!("v{}", i)).unwrap();
        }
        cache.get(&"k0".to_string());
        cache.get(&"k1".to_string());
        cache.get(&"missing".to_string());

        let stats = cache.stats();
        assert_eq!(stats.total_entries, 10);
        assert_eq!(stats.hit_count, 2);
        assert_eq!(stats.miss_count, 1);
        assert!(stats.hit_rate > 0.5);
    }

    #[test]
    fn test_get_or_insert() {
        let cache = make_cache();
        let val = cache.get_or_insert("k".to_string(), || "computed".to_string()).unwrap();
        assert_eq!(val, "computed");

        // Second call should return cached value
        let val2 = cache.get_or_insert("k".to_string(), || "new_value".to_string()).unwrap();
        assert_eq!(val2, "computed");
    }

    #[test]
    fn test_batch_operations() {
        let cache = make_cache();
        let entries: Vec<_> = (0..20).map(|i| (format!("k{}", i), format!("v{}", i))).collect();
        let results = cache.insert_many(entries);
        assert!(results.iter().all(|r| r.is_ok()));

        let keys: Vec<_> = (0..20).map(|i| format!("k{}", i)).collect();
        let values = cache.get_many(&keys);
        assert_eq!(values.len(), 20);
        assert!(values.iter().all(|(_, v)| v.is_some()));
    }

    #[test]
    fn test_eviction_policy_lru() {
        let config = CacheConfig::builder()
            .shard_count(1)
            .max_entries(5)
            .policy(EvictionPolicy::LRU)
            .build();
        let cache: ShardedCache<String, String> = ShardedCache::new(config);

        for i in 0..5 {
            cache.insert(format!("k{}", i), format!("v{}", i)).unwrap();
        }

        // Access k0 to make it recently used
        cache.get(&"k0".to_string());

        // Insert k5 — should evict the LRU entry (k1, since k0 was just accessed)
        cache.insert("k5".to_string(), "v5".to_string()).unwrap();

        assert!(cache.contains(&"k0".to_string())); // k0 should survive (recently used)
        assert!(cache.contains(&"k5".to_string())); // k5 was just inserted
    }

    #[test]
    fn test_config_builder() {
        let config = CacheConfig::builder()
            .shard_count(8)
            .max_entries(5000)
            .ttl(120)
            .policy(EvictionPolicy::LFU)
            .max_total_size(50 * 1024 * 1024)
            .build();

        assert_eq!(config.shard_count, 8);
        assert_eq!(config.max_entries, 5000);
        assert_eq!(config.ttl_seconds, 120);
        assert_eq!(config.policy, EvictionPolicy::LFU);
    }
}
