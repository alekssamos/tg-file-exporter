# type:ignore
from datetime import datetime
from pyrogram.types import Message
from pyrogram import Client, enums
from typing import AsyncGenerator, Optional, Union


async def search_messages_by_date(
    app: Client,
    chat_id: Union[int, str],
    filter: Optional[enums.MessagesFilter] = None,
    query: str = "",
    min_date: Optional[datetime] = None,
    max_date: Optional[datetime] = None,
    limit: int = 0,
    offset: Optional[int] = 0,
    offset_id: Optional[int] = 0,
    min_id: Optional[int] = 0,
    max_id: Optional[int] = 0,
    from_user: Union[int, str] = None,
    message_thread_id: Optional[int] = None,
) -> AsyncGenerator[Message, None]:
    """
    Асинхронный генератор, аналогичный app.search_messages(),
    но с клиентской фильтрацией по диапазону дат (min_date / max_date).
    """
    async for message in app.search_messages(
        chat_id=chat_id,
        query=query,
        filter=filter,
        limit=limit,
        offset=offset,
        offset_id=offset_id,
        min_id=min_id,
        max_id=max_id,
        from_user=from_user,
        message_thread_id=message_thread_id,
    ):
        # Telegram API возвращает UTC-время, сравниваем напрямую
        if min_date and message.date < min_date:
            continue
        if max_date and message.date > max_date:
            continue
        yield message
