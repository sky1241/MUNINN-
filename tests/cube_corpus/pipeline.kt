package io.pipeline.core

import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference
import java.util.concurrent.locks.ReentrantReadWriteLock
import java.util.UUID
import java.util.LinkedList
import java.util.TreeMap
import kotlin.math.min
import kotlin.math.max
import kotlin.math.sqrt

// ============================================================================
// Section 1: Core Types and Result Handling
// ============================================================================

sealed class Result<out T> {
    data class Ok<T>(val value: T) : Result<T>()
    data class Err<T>(val error: PipelineError) : Result<T>()

    fun <R> map(transform: (T) -> R): Result<R> = when (this) {
        is Ok -> Ok(transform(value))
        is Err -> Err(error)
    }

    fun <R> flatMap(transform: (T) -> Result<R>): Result<R> = when (this) {
        is Ok -> transform(value)
        is Err -> Err(error)
    }

    fun getOrElse(default: @UnsafeVariance T): T = when (this) {
        is Ok -> value
        is Err -> default
    }

    fun getOrThrow(): T = when (this) {
        is Ok -> value
        is Err -> throw PipelineException(error)
    }

    val isOk: Boolean get() = this is Ok
    val isErr: Boolean get() = this is Err
}

sealed class PipelineError(val message: String, val cause: Throwable? = null) {
    class SerializationError(msg: String, cause: Throwable? = null) : PipelineError(msg, cause)
    class SchemaError(msg: String) : PipelineError(msg)
    class StageError(val stageName: String, msg: String, cause: Throwable? = null) : PipelineError(msg, cause)
    class BackpressureError(msg: String) : PipelineError(msg)
    class CircuitBreakerOpen(val breakerName: String) : PipelineError("Circuit breaker '$breakerName' is open")
    class RetryExhausted(val attempts: Int, val lastError: PipelineError) : PipelineError("Retry exhausted after $attempts attempts: ${lastError.message}")
    class TimeoutError(val durationMs: Long) : PipelineError("Timeout after ${durationMs}ms")
    class StateError(msg: String) : PipelineError(msg)
    class QueryError(msg: String) : PipelineError(msg)
}

class PipelineException(val error: PipelineError) : RuntimeException(error.message, error.cause)

// ============================================================================
// Section 2: Record and Schema Types
// ============================================================================

data class Record<K, V>(
    val key: K?,
    val value: V,
    val timestamp: Long = System.currentTimeMillis(),
    val headers: Map<String, String> = emptyMap(),
    val partition: Int = 0,
    val offset: Long = -1L
) {
    fun <R> mapValue(transform: (V) -> R): Record<K, R> =
        Record(key, transform(value), timestamp, headers, partition, offset)

    fun withHeader(name: String, value: String): Record<K, V> =
        copy(headers = headers + (name to value))

    fun withTimestamp(ts: Long): Record<K, V> = copy(timestamp = ts)
}

sealed class FieldType {
    object StringType : FieldType()
    object IntType : FieldType()
    object LongType : FieldType()
    object DoubleType : FieldType()
    object BooleanType : FieldType()
    object BytesType : FieldType()
    data class ArrayType(val elementType: FieldType) : FieldType()
    data class MapType(val keyType: FieldType, val valueType: FieldType) : FieldType()
    data class RecordType(val schema: Schema) : FieldType()
    data class NullableType(val inner: FieldType) : FieldType()

    override fun toString(): String = when (this) {
        is StringType -> "string"
        is IntType -> "int"
        is LongType -> "long"
        is DoubleType -> "double"
        is BooleanType -> "boolean"
        is BytesType -> "bytes"
        is ArrayType -> "array<${elementType}>"
        is MapType -> "map<${keyType}, ${valueType}>"
        is RecordType -> "record(${schema.name})"
        is NullableType -> "${inner}?"
    }
}

data class Field(
    val name: String,
    val type: FieldType,
    val defaultValue: Any? = null,
    val doc: String = "",
    val aliases: List<String> = emptyList()
)

data class Schema(
    val name: String,
    val version: Int = 1,
    val fields: List<Field>,
    val doc: String = ""
) {
    private val fieldIndex: Map<String, Field> by lazy {
        fields.associateBy { it.name }
    }

    fun getField(name: String): Field? = fieldIndex[name]
    fun hasField(name: String): Boolean = name in fieldIndex

    fun fieldNames(): List<String> = fields.map { it.name }
}

// ============================================================================
// Section 3: Schema Evolution
// ============================================================================

sealed class SchemaEvolution {
    data class AddField(val field: Field) : SchemaEvolution()
    data class RemoveField(val fieldName: String) : SchemaEvolution()
    data class RenameField(val oldName: String, val newName: String) : SchemaEvolution()
    data class ChangeType(val fieldName: String, val newType: FieldType) : SchemaEvolution()
    data class SetDefault(val fieldName: String, val defaultValue: Any?) : SchemaEvolution()
    data class MakeNullable(val fieldName: String) : SchemaEvolution()
    data class AddAlias(val fieldName: String, val alias: String) : SchemaEvolution()
}

class SchemaRegistry {
    private val schemas = ConcurrentHashMap<String, TreeMap<Int, Schema>>()
    private val compatibilityRules = ConcurrentHashMap<String, CompatibilityMode>()

    enum class CompatibilityMode {
        NONE, BACKWARD, FORWARD, FULL
    }

    fun register(schema: Schema): Result<Schema> {
        val versions = schemas.getOrPut(schema.name) { TreeMap() }
        val latestVersion = versions.lastEntry()?.value

        if (latestVersion != null) {
            val mode = compatibilityRules[schema.name] ?: CompatibilityMode.BACKWARD
            val compatible = checkCompatibility(latestVersion, schema, mode)
            if (!compatible.isOk) return compatible as Result<Schema>
        }

        val versionedSchema = schema.copy(version = (latestVersion?.version ?: 0) + 1)
        versions[versionedSchema.version] = versionedSchema
        return Result.Ok(versionedSchema)
    }

    fun getSchema(name: String, version: Int? = null): Result<Schema> {
        val versions = schemas[name]
            ?: return Result.Err(PipelineError.SchemaError("Schema '$name' not found"))
        val schema = if (version != null) {
            versions[version]
        } else {
            versions.lastEntry()?.value
        }
        return schema?.let { Result.Ok(it) }
            ?: Result.Err(PipelineError.SchemaError("Schema '$name' version ${version ?: "latest"} not found"))
    }

    fun evolve(schemaName: String, evolution: SchemaEvolution): Result<Schema> {
        val current = getSchema(schemaName).getOrElse(null)
            ?: return Result.Err(PipelineError.SchemaError("Schema '$schemaName' not found"))

        val evolved = when (evolution) {
            is SchemaEvolution.AddField -> {
                if (current.hasField(evolution.field.name)) {
                    return Result.Err(PipelineError.SchemaError("Field '${evolution.field.name}' already exists"))
                }
                current.copy(fields = current.fields + evolution.field)
            }
            is SchemaEvolution.RemoveField -> {
                if (!current.hasField(evolution.fieldName)) {
                    return Result.Err(PipelineError.SchemaError("Field '${evolution.fieldName}' not found"))
                }
                current.copy(fields = current.fields.filter { it.name != evolution.fieldName })
            }
            is SchemaEvolution.RenameField -> {
                val field = current.getField(evolution.oldName)
                    ?: return Result.Err(PipelineError.SchemaError("Field '${evolution.oldName}' not found"))
                val renamed = field.copy(
                    name = evolution.newName,
                    aliases = field.aliases + evolution.oldName
                )
                current.copy(
                    fields = current.fields.map { if (it.name == evolution.oldName) renamed else it }
                )
            }
            is SchemaEvolution.ChangeType -> {
                val field = current.getField(evolution.fieldName)
                    ?: return Result.Err(PipelineError.SchemaError("Field '${evolution.fieldName}' not found"))
                current.copy(
                    fields = current.fields.map {
                        if (it.name == evolution.fieldName) it.copy(type = evolution.newType) else it
                    }
                )
            }
            is SchemaEvolution.SetDefault -> {
                val field = current.getField(evolution.fieldName)
                    ?: return Result.Err(PipelineError.SchemaError("Field '${evolution.fieldName}' not found"))
                current.copy(
                    fields = current.fields.map {
                        if (it.name == evolution.fieldName) it.copy(defaultValue = evolution.defaultValue) else it
                    }
                )
            }
            is SchemaEvolution.MakeNullable -> {
                val field = current.getField(evolution.fieldName)
                    ?: return Result.Err(PipelineError.SchemaError("Field '${evolution.fieldName}' not found"))
                current.copy(
                    fields = current.fields.map {
                        if (it.name == evolution.fieldName) it.copy(type = FieldType.NullableType(it.type)) else it
                    }
                )
            }
            is SchemaEvolution.AddAlias -> {
                val field = current.getField(evolution.fieldName)
                    ?: return Result.Err(PipelineError.SchemaError("Field '${evolution.fieldName}' not found"))
                current.copy(
                    fields = current.fields.map {
                        if (it.name == evolution.fieldName) it.copy(aliases = it.aliases + evolution.alias) else it
                    }
                )
            }
        }

        return register(evolved)
    }

    fun setCompatibility(schemaName: String, mode: CompatibilityMode) {
        compatibilityRules[schemaName] = mode
    }

    fun listSchemas(): List<String> = schemas.keys().toList()

    fun versions(schemaName: String): List<Int> =
        schemas[schemaName]?.keys?.toList() ?: emptyList()

    private fun checkCompatibility(
        existing: Schema,
        proposed: Schema,
        mode: CompatibilityMode
    ): Result<Unit> {
        return when (mode) {
            CompatibilityMode.NONE -> Result.Ok(Unit)
            CompatibilityMode.BACKWARD -> checkBackwardCompat(existing, proposed)
            CompatibilityMode.FORWARD -> checkForwardCompat(existing, proposed)
            CompatibilityMode.FULL -> {
                val backward = checkBackwardCompat(existing, proposed)
                if (backward.isErr) return backward
                checkForwardCompat(existing, proposed)
            }
        }
    }

    private fun checkBackwardCompat(existing: Schema, proposed: Schema): Result<Unit> {
        for (field in existing.fields) {
            val proposedField = proposed.getField(field.name)
            if (proposedField == null) {
                if (field.defaultValue == null && field.type !is FieldType.NullableType) {
                    return Result.Err(PipelineError.SchemaError(
                        "Backward incompatible: removed required field '${field.name}' without default"
                    ))
                }
            }
        }
        return Result.Ok(Unit)
    }

    private fun checkForwardCompat(existing: Schema, proposed: Schema): Result<Unit> {
        for (field in proposed.fields) {
            if (!existing.hasField(field.name)) {
                if (field.defaultValue == null && field.type !is FieldType.NullableType) {
                    return Result.Err(PipelineError.SchemaError(
                        "Forward incompatible: added required field '${field.name}' without default"
                    ))
                }
            }
        }
        return Result.Ok(Unit)
    }
}

// ============================================================================
// Section 4: Serialization / Deserialization Codecs
// ============================================================================

interface Codec<T> {
    fun serialize(value: T): Result<ByteArray>
    fun deserialize(bytes: ByteArray): Result<T>
}

class StringCodec : Codec<String> {
    override fun serialize(value: String): Result<ByteArray> =
        Result.Ok(value.toByteArray(Charsets.UTF_8))

    override fun deserialize(bytes: ByteArray): Result<String> =
        try {
            Result.Ok(String(bytes, Charsets.UTF_8))
        } catch (e: Exception) {
            Result.Err(PipelineError.SerializationError("Failed to deserialize string", e))
        }
}

class IntCodec : Codec<Int> {
    override fun serialize(value: Int): Result<ByteArray> {
        val bytes = ByteArray(4)
        bytes[0] = (value shr 24).toByte()
        bytes[1] = (value shr 16).toByte()
        bytes[2] = (value shr 8).toByte()
        bytes[3] = value.toByte()
        return Result.Ok(bytes)
    }

    override fun deserialize(bytes: ByteArray): Result<Int> {
        if (bytes.size < 4) {
            return Result.Err(PipelineError.SerializationError("Need at least 4 bytes for Int"))
        }
        val value = ((bytes[0].toInt() and 0xFF) shl 24) or
                ((bytes[1].toInt() and 0xFF) shl 16) or
                ((bytes[2].toInt() and 0xFF) shl 8) or
                (bytes[3].toInt() and 0xFF)
        return Result.Ok(value)
    }
}

class LongCodec : Codec<Long> {
    override fun serialize(value: Long): Result<ByteArray> {
        val bytes = ByteArray(8)
        for (i in 7 downTo 0) {
            bytes[7 - i] = (value shr (i * 8)).toByte()
        }
        return Result.Ok(bytes)
    }

    override fun deserialize(bytes: ByteArray): Result<Long> {
        if (bytes.size < 8) {
            return Result.Err(PipelineError.SerializationError("Need at least 8 bytes for Long"))
        }
        var value = 0L
        for (i in 0 until 8) {
            value = (value shl 8) or (bytes[i].toLong() and 0xFF)
        }
        return Result.Ok(value)
    }
}

class JsonCodec : Codec<Map<String, Any?>> {
    override fun serialize(value: Map<String, Any?>): Result<ByteArray> =
        try {
            Result.Ok(encodeJson(value).toByteArray(Charsets.UTF_8))
        } catch (e: Exception) {
            Result.Err(PipelineError.SerializationError("JSON serialization failed", e))
        }

    override fun deserialize(bytes: ByteArray): Result<Map<String, Any?>> =
        try {
            val json = String(bytes, Charsets.UTF_8)
            Result.Ok(parseJson(json))
        } catch (e: Exception) {
            Result.Err(PipelineError.SerializationError("JSON deserialization failed", e))
        }

    private fun encodeJson(value: Any?): String = when (value) {
        null -> "null"
        is String -> "\"${escapeJson(value)}\""
        is Number -> value.toString()
        is Boolean -> value.toString()
        is Map<*, *> -> {
            val entries = value.entries.joinToString(",") { (k, v) ->
                "\"${escapeJson(k.toString())}\":${encodeJson(v)}"
            }
            "{$entries}"
        }
        is List<*> -> {
            val items = value.joinToString(",") { encodeJson(it) }
            "[$items]"
        }
        is ByteArray -> "\"${java.util.Base64.getEncoder().encodeToString(value)}\""
        else -> "\"${escapeJson(value.toString())}\""
    }

    private fun escapeJson(s: String): String = s
        .replace("\\", "\\\\")
        .replace("\"", "\\\"")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")

    private fun parseJson(json: String): Map<String, Any?> {
        val trimmed = json.trim()
        if (!trimmed.startsWith("{")) throw IllegalArgumentException("Expected JSON object")
        return parseObject(trimmed, 0).first
    }

    private fun parseObject(json: String, start: Int): Pair<Map<String, Any?>, Int> {
        val result = mutableMapOf<String, Any?>()
        var i = start + 1
        i = skipWhitespace(json, i)

        if (i < json.length && json[i] == '}') return result to (i + 1)

        while (i < json.length) {
            i = skipWhitespace(json, i)
            val (key, nextIdx) = parseString(json, i)
            i = skipWhitespace(json, nextIdx)
            if (json[i] != ':') throw IllegalArgumentException("Expected ':' at $i")
            i = skipWhitespace(json, i + 1)
            val (value, endIdx) = parseValue(json, i)
            result[key] = value
            i = skipWhitespace(json, endIdx)
            if (i < json.length && json[i] == '}') return result to (i + 1)
            if (i < json.length && json[i] == ',') i++
        }
        return result to i
    }

    private fun parseValue(json: String, start: Int): Pair<Any?, Int> {
        val i = skipWhitespace(json, start)
        return when {
            json[i] == '"' -> parseString(json, i)
            json[i] == '{' -> parseObject(json, i)
            json[i] == '[' -> parseArray(json, i)
            json.startsWith("null", i) -> null to (i + 4)
            json.startsWith("true", i) -> true to (i + 4)
            json.startsWith("false", i) -> false to (i + 5)
            json[i].isDigit() || json[i] == '-' -> parseNumber(json, i)
            else -> throw IllegalArgumentException("Unexpected char '${json[i]}' at $i")
        }
    }

    private fun parseString(json: String, start: Int): Pair<String, Int> {
        val sb = StringBuilder()
        var i = start + 1
        while (i < json.length && json[i] != '"') {
            if (json[i] == '\\') {
                i++
                when (json[i]) {
                    '"' -> sb.append('"')
                    '\\' -> sb.append('\\')
                    'n' -> sb.append('\n')
                    'r' -> sb.append('\r')
                    't' -> sb.append('\t')
                    else -> { sb.append('\\'); sb.append(json[i]) }
                }
            } else {
                sb.append(json[i])
            }
            i++
        }
        return sb.toString() to (i + 1)
    }

    private fun parseArray(json: String, start: Int): Pair<List<Any?>, Int> {
        val result = mutableListOf<Any?>()
        var i = start + 1
        i = skipWhitespace(json, i)
        if (i < json.length && json[i] == ']') return result to (i + 1)

        while (i < json.length) {
            val (value, nextIdx) = parseValue(json, i)
            result.add(value)
            i = skipWhitespace(json, nextIdx)
            if (i < json.length && json[i] == ']') return result to (i + 1)
            if (i < json.length && json[i] == ',') i++
            i = skipWhitespace(json, i)
        }
        return result to i
    }

    private fun parseNumber(json: String, start: Int): Pair<Number, Int> {
        var i = start
        var isDouble = false
        if (json[i] == '-') i++
        while (i < json.length && (json[i].isDigit() || json[i] == '.' || json[i] == 'e' || json[i] == 'E')) {
            if (json[i] == '.' || json[i] == 'e' || json[i] == 'E') isDouble = true
            i++
        }
        val numStr = json.substring(start, i)
        return if (isDouble) numStr.toDouble() to i else numStr.toLong() to i
    }

    private fun skipWhitespace(json: String, start: Int): Int {
        var i = start
        while (i < json.length && json[i].isWhitespace()) i++
        return i
    }
}

class SchemaAwareCodec(
    private val registry: SchemaRegistry,
    private val schemaName: String
) : Codec<Map<String, Any?>> {
    private val jsonCodec = JsonCodec()

    override fun serialize(value: Map<String, Any?>): Result<ByteArray> {
        val schema = registry.getSchema(schemaName)
        if (schema.isErr) return Result.Err((schema as Result.Err).error)
        val s = (schema as Result.Ok).value

        val validated = mutableMapOf<String, Any?>()
        for (field in s.fields) {
            val fieldValue = value[field.name]
            if (fieldValue == null && field.defaultValue == null && field.type !is FieldType.NullableType) {
                return Result.Err(PipelineError.SerializationError(
                    "Required field '${field.name}' is missing"
                ))
            }
            validated[field.name] = fieldValue ?: field.defaultValue
        }

        val envelope = mapOf<String, Any?>(
            "_schema" to schemaName,
            "_version" to s.version,
            "_data" to validated
        )
        return jsonCodec.serialize(envelope)
    }

    @Suppress("UNCHECKED_CAST")
    override fun deserialize(bytes: ByteArray): Result<Map<String, Any?>> {
        val envelopeResult = jsonCodec.deserialize(bytes)
        if (envelopeResult.isErr) return envelopeResult

        val envelope = (envelopeResult as Result.Ok).value
        val dataSchemaName = envelope["_schema"] as? String
        val dataVersion = (envelope["_version"] as? Number)?.toInt() ?: 1
        val data = envelope["_data"] as? Map<String, Any?>
            ?: return Result.Err(PipelineError.SerializationError("Missing _data field in envelope"))

        val currentSchema = registry.getSchema(schemaName)
        if (currentSchema.isErr) return Result.Err((currentSchema as Result.Err).error)
        val schema = (currentSchema as Result.Ok).value

        val migrated = mutableMapOf<String, Any?>()
        for (field in schema.fields) {
            val value = data[field.name]
                ?: field.aliases.firstNotNullOfOrNull { alias -> data[alias] }
                ?: field.defaultValue
            migrated[field.name] = value
        }

        return Result.Ok(migrated)
    }
}

// ============================================================================
// Section 5: Bounded Channel with Backpressure
// ============================================================================

class BoundedChannel<T>(private val capacity: Int) {
    private val buffer = LinkedList<T>()
    private val lock = ReentrantReadWriteLock()
    private val closed = AtomicBoolean(false)
    private val metrics = ChannelMetrics()

    data class ChannelMetrics(
        val offered: AtomicLong = AtomicLong(0),
        val taken: AtomicLong = AtomicLong(0),
        val dropped: AtomicLong = AtomicLong(0),
        val backpressureEvents: AtomicLong = AtomicLong(0)
    )

    sealed class SendResult {
        object Sent : SendResult()
        object Full : SendResult()
        object Closed : SendResult()
    }

    sealed class ReceiveResult<out T> {
        data class Value<T>(val value: T) : ReceiveResult<T>()
        object Empty : ReceiveResult<Nothing>()
        object Closed : ReceiveResult<Nothing>()
    }

    fun trySend(element: T): SendResult {
        if (closed.get()) return SendResult.Closed

        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            if (buffer.size >= capacity) {
                metrics.backpressureEvents.incrementAndGet()
                return SendResult.Full
            }
            buffer.addLast(element)
            metrics.offered.incrementAndGet()
            return SendResult.Sent
        } finally {
            writeLock.unlock()
        }
    }

    fun sendBlocking(element: T, timeoutMs: Long = 5000): SendResult {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            val result = trySend(element)
            if (result != SendResult.Full) return result
            Thread.sleep(1)
        }
        metrics.dropped.incrementAndGet()
        return SendResult.Full
    }

    fun tryReceive(): ReceiveResult<T> {
        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            if (buffer.isEmpty()) {
                return if (closed.get()) ReceiveResult.Closed else ReceiveResult.Empty
            }
            val value = buffer.removeFirst()
            metrics.taken.incrementAndGet()
            return ReceiveResult.Value(value)
        } finally {
            writeLock.unlock()
        }
    }

    fun receiveBlocking(timeoutMs: Long = 5000): ReceiveResult<T> {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            val result = tryReceive()
            if (result !is ReceiveResult.Empty) return result
            Thread.sleep(1)
        }
        return if (closed.get()) ReceiveResult.Closed else ReceiveResult.Empty
    }

    fun close() {
        closed.set(true)
    }

    val size: Int
        get() {
            val readLock = lock.readLock()
            readLock.lock()
            try {
                return buffer.size
            } finally {
                readLock.unlock()
            }
        }

    val isClosed: Boolean get() = closed.get()
    val isEmpty: Boolean get() = size == 0
    val isFull: Boolean get() = size >= capacity

    fun getMetrics(): ChannelMetrics = metrics

    fun drain(): List<T> {
        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            val items = buffer.toList()
            buffer.clear()
            return items
        } finally {
            writeLock.unlock()
        }
    }
}

// ============================================================================
// Section 6: Circuit Breaker
// ============================================================================

class CircuitBreaker(
    private val name: String,
    private val failureThreshold: Int = 5,
    private val resetTimeoutMs: Long = 30_000,
    private val halfOpenMaxCalls: Int = 3
) {
    enum class State { CLOSED, OPEN, HALF_OPEN }

    private val state = AtomicReference(State.CLOSED)
    private val failureCount = AtomicLong(0)
    private val successCount = AtomicLong(0)
    private val halfOpenCalls = AtomicLong(0)
    private val lastFailureTime = AtomicLong(0)
    private val totalCalls = AtomicLong(0)
    private val totalFailures = AtomicLong(0)

    fun <T> execute(action: () -> T): Result<T> {
        return when (state.get()) {
            State.OPEN -> {
                if (shouldAttemptReset()) {
                    state.set(State.HALF_OPEN)
                    halfOpenCalls.set(0)
                    tryExecution(action)
                } else {
                    Result.Err(PipelineError.CircuitBreakerOpen(name))
                }
            }
            State.HALF_OPEN -> {
                if (halfOpenCalls.get() < halfOpenMaxCalls) {
                    halfOpenCalls.incrementAndGet()
                    tryExecution(action)
                } else {
                    Result.Err(PipelineError.CircuitBreakerOpen(name))
                }
            }
            State.CLOSED -> tryExecution(action)
            else -> Result.Err(PipelineError.CircuitBreakerOpen(name))
        }
    }

    private fun <T> tryExecution(action: () -> T): Result<T> {
        totalCalls.incrementAndGet()
        return try {
            val result = action()
            onSuccess()
            Result.Ok(result)
        } catch (e: Exception) {
            onFailure()
            Result.Err(PipelineError.StageError(name, e.message ?: "Unknown error", e))
        }
    }

    private fun onSuccess() {
        successCount.incrementAndGet()
        when (state.get()) {
            State.HALF_OPEN -> {
                if (successCount.get() >= halfOpenMaxCalls) {
                    state.set(State.CLOSED)
                    failureCount.set(0)
                    successCount.set(0)
                }
            }
            else -> {
                failureCount.set(0)
            }
        }
    }

    private fun onFailure() {
        totalFailures.incrementAndGet()
        lastFailureTime.set(System.currentTimeMillis())
        failureCount.incrementAndGet()
        when (state.get()) {
            State.HALF_OPEN -> {
                state.set(State.OPEN)
                successCount.set(0)
            }
            State.CLOSED -> {
                if (failureCount.get() >= failureThreshold) {
                    state.set(State.OPEN)
                }
            }
            else -> {}
        }
    }

    private fun shouldAttemptReset(): Boolean {
        return System.currentTimeMillis() - lastFailureTime.get() >= resetTimeoutMs
    }

    fun getState(): State = state.get()
    fun reset() {
        state.set(State.CLOSED)
        failureCount.set(0)
        successCount.set(0)
        halfOpenCalls.set(0)
    }

    fun getStats(): Map<String, Any> = mapOf(
        "state" to state.get().name,
        "failureCount" to failureCount.get(),
        "totalCalls" to totalCalls.get(),
        "totalFailures" to totalFailures.get(),
        "errorRate" to if (totalCalls.get() > 0) totalFailures.get().toDouble() / totalCalls.get() else 0.0
    )
}

// ============================================================================
// Section 7: Retry Policy
// ============================================================================

sealed class RetryPolicy {
    abstract val maxAttempts: Int
    abstract val retryableErrors: Set<Class<out PipelineError>>

    data class FixedDelay(
        override val maxAttempts: Int = 3,
        val delayMs: Long = 1000,
        override val retryableErrors: Set<Class<out PipelineError>> = emptySet()
    ) : RetryPolicy()

    data class ExponentialBackoff(
        override val maxAttempts: Int = 5,
        val initialDelayMs: Long = 100,
        val maxDelayMs: Long = 30_000,
        val multiplier: Double = 2.0,
        val jitterFraction: Double = 0.1,
        override val retryableErrors: Set<Class<out PipelineError>> = emptySet()
    ) : RetryPolicy()

    data class Linear(
        override val maxAttempts: Int = 3,
        val baseDelayMs: Long = 500,
        val incrementMs: Long = 500,
        override val retryableErrors: Set<Class<out PipelineError>> = emptySet()
    ) : RetryPolicy()

    object NoRetry : RetryPolicy() {
        override val maxAttempts: Int = 1
        override val retryableErrors: Set<Class<out PipelineError>> = emptySet()
    }

    fun shouldRetry(error: PipelineError, attempt: Int): Boolean {
        if (attempt >= maxAttempts) return false
        if (retryableErrors.isEmpty()) return true
        return retryableErrors.any { it.isInstance(error) }
    }

    fun getDelay(attempt: Int): Long = when (this) {
        is FixedDelay -> delayMs
        is ExponentialBackoff -> {
            val delay = (initialDelayMs * Math.pow(multiplier, attempt.toDouble())).toLong()
            val capped = min(delay, maxDelayMs)
            val jitter = (capped * jitterFraction * Math.random()).toLong()
            capped + jitter
        }
        is Linear -> baseDelayMs + (incrementMs * attempt)
        is NoRetry -> 0
    }
}

class RetryExecutor(private val policy: RetryPolicy) {
    data class RetryResult<T>(
        val result: Result<T>,
        val attempts: Int,
        val totalDelayMs: Long
    )

    fun <T> execute(action: () -> T): RetryResult<T> {
        var lastError: PipelineError? = null
        var totalDelay = 0L

        for (attempt in 0 until policy.maxAttempts) {
            try {
                val result = action()
                return RetryResult(Result.Ok(result), attempt + 1, totalDelay)
            } catch (e: PipelineException) {
                lastError = e.error
                if (!policy.shouldRetry(e.error, attempt + 1)) {
                    return RetryResult(Result.Err(e.error), attempt + 1, totalDelay)
                }
                val delay = policy.getDelay(attempt)
                totalDelay += delay
                Thread.sleep(delay)
            } catch (e: Exception) {
                val error = PipelineError.StageError("retry", e.message ?: "Unknown", e)
                lastError = error
                if (!policy.shouldRetry(error, attempt + 1)) {
                    return RetryResult(Result.Err(error), attempt + 1, totalDelay)
                }
                val delay = policy.getDelay(attempt)
                totalDelay += delay
                Thread.sleep(delay)
            }
        }

        return RetryResult(
            Result.Err(PipelineError.RetryExhausted(policy.maxAttempts, lastError!!)),
            policy.maxAttempts,
            totalDelay
        )
    }
}

// ============================================================================
// Section 8: Dead Letter Queue
// ============================================================================

data class DeadLetter<K, V>(
    val record: Record<K, V>,
    val error: PipelineError,
    val stageName: String,
    val timestamp: Long = System.currentTimeMillis(),
    val attemptCount: Int = 1,
    val id: String = UUID.randomUUID().toString()
)

class DeadLetterQueue<K, V>(private val maxSize: Int = 10_000) {
    private val queue = ConcurrentLinkedQueue<DeadLetter<K, V>>()
    private val count = AtomicLong(0)
    private val totalReceived = AtomicLong(0)
    private val handlers = mutableListOf<(DeadLetter<K, V>) -> Unit>()

    fun enqueue(deadLetter: DeadLetter<K, V>) {
        totalReceived.incrementAndGet()
        if (count.get() >= maxSize) {
            queue.poll()
            count.decrementAndGet()
        }
        queue.offer(deadLetter)
        count.incrementAndGet()
        handlers.forEach { handler ->
            try { handler(deadLetter) } catch (_: Exception) {}
        }
    }

    fun dequeue(): DeadLetter<K, V>? {
        val item = queue.poll()
        if (item != null) count.decrementAndGet()
        return item
    }

    fun peek(): DeadLetter<K, V>? = queue.peek()

    fun size(): Long = count.get()

    fun drain(): List<DeadLetter<K, V>> {
        val items = mutableListOf<DeadLetter<K, V>>()
        while (true) {
            val item = queue.poll() ?: break
            items.add(item)
        }
        count.set(0)
        return items
    }

    fun onDeadLetter(handler: (DeadLetter<K, V>) -> Unit) {
        handlers.add(handler)
    }

    fun getByStage(stageName: String): List<DeadLetter<K, V>> =
        queue.filter { it.stageName == stageName }

    fun getStats(): Map<String, Any> = mapOf(
        "size" to count.get(),
        "totalReceived" to totalReceived.get(),
        "byStage" to queue.groupBy { it.stageName }.mapValues { it.value.size }
    )
}

// ============================================================================
// Section 9: Metrics and Monitoring
// ============================================================================

class LatencyHistogram(private val maxSamples: Int = 10_000) {
    private val samples = mutableListOf<Long>()
    private val lock = ReentrantReadWriteLock()
    private val totalCount = AtomicLong(0)
    private val totalSum = AtomicLong(0)

    fun record(latencyNanos: Long) {
        totalCount.incrementAndGet()
        totalSum.addAndGet(latencyNanos)

        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            if (samples.size >= maxSamples) {
                samples.removeAt(0)
            }
            samples.add(latencyNanos)
        } finally {
            writeLock.unlock()
        }
    }

    fun percentile(p: Double): Long {
        val readLock = lock.readLock()
        readLock.lock()
        try {
            if (samples.isEmpty()) return 0
            val sorted = samples.sorted()
            val index = ((p / 100.0) * (sorted.size - 1)).toInt()
            return sorted[index.coerceIn(0, sorted.size - 1)]
        } finally {
            readLock.unlock()
        }
    }

    fun p50(): Long = percentile(50.0)
    fun p90(): Long = percentile(90.0)
    fun p95(): Long = percentile(95.0)
    fun p99(): Long = percentile(99.0)

    fun mean(): Double {
        val count = totalCount.get()
        if (count == 0L) return 0.0
        return totalSum.get().toDouble() / count
    }

    fun stddev(): Double {
        val readLock = lock.readLock()
        readLock.lock()
        try {
            if (samples.size < 2) return 0.0
            val avg = samples.average()
            val variance = samples.map { (it - avg) * (it - avg) }.average()
            return sqrt(variance)
        } finally {
            readLock.unlock()
        }
    }

    fun count(): Long = totalCount.get()

    fun reset() {
        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            samples.clear()
            totalCount.set(0)
            totalSum.set(0)
        } finally {
            writeLock.unlock()
        }
    }
}

class StageMetrics(val stageName: String) {
    val inputCount = AtomicLong(0)
    val outputCount = AtomicLong(0)
    val errorCount = AtomicLong(0)
    val latency = LatencyHistogram()
    val startTime = AtomicLong(System.currentTimeMillis())
    val lastProcessedTime = AtomicLong(0)

    fun recordInput() { inputCount.incrementAndGet() }
    fun recordOutput() { outputCount.incrementAndGet() }
    fun recordError() { errorCount.incrementAndGet() }

    fun throughput(): Double {
        val elapsed = System.currentTimeMillis() - startTime.get()
        if (elapsed <= 0) return 0.0
        return outputCount.get().toDouble() / (elapsed / 1000.0)
    }

    fun errorRate(): Double {
        val total = inputCount.get()
        if (total == 0L) return 0.0
        return errorCount.get().toDouble() / total
    }

    fun toMap(): Map<String, Any> = mapOf(
        "stageName" to stageName,
        "inputCount" to inputCount.get(),
        "outputCount" to outputCount.get(),
        "errorCount" to errorCount.get(),
        "throughput" to throughput(),
        "errorRate" to errorRate(),
        "latencyP50ms" to latency.p50() / 1_000_000.0,
        "latencyP90ms" to latency.p90() / 1_000_000.0,
        "latencyP95ms" to latency.p95() / 1_000_000.0,
        "latencyP99ms" to latency.p99() / 1_000_000.0,
        "latencyMeanMs" to latency.mean() / 1_000_000.0
    )
}

class PipelineMetrics(val pipelineName: String) {
    private val stageMetrics = ConcurrentHashMap<String, StageMetrics>()
    private val pipelineStartTime = AtomicLong(System.currentTimeMillis())
    private val totalRecordsIn = AtomicLong(0)
    private val totalRecordsOut = AtomicLong(0)

    fun getOrCreateStageMetrics(stageName: String): StageMetrics =
        stageMetrics.getOrPut(stageName) { StageMetrics(stageName) }

    fun recordPipelineInput() { totalRecordsIn.incrementAndGet() }
    fun recordPipelineOutput() { totalRecordsOut.incrementAndGet() }

    fun overallThroughput(): Double {
        val elapsed = System.currentTimeMillis() - pipelineStartTime.get()
        if (elapsed <= 0) return 0.0
        return totalRecordsOut.get().toDouble() / (elapsed / 1000.0)
    }

    fun overallErrorRate(): Double {
        val totalErrors = stageMetrics.values.sumOf { it.errorCount.get() }
        val totalInput = totalRecordsIn.get()
        if (totalInput == 0L) return 0.0
        return totalErrors.toDouble() / totalInput
    }

    fun summary(): Map<String, Any> = mapOf(
        "pipeline" to pipelineName,
        "totalRecordsIn" to totalRecordsIn.get(),
        "totalRecordsOut" to totalRecordsOut.get(),
        "overallThroughput" to overallThroughput(),
        "overallErrorRate" to overallErrorRate(),
        "stages" to stageMetrics.values.map { it.toMap() }
    )

    fun stageNames(): List<String> = stageMetrics.keys().toList()

    fun reset() {
        stageMetrics.clear()
        pipelineStartTime.set(System.currentTimeMillis())
        totalRecordsIn.set(0)
        totalRecordsOut.set(0)
    }
}

// ============================================================================
// Section 10: State Store
// ============================================================================

class StateStore<K, V>(private val name: String) {
    private val store = ConcurrentHashMap<K, V>()
    private val lock = ReentrantReadWriteLock()
    private val version = AtomicLong(0)
    private val changelog = ConcurrentLinkedQueue<StateChange<K, V>>()
    private val maxChangelogSize = 10_000

    data class StateChange<K, V>(
        val key: K,
        val oldValue: V?,
        val newValue: V?,
        val timestamp: Long = System.currentTimeMillis(),
        val version: Long
    )

    fun get(key: K): V? = store[key]

    fun getOrDefault(key: K, default: V): V = store.getOrDefault(key, default)

    fun put(key: K, value: V): V? {
        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            val old = store.put(key, value)
            val ver = version.incrementAndGet()
            recordChange(StateChange(key, old, value, version = ver))
            return old
        } finally {
            writeLock.unlock()
        }
    }

    fun putIfAbsent(key: K, value: V): V? {
        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            val existing = store[key]
            if (existing != null) return existing
            store[key] = value
            val ver = version.incrementAndGet()
            recordChange(StateChange(key, null, value, version = ver))
            return null
        } finally {
            writeLock.unlock()
        }
    }

    fun delete(key: K): V? {
        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            val old = store.remove(key)
            if (old != null) {
                val ver = version.incrementAndGet()
                recordChange(StateChange(key, old, null, version = ver))
            }
            return old
        } finally {
            writeLock.unlock()
        }
    }

    fun computeIfPresent(key: K, remapping: (K, V) -> V): V? {
        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            val existing = store[key] ?: return null
            val newValue = remapping(key, existing)
            store[key] = newValue
            val ver = version.incrementAndGet()
            recordChange(StateChange(key, existing, newValue, version = ver))
            return newValue
        } finally {
            writeLock.unlock()
        }
    }

    fun compute(key: K, remapping: (K, V?) -> V): V {
        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            val existing = store[key]
            val newValue = remapping(key, existing)
            store[key] = newValue
            val ver = version.incrementAndGet()
            recordChange(StateChange(key, existing, newValue, version = ver))
            return newValue
        } finally {
            writeLock.unlock()
        }
    }

    fun contains(key: K): Boolean = store.containsKey(key)

    fun keys(): Set<K> = store.keys.toSet()

    fun values(): Collection<V> = store.values.toList()

    fun entries(): Set<Map.Entry<K, V>> = store.entries.toSet()

    fun size(): Int = store.size

    fun clear() {
        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            store.clear()
            version.incrementAndGet()
        } finally {
            writeLock.unlock()
        }
    }

    fun snapshot(): Map<K, V> = store.toMap()

    fun getChangelog(sinceVersion: Long = 0): List<StateChange<K, V>> =
        changelog.filter { it.version > sinceVersion }

    fun getName(): String = name
    fun getVersion(): Long = version.get()

    private fun recordChange(change: StateChange<K, V>) {
        changelog.offer(change)
        while (changelog.size > maxChangelogSize) {
            changelog.poll()
        }
    }
}

// ============================================================================
// Section 11: Windowing
// ============================================================================

sealed class WindowType {
    data class Tumbling(val sizeMs: Long) : WindowType()
    data class Sliding(val sizeMs: Long, val slideMs: Long) : WindowType()
    data class Session(val gapMs: Long) : WindowType()
}

data class Window(
    val start: Long,
    val end: Long,
    val type: String
) {
    fun contains(timestamp: Long): Boolean = timestamp in start until end
    fun durationMs(): Long = end - start
    fun overlapsWith(other: Window): Boolean = start < other.end && end > other.start
}

data class WindowedRecord<K, V>(
    val window: Window,
    val records: List<Record<K, V>>
) {
    fun size(): Int = records.size
    fun isEmpty(): Boolean = records.isEmpty()
    fun timestamps(): List<Long> = records.map { it.timestamp }
    fun minTimestamp(): Long = records.minOfOrNull { it.timestamp } ?: 0L
    fun maxTimestamp(): Long = records.maxOfOrNull { it.timestamp } ?: 0L
}

class WindowAssigner<K, V>(private val windowType: WindowType) {
    private val openWindows = mutableListOf<MutableWindowBuffer<K, V>>()
    private val lock = ReentrantReadWriteLock()

    private data class MutableWindowBuffer<K, V>(
        val window: Window,
        val records: MutableList<Record<K, V>> = mutableListOf(),
        var lastActivity: Long = System.currentTimeMillis()
    )

    fun assign(record: Record<K, V>): List<WindowedRecord<K, V>> {
        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            return when (windowType) {
                is WindowType.Tumbling -> assignTumbling(record, windowType.sizeMs)
                is WindowType.Sliding -> assignSliding(record, windowType.sizeMs, windowType.slideMs)
                is WindowType.Session -> assignSession(record, windowType.gapMs)
            }
        } finally {
            writeLock.unlock()
        }
    }

    fun flush(): List<WindowedRecord<K, V>> {
        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            val result = openWindows.map { buf ->
                WindowedRecord(buf.window, buf.records.toList())
            }
            openWindows.clear()
            return result
        } finally {
            writeLock.unlock()
        }
    }

    private fun assignTumbling(record: Record<K, V>, sizeMs: Long): List<WindowedRecord<K, V>> {
        val closedWindows = mutableListOf<WindowedRecord<K, V>>()
        val windowStart = (record.timestamp / sizeMs) * sizeMs
        val windowEnd = windowStart + sizeMs

        val existing = openWindows.find { it.window.start == windowStart }
        if (existing != null) {
            existing.records.add(record)
            existing.lastActivity = System.currentTimeMillis()
        } else {
            // Close any older windows
            val iterator = openWindows.iterator()
            while (iterator.hasNext()) {
                val buf = iterator.next()
                if (buf.window.end <= record.timestamp) {
                    closedWindows.add(WindowedRecord(buf.window, buf.records.toList()))
                    iterator.remove()
                }
            }
            val window = Window(windowStart, windowEnd, "tumbling")
            val buffer = MutableWindowBuffer<K, V>(window)
            buffer.records.add(record)
            openWindows.add(buffer)
        }

        return closedWindows
    }

    private fun assignSliding(record: Record<K, V>, sizeMs: Long, slideMs: Long): List<WindowedRecord<K, V>> {
        val closedWindows = mutableListOf<WindowedRecord<K, V>>()
        val baseWindowStart = (record.timestamp / slideMs) * slideMs

        // A sliding window that contains this record
        val relevantStarts = mutableListOf<Long>()
        var ws = baseWindowStart
        while (ws + sizeMs > record.timestamp && ws <= record.timestamp) {
            relevantStarts.add(ws)
            ws -= slideMs
        }

        for (start in relevantStarts) {
            val window = Window(start, start + sizeMs, "sliding")
            val existing = openWindows.find { it.window.start == start && it.window.end == start + sizeMs }
            if (existing != null) {
                existing.records.add(record)
                existing.lastActivity = System.currentTimeMillis()
            } else {
                val buffer = MutableWindowBuffer<K, V>(window)
                buffer.records.add(record)
                openWindows.add(buffer)
            }
        }

        // Close expired windows
        val iterator = openWindows.iterator()
        while (iterator.hasNext()) {
            val buf = iterator.next()
            if (buf.window.end <= record.timestamp) {
                closedWindows.add(WindowedRecord(buf.window, buf.records.toList()))
                iterator.remove()
            }
        }

        return closedWindows
    }

    private fun assignSession(record: Record<K, V>, gapMs: Long): List<WindowedRecord<K, V>> {
        val closedWindows = mutableListOf<WindowedRecord<K, V>>()

        // Find sessions to merge into
        val mergeable = openWindows.filter { buf ->
            record.timestamp >= buf.window.start - gapMs && record.timestamp <= buf.window.end + gapMs
        }

        if (mergeable.isEmpty()) {
            val window = Window(record.timestamp, record.timestamp + 1, "session")
            val buffer = MutableWindowBuffer<K, V>(window)
            buffer.records.add(record)
            openWindows.add(buffer)
        } else if (mergeable.size == 1) {
            val buf = mergeable[0]
            buf.records.add(record)
            val newStart = min(buf.window.start, record.timestamp)
            val newEnd = max(buf.window.end, record.timestamp + 1)
            val idx = openWindows.indexOf(buf)
            openWindows[idx] = buf.copy(
                window = Window(newStart, newEnd, "session"),
                lastActivity = System.currentTimeMillis()
            )
        } else {
            // Merge multiple sessions
            val allRecords = mutableListOf<Record<K, V>>()
            for (buf in mergeable) {
                allRecords.addAll(buf.records)
                openWindows.remove(buf)
            }
            allRecords.add(record)
            val newStart = min(allRecords.minOf { it.timestamp }, record.timestamp)
            val newEnd = max(allRecords.maxOf { it.timestamp } + 1, record.timestamp + 1)
            val window = Window(newStart, newEnd, "session")
            val buffer = MutableWindowBuffer<K, V>(window)
            buffer.records.addAll(allRecords)
            openWindows.add(buffer)
        }

        // Check for expired sessions
        val now = System.currentTimeMillis()
        val expiredIterator = openWindows.iterator()
        while (expiredIterator.hasNext()) {
            val buf = expiredIterator.next()
            if (now - buf.lastActivity > gapMs * 2) {
                closedWindows.add(WindowedRecord(buf.window, buf.records.toList()))
                expiredIterator.remove()
            }
        }

        return closedWindows
    }
}

// ============================================================================
// Section 12: Watermark Tracking
// ============================================================================

class WatermarkTracker(
    private val allowedLatenessMs: Long = 0,
    private val idleTimeoutMs: Long = 60_000
) {
    private val currentWatermark = AtomicLong(Long.MIN_VALUE)
    private val lastEventTime = AtomicLong(System.currentTimeMillis())
    private val partitionWatermarks = ConcurrentHashMap<Int, Long>()
    private val lateEventCount = AtomicLong(0)
    private val droppedEventCount = AtomicLong(0)

    enum class EventTimeliness {
        ON_TIME, LATE_BUT_ALLOWED, DROPPED
    }

    fun advance(timestamp: Long, partition: Int = 0): EventTimeliness {
        lastEventTime.set(System.currentTimeMillis())
        partitionWatermarks[partition] = max(
            partitionWatermarks.getOrDefault(partition, Long.MIN_VALUE),
            timestamp
        )

        val minPartitionWm = if (partitionWatermarks.isEmpty()) {
            Long.MIN_VALUE
        } else {
            partitionWatermarks.values.min()
        }

        val wm = currentWatermark.get()

        return when {
            timestamp >= wm -> {
                currentWatermark.updateAndGet { max(it, minPartitionWm) }
                EventTimeliness.ON_TIME
            }
            timestamp >= wm - allowedLatenessMs -> {
                lateEventCount.incrementAndGet()
                EventTimeliness.LATE_BUT_ALLOWED
            }
            else -> {
                droppedEventCount.incrementAndGet()
                EventTimeliness.DROPPED
            }
        }
    }

    fun currentWatermark(): Long = currentWatermark.get()

    fun isIdle(): Boolean {
        return System.currentTimeMillis() - lastEventTime.get() > idleTimeoutMs
    }

    fun lateEventCount(): Long = lateEventCount.get()
    fun droppedEventCount(): Long = droppedEventCount.get()

    fun partitionWatermarks(): Map<Int, Long> = partitionWatermarks.toMap()

    fun reset() {
        currentWatermark.set(Long.MIN_VALUE)
        lastEventTime.set(System.currentTimeMillis())
        partitionWatermarks.clear()
        lateEventCount.set(0)
        droppedEventCount.set(0)
    }

    fun getStats(): Map<String, Any> = mapOf(
        "currentWatermark" to currentWatermark.get(),
        "lateEvents" to lateEventCount.get(),
        "droppedEvents" to droppedEventCount.get(),
        "partitions" to partitionWatermarks.size,
        "isIdle" to isIdle()
    )
}

// ============================================================================
// Section 13: Batching
// ============================================================================

class BatchAccumulator<K, V>(
    private val maxBatchSize: Int = 100,
    private val maxWaitMs: Long = 5000
) {
    private val buffer = mutableListOf<Record<K, V>>()
    private val lock = ReentrantReadWriteLock()
    private var batchStartTime = System.currentTimeMillis()
    private val batchCount = AtomicLong(0)
    private val totalRecords = AtomicLong(0)

    data class Batch<K, V>(
        val records: List<Record<K, V>>,
        val batchId: Long,
        val createdAt: Long = System.currentTimeMillis()
    ) {
        fun size(): Int = records.size
        fun isEmpty(): Boolean = records.isEmpty()
    }

    fun add(record: Record<K, V>): Batch<K, V>? {
        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            buffer.add(record)
            totalRecords.incrementAndGet()

            if (buffer.size >= maxBatchSize) {
                return emitBatch()
            }

            if (System.currentTimeMillis() - batchStartTime >= maxWaitMs && buffer.isNotEmpty()) {
                return emitBatch()
            }

            return null
        } finally {
            writeLock.unlock()
        }
    }

    fun flush(): Batch<K, V>? {
        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            if (buffer.isEmpty()) return null
            return emitBatch()
        } finally {
            writeLock.unlock()
        }
    }

    fun checkTimeout(): Batch<K, V>? {
        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            if (buffer.isEmpty()) return null
            if (System.currentTimeMillis() - batchStartTime >= maxWaitMs) {
                return emitBatch()
            }
            return null
        } finally {
            writeLock.unlock()
        }
    }

    private fun emitBatch(): Batch<K, V> {
        val records = buffer.toList()
        buffer.clear()
        batchStartTime = System.currentTimeMillis()
        val id = batchCount.incrementAndGet()
        return Batch(records, id)
    }

    fun pendingCount(): Int {
        val readLock = lock.readLock()
        readLock.lock()
        try {
            return buffer.size
        } finally {
            readLock.unlock()
        }
    }

    fun totalBatches(): Long = batchCount.get()
    fun totalRecords(): Long = totalRecords.get()
}

// ============================================================================
// Section 14: SQL-like Query DSL
// ============================================================================

sealed class Expr {
    data class Column(val name: String) : Expr()
    data class Literal(val value: Any?) : Expr()
    data class BinaryOp(val left: Expr, val op: String, val right: Expr) : Expr()
    data class UnaryOp(val op: String, val operand: Expr) : Expr()
    data class FunctionCall(val name: String, val args: List<Expr>) : Expr()
    data class Between(val expr: Expr, val low: Expr, val high: Expr) : Expr()
    data class InList(val expr: Expr, val values: List<Expr>) : Expr()
    data class IsNull(val expr: Expr) : Expr()
    data class IsNotNull(val expr: Expr) : Expr()
    data class Cast(val expr: Expr, val targetType: String) : Expr()
    data class Case(val conditions: List<Pair<Expr, Expr>>, val elseExpr: Expr?) : Expr()
}

sealed class QueryOp {
    data class Select(val columns: List<Pair<Expr, String?>>) : QueryOp()
    data class Filter(val predicate: Expr) : QueryOp()
    data class Project(val columns: List<String>) : QueryOp()
    data class OrderBy(val column: String, val ascending: Boolean = true) : QueryOp()
    data class Limit(val count: Int) : QueryOp()
    data class Offset(val count: Int) : QueryOp()
    data class GroupBy(val columns: List<String>, val aggregations: List<Aggregation>) : QueryOp()
    data class Distinct(val columns: List<String> = emptyList()) : QueryOp()
    data class Having(val predicate: Expr) : QueryOp()
}

data class Aggregation(
    val function: AggregateFunction,
    val column: String,
    val alias: String
)

enum class AggregateFunction {
    COUNT, SUM, AVG, MIN, MAX, COUNT_DISTINCT
}

class QueryBuilder {
    private val operations = mutableListOf<QueryOp>()

    fun select(vararg columns: Pair<Expr, String?>): QueryBuilder {
        operations.add(QueryOp.Select(columns.toList()))
        return this
    }

    fun selectColumns(vararg names: String): QueryBuilder {
        val cols = names.map { Expr.Column(it) to null as String? }
        operations.add(QueryOp.Select(cols))
        return this
    }

    fun filter(predicate: Expr): QueryBuilder {
        operations.add(QueryOp.Filter(predicate))
        return this
    }

    fun where(predicate: Expr): QueryBuilder = filter(predicate)

    fun project(vararg columns: String): QueryBuilder {
        operations.add(QueryOp.Project(columns.toList()))
        return this
    }

    fun orderBy(column: String, ascending: Boolean = true): QueryBuilder {
        operations.add(QueryOp.OrderBy(column, ascending))
        return this
    }

    fun limit(count: Int): QueryBuilder {
        operations.add(QueryOp.Limit(count))
        return this
    }

    fun offset(count: Int): QueryBuilder {
        operations.add(QueryOp.Offset(count))
        return this
    }

    fun groupBy(columns: List<String>, aggregations: List<Aggregation>): QueryBuilder {
        operations.add(QueryOp.GroupBy(columns, aggregations))
        return this
    }

    fun distinct(vararg columns: String): QueryBuilder {
        operations.add(QueryOp.Distinct(columns.toList()))
        return this
    }

    fun having(predicate: Expr): QueryBuilder {
        operations.add(QueryOp.Having(predicate))
        return this
    }

    fun build(): Query = Query(operations.toList())
}

data class Query(val operations: List<QueryOp>)

// Expression builder helpers
fun col(name: String): Expr = Expr.Column(name)
fun lit(value: Any?): Expr = Expr.Literal(value)
infix fun Expr.eq(other: Expr): Expr = Expr.BinaryOp(this, "=", other)
infix fun Expr.neq(other: Expr): Expr = Expr.BinaryOp(this, "!=", other)
infix fun Expr.gt(other: Expr): Expr = Expr.BinaryOp(this, ">", other)
infix fun Expr.gte(other: Expr): Expr = Expr.BinaryOp(this, ">=", other)
infix fun Expr.lt(other: Expr): Expr = Expr.BinaryOp(this, "<", other)
infix fun Expr.lte(other: Expr): Expr = Expr.BinaryOp(this, "<=", other)
infix fun Expr.and(other: Expr): Expr = Expr.BinaryOp(this, "AND", other)
infix fun Expr.or(other: Expr): Expr = Expr.BinaryOp(this, "OR", other)
fun Expr.not(): Expr = Expr.UnaryOp("NOT", this)
fun Expr.isNull(): Expr = Expr.IsNull(this)
fun Expr.isNotNull(): Expr = Expr.IsNotNull(this)
infix fun Expr.like(pattern: Expr): Expr = Expr.BinaryOp(this, "LIKE", pattern)
fun Expr.between(low: Expr, high: Expr): Expr = Expr.Between(this, low, high)
fun Expr.inList(vararg values: Expr): Expr = Expr.InList(this, values.toList())
fun count(column: String): Expr = Expr.FunctionCall("COUNT", listOf(col(column)))
fun sum(column: String): Expr = Expr.FunctionCall("SUM", listOf(col(column)))
fun avg(column: String): Expr = Expr.FunctionCall("AVG", listOf(col(column)))
fun minOf(column: String): Expr = Expr.FunctionCall("MIN", listOf(col(column)))
fun maxOf(column: String): Expr = Expr.FunctionCall("MAX", listOf(col(column)))

class QueryExecutor {
    @Suppress("UNCHECKED_CAST")
    fun execute(query: Query, data: List<Map<String, Any?>>): Result<List<Map<String, Any?>>> {
        try {
            var result = data.toMutableList()

            for (op in query.operations) {
                result = when (op) {
                    is QueryOp.Filter -> {
                        result.filter { row -> evaluatePredicate(op.predicate, row) }.toMutableList()
                    }
                    is QueryOp.Project -> {
                        result.map { row -> row.filterKeys { it in op.columns } }.toMutableList()
                    }
                    is QueryOp.Select -> {
                        result.map { row ->
                            val newRow = mutableMapOf<String, Any?>()
                            for ((expr, alias) in op.columns) {
                                val key = alias ?: when (expr) {
                                    is Expr.Column -> expr.name
                                    else -> expr.toString()
                                }
                                newRow[key] = evaluateExpr(expr, row)
                            }
                            newRow as Map<String, Any?>
                        }.toMutableList()
                    }
                    is QueryOp.OrderBy -> {
                        result.sortedWith(compareBy<Map<String, Any?>> {
                            val v = it[op.column]
                            when (v) {
                                is Comparable<*> -> v as Comparable<Any>
                                null -> null
                                else -> v.toString() as Comparable<Any>
                            }
                        }.let { if (!op.ascending) it.reversed() else it }).toMutableList()
                    }
                    is QueryOp.Limit -> result.take(op.count).toMutableList()
                    is QueryOp.Offset -> result.drop(op.count).toMutableList()
                    is QueryOp.Distinct -> {
                        if (op.columns.isEmpty()) {
                            result.distinct().toMutableList()
                        } else {
                            val seen = mutableSetOf<List<Any?>>()
                            result.filter { row ->
                                val key = op.columns.map { row[it] }
                                seen.add(key)
                            }.toMutableList()
                        }
                    }
                    is QueryOp.GroupBy -> executeGroupBy(result, op)
                    is QueryOp.Having -> {
                        result.filter { row -> evaluatePredicate(op.predicate, row) }.toMutableList()
                    }
                }
            }

            return Result.Ok(result)
        } catch (e: Exception) {
            return Result.Err(PipelineError.QueryError("Query execution failed: ${e.message}"))
        }
    }

    @Suppress("UNCHECKED_CAST")
    private fun executeGroupBy(
        data: MutableList<Map<String, Any?>>,
        op: QueryOp.GroupBy
    ): MutableList<Map<String, Any?>> {
        val groups = data.groupBy { row -> op.columns.map { row[it] } }

        return groups.map { (groupKey, rows) ->
            val result = mutableMapOf<String, Any?>()

            // Add group-by columns
            op.columns.forEachIndexed { idx, col ->
                result[col] = groupKey[idx]
            }

            // Add aggregations
            for (agg in op.aggregations) {
                result[agg.alias] = when (agg.function) {
                    AggregateFunction.COUNT -> rows.size.toLong()
                    AggregateFunction.COUNT_DISTINCT -> rows.map { it[agg.column] }.distinct().size.toLong()
                    AggregateFunction.SUM -> {
                        rows.mapNotNull { (it[agg.column] as? Number)?.toDouble() }.sum()
                    }
                    AggregateFunction.AVG -> {
                        val values = rows.mapNotNull { (it[agg.column] as? Number)?.toDouble() }
                        if (values.isEmpty()) 0.0 else values.average()
                    }
                    AggregateFunction.MIN -> {
                        rows.mapNotNull { it[agg.column] as? Comparable<Any> }.minOrNull()
                    }
                    AggregateFunction.MAX -> {
                        rows.mapNotNull { it[agg.column] as? Comparable<Any> }.maxOrNull()
                    }
                }
            }

            result as Map<String, Any?>
        }.toMutableList()
    }

    private fun evaluatePredicate(expr: Expr, row: Map<String, Any?>): Boolean {
        val result = evaluateExpr(expr, row)
        return result as? Boolean ?: false
    }

    @Suppress("UNCHECKED_CAST")
    private fun evaluateExpr(expr: Expr, row: Map<String, Any?>): Any? {
        return when (expr) {
            is Expr.Column -> row[expr.name]
            is Expr.Literal -> expr.value
            is Expr.BinaryOp -> {
                val left = evaluateExpr(expr.left, row)
                val right = evaluateExpr(expr.right, row)
                when (expr.op) {
                    "=" -> left == right
                    "!=" -> left != right
                    ">" -> compareValues(left, right) > 0
                    ">=" -> compareValues(left, right) >= 0
                    "<" -> compareValues(left, right) < 0
                    "<=" -> compareValues(left, right) <= 0
                    "AND" -> (left as? Boolean ?: false) && (right as? Boolean ?: false)
                    "OR" -> (left as? Boolean ?: false) || (right as? Boolean ?: false)
                    "LIKE" -> matchLike(left?.toString() ?: "", right?.toString() ?: "")
                    "+" -> numericOp(left, right) { a, b -> a + b }
                    "-" -> numericOp(left, right) { a, b -> a - b }
                    "*" -> numericOp(left, right) { a, b -> a * b }
                    "/" -> numericOp(left, right) { a, b -> if (b != 0.0) a / b else Double.NaN }
                    "%" -> numericOp(left, right) { a, b -> if (b != 0.0) a % b else Double.NaN }
                    else -> throw IllegalArgumentException("Unknown operator: ${expr.op}")
                }
            }
            is Expr.UnaryOp -> {
                val operand = evaluateExpr(expr.operand, row)
                when (expr.op) {
                    "NOT" -> !(operand as? Boolean ?: false)
                    "-" -> when (operand) {
                        is Int -> -operand
                        is Long -> -operand
                        is Double -> -operand
                        else -> null
                    }
                    else -> null
                }
            }
            is Expr.FunctionCall -> evaluateFunction(expr.name, expr.args.map { evaluateExpr(it, row) })
            is Expr.Between -> {
                val value = evaluateExpr(expr.expr, row)
                val low = evaluateExpr(expr.low, row)
                val high = evaluateExpr(expr.high, row)
                compareValues(value, low) >= 0 && compareValues(value, high) <= 0
            }
            is Expr.InList -> {
                val value = evaluateExpr(expr.expr, row)
                expr.values.any { evaluateExpr(it, row) == value }
            }
            is Expr.IsNull -> evaluateExpr(expr.expr, row) == null
            is Expr.IsNotNull -> evaluateExpr(expr.expr, row) != null
            is Expr.Cast -> {
                val value = evaluateExpr(expr.expr, row)
                when (expr.targetType.lowercase()) {
                    "string" -> value?.toString()
                    "int" -> (value as? Number)?.toInt() ?: value?.toString()?.toIntOrNull()
                    "long" -> (value as? Number)?.toLong() ?: value?.toString()?.toLongOrNull()
                    "double" -> (value as? Number)?.toDouble() ?: value?.toString()?.toDoubleOrNull()
                    "boolean" -> value?.toString()?.toBooleanStrictOrNull()
                    else -> value
                }
            }
            is Expr.Case -> {
                for ((condition, result) in expr.conditions) {
                    if (evaluatePredicate(condition, row)) {
                        return evaluateExpr(result, row)
                    }
                }
                expr.elseExpr?.let { evaluateExpr(it, row) }
            }
        }
    }

    @Suppress("UNCHECKED_CAST")
    private fun compareValues(left: Any?, right: Any?): Int {
        if (left == null && right == null) return 0
        if (left == null) return -1
        if (right == null) return 1

        return when {
            left is Number && right is Number -> left.toDouble().compareTo(right.toDouble())
            left is Comparable<*> && right is Comparable<*> -> {
                try {
                    (left as Comparable<Any>).compareTo(right)
                } catch (_: ClassCastException) {
                    left.toString().compareTo(right.toString())
                }
            }
            else -> left.toString().compareTo(right.toString())
        }
    }

    private fun numericOp(left: Any?, right: Any?, op: (Double, Double) -> Double): Any? {
        val l = (left as? Number)?.toDouble() ?: return null
        val r = (right as? Number)?.toDouble() ?: return null
        return op(l, r)
    }

    private fun matchLike(value: String, pattern: String): Boolean {
        val regex = pattern
            .replace("%", ".*")
            .replace("_", ".")
        return Regex("^$regex$", RegexOption.IGNORE_CASE).matches(value)
    }

    private fun evaluateFunction(name: String, args: List<Any?>): Any? {
        return when (name.uppercase()) {
            "COUNT" -> args.count { it != null }.toLong()
            "SUM" -> args.filterIsInstance<Number>().sumOf { it.toDouble() }
            "AVG" -> {
                val nums = args.filterIsInstance<Number>()
                if (nums.isEmpty()) 0.0 else nums.sumOf { it.toDouble() } / nums.size
            }
            "MIN" -> args.filterNotNull().minByOrNull { it.toString() }
            "MAX" -> args.filterNotNull().maxByOrNull { it.toString() }
            "UPPER" -> args.firstOrNull()?.toString()?.uppercase()
            "LOWER" -> args.firstOrNull()?.toString()?.lowercase()
            "TRIM" -> args.firstOrNull()?.toString()?.trim()
            "LENGTH" -> args.firstOrNull()?.toString()?.length?.toLong()
            "COALESCE" -> args.firstOrNull { it != null }
            "ABS" -> (args.firstOrNull() as? Number)?.toDouble()?.let { kotlin.math.abs(it) }
            "ROUND" -> {
                val value = (args.getOrNull(0) as? Number)?.toDouble() ?: return null
                val places = (args.getOrNull(1) as? Number)?.toInt() ?: 0
                val factor = Math.pow(10.0, places.toDouble())
                Math.round(value * factor) / factor
            }
            "CONCAT" -> args.joinToString("") { it?.toString() ?: "" }
            "SUBSTRING" -> {
                val str = args.getOrNull(0)?.toString() ?: return null
                val start = (args.getOrNull(1) as? Number)?.toInt() ?: 0
                val len = (args.getOrNull(2) as? Number)?.toInt() ?: str.length
                str.substring(start.coerceAtLeast(0), (start + len).coerceAtMost(str.length))
            }
            "IF" -> {
                val condition = args.getOrNull(0) as? Boolean ?: false
                if (condition) args.getOrNull(1) else args.getOrNull(2)
            }
            else -> null
        }
    }
}

// ============================================================================
// Section 15: Pipeline Stage Types
// ============================================================================

sealed class StageType {
    data class Source<K, V>(
        val name: String,
        val produce: () -> Record<K, V>?
    ) : StageType()

    data class Transform<KIn, VIn, KOut, VOut>(
        val name: String,
        val transform: (Record<KIn, VIn>) -> Record<KOut, VOut>?
    ) : StageType()

    data class FlatMapTransform<KIn, VIn, KOut, VOut>(
        val name: String,
        val transform: (Record<KIn, VIn>) -> List<Record<KOut, VOut>>
    ) : StageType()

    data class FilterStage<K, V>(
        val name: String,
        val predicate: (Record<K, V>) -> Boolean
    ) : StageType()

    data class StatefulTransform<KIn, VIn, KOut, VOut, S>(
        val name: String,
        val stateStore: StateStore<String, S>,
        val transform: (Record<KIn, VIn>, StateStore<String, S>) -> Record<KOut, VOut>?
    ) : StageType()

    data class WindowedTransform<KIn, VIn, KOut, VOut>(
        val name: String,
        val windowType: WindowType,
        val aggregate: (WindowedRecord<KIn, VIn>) -> Record<KOut, VOut>?
    ) : StageType()

    data class Sink<K, V>(
        val name: String,
        val consume: (Record<K, V>) -> Unit
    ) : StageType()

    data class BatchSink<K, V>(
        val name: String,
        val maxBatchSize: Int = 100,
        val maxWaitMs: Long = 5000,
        val consume: (List<Record<K, V>>) -> Unit
    ) : StageType()
}

// ============================================================================
// Section 16: Stage Configuration
// ============================================================================

data class StageConfig(
    val parallelism: Int = 1,
    val channelCapacity: Int = 1000,
    val retryPolicy: RetryPolicy = RetryPolicy.NoRetry,
    val circuitBreaker: CircuitBreakerConfig? = null,
    val enableMetrics: Boolean = true,
    val timeoutMs: Long = 30_000,
    val errorHandler: ErrorHandler = ErrorHandler.DEFAULT
)

data class CircuitBreakerConfig(
    val failureThreshold: Int = 5,
    val resetTimeoutMs: Long = 30_000,
    val halfOpenMaxCalls: Int = 3
)

sealed class ErrorHandler {
    object DEFAULT : ErrorHandler()
    object SKIP : ErrorHandler()
    object FAIL_FAST : ErrorHandler()
    data class DeadLetter(val queueName: String) : ErrorHandler()
    data class Fallback<T>(val fallbackValue: T) : ErrorHandler()
    data class Custom(val handler: (Record<*, *>, PipelineError) -> ErrorAction) : ErrorHandler()
}

enum class ErrorAction {
    SKIP, RETRY, FAIL, DEAD_LETTER
}

// ============================================================================
// Section 17: Stage Wrapper
// ============================================================================

class Stage<KIn, VIn, KOut, VOut>(
    val name: String,
    val config: StageConfig,
    private val processor: (Record<KIn, VIn>) -> List<Record<KOut, VOut>>,
    val metrics: StageMetrics = StageMetrics(name)
) {
    private val circuitBreaker: CircuitBreaker? = config.circuitBreaker?.let {
        CircuitBreaker(name, it.failureThreshold, it.resetTimeoutMs, it.halfOpenMaxCalls)
    }
    private val retryExecutor = RetryExecutor(config.retryPolicy)

    @Suppress("UNCHECKED_CAST")
    fun process(record: Record<KIn, VIn>): Result<List<Record<KOut, VOut>>> {
        metrics.recordInput()
        val startTime = System.nanoTime()

        try {
            val result = if (circuitBreaker != null) {
                circuitBreaker.execute {
                    retryExecutor.execute { processor(record) }.result.getOrThrow()
                }
            } else {
                retryExecutor.execute { processor(record) }.result
            }

            val elapsed = System.nanoTime() - startTime
            metrics.latency.record(elapsed)

            return when (result) {
                is Result.Ok -> {
                    result.value.forEach { _ -> metrics.recordOutput() }
                    result
                }
                is Result.Err -> {
                    metrics.recordError()
                    result
                }
            }
        } catch (e: PipelineException) {
            metrics.recordError()
            val elapsed = System.nanoTime() - startTime
            metrics.latency.record(elapsed)
            return Result.Err(e.error)
        } catch (e: Exception) {
            metrics.recordError()
            val elapsed = System.nanoTime() - startTime
            metrics.latency.record(elapsed)
            return Result.Err(PipelineError.StageError(name, e.message ?: "Unknown error", e))
        }
    }

    fun getCircuitBreakerState(): CircuitBreaker.State? = circuitBreaker?.getState()
    fun resetCircuitBreaker() { circuitBreaker?.reset() }
}

// ============================================================================
// Section 18: Pipeline Builder DSL
// ============================================================================

class PipelineBuilder<K, V>(private val pipelineName: String) {
    private val stages = mutableListOf<StageEntry>()
    private var defaultConfig = StageConfig()
    private val deadLetterQueues = mutableMapOf<String, DeadLetterQueue<Any?, Any?>>()
    private var watermarkTracker: WatermarkTracker? = null
    private val stateStores = mutableMapOf<String, StateStore<*, *>>()

    private data class StageEntry(
        val name: String,
        val stage: Stage<*, *, *, *>,
        val config: StageConfig
    )

    fun withDefaults(config: StageConfig): PipelineBuilder<K, V> {
        defaultConfig = config
        return this
    }

    fun withWatermark(
        allowedLatenessMs: Long = 0,
        idleTimeoutMs: Long = 60_000
    ): PipelineBuilder<K, V> {
        watermarkTracker = WatermarkTracker(allowedLatenessMs, idleTimeoutMs)
        return this
    }

    fun <KOut, VOut> map(
        name: String,
        config: StageConfig = defaultConfig,
        transform: (Record<K, V>) -> Record<KOut, VOut>?
    ): PipelineBuilder<KOut, VOut> {
        val stage = Stage<K, V, KOut, VOut>(name, config, { record ->
            val result = transform(record)
            if (result != null) listOf(result) else emptyList()
        })
        stages.add(StageEntry(name, stage, config))
        @Suppress("UNCHECKED_CAST")
        return this as PipelineBuilder<KOut, VOut>
    }

    fun <KOut, VOut> flatMap(
        name: String,
        config: StageConfig = defaultConfig,
        transform: (Record<K, V>) -> List<Record<KOut, VOut>>
    ): PipelineBuilder<KOut, VOut> {
        val stage = Stage<K, V, KOut, VOut>(name, config, transform)
        stages.add(StageEntry(name, stage, config))
        @Suppress("UNCHECKED_CAST")
        return this as PipelineBuilder<KOut, VOut>
    }

    fun filter(
        name: String,
        config: StageConfig = defaultConfig,
        predicate: (Record<K, V>) -> Boolean
    ): PipelineBuilder<K, V> {
        val stage = Stage<K, V, K, V>(name, config, { record ->
            if (predicate(record)) listOf(record) else emptyList()
        })
        stages.add(StageEntry(name, stage, config))
        return this
    }

    fun <S> stateful(
        name: String,
        storeName: String,
        initialState: S,
        config: StageConfig = defaultConfig,
        transform: (Record<K, V>, StateStore<String, S>) -> Record<K, V>?
    ): PipelineBuilder<K, V> {
        @Suppress("UNCHECKED_CAST")
        val store = stateStores.getOrPut(storeName) {
            StateStore<String, S>(storeName)
        } as StateStore<String, S>

        val stage = Stage<K, V, K, V>(name, config, { record ->
            val result = transform(record, store)
            if (result != null) listOf(result) else emptyList()
        })
        stages.add(StageEntry(name, stage, config))
        return this
    }

    fun <KOut, VOut> windowed(
        name: String,
        windowType: WindowType,
        config: StageConfig = defaultConfig,
        aggregate: (WindowedRecord<K, V>) -> Record<KOut, VOut>?
    ): PipelineBuilder<KOut, VOut> {
        val assigner = WindowAssigner<K, V>(windowType)
        val stage = Stage<K, V, KOut, VOut>(name, config, { record ->
            val closedWindows = assigner.assign(record)
            closedWindows.mapNotNull { aggregate(it) }
        })
        stages.add(StageEntry(name, stage, config))
        @Suppress("UNCHECKED_CAST")
        return this as PipelineBuilder<KOut, VOut>
    }

    fun sink(
        name: String,
        config: StageConfig = defaultConfig,
        consume: (Record<K, V>) -> Unit
    ): Pipeline {
        val stage = Stage<K, V, K, V>(name, config, { record ->
            consume(record)
            emptyList()
        })
        stages.add(StageEntry(name, stage, config))

        return Pipeline(
            pipelineName,
            stages.toList(),
            deadLetterQueues,
            watermarkTracker,
            stateStores
        )
    }

    fun batchSink(
        name: String,
        maxBatchSize: Int = 100,
        maxWaitMs: Long = 5000,
        config: StageConfig = defaultConfig,
        consume: (List<Record<K, V>>) -> Unit
    ): Pipeline {
        val accumulator = BatchAccumulator<K, V>(maxBatchSize, maxWaitMs)
        val stage = Stage<K, V, K, V>(name, config, { record ->
            val batch = accumulator.add(record)
            if (batch != null) {
                @Suppress("UNCHECKED_CAST")
                consume(batch.records)
            }
            emptyList()
        })
        stages.add(StageEntry(name, stage, config))

        return Pipeline(
            pipelineName,
            stages.toList(),
            deadLetterQueues,
            watermarkTracker,
            stateStores
        )
    }

    fun withDeadLetterQueue(
        name: String,
        maxSize: Int = 10_000
    ): PipelineBuilder<K, V> {
        @Suppress("UNCHECKED_CAST")
        deadLetterQueues[name] = DeadLetterQueue<Any?, Any?>(maxSize)
        return this
    }
}

// ============================================================================
// Section 19: Pipeline Execution Engine
// ============================================================================

class Pipeline internal constructor(
    val name: String,
    private val stages: List<PipelineBuilder.StageEntry>,
    private val deadLetterQueues: Map<String, DeadLetterQueue<Any?, Any?>>,
    private val watermarkTracker: WatermarkTracker?,
    private val stateStores: Map<String, StateStore<*, *>>
) {
    // StageEntry is internal to PipelineBuilder, re-reference via reflection-free approach
    private val metrics = PipelineMetrics(name)
    private val running = AtomicBoolean(false)
    private val processedCount = AtomicLong(0)
    private val errorCount = AtomicLong(0)

    @Suppress("UNCHECKED_CAST")
    fun <K, V> process(record: Record<K, V>): Result<Unit> {
        metrics.recordPipelineInput()

        // Track watermark if configured
        watermarkTracker?.let { tracker ->
            val timeliness = tracker.advance(record.timestamp, record.partition)
            if (timeliness == WatermarkTracker.EventTimeliness.DROPPED) {
                return Result.Err(PipelineError.TimeoutError(0))
            }
        }

        var current: List<Any?> = listOf(record)

        for (entry in stages) {
            val stage = entry.stage as Stage<Any?, Any?, Any?, Any?>
            val nextRecords = mutableListOf<Any?>()

            for (item in current) {
                val rec = item as Record<Any?, Any?>
                val result = stage.process(rec)

                when (result) {
                    is Result.Ok -> nextRecords.addAll(result.value)
                    is Result.Err -> {
                        errorCount.incrementAndGet()
                        handleStageError(entry.name, rec, result.error, entry.config)
                        // Unless FAIL_FAST, continue with remaining records
                        if (entry.config.errorHandler is ErrorHandler.FAIL_FAST) {
                            return Result.Err(result.error)
                        }
                    }
                }
            }

            current = nextRecords
        }

        processedCount.incrementAndGet()
        metrics.recordPipelineOutput()
        return Result.Ok(Unit)
    }

    @Suppress("UNCHECKED_CAST")
    fun <K, V> processBatch(records: List<Record<K, V>>): BatchResult {
        val successes = AtomicLong(0)
        val failures = AtomicLong(0)
        val errors = mutableListOf<Pair<Record<K, V>, PipelineError>>()

        for (record in records) {
            val result = process(record)
            when (result) {
                is Result.Ok -> successes.incrementAndGet()
                is Result.Err -> {
                    failures.incrementAndGet()
                    errors.add(record to result.error)
                }
            }
        }

        return BatchResult(
            total = records.size,
            successes = successes.get(),
            failures = failures.get(),
            errors = errors.map { (record, error) ->
                BatchError(record.toString(), error.message)
            }
        )
    }

    @Suppress("UNCHECKED_CAST")
    private fun handleStageError(
        stageName: String,
        record: Record<Any?, Any?>,
        error: PipelineError,
        config: StageConfig
    ) {
        when (config.errorHandler) {
            is ErrorHandler.DEFAULT, is ErrorHandler.SKIP -> { /* skip */ }
            is ErrorHandler.FAIL_FAST -> throw PipelineException(error)
            is ErrorHandler.DeadLetter -> {
                val queueName = (config.errorHandler as ErrorHandler.DeadLetter).queueName
                val dlq = deadLetterQueues[queueName]
                dlq?.enqueue(DeadLetter(record, error, stageName))
            }
            is ErrorHandler.Fallback<*> -> { /* handled at stage level */ }
            is ErrorHandler.Custom -> {
                val handler = (config.errorHandler as ErrorHandler.Custom).handler
                val action = handler(record, error)
                when (action) {
                    ErrorAction.FAIL -> throw PipelineException(error)
                    ErrorAction.DEAD_LETTER -> {
                        deadLetterQueues.values.firstOrNull()?.enqueue(
                            DeadLetter(record, error, stageName)
                        )
                    }
                    else -> { /* SKIP or RETRY handled elsewhere */ }
                }
            }
        }
    }

    fun getMetrics(): PipelineMetrics = metrics
    fun getProcessedCount(): Long = processedCount.get()
    fun getErrorCount(): Long = errorCount.get()
    fun getWatermarkTracker(): WatermarkTracker? = watermarkTracker

    fun getStateStore(name: String): StateStore<*, *>? = stateStores[name]

    fun getDeadLetterQueue(name: String): DeadLetterQueue<Any?, Any?>? = deadLetterQueues[name]

    data class BatchResult(
        val total: Int,
        val successes: Long,
        val failures: Long,
        val errors: List<BatchError>
    )

    data class BatchError(
        val record: String,
        val error: String
    )

    companion object {
        fun <K, V> builder(name: String): PipelineBuilder<K, V> = PipelineBuilder(name)
    }
}

// ============================================================================
// Section 20: Parallel Executor (Coroutine-like patterns without kotlinx)
// ============================================================================

class ParallelExecutor(
    private val parallelism: Int = Runtime.getRuntime().availableProcessors(),
    private val channelCapacity: Int = 1000
) {
    private val taskQueue = BoundedChannel<() -> Unit>(channelCapacity)
    private val workers = mutableListOf<Thread>()
    private val running = AtomicBoolean(false)
    private val completedTasks = AtomicLong(0)
    private val failedTasks = AtomicLong(0)

    fun start() {
        if (running.compareAndSet(false, true)) {
            for (i in 0 until parallelism) {
                val worker = Thread({
                    while (running.get() || !taskQueue.isEmpty) {
                        val result = taskQueue.receiveBlocking(100)
                        when (result) {
                            is BoundedChannel.ReceiveResult.Value -> {
                                try {
                                    result.value()
                                    completedTasks.incrementAndGet()
                                } catch (_: Exception) {
                                    failedTasks.incrementAndGet()
                                }
                            }
                            is BoundedChannel.ReceiveResult.Empty -> { /* spin */ }
                            is BoundedChannel.ReceiveResult.Closed -> return@Thread
                        }
                    }
                }, "pipeline-worker-$i")
                worker.isDaemon = true
                worker.start()
                workers.add(worker)
            }
        }
    }

    fun submit(task: () -> Unit): Boolean {
        if (!running.get()) return false
        return taskQueue.trySend(task) == BoundedChannel.SendResult.Sent
    }

    fun submitBlocking(task: () -> Unit, timeoutMs: Long = 5000): Boolean {
        if (!running.get()) return false
        return taskQueue.sendBlocking(task, timeoutMs) == BoundedChannel.SendResult.Sent
    }

    fun <T> submitWithResult(task: () -> T): Future<T> {
        val future = Future<T>()
        submit {
            try {
                future.complete(task())
            } catch (e: Exception) {
                future.completeExceptionally(e)
            }
        }
        return future
    }

    fun shutdown(waitMs: Long = 5000) {
        running.set(false)
        taskQueue.close()
        val deadline = System.currentTimeMillis() + waitMs
        for (worker in workers) {
            val remaining = deadline - System.currentTimeMillis()
            if (remaining > 0) {
                worker.join(remaining)
            }
        }
        workers.clear()
    }

    fun isRunning(): Boolean = running.get()
    fun completedTasks(): Long = completedTasks.get()
    fun failedTasks(): Long = failedTasks.get()
    fun pendingTasks(): Int = taskQueue.size

    class Future<T> {
        private val result = AtomicReference<Result<T>?>(null)
        private val latch = java.util.concurrent.CountDownLatch(1)

        fun complete(value: T) {
            result.set(Result.Ok(value))
            latch.countDown()
        }

        fun completeExceptionally(e: Exception) {
            result.set(Result.Err(PipelineError.StageError("future", e.message ?: "Unknown", e)))
            latch.countDown()
        }

        fun get(timeoutMs: Long = 30_000): Result<T> {
            if (!latch.await(timeoutMs, java.util.concurrent.TimeUnit.MILLISECONDS)) {
                return Result.Err(PipelineError.TimeoutError(timeoutMs))
            }
            return result.get()!!
        }

        fun isDone(): Boolean = latch.count == 0L
    }
}

// ============================================================================
// Section 21: Fan-Out / Fan-In Patterns
// ============================================================================

class FanOut<K, V>(
    private val parallelism: Int,
    private val channelCapacity: Int = 1000,
    private val partitioner: (Record<K, V>) -> Int = { it.key.hashCode() }
) {
    private val channels = (0 until parallelism).map { BoundedChannel<Record<K, V>>(channelCapacity) }

    fun dispatch(record: Record<K, V>): BoundedChannel.SendResult {
        val partition = Math.floorMod(partitioner(record), parallelism)
        return channels[partition].trySend(record)
    }

    fun getChannel(partition: Int): BoundedChannel<Record<K, V>> = channels[partition]

    fun closeAll() {
        channels.forEach { it.close() }
    }

    fun totalPending(): Int = channels.sumOf { it.size }
}

class FanIn<K, V>(private val channelCapacity: Int = 1000) {
    private val output = BoundedChannel<Record<K, V>>(channelCapacity)
    private val inputCount = AtomicLong(0)
    private val outputCount = AtomicLong(0)

    fun submit(record: Record<K, V>): BoundedChannel.SendResult {
        inputCount.incrementAndGet()
        return output.trySend(record)
    }

    fun receive(timeoutMs: Long = 1000): BoundedChannel.ReceiveResult<Record<K, V>> {
        val result = output.receiveBlocking(timeoutMs)
        if (result is BoundedChannel.ReceiveResult.Value) {
            outputCount.incrementAndGet()
        }
        return result
    }

    fun close() { output.close() }

    fun stats(): Map<String, Long> = mapOf(
        "inputCount" to inputCount.get(),
        "outputCount" to outputCount.get(),
        "pending" to output.size.toLong()
    )
}

// ============================================================================
// Section 22: Rate Limiter
// ============================================================================

class RateLimiter(
    private val maxPerSecond: Double,
    private val burstSize: Int = 1
) {
    private val tokenBucket = AtomicLong(burstSize.toLong())
    private val lastRefillTime = AtomicLong(System.nanoTime())
    private val intervalNanos = (1_000_000_000.0 / maxPerSecond).toLong()
    private val acquiredCount = AtomicLong(0)
    private val rejectedCount = AtomicLong(0)

    fun tryAcquire(): Boolean {
        refill()
        val current = tokenBucket.get()
        if (current > 0 && tokenBucket.compareAndSet(current, current - 1)) {
            acquiredCount.incrementAndGet()
            return true
        }
        rejectedCount.incrementAndGet()
        return false
    }

    fun acquireBlocking(timeoutMs: Long = 5000): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            if (tryAcquire()) return true
            Thread.sleep(1)
        }
        return false
    }

    private fun refill() {
        val now = System.nanoTime()
        val last = lastRefillTime.get()
        val elapsed = now - last
        val tokensToAdd = elapsed / intervalNanos

        if (tokensToAdd > 0 && lastRefillTime.compareAndSet(last, last + tokensToAdd * intervalNanos)) {
            val newTokens = min(tokenBucket.get() + tokensToAdd, burstSize.toLong())
            tokenBucket.set(newTokens)
        }
    }

    fun stats(): Map<String, Any> = mapOf(
        "acquired" to acquiredCount.get(),
        "rejected" to rejectedCount.get(),
        "currentTokens" to tokenBucket.get(),
        "maxPerSecond" to maxPerSecond
    )
}

// ============================================================================
// Section 23: Health Check and Lifecycle
// ============================================================================

enum class HealthStatus {
    HEALTHY, DEGRADED, UNHEALTHY, UNKNOWN
}

data class HealthReport(
    val status: HealthStatus,
    val components: Map<String, ComponentHealth>,
    val timestamp: Long = System.currentTimeMillis()
) {
    data class ComponentHealth(
        val name: String,
        val status: HealthStatus,
        val details: Map<String, Any> = emptyMap(),
        val lastChecked: Long = System.currentTimeMillis()
    )
}

class HealthChecker(private val pipeline: Pipeline) {
    private val checks = mutableListOf<NamedCheck>()

    private data class NamedCheck(
        val name: String,
        val check: () -> HealthReport.ComponentHealth
    )

    fun addCheck(name: String, check: () -> HealthReport.ComponentHealth): HealthChecker {
        checks.add(NamedCheck(name, check))
        return this
    }

    fun check(): HealthReport {
        val components = mutableMapOf<String, HealthReport.ComponentHealth>()

        for (namedCheck in checks) {
            val health = try {
                namedCheck.check()
            } catch (e: Exception) {
                HealthReport.ComponentHealth(
                    namedCheck.name,
                    HealthStatus.UNHEALTHY,
                    mapOf("error" to (e.message ?: "Unknown"))
                )
            }
            components[namedCheck.name] = health
        }

        // Add pipeline metrics check
        val metrics = pipeline.getMetrics()
        val errorRate = metrics.overallErrorRate()
        val pipelineStatus = when {
            errorRate > 0.5 -> HealthStatus.UNHEALTHY
            errorRate > 0.1 -> HealthStatus.DEGRADED
            else -> HealthStatus.HEALTHY
        }
        components["pipeline"] = HealthReport.ComponentHealth(
            "pipeline",
            pipelineStatus,
            mapOf(
                "errorRate" to errorRate,
                "throughput" to metrics.overallThroughput(),
                "processedCount" to pipeline.getProcessedCount()
            )
        )

        val overallStatus = when {
            components.values.any { it.status == HealthStatus.UNHEALTHY } -> HealthStatus.UNHEALTHY
            components.values.any { it.status == HealthStatus.DEGRADED } -> HealthStatus.DEGRADED
            components.values.all { it.status == HealthStatus.HEALTHY } -> HealthStatus.HEALTHY
            else -> HealthStatus.UNKNOWN
        }

        return HealthReport(overallStatus, components)
    }
}

// ============================================================================
// Section 24: Topology Descriptor
// ============================================================================

data class Topology(
    val name: String,
    val stages: List<TopologyStage>,
    val edges: List<TopologyEdge>
) {
    data class TopologyStage(
        val name: String,
        val type: String,
        val parallelism: Int,
        val config: Map<String, Any>
    )

    data class TopologyEdge(
        val from: String,
        val to: String,
        val channelCapacity: Int
    )

    fun describe(): String {
        val sb = StringBuilder()
        sb.appendLine("Topology: $name")
        sb.appendLine("Stages:")
        for (stage in stages) {
            sb.appendLine("  ${stage.name} (${stage.type}, parallelism=${stage.parallelism})")
        }
        sb.appendLine("Edges:")
        for (edge in edges) {
            sb.appendLine("  ${edge.from} -> ${edge.to} (capacity=${edge.channelCapacity})")
        }
        return sb.toString()
    }

    fun validate(): Result<Unit> {
        val stageNames = stages.map { it.name }.toSet()

        for (edge in edges) {
            if (edge.from !in stageNames) {
                return Result.Err(PipelineError.StageError(edge.from, "Source stage not found in topology"))
            }
            if (edge.to !in stageNames) {
                return Result.Err(PipelineError.StageError(edge.to, "Target stage not found in topology"))
            }
        }

        // Check for cycles using DFS
        val adjacency = edges.groupBy { it.from }.mapValues { it.value.map { e -> e.to } }
        val visited = mutableSetOf<String>()
        val recursionStack = mutableSetOf<String>()

        fun hasCycle(node: String): Boolean {
            visited.add(node)
            recursionStack.add(node)
            for (neighbor in adjacency[node] ?: emptyList()) {
                if (neighbor !in visited && hasCycle(neighbor)) return true
                if (neighbor in recursionStack) return true
            }
            recursionStack.remove(node)
            return false
        }

        for (stage in stageNames) {
            if (stage !in visited && hasCycle(stage)) {
                return Result.Err(PipelineError.StageError(stage, "Cycle detected in topology"))
            }
        }

        return Result.Ok(Unit)
    }
}

// ============================================================================
// Section 25: Checkpoint and Recovery
// ============================================================================

data class Checkpoint(
    val pipelineName: String,
    val stageOffsets: Map<String, Long>,
    val stateSnapshots: Map<String, Map<String, Any?>>,
    val watermark: Long,
    val timestamp: Long = System.currentTimeMillis(),
    val id: String = UUID.randomUUID().toString()
)

class CheckpointManager(
    private val pipeline: Pipeline,
    private val maxCheckpoints: Int = 10
) {
    private val checkpoints = LinkedList<Checkpoint>()
    private val lock = ReentrantReadWriteLock()
    private val checkpointCount = AtomicLong(0)

    fun createCheckpoint(): Checkpoint {
        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            val stateSnapshots = mutableMapOf<String, Map<String, Any?>>()
            // Capture state store snapshots would go here in production

            val checkpoint = Checkpoint(
                pipelineName = pipeline.name,
                stageOffsets = emptyMap(), // populated from actual offsets in production
                stateSnapshots = stateSnapshots,
                watermark = pipeline.getWatermarkTracker()?.currentWatermark() ?: Long.MIN_VALUE
            )

            checkpoints.addLast(checkpoint)
            if (checkpoints.size > maxCheckpoints) {
                checkpoints.removeFirst()
            }
            checkpointCount.incrementAndGet()

            return checkpoint
        } finally {
            writeLock.unlock()
        }
    }

    fun latestCheckpoint(): Checkpoint? {
        val readLock = lock.readLock()
        readLock.lock()
        try {
            return checkpoints.lastOrNull()
        } finally {
            readLock.unlock()
        }
    }

    fun getCheckpoint(id: String): Checkpoint? {
        val readLock = lock.readLock()
        readLock.lock()
        try {
            return checkpoints.find { it.id == id }
        } finally {
            readLock.unlock()
        }
    }

    fun checkpointCount(): Long = checkpointCount.get()

    fun purgeOlderThan(timestamp: Long): Int {
        val writeLock = lock.writeLock()
        writeLock.lock()
        try {
            val before = checkpoints.size
            checkpoints.removeAll { it.timestamp < timestamp }
            return before - checkpoints.size
        } finally {
            writeLock.unlock()
        }
    }
}

// ============================================================================
// Section 26: Predefined Transforms
// ============================================================================

object Transforms {
    fun <K> passthrough(): (Record<K, Any?>) -> Record<K, Any?> = { it }

    fun <K, V> logRecord(prefix: String = ""): (Record<K, V>) -> Record<K, V> = { record ->
        println("${prefix}[${record.timestamp}] key=${record.key} value=${record.value}")
        record
    }

    fun <K> addTimestamp(): (Record<K, Any?>) -> Record<K, Any?> = { record ->
        record.withHeader("_processedAt", System.currentTimeMillis().toString())
    }

    fun <K> tagPartition(partitions: Int): (Record<K, Any?>) -> Record<K, Any?> = { record ->
        val partition = Math.floorMod(record.key.hashCode(), partitions)
        record.copy(partition = partition)
    }

    @Suppress("UNCHECKED_CAST")
    fun <K> enrichFromMap(
        lookup: Map<String, Any?>,
        keyExtractor: (Record<K, Map<String, Any?>>) -> String,
        fieldName: String
    ): (Record<K, Map<String, Any?>>) -> Record<K, Map<String, Any?>> = { record ->
        val lookupKey = keyExtractor(record)
        val enrichment = lookup[lookupKey]
        if (enrichment != null) {
            record.mapValue { it + (fieldName to enrichment) }
        } else {
            record
        }
    }

    fun <K, V> deduplicate(
        windowMs: Long = 60_000,
        keyFn: (Record<K, V>) -> String
    ): (Record<K, V>) -> Record<K, V>? {
        val seen = ConcurrentHashMap<String, Long>()

        return { record ->
            val dedupeKey = keyFn(record)
            val now = System.currentTimeMillis()

            // Evict old entries
            seen.entries.removeIf { now - it.value > windowMs }

            val existing = seen.putIfAbsent(dedupeKey, now)
            if (existing == null) record else null
        }
    }

    @Suppress("UNCHECKED_CAST")
    fun <K> projectFields(
        vararg fields: String
    ): (Record<K, Map<String, Any?>>) -> Record<K, Map<String, Any?>> = { record ->
        record.mapValue { map -> map.filterKeys { it in fields } }
    }

    @Suppress("UNCHECKED_CAST")
    fun <K> renameFields(
        vararg mappings: Pair<String, String>
    ): (Record<K, Map<String, Any?>>) -> Record<K, Map<String, Any?>> = { record ->
        val renameMap = mappings.toMap()
        record.mapValue { map ->
            map.entries.associate { (k, v) ->
                (renameMap[k] ?: k) to v
            }
        }
    }

    fun <K> filterByQuery(
        query: Query,
        executor: QueryExecutor = QueryExecutor()
    ): (Record<K, Map<String, Any?>>) -> Boolean = { record ->
        val result = executor.execute(query, listOf(record.value))
        when (result) {
            is Result.Ok -> result.value.isNotEmpty()
            is Result.Err -> false
        }
    }
}

// ============================================================================
// Section 27: Aggregation Functions
// ============================================================================

sealed class AggregateState<T> {
    abstract fun add(value: T): AggregateState<T>
    abstract fun result(): Any?
    abstract fun merge(other: AggregateState<T>): AggregateState<T>

    class Count<T> : AggregateState<T>() {
        private var count = 0L
        override fun add(value: T): Count<T> { count++; return this }
        override fun result(): Long = count
        override fun merge(other: AggregateState<T>): Count<T> {
            count += (other as Count).count; return this
        }
    }

    class Sum : AggregateState<Number>() {
        private var sum = 0.0
        override fun add(value: Number): Sum { sum += value.toDouble(); return this }
        override fun result(): Double = sum
        override fun merge(other: AggregateState<Number>): Sum {
            sum += (other as Sum).sum; return this
        }
    }

    class Average : AggregateState<Number>() {
        private var sum = 0.0
        private var count = 0L
        override fun add(value: Number): Average {
            sum += value.toDouble(); count++; return this
        }
        override fun result(): Double = if (count > 0) sum / count else 0.0
        override fun merge(other: AggregateState<Number>): Average {
            val o = other as Average
            sum += o.sum; count += o.count; return this
        }
    }

    class Min : AggregateState<Comparable<Any>>() {
        private var min: Comparable<Any>? = null
        @Suppress("UNCHECKED_CAST")
        override fun add(value: Comparable<Any>): Min {
            if (min == null || value < min!!) min = value; return this
        }
        override fun result(): Comparable<Any>? = min
        @Suppress("UNCHECKED_CAST")
        override fun merge(other: AggregateState<Comparable<Any>>): Min {
            val o = other as Min
            if (o.min != null && (min == null || o.min!! < min!!)) min = o.min
            return this
        }
    }

    class Max : AggregateState<Comparable<Any>>() {
        private var max: Comparable<Any>? = null
        @Suppress("UNCHECKED_CAST")
        override fun add(value: Comparable<Any>): Max {
            if (max == null || value > max!!) max = value; return this
        }
        override fun result(): Comparable<Any>? = max
        @Suppress("UNCHECKED_CAST")
        override fun merge(other: AggregateState<Comparable<Any>>): Max {
            val o = other as Max
            if (o.max != null && (max == null || o.max!! > max!!)) max = o.max
            return this
        }
    }

    class CollectList<T> : AggregateState<T>() {
        private val items = mutableListOf<T>()
        override fun add(value: T): CollectList<T> { items.add(value); return this }
        override fun result(): List<T> = items.toList()
        override fun merge(other: AggregateState<T>): CollectList<T> {
            items.addAll((other as CollectList).items); return this
        }
    }

    class CollectSet<T> : AggregateState<T>() {
        private val items = mutableSetOf<T>()
        override fun add(value: T): CollectSet<T> { items.add(value); return this }
        override fun result(): Set<T> = items.toSet()
        override fun merge(other: AggregateState<T>): CollectSet<T> {
            items.addAll((other as CollectSet).items); return this
        }
    }
}

// ============================================================================
// Section 28: Event Time Processor
// ============================================================================

class EventTimeProcessor<K, V>(
    private val watermarkTracker: WatermarkTracker,
    private val windowAssigner: WindowAssigner<K, V>,
    private val allowLateEvents: Boolean = true
) {
    private val lateEventBuffer = ConcurrentLinkedQueue<Record<K, V>>()
    private val maxLateBufferSize = 10_000
    private val processedWindows = AtomicLong(0)
    private val processedRecords = AtomicLong(0)

    data class ProcessingResult<K, V>(
        val closedWindows: List<WindowedRecord<K, V>>,
        val lateEvents: List<Record<K, V>>,
        val droppedEvents: List<Record<K, V>>
    )

    fun process(record: Record<K, V>): ProcessingResult<K, V> {
        processedRecords.incrementAndGet()
        val timeliness = watermarkTracker.advance(record.timestamp, record.partition)

        return when (timeliness) {
            WatermarkTracker.EventTimeliness.ON_TIME -> {
                val closedWindows = windowAssigner.assign(record)
                processedWindows.addAndGet(closedWindows.size.toLong())
                ProcessingResult(closedWindows, emptyList(), emptyList())
            }
            WatermarkTracker.EventTimeliness.LATE_BUT_ALLOWED -> {
                if (allowLateEvents) {
                    if (lateEventBuffer.size < maxLateBufferSize) {
                        lateEventBuffer.offer(record)
                    }
                    val closedWindows = windowAssigner.assign(record)
                    ProcessingResult(closedWindows, listOf(record), emptyList())
                } else {
                    ProcessingResult(emptyList(), emptyList(), listOf(record))
                }
            }
            WatermarkTracker.EventTimeliness.DROPPED -> {
                ProcessingResult(emptyList(), emptyList(), listOf(record))
            }
        }
    }

    fun flushWindows(): List<WindowedRecord<K, V>> {
        val flushed = windowAssigner.flush()
        processedWindows.addAndGet(flushed.size.toLong())
        return flushed
    }

    fun drainLateEvents(): List<Record<K, V>> {
        val events = mutableListOf<Record<K, V>>()
        while (true) {
            events.add(lateEventBuffer.poll() ?: break)
        }
        return events
    }

    fun stats(): Map<String, Any> = mapOf(
        "processedRecords" to processedRecords.get(),
        "processedWindows" to processedWindows.get(),
        "lateBufferSize" to lateEventBuffer.size,
        "watermark" to watermarkTracker.currentWatermark()
    )
}

// ============================================================================
// Section 29: Pipeline Configuration DSL
// ============================================================================

class PipelineConfig private constructor(
    val name: String,
    val defaultParallelism: Int,
    val defaultChannelCapacity: Int,
    val defaultRetryPolicy: RetryPolicy,
    val metricsEnabled: Boolean,
    val checkpointIntervalMs: Long,
    val maxInFlightRecords: Int,
    val shutdownTimeoutMs: Long,
    val rateLimitPerSecond: Double?,
    val properties: Map<String, String>
) {
    class Builder(private val name: String) {
        private var defaultParallelism: Int = 1
        private var defaultChannelCapacity: Int = 1000
        private var defaultRetryPolicy: RetryPolicy = RetryPolicy.NoRetry
        private var metricsEnabled: Boolean = true
        private var checkpointIntervalMs: Long = 60_000
        private var maxInFlightRecords: Int = 10_000
        private var shutdownTimeoutMs: Long = 30_000
        private var rateLimitPerSecond: Double? = null
        private var properties: MutableMap<String, String> = mutableMapOf()

        fun parallelism(p: Int) = apply { defaultParallelism = p }
        fun channelCapacity(c: Int) = apply { defaultChannelCapacity = c }
        fun retry(policy: RetryPolicy) = apply { defaultRetryPolicy = policy }
        fun enableMetrics(enabled: Boolean) = apply { metricsEnabled = enabled }
        fun checkpointInterval(ms: Long) = apply { checkpointIntervalMs = ms }
        fun maxInFlight(max: Int) = apply { maxInFlightRecords = max }
        fun shutdownTimeout(ms: Long) = apply { shutdownTimeoutMs = ms }
        fun rateLimit(perSecond: Double) = apply { rateLimitPerSecond = perSecond }
        fun property(key: String, value: String) = apply { properties[key] = value }

        fun build(): PipelineConfig = PipelineConfig(
            name, defaultParallelism, defaultChannelCapacity, defaultRetryPolicy,
            metricsEnabled, checkpointIntervalMs, maxInFlightRecords, shutdownTimeoutMs,
            rateLimitPerSecond, properties.toMap()
        )
    }

    companion object {
        fun builder(name: String): Builder = Builder(name)
    }
}

// ============================================================================
// Section 30: Utility Extensions and Helpers
// ============================================================================

fun <K, V> Record<K, V>.toMap(): Map<String, Any?> = mapOf(
    "key" to key,
    "value" to value,
    "timestamp" to timestamp,
    "partition" to partition,
    "offset" to offset,
    "headers" to headers
)

fun <K, V> List<Record<K, V>>.totalSize(): Int = size

fun <K, V> List<Record<K, V>>.timeRange(): Pair<Long, Long> {
    if (isEmpty()) return 0L to 0L
    return minOf { it.timestamp } to maxOf { it.timestamp }
}

fun <K, V> List<Record<K, V>>.partitionBy(partitions: Int): Map<Int, List<Record<K, V>>> {
    return groupBy { Math.floorMod(it.key.hashCode(), partitions) }
}

fun <K, V> List<Record<K, V>>.sortByTimestamp(): List<Record<K, V>> =
    sortedBy { it.timestamp }

fun <K, V> List<Record<K, V>>.filterByTimeRange(start: Long, end: Long): List<Record<K, V>> =
    filter { it.timestamp in start until end }

fun <K, V> List<Record<K, V>>.keySet(): Set<K?> = map { it.key }.toSet()

inline fun <K, V, R> List<Record<K, V>>.mapValues(transform: (V) -> R): List<Record<K, R>> =
    map { it.mapValue(transform) }

fun Map<String, Any?>.getStringOrDefault(key: String, default: String): String =
    (this[key] as? String) ?: default

fun Map<String, Any?>.getIntOrDefault(key: String, default: Int): Int =
    (this[key] as? Number)?.toInt() ?: default

fun Map<String, Any?>.getLongOrDefault(key: String, default: Long): Long =
    (this[key] as? Number)?.toLong() ?: default

fun Map<String, Any?>.getDoubleOrDefault(key: String, default: Double): Double =
    (this[key] as? Number)?.toDouble() ?: default

fun Map<String, Any?>.getBooleanOrDefault(key: String, default: Boolean): Boolean =
    (this[key] as? Boolean) ?: default

@Suppress("UNCHECKED_CAST")
fun Map<String, Any?>.getNestedMap(key: String): Map<String, Any?>? =
    this[key] as? Map<String, Any?>

@Suppress("UNCHECKED_CAST")
fun Map<String, Any?>.getList(key: String): List<Any?>? =
    this[key] as? List<Any?>

// Timing helper
inline fun <T> timed(block: () -> T): Pair<T, Long> {
    val start = System.nanoTime()
    val result = block()
    val elapsed = System.nanoTime() - start
    return result to elapsed
}

// Retry helper
inline fun <T> retryWith(
    maxAttempts: Int = 3,
    delayMs: Long = 100,
    block: (attempt: Int) -> T
): T {
    var lastException: Exception? = null
    for (attempt in 1..maxAttempts) {
        try {
            return block(attempt)
        } catch (e: Exception) {
            lastException = e
            if (attempt < maxAttempts) {
                Thread.sleep(delayMs * attempt)
            }
        }
    }
    throw lastException!!
}

// ============================================================================
// Section 31: Pipeline Introspection and Debugging
// ============================================================================

class PipelineInspector(private val pipeline: Pipeline) {
    fun stageMetrics(): List<Map<String, Any>> {
        val metrics = pipeline.getMetrics()
        return metrics.stageNames().map { name ->
            metrics.getOrCreateStageMetrics(name).toMap()
        }
    }

    fun bottleneck(): String? {
        val metrics = pipeline.getMetrics()
        return metrics.stageNames()
            .map { name -> name to metrics.getOrCreateStageMetrics(name) }
            .maxByOrNull { (_, m) -> m.latency.p99() }
            ?.first
    }

    fun errorHotspot(): String? {
        val metrics = pipeline.getMetrics()
        return metrics.stageNames()
            .map { name -> name to metrics.getOrCreateStageMetrics(name) }
            .maxByOrNull { (_, m) -> m.errorRate() }
            ?.takeIf { (_, m) -> m.errorRate() > 0 }
            ?.first
    }

    fun summary(): Map<String, Any> {
        val metrics = pipeline.getMetrics()
        return mapOf(
            "pipeline" to pipeline.name,
            "processedCount" to pipeline.getProcessedCount(),
            "errorCount" to pipeline.getErrorCount(),
            "overallThroughput" to metrics.overallThroughput(),
            "overallErrorRate" to metrics.overallErrorRate(),
            "bottleneck" to (bottleneck() ?: "none"),
            "errorHotspot" to (errorHotspot() ?: "none"),
            "watermark" to (pipeline.getWatermarkTracker()?.currentWatermark() ?: "N/A")
        )
    }
}

// ============================================================================
// Section 32: Example Usage Patterns
// ============================================================================

/**
 * Example: Building and running a data processing pipeline.
 *
 * ```kotlin
 * // 1. Define schema
 * val registry = SchemaRegistry()
 * val userSchema = Schema(
 *     name = "user_event",
 *     fields = listOf(
 *         Field("userId", FieldType.StringType),
 *         Field("action", FieldType.StringType),
 *         Field("amount", FieldType.DoubleType, defaultValue = 0.0),
 *         Field("timestamp", FieldType.LongType)
 *     )
 * )
 * registry.register(userSchema)
 *
 * // 2. Build pipeline
 * val pipeline = Pipeline.builder<String, Map<String, Any?>>("user-analytics")
 *     .withWatermark(allowedLatenessMs = 5000)
 *     .filter("validate") { record ->
 *         record.value.containsKey("userId")
 *     }
 *     .map("enrich") { record ->
 *         record.mapValue { it + ("processedAt" to System.currentTimeMillis()) }
 *     }
 *     .stateful("count-actions", "action-counts", 0L) { record, store ->
 *         val action = record.value["action"]?.toString() ?: "unknown"
 *         val count = store.compute(action) { _, v -> (v ?: 0L) + 1L }
 *         record.mapValue { it + ("actionCount" to count) }
 *     }
 *     .windowed(
 *         "tumbling-1min",
 *         WindowType.Tumbling(60_000)
 *     ) { windowedRecord ->
 *         val totalAmount = windowedRecord.records
 *             .mapNotNull { (it.value["amount"] as? Number)?.toDouble() }
 *             .sum()
 *         Record(
 *             key = "window-${windowedRecord.window.start}",
 *             value = mapOf(
 *                 "windowStart" to windowedRecord.window.start,
 *                 "windowEnd" to windowedRecord.window.end,
 *                 "count" to windowedRecord.size(),
 *                 "totalAmount" to totalAmount
 *             ),
 *             timestamp = windowedRecord.window.end
 *         )
 *     }
 *     .sink("console") { record ->
 *         println("Output: ${record.value}")
 *     }
 *
 * // 3. Process records
 * pipeline.process(Record(
 *     key = "user-123",
 *     value = mapOf(
 *         "userId" to "user-123",
 *         "action" to "purchase",
 *         "amount" to 42.99,
 *         "timestamp" to System.currentTimeMillis()
 *     )
 * ))
 *
 * // 4. Query with SQL-like DSL
 * val query = QueryBuilder()
 *     .filter(col("action") eq lit("purchase"))
 *     .filter(col("amount") gt lit(10.0))
 *     .selectColumns("userId", "amount")
 *     .orderBy("amount", ascending = false)
 *     .limit(100)
 *     .build()
 *
 * val executor = QueryExecutor()
 * val results = executor.execute(query, data)
 *
 * // 5. Inspect pipeline health
 * val inspector = PipelineInspector(pipeline)
 * println(inspector.summary())
 * ```
 */
object ExamplePatterns {
    fun demonstrateSchemaEvolution(registry: SchemaRegistry) {
        val v1 = Schema(
            name = "order",
            fields = listOf(
                Field("orderId", FieldType.StringType),
                Field("total", FieldType.DoubleType),
                Field("status", FieldType.StringType)
            )
        )
        registry.register(v1)

        // Evolve: add customer field
        registry.evolve("order", SchemaEvolution.AddField(
            Field("customerId", FieldType.StringType, defaultValue = "unknown")
        ))

        // Evolve: rename field
        registry.evolve("order", SchemaEvolution.RenameField("total", "orderTotal"))

        // Evolve: make nullable
        registry.evolve("order", SchemaEvolution.MakeNullable("status"))
    }

    fun demonstrateCircuitBreaker() {
        val breaker = CircuitBreaker(
            name = "external-api",
            failureThreshold = 3,
            resetTimeoutMs = 10_000
        )

        val result = breaker.execute {
            // Simulate API call
            if (Math.random() < 0.3) throw RuntimeException("API timeout")
            mapOf("data" to "response")
        }

        when (result) {
            is Result.Ok -> println("Success: ${result.value}")
            is Result.Err -> println("Error: ${result.error.message}")
        }
    }

    fun demonstrateBatching() {
        val accumulator = BatchAccumulator<String, String>(
            maxBatchSize = 10,
            maxWaitMs = 1000
        )

        for (i in 1..25) {
            val record = Record("key-$i", "value-$i")
            val batch = accumulator.add(record)
            if (batch != null) {
                println("Batch #${batch.batchId}: ${batch.size()} records")
            }
        }

        // Flush remaining
        val remaining = accumulator.flush()
        if (remaining != null) {
            println("Final batch: ${remaining.size()} records")
        }
    }

    fun demonstrateParallelExecution() {
        val executor = ParallelExecutor(parallelism = 4)
        executor.start()

        val futures = (1..100).map { i ->
            executor.submitWithResult {
                Thread.sleep(10) // simulate work
                i * i
            }
        }

        val results = futures.map { it.get(5000) }
        println("Completed: ${results.count { it.isOk }} / ${results.size}")

        executor.shutdown()
    }
}

// ============================================================================
// Section 33: Serialization Format Registry
// ============================================================================

class CodecRegistry {
    private val codecs = ConcurrentHashMap<String, Codec<*>>()

    init {
        register("string", StringCodec())
        register("int", IntCodec())
        register("long", LongCodec())
        register("json", JsonCodec())
    }

    fun <T> register(name: String, codec: Codec<T>) {
        codecs[name] = codec
    }

    @Suppress("UNCHECKED_CAST")
    fun <T> getCodec(name: String): Codec<T>? = codecs[name] as? Codec<T>

    fun listCodecs(): List<String> = codecs.keys().toList()

    fun hasCodec(name: String): Boolean = name in codecs
}

// ============================================================================
// Section 34: Keyed State with Time-To-Live
// ============================================================================

class TTLStateStore<K, V>(
    name: String,
    private val defaultTtlMs: Long = 3_600_000 // 1 hour
) {
    private data class TTLEntry<V>(
        val value: V,
        val expiresAt: Long
    )

    private val store = ConcurrentHashMap<K, TTLEntry<V>>()
    private val evictionCount = AtomicLong(0)

    fun get(key: K): V? {
        val entry = store[key] ?: return null
        if (System.currentTimeMillis() > entry.expiresAt) {
            store.remove(key)
            evictionCount.incrementAndGet()
            return null
        }
        return entry.value
    }

    fun put(key: K, value: V, ttlMs: Long = defaultTtlMs) {
        val expiresAt = System.currentTimeMillis() + ttlMs
        store[key] = TTLEntry(value, expiresAt)
    }

    fun remove(key: K): V? {
        val entry = store.remove(key) ?: return null
        return entry.value
    }

    fun cleanup(): Int {
        val now = System.currentTimeMillis()
        var cleaned = 0
        val iterator = store.entries.iterator()
        while (iterator.hasNext()) {
            val entry = iterator.next()
            if (now > entry.value.expiresAt) {
                iterator.remove()
                cleaned++
                evictionCount.incrementAndGet()
            }
        }
        return cleaned
    }

    fun size(): Int = store.size

    fun evictionCount(): Long = evictionCount.get()

    fun stats(): Map<String, Any> = mapOf(
        "size" to store.size,
        "evictions" to evictionCount.get(),
        "defaultTtlMs" to defaultTtlMs
    )
}

// ============================================================================
// Section 35: Pipeline Testing Utilities
// ============================================================================

class TestHarness<K, V> {
    private val inputRecords = mutableListOf<Record<K, V>>()
    private val outputRecords = mutableListOf<Record<*, *>>()
    private val errors = mutableListOf<Pair<Record<K, V>, PipelineError>>()

    fun input(record: Record<K, V>): TestHarness<K, V> {
        inputRecords.add(record)
        return this
    }

    fun input(key: K, value: V, timestamp: Long = System.currentTimeMillis()): TestHarness<K, V> {
        inputRecords.add(Record(key, value, timestamp))
        return this
    }

    fun inputBatch(records: List<Record<K, V>>): TestHarness<K, V> {
        inputRecords.addAll(records)
        return this
    }

    fun runWith(pipeline: Pipeline): TestResult<K, V> {
        outputRecords.clear()
        errors.clear()

        for (record in inputRecords) {
            val result = pipeline.process(record)
            when (result) {
                is Result.Ok -> { /* output captured at sink level */ }
                is Result.Err -> errors.add(record to result.error)
            }
        }

        return TestResult(
            inputCount = inputRecords.size,
            outputCount = pipeline.getProcessedCount().toInt(),
            errorCount = errors.size,
            errors = errors.toList(),
            metrics = pipeline.getMetrics().summary()
        )
    }

    data class TestResult<K, V>(
        val inputCount: Int,
        val outputCount: Int,
        val errorCount: Int,
        val errors: List<Pair<Record<K, V>, PipelineError>>,
        val metrics: Map<String, Any>
    ) {
        val successRate: Double
            get() = if (inputCount > 0) (inputCount - errorCount).toDouble() / inputCount else 0.0
    }

    companion object {
        fun <K, V> create(): TestHarness<K, V> = TestHarness()

        fun generateRecords(
            count: Int,
            keyFn: (Int) -> String = { "key-$it" },
            valueFn: (Int) -> Map<String, Any?> = { mapOf("index" to it, "data" to "value-$it") },
            timestampFn: (Int) -> Long = { System.currentTimeMillis() + it * 100L }
        ): List<Record<String, Map<String, Any?>>> {
            return (0 until count).map { i ->
                Record(keyFn(i), valueFn(i), timestampFn(i))
            }
        }
    }
}
