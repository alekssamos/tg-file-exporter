# TG File Exporter

Программа для экспорта файлов из Telegram чатов.

## Установка

1. Установите uv (если у вас его ещё нет)
  Выберите один из способов
  macOS, Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  PyPI: `pip install uv` or `pipx install uv`
2. Установите зависимости: `uv sync`
3. Получите api_id и api_hash от [Telegram API](https://my.telegram.org/auth)
4. Замените плейсхолдеры в main.py на реальные значения.

## Запуск

`uvw run -m tg_file_exporter`

## Использование

Программа проведет вас через пошаговый мастер:
1. Вход в аккаунт
2. Выбор чата
3. Выбор темы (если есть)
4. Выбор пути сохранения
5. Выбор типов файлов b периода
6. Непосредственно экспорт файлов

Copyright 2025 @alekssamos
