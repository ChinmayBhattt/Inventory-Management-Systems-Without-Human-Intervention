import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Optional
import redis.asyncio as aioredis
from backend.app.core.config import settings
from backend.app.core.logging import logger


class InMemoryLock:
    """Re-entrant in-memory lock for environments without Redis or within the same task."""
    _locks: Dict[str, Dict] = {}
    _holders: Dict[str, asyncio.Task] = {}

    @classmethod
    @asynccontextmanager
    async def acquire(cls, key: str, timeout: float = 10.0, retry_interval: float = 0.02):
        current_task = asyncio.current_task()
        
        # Check re-entrancy for the same asyncio task
        if key in cls._holders and cls._holders[key] == current_task:
            cls._locks[key]["depth"] += 1
            try:
                yield
            finally:
                cls._locks[key]["depth"] -= 1
                if cls._locks[key]["depth"] <= 0:
                    cls._holders.pop(key, None)
                    if cls._locks[key]["lock"].locked():
                        cls._locks[key]["lock"].release()
            return

        lock_entry = cls._locks.setdefault(key, {"lock": asyncio.Lock(), "depth": 0})
        lock = lock_entry["lock"]
        start = time.time()
        acquired = False
        
        while time.time() - start < timeout:
            if not lock.locked():
                await lock.acquire()
                acquired = True
                cls._holders[key] = current_task
                lock_entry["depth"] = 1
                break
            await asyncio.sleep(retry_interval)

        if not acquired:
            raise TimeoutError(f"Could not acquire in-memory lock for {key}")
        try:
            yield
        finally:
            if key in cls._holders and cls._holders[key] == current_task:
                lock_entry["depth"] -= 1
                if lock_entry["depth"] <= 0:
                    cls._holders.pop(key, None)
                    if lock.locked():
                        lock.release()


class RedisManager:
    def __init__(self):
        self._client: Optional[aioredis.Redis] = None
        self._is_connected = False

    async def get_client(self) -> Optional[aioredis.Redis]:
        if self._client is None:
            try:
                client = aioredis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=1.0
                )
                await client.ping()
                self._client = client
                self._is_connected = True
                logger.info("Connected to Redis successfully.")
            except Exception as e:
                self._client = None
                self._is_connected = False
        return self._client

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @asynccontextmanager
    async def distributed_lock(self, key: str, expire_seconds: int = 15, timeout: float = 10.0):
        client = await self.get_client()
        lock_key = f"lock:{key}"

        if client is not None:
            lock = client.lock(lock_key, timeout=expire_seconds, sleep=0.05, blocking_timeout=timeout)
            acquired = await lock.acquire()
            if not acquired:
                raise TimeoutError(f"Could not acquire Redis lock for key: {key}")
            try:
                yield
            finally:
                try:
                    await lock.release()
                except Exception:
                    pass
        else:
            # Re-entrant in-memory lock fallback
            async with InMemoryLock.acquire(key, timeout=timeout):
                yield

    async def get(self, key: str) -> Optional[str]:
        client = await self.get_client()
        if client:
            try:
                return await client.get(key)
            except Exception:
                pass
        return None

    async def set(self, key: str, value: str, expire_seconds: Optional[int] = None) -> bool:
        client = await self.get_client()
        if client:
            try:
                await client.set(key, value, ex=expire_seconds)
                return True
            except Exception:
                pass
        return False

    async def close(self):
        if self._client:
            await self._client.close()
            self._client = None


redis_manager = RedisManager()
