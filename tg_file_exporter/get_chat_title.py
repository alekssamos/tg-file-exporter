from pyrogram.types import Chat


def getChatTitle(chat: Chat) -> str:
    name: str = chat.title or (chat.first_name or "") + " " + (chat.last_name or "")
    return name.strip() or "deleted?"
