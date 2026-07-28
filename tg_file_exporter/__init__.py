import asyncio
import os
import platform
import sys
from threading import Lock

import aiofiles
import wx  # type:ignore
import wx.adv  # type:ignore
from loguru import logger
from pyrogram import Client, enums, errors
from pyrogram.types import Message
from wxasync import AsyncBind, StartCoroutine, WxAsyncApp  # type:ignore

from .auth_steps import AuthData, CodeStep, PasswordStep, PhoneStep
from .base_wizard_step import WizardStep
from .chat_selection_step import ChatSelectionStep  # type:ignore
from .file_type_selection_step import FileTypeSelectionStep  # type:ignore
from .get_chat_title import getChatTitle
from .path_selection_step import PathSelectionStep  # type:ignore
from .search_messages_by_date import search_messages_by_date  # type:ignore
from .topic_selection_step import TopicSelectionStep  # type:ignore
from .wx_to_py_date import WxToPyDate  # type:ignore

MAX_WORKERS = 4
NEXT_BUTTON_LABEL = "&Далее>"
LOCK = Lock()

logger.remove()
if not getattr(sys, "frozen", False):
    logger.add(
        sys.stderr,
        level="INFO",
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

if getattr(sys, "frozen", False):
    logger.info("program is frozen exe")
else:
    logger.info("program is a .py script")


def _links_to_html(entities: list, plain_text: str, html_text: str) -> str:
    urls = []

    for ent in entities:
        if ent.type != enums.MessageEntityType.URL:
            continue

        start = ent.offset
        end = start + ent.length

        urls.append(plain_text[start:end])
    content = html_text
    prefix = ""
    replaced = set()
    for url in urls:
        if url in replaced:
            continue
        prefix = ""
        if "://" not in url:
            prefix = "http://"
        content = content.replace(
            url,
            f'<a href="{prefix + url}">{url}</a>',
            1,
        )
        replaced.add(url)
    return content


def _wrap_message(message: Message) -> str:
    dt = message.date
    formatted_date = (
        f"{dt.strftime('%d.%m.%Y')} {dt.hour}:{dt.strftime('%M:%S')}" if dt else ""
    )
    t = message.caption or message.text
    e = message.entities or message.caption_entities or []
    message_content = _links_to_html(e, t, t.html)  # type:ignore
    return f"""
<div class="message" id="msg{message.id}">
<h3>{formatted_date}</h3>
<p>{message_content}</p>
</div>
    """


class TGFileExporter(WxAsyncApp):
    def __init__(self):
        super().__init__(sleep_duration=0.000001)

    @logger.catch
    def OnInit(self):
        # Параметры для Kurigram
        self.api_id = 2040
        self.api_hash = "b18441a1ff607e10a989891a5462e627"
        self.client = Client(
            "tg_file_exporter",
            api_id=self.api_id,
            api_hash=self.api_hash,
            max_concurrent_transmissions=6,
            no_updates=True,
            workdir=os.path.abspath("."),
        )
        self.wizard = ExportWizard(None, title="TG File Exporter", client=self.client)
        self.wizard.Show()
        return True


class ExportWizard(wx.Frame):
    def __init__(self, parent, title, client):
        super().__init__(parent, title=title, name="tg_exporter", size=(600, 400))
        self.export_thread = None
        self.client = client
        self.auth_data = AuthData(None, None)
        self.errors_count: int = 0
        self.success_count: int = 0
        self.close_running: bool = False
        self.completed_export: bool = False
        self.only_links: bool = False
        self.messages_with_links: list = []
        self.main_panel = wx.Panel(self)
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.main_panel.SetSizer(self.main_sizer)

        # Шаги мастера
        self.steps: list[WizardStep] = []
        self.current_step = 0

        # Кнопки навигации
        self.button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.back_button = wx.Button(self.main_panel, label="<&Назад")
        self.next_button = wx.Button(self.main_panel, label=NEXT_BUTTON_LABEL)
        self.cancel_button = wx.Button(self.main_panel, label="&Отмена")
        self.gh_button = wx.Button(self.main_panel, label="GitHub")
        self.gh_button.Bind(wx.EVT_BUTTON, self.on_gh)

        AsyncBind(wx.EVT_BUTTON, self.on_back, self.back_button)
        AsyncBind(wx.EVT_BUTTON, self.on_next, self.next_button)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key_up)
        AsyncBind(wx.EVT_BUTTON, self.on_cancel, self.cancel_button)
        AsyncBind(wx.EVT_CLOSE, self.on_cancel, self)

        self.button_sizer.Add(self.back_button, 0, wx.ALL, 5)
        self.button_sizer.Add(self.next_button, 0, wx.ALL, 5)
        self.button_sizer.Add(self.cancel_button, 0, wx.ALL, 5)
        self.button_sizer.Add(self.gh_button, 0, wx.ALL, 5)

        self.main_sizer.Add(self.button_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        # Инициализация шагов
        self.init_steps()
        # Добавить все шаги в main_sizer для видимости
        for step in self.steps:
            self.main_sizer.Add(step, 1, wx.EXPAND | wx.ALL, 5)
        StartCoroutine(self.show_step(0), self)

        self.Centre()

    def on_gh(self, event):
        import webbrowser

        webbrowser.open("https://github.com/alekssamos/tg-file-exporter/")

    def on_key_up(self, event):
        key = event.GetKeyCode()
        event.Skip()
        if key in [10, 13, 370] and self.current_step < 7:
            StartCoroutine(self.on_next(event), self)
        if key == 27 and self.current_step < 7:
            StartCoroutine(self.on_cancel(event), self)

    @logger.catch
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
        # Шаг 7: Типы файлов и период
        self.steps.append(FileTypeSelectionStep(self.main_panel))
        # Шаг 8: Экспорт
        self.steps.append(ExportStep(self.main_panel, self.client))

    async def check_auth(self) -> bool:
        try:
            await self.client.get_me()
            return True
        except errors.exceptions.unauthorized_401.AuthKeyUnregistered:
            return False
        return False

    @logger.catch
    async def show_step(self, step_index):
        # Пропустить шаги авторизации если авторизован
        if step_index == 0:
            if (await self.client.connect()) and (await self.check_auth()):
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
        self.back_button.Enable(step_index > 0 and step_index != 3)
        self.next_button.SetLabel(
            NEXT_BUTTON_LABEL if step_index < len(self.steps) - 2 else "&Экспорт"
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

    @logger.catch
    async def on_back(self, event):
        logger.debug(f"back: current_step={self.current_step}")
        if self.current_step > 0 and self.current_step != 3:
            self.current_step -= 1
            if self.current_step == 4 and not self.steps[self.current_step].has_topics:
                self.current_step -= 1
            await self.show_step(self.current_step)

    @logger.catch
    async def on_next(self, event):
        logger.debug(f"next: current_step={self.current_step}")
        ############### events ###<
        autoskip: bool = False
        # отправить код
        if self.current_step == 0:
            await self.steps[self.current_step].on_send_code(None)
        # Проверить код
        if self.current_step == 1:
            await self.steps[self.current_step].on_sign_in(None)
            # проверить нужен ли пароль?
            if not self.steps[self.current_step].password_needed:
                self.current_step = 3
                autoskip = True
            else:
                await self.steps[2].set_password_hint()
        # Проверить пароль
        if self.current_step == 2 and self.steps[1].password_needed:
            await self.steps[self.current_step].on_submit(None)
        ############### events ###>
        if self.current_step < len(self.steps) - 1:
            # Проверить, можно ли перейти дальше
            if autoskip:
                await self.show_step(self.current_step)
            if not autoskip and self.steps[self.current_step].can_proceed():
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
        if self.close_running:
            return
        if (
            not self.completed_export
            and wx.MessageBox(
                "Отменить и выйти из программы?",
                "Закрыть программу?",
                wx.YES_NO | wx.ICON_WARNING | wx.NO_DEFAULT,
            )
            != wx.YES
        ):
            return
        self.close_running = True
        await self._shutdown()

    async def _shutdown(self):
        """Properly shut down all resources and exit the application."""
        # Cancel export tasks
        if self.export_thread:
            self.export_thread.cancel()
        if hasattr(self, "workers"):
            for worker in self.workers:
                worker.cancel()

        # Cancel chat loading thread
        if (
            len(self.steps) > 3
            and hasattr(self.steps[3], "update_chats_thread")
            and self.steps[3].update_chats_thread
        ):
            self.steps[3].update_chats_thread.cancel()

        # Disconnect Telegram client
        try:
            await self.client.disconnect()
        except ConnectionError:
            pass

        # Close cache database
        if len(self.steps) > 3 and hasattr(self.steps[3], "adc"):
            await self.steps[3].adc.close()

        # Destroy window and stop wx event loop
        self.Destroy()
        try:
            wx.GetApp().ExitMainLoop()
        except RuntimeError:
            pass

    @logger.catch
    async def start_export(self):
        self.q: asyncio.queues.Queue = asyncio.queues.Queue(maxsize=MAX_WORKERS)
        self.workers = []
        for _ in range(MAX_WORKERS + 1):
            self.workers.append(StartCoroutine(self.download_media_worker(), self))
        self.export_thread = StartCoroutine(self.do_export(), self)

    @logger.catch
    async def do_export(self):
        # скрыть не нужужные кнопки
        self.back_button.Hide()
        self.next_button.Hide()
        # Собрать параметры
        chat = self.steps[3].selected_chat
        topic = self.steps[4].selected_topic
        path = self.steps[5].path_input.GetValue()
        min_date = None
        max_date = None
        message_filter = self.steps[6].filters_choices[
            self.steps[6].choice_file_type.GetSelection()
        ][1]
        self.only_links = (
            self.steps[6].filters_choices[
                self.steps[6].choice_file_type.GetSelection()
            ][1]
            == enums.MessagesFilter.URL
        )
        if self.steps[6].checkbox_period.IsChecked():
            min_date = WxToPyDate(self.steps[6].start_date.GetValue())
            max_date = WxToPyDate(self.steps[6].end_date.GetValue(), True)

        wx.CallAfter(self.steps[-1].update_progress, "Экспорт начат...")

        # параметры поиска
        kwargs = {"app": self.client, "chat_id": chat.chat.id, "filter": message_filter}
        # заполняем дату и тему, если указана
        if min_date:
            kwargs["min_date"] = min_date
            logger.info(f"min_date={min_date}")
        if max_date:
            kwargs["max_date"] = max_date
            logger.info(f"max_date={max_date}")
        if topic:
            kwargs["message_thread_id"] = topic
            logger.info(f"topic={topic}")
        # Использовать search_messages для фильтрации
        i: int = 0
        async for message in search_messages_by_date(**kwargs):
            i += 1
            await self.q.put((message, path))

        await self.q.join()
        if self.only_links:
            async with aiofiles.open(
                os.path.join(path, "links_" + str(chat.chat.id) + ".html"),
                "w",
                encoding="UTF-8",
            ) as fpl:
                await fpl.write(
                    """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{chat_title}</title>
</head>
<body>
<header>
<h2>{chat_title}</h2>
</header>
<main>
<div class="messages">{links}</div>
</main>
<footer>
<p>Powered by tg-file-exporter</p>
</footer>
</body>
</html>
                """.format(
                        chat_title=getChatTitle(chat.chat),
                        links="\n".join(self.messages_with_links),
                    )
                )
            self.messages_with_links.clear()
        self.completed_export = True
        self.cancel_button.SetLabel("&Готово")
        self.cancel_button.SetFocus()
        wx.CallAfter(
            self.steps[-1].update_progress,
            f"Экспорт завершен! Скачано {self.success_count} файлов, {self.errors_count} ошибок.",
        )
        wx.CallAfter(
            wx.MessageBox,
            f"Экспорт завершен!  Скачано {self.success_count} файлов,  {self.errors_count} ошибок.",
            "Информация",
            wx.OK | wx.ICON_INFORMATION,
        )
        if platform.platform().startswith("Win"):
            await asyncio.create_subprocess_exec(["explorer.exe", path])  # type:ignore

    @logger.catch
    async def download_media_worker(self):
        while True:
            try:
                message, path = await self.q.get()
                if not path.endswith(os.path.sep):
                    path = path + os.path.sep
                # собрать сообщения со ссылками
                if self.only_links:
                    if (message.text or message.caption) is None:
                        continue
                    self.messages_with_links.append(_wrap_message(message))
                if not self.only_links:
                    # Скачать медиа
                    if message.media not in [
                        enums.MessageMediaType.AUDIO,
                        enums.MessageMediaType.DOCUMENT,
                    ]:
                        await message.download(path)
                    elif hasattr(message.media, "value"):
                        # https://docs.kurigram.live/api/types/Message/
                        media = getattr(message, message.media.value)
                        file_name = media.file_name
                        for simbel in r"""{}/\'*<>"~""":
                            if simbel in file_name:
                                file_name = file_name.replace(simbel, "_")
                        file_name_parts = file_name.split(".")
                        ext = file_name_parts.pop()
                        file_name_parts.append(str(message.id))
                        file_name_parts.append(ext)
                        file_name = ".".join(file_name_parts)
                        if not os.path.isfile(path + file_name):
                            await message.download(path + file_name)
                        else:
                            logger.info(f"file {file_name} already exists, skiping...")
                with LOCK:
                    self.success_count += 1
                wx.CallAfter(
                    self.steps[-1].update_progress, f"Скачано {self.success_count}"
                )

            except (
                errors.RPCError,
                ValueError,
                AttributeError,
                OSError,
                FileExistsError,
            ) as e:
                logger.exception("error in worker")
                await message.forward("me")
                with LOCK:
                    self.errors_count += 1
                wx.CallAfter(
                    self.steps[-1].update_progress,
                    f"Ошибка #{self.errors_count}: {e!s}",
                )
            finally:
                try:
                    self.q.task_done()
                except ValueError:
                    pass


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
        # self.progress_text.AppendText(message + "\n")
        self.progress_text.SetValue(message)


async def main():
    app = TGFileExporter()
    await app.MainLoop()


if __name__ == "__main__":
    asyncio.run(main())
