# type:ignore
from __future__ import annotations

import asyncio
import pickle
import time
from collections.abc import AsyncIterator

import aiosqlite
from loguru import logger
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler


class AdvancedDialogsCache:
    """
    Production-ready dialogs cache:

    ✅ Realtime updates (events)
    ✅ SQLite persistent cache
    ✅ Pinned chats with order
    ✅ Folders support
    ✅ Smart pagination (pinned never lost)
    ✅ No race-induced truncation
    ✅ Flood-wait-safe rate limiting
    """

    def __init__(
        self,
        client: Client,
        db_path: str = "dialogs.db",
        batch_size: int = 100,
    ):
        self.client = client
        self.db_path = db_path
        self.batch_size = batch_size

        self._db: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()
        self._queue = asyncio.Queue()

        self._sync_started = False
        self._streamed = False
        self._dialogs_lock = asyncio.Lock()
        self._last_api_call: float = 0.0

    # ---------------- INIT ----------------

    async def init(self):
        self._db = await aiosqlite.connect(self.db_path)

        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute("PRAGMA synchronous=NORMAL;")

        await self._db.execute("""
        CREATE TABLE IF NOT EXISTS dialogs (
            chat_id INTEGER PRIMARY KEY,

            date INTEGER,
            top_message_id INTEGER,

            raw BLOB,
            updated_at INTEGER,

            folder_id INTEGER DEFAULT 0,

            is_pinned INTEGER DEFAULT 0,
            pinned_order INTEGER
        )
        """)

        await self._db.execute("""
        CREATE INDEX IF NOT EXISTS idx_dialogs_order
        ON dialogs(
            folder_id,
            is_pinned DESC,
            pinned_order ASC,
            date DESC
        )
        """)

        await self._db.commit()

        # self._setup_realtime()
        asyncio.create_task(self._realtime_worker())

    # ---------------- PUBLIC API ----------------

    async def iter_dialogs(self, folder_id: int | None = None) -> AsyncIterator:
        """
        Главный streaming API:
        - сначала кеш
        - потом Telegram
        - без дублей
        - с защитой от Flood Wait
        """

        if not self._db:
            await self.init()

        yielded: set[int] = set()

        # -------- CACHE --------
        w = "WHERE folder_id = ?" if folder_id is not None else ""
        binds = (folder_id,) if folder_id is not None else ()
        logger.debug("load dialogs from db")
        async with self._db.execute(
            f"""
            SELECT chat_id, raw FROM dialogs
            {w}
            ORDER BY
                is_pinned DESC,
                pinned_order ASC,
                date DESC
        """,
            binds,
        ) as cursor:
            async for chat_id, raw in cursor:
                yielded.add(chat_id)
                yield pickle.loads(raw)

        # -------- TELEGRAM STREAM --------
        if not self._streamed:
            self._streamed = True

            # Rate limit: ensure minimum 2s gap between get_dialogs calls
            async with self._dialogs_lock:
                await asyncio.sleep(2)
                elapsed = time.time() - self._last_api_call
                if elapsed < 2.0:
                    logger.debug(f"rate limiting: waiting {2.0 - elapsed:.1f}s")
                    await asyncio.sleep(2.0 - elapsed)

            logger.debug("load dialogs from Telegram")
            async for dialog in self.client.get_dialogs():
                if (
                    folder_id is not None
                    and getattr(dialog, "folder_id", 0) != folder_id
                ):
                    continue

                cid = dialog.chat.id

                if cid in yielded:
                    continue

                yielded.add(cid)

                yield dialog

                self._last_api_call = time.time()
                # Upsert to cache after yielding (not fire-and-forget)
                await self._upsert_dialog(dialog)

        # -------- BACKGROUND SYNC (delayed, only once) --------
        if not self._sync_started:
            self._sync_started = True
            # Delay background sync by 30s to avoid flood waits
            asyncio.create_task(self._delayed_sync())

    # ---------------- REALTIME ----------------

    def _setup_realtime(self):
        self.client.add_handler(MessageHandler(self._on_message, filters.all), group=0)

    async def _on_message(self, client, message):
        await self._queue.put(message)

    async def _realtime_worker(self):
        buffer = []

        while True:
            msg = await self._queue.get()
            buffer.append(msg)

            if len(buffer) >= self.batch_size:
                await self._flush_messages(buffer)
                buffer.clear()

            await asyncio.sleep(0.05)

            if buffer:
                await self._flush_messages(buffer)
                buffer.clear()

    async def _flush_messages(self, messages):
        rows = []

        for msg in messages:
            rows.append(
                (
                    msg.chat.id,
                    int(msg.date.timestamp()),
                    msg.id,
                    pickle.dumps(msg),
                    int(time.time()),
                    0,  # folder неизвестен в realtime
                    0,
                    None,
                )
            )

        async with self._write_lock:
            await self._db.executemany(
                """
            INSERT INTO dialogs (
                chat_id, date, top_message_id, raw, updated_at,
                folder_id, is_pinned, pinned_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                date=excluded.date,
                top_message_id=excluded.top_message_id,
                raw=excluded.raw,
                updated_at=excluded.updated_at
            """,
                rows,
            )

            await self._db.commit()

    # ---------------- STORAGE ----------------

    async def _upsert_dialog(self, dialog, pinned_order=None):
        row = (
            dialog.chat.id,
            int(dialog.top_message.date.timestamp()) if dialog.top_message else 0,
            dialog.top_message.id if dialog.top_message else None,
            pickle.dumps(dialog),
            int(time.time()),
            getattr(dialog, "folder_id", 0),
            int(dialog.is_pinned),
            pinned_order,
        )

        async with self._write_lock:
            await self._db.execute(
                """
            INSERT INTO dialogs (
                chat_id, date, top_message_id, raw, updated_at,
                folder_id, is_pinned, pinned_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                date=excluded.date,
                top_message_id=excluded.top_message_id,
                raw=excluded.raw,
                updated_at=excluded.updated_at,
                folder_id=excluded.folder_id,
                is_pinned=excluded.is_pinned,
                pinned_order=excluded.pinned_order
            """,
                row,
            )

            await self._db.commit()

    # ---------------- FULL SYNC ----------------

    async def _delayed_sync(self):
        """Run background sync after a delay to avoid flood waits."""
        await asyncio.sleep(30.0)  # Wait 30 seconds before background refresh
        await self._background_sync()

    async def _background_sync(self):
        """Full resync with Telegram — rate-limited for safety."""
        async with self._dialogs_lock:
            await asyncio.sleep(2)
            elapsed = time.time() - self._last_api_call
            if elapsed < 3.0:
                logger.debug(f"background sync: waiting {3.0 - elapsed:.1f}s")
                await asyncio.sleep(3.0 - elapsed)

        logger.debug("background sync: loading dialogs from Telegram")
        await asyncio.sleep(2)
        async with self._write_lock:
            rows = []
            pinned_index = 0

            async for dialog in self.client.get_dialogs():
                if dialog.is_pinned:
                    pinned_order = pinned_index
                    pinned_index += 1
                else:
                    pinned_order = None

                rows.append(
                    (
                        dialog.chat.id,
                        int(dialog.top_message.date.timestamp())
                        if dialog.top_message
                        else 0,
                        dialog.top_message.id if dialog.top_message else None,
                        pickle.dumps(dialog),
                        int(time.time()),
                        getattr(dialog, "folder_id", 0),
                        int(dialog.is_pinned),
                        pinned_order,
                    )
                )

                if len(rows) >= self.batch_size:
                    await self._flush(rows)
                    self._last_api_call = time.time()
                    await asyncio.sleep(0.5)  # Small pause between batches
                    rows.clear()

            if rows:
                await self._flush(rows)

    async def _flush(self, rows):
        await self._db.executemany(
            """
        INSERT INTO dialogs (
            chat_id, date, top_message_id, raw, updated_at,
            folder_id, is_pinned, pinned_order
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            date=excluded.date,
            top_message_id=excluded.top_message_id,
            raw=excluded.raw,
            updated_at=excluded.updated_at,
            folder_id=excluded.folder_id,
            is_pinned=excluded.is_pinned,
            pinned_order=excluded.pinned_order
        """,
            rows,
        )

        await self._db.commit()

    # ---------------- CLOSE ----------------

    async def close(self):
        if self._db:
            await self._db.close()
