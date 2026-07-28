import wx  # type:ignore
from pyrogram import enums

from .base_wizard_step import WizardStep
from .wx_to_py_date import WxToPyDate


# Шаг 6: Типы файлов и период
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
            ("Ссылки", enums.MessagesFilter.URL),
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
        end_date = WxToPyDate(self.end_date.GetValue(), True)
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
