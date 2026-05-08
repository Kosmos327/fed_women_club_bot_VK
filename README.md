# Federal Women Club VK Bot

MVP VK bot skeleton for subscription club client interface.

Проект находится на этапе переноса skeleton из `Kosmos327/vk_bot` в отдельный репозиторий VK-бота. В этом PR не выполняется глубокий ребрендинг, не переписываются сценарии и не меняются API-контракты: skeleton оставлен как MVP-клиентский интерфейс для subscription club.

## Структура проекта

```text
.
├── main.py                    # точка входа VK Long Poll bot
├── config.py                  # загрузка env-конфигурации без хардкода секретов
├── keyboards.py               # VK-клавиатуры MVP-сценариев
├── texts.py                   # базовые тексты бота
├── routing.py                 # парсинг текстовых команд
├── state.py                   # in-memory пользовательское состояние MVP
├── diagnostics.py             # debug/health helpers
├── vk_attachments.py          # извлечение URL из VK-вложений
├── services/
│   └── backend_gateway.py     # HTTP gateway к WEB/CRM API
├── tests/                     # pytest-проверки skeleton
├── requirements.txt           # Python-зависимости
├── .env.example               # безопасные env placeholders
└── .gitignore                 # исключения secrets/cache/runtime
```

WEB/CRM находится в отдельном репозитории: `Kosmos327/fed_women_club_WEB`.

## Env placeholders

Скопируйте `.env.example` в локальный `.env` и заполните значения. `.env` не должен попадать в git.

```env
VK_GROUP_TOKEN=your_vk_group_token
VK_GROUP_ID=123456
ADMIN_ID=123456789
VK_BOT_USE_BACKEND=true
BACKEND_BASE_URL=https://women-club.example/api/v1
BOT_API_TOKEN=your_bot_api_token
CLUB_INVITE_LINK=https://women-club.example/invite
```

Важно:

- `VK_GROUP_TOKEN` и `BOT_API_TOKEN` не хардкодятся в коде.
- `BACKEND_BASE_URL` в skeleton использует placeholder `https://women-club.example/api/v1`.
- Production env, runtime-файлы и логи не переносятся.

## Локальная проверка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. pytest -q
python -m py_compile main.py keyboards.py config.py
python -m compileall .
git check-ignore .env .venv/ __pycache__/ .pytest_cache/
rg -n "<forbidden legacy brand/domain patterns>" -S -uu --glob '!**/.git/**'
```

## Запуск

```bash
python main.py
```

Для запуска нужен безопасно настроенный локальный `.env` с VK credentials и тестовым/production backend endpoint. Secrets в репозиторий не добавляются.
