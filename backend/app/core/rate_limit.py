"""LLM 调用共享限流（FR-19/20）：令牌桶 + 在途计数双约束，跨进程/跨实例共享。

语义：并发上限（在途 ≤ max_concurrent_llm，严格）+ 速率上限（令牌桶，
容量 = max_concurrent_llm，补充速率 = llm_rate_per_second）。取配额需同时
满足「令牌 ≥ 1 且 在途 < 容量」，退出时释放在途计数（令牌按时间自然补充）。

后端优先级（首次使用时探测并缓存决定）：
  1. Redis（settings.redis_url 配置时）：Lua 原子「补充+判定+扣减」；
  2. PostgreSQL（默认，Phase 9 系统存储）：单条 CTE + FOR UPDATE 原子完成，
     跨实例共享；
  3. 进程内 asyncio.Semaphore（以上全部不可用时兜底，仅单进程语义，告警）。

获取不到时轮询等待（50ms 间隔），超时上限 llm_timeout；
后端异常时故障开放（宁可超配额也不阻断服务）。

用法：
    from app.core import rate_limit
    async with rate_limit.llm_limiter():
        await llm_call(...)
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager

from app.core.config import settings

logger = logging.getLogger("nl2sql.limit")

KEY = "llm"
_POLL_INTERVAL = 0.05  # 配额不足时的轮询间隔（s）

# Redis 令牌桶 + 在途计数 Lua（原子：补充 → 双判定 → 扣减）
_REDIS_TAKE_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local state = redis.call('HMGET', key, 'tokens', 'ts', 'inflight')
local tokens = tonumber(state[1])
if not tokens then tokens = capacity end
local ts = tonumber(state[2]) or now
local inflight = tonumber(state[3]) or 0
tokens = math.min(capacity, tokens + (now - ts) * rate)
local ok = 0
if tokens >= 1 and inflight < capacity then
  tokens = tokens - 1
  inflight = inflight + 1
  ok = 1
end
redis.call('HMSET', key, 'tokens', tokens, 'ts', now, 'inflight', inflight)
redis.call('PEXPIRE', key, 60000)
return ok
"""

_REDIS_RELEASE_LUA = """
local key = KEYS[1]
local inflight = tonumber(redis.call('HGET', key, 'inflight')) or 0
if inflight > 0 then redis.call('HSET', key, 'inflight', inflight - 1) end
return 1
"""

# PG：单条 CTE（FOR UPDATE 行锁）原子完成 补充→双判定→扣减
_PG_TAKE_SQL = """
WITH ref AS (
  SELECT LEAST(%(cap)s, tokens + (EXTRACT(EPOCH FROM clock_timestamp()) - ts) * %(rate)s) AS new_tokens,
         inflight
  FROM llm_limiter WHERE key = %(key)s FOR UPDATE
)
UPDATE llm_limiter SET
  tokens   = CASE WHEN ref.new_tokens >= 1.0 AND ref.inflight < %(cap)s THEN ref.new_tokens - 1.0 ELSE ref.new_tokens END,
  ts       = EXTRACT(EPOCH FROM clock_timestamp()),
  inflight = CASE WHEN ref.new_tokens >= 1.0 AND ref.inflight < %(cap)s THEN ref.inflight + 1 ELSE ref.inflight END,
  taken    = CASE WHEN ref.new_tokens >= 1.0 AND ref.inflight < %(cap)s THEN 1 ELSE 0 END
FROM ref WHERE llm_limiter.key = %(key)s
RETURNING llm_limiter.taken
"""


class _RedisBucket:
    def __init__(self, url: str):
        import redis.asyncio as aioredis
        self._redis = aioredis.from_url(url, socket_timeout=3, socket_connect_timeout=3)
        self._take = self._redis.register_script(_REDIS_TAKE_LUA)
        self._release = self._redis.register_script(_REDIS_RELEASE_LUA)

    async def take(self) -> bool:
        got = await self._take(
            keys=[KEY],
            args=[settings.max_concurrent_llm, settings.llm_rate_per_second, time.time()],
        )
        return bool(got)

    async def release(self) -> None:
        await self._release(keys=[KEY])


class _PGBucket:
    """PostgreSQL 共享后端（Phase 9，跨实例）。"""

    def take(self) -> bool:
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(settings.pg_dsn, row_factory=dict_row)
        try:
            conn.execute(
                "INSERT INTO llm_limiter (key, tokens, ts, inflight, taken) VALUES (%s, %s, %s, 0, 0) "
                "ON CONFLICT (key) DO NOTHING",
                (KEY, float(settings.max_concurrent_llm), time.time()),
            )
            row = conn.execute(
                _PG_TAKE_SQL,
                {"key": KEY, "cap": float(settings.max_concurrent_llm),
                 "rate": float(settings.llm_rate_per_second)},
            ).fetchone()
            conn.commit()
            return bool(row and row["taken"])
        finally:
            conn.close()

    def release(self) -> None:
        import psycopg

        conn = psycopg.connect(settings.pg_dsn)
        try:
            conn.execute(
                "UPDATE llm_limiter SET inflight = GREATEST(inflight - 1, 0) WHERE key = %s", (KEY,)
            )
            conn.commit()
        finally:
            conn.close()


class _LocalSemaphore:
    """进程内兜底（仅单进程语义，严格并发上限，无速率）。"""
    def __init__(self):
        self._sem = asyncio.Semaphore(max(settings.max_concurrent_llm, 1))

    async def take(self) -> bool:
        await self._sem.acquire()
        return True

    async def release(self) -> None:
        self._sem.release()


_backends: dict[tuple[str, str], object] = {}  # (redis_url, pg_dsn) → 后端实例


def _get_backend():
    key = (settings.redis_url, settings.pg_dsn)
    if key in _backends:
        return _backends[key]
    backend = None
    if settings.redis_url:
        try:
            backend = _RedisBucket(settings.redis_url)
            logger.info("共享限流后端: Redis（%s）", settings.redis_url)
        except Exception as e:
            logger.warning("Redis 不可用（%s），降级 PostgreSQL 共享限流", e)
            backend = None
    if backend is None:
        try:
            backend = _PGBucket()
            logger.info("共享限流后端: PostgreSQL（跨实例共享）")
        except Exception as e:
            logger.error("PG 限流不可用（%s），降级进程内信号量（仅单进程语义）", e)
            backend = _LocalSemaphore()
    _backends[key] = backend
    return backend


async def _acquire() -> None:
    backend = _get_backend()
    deadline = time.monotonic() + max(settings.llm_timeout, 10)
    waited = 0.0
    while True:
        try:
            if isinstance(backend, _PGBucket):
                got = await asyncio.to_thread(backend.take)  # 同步 PG 放线程池
            else:
                got = await backend.take()
            if got:
                if waited >= 0.2:
                    logger.info("限流等待 %.2fs（全局并发上限 %d）", waited, settings.max_concurrent_llm)
                return
        except Exception as e:
            logger.error("限流后端异常（故障开放）: %s", e)
            return  # 宁可超配额也不阻断服务
        if time.monotonic() >= deadline:
            logger.error("限流等待超时（%.0fs），放行", settings.llm_timeout)
            return
        await asyncio.sleep(_POLL_INTERVAL)
        waited += _POLL_INTERVAL


async def _release() -> None:
    backend = _get_backend()
    try:
        if isinstance(backend, _PGBucket):
            await asyncio.to_thread(backend.release)
        else:
            await backend.release()
    except Exception as e:
        logger.warning("限流释放失败（下次取令牌前会自动校正）: %s", e)


@asynccontextmanager
async def llm_limiter():
    """异步上下文管理器：进入时取得配额，退出时释放在途计数。"""
    await _acquire()
    try:
        yield
    finally:
        await _release()


def reset_backends() -> None:
    """测试用：清空后端缓存。"""
    _backends.clear()
