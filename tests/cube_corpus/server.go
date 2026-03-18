// Package main implements a concurrent HTTP server with middleware,
// rate limiting, circuit breaker, and connection pooling.
package main

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"math"
	"math/rand"
	"net"
	"net/http"
	"os"
	"os/signal"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

// ─── Configuration ─────────────────────────────────────────────────

const (
	DefaultPort         = 8080
	MaxRequestBodySize  = 10 << 20 // 10MB
	ReadTimeout         = 15 * time.Second
	WriteTimeout        = 30 * time.Second
	IdleTimeout         = 60 * time.Second
	ShutdownTimeout     = 30 * time.Second
	MaxConnectionsPerIP = 100
	RateLimitWindow     = time.Minute
	RateLimitMax        = 1000
	CircuitBreakerMax   = 5
	CircuitBreakerReset = 30 * time.Second
	PoolMaxIdle         = 50
	PoolMaxOpen         = 100
	PoolMaxLifetime     = 5 * time.Minute
	RetryMaxAttempts    = 3
	RetryBaseDelay      = 100 * time.Millisecond
	RetryMaxDelay       = 5 * time.Second
	MetricsFlushInterval = 10 * time.Second
)

// ─── Domain Types ──────────────────────────────────────────────────

type User struct {
	ID        int64     `json:"id"`
	Email     string    `json:"email"`
	Name      string    `json:"name"`
	Role      string    `json:"role"`
	Active    bool      `json:"active"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
	Metadata  map[string]interface{} `json:"metadata,omitempty"`
}

type Session struct {
	Token     string    `json:"token"`
	UserID    int64     `json:"user_id"`
	ExpiresAt time.Time `json:"expires_at"`
	IP        string    `json:"ip"`
	UserAgent string    `json:"user_agent"`
}

type APIResponse struct {
	Status  int         `json:"status"`
	Data    interface{} `json:"data,omitempty"`
	Error   string      `json:"error,omitempty"`
	TraceID string      `json:"trace_id"`
	Latency string      `json:"latency"`
}

type PaginatedResponse struct {
	Items      interface{} `json:"items"`
	Total      int64       `json:"total"`
	Page       int         `json:"page"`
	PerPage    int         `json:"per_page"`
	TotalPages int         `json:"total_pages"`
}

type HealthCheck struct {
	Status    string            `json:"status"`
	Version   string            `json:"version"`
	Uptime    string            `json:"uptime"`
	Checks    map[string]string `json:"checks"`
	Timestamp time.Time         `json:"timestamp"`
}

// ─── Rate Limiter ──────────────────────────────────────────────────

type RateLimiter struct {
	mu       sync.RWMutex
	counters map[string]*rateBucket
	window   time.Duration
	max      int
	cleanup  *time.Ticker
}

type rateBucket struct {
	count    int
	resetAt  time.Time
}

func NewRateLimiter(window time.Duration, max int) *RateLimiter {
	rl := &RateLimiter{
		counters: make(map[string]*rateBucket),
		window:   window,
		max:      max,
		cleanup:  time.NewTicker(window * 2),
	}
	go rl.cleanupLoop()
	return rl
}

func (rl *RateLimiter) Allow(key string) bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	bucket, exists := rl.counters[key]
	if !exists || now.After(bucket.resetAt) {
		rl.counters[key] = &rateBucket{
			count:   1,
			resetAt: now.Add(rl.window),
		}
		return true
	}

	if bucket.count >= rl.max {
		return false
	}
	bucket.count++
	return true
}

func (rl *RateLimiter) Remaining(key string) int {
	rl.mu.RLock()
	defer rl.mu.RUnlock()

	bucket, exists := rl.counters[key]
	if !exists || time.Now().After(bucket.resetAt) {
		return rl.max
	}
	remaining := rl.max - bucket.count
	if remaining < 0 {
		return 0
	}
	return remaining
}

func (rl *RateLimiter) cleanupLoop() {
	for range rl.cleanup.C {
		rl.mu.Lock()
		now := time.Now()
		for key, bucket := range rl.counters {
			if now.After(bucket.resetAt) {
				delete(rl.counters, key)
			}
		}
		rl.mu.Unlock()
	}
}

// ─── Circuit Breaker ───────────────────────────────────────────────

type CircuitState int

const (
	CircuitClosed CircuitState = iota
	CircuitOpen
	CircuitHalfOpen
)

func (s CircuitState) String() string {
	switch s {
	case CircuitClosed:
		return "closed"
	case CircuitOpen:
		return "open"
	case CircuitHalfOpen:
		return "half-open"
	default:
		return "unknown"
	}
}

type CircuitBreaker struct {
	mu            sync.RWMutex
	state         CircuitState
	failures      int
	maxFailures   int
	resetTimeout  time.Duration
	lastFailure   time.Time
	successCount  int
	halfOpenMax   int
	onStateChange func(from, to CircuitState)
}

func NewCircuitBreaker(maxFailures int, resetTimeout time.Duration) *CircuitBreaker {
	return &CircuitBreaker{
		state:        CircuitClosed,
		maxFailures:  maxFailures,
		resetTimeout: resetTimeout,
		halfOpenMax:  3,
	}
}

func (cb *CircuitBreaker) Execute(fn func() error) error {
	if !cb.canExecute() {
		return errors.New("circuit breaker is open")
	}

	err := fn()
	if err != nil {
		cb.recordFailure()
		return err
	}

	cb.recordSuccess()
	return nil
}

func (cb *CircuitBreaker) canExecute() bool {
	cb.mu.RLock()
	defer cb.mu.RUnlock()

	switch cb.state {
	case CircuitClosed:
		return true
	case CircuitOpen:
		if time.Since(cb.lastFailure) > cb.resetTimeout {
			cb.mu.RUnlock()
			cb.mu.Lock()
			cb.state = CircuitHalfOpen
			cb.successCount = 0
			if cb.onStateChange != nil {
				cb.onStateChange(CircuitOpen, CircuitHalfOpen)
			}
			cb.mu.Unlock()
			cb.mu.RLock()
			return true
		}
		return false
	case CircuitHalfOpen:
		return cb.successCount < cb.halfOpenMax
	default:
		return false
	}
}

func (cb *CircuitBreaker) recordFailure() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	cb.failures++
	cb.lastFailure = time.Now()

	if cb.failures >= cb.maxFailures {
		oldState := cb.state
		cb.state = CircuitOpen
		if oldState != CircuitOpen && cb.onStateChange != nil {
			cb.onStateChange(oldState, CircuitOpen)
		}
	}
}

func (cb *CircuitBreaker) recordSuccess() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	if cb.state == CircuitHalfOpen {
		cb.successCount++
		if cb.successCount >= cb.halfOpenMax {
			cb.state = CircuitClosed
			cb.failures = 0
			if cb.onStateChange != nil {
				cb.onStateChange(CircuitHalfOpen, CircuitClosed)
			}
		}
	} else {
		cb.failures = 0
	}
}

func (cb *CircuitBreaker) State() CircuitState {
	cb.mu.RLock()
	defer cb.mu.RUnlock()
	return cb.state
}

func (cb *CircuitBreaker) Reset() {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	cb.state = CircuitClosed
	cb.failures = 0
	cb.successCount = 0
}

// ─── Connection Pool ───────────────────────────────────────────────

type ConnPool struct {
	mu          sync.Mutex
	conns       chan net.Conn
	factory     func() (net.Conn, error)
	maxIdle     int
	maxOpen     int
	maxLifetime time.Duration
	numOpen     int32
	stats       PoolStats
}

type PoolStats struct {
	MaxOpenConnections int   `json:"max_open_connections"`
	OpenConnections    int32 `json:"open_connections"`
	InUse              int32 `json:"in_use"`
	Idle               int32 `json:"idle"`
	WaitCount          int64 `json:"wait_count"`
	WaitDuration       int64 `json:"wait_duration_ms"`
	MaxIdleClosed      int64 `json:"max_idle_closed"`
	MaxLifetimeClosed  int64 `json:"max_lifetime_closed"`
}

func NewConnPool(factory func() (net.Conn, error), maxIdle, maxOpen int, maxLifetime time.Duration) *ConnPool {
	return &ConnPool{
		conns:       make(chan net.Conn, maxIdle),
		factory:     factory,
		maxIdle:     maxIdle,
		maxOpen:     maxOpen,
		maxLifetime: maxLifetime,
	}
}

func (p *ConnPool) Get(ctx context.Context) (net.Conn, error) {
	select {
	case conn := <-p.conns:
		atomic.AddInt32(&p.stats.Idle, -1)
		atomic.AddInt32(&p.stats.InUse, 1)
		return conn, nil
	default:
	}

	current := atomic.LoadInt32(&p.numOpen)
	if int(current) >= p.maxOpen {
		atomic.AddInt64(&p.stats.WaitCount, 1)
		start := time.Now()
		select {
		case conn := <-p.conns:
			atomic.AddInt64(&p.stats.WaitDuration, time.Since(start).Milliseconds())
			atomic.AddInt32(&p.stats.Idle, -1)
			atomic.AddInt32(&p.stats.InUse, 1)
			return conn, nil
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	}

	conn, err := p.factory()
	if err != nil {
		return nil, fmt.Errorf("pool factory error: %w", err)
	}
	atomic.AddInt32(&p.numOpen, 1)
	atomic.AddInt32(&p.stats.InUse, 1)
	return conn, nil
}

func (p *ConnPool) Put(conn net.Conn) {
	atomic.AddInt32(&p.stats.InUse, -1)

	select {
	case p.conns <- conn:
		atomic.AddInt32(&p.stats.Idle, 1)
	default:
		conn.Close()
		atomic.AddInt32(&p.numOpen, -1)
		atomic.AddInt64(&p.stats.MaxIdleClosed, 1)
	}
}

func (p *ConnPool) Close() error {
	close(p.conns)
	for conn := range p.conns {
		conn.Close()
	}
	return nil
}

func (p *ConnPool) Stats() PoolStats {
	return PoolStats{
		MaxOpenConnections: p.maxOpen,
		OpenConnections:    atomic.LoadInt32(&p.numOpen),
		InUse:              atomic.LoadInt32(&p.stats.InUse),
		Idle:               atomic.LoadInt32(&p.stats.Idle),
		WaitCount:          atomic.LoadInt64(&p.stats.WaitCount),
		WaitDuration:       atomic.LoadInt64(&p.stats.WaitDuration),
		MaxIdleClosed:      atomic.LoadInt64(&p.stats.MaxIdleClosed),
		MaxLifetimeClosed:  atomic.LoadInt64(&p.stats.MaxLifetimeClosed),
	}
}

// ─── Metrics Collector ─────────────────────────────────────────────

type MetricsCollector struct {
	mu             sync.RWMutex
	requestCount   map[string]*atomic.Int64
	requestLatency map[string][]time.Duration
	errorCount     map[string]*atomic.Int64
	activeConns    atomic.Int64
	totalBytes     atomic.Int64
	startTime      time.Time
	flushInterval  time.Duration
	done           chan struct{}
}

func NewMetricsCollector(flushInterval time.Duration) *MetricsCollector {
	mc := &MetricsCollector{
		requestCount:   make(map[string]*atomic.Int64),
		requestLatency: make(map[string][]time.Duration),
		errorCount:     make(map[string]*atomic.Int64),
		startTime:      time.Now(),
		flushInterval:  flushInterval,
		done:           make(chan struct{}),
	}
	go mc.flushLoop()
	return mc
}

func (mc *MetricsCollector) RecordRequest(method, path string, latency time.Duration, statusCode int) {
	key := fmt.Sprintf("%s:%s", method, path)

	mc.mu.Lock()
	if _, ok := mc.requestCount[key]; !ok {
		mc.requestCount[key] = &atomic.Int64{}
		mc.requestLatency[key] = make([]time.Duration, 0, 1000)
	}
	mc.requestCount[key].Add(1)
	mc.requestLatency[key] = append(mc.requestLatency[key], latency)
	mc.mu.Unlock()

	if statusCode >= 400 {
		errKey := fmt.Sprintf("%s:%d", key, statusCode)
		mc.mu.Lock()
		if _, ok := mc.errorCount[errKey]; !ok {
			mc.errorCount[errKey] = &atomic.Int64{}
		}
		mc.errorCount[errKey].Add(1)
		mc.mu.Unlock()
	}
}

func (mc *MetricsCollector) GetPercentile(method, path string, percentile float64) time.Duration {
	key := fmt.Sprintf("%s:%s", method, path)

	mc.mu.RLock()
	defer mc.mu.RUnlock()

	latencies, ok := mc.requestLatency[key]
	if !ok || len(latencies) == 0 {
		return 0
	}

	sorted := make([]time.Duration, len(latencies))
	copy(sorted, latencies)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i] < sorted[j] })

	idx := int(math.Ceil(percentile/100*float64(len(sorted)))) - 1
	if idx < 0 {
		idx = 0
	}
	if idx >= len(sorted) {
		idx = len(sorted) - 1
	}
	return sorted[idx]
}

func (mc *MetricsCollector) Snapshot() map[string]interface{} {
	mc.mu.RLock()
	defer mc.mu.RUnlock()

	snapshot := map[string]interface{}{
		"uptime":       time.Since(mc.startTime).String(),
		"active_conns": mc.activeConns.Load(),
		"total_bytes":  mc.totalBytes.Load(),
		"endpoints":    map[string]interface{}{},
	}

	endpoints := snapshot["endpoints"].(map[string]interface{})
	for key, count := range mc.requestCount {
		latencies := mc.requestLatency[key]
		var totalLatency time.Duration
		for _, l := range latencies {
			totalLatency += l
		}
		avgLatency := time.Duration(0)
		if len(latencies) > 0 {
			avgLatency = totalLatency / time.Duration(len(latencies))
		}

		endpoints[key] = map[string]interface{}{
			"count":       count.Load(),
			"avg_latency": avgLatency.String(),
			"p95_latency": mc.GetPercentile(strings.SplitN(key, ":", 2)[0],
				strings.SplitN(key, ":", 2)[1], 95).String(),
		}
	}

	return snapshot
}

func (mc *MetricsCollector) flushLoop() {
	ticker := time.NewTicker(mc.flushInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			mc.mu.Lock()
			for key := range mc.requestLatency {
				if len(mc.requestLatency[key]) > 10000 {
					mc.requestLatency[key] = mc.requestLatency[key][len(mc.requestLatency[key])-1000:]
				}
			}
			mc.mu.Unlock()
		case <-mc.done:
			return
		}
	}
}

func (mc *MetricsCollector) Close() {
	close(mc.done)
}

// ─── Middleware Stack ──────────────────────────────────────────────

type Middleware func(http.Handler) http.Handler

func ChainMiddleware(h http.Handler, middlewares ...Middleware) http.Handler {
	for i := len(middlewares) - 1; i >= 0; i-- {
		h = middlewares[i](h)
	}
	return h
}

func LoggingMiddleware(logger *log.Logger) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			wrapped := &responseWriter{ResponseWriter: w, statusCode: http.StatusOK}

			defer func() {
				logger.Printf(
					"%s %s %s %d %s %s",
					r.RemoteAddr,
					r.Method,
					r.URL.Path,
					wrapped.statusCode,
					time.Since(start),
					r.UserAgent(),
				)
			}()

			next.ServeHTTP(wrapped, r)
		})
	}
}

func RateLimitMiddleware(limiter *RateLimiter) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			ip := extractIP(r)
			if !limiter.Allow(ip) {
				remaining := limiter.Remaining(ip)
				w.Header().Set("X-RateLimit-Remaining", strconv.Itoa(remaining))
				w.Header().Set("Retry-After", "60")
				http.Error(w, "rate limit exceeded", http.StatusTooManyRequests)
				return
			}
			w.Header().Set("X-RateLimit-Remaining", strconv.Itoa(limiter.Remaining(ip)))
			next.ServeHTTP(w, r)
		})
	}
}

func RecoveryMiddleware(logger *log.Logger) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			defer func() {
				if err := recover(); err != nil {
					logger.Printf("PANIC: %v [%s %s]", err, r.Method, r.URL.Path)
					http.Error(w, "internal server error", http.StatusInternalServerError)
				}
			}()
			next.ServeHTTP(wrapped, r)
		})
	}
}

func CORSMiddleware(allowedOrigins []string) Middleware {
	allowed := make(map[string]bool)
	for _, origin := range allowedOrigins {
		allowed[origin] = true
	}

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			origin := r.Header.Get("Origin")
			if allowed[origin] || allowed["*"] {
				w.Header().Set("Access-Control-Allow-Origin", origin)
				w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
				w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Request-ID")
				w.Header().Set("Access-Control-Max-Age", "86400")
			}

			if r.Method == http.MethodOptions {
				w.WriteHeader(http.StatusNoContent)
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}

func AuthMiddleware(sessionStore *SessionStore) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			token := extractToken(r)
			if token == "" {
				writeJSON(w, http.StatusUnauthorized, APIResponse{
					Status: http.StatusUnauthorized,
					Error:  "missing authentication token",
				})
				return
			}

			session, err := sessionStore.Get(token)
			if err != nil || session == nil {
				writeJSON(w, http.StatusUnauthorized, APIResponse{
					Status: http.StatusUnauthorized,
					Error:  "invalid or expired session",
				})
				return
			}

			ctx := context.WithValue(r.Context(), "user_id", session.UserID)
			ctx = context.WithValue(ctx, "session", session)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func MetricsMiddleware(mc *MetricsCollector) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			mc.activeConns.Add(1)
			defer mc.activeConns.Add(-1)

			start := time.Now()
			wrapped := &responseWriter{ResponseWriter: w, statusCode: http.StatusOK}
			next.ServeHTTP(wrapped, r)

			mc.RecordRequest(r.Method, r.URL.Path, time.Since(start), wrapped.statusCode)
			mc.totalBytes.Add(int64(wrapped.bytesWritten))
		})
	}
}

// ─── Response Writer Wrapper ───────────────────────────────────────

type responseWriter struct {
	http.ResponseWriter
	statusCode   int
	bytesWritten int
	headerSent   bool
}

func (rw *responseWriter) WriteHeader(code int) {
	if !rw.headerSent {
		rw.statusCode = code
		rw.headerSent = true
		rw.ResponseWriter.WriteHeader(code)
	}
}

func (rw *responseWriter) Write(b []byte) (int, error) {
	if !rw.headerSent {
		rw.headerSent = true
	}
	n, err := rw.ResponseWriter.Write(b)
	rw.bytesWritten += n
	return n, err
}

// ─── Session Store ─────────────────────────────────────────────────

type SessionStore struct {
	mu       sync.RWMutex
	sessions map[string]*Session
	ttl      time.Duration
}

func NewSessionStore(ttl time.Duration) *SessionStore {
	ss := &SessionStore{
		sessions: make(map[string]*Session),
		ttl:      ttl,
	}
	go ss.cleanupLoop()
	return ss
}

func (ss *SessionStore) Create(userID int64, ip, userAgent string) *Session {
	ss.mu.Lock()
	defer ss.mu.Unlock()

	token := generateToken()
	session := &Session{
		Token:     token,
		UserID:    userID,
		ExpiresAt: time.Now().Add(ss.ttl),
		IP:        ip,
		UserAgent: userAgent,
	}
	ss.sessions[token] = session
	return session
}

func (ss *SessionStore) Get(token string) (*Session, error) {
	ss.mu.RLock()
	defer ss.mu.RUnlock()

	session, ok := ss.sessions[token]
	if !ok {
		return nil, errors.New("session not found")
	}
	if time.Now().After(session.ExpiresAt) {
		return nil, errors.New("session expired")
	}
	return session, nil
}

func (ss *SessionStore) Delete(token string) {
	ss.mu.Lock()
	defer ss.mu.Unlock()
	delete(ss.sessions, token)
}

func (ss *SessionStore) ActiveCount() int {
	ss.mu.RLock()
	defer ss.mu.RUnlock()

	count := 0
	now := time.Now()
	for _, s := range ss.sessions {
		if now.Before(s.ExpiresAt) {
			count++
		}
	}
	return count
}

func (ss *SessionStore) cleanupLoop() {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()

	for range ticker.C {
		ss.mu.Lock()
		now := time.Now()
		for token, session := range ss.sessions {
			if now.After(session.ExpiresAt) {
				delete(ss.sessions, token)
			}
		}
		ss.mu.Unlock()
	}
}

// ─── Router & Handlers ─────────────────────────────────────────────

type Router struct {
	mux      *http.ServeMux
	handlers map[string]http.HandlerFunc
	prefix   string
}

func NewRouter(prefix string) *Router {
	return &Router{
		mux:      http.NewServeMux(),
		handlers: make(map[string]http.HandlerFunc),
		prefix:   prefix,
	}
}

func (r *Router) Handle(pattern string, handler http.HandlerFunc) {
	fullPattern := r.prefix + pattern
	r.handlers[fullPattern] = handler
	r.mux.HandleFunc(fullPattern, handler)
}

func (r *Router) ServeHTTP(w http.ResponseWriter, req *http.Request) {
	r.mux.ServeHTTP(w, req)
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	health := HealthCheck{
		Status:    "healthy",
		Version:   "1.0.0",
		Uptime:    time.Since(startTime).String(),
		Timestamp: time.Now(),
		Checks: map[string]string{
			"database": "ok",
			"cache":    "ok",
			"disk":     "ok",
		},
	}
	writeJSON(w, http.StatusOK, health)
}

func handleListUsers(store *UserStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		page, _ := strconv.Atoi(r.URL.Query().Get("page"))
		if page < 1 {
			page = 1
		}
		perPage, _ := strconv.Atoi(r.URL.Query().Get("per_page"))
		if perPage < 1 || perPage > 100 {
			perPage = 20
		}

		users, total := store.List(page, perPage)
		totalPages := int(math.Ceil(float64(total) / float64(perPage)))

		writeJSON(w, http.StatusOK, PaginatedResponse{
			Items:      users,
			Total:      total,
			Page:       page,
			PerPage:    perPage,
			TotalPages: totalPages,
		})
	}
}

func handleGetUser(store *UserStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		idStr := strings.TrimPrefix(r.URL.Path, "/api/v1/users/")
		id, err := strconv.ParseInt(idStr, 10, 64)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, APIResponse{
				Status: http.StatusBadRequest,
				Error:  "invalid user ID",
			})
			return
		}

		user, err := store.GetByID(id)
		if err != nil {
			writeJSON(w, http.StatusNotFound, APIResponse{
				Status: http.StatusNotFound,
				Error:  "user not found",
			})
			return
		}

		writeJSON(w, http.StatusOK, APIResponse{
			Status: http.StatusOK,
			Data:   user,
		})
	}
}

func handleCreateUser(store *UserStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSON(w, http.StatusMethodNotAllowed, APIResponse{
				Status: http.StatusMethodNotAllowed,
				Error:  "method not allowed",
			})
			return
		}

		var user User
		if err := json.NewDecoder(io.LimitReader(r.Body, MaxRequestBodySize)).Decode(&user); err != nil {
			writeJSON(w, http.StatusBadRequest, APIResponse{
				Status: http.StatusBadRequest,
				Error:  fmt.Sprintf("invalid request body: %v", err),
			})
			return
		}

		if user.Email == "" || user.Name == "" {
			writeJSON(w, http.StatusBadRequest, APIResponse{
				Status: http.StatusBadRequest,
				Error:  "email and name are required",
			})
			return
		}

		created, err := store.Create(user)
		if err != nil {
			writeJSON(w, http.StatusConflict, APIResponse{
				Status: http.StatusConflict,
				Error:  err.Error(),
			})
			return
		}

		writeJSON(w, http.StatusCreated, APIResponse{
			Status: http.StatusCreated,
			Data:   created,
		})
	}
}

func handleDeleteUser(store *UserStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			writeJSON(w, http.StatusMethodNotAllowed, APIResponse{
				Status: http.StatusMethodNotAllowed,
				Error:  "method not allowed",
			})
			return
		}

		idStr := strings.TrimPrefix(r.URL.Path, "/api/v1/users/")
		id, err := strconv.ParseInt(idStr, 10, 64)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, APIResponse{
				Status: http.StatusBadRequest,
				Error:  "invalid user ID",
			})
			return
		}

		if err := store.Delete(id); err != nil {
			writeJSON(w, http.StatusNotFound, APIResponse{
				Status: http.StatusNotFound,
				Error:  "user not found",
			})
			return
		}

		writeJSON(w, http.StatusOK, APIResponse{
			Status: http.StatusOK,
			Data:   map[string]string{"deleted": idStr},
		})
	}
}

// ─── User Store ────────────────────────────────────────────────────

type UserStore struct {
	mu    sync.RWMutex
	users map[int64]*User
	byEmail map[string]int64
	nextID atomic.Int64
}

func NewUserStore() *UserStore {
	us := &UserStore{
		users:   make(map[int64]*User),
		byEmail: make(map[string]int64),
	}
	us.nextID.Store(1)
	return us
}

func (us *UserStore) Create(u User) (*User, error) {
	us.mu.Lock()
	defer us.mu.Unlock()

	email := strings.ToLower(strings.TrimSpace(u.Email))
	if _, exists := us.byEmail[email]; exists {
		return nil, fmt.Errorf("email %s already exists", email)
	}

	id := us.nextID.Add(1) - 1
	now := time.Now()
	user := &User{
		ID:        id,
		Email:     email,
		Name:      strings.TrimSpace(u.Name),
		Role:      u.Role,
		Active:    true,
		CreatedAt: now,
		UpdatedAt: now,
		Metadata:  u.Metadata,
	}

	if user.Role == "" {
		user.Role = "user"
	}

	us.users[id] = user
	us.byEmail[email] = id
	return user, nil
}

func (us *UserStore) GetByID(id int64) (*User, error) {
	us.mu.RLock()
	defer us.mu.RUnlock()

	user, ok := us.users[id]
	if !ok {
		return nil, fmt.Errorf("user %d not found", id)
	}
	return user, nil
}

func (us *UserStore) GetByEmail(email string) (*User, error) {
	us.mu.RLock()
	defer us.mu.RUnlock()

	id, ok := us.byEmail[strings.ToLower(email)]
	if !ok {
		return nil, fmt.Errorf("user with email %s not found", email)
	}
	return us.users[id], nil
}

func (us *UserStore) List(page, perPage int) ([]*User, int64) {
	us.mu.RLock()
	defer us.mu.RUnlock()

	all := make([]*User, 0, len(us.users))
	for _, u := range us.users {
		if u.Active {
			all = append(all, u)
		}
	}

	sort.Slice(all, func(i, j int) bool { return all[i].ID < all[j].ID })

	total := int64(len(all))
	start := (page - 1) * perPage
	if start >= len(all) {
		return []*User{}, total
	}
	end := start + perPage
	if end > len(all) {
		end = len(all)
	}
	return all[start:end], total
}

func (us *UserStore) Delete(id int64) error {
	us.mu.Lock()
	defer us.mu.Unlock()

	user, ok := us.users[id]
	if !ok {
		return fmt.Errorf("user %d not found", id)
	}
	delete(us.byEmail, user.Email)
	delete(us.users, id)
	return nil
}

func (us *UserStore) Update(id int64, updates map[string]interface{}) (*User, error) {
	us.mu.Lock()
	defer us.mu.Unlock()

	user, ok := us.users[id]
	if !ok {
		return nil, fmt.Errorf("user %d not found", id)
	}

	if name, ok := updates["name"].(string); ok {
		user.Name = name
	}
	if role, ok := updates["role"].(string); ok {
		user.Role = role
	}
	if active, ok := updates["active"].(bool); ok {
		user.Active = active
	}
	if meta, ok := updates["metadata"].(map[string]interface{}); ok {
		if user.Metadata == nil {
			user.Metadata = make(map[string]interface{})
		}
		for k, v := range meta {
			user.Metadata[k] = v
		}
	}

	user.UpdatedAt = time.Now()
	return user, nil
}

func (us *UserStore) Count() int {
	us.mu.RLock()
	defer us.mu.RUnlock()
	return len(us.users)
}

func (us *UserStore) Search(query string) []*User {
	us.mu.RLock()
	defer us.mu.RUnlock()

	query = strings.ToLower(query)
	results := make([]*User, 0)
	for _, u := range us.users {
		if strings.Contains(strings.ToLower(u.Name), query) ||
			strings.Contains(u.Email, query) {
			results = append(results, u)
		}
	}
	sort.Slice(results, func(i, j int) bool { return results[i].ID < results[j].ID })
	return results
}

// ─── Retry Logic ───────────────────────────────────────────────────

type RetryConfig struct {
	MaxAttempts int
	BaseDelay   time.Duration
	MaxDelay    time.Duration
	Multiplier  float64
	Jitter      bool
}

func DefaultRetryConfig() RetryConfig {
	return RetryConfig{
		MaxAttempts: RetryMaxAttempts,
		BaseDelay:   RetryBaseDelay,
		MaxDelay:    RetryMaxDelay,
		Multiplier:  2.0,
		Jitter:      true,
	}
}

func RetryWithBackoff(ctx context.Context, config RetryConfig, fn func() error) error {
	var lastErr error
	delay := config.BaseDelay

	for attempt := 0; attempt < config.MaxAttempts; attempt++ {
		if err := ctx.Err(); err != nil {
			return fmt.Errorf("context cancelled after %d attempts: %w", attempt, err)
		}

		lastErr = fn()
		if lastErr == nil {
			return nil
		}

		if attempt < config.MaxAttempts-1 {
			if config.Jitter {
				jitter := time.Duration(rand.Int63n(int64(delay / 2)))
				delay = delay + jitter
			}
			if delay > config.MaxDelay {
				delay = config.MaxDelay
			}

			select {
			case <-time.After(delay):
			case <-ctx.Done():
				return ctx.Err()
			}

			delay = time.Duration(float64(delay) * config.Multiplier)
		}
	}

	return fmt.Errorf("max retries (%d) exceeded: %w", config.MaxAttempts, lastErr)
}

// ─── Utility Functions ─────────────────────────────────────────────

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(data); err != nil {
		log.Printf("ERROR: failed to encode JSON response: %v", err)
	}
}

func extractIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		parts := strings.Split(xff, ",")
		return strings.TrimSpace(parts[0])
	}
	if xri := r.Header.Get("X-Real-IP"); xri != "" {
		return xri
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

func extractToken(r *http.Request) string {
	auth := r.Header.Get("Authorization")
	if strings.HasPrefix(auth, "Bearer ") {
		return strings.TrimPrefix(auth, "Bearer ")
	}
	if cookie, err := r.Cookie("session_token"); err == nil {
		return cookie.Value
	}
	return r.URL.Query().Get("token")
}

func generateToken() string {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		panic(fmt.Sprintf("failed to generate token: %v", err))
	}
	return fmt.Sprintf("%x", b)
}

var startTime = time.Now()

// ─── TLS Configuration ────────────────────────────────────────────

func configureTLS(certFile, keyFile string) *tls.Config {
	return &tls.Config{
		MinVersion:               tls.VersionTLS13,
		CurvePreferences:         []tls.CurveID{tls.X25519, tls.CurveP256},
		PreferServerCipherSuites: true,
		CipherSuites: []uint16{
			tls.TLS_AES_128_GCM_SHA256,
			tls.TLS_AES_256_GCM_SHA384,
			tls.TLS_CHACHA20_POLY1305_SHA256,
		},
	}
}

// ─── Graceful Shutdown ─────────────────────────────────────────────

func gracefulShutdown(srv *http.Server, done chan<- struct{}) {
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	sig := <-sigChan
	log.Printf("Received signal %v, initiating graceful shutdown...", sig)

	ctx, cancel := context.WithTimeout(context.Background(), ShutdownTimeout)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		log.Printf("ERROR: server shutdown failed: %v", err)
		srv.Close()
	}

	close(done)
}

// ─── Main ──────────────────────────────────────────────────────────

func main() {
	logger := log.New(os.Stdout, "[server] ", log.LstdFlags|log.Lmicroseconds)

	port := os.Getenv("PORT")
	if port == "" {
		port = strconv.Itoa(DefaultPort)
	}

	userStore := NewUserStore()
	sessionStore := NewSessionStore(24 * time.Hour)
	rateLimiter := NewRateLimiter(RateLimitWindow, RateLimitMax)
	metrics := NewMetricsCollector(MetricsFlushInterval)
	breaker := NewCircuitBreaker(CircuitBreakerMax, CircuitBreakerReset)

	_ = breaker // used in production handlers

	router := NewRouter("/api/v1")
	router.Handle("/health", handleHealth)
	router.Handle("/users", handleListUsers(userStore))
	router.Handle("/users/", handleGetUser(userStore))

	handler := ChainMiddleware(
		router,
		MetricsMiddleware(metrics),
		RateLimitMiddleware(rateLimiter),
		LoggingMiddleware(logger),
		RecoveryMiddleware(logger),
		CORSMiddleware([]string{"*"}),
	)

	srv := &http.Server{
		Addr:         ":" + port,
		Handler:      handler,
		ReadTimeout:  ReadTimeout,
		WriteTimeout: WriteTimeout,
		IdleTimeout:  IdleTimeout,
		MaxHeaderBytes: 1 << 20,
	}

	done := make(chan struct{})
	go gracefulShutdown(srv, done)

	logger.Printf("Server starting on :%s", port)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		logger.Fatalf("Server failed: %v", err)
	}

	<-done
	metrics.Close()
	logger.Println("Server stopped")
}
