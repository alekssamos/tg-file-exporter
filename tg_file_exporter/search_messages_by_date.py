from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime

from pyrogram import Client, enums
from pyrogram.types import Message


async def search_messages_by_date(
    app: Client,
    chat_id: int | str,
    filter: enums.MessagesFilter | None = None,
    query: str = "",
    min_date: datetime | None = None,
    max_date: datetime | None = None,
    limit: int = 0,
    offset: int | None = 0,
    offset_id: int | None = 0,
    min_id: int | None = 0,
    max_id: int | None = 0,
    from_user: int | str | None = None,
    message_thread_id: int | None = None,
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
        from_user=from_user,  # type:ignore
        message_thread_id=message_thread_id,
    ):
        # Telegram API возвращает UTC-время, сравниваем напрямую
        if min_date and message.date < min_date:  # type:ignore
            continue
        if max_date and message.date > max_date:  # type:ignore
            continue
        yield message
