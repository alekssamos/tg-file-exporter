import re

import wx  # type:ignore
from loguru import logger
from pyrogram.errors import BadRequest, RPCError, SessionPasswordNeeded

from .base_wizard_step import WizardStep


class AuthData:
    def __init__(self, phone, sent_code):
        self.phone = phone
        self.sent_code = sent_code


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

    @logger.catch
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
                # wx.MessageBox(
                # "Код отправлен на ваш телефон.",
                # "Информация",
                # wx.OK | wx.ICON_INFORMATION,
                # )
            except BadRequest as e:
                logger.exception("error in sending code")
                wx.MessageBox(
                    f"Ошибка отправки кода: {e!s}", "Ошибка", wx.OK | wx.ICON_ERROR
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

    @logger.catch
    async def on_sign_in(self, event):
        code = self.code_input.GetValue() or ""
        if code:
            try:
                logger.info("trying sign in")
                await self.client.sign_in(
                    self.auth_data.phone, self.auth_data.sent_code.phone_code_hash, code
                )
                self.code_entered = True
                logger.info("authorized successfully")
            except SessionPasswordNeeded:
                self.code_entered = True
                self.password_needed = True
                logger.info("needed password")
            except BadRequest as e:
                logger.exception("error sign in")
                wx.MessageBox(f"Ошибка входа: {e!s}", "Ошибка", wx.OK | wx.ICON_ERROR)

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
        self.password_hint_label = wx.StaticText(self, label="Подсказка")
        self.password_hint_label.SetCanFocus(True)
        self.step_sizer.Add(self.password_hint_label, 0, wx.EXPAND | wx.ALL, 5)

    @logger.catch
    async def set_password_hint(self):
        password_hint = (await self.client.get_password_hint()) or ""
        self.password_hint_label.SetLabelText("Подсказка: " + password_hint)

    @logger.catch
    async def on_submit(self, event):
        password = self.password_input.GetValue()
        try:
            logger.info("trying password auth")
            await self.client.check_password(password)
            self.password_entered = True
        except RPCError as e:
            logger.exception("error password")
            wx.MessageBox(f"Ошибка пароля: {e!s}", "Ошибка", wx.OK | wx.ICON_ERROR)

    def can_proceed(self):
        return self.password_entered
