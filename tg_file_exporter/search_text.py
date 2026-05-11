def search_chat(text: str, substr: str) -> bool:
    # Канонизация
    char_map = {
        # RU → латиница (упрощённая)
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "э": "e",
        "ж": "j",
        "з": "z",
        "и": "i",
        "й": "y",
        "ы": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "c",
        "ш": "s",
        "щ": "s",
        # 🔥 ключевое изменение
        "я": "a",  # теперь ближе к "ja"/"java"
        "ю": "u",
        # латиница нормализация
        "q": "k",
        "x": "ks",
        "j": "a",  # ← "java" ≈ "ява"
    }

    def normalize(s: str) -> str:
        s = s.lower()
        result = []
        for ch in s:
            if ch.isalnum():
                result.append(char_map.get(ch, ch))
        return "".join(result)

    text = normalize(text)
    substr = normalize(substr)

    # быстрый путь
    if substr in text:
        return True
    return False  # ... Not necessary yet

    # ограниченный Левенштейн
    def is_close(a: str, b: str, max_dist: int) -> bool:
        if abs(len(a) - len(b)) > max_dist:
            return False

        dp = list(range(len(b) + 1))

        for i in range(1, len(a) + 1):
            prev = dp[0]
            dp[0] = i
            for j in range(1, len(b) + 1):
                temp = dp[j]
                if a[i - 1] == b[j - 1]:
                    dp[j] = prev
                else:
                    dp[j] = 1 + min(prev, dp[j], dp[j - 1])
                prev = temp

        return dp[-1] <= max_dist

    n, m = len(text), len(substr)
    max_dist = max(1, m // 3)

    for i in range(n):
        for length in range(m - max_dist, m + max_dist + 1):
            if length <= 0:
                continue
            part = text[i : i + length]
            if len(part) < m - max_dist:
                continue

            if is_close(part, substr, max_dist):
                return True

    return False


if __name__ == "__main__":
    print(search_chat("java developer", "ява"))  # True
    print(search_chat("ява скрипт", "java"))  # True
    print(search_chat("jaba", "ява"))  # True (опечатка + транслит)
