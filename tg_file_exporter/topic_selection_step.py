import wx  # type:ignore
from loguru import logger
from pyrogram.errors import RPCError

from .base_wizard_step import WizardStep
from .get_chat_title import getChatTitle


# Шаг 4: Выбор темы
class TopicSelectionStep(WizardStep):
    def __init__(self, parent, client):
        super().__init__(parent)
        self.client = client
        self.selected_topic = None
        self.has_topics = False

        self.topic_list = wx.ListBox(self)
        self.topic_list.Bind(wx.EVT_LISTBOX, self.on_topic_select)

        self.step_sizer.Add(
            wx.StaticText(self, label="Выберите тему (или 'Все'):"), 0, wx.ALL, 5
        )
        self.step_sizer.Add(self.topic_list, 1, wx.EXPAND | wx.ALL, 5)

    @logger.catch
    async def set_chat(self, chat):
        self.chat = chat

    @logger.catch
    async def load_topics(self, p):
        try:
            # Проверить, есть ли темы в чате
            topics = []
            if self.chat.chat.is_forum:
                async for topic in self.client.get_forum_topics(self.chat.chat.id):
                    topics.append(topic)
            self.topics = topics
            if topics:
                self.has_topics = True
                self.topic_list.Clear()
                self.topic_list.Append("Все")
                for topic in topics:
                    self.topic_list.Append(topic.title)
                self.topic_list.SetSelection(0)  # Выбрать "Все" по умолчанию
                self.selected_topic = None  # None значит все
            else:
                self.has_topics = False
                self.topic_list.Clear()
                self.topic_list.Append("Чат без тем")
                self.topic_list.SetSelection(0)
                self.selected_topic = None
                await p.on_next(None)
        except (RPCError, ValueError, AttributeError) as e:
            logger.exception("error in get topics")
            self.has_topics = False
            wx.MessageBox(
                f"Ошибка загрузки тем из {getChatTitle(self.chat.chat)}: {e!s}",
                "Ошибка",
                wx.OK | wx.ICON_ERROR,
            )

    @logger.catch
    def on_topic_select(self, event):
        index = self.topic_list.GetSelection()
        if index == 0:
            self.selected_topic = None  # Все
        else:
            self.selected_topic = self.topics[index - 1].id  # id темы

    def can_proceed(self):
        return True  # Всегда можно перейти, даже без выбора
