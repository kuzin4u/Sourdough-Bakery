#!/usr/bin/env python3
"""PreToolUse-хук Масса Мадре: защита ключевых страниц и запрет адресов API в страницах.

1. catalog.html — главная (build.sh копирует её в index.html), sourdough-shop.html —
   оформление заказа. Правка только с разрешением владельца: запустить claude
   с ALLOW_MAIN_EDIT=1. В shell блокируется только запись, где страница — цель
   (> / >> перед именем, sed -i, tee, cp в неё, mv, rm, truncate, dd of=);
   упоминание страницы рядом с символом > запись не считается.
2. Адреса API в .html запрещены — их подставляет build.sh (safe_replace)
   через плейсхолдеры BOT_API_URL / REVIEWS_API_URL / ORDERS_API_URL.
3. Ключ Anthropic (префикс — константа SECRET) запрещён в любой правке любого файла и в записи
   через shell — ключ живёт только в Environment бота на Render. Разрешения нет.
Код выхода 2 = блокировать; stderr получает Claude.
Журнал: .claude/hooks.log (JSON по строке), сводка — session_summary.py.
"""
import json
import os
import re
import sys

HOOK = "guard"
PROTECTED = ("catalog.html", "sourdough-shop.html")
API_URL = re.compile(r"https://[a-z0-9-]+\.onrender\.com")
WRITE_OPS = re.compile(r"(>>?|\btee\b|\bsed\b[^|;&]*\s-i|\bmv\b|\bcp\b|\brm\b|\btruncate\b|\bdd\b|\bperl\b[^|;&]*\s-i)")


def _target_patterns(page: str) -> re.Pattern:
    """Команды shell, где защищённая страница — цель записи, а не просто упоминание."""
    path = r"""['"]?(?:[\w.~/-]*/)?""" + re.escape(page) + r"""['"]?"""
    end = r"(?=\s|$|[|;&)])"
    seg = r"[^|;&\n]*"  # в пределах одной команды конвейера
    return re.compile("|".join([
        r">>?\s*" + path + end,                                   # > файл, >> файл, 2> файл
        r"\btee\b" + seg + r"\s" + path + end,                    # tee [-a] файл
        r"\b(?:sed|perl)\b" + seg + r"\s-i\S*" + seg + r"\s" + path + end,  # sed -i … файл
        r"\bcp\b" + seg + r"\s" + path + r"\s*(?=$|[|;&\n)])",    # cp … файл — файл последним аргументом
        r"\b(?:mv|rm|truncate)\b" + seg + r"\s" + path + end,     # переместить, удалить, обрезать
        r"\bdd\b" + seg + r"\bof=" + path + end,                  # dd of=файл
    ]))


PAGE_WRITES = {page: _target_patterns(page) for page in PROTECTED}
MSG_MAIN = ("{page} — защищённая страница (главная catalog.html или оформление заказа sourdough-shop.html). "
            "Остановись и спроси владельца; правка возможна только с его разрешения.")
MSG_API = ("Адрес API в странице запрещён: используй плейсхолдер BOT_API_URL, "
           "REVIEWS_API_URL или ORDERS_API_URL — его подставит build.sh.")
# Префикс собран из частей, чтобы сам хук и тесты не содержали его целиком и оставались редактируемыми.
SECRET = "sk-" + "ant-"
MSG_SECRET = ("Ключ Anthropic в файле запрещён: ANTHROPIC_API_KEY живёт только в Environment "
              "сервиса sourdough-bakery-bot на Render. Не записывай ключ — спроси владельца.")

def log_event(hook, data, decision, reason=""):
    """Пишет одну строку JSON в .claude/hooks.log. Сбой журнала не мешает работе."""
    try:
        import datetime, pathlib
        inp = data.get("tool_input", {}) or {}
        target = inp.get("file_path") or inp.get("notebook_path") or (inp.get("command") or "")[:120]
        rec = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "session": data.get("session_id", ""),
            "hook": hook,
            "tool": data.get("tool_name", ""),
            "target": target,
            "decision": decision,
            "reason": reason,
        }
        root = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
        with (root / ".claude" / "hooks.log").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def edited_text(inp: dict) -> str:
    parts = [inp.get("content", ""), inp.get("new_string", ""), inp.get("new_source", "")]
    for e in inp.get("edits", []) or []:
        parts.append(e.get("new_string", ""))
    return "\n".join(p for p in parts if p)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    tool = data.get("tool_name", "")
    inp = data.get("tool_input", {}) or {}
    allow_main = os.environ.get("ALLOW_MAIN_EDIT") == "1"

    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = inp.get("file_path") or inp.get("notebook_path") or ""
        if SECRET in edited_text(inp):
            log_event(HOOK, data, "BLOCK", "secret_in_edit")
            print(MSG_SECRET, file=sys.stderr)
            return 2
        page = os.path.basename(path)
        if page in PROTECTED and not allow_main:
            log_event(HOOK, data, "BLOCK", "main_page")
            print(MSG_MAIN.format(page=page), file=sys.stderr)
            return 2
        if path.endswith(".html") and API_URL.search(edited_text(inp)):
            log_event(HOOK, data, "BLOCK", "api_url_in_html")
            print(MSG_API, file=sys.stderr)
            return 2
    elif tool == "Bash":
        cmd = inp.get("command", "")
        if SECRET in cmd and WRITE_OPS.search(cmd):
            log_event(HOOK, data, "BLOCK", "secret_shell")
            print(MSG_SECRET + " (команда shell похожа на запись ключа в файл)", file=sys.stderr)
            return 2
        page = next((p for p, rx in PAGE_WRITES.items() if rx.search(cmd)), None)
        if page and not allow_main:
            log_event(HOOK, data, "BLOCK", "main_page_shell")
            print(MSG_MAIN.format(page=page) + " (команда shell похожа на запись в защищённую страницу)", file=sys.stderr)
            return 2

    log_event(HOOK, data, "ALLOW")
    return 0


if __name__ == "__main__":
    sys.exit(main())
