# type:ignore
from pyrogram import Client
from pyrogram import enums
from pyrogram import errors
from pyrogram.types import Chat
from pyrogram.errors import SessionPasswordNeeded
from datetime import datetime
from loguru import logger
import wx
import wx.adv
import asyncio
import tempfile
import re
from wxasync import AsyncBind, WxAsyncApp, StartCoroutine
import os
import sys

MAX_WORKERS = 5
logger.remove()
logger.add(
    sys.stderr,
    level="DEBUG",
    format="<green>{time:HH:mm:ss.SSS}</green> <level>{message}</level>   <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>",
    backtrace=True,
    diagnose=True,
)
logger.add(
    "tg_file_exporter.log",
    level="DEBUG",
    format="<green>{time:MM-DD HH:mm:ss.SSS}</green>  <level>{level: <8}</level>  <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    backtrace=True,
    diagnose=True,
)


def save_path(path=""):
    _filename = os.path.join(tempfile.gettempdir(), "tg_file_exporter_selected_dir")
    if path:
        with open(_filename, "w", encoding="UTF-8") as f:
            f.write(path)
    if os.path.isfile(_filename) and os.path.getsize(_filename) > 0:
        with open(_filename, "r", encoding="UTF-8") as f:
            return f.read(1024).strip()
    return ""


def WxToPyDate(date: wx._core.DateTime) -> datetime:
    return datetime(date.GetYear(), date.GetMonth(), date.GetDay())


def _getChatTitle(chat: Chat) -> str:
    name: str = chat.title or (chat.first_name or "") + " " + (chat.last_name or "")
    return name.strip() or "deleted?"


class TGFileExporter(WxAsyncApp):
    def __init__(self):
        super().__init__(sleep_duration=0.000001)

    def OnInit(self):
        # Параметры для Kurigram
        self.api_id = 2040
        self.api_hash = "b18441a1ff607e10a989891a5462e627"
        self.client = Client(
            "tg_file_exporter",
            api_id=self.api_id,
            api_hash=self.api_hash,
            max_concurrent_transmissions=True,
            no_updates=True,
        )
        self.wizard = ExportWizard(None, title="TG File Exporter", client=self.client)
        self.wizard.Show()
        return True


class AuthData:
    def __init__(self, phone, sent_code):
        self.phone = phone
        self.sent_code = sent_code


class ExportWizard(wx.Frame):
    def __init__(self, parent, title, client):
        super().__init__(parent, title=title, name="tg_exporter", size=(600, 400))
        self.export_thread = None
        self.client = client
        self.auth_data = AuthData(None, None)
        self.main_panel = wx.Panel(self)
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.main_panel.SetSizer(self.main_sizer)

        # Шаги мастера
        self.steps = []
        self.current_step = 0

        # Кнопки навигации
        self.button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.back_button = wx.Button(self.main_panel, label="Назад")
        self.next_button = wx.Button(self.main_panel, label="Далее")
        self.cancel_button = wx.Button(self.main_panel, label="Отмена")

        AsyncBind(wx.EVT_BUTTON, self.on_back, self.back_button)
        AsyncBind(wx.EVT_BUTTON, self.on_next, self.next_button)
        AsyncBind(wx.EVT_BUTTON, self.on_cancel, self.cancel_button)

        self.button_sizer.Add(self.back_button, 0, wx.ALL, 5)
        self.button_sizer.Add(self.next_button, 0, wx.ALL, 5)
        self.button_sizer.Add(self.cancel_button, 0, wx.ALL, 5)

        self.main_sizer.Add(self.button_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        # Инициализация шагов
        self.init_steps()
        # Добавить все шаги в main_sizer для видимости
        for step in self.steps:
            self.main_sizer.Add(step, 1, wx.EXPAND | wx.ALL, 5)
        StartCoroutine(self.show_step(0), self)

        self.Centre()

    def init_steps(self):
        logger.debug("adding steps")
        # Шаг 1: Номер телефона
        self.steps.append(PhoneStep(self.main_panel, self.client, self.auth_data))
        # Шаг 2: Код
        self.steps.append(CodeStep(self.main_panel, self.client, self.auth_data))
        # Шаг 3: Пароль
        self.steps.append(PasswordStep(self.main_panel, self.client))
        # Шаг 4: Выбор чата
        self.steps.append(ChatSelectionStep(self.main_panel, self.client))
        # Шаг 5: Выбор темы
        self.steps.append(TopicSelectionStep(self.main_panel, self.client))
        # Шаг 6: Путь сохранения
        self.steps.append(PathSelectionStep(self.main_panel))
        # Шаг 7: Типы файлов b период
        self.steps.append(FileTypeSelectionStep(self.main_panel))
        # Шаг 8: Экспорт
        self.steps.append(ExportStep(self.main_panel, self.client))

    async def show_step(self, step_index):
        # Пропустить шаги авторизации если авторизован
        if step_index == 0:
            if await self.client.connect():
                step_index = 3  # Пропустить к выбору чата
                self.current_step = step_index
                logger.info("already authorized")
            else:
                step_index = 0  # Начать с телефона

        # Скрыть все шаги
        for step in self.steps:
            step.Hide()

        # Показать текущий шаг
        self.steps[step_index].Show()
        self.main_sizer.Layout()
        self.Layout()

        # Обновить кнопки
        self.back_button.Enable(step_index > 0)
        self.next_button.SetLabel(
            "Далее" if step_index < len(self.steps) - 2 else "Экспорт"
        )
        self.next_button.Enable(True)
        if step_index == 7:
            self.back_button.Disable()
            StartCoroutine(self.start_export(), self)
            self.next_button.Disable()
        # фокус
        if step_index == 0:
            self.steps[step_index].phone_input.SetFocus()
        if step_index == 1:
            self.steps[step_index].code_input.SetFocus()
        if step_index == 2:
            self.steps[step_index].password_input.SetFocus()
        if step_index == 3:
            self.steps[step_index].chat_list.SetFocus()
        if step_index == 4:
            self.steps[step_index].topic_list.SetFocus()
        if step_index == 5:
            self.steps[step_index].path_input.SetFocus()
        if step_index == 6:
            self.steps[step_index].choice_file_type.SetFocus()

        # загрузить чаты
        if step_index == 3:
            if self.steps[step_index].update_chats_thread:
                self.steps[step_index].update_chats_thread.cancel()
            self.steps[step_index].update_chats_thread = StartCoroutine(
                self.steps[step_index].load_chats(), self
            )

        # загрузить темы
        if step_index == 4:
            StartCoroutine(self.steps[step_index].load_topics(self), self)

    async def on_back(self, event):
        logger.debug(f"back: current_step={self.current_step}")
        if self.current_step > 0 and self.current_step != 3:
            self.current_step -= 1
            if self.current_step == 4 and not self.steps[self.current_step].has_topics:
                self.current_step -= 1
            await self.show_step(self.current_step)

    async def on_next(self, event):
        logger.debug(f"next: current_step={self.current_step}")
        ############### events ###<
        # отправить код
        if self.current_step == 0:
            await self.steps[self.current_step].on_send_code(None)
        # Проверить код
        if self.current_step == 1:
            await self.steps[self.current_step].on_sign_in(None)
            # проверить нужен ли пароль?
            if not self.steps[self.current_step].password_needed:
                self.current_step = 2
        # Проверить пароль
        if self.current_step == 2 and self.steps[1].password_needed:
            await self.steps[self.current_step].on_submit(None)
        ############### events ###>
        if self.current_step < len(self.steps) - 1:
            # Проверить, можно ли перейти дальше
            if self.steps[self.current_step].can_proceed():
                self.current_step += 1
                # Если переходим к выбору темы, передать чат
                if self.current_step == 4 and hasattr(self.steps[3], "selected_chat"):
                    await self.steps[4].set_chat(self.steps[3].selected_chat)
                await self.show_step(self.current_step)
        else:
            # Начать экспорт
            if not hasattr(self, "workers"):
                self.next_button.Disable()
                await self.start_export()

    @logger.catch
    async def on_cancel(self, event):
        if self.export_thread:
            self.export_thread.cancel()
        if hasattr(self, "workers") and len(self.workers) > 0:
            for worker in self.workers:
                worker.cancel()
        self.Close()
        self.Destroy()
        await asyncio.sleep(0.5)
        event.skip()

    async def start_export(self):
        self.q = asyncio.queues.Queue(maxsize=MAX_WORKERS)
        self.workers = []
        for _ in range(MAX_WORKERS + 1):
            self.workers.append(StartCoroutine(self.download_media_worker(), self))
        self.export_thread = StartCoroutine(self.do_export(), self)

    async def do_export(self):
        # Собрать параметры
        chat = self.steps[3].selected_chat
        topic = self.steps[4].selected_topic
        path = self.steps[5].path_input.GetValue()
        min_date = None
        max_date = None
        message_filter = self.steps[6].filters_choices[
            self.steps[6].choice_file_type.GetSelection()
        ][1]
        if self.steps[6].checkbox_period.IsChecked():
            min_date = WxToPyDate(self.steps[6].start_date.GetValue())
            max_date = WxToPyDate(self.steps[6].end_date.GetValue())

        wx.CallAfter(self.steps[-1].update_progress, "Экспорт начат...")

        # параметры поиска
        kwargs = {"chat_id": chat.chat.id, "filter": message_filter}
        try:
            # Использовать search_messages_count для подсчёта
            total = await self.client.search_messages_count(**kwargs)
            # к сожалению, нельзя указать дату в search_messages_count
            i = 0  # счётчик для прогресса
            # заполняем дату и тему, если указана
            if min_date:
                kwargs["min_date"] = min_date
            if max_date:
                kwargs["max_date"] = max_date
            if topic:
                kwargs["message_thread_id"] = topic
            # Использовать search_messages для фильтрации
            async for message in self.client.search_messages(**kwargs):
                await self.q.put((message, path))
                wx.CallAfter(self.steps[-1].update_progress, f"Скачано {i + 1}/{total}")
                i += 1

            await self.q.join()
            wx.CallAfter(self.steps[-1].update_progress, "Экспорт завершен!")
            wx.CallAfter(
                wx.MessageBox,
                "Экспорт завершен!",
                "Информация",
                wx.OK | wx.ICON_INFORMATION,
            )
        except Exception as e:
            logger.exception("error in export")
            wx.CallAfter(self.steps[-1].update_progress, f"Ошибка: {str(e)}")
        finally:
            self.cancel_button.SetLabel("Готово")

    async def download_media_worker(self):
        while True:
            try:
                message, path = await self.q.get()
                if not path.endswith(os.path.sep):
                    path = path + os.path.sep
                # Скачать медиа
                await message.download(path)
            except (
                errors.RPCError,
                ValueError,
                AttributeError,
                OSError,
                FileExistsError,
            ):
                logger.exception("error in worker")
            finally:
                try:
                    self.q.task_done()
                except ValueError:
                    pass


# Базовый класс для шагов
class WizardStep(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.step_sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.step_sizer)

    def can_proceed(self):
        return True


# Шаг 1: Номер телефона
class PhoneStep(WizardStep):
    def __init__(self, parent, client, auth_data):
        super().__init__(parent)
        logger.debug("PhoneStep")
        self.client = client
        self.auth_data = auth_data

        self.step_sizer.Add(wx.StaticText(self, label="Номер телефона:"), 0, wx.ALL, 5)

        self.phone_input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.phone_input.SetMaxLength(20)

        # self.phone_input.Bind(wx.EVT_TEXT_ENTER, self.on_send_code)

        self.step_sizer.Add(self.phone_input, 0, wx.EXPAND | wx.ALL, 5)

    async def on_send_code(self, event):
        logger.info("Going to send the code...")
        phone = re.sub(r"\D+", "", (self.phone_input.GetValue() or ""))
        logger.debug("phone: " + phone)
        if phone and len(phone) > 10:
            try:
                logger.info("sending code...")
                self.auth_data.phone = "+" + phone
                self.auth_data.sent_code = await self.client.send_code(
                    self.auth_data.phone
                )
                wx.MessageBox(
                    "Код отправлен на ваш телефон.",
                    "Информация",
                    wx.OK | wx.ICON_INFORMATION,
                )
            except Exception as e:
                logger.exception("error in sending code")
                wx.MessageBox(
                    f"Ошибка отправки кода: {str(e)}", "Ошибка", wx.OK | wx.ICON_ERROR
                )

    def can_proceed(self):
        return self.auth_data.sent_code is not None


# Шаг 2: Код
class CodeStep(WizardStep):
    def __init__(self, parent, client, auth_data):
        super().__init__(parent)
        logger.debug("CodeStep")
        self.client = client
        self.code_entered = False
        self.password_needed = False
        self.auth_data = auth_data

        self.step_sizer.Add(wx.StaticText(self, label="Код из SMS:"), 0, wx.ALL, 5)

        self.code_input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.code_input.SetMaxLength(6)

        self.step_sizer.Add(self.code_input, 0, wx.EXPAND | wx.ALL, 5)

    async def on_sign_in(self, event):
        code = self.code_input.GetValue() or ""
        if code:
            try:
                logger.info("trying sign in")
                await self.client.sign_in(
                    self.auth_data.phone, self.auth_data.sent_code.phone_code_hash, code
                )
                wx.MessageBox(
                    "Вход выполнен успешно!", "Успех", wx.OK | wx.ICON_INFORMATION
                )
                self.code_entered = True
            except SessionPasswordNeeded:
                self.code_entered = True
                self.password_needed = True
            except Exception as e:
                logger.exception("error sign in")
                wx.MessageBox(
                    f"Ошибка входа: {str(e)}", "Ошибка", wx.OK | wx.ICON_ERROR
                )

    def can_proceed(self):
        return self.code_entered


# Шаг 3: Пароль
class PasswordStep(WizardStep):
    def __init__(self, parent, client):
        super().__init__(parent)
        logger.debug("PasswordStep")
        self.client = client
        self.password_entered = False

        self.step_sizer.Add(wx.StaticText(self, label="Пароль:"), 0, wx.ALL, 5)

        self.password_input = wx.TextCtrl(
            self, style=wx.TE_PASSWORD | wx.TE_PROCESS_ENTER
        )
        self.password_input.SetMaxLength(100)

        self.step_sizer.Add(self.password_input, 0, wx.EXPAND | wx.ALL, 5)

    async def on_submit(self, event):
        password = self.password_input.GetValue()
        try:
            logger.info("trying password auth")
            await self.client.check_password(password)
            wx.MessageBox("Пароль принят!", "Успех", wx.OK | wx.ICON_INFORMATION)
            self.password_entered = True
        except Exception as e:
            logger.exception("error password")
            wx.MessageBox(f"Ошибка пароля: {str(e)}", "Ошибка", wx.OK | wx.ICON_ERROR)

    def can_proceed(self):
        return self.password_entered


# Шаг 3: Выбор чата
class ChatSelectionStep(WizardStep):
    def __init__(self, parent, client):
        super().__init__(parent)
        logger.debug("ChatSelectionStep")
        self.client = client
        self.chats = []
        self.selected_chat = None
        self.update_chats_thread = None

        self.chat_list = wx.ListBox(self)
        self.search_input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_input.Disable()
        self.search_button = wx.Button(self, label="Поиск")
        self.search_button.Disable()

        AsyncBind(wx.EVT_TEXT_ENTER, self.on_search, self.search_input)
        AsyncBind(wx.EVT_BUTTON, self.on_search, self.search_button)
        self.chat_list.Bind(wx.EVT_LISTBOX, self.on_chat_select)

        self.step_sizer.Add(wx.StaticText(self, label="Выберите чат:"), 0, wx.ALL, 5)
        self.step_sizer.Add(self.search_input, 0, wx.EXPAND | wx.ALL, 5)
        self.step_sizer.Add(self.search_button, 0, wx.ALL, 5)
        self.step_sizer.Add(self.chat_list, 1, wx.EXPAND | wx.ALL, 5)

    async def load_chats(self):
        try:
            self.chat_list.Clear()
            self.chats = []
            async for dialog in self.client.get_dialogs():
                self.chats.append(dialog)
                tm = ""
                if dialog.top_message:
                    tm = dialog.top_message.text or dialog.top_message.caption or ""
                wx.CallAfter(
                    self.chat_list.Append,
                    f"{_getChatTitle(dialog.chat)} ({tm})",
                )
        except Exception as e:
            logger.exception("error in update dialogs")
            wx.CallAfter(
                wx.MessageBox,
                f"Ошибка загрузки чатов: {str(e)}",
                "Ошибка",
                wx.OK | wx.ICON_ERROR,
            )

    def update_chat_list(self, chats):
        self.update_chats_thread.cancel()
        self.chat_list.Clear()
        for chat in chats:
            tm = ""
            if chat.top_message:
                tm = chat.top_message.text or chat.top_message.caption or ""
            self.chat_list.Append(f"{_getChatTitle(chat.chat)} ({tm})")

    async def on_search(self, event):
        query = (self.search_input.GetValue() or "").strip()
        if query:
            try:
                # Использовать search_global для поиска
                results = []
                async for result in self.client.search_global(query, limit=30):
                    results.append(results)
                wx.CallAfter(self.update_chat_list, results)
            except Exception as e:
                logger.exception("error in search")
                wx.CallAfter(
                    wx.MessageBox,
                    f"Ошибка поиска: {str(e)}",
                    "Ошибка",
                    wx.OK | wx.ICON_ERROR,
                )
        else:
            wx.CallAfter(self.update_chat_list, self.chats)

    def on_chat_select(self, event):
        index = self.chat_list.GetSelection()
        if index != wx.NOT_FOUND:
            self.selected_chat = self.chats[index]

    def can_proceed(self):
        return self.selected_chat is not None


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

    async def set_chat(self, chat):
        self.chat = chat

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
        except Exception as e:
            logger.exception("error in get topics")
            self.has_topics = False
            wx.MessageBox(
                f"Ошибка загрузки тем из {_getChatTitle(self.chat.chat)}: {str(e)}",
                "Ошибка",
                wx.OK | wx.ICON_ERROR,
            )

    def on_topic_select(self, event):
        index = self.topic_list.GetSelection()
        if index == 0:
            self.selected_topic = None  # Все
        else:
            self.selected_topic = self.topics[index - 1].id  # id темы

    def can_proceed(self):
        return True  # Всегда можно перейти, даже без выбора


# Шаг 5: Путь сохранения
class PathSelectionStep(WizardStep):
    def __init__(self, parent):
        super().__init__(parent)
        self.step_sizer.Add(wx.StaticText(self, label="Путь сохранения:"), 0, wx.ALL, 5)
        self.path_input = wx.TextCtrl(self)
        self.path_input.SetMaxLength(1024)
        self.path_input.SetValue(save_path())
        self.browse_button = wx.Button(self, label="Обзор")

        self.browse_button.Bind(wx.EVT_BUTTON, self.on_browse)

        h_sizer = wx.BoxSizer(wx.HORIZONTAL)
        h_sizer.Add(self.path_input, 1, wx.EXPAND | wx.ALL, 5)
        h_sizer.Add(self.browse_button, 0, wx.ALL, 5)

        self.step_sizer.Add(h_sizer, 0, wx.EXPAND)

    def can_proceed(self):
        path = self.path_input.GetValue().strip()
        try:
            if len(path) > 0:
                os.makedirs(path, exist_ok=True)
        except (ValueError, OSError, FileExistsError, RuntimeError):
            logger.exception("error create export dir")
            return False
        if len(path) == 0 or not os.path.isdir(path):
            wx.MessageBox(
                "Укажите корректный путь к папке для скачивания в неё файлов",
                "Ошибка",
                wx.OK | wx.ICON_ERROR,
            )
            self.browse_button.SetFocus()
            return False
        save_path(path)
        return True

    def on_browse(self, event):
        dialog = wx.DirDialog(self, "Выберите папку для сохранения")
        if dialog.ShowModal() == wx.ID_OK:
            self.path_input.SetValue(dialog.GetPath())
        dialog.Destroy()


# Шаг 6: Типы файлов b период
class FileTypeSelectionStep(WizardStep):
    def __init__(self, parent):
        super().__init__(parent)
        self.filters_choices = (
            ("Музыка", enums.MessagesFilter.AUDIO),
            ("Фото", enums.MessagesFilter.PHOTO),
            ("Видео", enums.MessagesFilter.VIDEO),
            ("Фото и видео", enums.MessagesFilter.PHOTO_VIDEO),
            ("Файлы", enums.MessagesFilter.DOCUMENT),
            ("Голосовые", enums.MessagesFilter.AUDIO_VIDEO_NOTE),
        )
        self.choice_file_type = wx.Choice(
            self, choices=[c[0] for c in self.filters_choices]
        )
        self.choice_file_type.SetSelection(0)

        self.step_sizer.Add(
            wx.StaticText(self, label="Выберите типы файлов:"), 0, wx.ALL, 5
        )
        self.step_sizer.Add(self.choice_file_type, 0, wx.ALL, 5)
        h_sizer_2 = wx.BoxSizer(wx.HORIZONTAL)
        self.checkbox_period = wx.CheckBox(self, label="За период")
        self.checkbox_period.Bind(wx.EVT_CHECKBOX, self.on_check_period)
        self.start_date = wx.adv.DatePickerCtrl(self, wx.ID_ANY)
        self.start_date.Disable()
        self.end_date = wx.adv.DatePickerCtrl(self, wx.ID_ANY)
        self.end_date.Disable()
        h_sizer_2.Add(self.checkbox_period, 0, wx.ALL, 5)
        h_sizer_2.Add(self.start_date, 0, wx.ALL, 5)
        h_sizer_2.Add(self.end_date, 0, wx.ALL, 5)
        self.step_sizer.Add(wx.StaticText(self, label="Фильтр по дате:"), 0, wx.ALL, 5)
        self.step_sizer.Add(h_sizer_2, 0, wx.EXPAND)

    def can_proceed(self):
        start_date = WxToPyDate(self.start_date.GetValue())
        end_date = WxToPyDate(self.end_date.GetValue())
        if start_date > end_date and self.checkbox_period.IsChecked():
            wx.MessageBox(
                "Дата начала не может быть из будущего",
                "Ошибка",
                wx.OK | wx.ICON_ERROR,
            )
            self.start_date.SetFocus()
            return False

        return True

    def on_check_period(self, event):
        event.Skip()
        datepickers = [self.start_date, self.end_date]
        for dp in datepickers:
            if self.checkbox_period.IsChecked():
                dp.Enable()
            else:
                dp.Disable()


# Шаг 7: Экспорт
class ExportStep(WizardStep):
    def __init__(self, parent, client):
        super().__init__(parent)
        self.client = client
        self.step_sizer.Add(
            wx.StaticText(self, label="Прогресс экспорта:"), 0, wx.ALL, 5
        )
        self.progress_text = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.progress_text.SetMinSize((600, 400))
        self.step_sizer.Add(self.progress_text, 1, wx.EXPAND | wx.ALL, 5)

    def update_progress(self, message):
        if len(self.progress_text.GetValue()) > 2000000:
            self.progress_text.SetValue("")
        self.progress_text.AppendText(message + "\n")


async def main():
    app = TGFileExporter()
    await app.MainLoop()


if __name__ == "__main__":
    asyncio.run(main())
