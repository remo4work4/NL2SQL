"""Phase 8/9 共享限流测试：PG 后端（默认）+ Redis 后端（部署环境运行时）+ 故障开放降级。

语义（FR-19/20）：令牌桶（速率）+ 在途计数（严格并发上限）双约束。
"""
import asyncio
import time

import pytest

from app.core import rate_limit
from app.core.config import settings
from app.core.database import connect_db


@pytest.fixture()
def pg_backend(db_paths, monkeypatch):
    """强制 PG 后端 + 已知参数。"""
    monkeypatch.setattr(settings, "redis_url", "")
    monkeypatch.setattr(settings, "max_concurrent_llm", 2)
    monkeypatch.setattr(settings, "llm_rate_per_second", 2.0)
    monkeypatch.setattr(settings, "llm_timeout", 15)
    rate_limit.reset_backends()
    return rate_limit._PGBucket()


class TestPGBucket:
    def test_take_respects_capacity(self, pg_backend):
        assert pg_backend.take() is True
        assert pg_backend.take() is True
        assert pg_backend.take() is False  # 在途 = 容量，第三取空

    def test_release_then_refill(self, pg_backend):
        assert pg_backend.take() and pg_backend.take()
        assert pg_backend.take() is False
        pg_backend.release()
        pg_backend.release()
        time.sleep(1.1)  # 速率 2/s → 1.1s 补充约 2.2 个（截断到容量）
        assert pg_backend.take() is True

    def test_release_without_take_is_safe(self, pg_backend):
        pg_backend.release()  # inflight 0 → 不出现负数
        assert pg_backend.take() and pg_backend.take()

    def test_never_exceeds_capacity_over_long_idle(self, pg_backend):
        time.sleep(1.5)
        assert pg_backend.take() and pg_backend.take()
        assert pg_backend.take() is False  # 长时间空闲只补到容量，且并发严格受限

    def test_state_shared_across_instances(self, pg_backend):
        """两个实例的等价物：两个 bucket 对象指向同一 PG，配额共享（跨实例语义）。"""
        other = rate_limit._PGBucket()
        assert pg_backend.take() and pg_backend.take()
        assert other.take() is False  # 对方把配额用完
        other.release()
        other.release()
        time.sleep(1.1)
        assert pg_backend.take() is True  # 对方释放后本实例可继续取


class TestRedisBucket:
    def test_take_release_semantics(self, monkeypatch):
        if not _redis_available():
            pytest.skip("Redis 未运行（127.0.0.1:6379）")
        monkeypatch.setattr(settings, "max_concurrent_llm", 2)
        monkeypatch.setattr(settings, "llm_rate_per_second", 2.0)

        async def run():
            b = rate_limit._RedisBucket("redis://127.0.0.1:6379/0")
            await b._redis.delete(rate_limit.KEY)  # 清理残留状态
            r = [await b.take() for _ in range(3)]
            assert r == [True, True, False]
            await b.release()
            await b.release()
            await asyncio.sleep(1.1)
            assert await b.take() is True
            await b.release()

        asyncio.run(run())

    def test_backend_selected_when_configured(self, db_paths, monkeypatch):
        if not _redis_available():
            pytest.skip("Redis 未运行（127.0.0.1:6379）")
        monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:6379/0")
        rate_limit.reset_backends()
        try:
            backend = rate_limit._get_backend()
            assert isinstance(backend, rate_limit._RedisBucket)
        finally:
            rate_limit.reset_backends()


class TestLimiterContext:
    def test_concurrent_limited_to_capacity(self, db_paths, monkeypatch):
        monkeypatch.setattr(settings, "redis_url", "")
        monkeypatch.setattr(settings, "max_concurrent_llm", 2)
        monkeypatch.setattr(settings, "llm_rate_per_second", 100.0)  # 高速率下并发上限依然严格
        monkeypatch.setattr(settings, "llm_timeout", 15)
        rate_limit.reset_backends()

        active = 0
        peak = 0
        lock = asyncio.Lock()

        async def worker():
            nonlocal active, peak
            async with rate_limit.llm_limiter():
                async with lock:
                    active += 1
                    peak = max(peak, active)
                await asyncio.sleep(0.3)
                async with lock:
                    active -= 1

        async def run():
            await asyncio.gather(*[worker() for _ in range(6)])

        asyncio.run(run())
        assert peak <= 2  # 高速率 + 令牌充足时，在途计数仍把并发钉在容量内

    def test_waits_and_eventually_acquires(self, db_paths, monkeypatch):
        monkeypatch.setattr(settings, "redis_url", "")
        monkeypatch.setattr(settings, "max_concurrent_llm", 1)
        monkeypatch.setattr(settings, "llm_rate_per_second", 5.0)
        monkeypatch.setattr(settings, "llm_timeout", 15)
        rate_limit.reset_backends()

        results = []

        async def worker(i):
            async with rate_limit.llm_limiter():
                await asyncio.sleep(0.2)
                results.append(i)

        async def run():
            await asyncio.gather(*[worker(i) for i in range(3)])

        asyncio.run(run())
        assert sorted(results) == [0, 1, 2]  # 全部最终获得配额


class TestBackendSelection:
    def test_default_is_pg_without_redis_url(self, db_paths, monkeypatch):
        monkeypatch.setattr(settings, "redis_url", "")
        rate_limit.reset_backends()
        backend = rate_limit._get_backend()
        assert isinstance(backend, rate_limit._PGBucket)

    def test_failure_open_on_db_gone(self, db_paths, monkeypatch):
        """take() 异常时故障开放：_acquire 不抛错、快速返回（宁可超配额不阻断服务）。

        注：用错误密码（真实端口）制造即时认证失败——Windows 防火墙对未监听
        端口是丢包黑洞，TCP 连接会挂到超时，不适合做快速失败测试。
        """
        monkeypatch.setattr(settings, "redis_url", "")
        monkeypatch.setattr(settings, "pg_dsn", "postgresql://nl2sql:wrongpass@127.0.0.1:5433/nl2sql_test")
        monkeypatch.setattr(settings, "llm_timeout", 15)
        rate_limit.reset_backends()
        t0 = time.monotonic()
        asyncio.run(rate_limit._acquire())  # 不应抛异常
        assert time.monotonic() - t0 < 10.0  # 故障开放：快速放行而非等到超时


def _redis_available() -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 6379), timeout=2):
            return True
    except OSError:
        return False


def test_llm_limiter_table_created_in_app_db(db_paths):
    conn = connect_db()
    try:
        tables = [
            row["table_name"]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'llm_limiter'"
            ).fetchall()
        ]
        assert "llm_limiter" in tables
    finally:
        conn.close()
