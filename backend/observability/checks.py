import logging

from sqlalchemy import text

from backend.db.session import get_sessionmaker

logger = logging.getLogger(__name__)


async def db_ping() -> bool:
    try:
        sm = get_sessionmaker()
        async with sm() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("DB ping failed")
        return False
