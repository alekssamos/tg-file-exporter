import os
import os.path
import tempfile

import wx  # type:ignore
from loguru import logger

from .base_wizard_step import WizardStep


def save_path(path=""):
    _filename = os.path.join(tempfile.gettempdir(), "tg_file_exporter_selected_dir")
    if path:
        with open(_filename, "w", encoding="UTF-8") as f:
            f.write(path)
    if os.path.isfile(_filename) and os.path.getsize(_filename) > 0:
        with open(_filename, "r", encoding="UTF-8") as f:
            return f.read(1024).strip()
    return ""


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
