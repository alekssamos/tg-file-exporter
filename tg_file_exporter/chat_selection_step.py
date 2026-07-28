import asyncio

import wx  # type:ignore
from loguru import logger
from pyrogram.errors import RPCError
from pyrogram.types import Message
from wxasync import AsyncBind, StartCoroutine  # type:ignore

from .advanced_dialogs_cache import AdvancedDialogsCache  # type:ignore
from .base_wizard_step import WizardStep
from .get_chat_title import getChatTitle
from .search_text import search_chat


# Шаг 3: Выбор чата
class ChatSelectionStep(WizardStep):
    def __init__(self, parent, client):
        super().__init__(parent)
        logger.debug("ChatSelectionStep")
        self.client = client
        self.folders = [
            None,
        ]
        self._folders = []
        self.selected_folder = None
        self.chats = []
        self.selected_chat = None
        self.update_chats_thread = None
        if not hasattr(self, "adc"):
            self.adc = AdvancedDialogsCache(self.client)

        self.folder_list = wx.ListBox(self)
        self.folder_list.Disable()
        self.folder_list.Hide()
        self.chat_list = wx.ListBox(self)
        self.search_input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        # self.search_input.Disable()
        # self.search_button = wx.Button(self, label="Поиск")
        # self.search_button.Disable()

        AsyncBind(wx.EVT_KEY_UP, self.on_search, self.search_input)
        # AsyncBind(wx.EVT_BUTTON, self.on_search, self.search_button)
        self.folder_list.Bind(wx.EVT_LISTBOX, self.on_folder_select)
        self.chat_list.Bind(wx.EVT_LISTBOX, self.on_chat_select)

        self.step_sizer.Add(self.folder_list, 1, wx.EXPAND | wx.ALL, 5)
        self.step_sizer.Add(wx.StaticText(self, label="Выберите чат:"), 0, wx.ALL, 5)
        self.step_sizer.Add(self.search_input, 0, wx.EXPAND | wx.ALL, 5)
        # self.step_sizer.Add(self.search_button, 0, wx.ALL, 5)
        self.step_sizer.Add(self.chat_list, 1, wx.EXPAND | wx.ALL, 5)
        self.folder_list.Append("Все чаты")
        self.folder_list.SetSelection(0)

    @logger.catch
    async def load_chats(self):
        try:
            if not self._folders:
                self._folders = await self.client.get_folders()
            for folder in self._folders:
                self.folders.append(folder)
                wx.CallAfter(
                    self.folder_list.Append,
                    folder.name,
                )
            self.chat_list.Clear()
            self.chats = []
            folder_id = self.selected_folder.id if self.selected_folder else None
            async for dialog in self.adc.iter_dialogs(folder_id):
                tm = ""
                if dialog.top_message:
                    tm = dialog.top_message.text or dialog.top_message.caption or ""
                chatline = f"{getChatTitle(dialog.chat)} ({tm})"
                if (
                    self.search_input.GetValue()
                    and self.search_input.GetValue().strip()
                ) and not search_chat(
                    getChatTitle(dialog.chat), self.search_input.GetValue().strip()
                ):
                    continue
                self.chats.append(dialog)
                wx.CallAfter(
                    self.chat_list.Append,
                    chatline,
                )
        except (RPCError, AttributeError) as e:
            logger.exception("error in update dialogs")
            wx.CallAfter(
                wx.MessageBox,
                f"Ошибка загрузки чатов: {e!s}",
                "Ошибка",
                wx.OK | wx.ICON_ERROR,
            )

    def update_chat_list(self, chats):
        self.update_chats_thread.cancel()  # type:ignore
        self.chat_list.Clear()
        for chat in chats:
            tm = ""
            if chat.top_message:
                tm = chat.top_message.text or chat.top_message.caption or ""
            self.chat_list.Append(f"{getChatTitle(chat.chat)} ({tm})")

    @logger.catch
    async def on_search(self, event):
        event.Skip()
        kc = event.GetKeyCode()
        if (kc >= 300 and kc <= 350) or kc in [9, 10, 27]:
            return
        # Debounce: cancel previous debounce task and start a new one
        if hasattr(self, "_debounce_task") and self._debounce_task:  # type:ignore
            self._debounce_task.cancel()  # type:ignore
        self._debounce_task = asyncio.ensure_future(self._debounced_load())
        return

    async def _debounced_load(self):
        """Wait for typing to settle before reloading chats."""
        try:
            await asyncio.sleep(0.4)
            self.update_chats_thread = StartCoroutine(self.load_chats(), self)
        except asyncio.CancelledError:
            pass
        return
        query = (self.search_input.GetValue() or "").strip()
        if query:
            try:
                # Использовать search_global для поиска
                results: list[Message] = []
                async for result in self.client.search_global(query, limit=30):
                    results.append(result)
                wx.CallAfter(self.update_chat_list, results)
            except (RPCError, AttributeError, ValueError) as e:
                logger.exception("error in search")
                wx.CallAfter(
                    wx.MessageBox,
                    f"Ошибка поиска: {e!s}",
                    "Ошибка",
                    wx.OK | wx.ICON_ERROR,
                )
        else:
            wx.CallAfter(self.update_chat_list, self.chats)

    def on_folder_select(self, event):
        event.Skip()
        index = self.folder_list.GetSelection()
        if index != wx.NOT_FOUND:
            self.selected_folder = self.folders[index]
        if hasattr(self, "_debounce_task") and self._debounce_task:
            self._debounce_task.cancel()
        if self.update_chats_thread:
            self.update_chats_thread.cancel()
        self.update_chats_thread = StartCoroutine(self.load_chats(), self)

    def on_chat_select(self, event):
        event.Skip()
        index = self.chat_list.GetSelection()
        if index != wx.NOT_FOUND:
            self.selected_chat = self.chats[index]

    def can_proceed(self):
        return self.selected_chat is not None
