# TG File Exporter

Программа для экспорта файлов из Telegram чатов.

## Установка

1. Установите uv (если у вас его ещё нет)
  
  Выберите один из способов
  
  macOS, Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  
  Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  
  PyPI: `pip install uv` or `pipx install uv`

2. Установите зависимости: `uv sync`
3. Склонируйте репозиторий: `git clone https://github.com/alekssamos/tg-file-exporter/`
4. Получите api_id и api_hash от [Telegram API](https://my.telegram.org/auth)
5. Замените плейсхолдеры в `tg_file_exporter/__init__.py` на реальные значения.

## Запуск

Из исходников: `uvw run -m tg_file_exporter`

Или автоматически установить из PyPI последнюю версию и запустить: `uvx tg-file-exporter`

## Использование

Программа проведет вас через пошаговый мастер:
1. Вход в аккаунт
2. Выбор чата
3. Выбор темы (если есть)
4. Выбор пути сохранения
5. Выбор типов файлов b периода
6. Непосредственно экспорт файлов

## Todo

Доделать поиск, сейчас он не работает. Пользуйтесь первой буквой в списке.


Copyright 2025 @alekssamos
