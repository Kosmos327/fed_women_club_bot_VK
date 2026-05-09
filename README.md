# Federal Women Club VK Bot

VK-бот для продукта **«Женский клуб»** — федерального клуба привилегий для женщин.

Бот является клиентским VK-интерфейсом к WEB/CRM из репозитория `Kosmos327/fed_women_club_WEB`: помогает участнице выбрать город, посмотреть партнёров и скидки, получить/подтвердить привилегию через QR и оформить или продлить подписку.

## Позиционирование

**Женский клуб** — федеральный клуб привилегий для женщин: скидки, подарки, розыгрыши и специальные предложения у партнёров в разных городах.

Тональность пользовательских текстов: мягкая, премиальная и дружелюбная.

## Основные сценарии MVP

- **Выбрать город** — участница нажимает `🌸 Выбрать город` и выбирает один из городов MVP: Новосибирск, Москва, Санкт-Петербург, Екатеринбург, Казань.
- **Посмотреть партнёров** — раздел `✨ Партнёры и скидки` показывает женские категории и партнёрские предложения.
- **Подтвердить привилегию через QR** — текущий flow `verify_partner_<id>` сохраняется; бот показывает код подтверждения, срок действия 5 минут и просит показать экран сотруднику партнёра.
- **Оплатить/продлить подписку** — раздел `💳 Оплатить / Продлить` создаёт заявку на оплату через существующий backend gateway.
- **Посмотреть свои привилегии** — раздел `🎁 Мои привилегии` использует существующий API-совместимый flow кодов.
- **Присоединиться к клубу** — кнопка `💗 Присоединиться к клубу` создаёт или находит WEB-кабинет через `/api/v1/bot/vk/onboard-client`, сохраняет client token в `USER_STATE` и не запрашивает, не генерирует и не отправляет пароль. Подписка и оплата остаются отдельными сценариями.
- **Привязать WEB-кабинет** — участница создаёт одноразовый VK-код в профиле bloomclub.ru и отправляет в VK команду `Привязать <код>`; также доступны `link <код>`, `код <код>` и `Статус привязки`.

## City selection MVP

Выбранный город хранится в текущем in-memory state бота (`USER_STATE`) как `selected_city`.

Постоянный endpoint синхронизации выбранного города в backend gateway пока не добавляется, чтобы не менять API-контракты без необходимости. Когда WEB/CRM предоставит endpoint `selected_city`, значение можно будет синхронизировать через `services/backend_gateway.py`.

## Структура проекта

```text
.
├── main.py                    # точка входа VK Long Poll bot и сценарии MVP
├── config.py                  # загрузка env-конфигурации без хардкода секретов
├── keyboards.py               # VK-клавиатуры, города и женские категории
├── texts.py                   # брендовые пользовательские тексты
├── routing.py                 # парсинг текстовых команд
├── state.py                   # in-memory пользовательское состояние MVP
├── diagnostics.py             # debug/health helpers
├── vk_attachments.py          # извлечение URL из VK-вложений
├── services/
│   ├── backend_gateway.py     # текущий HTTP gateway к bot-specific WEB/CRM API
│   └── web_api_client.py      # изолированный foundation client для актуального WEB /api/v1
├── tests/                     # pytest-проверки VK bot MVP
├── requirements.txt           # Python-зависимости
├── .env.example               # безопасные env placeholders
└── .gitignore                 # исключения secrets/cache/runtime
```

## Документация

- [VK bot architecture audit and WEB integration roadmap](docs/vk_bot_audit.md) — текущая архитектура бота, mismatch с WEB API, auth/binding gaps и staged roadmap интеграции.
- [VK ↔ WEB auth/binding decision record](docs/vk_web_auth_binding.md) — безопасная схема привязки `vk_user_id` к WEB client user/token перед подключением каталога и verify.

## Env placeholders

Скопируйте `.env.example` в локальный `.env` и заполните значения. `.env` не должен попадать в git.

```env
VK_GROUP_TOKEN=your_vk_group_token
VK_GROUP_ID=123456
ADMIN_ID=123456789
VK_BOT_USE_BACKEND=true
BACKEND_BASE_URL=https://women-club.example/api/v1
BOT_API_TOKEN=your_bot_api_token
WEB_API_BASE_URL=https://bloomclub.ru
WEB_API_TIMEOUT_SECONDS=10
CLUB_INVITE_LINK=https://women-club.example/invite
```

Важно:

- `VK_GROUP_TOKEN` и `BOT_API_TOKEN` не хардкодятся в коде.
- `BACKEND_BASE_URL` использует безопасный placeholder `https://women-club.example/api/v1`.
- `WEB_API_BASE_URL` и `WEB_API_TIMEOUT_SECONDS` настраивают WEB API client foundation для актуальных `/api/v1/...` endpoints. В runtime подключены безопасный link-code exchange/status foundation и VK onboarding `POST /api/v1/bot/vk/onboard-client`; каталог, verify и payment остаются на существующем backend gateway flow.
- `BOT_API_TOKEN` должен совпадать с WEB `BOT_API_TOKEN` для service endpoints `/api/v1/bot/vk/*`. Этот же env продолжает использоваться текущим `services/backend_gateway.py`, отдельный secret для WEB не добавляется.
- Production env, runtime-файлы и логи не переносятся в репозиторий.
- WEB repo в рамках изменений VK-бота не деплоится и не изменяется.

## Локальная проверка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. pytest -q
python -m py_compile main.py keyboards.py config.py
python -m compileall .
rg -n "<legacy brand patterns>" -S -uu --glob '!**/.git/**'
```

## Запуск

```bash
python main.py
```

Для запуска нужен безопасно настроенный локальный `.env` с VK credentials и backend endpoint. Secrets в репозиторий не добавляются.
