#!/usr/bin/env python3
"""Тесты guard.py и журнала. Запуск из корня репозитория:
   python3 .claude/hooks/test_guard.py
Работает во временной папке — реальный .claude/hooks.log не трогает."""
import json, os, pathlib, subprocess, sys, tempfile
HERE = pathlib.Path(__file__).resolve().parent
HOOK, SUMMARY = HERE / "guard.py", HERE / "session_summary.py"
KEY = "sk-" + "ant-" + "api03-TESTONLY"  # поддельный ключ; собран из частей, чтобы файл не блокировался хуком
CASES = [
    ("правка главной → блок", {"tool_name": "Edit", "tool_input": {"file_path": "website/sourdough-shop.html", "new_string": "x"}}, {}, 2),
    ("правка главной с ALLOW_MAIN_EDIT=1 → проходит", {"tool_name": "Edit", "tool_input": {"file_path": "website/sourdough-shop.html", "new_string": "x"}}, {"ALLOW_MAIN_EDIT": "1"}, 0),
    ("адрес onrender.com в .html → блок", {"tool_name": "Edit", "tool_input": {"file_path": "website/schedule.html", "new_string": "fetch('https://marketplace-api-ujfh.onrender.com/api')"}}, {}, 2),
    ("адрес в Write целиком → блок", {"tool_name": "Write", "tool_input": {"file_path": "website/card.html", "content": "<script>const u='https://bot-x.onrender.com'</script>"}}, {}, 2),
    ("адрес в MultiEdit → блок", {"tool_name": "MultiEdit", "tool_input": {"file_path": "website/schedule.html", "edits": [{"old_string": "a", "new_string": "https://a-b.onrender.com"}]}}, {}, 2),
    ("плейсхолдер вместо адреса → проходит", {"tool_name": "Edit", "tool_input": {"file_path": "website/schedule.html", "new_string": "fetch(BOT_API_URL)"}}, {}, 0),
    ("адрес в коде бота, не в странице → проходит", {"tool_name": "Write", "tool_input": {"file_path": "bot/app.py", "content": "URL='https://a.onrender.com'"}}, {}, 0),
    ("запись в главную через shell → блок", {"tool_name": "Bash", "tool_input": {"command": "sed -i s/a/b/ website/sourdough-shop.html"}}, {}, 2),
    ("чтение главной через shell → проходит", {"tool_name": "Bash", "tool_input": {"command": "grep title website/sourdough-shop.html"}}, {}, 0),
    ("чтение файла Read → проходит", {"tool_name": "Read", "tool_input": {"file_path": "website/sourdough-shop.html"}}, {}, 0),
    ("правка каталога → блок", {"tool_name": "Edit", "tool_input": {"file_path": "website/catalog.html", "new_string": "x"}}, {}, 2),
    ("Write в каталог → блок", {"tool_name": "Write", "tool_input": {"file_path": "website/catalog.html", "content": "x"}}, {}, 2),
    ("правка каталога с ALLOW_MAIN_EDIT=1 → проходит", {"tool_name": "Edit", "tool_input": {"file_path": "website/catalog.html", "new_string": "x"}}, {"ALLOW_MAIN_EDIT": "1"}, 0),
    ("запись в каталог через shell → блок", {"tool_name": "Bash", "tool_input": {"command": "echo x >> website/catalog.html"}}, {}, 2),
    ("чтение каталога через shell → проходит", {"tool_name": "Bash", "tool_input": {"command": "grep BOT_API website/catalog.html"}}, {}, 0),
    ("правка карточки, не защищённой страницы → проходит", {"tool_name": "Edit", "tool_input": {"file_path": "website/card-tartin.html", "new_string": "x"}}, {}, 0),
    ("ключ Anthropic в Edit → блок", {"tool_name": "Edit", "tool_input": {"file_path": "telegram-bot-python/main.py", "new_string": f"KEY='{KEY}'"}}, {}, 2),
    ("ключ Anthropic в Write → блок", {"tool_name": "Write", "tool_input": {"file_path": "notes.txt", "content": f"ANTHROPIC_API_KEY={KEY}"}}, {}, 2),
    ("ключ Anthropic в MultiEdit → блок", {"tool_name": "MultiEdit", "tool_input": {"file_path": "docs/SPEC.md", "edits": [{"old_string": "a", "new_string": KEY}]}}, {}, 2),
    ("ключ Anthropic через shell → блок", {"tool_name": "Bash", "tool_input": {"command": f"echo ANTHROPIC_API_KEY={KEY} >> vk-bot/config.txt"}}, {}, 2),
    ("ключ Anthropic с ALLOW_MAIN_EDIT=1 → всё равно блок", {"tool_name": "Edit", "tool_input": {"file_path": "website/sourdough-shop.html", "new_string": KEY}}, {"ALLOW_MAIN_EDIT": "1"}, 2),
    ("имя переменной без ключа → проходит", {"tool_name": "Edit", "tool_input": {"file_path": "docs/ARCHITECTURE.md", "new_string": "ANTHROPIC_API_KEY — в Environment бота"}}, {}, 0),
    # Бывшие ложные срабатывания (сессия 2026-09-24): страница упомянута, но не цель записи
    ("чтение с 2>&1 рядом с главной → проходит", {"tool_name": "Bash", "tool_input": {"command": "ls telegram-bot 2>&1; grep -n FAQ website/sourdough-shop.html"}}, {}, 0),
    ("> внутри регулярного выражения → проходит", {"tool_name": "Bash", "tool_input": {"command": "grep -oE \"<title>[^<]*</title>\" website/sourdough-shop.html website/catalog.html"}}, {}, 0),
    ("имя страницы в тексте heredoc → проходит", {"tool_name": "Bash", "tool_input": {"command": "python3 - <<'EOF'\nrep('docs/FAQ_unified.md', '`sourdough-shop.html` (виджет)', 'x')\nEOF"}}, {}, 0),
    ("вывод чтения каталога в другой файл → проходит", {"tool_name": "Bash", "tool_input": {"command": "grep BOT_API website/catalog.html > /tmp/out.txt"}}, {}, 0),
    ("копия каталога в другой файл → проходит", {"tool_name": "Bash", "tool_input": {"command": "cp website/catalog.html /tmp/catalog-backup.html"}}, {}, 0),
    # Настоящая запись в защищённую страницу
    ("> в главную → блок", {"tool_name": "Bash", "tool_input": {"command": "echo x > website/sourdough-shop.html"}}, {}, 2),
    (">> в кавычках → блок", {"tool_name": "Bash", "tool_input": {"command": "echo x >>\"website/catalog.html\""}}, {}, 2),
    ("sed -i '' в каталог → блок", {"tool_name": "Bash", "tool_input": {"command": "sed -i '' s/a/b/ website/catalog.html"}}, {}, 2),
    ("tee в каталог → блок", {"tool_name": "Bash", "tool_input": {"command": "cat /tmp/x | tee -a website/catalog.html"}}, {}, 2),
    ("cp поверх главной → блок", {"tool_name": "Bash", "tool_input": {"command": "cp /tmp/x.html website/sourdough-shop.html"}}, {}, 2),
    ("mv каталога → блок", {"tool_name": "Bash", "tool_input": {"command": "mv website/catalog.html /tmp/"}}, {}, 2),
    ("rm каталога → блок", {"tool_name": "Bash", "tool_input": {"command": "rm website/catalog.html"}}, {}, 2),
    ("запись в каталог с ALLOW_MAIN_EDIT=1 → проходит", {"tool_name": "Bash", "tool_input": {"command": "echo x >> website/catalog.html"}}, {"ALLOW_MAIN_EDIT": "1"}, 0),
]
def run():
    tmp = tempfile.mkdtemp(); (pathlib.Path(tmp) / ".claude").mkdir()
    fails = 0
    for name, data, env, want in CASES:
        data = dict(data, session_id="test-session-0001")
        e = dict(os.environ, CLAUDE_PROJECT_DIR=tmp, **env)
        r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(data), text=True, capture_output=True, env=e)
        ok = r.returncode == want
        fails += not ok
        print(f"{'OK ' if ok else 'FAIL'} {name} (код {r.returncode}, ждали {want})")
    log = (pathlib.Path(tmp) / ".claude" / "hooks.log").read_text().splitlines()
    ok = len(log) == len(CASES)
    fails += not ok
    print(f"{'OK ' if ok else 'FAIL'} журнал: {len(log)} записей из {len(CASES)}")
    s = subprocess.run([sys.executable, str(SUMMARY)], text=True, capture_output=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=tmp))
    ok = "Блокировки: 20" in s.stdout
    fails += not ok
    print(f"{'OK ' if ok else 'FAIL'} сводка видит 20 блокировок")
    print("\n--- пример сводки ---\n" + s.stdout)
    print("ИТОГ:", "все тесты пройдены" if not fails else f"провалено: {fails}")
    return 1 if fails else 0
if __name__ == "__main__":
    sys.exit(run())
