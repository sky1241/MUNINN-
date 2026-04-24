// store.ts — Lightweight state management library
// Inspired by Redux, Zustand, and Redux Toolkit patterns
// Zero external dependencies

// ============================================================================
// Core Type Definitions
// ============================================================================

type DeepPartial<T> = { [P in keyof T]?: T[P] extends object ? DeepPartial<T[P]> : T[P] };
type DeepReadonly<T> = { readonly [P in keyof T]: T[P] extends object ? DeepReadonly<T[P]> : T[P] };
type Listener<S> = (state: S, prevState: S) => void;
type Unsubscribe = () => void;
type Selector<S, R> = (state: S) => R;
type EqualityFn<T> = (a: T, b: T) => boolean;
type Draft<T> = { -readonly [P in keyof T]: Draft<T[P]> };

interface Action<T extends string = string> {
  type: T;
  payload?: unknown;
  meta?: Record<string, unknown>;
  error?: boolean;
}

interface ActionCreator<T extends string, P = void> {
  type: T;
  (payload: P): Action<T> & { payload: P };
  match(action: Action): action is Action<T> & { payload: P };
}

type Reducer<S, A extends Action = Action> = (state: S, action: A) => S;
type Dispatch = (action: Action | ThunkAction) => unknown;
type ThunkAction = (dispatch: Dispatch, getState: () => unknown) => unknown;

interface Middleware<S = unknown> {
  name: string;
  (store: MiddlewareAPI<S>): (next: Dispatch) => (action: Action | ThunkAction) => unknown;
}

interface MiddlewareAPI<S = unknown> {
  getState: () => S;
  dispatch: Dispatch;
}

interface StoreOptions<S> {
  initialState: S;
  reducer: Reducer<S>;
  middleware?: Middleware<S>[];
  devtools?: boolean;
  enableUndo?: boolean;
  maxUndoHistory?: number;
  batchUpdates?: boolean;
}

interface StorageAdapter {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

interface CaseReducer<S, A extends Action = Action> {
  (state: S, action: A): S | void;
}

interface ReducerBuilder<S> {
  addCase<T extends string, P>(
    actionCreator: ActionCreator<T, P>,
    reducer: CaseReducer<S, Action<T> & { payload: P }>
  ): ReducerBuilder<S>;
  addMatcher(
    matcher: (action: Action) => boolean,
    reducer: CaseReducer<S, Action>
  ): ReducerBuilder<S>;
  addDefaultCase(reducer: CaseReducer<S, Action>): ReducerBuilder<S>;
}

// ============================================================================
// Utility Functions
// ============================================================================

function shallowEqual<T>(a: T, b: T): boolean {
  if (Object.is(a, b)) return true;
  if (typeof a !== "object" || a === null || typeof b !== "object" || b === null) return false;
  const keysA = Object.keys(a as Record<string, unknown>);
  const keysB = Object.keys(b as Record<string, unknown>);
  if (keysA.length !== keysB.length) return false;
  for (const key of keysA) {
    if (!Object.is((a as Record<string, unknown>)[key], (b as Record<string, unknown>)[key])) return false;
  }
  return true;
}

function deepEqual(a: unknown, b: unknown): boolean {
  if (Object.is(a, b)) return true;
  if (typeof a !== typeof b || a === null || b === null || typeof a !== "object") return false;
  const objA = a as Record<string, unknown>;
  const objB = b as Record<string, unknown>;
  if (Array.isArray(objA) !== Array.isArray(objB)) return false;
  const keysA = Object.keys(objA);
  if (keysA.length !== Object.keys(objB).length) return false;
  for (const key of keysA) {
    if (!deepEqual(objA[key], objB[key])) return false;
  }
  return true;
}

function deepClone<T>(obj: T): T {
  if (obj === null || typeof obj !== "object") return obj;
  if (Array.isArray(obj)) return obj.map((item) => deepClone(item)) as unknown as T;
  const cloned: Record<string, unknown> = {};
  for (const key of Object.keys(obj as Record<string, unknown>)) {
    cloned[key] = deepClone((obj as Record<string, unknown>)[key]);
  }
  return cloned as T;
}

function deepFreeze<T>(obj: T): DeepReadonly<T> {
  if (obj === null || typeof obj !== "object") return obj as DeepReadonly<T>;
  Object.freeze(obj);
  for (const key of Object.keys(obj as Record<string, unknown>)) {
    const value = (obj as Record<string, unknown>)[key];
    if (typeof value === "object" && value !== null && !Object.isFrozen(value)) deepFreeze(value);
  }
  return obj as DeepReadonly<T>;
}

function deepMerge<T extends Record<string, unknown>>(target: T, source: DeepPartial<T>): T {
  const result = { ...target };
  for (const key of Object.keys(source)) {
    const sv = (source as Record<string, unknown>)[key];
    const tv = (result as Record<string, unknown>)[key];
    if (typeof sv === "object" && sv !== null && !Array.isArray(sv) && typeof tv === "object" && tv !== null && !Array.isArray(tv)) {
      (result as Record<string, unknown>)[key] = deepMerge(tv as Record<string, unknown>, sv as DeepPartial<Record<string, unknown>>);
    } else {
      (result as Record<string, unknown>)[key] = sv;
    }
  }
  return result;
}

// ============================================================================
// Immer-like Produce (Structural Sharing via Proxy)
// ============================================================================

interface DraftState<T> {
  base: T; copy: T | undefined; modified: boolean;
  children: Map<string | symbol, DraftState<unknown>>;
  parent: DraftState<unknown> | null;
}

function createDraftState<T>(base: T, parent: DraftState<unknown> | null = null): DraftState<T> {
  return { base, copy: undefined, modified: false, children: new Map(), parent };
}

function markModified(state: DraftState<unknown>): void {
  if (state.modified) return;
  state.modified = true;
  if (state.copy === undefined) {
    if (Array.isArray(state.base)) state.copy = [...state.base] as unknown;
    else if (typeof state.base === "object" && state.base !== null)
      state.copy = { ...(state.base as Record<string, unknown>) } as unknown;
  }
  if (state.parent) markModified(state.parent);
}

function createProxy<T extends object>(state: DraftState<T>): Draft<T> {
  const handler: ProxyHandler<T> = {
    get(_target: T, prop: string | symbol): unknown {
      const source = state.modified ? (state.copy as T) : state.base;
      const value = (source as Record<string | symbol, unknown>)[prop];
      if (typeof value === "object" && value !== null) {
        const key = prop as string;
        if (!state.children.has(key)) {
          state.children.set(key, createDraftState(value, state as DraftState<unknown>));
        }
        return createProxy(state.children.get(key) as DraftState<object>);
      }
      return value;
    },
    set(_target: T, prop: string | symbol, value: unknown): boolean {
      markModified(state);
      (state.copy as Record<string | symbol, unknown>)[prop] = value;
      state.children.delete(prop as string);
      return true;
    },
    deleteProperty(_target: T, prop: string | symbol): boolean {
      markModified(state);
      delete (state.copy as Record<string | symbol, unknown>)[prop];
      state.children.delete(prop as string);
      return true;
    },
    has(_target: T, prop: string | symbol): boolean {
      const source = state.modified ? (state.copy as T) : state.base;
      return prop in (source as Record<string | symbol, unknown>);
    },
    ownKeys(): (string | symbol)[] {
      return Reflect.ownKeys((state.modified ? state.copy : state.base) as object);
    },
  };
  return new Proxy(state.base, handler) as Draft<T>;
}

function finalize<T>(state: DraftState<T>): T {
  if (!state.modified) return state.base;
  const result = state.copy as T;
  for (const [key, childState] of state.children) {
    (result as Record<string | symbol, unknown>)[key] = finalize(childState as DraftState<unknown>);
  }
  return result;
}

function produce<T extends object>(base: T, recipe: (draft: Draft<T>) => void | T): T {
  const state = createDraftState(base);
  const result = recipe(createProxy(state));
  if (result !== undefined) return result as T;
  return finalize(state);
}

// ============================================================================
// Action Creators
// ============================================================================

function createAction<T extends string, P = void>(type: T): ActionCreator<T, P> {
  const ac = (payload: P) => ({ type, payload });
  ac.type = type;
  ac.match = (action: Action): action is Action<T> & { payload: P } => action.type === type;
  return ac as ActionCreator<T, P>;
}

// ============================================================================
// Reducer Builder & Combine
// ============================================================================

function createReducer<S>(
  initialState: S,
  builderCallback: (builder: ReducerBuilder<S>) => void
): Reducer<S> {
  const cases = new Map<string, CaseReducer<S, Action>>();
  const matchers: Array<{ matcher: (a: Action) => boolean; reducer: CaseReducer<S, Action> }> = [];
  let defaultCase: CaseReducer<S, Action> | null = null;

  const builder: ReducerBuilder<S> = {
    addCase(ac: { type: string }, reducer: CaseReducer<S, Action>): ReducerBuilder<S> {
      cases.set(ac.type, reducer as CaseReducer<S, Action>);
      return builder;
    },
    addMatcher(matcher: (a: Action) => boolean, reducer: CaseReducer<S, Action>): ReducerBuilder<S> {
      matchers.push({ matcher, reducer });
      return builder;
    },
    addDefaultCase(reducer: CaseReducer<S, Action>): ReducerBuilder<S> {
      defaultCase = reducer;
      return builder;
    },
  };

  builderCallback(builder);

  return (state: S = initialState, action: Action): S => {
    let next = state;
    const applyReducer = (r: CaseReducer<S, Action>, s: S, a: Action): S => {
      if (typeof s === "object" && s !== null) {
        return produce(s as object, (draft) => { return r(draft as S, a) as void; }) as S;
      }
      const result = r(s, a);
      return result !== undefined ? result : s;
    };

    const caseR = cases.get(action.type);
    if (caseR) next = applyReducer(caseR, next, action);

    for (const { matcher, reducer } of matchers) {
      if (matcher(action)) next = applyReducer(reducer, next, action);
    }

    if (next === state && defaultCase) next = applyReducer(defaultCase, state, action);
    return next;
  };
}

type ReducersMapObject<S> = { [K in keyof S]: Reducer<S[K]> };

function combineReducers<S extends Record<string, unknown>>(reducers: ReducersMapObject<S>): Reducer<S> {
  const keys = Object.keys(reducers) as Array<keyof S>;
  return (state: S, action: Action): S => {
    let changed = false;
    const next = {} as S;
    for (const key of keys) {
      const prev = state ? state[key] : undefined;
      next[key] = reducers[key](prev as S[typeof key], action);
      changed = changed || next[key] !== prev;
    }
    return changed ? next : state;
  };
}

// ============================================================================
// Memoized Selectors (Reselect-like)
// ============================================================================

interface MemoizedSelector<S, R> {
  (state: S): R;
  recomputations: () => number;
  resetRecomputations: () => void;
  lastResult: () => R | undefined;
  clearCache: () => void;
}

function createSelector<S, Result>(
  ...args: [...Selector<S, unknown>[], (...values: unknown[]) => Result]
): MemoizedSelector<S, Result> {
  const combiner = args.pop() as (...v: unknown[]) => Result;
  const selectors = args as Selector<S, unknown>[];
  let lastInputs: unknown[] | null = null;
  let lastResult: Result | undefined;
  let count = 0;

  const memoized = (state: S): Result => {
    const inputs = selectors.map((s) => s(state));
    if (lastInputs && inputs.length === lastInputs.length && inputs.every((v, i) => Object.is(v, lastInputs![i]))) {
      return lastResult!;
    }
    lastInputs = inputs;
    count++;
    lastResult = combiner(...inputs);
    return lastResult;
  };
  memoized.recomputations = () => count;
  memoized.resetRecomputations = () => { count = 0; };
  memoized.lastResult = () => lastResult;
  memoized.clearCache = () => { lastInputs = null; lastResult = undefined; };
  return memoized;
}

// ============================================================================
// Subscription Manager with Batching
// ============================================================================

interface SubscriptionManager<S> {
  subscribe(listener: Listener<S>): Unsubscribe;
  subscribeWithSelector<R>(sel: Selector<S, R>, fn: (s: R, p: R) => void, eq?: EqualityFn<R>): Unsubscribe;
  notify(state: S, prev: S): void;
  getListenerCount(): number;
  clear(): void;
}

function createSubscriptionManager<S>(batched: boolean = false): SubscriptionManager<S> {
  const listeners = new Set<Listener<S>>();
  let batchQueue: Array<{ state: S; prevState: S }> = [];
  let batchTimer: ReturnType<typeof setTimeout> | null = null;

  function processBatch(): void {
    if (batchQueue.length === 0) return;
    const first = batchQueue[0].prevState;
    const last = batchQueue[batchQueue.length - 1].state;
    batchQueue = [];
    for (const l of listeners) { try { l(last, first); } catch (e) { console.error("[Store]", e); } }
  }

  return {
    subscribe(listener: Listener<S>): Unsubscribe {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    subscribeWithSelector<R>(sel: Selector<S, R>, fn: (s: R, p: R) => void, eq: EqualityFn<R> = Object.is): Unsubscribe {
      let last: R | undefined; let init = false;
      const wrapped: Listener<S> = (state) => {
        const cur = sel(state);
        if (!init) { init = true; last = cur; return; }
        if (!eq(cur, last as R)) { const prev = last as R; last = cur; fn(cur, prev); }
      };
      listeners.add(wrapped);
      return () => { listeners.delete(wrapped); };
    },
    notify(state: S, prev: S): void {
      if (batched) {
        batchQueue.push({ state, prevState: prev });
        if (batchTimer === null) {
          batchTimer = setTimeout(() => { batchTimer = null; processBatch(); }, 0);
        }
      } else {
        for (const l of listeners) { try { l(state, prev); } catch (e) { console.error("[Store]", e); } }
      }
    },
    getListenerCount: () => listeners.size,
    clear(): void {
      listeners.clear(); batchQueue = [];
      if (batchTimer !== null) { clearTimeout(batchTimer); batchTimer = null; }
    },
  };
}

// ============================================================================
// Undo/Redo History
// ============================================================================

interface UndoRedoState<S> { past: S[]; present: S; future: S[] }

const UNDO_ACTION = "@@store/UNDO";
const REDO_ACTION = "@@store/REDO";

function createUndoRedoManager<S>(initialState: S, maxHistory: number = 50) {
  const st: UndoRedoState<S> = { past: [], present: initialState, future: [] };

  return {
    getState: () => ({ ...st }),
    push(newState: S): void {
      if (Object.is(newState, st.present)) return;
      st.past.push(st.present);
      if (st.past.length > maxHistory) st.past.shift();
      st.present = newState;
      st.future = [];
    },
    undo(): S | null {
      if (st.past.length === 0) return null;
      st.future.unshift(st.present);
      st.present = st.past.pop()!;
      return st.present;
    },
    redo(): S | null {
      if (st.future.length === 0) return null;
      st.past.push(st.present);
      st.present = st.future.shift()!;
      return st.present;
    },
    canUndo: () => st.past.length > 0,
    canRedo: () => st.future.length > 0,
    clear(): void { st.past = []; st.future = []; },
    jumpToPast(index: number): S | null {
      if (index < 0 || index >= st.past.length) return null;
      const target = st.past[index];
      const newFuture = [...st.past.slice(index + 1), st.present, ...st.future];
      st.past = st.past.slice(0, index);
      st.present = target;
      st.future = newFuture;
      return target;
    },
    jumpToFuture(index: number): S | null {
      if (index < 0 || index >= st.future.length) return null;
      const target = st.future[index];
      const newPast = [...st.past, st.present, ...st.future.slice(0, index)];
      st.past = newPast;
      st.present = target;
      st.future = st.future.slice(index + 1);
      return target;
    },
    getPastLength: () => st.past.length,
    getFutureLength: () => st.future.length,
  };
}

// ============================================================================
// Middleware: Logger
// ============================================================================

interface LoggerOptions {
  collapsed?: boolean;
  predicate?: (state: unknown, action: Action) => boolean;
  timestamp?: boolean;
  duration?: boolean;
  diff?: boolean;
}

interface DiffEntry { path: string; oldValue: unknown; newValue: unknown }

function computeDiff(prev: Record<string, unknown>, next: Record<string, unknown>, path = ""): DiffEntry[] {
  const diffs: DiffEntry[] = [];
  const allKeys = new Set([...Object.keys(prev), ...Object.keys(next)]);
  for (const key of allKeys) {
    const cp = path ? `${path}.${key}` : key;
    const pv = prev[key], nv = next[key];
    if (Object.is(pv, nv)) continue;
    if (typeof pv === "object" && pv !== null && typeof nv === "object" && nv !== null && !Array.isArray(pv) && !Array.isArray(nv)) {
      diffs.push(...computeDiff(pv as Record<string, unknown>, nv as Record<string, unknown>, cp));
    } else {
      diffs.push({ path: cp, oldValue: pv, newValue: nv });
    }
  }
  return diffs;
}

function createLoggerMiddleware<S>(options: LoggerOptions = {}): Middleware<S> {
  const { collapsed = false, predicate, timestamp = true, duration = true, diff = false } = options;
  const mw: Middleware<S> = (store) => (next) => (action) => {
    if (typeof action === "function") return next(action);
    const typed = action as Action;
    if (predicate && !predicate(store.getState(), typed)) return next(action);
    const start = Date.now();
    const prevState = store.getState();
    const grp = collapsed ? "groupCollapsed" : "group";
    const title = `action: ${typed.type}${timestamp ? ` @ ${new Date().toISOString()}` : ""}`;
    if ((console as Record<string, unknown>)[grp]) (console as Record<string, Function>)[grp](title);
    console.log("%c prev state", "color: #9E9E9E; font-weight: bold", prevState);
    console.log("%c action    ", "color: #03A9F4; font-weight: bold", typed);
    const result = next(action);
    const nextState = store.getState();
    console.log("%c next state", "color: #4CAF50; font-weight: bold", nextState);
    if (duration) console.log("%c duration  ", "color: #808080; font-weight: bold", `${Date.now() - start}ms`);
    if (diff && typeof prevState === "object" && typeof nextState === "object") {
      const changes = computeDiff(prevState as Record<string, unknown>, nextState as Record<string, unknown>);
      if (changes.length > 0) console.log("%c diff", "color: #E8710A; font-weight: bold", changes);
    }
    if (console.groupEnd) console.groupEnd();
    return result;
  };
  mw.name = "logger";
  return mw;
}

// ============================================================================
// Middleware: Thunk
// ============================================================================

function createThunkMiddleware<S>(): Middleware<S> {
  const mw: Middleware<S> = (store) => (next) => (action) => {
    if (typeof action === "function") return (action as ThunkAction)(store.dispatch, store.getState as () => unknown);
    return next(action);
  };
  mw.name = "thunk";
  return mw;
}

// ============================================================================
// Middleware: DevTools
// ============================================================================

interface DevToolsEntry { action: Action; state: unknown; timestamp: number; duration?: number }

class DevToolsMonitor {
  private entries: DevToolsEntry[] = [];
  private currentIndex = -1;
  private isPaused = false;
  private maxEntries: number;
  private listeners = new Set<(entries: DevToolsEntry[]) => void>();

  constructor(maxEntries = 200) { this.maxEntries = maxEntries; }

  record(action: Action, state: unknown, duration?: number): void {
    if (this.isPaused) return;
    this.entries = this.entries.slice(0, this.currentIndex + 1);
    this.entries.push({ action, state: deepClone(state), timestamp: Date.now(), duration });
    if (this.entries.length > this.maxEntries) this.entries.shift();
    this.currentIndex = this.entries.length - 1;
    for (const l of this.listeners) l(this.entries);
  }

  jumpToState(i: number): unknown | null {
    if (i < 0 || i >= this.entries.length) return null;
    this.currentIndex = i;
    return this.entries[i].state;
  }

  pause(): void { this.isPaused = true; }
  resume(): void { this.isPaused = false; }
  reset(): void { this.entries = []; this.currentIndex = -1; }
  getEntries(): DevToolsEntry[] { return [...this.entries]; }

  subscribe(listener: (entries: DevToolsEntry[]) => void): Unsubscribe {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

function createDevToolsMiddleware<S>(monitor?: DevToolsMonitor): Middleware<S> {
  const dt = monitor || new DevToolsMonitor();
  const mw: Middleware<S> = (store) => (next) => (action) => {
    if (typeof action === "function") return next(action);
    const start = performance.now();
    const result = next(action);
    dt.record(action as Action, store.getState(), performance.now() - start);
    return result;
  };
  mw.name = "devtools";
  return mw;
}

// ============================================================================
// Middleware: Persistence
// ============================================================================

class InMemoryStorage implements StorageAdapter {
  private data = new Map<string, string>();
  getItem(key: string): string | null { return this.data.get(key) || null; }
  setItem(key: string, value: string): void { this.data.set(key, value); }
  removeItem(key: string): void { this.data.delete(key); }
}

interface PersistenceOptions {
  key: string;
  storage?: StorageAdapter;
  whitelist?: string[];
  blacklist?: string[];
  debounceMs?: number;
  version?: number;
  migrate?: (persisted: unknown, version: number) => unknown;
}

function createPersistenceMiddleware<S>(options: PersistenceOptions): Middleware<S> {
  const { key, storage = new InMemoryStorage(), whitelist, blacklist, debounceMs = 100, version = 1 } = options;
  let timer: ReturnType<typeof setTimeout> | null = null;

  function filterAndSave(state: S): void {
    if (typeof state !== "object" || state === null) return;
    const filtered: Record<string, unknown> = {};
    for (const k of Object.keys(state as Record<string, unknown>)) {
      if (whitelist && !whitelist.includes(k)) continue;
      if (blacklist && blacklist.includes(k)) continue;
      filtered[k] = (state as Record<string, unknown>)[k];
    }
    storage.setItem(key, JSON.stringify({ version, state: filtered, timestamp: Date.now() }));
  }

  const mw: Middleware<S> = (_store) => (next) => (action) => {
    const result = next(action);
    const current = _store.getState() as S;
    if (timer !== null) clearTimeout(timer);
    timer = setTimeout(() => { filterAndSave(current); timer = null; }, debounceMs);
    return result;
  };
  mw.name = "persistence";
  return mw;
}

function loadPersistedState<S>(options: PersistenceOptions): Partial<S> | null {
  const { key, storage = new InMemoryStorage(), version = 1, migrate } = options;
  try {
    const raw = storage.getItem(key);
    if (!raw) return null;
    const envelope = JSON.parse(raw) as { version: number; state: unknown };
    if (envelope.version !== version && migrate) return migrate(envelope.state, envelope.version) as Partial<S>;
    return envelope.state as Partial<S>;
  } catch { return null; }
}

// ============================================================================
// State Serialization / Deserialization
// ============================================================================

const TYPE_TAG = "__$$type";
const VALUE_TAG = "__$$value";

function createSerializer() {
  return (state: unknown): string => {
    return JSON.stringify(state, (_key, value) => {
      if (value instanceof Date) return { [TYPE_TAG]: "Date", [VALUE_TAG]: value.toISOString() };
      if (value instanceof Map) return { [TYPE_TAG]: "Map", [VALUE_TAG]: Array.from(value.entries()) };
      if (value instanceof Set) return { [TYPE_TAG]: "Set", [VALUE_TAG]: Array.from(value) };
      if (value instanceof RegExp) return { [TYPE_TAG]: "RegExp", [VALUE_TAG]: { source: value.source, flags: value.flags } };
      if (value === undefined) return { [TYPE_TAG]: "undefined" };
      if (typeof value === "bigint") return { [TYPE_TAG]: "BigInt", [VALUE_TAG]: value.toString() };
      return value;
    }, 2);
  };
}

function createDeserializer() {
  return (data: string): unknown => {
    return JSON.parse(data, (_key, value) => {
      if (typeof value === "object" && value !== null && TYPE_TAG in value) {
        const type = value[TYPE_TAG]; const val = value[VALUE_TAG];
        if (type === "Date") return new Date(val);
        if (type === "Map") return new Map(val);
        if (type === "Set") return new Set(val);
        if (type === "RegExp") return new RegExp(val.source, val.flags);
        if (type === "undefined") return undefined;
        if (type === "BigInt") return BigInt(val);
      }
      return value;
    });
  };
}

function createStateSnapshot<S>(state: S): string { return createSerializer()(state); }
function restoreStateSnapshot<S>(data: string): S { return createDeserializer()(data) as S; }

// ============================================================================
// Normalized Entity Adapter
// ============================================================================

interface EntityState<T> { ids: string[]; entities: Record<string, T> }

interface EntitySelectors<T, S> {
  selectIds: (state: S) => string[];
  selectEntities: (state: S) => Record<string, T>;
  selectAll: (state: S) => T[];
  selectTotal: (state: S) => number;
  selectById: (state: S, id: string) => T | undefined;
}

interface SortComparer<T> { (a: T, b: T): number }

interface EntityAdapter<T> {
  getInitialState(): EntityState<T>;
  getInitialState<E extends Record<string, unknown>>(extra: E): EntityState<T> & E;
  addOne(state: EntityState<T>, entity: T): EntityState<T>;
  addMany(state: EntityState<T>, entities: T[]): EntityState<T>;
  setOne(state: EntityState<T>, entity: T): EntityState<T>;
  setAll(state: EntityState<T>, entities: T[]): EntityState<T>;
  removeOne(state: EntityState<T>, id: string): EntityState<T>;
  removeMany(state: EntityState<T>, ids: string[]): EntityState<T>;
  removeAll(state: EntityState<T>): EntityState<T>;
  updateOne(state: EntityState<T>, update: { id: string; changes: Partial<T> }): EntityState<T>;
  upsertOne(state: EntityState<T>, entity: T): EntityState<T>;
  upsertMany(state: EntityState<T>, entities: T[]): EntityState<T>;
  getSelectors(): EntitySelectors<T, EntityState<T>>;
  getSelectors<S>(selectState: (state: S) => EntityState<T>): EntitySelectors<T, S>;
}

function createEntityAdapter<T>(opts: { selectId?: (e: T) => string; sortComparer?: SortComparer<T> } = {}): EntityAdapter<T> {
  const { selectId = (e: T) => (e as Record<string, unknown>)["id"] as string, sortComparer } = opts;

  function sorted(st: EntityState<T>): EntityState<T> {
    if (!sortComparer) return st;
    const items = st.ids.map((id) => st.entities[id]).filter(Boolean).sort(sortComparer);
    return { ids: items.map((e) => selectId(e)), entities: st.entities };
  }

  function addOneInternal(st: EntityState<T>, entity: T): EntityState<T> {
    const id = selectId(entity);
    if (st.entities[id]) return st;
    return sorted({ ids: [...st.ids, id], entities: { ...st.entities, [id]: entity } });
  }

  return {
    getInitialState<E extends Record<string, unknown>>(extra?: E) {
      const base: EntityState<T> = { ids: [], entities: {} };
      return extra ? { ...base, ...extra } as EntityState<T> & E : base as EntityState<T> & E;
    },
    addOne: (st, e) => addOneInternal(st, e),
    addMany: (st, es) => es.reduce((s, e) => addOneInternal(s, e), st),
    setOne(st, entity) {
      const id = selectId(entity);
      const exists = !!st.entities[id];
      return sorted({ ids: exists ? [...st.ids] : [...st.ids, id], entities: { ...st.entities, [id]: entity } });
    },
    setAll(_, entities) {
      const ents: Record<string, T> = {}; const ids: string[] = [];
      for (const e of entities) { const id = selectId(e); ents[id] = e; ids.push(id); }
      return sorted({ ids, entities: ents });
    },
    removeOne(st, id) {
      if (!st.entities[id]) return st;
      const ents = { ...st.entities }; delete ents[id];
      return { ids: st.ids.filter((i) => i !== id), entities: ents };
    },
    removeMany(st, ids) {
      const set = new Set(ids); const ents = { ...st.entities };
      for (const id of ids) delete ents[id];
      return { ids: st.ids.filter((i) => !set.has(i)), entities: ents };
    },
    removeAll: () => ({ ids: [], entities: {} }),
    updateOne(st, update) {
      const existing = st.entities[update.id];
      if (!existing) return st;
      return sorted({ ids: [...st.ids], entities: { ...st.entities, [update.id]: { ...existing, ...update.changes } } });
    },
    upsertOne(st, entity) {
      const id = selectId(entity);
      const existing = st.entities[id];
      if (existing) return sorted({ ids: [...st.ids], entities: { ...st.entities, [id]: { ...existing, ...entity } } });
      return addOneInternal(st, entity);
    },
    upsertMany(st, entities) { return entities.reduce((s, e) => this.upsertOne(s, e), st); },
    getSelectors<S>(selectState?: (state: S) => EntityState<T>): EntitySelectors<T, S> {
      const sel = selectState || ((s: unknown) => s as EntityState<T>);
      return {
        selectIds: (s: S) => (sel(s) as EntityState<T>).ids,
        selectEntities: (s: S) => (sel(s) as EntityState<T>).entities,
        selectAll: (s: S) => { const es = sel(s) as EntityState<T>; return es.ids.map((id) => es.entities[id]).filter(Boolean); },
        selectTotal: (s: S) => (sel(s) as EntityState<T>).ids.length,
        selectById: (s: S, id: string) => (sel(s) as EntityState<T>).entities[id],
      } as EntitySelectors<T, S>;
    },
  } as EntityAdapter<T>;
}

// ============================================================================
// Async Action Handling
// ============================================================================

interface AsyncState<T> {
  data: T | null; loading: boolean; error: string | null;
  lastFetched: number | null; requestId: string | null;
}

let asyncIdCounter = 0;

interface AsyncThunk<Arg, Result> {
  (arg: Arg): ThunkAction;
  typePrefix: string;
  pending: ActionCreator<string, { arg: Arg; requestId: string }>;
  fulfilled: ActionCreator<string, { arg: Arg; result: Result; requestId: string }>;
  rejected: ActionCreator<string, { arg: Arg; error: string; requestId: string }>;
}

function createAsyncThunk<Arg, Result>(
  typePrefix: string,
  payloadCreator: (arg: Arg, api: { dispatch: Dispatch; getState: () => unknown; requestId: string }) => Promise<Result>
): AsyncThunk<Arg, Result> {
  const pending = createAction<string, { arg: Arg; requestId: string }>(`${typePrefix}/pending`);
  const fulfilled = createAction<string, { arg: Arg; result: Result; requestId: string }>(`${typePrefix}/fulfilled`);
  const rejected = createAction<string, { arg: Arg; error: string; requestId: string }>(`${typePrefix}/rejected`);

  const thunk = (arg: Arg): ThunkAction => {
    return async (dispatch: Dispatch, getState: () => unknown) => {
      const requestId = `req_${++asyncIdCounter}_${Date.now()}`;
      dispatch(pending({ arg, requestId }));
      try {
        const result = await payloadCreator(arg, { dispatch, getState, requestId });
        dispatch(fulfilled({ arg, result, requestId }));
        return result;
      } catch (err) {
        dispatch(rejected({ arg, error: err instanceof Error ? err.message : String(err), requestId }));
        throw err;
      }
    };
  };

  thunk.typePrefix = typePrefix;
  thunk.pending = pending;
  thunk.fulfilled = fulfilled;
  thunk.rejected = rejected;
  return thunk as AsyncThunk<Arg, Result>;
}

function createAsyncState<T>(initial: T | null = null): AsyncState<T> {
  return { data: initial, loading: false, error: null, lastFetched: null, requestId: null };
}

// ============================================================================
// Router State Management
// ============================================================================

interface RouteParams { [key: string]: string }
interface RouteDefinition { path: string; name?: string; meta?: Record<string, unknown>; children?: RouteDefinition[] }

interface RouterState {
  currentPath: string; params: RouteParams; query: Record<string, string>;
  hash: string; history: string[]; historyIndex: number;
  routes: RouteDefinition[]; matchedRoute: RouteDefinition | null;
  isNavigating: boolean; navigationError: string | null;
}

interface NavigatePayload {
  path: string; params?: RouteParams; query?: Record<string, string>;
  hash?: string; replace?: boolean;
}

const routerActions = {
  navigate: createAction<"@@router/NAVIGATE", NavigatePayload>("@@router/NAVIGATE"),
  navigateBack: createAction<"@@router/BACK">("@@router/BACK"),
  navigateForward: createAction<"@@router/FORWARD">("@@router/FORWARD"),
  setRoutes: createAction<"@@router/SET_ROUTES", RouteDefinition[]>("@@router/SET_ROUTES"),
  navigationStart: createAction<"@@router/NAV_START", string>("@@router/NAV_START"),
  navigationEnd: createAction<"@@router/NAV_END", string>("@@router/NAV_END"),
  navigationError: createAction<"@@router/NAV_ERROR", string>("@@router/NAV_ERROR"),
};

function parsePath(fullPath: string): { path: string; query: Record<string, string>; hash: string } {
  let path = fullPath, hash = "", queryString = "";
  const hi = path.indexOf("#");
  if (hi !== -1) { hash = path.slice(hi + 1); path = path.slice(0, hi); }
  const qi = path.indexOf("?");
  if (qi !== -1) { queryString = path.slice(qi + 1); path = path.slice(0, qi); }
  const query: Record<string, string> = {};
  if (queryString) for (const pair of queryString.split("&")) {
    const [k, v] = pair.split("=");
    if (k) query[decodeURIComponent(k)] = v ? decodeURIComponent(v) : "";
  }
  return { path, query, hash };
}

function buildQueryString(query: Record<string, string>): string {
  const entries = Object.entries(query);
  if (entries.length === 0) return "";
  return "?" + entries.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&");
}

function matchRoute(routePath: string, actualPath: string): { params: RouteParams; matched: boolean } | null {
  const rp = routePath.split("/").filter(Boolean);
  const ap = actualPath.split("/").filter(Boolean);
  if (rp.length !== ap.length && rp[rp.length - 1] !== "*") return null;
  const params: RouteParams = {};
  for (let i = 0; i < rp.length; i++) {
    if (rp[i] === "*") { params["*"] = ap.slice(i).join("/"); return { params, matched: true }; }
    if (rp[i].startsWith(":")) { params[rp[i].slice(1)] = ap[i] || ""; }
    else if (rp[i] !== ap[i]) return null;
  }
  return { params, matched: true };
}

function findMatchingRoute(routes: RouteDefinition[], path: string): { route: RouteDefinition; params: RouteParams } | null {
  for (const route of routes) {
    const m = matchRoute(route.path, path);
    if (m) return { route, params: m.params };
    if (route.children) { const cm = findMatchingRoute(route.children, path); if (cm) return cm; }
  }
  return null;
}

function createRouterInitialState(): RouterState {
  return {
    currentPath: "/", params: {}, query: {}, hash: "",
    history: ["/"], historyIndex: 0, routes: [],
    matchedRoute: null, isNavigating: false, navigationError: null,
  };
}

function createRouterReducer(): Reducer<RouterState> {
  return createReducer(createRouterInitialState(), (builder) => {
    builder
      .addCase(routerActions.navigate, (state, action) => {
        const payload = action.payload;
        const { path, query, hash } = parsePath(payload.path);
        state.currentPath = path;
        state.query = { ...query, ...(payload.query || {}) };
        state.hash = payload.hash || hash || "";
        state.navigationError = null;
        const match = findMatchingRoute(state.routes, path);
        state.params = match ? { ...match.params, ...(payload.params || {}) } : (payload.params || {});
        state.matchedRoute = match ? match.route : null;
        if (payload.replace && state.history.length > 0) {
          state.history[state.historyIndex] = path;
        } else {
          state.history = state.history.slice(0, state.historyIndex + 1);
          state.history.push(path);
          state.historyIndex = state.history.length - 1;
        }
      })
      .addCase(routerActions.navigateBack, (state) => {
        if (state.historyIndex > 0) {
          state.historyIndex -= 1;
          state.currentPath = state.history[state.historyIndex];
          const m = findMatchingRoute(state.routes, state.currentPath);
          if (m) { state.params = m.params; state.matchedRoute = m.route; }
        }
      })
      .addCase(routerActions.navigateForward, (state) => {
        if (state.historyIndex < state.history.length - 1) {
          state.historyIndex += 1;
          state.currentPath = state.history[state.historyIndex];
          const m = findMatchingRoute(state.routes, state.currentPath);
          if (m) { state.params = m.params; state.matchedRoute = m.route; }
        }
      })
      .addCase(routerActions.setRoutes, (state, action) => {
        state.routes = action.payload;
        const m = findMatchingRoute(action.payload, state.currentPath);
        if (m) { state.params = m.params; state.matchedRoute = m.route; }
      })
      .addCase(routerActions.navigationStart, (state) => { state.isNavigating = true; state.navigationError = null; })
      .addCase(routerActions.navigationEnd, (state) => { state.isNavigating = false; })
      .addCase(routerActions.navigationError, (state, action) => { state.isNavigating = false; state.navigationError = action.payload; });
  });
}

// ============================================================================
// Form State Management with Validation
// ============================================================================

type ValidationRule<T = unknown> =
  | { type: "required"; message?: string }
  | { type: "minLength"; value: number; message?: string }
  | { type: "maxLength"; value: number; message?: string }
  | { type: "pattern"; value: RegExp; message?: string }
  | { type: "min"; value: number; message?: string }
  | { type: "max"; value: number; message?: string }
  | { type: "email"; message?: string }
  | { type: "custom"; validate: (value: T, formValues: Record<string, unknown>) => string | null };

interface FieldState<T = unknown> {
  value: T; initialValue: T; error: string | null; errors: string[];
  touched: boolean; dirty: boolean; validating: boolean; valid: boolean;
}

interface FormState<T extends Record<string, unknown>> {
  fields: { [K in keyof T]: FieldState<T[K]> };
  isValid: boolean; isDirty: boolean; isSubmitting: boolean;
  isSubmitted: boolean; submitCount: number; submitError: string | null;
  touchedFields: Set<keyof T>; dirtyFields: Set<keyof T>;
}

interface FieldConfig<T = unknown> {
  initialValue: T;
  rules?: ValidationRule<T>[];
  validateOnChange?: boolean;
  validateOnBlur?: boolean;
  transform?: (value: unknown) => T;
}

interface FormConfig<T extends Record<string, unknown>> {
  fields: { [K in keyof T]: FieldConfig<T[K]> };
  validateOnChange?: boolean;
  validateOnBlur?: boolean;
  onSubmit?: (values: T) => Promise<void> | void;
}

const EMAIL_REGEX = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/;

function validateField<T>(value: T, rules: ValidationRule<T>[], formValues: Record<string, unknown>): string[] {
  const errors: string[] = [];
  for (const rule of rules) {
    switch (rule.type) {
      case "required":
        if (value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0))
          errors.push(rule.message || "This field is required");
        break;
      case "minLength":
        if (String(value || "").length < rule.value) errors.push(rule.message || `Must be at least ${rule.value} characters`);
        break;
      case "maxLength":
        if (String(value || "").length > rule.value) errors.push(rule.message || `Must be no more than ${rule.value} characters`);
        break;
      case "pattern":
        if (!rule.value.test(String(value || ""))) errors.push(rule.message || "Invalid format");
        break;
      case "min": {
        const n = Number(value);
        if (isNaN(n) || n < rule.value) errors.push(rule.message || `Must be at least ${rule.value}`);
        break;
      }
      case "max": {
        const n = Number(value);
        if (isNaN(n) || n > rule.value) errors.push(rule.message || `Must be no more than ${rule.value}`);
        break;
      }
      case "email":
        if (String(value || "") && !EMAIL_REGEX.test(String(value || ""))) errors.push(rule.message || "Invalid email address");
        break;
      case "custom": {
        const err = rule.validate(value, formValues);
        if (err) errors.push(err);
        break;
      }
    }
  }
  return errors;
}

const formActions = {
  setValue: createAction<"@@form/SET_VALUE", { field: string; value: unknown }>("@@form/SET_VALUE"),
  setTouched: createAction<"@@form/SET_TOUCHED", { field: string }>("@@form/SET_TOUCHED"),
  setError: createAction<"@@form/SET_ERROR", { field: string; error: string | null }>("@@form/SET_ERROR"),
  setErrors: createAction<"@@form/SET_ERRORS", { field: string; errors: string[] }>("@@form/SET_ERRORS"),
  validateField: createAction<"@@form/VALIDATE_FIELD", { field: string }>("@@form/VALIDATE_FIELD"),
  validateAll: createAction<"@@form/VALIDATE_ALL">("@@form/VALIDATE_ALL"),
  reset: createAction<"@@form/RESET">("@@form/RESET"),
  resetField: createAction<"@@form/RESET_FIELD", { field: string }>("@@form/RESET_FIELD"),
  submitStart: createAction<"@@form/SUBMIT_START">("@@form/SUBMIT_START"),
  submitSuccess: createAction<"@@form/SUBMIT_SUCCESS">("@@form/SUBMIT_SUCCESS"),
  submitFailure: createAction<"@@form/SUBMIT_FAILURE", { error: string }>("@@form/SUBMIT_FAILURE"),
};

function createFormInitialState<T extends Record<string, unknown>>(config: FormConfig<T>): FormState<T> {
  const fields = {} as { [K in keyof T]: FieldState<T[K]> };
  for (const key of Object.keys(config.fields) as Array<keyof T>) {
    const fc = config.fields[key];
    fields[key] = {
      value: fc.initialValue, initialValue: fc.initialValue,
      error: null, errors: [], touched: false, dirty: false, validating: false, valid: true,
    };
  }
  return {
    fields, isValid: true, isDirty: false, isSubmitting: false,
    isSubmitted: false, submitCount: 0, submitError: null,
    touchedFields: new Set<keyof T>(), dirtyFields: new Set<keyof T>(),
  };
}

function createFormReducer<T extends Record<string, unknown>>(config: FormConfig<T>): Reducer<FormState<T>> {
  const initialState = createFormInitialState(config);

  function getFormValues(state: FormState<T>): T {
    const v = {} as T;
    for (const k of Object.keys(state.fields) as Array<keyof T>) v[k] = state.fields[k].value;
    return v;
  }

  function updateValidity(state: FormState<T>): void {
    state.isValid = (Object.keys(state.fields) as Array<keyof T>).every((k) => state.fields[k].valid);
  }

  return createReducer(initialState, (builder) => {
    builder
      .addCase(formActions.setValue, (state, action) => {
        const { field, value } = action.payload;
        const fk = field as keyof T;
        const fs = state.fields[fk];
        if (!fs) return;
        const fc = config.fields[fk];
        const tv = fc.transform ? fc.transform(value) : value;
        (fs as FieldState<unknown>).value = tv;
        fs.dirty = !Object.is(tv, fs.initialValue);
        state.dirtyFields = new Set(state.dirtyFields);
        if (fs.dirty) state.dirtyFields.add(fk); else state.dirtyFields.delete(fk);
        state.isDirty = state.dirtyFields.size > 0;
        if ((fc.validateOnChange ?? config.validateOnChange ?? false) && fc.rules) {
          const errs = validateField(tv, fc.rules as ValidationRule<unknown>[], getFormValues(state as FormState<T>) as Record<string, unknown>);
          fs.errors = errs; fs.error = errs[0] || null; fs.valid = errs.length === 0;
          updateValidity(state as FormState<T>);
        }
      })
      .addCase(formActions.setTouched, (state, action) => {
        const fk = action.payload.field as keyof T;
        const fs = state.fields[fk];
        if (!fs) return;
        fs.touched = true;
        state.touchedFields = new Set(state.touchedFields); state.touchedFields.add(fk);
        const fc = config.fields[fk];
        if ((fc.validateOnBlur ?? config.validateOnBlur ?? true) && fc.rules) {
          const errs = validateField(fs.value, fc.rules as ValidationRule<unknown>[], getFormValues(state as FormState<T>) as Record<string, unknown>);
          fs.errors = errs; fs.error = errs[0] || null; fs.valid = errs.length === 0;
          updateValidity(state as FormState<T>);
        }
      })
      .addCase(formActions.setError, (state, action) => {
        const fs = state.fields[action.payload.field as keyof T];
        if (!fs) return;
        fs.error = action.payload.error; fs.valid = action.payload.error === null;
        updateValidity(state as FormState<T>);
      })
      .addCase(formActions.validateAll, (state) => {
        const fv = getFormValues(state as FormState<T>);
        for (const k of Object.keys(state.fields) as Array<keyof T>) {
          const fc = config.fields[k];
          if (fc.rules) {
            const errs = validateField(state.fields[k].value, fc.rules as ValidationRule<unknown>[], fv as Record<string, unknown>);
            state.fields[k].errors = errs; state.fields[k].error = errs[0] || null; state.fields[k].valid = errs.length === 0;
          }
        }
        updateValidity(state as FormState<T>);
      })
      .addCase(formActions.reset, (state) => {
        for (const k of Object.keys(state.fields) as Array<keyof T>) {
          const fs = state.fields[k];
          fs.value = fs.initialValue; fs.error = null; fs.errors = [];
          fs.touched = false; fs.dirty = false; fs.validating = false; fs.valid = true;
        }
        state.isValid = true; state.isDirty = false; state.isSubmitting = false;
        state.isSubmitted = false; state.submitCount = 0; state.submitError = null;
        state.touchedFields = new Set<keyof T>(); state.dirtyFields = new Set<keyof T>();
      })
      .addCase(formActions.resetField, (state, action) => {
        const fk = action.payload.field as keyof T;
        const fs = state.fields[fk];
        if (!fs) return;
        fs.value = fs.initialValue; fs.error = null; fs.errors = [];
        fs.touched = false; fs.dirty = false; fs.valid = true;
        state.dirtyFields = new Set(state.dirtyFields); state.dirtyFields.delete(fk);
        state.touchedFields = new Set(state.touchedFields); state.touchedFields.delete(fk);
        state.isDirty = state.dirtyFields.size > 0;
        updateValidity(state as FormState<T>);
      })
      .addCase(formActions.submitStart, (state) => { state.isSubmitting = true; state.submitError = null; })
      .addCase(formActions.submitSuccess, (state) => { state.isSubmitting = false; state.isSubmitted = true; state.submitCount += 1; })
      .addCase(formActions.submitFailure, (state, action) => { state.isSubmitting = false; state.submitError = action.payload.error; state.submitCount += 1; });
  });
}

// ============================================================================
// Main Store Class
// ============================================================================

class Store<S> {
  private state: S;
  private reducer: Reducer<S>;
  private subscriptions: SubscriptionManager<S>;
  private undoManager: ReturnType<typeof createUndoRedoManager<S>> | null;
  private middlewareChain: Dispatch;
  private isDispatching = false;
  private dispatchQueue: Action[] = [];
  private isDestroyed = false;
  private computedCache = new Map<string, { deps: unknown[]; value: unknown }>();

  constructor(options: StoreOptions<S>) {
    const { initialState, reducer, middleware = [], enableUndo = false, maxUndoHistory = 50, batchUpdates = false } = options;
    this.state = initialState;
    this.reducer = reducer;
    this.subscriptions = createSubscriptionManager<S>(batchUpdates);
    this.undoManager = enableUndo ? createUndoRedoManager(initialState, maxUndoHistory) : null;

    const storeAPI: MiddlewareAPI<S> = {
      getState: () => this.state,
      dispatch: (action: Action | ThunkAction) => this.dispatch(action),
    };

    let chain: Dispatch = (action: Action | ThunkAction) => {
      if (typeof action === "function") throw new Error("Thunk actions require thunk middleware");
      return this._baseDispatch(action as Action);
    };

    for (const mw of [...middleware].reverse()) chain = mw(storeAPI)(chain);
    this.middlewareChain = chain;
    this.dispatch({ type: "@@INIT" });
  }

  getState(): S { this.ensureAlive(); return this.state; }

  dispatch(action: Action | ThunkAction): unknown {
    this.ensureAlive();
    if (typeof action === "function") return this.middlewareChain(action);
    if (this.isUndoRedo(action)) return this.handleUndoRedo(action);
    return this.middlewareChain(action);
  }

  private _baseDispatch(action: Action): Action {
    if (this.isDispatching) { this.dispatchQueue.push(action); return action; }
    this.isDispatching = true;
    const prev = this.state;
    try {
      this.state = this.reducer(this.state, action);
      if (this.undoManager && action.type !== "@@INIT") this.undoManager.push(this.state);
    } finally { this.isDispatching = false; }
    if (this.state !== prev) this.subscriptions.notify(this.state, prev);
    while (this.dispatchQueue.length > 0) this.dispatch(this.dispatchQueue.shift()!);
    return action;
  }

  private isUndoRedo(action: Action | ThunkAction): boolean {
    if (typeof action === "function") return false;
    return action.type === UNDO_ACTION || action.type === REDO_ACTION;
  }

  private handleUndoRedo(action: Action): Action {
    if (!this.undoManager) return action;
    const prev = this.state;
    const next = action.type === UNDO_ACTION ? this.undoManager.undo() : this.undoManager.redo();
    if (next !== null) { this.state = next; this.subscriptions.notify(this.state, prev); }
    return action;
  }

  subscribe(listener: Listener<S>): Unsubscribe { this.ensureAlive(); return this.subscriptions.subscribe(listener); }

  subscribeWithSelector<R>(sel: Selector<S, R>, fn: (s: R, p: R) => void, eq?: EqualityFn<R>): Unsubscribe {
    this.ensureAlive();
    return this.subscriptions.subscribeWithSelector(sel, fn, eq);
  }

  select<R>(selector: Selector<S, R>): R { this.ensureAlive(); return selector(this.state); }

  computed<R>(key: string, deps: Selector<S, unknown>[], compute: (...args: unknown[]) => R): R {
    this.ensureAlive();
    const curDeps = deps.map((d) => d(this.state));
    const cached = this.computedCache.get(key);
    if (cached && cached.deps.length === curDeps.length && cached.deps.every((d, i) => Object.is(d, curDeps[i]))) return cached.value as R;
    const value = compute(...curDeps);
    this.computedCache.set(key, { deps: curDeps, value });
    return value;
  }

  undo(): void { this.dispatch({ type: UNDO_ACTION }); }
  redo(): void { this.dispatch({ type: REDO_ACTION }); }
  canUndo(): boolean { return this.undoManager?.canUndo() ?? false; }
  canRedo(): boolean { return this.undoManager?.canRedo() ?? false; }

  serialize(): string { return createStateSnapshot(this.state); }

  hydrate(data: string): void {
    const prev = this.state;
    this.state = restoreStateSnapshot<S>(data);
    this.subscriptions.notify(this.state, prev);
  }

  replaceReducer(next: Reducer<S>): void { this.reducer = next; this.dispatch({ type: "@@REPLACE_REDUCER" }); }
  getListenerCount(): number { return this.subscriptions.getListenerCount(); }

  destroy(): void {
    this.subscriptions.clear(); this.computedCache.clear();
    this.dispatchQueue = []; this.isDestroyed = true;
  }

  private ensureAlive(): void { if (this.isDestroyed) throw new Error("Store has been destroyed"); }
}

// ============================================================================
// Slice & Factory
// ============================================================================

interface SliceConfig<S, N extends string> {
  name: N; initialState: S;
  reducers: Record<string, CaseReducer<S, Action>>;
  extraReducers?: (builder: ReducerBuilder<S>) => void;
}

interface Slice<S, N extends string> {
  name: N; reducer: Reducer<S>;
  actions: Record<string, ActionCreator<string, unknown>>;
  getInitialState: () => S;
}

function createSlice<S, N extends string>(config: SliceConfig<S, N>): Slice<S, N> {
  const actions: Record<string, ActionCreator<string, unknown>> = {};
  const actionTypes: Record<string, CaseReducer<S, Action>> = {};

  for (const [name, fn] of Object.entries(config.reducers)) {
    const type = `${config.name}/${name}`;
    actions[name] = createAction<string, unknown>(type);
    actionTypes[type] = fn;
  }

  const reducer = createReducer(config.initialState, (builder) => {
    for (const [type, fn] of Object.entries(actionTypes)) {
      builder.addMatcher((a) => a.type === type, fn);
    }
    if (config.extraReducers) config.extraReducers(builder);
  });

  return { name: config.name, reducer, actions, getInitialState: () => deepClone(config.initialState) };
}

function createStore<S>(options: StoreOptions<S>): Store<S> { return new Store(options); }

// ============================================================================
// State Machine Pattern
// ============================================================================

interface MachineState { value: string; context: Record<string, unknown>; history: string[] }

interface MachineTransition {
  target: string;
  guard?: (ctx: Record<string, unknown>, event: Action) => boolean;
  actions?: Array<(ctx: Record<string, unknown>, event: Action) => Record<string, unknown>>;
}

interface MachineConfig {
  id: string; initial: string; context: Record<string, unknown>;
  states: Record<string, {
    on?: Record<string, MachineTransition | string>;
    entry?: (ctx: Record<string, unknown>) => Record<string, unknown>;
    exit?: (ctx: Record<string, unknown>) => Record<string, unknown>;
  }>;
}

function createMachineReducer(config: MachineConfig): Reducer<MachineState> {
  const init: MachineState = { value: config.initial, context: { ...config.context }, history: [config.initial] };

  return (state: MachineState = init, action: Action): MachineState => {
    const curCfg = config.states[state.value];
    if (!curCfg?.on) return state;
    const tc = curCfg.on[action.type];
    if (!tc) return state;
    const trans: MachineTransition = typeof tc === "string" ? { target: tc } : tc;
    if (trans.guard && !trans.guard(state.context, action)) return state;

    let ctx = { ...state.context };
    if (curCfg.exit) ctx = { ...ctx, ...curCfg.exit(ctx) };
    if (trans.actions) for (const a of trans.actions) ctx = { ...ctx, ...a(ctx, action) };
    const targetCfg = config.states[trans.target];
    if (targetCfg?.entry) ctx = { ...ctx, ...targetCfg.entry(ctx) };

    return { value: trans.target, context: ctx, history: [...state.history, trans.target] };
  };
}

// ============================================================================
// Patch Generation & Application
// ============================================================================

type PatchOp =
  | { op: "replace"; path: string[]; value: unknown }
  | { op: "add"; path: string[]; value: unknown }
  | { op: "remove"; path: string[] };

function generatePatches(prev: unknown, next: unknown, path: string[] = []): PatchOp[] {
  if (Object.is(prev, next)) return [];
  if (typeof prev !== typeof next || prev === null || next === null || typeof prev !== "object") {
    return [{ op: "replace", path, value: next }];
  }
  const patches: PatchOp[] = [];
  const pObj = prev as Record<string, unknown>, nObj = next as Record<string, unknown>;
  const allKeys = new Set([...Object.keys(pObj), ...Object.keys(nObj)]);
  for (const key of allKeys) {
    const cp = [...path, key];
    if (!(key in pObj)) patches.push({ op: "add", path: cp, value: nObj[key] });
    else if (!(key in nObj)) patches.push({ op: "remove", path: cp });
    else patches.push(...generatePatches(pObj[key], nObj[key], cp));
  }
  return patches;
}

function applyPatches<T>(state: T, patches: PatchOp[]): T {
  const result = deepClone(state);
  for (const patch of patches) {
    const parentPath = patch.path.slice(0, -1);
    const key = patch.path[patch.path.length - 1];
    let target: Record<string, unknown> = result as Record<string, unknown>;
    for (const seg of parentPath) target = target[seg] as Record<string, unknown>;
    if (patch.op === "remove") delete target[key];
    else target[key] = patch.value;
  }
  return result;
}

// ============================================================================
// Effect Manager
// ============================================================================

interface Effect<S> {
  name: string;
  predicate: (action: Action, state: S) => boolean;
  handler: (action: Action, state: S, dispatch: Dispatch) => void | Promise<void>;
  once?: boolean;
}

class EffectManager<S> {
  private effects = new Map<string, Effect<S>>();
  private executedOnce = new Set<string>();

  addEffect(effect: Effect<S>): void { this.effects.set(effect.name, effect); }
  removeEffect(name: string): void { this.effects.delete(name); this.executedOnce.delete(name); }

  createMiddleware(): Middleware<S> {
    const self = this;
    const mw: Middleware<S> = (store) => (next) => (action) => {
      const result = next(action);
      if (typeof action !== "function") {
        const typed = action as Action;
        const state = store.getState() as S;
        for (const [name, effect] of self.effects) {
          if (effect.once && self.executedOnce.has(name)) continue;
          if (effect.predicate(typed, state)) {
            if (effect.once) self.executedOnce.add(name);
            try {
              const r = effect.handler(typed, state, store.dispatch);
              if (r instanceof Promise) r.catch((e) => console.error(`[Effect] "${name}":`, e));
            } catch (e) { console.error(`[Effect] "${name}":`, e); }
          }
        }
      }
      return result;
    };
    mw.name = "effects";
    return mw;
  }

  clear(): void { this.effects.clear(); this.executedOnce.clear(); }
  getEffectNames(): string[] { return Array.from(this.effects.keys()); }
}

// ============================================================================
// Batch Dispatch
// ============================================================================

function batchActions(actions: Action[]): Action { return { type: "@@BATCH", payload: actions }; }

function createBatchMiddleware<S>(): Middleware<S> {
  const mw: Middleware<S> = (_store) => (next) => (action) => {
    if (typeof action !== "function" && (action as Action).type === "@@BATCH") {
      let last: unknown;
      for (const a of (action as Action).payload as Action[]) last = next(a);
      return last;
    }
    return next(action);
  };
  mw.name = "batch";
  return mw;
}

// ============================================================================
// Computed State Manager
// ============================================================================

class ComputedStateManager<S> {
  private fields = new Map<string, {
    deps: Selector<S, unknown>[]; compute: (...args: unknown[]) => unknown;
    lastArgs: unknown[] | null; lastResult: unknown; recomputations: number;
  }>();

  register<R>(key: string, deps: Selector<S, unknown>[], compute: (...args: unknown[]) => R): void {
    this.fields.set(key, { deps, compute, lastArgs: null, lastResult: undefined, recomputations: 0 });
  }

  get<R>(key: string, state: S): R {
    const f = this.fields.get(key);
    if (!f) throw new Error(`Computed field "${key}" not registered`);
    const args = f.deps.map((d) => d(state));
    if (f.lastArgs && args.length === f.lastArgs.length && args.every((a, i) => Object.is(a, f.lastArgs![i]))) return f.lastResult as R;
    f.lastArgs = args; f.recomputations++; f.lastResult = f.compute(...args);
    return f.lastResult as R;
  }

  invalidate(key: string): void { const f = this.fields.get(key); if (f) { f.lastArgs = null; f.lastResult = undefined; } }
  invalidateAll(): void { for (const f of this.fields.values()) { f.lastArgs = null; f.lastResult = undefined; } }
  getRecomputations(key: string): number { return this.fields.get(key)?.recomputations ?? 0; }
}

// ============================================================================
// Query Cache
// ============================================================================

interface QueryCacheEntry<T> {
  data: T; fetchedAt: number; expiresAt: number;
  status: "fresh" | "stale" | "expired"; error: string | null; refetchCount: number;
}

class QueryCache<T = unknown> {
  private cache = new Map<string, QueryCacheEntry<T>>();
  private defaultTTL: number;
  private maxEntries: number;
  private staleTime: number;
  private accessOrder: string[] = [];

  constructor(config: { defaultTTL?: number; maxEntries?: number; staleTime?: number } = {}) {
    this.defaultTTL = config.defaultTTL ?? 300_000;
    this.maxEntries = config.maxEntries ?? 100;
    this.staleTime = config.staleTime ?? 60_000;
  }

  set(key: string, data: T, ttl?: number): void {
    const now = Date.now();
    this.cache.set(key, {
      data, fetchedAt: now, expiresAt: now + (ttl ?? this.defaultTTL),
      status: "fresh", error: null, refetchCount: (this.cache.get(key)?.refetchCount ?? 0) + 1,
    });
    this.accessOrder = this.accessOrder.filter((k) => k !== key);
    this.accessOrder.push(key);
    while (this.cache.size > this.maxEntries && this.accessOrder.length > 0) {
      this.cache.delete(this.accessOrder.shift()!);
    }
  }

  get(key: string): QueryCacheEntry<T> | null {
    const entry = this.cache.get(key);
    if (!entry) return null;
    const now = Date.now();
    if (now > entry.expiresAt) entry.status = "expired";
    else if (now > entry.fetchedAt + this.staleTime) entry.status = "stale";
    else entry.status = "fresh";
    return entry;
  }

  invalidate(key: string): void {
    const e = this.cache.get(key);
    if (e) { e.status = "expired"; e.expiresAt = 0; }
  }

  invalidateByPrefix(prefix: string): void {
    for (const key of this.cache.keys()) if (key.startsWith(prefix)) this.invalidate(key);
  }

  remove(key: string): void { this.cache.delete(key); this.accessOrder = this.accessOrder.filter((k) => k !== key); }
  clear(): void { this.cache.clear(); this.accessOrder = []; }
  has(key: string): boolean { const e = this.cache.get(key); return e ? Date.now() <= e.expiresAt : false; }
  size(): number { return this.cache.size; }
  keys(): string[] { return Array.from(this.cache.keys()); }
}

// ============================================================================
// Subscription Helpers
// ============================================================================

function when<S>(store: Store<S>, predicate: (s: S) => boolean, callback: (s: S) => void): Unsubscribe {
  if (predicate(store.getState())) { callback(store.getState()); return () => {}; }
  const unsub = store.subscribe((state) => { if (predicate(state)) { unsub(); callback(state); } });
  return unsub;
}

function watchEffect<S>(store: Store<S>, effect: (s: S) => (() => void) | void): Unsubscribe {
  let cleanup: (() => void) | void;
  const run = (s: S) => { if (cleanup) cleanup(); cleanup = effect(s); };
  run(store.getState());
  const unsub = store.subscribe((s) => run(s));
  return () => { unsub(); if (cleanup) cleanup(); };
}

function debounceSubscription<S>(store: Store<S>, listener: Listener<S>, delayMs: number): Unsubscribe {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let ls: S | null = null, lp: S | null = null;
  const unsub = store.subscribe((s, p) => {
    ls = s; lp = p;
    if (timer !== null) clearTimeout(timer);
    timer = setTimeout(() => { if (ls !== null && lp !== null) listener(ls, lp); timer = null; }, delayMs);
  });
  return () => { unsub(); if (timer !== null) clearTimeout(timer); };
}

function throttleSubscription<S>(store: Store<S>, listener: Listener<S>, intervalMs: number): Unsubscribe {
  let lastCall = 0, pending: { s: S; p: S } | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const unsub = store.subscribe((s, p) => {
    const now = Date.now();
    if (now - lastCall >= intervalMs) { lastCall = now; listener(s, p); }
    else {
      pending = { s, p };
      if (timer === null) {
        timer = setTimeout(() => {
          if (pending) { lastCall = Date.now(); listener(pending.s, pending.p); pending = null; }
          timer = null;
        }, intervalMs - (now - lastCall));
      }
    }
  });
  return () => { unsub(); if (timer !== null) clearTimeout(timer); };
}

// ============================================================================
// Aggregate Store
// ============================================================================

function createAggregateStore(config: {
  slices: Slice<unknown, string>[]; middleware?: Middleware[];
  devtools?: boolean; enableUndo?: boolean;
}): Store<Record<string, unknown>> {
  const { slices, middleware = [], devtools = false, enableUndo = false } = config;
  const reducers: Record<string, Reducer<unknown>> = {};
  const initialState: Record<string, unknown> = {};
  for (const slice of slices) { reducers[slice.name] = slice.reducer; initialState[slice.name] = slice.getInitialState(); }
  const root = combineReducers(reducers as ReducersMapObject<Record<string, unknown>>);
  const allMw: Middleware[] = [...middleware];
  if (devtools) allMw.push(createDevToolsMiddleware());
  return createStore({ initialState, reducer: root, middleware: allMw, enableUndo });
}

// ============================================================================
// Type Guards
// ============================================================================

function isAction(value: unknown): value is Action {
  return typeof value === "object" && value !== null && "type" in value && typeof (value as Action).type === "string";
}

function isPendingAction(action: Action): boolean { return action.type.endsWith("/pending"); }
function isFulfilledAction(action: Action): boolean { return action.type.endsWith("/fulfilled"); }
function isRejectedAction(action: Action): boolean { return action.type.endsWith("/rejected"); }

function isAnyOf(...creators: Array<{ type: string }>): (action: Action) => boolean {
  const types = new Set(creators.map((c) => c.type));
  return (action: Action) => types.has(action.type);
}

function isAllOf(...predicates: Array<(a: Action) => boolean>): (a: Action) => boolean {
  return (a: Action) => predicates.every((p) => p(a));
}

// ============================================================================
// Time Travel Debugger
// ============================================================================

class TimeTravelDebugger<S> {
  private snapshots: Array<{ action: Action; state: S; timestamp: number }> = [];
  private currentIndex = -1;
  private isReplaying = false;
  private store: Store<S> | null = null;
  private unsub: Unsubscribe | null = null;
  private maxSnapshots: number;

  constructor(maxSnapshots = 100) { this.maxSnapshots = maxSnapshots; }

  attach(store: Store<S>): void {
    this.store = store;
    this.snapshots.push({ action: { type: "@@INIT" }, state: deepClone(store.getState()), timestamp: Date.now() });
    this.currentIndex = 0;
    this.unsub = store.subscribe((newState) => {
      if (this.isReplaying) return;
      if (this.currentIndex < this.snapshots.length - 1) this.snapshots = this.snapshots.slice(0, this.currentIndex + 1);
      this.snapshots.push({ action: { type: "@@STATE_CHANGE" }, state: deepClone(newState), timestamp: Date.now() });
      if (this.snapshots.length > this.maxSnapshots) this.snapshots.shift();
      this.currentIndex = this.snapshots.length - 1;
    });
  }

  jumpTo(index: number): S | null {
    if (!this.store || index < 0 || index >= this.snapshots.length) return null;
    this.isReplaying = true; this.currentIndex = index;
    this.store.hydrate(createStateSnapshot(this.snapshots[index].state));
    this.isReplaying = false;
    return this.snapshots[index].state;
  }

  stepBack(): S | null { return this.currentIndex > 0 ? this.jumpTo(this.currentIndex - 1) : null; }
  stepForward(): S | null { return this.currentIndex < this.snapshots.length - 1 ? this.jumpTo(this.currentIndex + 1) : null; }
  getSnapshots() { return [...this.snapshots]; }
  getCurrentIndex() { return this.currentIndex; }

  detach(): void {
    if (this.unsub) { this.unsub(); this.unsub = null; }
    this.store = null; this.snapshots = []; this.currentIndex = -1;
  }
}

// ============================================================================
// Plugin System
// ============================================================================

interface Plugin<S> {
  name: string; version?: string;
  install(store: Store<S>, options?: Record<string, unknown>): void;
  uninstall?(store: Store<S>): void;
}

class PluginManager<S> {
  private plugins = new Map<string, Plugin<S>>();
  private installed = new Map<string, { plugin: Plugin<S>; options?: Record<string, unknown> }>();

  register(plugin: Plugin<S>): void { this.plugins.set(plugin.name, plugin); }

  install(store: Store<S>, pluginName: string, options?: Record<string, unknown>): void {
    const plugin = this.plugins.get(pluginName);
    if (!plugin) throw new Error(`Plugin "${pluginName}" not found`);
    if (this.installed.has(pluginName)) return;
    plugin.install(store, options);
    this.installed.set(pluginName, { plugin, options });
  }

  uninstall(store: Store<S>, pluginName: string): void {
    const inst = this.installed.get(pluginName);
    if (!inst) return;
    if (inst.plugin.uninstall) inst.plugin.uninstall(store);
    this.installed.delete(pluginName);
  }

  isInstalled(name: string): boolean { return this.installed.has(name); }
  getInstalledPlugins(): string[] { return Array.from(this.installed.keys()); }
}

// ============================================================================
// Observable Store (Reactive Streams Pattern)
// ============================================================================

interface Observable<T> {
  subscribe(observer: Observer<T>): Subscription;
  pipe<R>(...operators: Array<OperatorFn<unknown, unknown>>): Observable<R>;
}

interface Observer<T> {
  next: (value: T) => void;
  error?: (err: unknown) => void;
  complete?: () => void;
}

interface Subscription {
  unsubscribe(): void;
  readonly closed: boolean;
}

type OperatorFn<T, R> = (source: Observable<T>) => Observable<R>;

function createObservableStore<S>(store: Store<S>): Observable<S> & { getValue: () => S } {
  const observable: Observable<S> & { getValue: () => S } = {
    getValue: () => store.getState(),

    subscribe(observer: Observer<S>): Subscription {
      let closed = false;

      // Emit current value immediately
      try {
        observer.next(store.getState());
      } catch (err) {
        if (observer.error) observer.error(err);
      }

      const unsub = store.subscribe((state) => {
        if (closed) return;
        try {
          observer.next(state);
        } catch (err) {
          if (observer.error) observer.error(err);
        }
      });

      return {
        unsubscribe(): void {
          if (closed) return;
          closed = true;
          unsub();
          if (observer.complete) observer.complete();
        },
        get closed() { return closed; },
      };
    },

    pipe<R>(...operators: Array<OperatorFn<unknown, unknown>>): Observable<R> {
      let result: Observable<unknown> = observable;
      for (const op of operators) {
        result = op(result);
      }
      return result as Observable<R>;
    },
  };

  return observable;
}

// Observable operators
function mapOperator<T, R>(project: (value: T) => R): OperatorFn<T, R> {
  return (source: Observable<T>): Observable<R> => ({
    subscribe(observer: Observer<R>): Subscription {
      return source.subscribe({
        next: (value: T) => {
          try {
            observer.next(project(value));
          } catch (err) {
            if (observer.error) observer.error(err);
          }
        },
        error: observer.error,
        complete: observer.complete,
      });
    },
    pipe<R2>(...ops: Array<OperatorFn<unknown, unknown>>): Observable<R2> {
      let result: Observable<unknown> = this;
      for (const op of ops) result = op(result);
      return result as Observable<R2>;
    },
  });
}

function filterOperator<T>(predicate: (value: T) => boolean): OperatorFn<T, T> {
  return (source: Observable<T>): Observable<T> => ({
    subscribe(observer: Observer<T>): Subscription {
      return source.subscribe({
        next: (value: T) => {
          if (predicate(value)) observer.next(value);
        },
        error: observer.error,
        complete: observer.complete,
      });
    },
    pipe<R>(...ops: Array<OperatorFn<unknown, unknown>>): Observable<R> {
      let result: Observable<unknown> = this;
      for (const op of ops) result = op(result);
      return result as Observable<R>;
    },
  });
}

function distinctUntilChangedOperator<T>(comparator: EqualityFn<T> = Object.is): OperatorFn<T, T> {
  return (source: Observable<T>): Observable<T> => ({
    subscribe(observer: Observer<T>): Subscription {
      let lastValue: T | undefined;
      let hasValue = false;
      return source.subscribe({
        next: (value: T) => {
          if (!hasValue || !comparator(value, lastValue!)) {
            hasValue = true;
            lastValue = value;
            observer.next(value);
          }
        },
        error: observer.error,
        complete: observer.complete,
      });
    },
    pipe<R>(...ops: Array<OperatorFn<unknown, unknown>>): Observable<R> {
      let result: Observable<unknown> = this;
      for (const op of ops) result = op(result);
      return result as Observable<R>;
    },
  });
}

function scanOperator<T, R>(accumulator: (acc: R, value: T) => R, seed: R): OperatorFn<T, R> {
  return (source: Observable<T>): Observable<R> => ({
    subscribe(observer: Observer<R>): Subscription {
      let acc = seed;
      return source.subscribe({
        next: (value: T) => {
          acc = accumulator(acc, value);
          observer.next(acc);
        },
        error: observer.error,
        complete: observer.complete,
      });
    },
    pipe<R2>(...ops: Array<OperatorFn<unknown, unknown>>): Observable<R2> {
      let result: Observable<unknown> = this;
      for (const op of ops) result = op(result);
      return result as Observable<R2>;
    },
  });
}

// ============================================================================
// Enhanced Selector Composition
// ============================================================================

function createStructuredSelector<S, T extends Record<string, Selector<S, unknown>>>(
  selectors: T
): Selector<S, { [K in keyof T]: ReturnType<T[K]> }> {
  const keys = Object.keys(selectors) as Array<keyof T>;
  let lastArgs: Record<keyof T, unknown> | null = null;
  let lastResult: { [K in keyof T]: ReturnType<T[K]> } | null = null;

  return (state: S) => {
    const results = {} as Record<keyof T, unknown>;
    let changed = lastArgs === null;

    for (const key of keys) {
      results[key] = selectors[key](state);
      if (!changed && !Object.is(results[key], lastArgs![key])) {
        changed = true;
      }
    }

    if (!changed) return lastResult!;
    lastArgs = results;
    lastResult = results as { [K in keyof T]: ReturnType<T[K]> };
    return lastResult;
  };
}

// Parameterized selector factory
function createParametricSelector<S, P, R>(
  factory: (param: P) => Selector<S, R>,
  cacheSize: number = 10
): (param: P) => Selector<S, R> {
  const cache = new Map<string, { selector: Selector<S, R>; lastAccess: number }>();

  return (param: P): Selector<S, R> => {
    const key = JSON.stringify(param);
    const cached = cache.get(key);

    if (cached) {
      cached.lastAccess = Date.now();
      return cached.selector;
    }

    const selector = factory(param);
    cache.set(key, { selector, lastAccess: Date.now() });

    // Evict oldest entries if cache is full
    if (cache.size > cacheSize) {
      let oldestKey = "";
      let oldestTime = Infinity;
      for (const [k, v] of cache) {
        if (v.lastAccess < oldestTime) {
          oldestTime = v.lastAccess;
          oldestKey = k;
        }
      }
      if (oldestKey) cache.delete(oldestKey);
    }

    return selector;
  };
}

// ============================================================================
// Middleware Composition Helpers
// ============================================================================

function composeMiddleware<S>(...middlewares: Middleware<S>[]): Middleware<S> {
  const composed: Middleware<S> = (store) => {
    const chain = middlewares.map((mw) => mw(store));
    return (next) => {
      let dispatch = next;
      for (let i = chain.length - 1; i >= 0; i--) {
        dispatch = chain[i](dispatch);
      }
      return dispatch;
    };
  };
  composed.name = "composed";
  return composed;
}

// Conditional middleware: only applies if predicate returns true
function conditionalMiddleware<S>(
  predicate: (action: Action) => boolean,
  middleware: Middleware<S>
): Middleware<S> {
  const conditional: Middleware<S> = (store) => {
    const applied = middleware(store);
    return (next) => {
      const middlewareDispatch = applied(next);
      return (action) => {
        if (typeof action !== "function" && predicate(action as Action)) {
          return middlewareDispatch(action);
        }
        return next(action);
      };
    };
  };
  conditional.name = `conditional(${middleware.name})`;
  return conditional;
}

// ============================================================================
// Action Validation Middleware
// ============================================================================

interface ActionValidator<S> {
  actionType: string;
  validate: (payload: unknown, state: S) => string | null;
}

function createValidationMiddleware<S>(validators: ActionValidator<S>[]): Middleware<S> {
  const validatorMap = new Map<string, ActionValidator<S>>();
  for (const v of validators) validatorMap.set(v.actionType, v);

  const mw: Middleware<S> = (store) => (next) => (action) => {
    if (typeof action === "function") return next(action);
    const typed = action as Action;
    const validator = validatorMap.get(typed.type);
    if (validator) {
      const error = validator.validate(typed.payload, store.getState() as S);
      if (error) {
        console.warn(`[Validation] Action ${typed.type} rejected: ${error}`);
        return { ...typed, error: true, meta: { ...typed.meta, validationError: error } };
      }
    }
    return next(action);
  };
  mw.name = "validation";
  return mw;
}

// ============================================================================
// State Snapshotter (periodic automatic snapshots)
// ============================================================================

class StateSnapshotter<S> {
  private snapshots: Array<{ state: S; timestamp: number; label?: string }> = [];
  private maxSnapshots: number;
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private unsub: Unsubscribe | null = null;

  constructor(maxSnapshots: number = 50) {
    this.maxSnapshots = maxSnapshots;
  }

  takeSnapshot(store: Store<S>, label?: string): void {
    this.snapshots.push({
      state: deepClone(store.getState()),
      timestamp: Date.now(),
      label,
    });
    if (this.snapshots.length > this.maxSnapshots) {
      this.snapshots.shift();
    }
  }

  startAutoSnapshot(store: Store<S>, intervalMs: number): void {
    this.stopAutoSnapshot();
    this.intervalId = setInterval(() => {
      this.takeSnapshot(store, "auto");
    }, intervalMs);
  }

  stopAutoSnapshot(): void {
    if (this.intervalId !== null) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }

  snapshotOnAction(store: Store<S>, actionTypes: string[]): void {
    const types = new Set(actionTypes);
    this.unsub = store.subscribe((state, _prev) => {
      // We can't directly access the action here, so snapshot on every change
      // In practice this would be integrated with middleware
      this.snapshots.push({ state: deepClone(state), timestamp: Date.now() });
      if (this.snapshots.length > this.maxSnapshots) this.snapshots.shift();
    });
  }

  getSnapshots(): Array<{ state: S; timestamp: number; label?: string }> {
    return [...this.snapshots];
  }

  getSnapshotAt(index: number): S | null {
    if (index < 0 || index >= this.snapshots.length) return null;
    return deepClone(this.snapshots[index].state);
  }

  findSnapshotByLabel(label: string): S | null {
    const snap = this.snapshots.find((s) => s.label === label);
    return snap ? deepClone(snap.state) : null;
  }

  clear(): void {
    this.snapshots = [];
    this.stopAutoSnapshot();
    if (this.unsub) { this.unsub(); this.unsub = null; }
  }
}

// ============================================================================
// Exports
// ============================================================================

export {
  // Types
  Action, ActionCreator, Reducer, Dispatch, ThunkAction, Middleware, MiddlewareAPI,
  StoreOptions, StorageAdapter, Listener, Unsubscribe, Selector, EqualityFn,
  DeepPartial, DeepReadonly, Draft, CaseReducer, ReducerBuilder,

  // Store
  Store, createStore,

  // Actions & Reducers
  createAction, createReducer, combineReducers, createSlice,
  Slice, SliceConfig,

  // Selectors
  createSelector, MemoizedSelector,

  // Produce
  produce,

  // Entity Adapter
  createEntityAdapter, EntityAdapter, EntityState, EntitySelectors,

  // Async
  createAsyncThunk, createAsyncState, AsyncState, AsyncThunk,

  // Middleware
  createLoggerMiddleware, createThunkMiddleware, createDevToolsMiddleware,
  createPersistenceMiddleware, createBatchMiddleware, loadPersistedState,
  DevToolsMonitor, InMemoryStorage,

  // Router
  RouterState, RouteDefinition, routerActions, createRouterReducer,
  createRouterInitialState, matchRoute, parsePath, buildQueryString,

  // Forms
  FormState, FieldState, FormConfig, FieldConfig, ValidationRule,
  formActions, createFormReducer, createFormInitialState,

  // Undo/Redo
  createUndoRedoManager, UNDO_ACTION, REDO_ACTION,

  // Serialization
  createSerializer, createDeserializer, createStateSnapshot, restoreStateSnapshot,

  // Computed
  ComputedStateManager,

  // Effects
  EffectManager, Effect,

  // Batch
  batchActions,

  // State Machine
  createMachineReducer, MachineState, MachineConfig,

  // Plugins
  PluginManager, Plugin,

  // Patches
  generatePatches, applyPatches, PatchOp,

  // Aggregate
  createAggregateStore,

  // Subscriptions
  when, watchEffect, debounceSubscription, throttleSubscription,

  // Query Cache
  QueryCache, QueryCacheEntry,

  // Time Travel
  TimeTravelDebugger,

  // Utilities
  shallowEqual, deepEqual, deepClone, deepFreeze, deepMerge,

  // Type Guards
  isAction, isPendingAction, isFulfilledAction, isRejectedAction, isAnyOf, isAllOf,

  // Observable
  Observable, Observer, Subscription as ObservableSubscription,
  createObservableStore, mapOperator, filterOperator,
  distinctUntilChangedOperator, scanOperator,

  // Structured Selectors
  createStructuredSelector, createParametricSelector,

  // Middleware Helpers
  composeMiddleware, conditionalMiddleware, createValidationMiddleware,
  ActionValidator,

  // Snapshotter
  StateSnapshotter,
};
