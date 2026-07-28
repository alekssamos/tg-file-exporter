from datetime import datetime, timezone

import wx  # type:ignore
from loguru import logger


def WxToPyDate(date: wx._core.DateTime, is_end: bool = False) -> datetime:
    hour: int = 0
    minute: int = 0
    second: int = 0
    if is_end:
        hour = 23
        minute = 59
        second = 59
    logger.debug(f"wx date is {date}")
    # Undocumented: wx DateTime returns Month from 0, not from 1
    return datetime(
        date.GetYear(), date.GetMonth() + 1, date.GetDay(), hour, minute, second, 0, timezone.utc
    )


