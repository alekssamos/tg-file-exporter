import wx


# Базовый класс для шагов
class WizardStep(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.step_sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.step_sizer)

    def can_proceed(self):
        return True
