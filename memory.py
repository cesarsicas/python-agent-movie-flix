from langgraph.checkpoint.memory import InMemorySaver
from config import settings


async def create_checkpointer():
    try:
        from langgraph.checkpoint.redis.aio import AsyncRedisSaver
        saver = AsyncRedisSaver.from_conn_string(settings.redis_url)
        await saver.asetup()
        return saver
    except Exception:
        return InMemorySaver()
