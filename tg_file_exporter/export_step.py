import wx  # type:ignore

from .base_wizard_step import WizardStep


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
