# VK bot architecture audit and WEB integration roadmap

Документ фиксирует результаты статического аудита текущего VK bot repo `Kosmos327/fed_women_club_bot_VK` для проекта Federal Women Club / «Женский клуб» / bloomclub.ru.

Scope этого PR: **documentation only**. Runtime-код, `main.py`, `services/backend_gateway.py`, `config.py`, env/secrets, deploy и WEB repo `Kosmos327/fed_women_club_WEB` не меняются.

## 1. Repo map

- `README.md` — описание продукта, MVP-сценариев, env placeholders, структуры проекта и локальной проверки.
- `.env.example` — безопасный шаблон переменных окружения без реальных секретов.
- `requirements.txt` — Python-зависимости для runtime и тестов.
- `main.py` — точка входа VK Long Poll bot, dispatch пользовательских сценариев, форматирование карточек и обработка backend errors.
- `config.py` — загрузка и валидация env-конфигурации.
- `keyboards.py` — VK-клавиатуры, кнопки главного меню, выбор города, категории, действия с партнёрами/услугами, оплата и admin keyboard.
- `texts.py` — пользовательские тексты и сообщения об ошибках/состояниях.
- `routing.py` — парсинг текстовых команд вида `партнёр <id>`, `услуга <id>`, `код <id>`, legacy-команд и `verify_partner_<id>`.
- `state.py` — in-memory `USER_STATE` и helpers для получения/очистки пользовательского состояния.
- `diagnostics.py` — форматирование debug/health статуса для admin-сценариев.
- `vk_attachments.py` — извлечение URL из VK photo/doc attachments.
- `services/backend_gateway.py` — HTTP gateway к текущему bot-specific backend contract.
- `tests/*` — pytest-проверки конфигурации, текстов, клавиатур и routing helpers.

## 2. Current behavior

Текущий VK bot уже покрывает MVP-поведение клиентского интерфейса:

- `/start`, `start`, `начать` — приветствие, авторизация VK-пользователя через backend при включённом gateway и показ главного меню.
- Главное меню — навигация по основным разделам: город, партнёры/скидки, привилегии, подписка, оплата, помощь.
- Выбор города — пользователь выбирает город MVP, выбранное значение сохраняется в in-memory state.
- Категории — бот показывает женские категории и использует их как фильтр партнёров.
- Партнёры/услуги — бот получает партнёров, карточку партнёра, список услуг/предложений и карточку конкретной услуги.
- «Мои привилегии» — бот показывает фильтры и список выданных кодов/привилегий.
- Подписка — бот запрашивает статус подписки и показывает активное/неактивное состояние.
- Оплата — бот создаёт payment request, сохраняет `last_payment_request_id`, обрабатывает кнопку «Я оплатил» и переводит пользователя в ожидание чека.
- Attachment receipt — бот извлекает URL из VK photo/doc attachments и отправляет чек оплаты в backend.
- `verify_partner_<id>` — бот распознаёт текстовую команду, вызывает подтверждение партнёра, показывает dynamic code и просит показать экран сотруднику партнёра.
- Debug/health для admin — admin-команды показывают конфигурационный debug status и health status backend gateway.

## 3. State

`USER_STATE` хранится in-memory в процессе VK bot. По текущему поведению в state попадают:

- `selected_city` — выбранный пользователем город.
- `last_payment_request_id` — последняя созданная заявка на оплату для дальнейшего `payment_paid` flow.
- Состояния search/payment/receipt flow, включая флаг ожидания платежного чека и поисковый режим.
- Временные данные меню, например последние загруженные партнёры, услуги, выбранные `last_partner_id` / `last_category`.

Риск: после restart процесса, redeploy или падения контейнера in-memory state теряется. Это может сбросить выбранный город, текущий payment/receipt flow и временный контекст меню. Перед production-интеграцией с WEB нужно решить, какие значения остаются ephemeral, а какие должны синхронизироваться с backend/WEB.

## 4. Backend gateway

Текущий `BackendGateway` работает с bot-specific endpoints относительно `BACKEND_BASE_URL`:

- `GET health`
- `POST bot/vk/auth`
- `GET bot/categories`
- `GET bot/partners`
- `GET bot/partners/{id}`
- `GET bot/partners/{id}/services`
- `GET bot/services/search`
- `POST bot/codes`
- `GET bot/codes`
- `GET bot/subscription`
- `GET bot/payments/latest`
- `POST bot/payments`
- `POST bot/payments/paid`
- `POST bot/payments/receipt`
- `POST bot/partners/verify`

Для целей интеграции важно, что этот contract уже зашит в gateway и сценарии `main.py`. Это не универсальный WEB API client.

## 5. WEB API snapshot

Актуальные WEB endpoints, которые уже есть на стороне WEB repo по результатам аудита:

- `GET /api/v1/health`
- `POST /api/v1/auth/user-login`
- `GET /api/v1/auth/user-me`
- `GET /api/v1/clients/me`
- `PATCH /api/v1/clients/me`
- `GET /api/v1/clients/me/subscription`
- `GET /api/v1/clients/catalog/partners`
- `GET /api/v1/clients/partners/{partner_id}/offers`
- `POST /api/v1/clients/partners/{partner_id}/verify`
- `GET /api/v1/clients/me/verifications`
- `GET /r/p/{slug}`

Этот snapshot нужен как целевой ориентир для последующих PR, но в текущем docs-only PR runtime-интеграция с WEB не добавляется.

## 6. Contract mismatch

- VK bot сейчас вызывает `bot/...` endpoints через `services/backend_gateway.py`.
- WEB repo сейчас предоставляет клиентские endpoints в namespace `/api/v1/clients/...` и auth endpoints `/api/v1/auth/...`.
- Прямой совместимости между текущим VK bot gateway contract и WEB API contract нет.
- Текущий `BackendGateway` нельзя просто направить на WEB repo изменением `BACKEND_BASE_URL`: пути, auth model, payloads и response mapping не совпадают.

Следовательно, интеграция должна идти через отдельный WEB API client/adapter layer и явный mapping контрактов, а не через silent replacement существующего gateway.

## 7. Auth/binding gap

- VK bot знает `vk_user_id` из VK event.
- WEB client endpoints требуют Bearer JWT unified user token.
- WEB `ClientProfile` имеет поле `vk_user_id`.
- В текущем WEB API не подтверждён endpoint для безопасного binding `vk_user_id` → client profile/user token.
- Бот не должен хранить пароль пользователя или выполнять user-login от имени пользователя через сохранённые credentials.
- Нельзя использовать admin token вместо client token: это нарушит user-level authorization, аудит действий и безопасность персональных данных.

До появления согласованного auth/binding design VK bot не может корректно обращаться к client endpoints WEB от имени конкретной участницы.

## 8. Deep link gap

- `routing.py` умеет распарсить `verify_partner_<id>` как обычный текст команды.
- В текущем routing нет отдельного нормализованного парсинга VK `start` payload variants, например вариантов payload после перехода по deep link, encoded payload или альтернативных префиксов.
- WEB endpoint `GET /r/p/{slug}` может redirect на `deep_link_payload`, но VK bot должен гарантированно понимать этот формат и иметь тесты на все поддержанные варианты.

До добавления parser contract нельзя считать QR/deep link flow end-to-end совместимым.

## 9. Payment/subscription mismatch

- VK bot уже имеет `bot/payments` flow: create request, paid mark, receipt attachment.
- На стороне WEB currently confirmed клиентский endpoint для подписки: `GET /api/v1/clients/me/subscription`.
- WEB payment endpoints для create/paid/receipt в текущем WEB API не подтверждены.
- Интеграцию оплаты нельзя выдумывать: нужен явный WEB payment/subscription contract, payload schema, security model и UX для чека/статуса.

До подтверждения payment endpoints текущий bot payment flow должен оставаться привязанным к существующему bot-specific backend contract.

## 10. Risks

- In-memory state теряется после restart/redeploy и не подходит для durable production flows без дополнительных решений.
- В repo нет deploy artifacts/checklist для production VK bot runtime, секретов, логирования, мониторинга и rollback.
- Нет WEB contract tests, которые фиксируют соответствие VK adapter ↔ WEB `/api/v1/clients/...` responses.
- `requirements.txt` смешивает pytest с runtime dependencies; это удобно для MVP, но усложняет production dependency split.
- Debug output показывает backend URL только admin-пользователю; это допустимо для диагностики, но всё равно требует аккуратной настройки admin id и окружения.
- WEB unavailable handling сейчас основан на generic backend errors; для WEB adapter нужны typed errors и предсказуемый UX для auth expired, forbidden, not found, validation и network failures.

## 11. Roadmap

### PR 1: docs-only audit

- Цель: зафиксировать текущую архитектуру, mismatch с WEB API, auth/binding gaps, deep link gaps и staged plan.
- Файлы менять: `docs/vk_bot_audit.md`; опционально короткая ссылка в `README.md`.
- Tests добавить: новые tests не требуются; выполнить `git diff --check`, `git status --short`, опционально `pytest -q` если без побочных файлов.
- Нельзя трогать: runtime-код, `main.py`, `services/backend_gateway.py`, `config.py`, env/secrets, deploy, WEB repo.

### PR 2: isolated WEB API client foundation

- Статус: foundation добавлен в `services/web_api_client.py` и покрыт unit tests без реальных network calls.
- Добавлены optional config placeholders `WEB_API_BASE_URL` и `WEB_API_TIMEOUT_SECONDS` для актуального WEB `/api/v1/...` client.
- Client умеет нормализовать `https://bloomclub.ru`, `https://bloomclub.ru/` и `https://bloomclub.ru/api/v1`, строить `/api/v1/...` URLs, добавлять Bearer client token только при явной передаче, парсить JSON/text responses и маппить HTTP/network failures в typed `WebApiError`.
- Runtime routes не менялись: `main.py`, текущий `services/backend_gateway.py`, меню VK bot, `verify_partner` и payment flow остаются на прежнем bot-specific contract.
- VK↔WEB auth/binding всё ещё не реализован; до появления client token binding catalog/verify не считаются end-to-end совместимыми с WEB API.

### PR 3: VK ↔ WEB auth/binding design

- Цель: описать и согласовать безопасный способ binding `vk_user_id` к WEB user/client token.
- Файлы менять: design doc в `docs/`, возможно `.env.example` только для новых безопасных placeholders после утверждения.
- Tests добавить: contract tests/fixtures для proposed binding endpoint после его появления.
- Нельзя трогать: хранение пользовательских паролей в боте, admin-token impersonation, production auth behavior без утверждённого WEB endpoint.

### PR 4: city/category mapping for WEB catalog

- Цель: определить mapping текущих городов/категорий VK bot к WEB catalog filters.
- Файлы менять: docs + изолированные mapping helpers/fixtures, если WEB contract подтверждён.
- Tests добавить: unit tests на city/category normalization, unknown values и backward compatibility с текущими кнопками.
- Нельзя трогать: runtime catalog flow до готовности WEB client/auth.

### PR 5: WEB catalog response mapping

- Цель: преобразовать WEB partners/offers responses в текущие bot cards без изменения UX.
- Файлы менять: adapter/mapping layer и unit tests; `main.py` только в отдельном runtime integration PR после готовности feature flag.
- Tests добавить: fixtures для `/api/v1/clients/catalog/partners` и `/api/v1/clients/partners/{partner_id}/offers`, tests на missing optional fields.
- Нельзя трогать: payment, verification, auth shortcuts, WEB repo.

### PR 6: VK deep link/start payload parser

- Цель: добавить нормализованный parser для VK start payload variants и подтвердить формат от WEB `/r/p/{slug}`.
- Файлы менять: `routing.py`, tests routing; docs с поддержанными payload examples.
- Tests добавить: `verify_partner_<id>`, VK start payload variants, invalid/encoded/empty payload cases.
- Нельзя трогать: verify session adapter, auth model, WEB repo, payment.

### PR 7: WEB verification session adapter, only after auth/binding

- Цель: подключить подтверждение партнёра через `POST /api/v1/clients/partners/{partner_id}/verify` только после готового client JWT/binding.
- Файлы менять: WEB adapter, feature-flagged integration point, tests.
- Tests добавить: success, no subscription/forbidden, partner not found, expired auth, network error, response mapping to VK text.
- Нельзя трогать: admin-token impersonation, legacy `bot/partners/verify` без migration plan, payment.

### PR 8: WEB verification history adapter

- Цель: подключить историю подтверждений/привилегий через `GET /api/v1/clients/me/verifications`.
- Файлы менять: adapter + mapping для «Мои привилегии» после согласования schema.
- Tests добавить: empty history, active/used/expired statuses, pagination/limits если есть, formatting tests.
- Нельзя трогать: оплату, auth shortcuts, WEB repo.

### PR 9: payment/subscription contract design

- Цель: согласовать WEB contract для payment create/paid/receipt и subscription state.
- Файлы менять: docs/design; код только после подтверждения endpoints.
- Tests добавить: contract fixtures для subscription и payment states после появления endpoints.
- Нельзя трогать: выдуманные payment endpoints, production payment UX без security review, env/secrets.

### PR 10: VK production deploy checklist

- Цель: подготовить production checklist для VK bot: env, secrets, process manager/container, logs, monitoring, backups, rollback, health checks.
- Файлы менять: `docs/` deploy checklist, возможно `.env.example` placeholders после согласования.
- Tests добавить: smoke-check instructions; automated tests только если не требуют real VK/WEB credentials.
- Нельзя трогать: deploy в рамках PR, реальные секреты, WEB repo.

## 12. Current end-to-end status

Полноценно проверить VK bot → WEB catalog → QR/deep link → WEB verify session сейчас нельзя.

Причины:

- Нет client JWT в VK bot.
- Нет `vk_user_id` binding endpoint.
- Gateway contract mismatch: VK bot вызывает `bot/...`, WEB предоставляет `/api/v1/clients/...`.
- Verify endpoint mismatch: текущий bot flow вызывает `POST bot/partners/verify`, WEB snapshot содержит `POST /api/v1/clients/partners/{partner_id}/verify` с client auth.
- Deep link parser неполный: есть текстовый `verify_partner_<id>`, но нет отдельного contract parser для VK start payload variants от WEB redirect.

До закрытия этих gaps текущий результат аудита — roadmap и набор ограничений для безопасной staged-интеграции, а не готовая runtime-интеграция.
