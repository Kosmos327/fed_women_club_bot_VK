# VK ↔ WEB auth/binding decision record

Документ фиксирует безопасный дизайн связывания VK-пользователя с WEB client user/token для проекта Federal Women Club / «Женский клуб» / bloomclub.ru.

Scope: **documentation only**. Этот decision record не меняет runtime VK bot, `main.py`, `services/backend_gateway.py`, `services/web_api_client.py`, `config.py`, env/secrets, WEB repo `Kosmos327/fed_women_club_WEB` и не реализует новые endpoints.

## 1. Current facts

- VK bot знает `vk_user_id` из события VK.
- WEB client endpoints требуют Bearer JWT unified `User` token.
- WEB token subject format: `user:<id>`.
- WEB `User` имеет `role`: `admin` / `partner` / `client`.
- WEB `ClientProfile` имеет `vk_user_id`.
- Current WEB client endpoints:
  - `GET /api/v1/clients/me`
  - `GET /api/v1/clients/catalog/partners`
  - `POST /api/v1/clients/partners/{partner_id}/verify`
  - `GET /api/v1/clients/me/verifications`
- В текущем WEB API нет endpoint для safe VK binding или token exchange.

Следствие: VK bot не может безопасно вызвать client endpoints WEB только на основании `vk_user_id`. Нужен отдельный WEB contract, который доказывает владение WEB-аккаунтом и выдаёт token/session с правами конкретного client user.

## 2. Security constraints

- VK bot не должен хранить WEB password клиента.
- VK bot не должен запрашивать пароль клиента в чате.
- Нельзя использовать `AdminUser` token для client actions.
- Нельзя выдавать client JWT только по `vk_user_id` без проверки владения.
- Binding должен быть auditable/revocable.
- Bot service token, если появится, должен иметь ограниченные права только на VK binding/exchange.
- Секреты должны передаваться только через env и не попадать в git.

## 3. Candidate designs

### A. One-time link code from WEB cabinet

Flow:

1. Клиент входит в WEB личный кабинет bloomclub.ru.
2. Клиент нажимает «Привязать VK».
3. WEB генерирует одноразовый short code/nonce.
4. Клиент отправляет код VK-боту.
5. VK bot отправляет `code` + `vk_user_id` в WEB.
6. WEB проверяет код, срок действия и принадлежность к authenticated client user.
7. WEB связывает `ClientProfile.vk_user_id` и возвращает bot-scoped client token/session или подтверждение успешной привязки.

Pros:

- Пользователь доказывает владение WEB-аккаунтом через уже существующий WEB login.
- Бот не видит и не хранит WEB password.
- Код можно сделать одноразовым, короткоживущим и аудируемым.
- Хорошо подходит для self-service пользовательского сценария.
- Можно явно показывать пользователю, какой VK аккаунт был привязан, и дать revoke/unlink в WEB cabinet.

Cons:

- Требует изменения WEB repo: UI в личном кабинете, endpoint генерации кода и endpoint обмена кода для бота.
- Требует UX-тексты и обработку ошибок: истёкший код, повторное использование, код не найден, аккаунт уже привязан к другому VK.
- Пользователю нужно переключиться между WEB cabinet и VK chat.

### B. Signed VK deep link / nonce

Flow:

1. WEB создаёт signed deep link для VK bot с payload/nonce.
2. Пользователь переходит в VK bot по ссылке.
3. Бот получает payload и фактический `vk_user_id` из VK event.
4. Бот отправляет `payload` + `vk_user_id` в WEB.
5. WEB валидирует signature, expiry, одноразовость payload и связывает `ClientProfile.vk_user_id`.

Pros:

- Более плавкий UX: пользователь нажимает ссылку вместо ручного ввода кода.
- Payload может быть короткоживущим и одноразовым.
- Можно использовать тот же принцип владения WEB-аккаунтом, если deep link создаётся только в authenticated WEB cabinet.

Cons:

- Требует точного contract по VK deep link payload формату и parser tests в VK bot.
- Нужно учитывать ограничения/особенности VK start payload, URL encoding и возможные потери payload в клиентах.
- Сложнее отлаживать, чем ручной short code.
- Всё равно требует WEB endpoints для валидации nonce и token/session exchange.

### C. Admin manual binding MVP

Flow:

1. Админ в WEB вручную проставляет `vk_user_id` клиенту.
2. Бот по `vk_user_id` делает token exchange через service endpoint.
3. WEB endpoint проверяет bot service token, находит уже привязанный `ClientProfile` и возвращает limited client token/session.

Pros:

- Самый быстрый путь для внутренней проверки end-to-end каталога и verify без пользовательского self-service UX.
- Не требует сразу проектировать полный кабинетный flow генерации кода.
- Позволяет проверить mapping, token exchange и WEB client endpoints на ограниченной группе тестовых пользователей.

Cons:

- Не является полноценным пользовательским сценарием.
- Высокий риск ошибки ручного ввода `vk_user_id`; нужен аудит, журнал изменений и revoke.
- Нельзя использовать как массовую production-механику без дополнительных проверок владения.
- Service endpoint должен быть строго ограничен: только bot service token, только уже bound profiles, limited token/session, rate limit и аудит.

### D. Password login inside VK bot

Flow:

1. Бот спрашивает у пользователя phone/email/password в VK chat.
2. Бот вызывает `/api/v1/auth/user-login`.
3. Бот сохраняет или использует полученный client JWT для catalog/verify.

Decision: **NOT recommended**.

Почему не рекомендуется:

- Пароль оказывается в VK chat, где его могут увидеть в истории сообщений, уведомлениях, логах клиента или на чужом устройстве.
- Бот становится обработчиком пользовательских passwords и должен соответствовать гораздо более строгой security модели.
- Повышается риск phishing-паттерна: пользователь привыкает вводить пароль в чат-бот.
- Нужны сложные меры очистки сообщений, логов, state и инцидент-реакции; это не оправдано для MVP.

## 4. Recommended MVP

Рекомендация для полноценного пользовательского сценария: **A. One-time link code from WEB cabinet**.

Причины:

- WEB cabinet уже является правильным местом, где пользователь проходит authentication и доказывает владение client account.
- VK bot получает только одноразовый code и `vk_user_id`, а не пароль.
- Binding можно сделать auditable, revocable и явно понятным пользователю.
- Этот вариант проще и надёжнее, чем deep link payload, для первого production-ready contract.

Для быстрой внутренней проверки можно временно использовать **C. Admin manual binding MVP**, но только при условиях:

- WEB endpoint строго проверяет `BOT_API_TOKEN` / service token.
- Exchange работает только для уже вручную bound `ClientProfile.vk_user_id`.
- Endpoint возвращает limited client token/session, а не admin token.
- Все exchange/binding операции логируются и могут быть отозваны.
- Этот сценарий явно помечен как internal/test и не заменяет self-service link-code flow.

## 5. Required WEB changes

Нужные WEB endpoints и UI changes, которые должны быть реализованы в WEB repo отдельно. В рамках этого VK bot docs-only PR они **не реализуются**.

### Required for link-code MVP

- `POST /api/v1/clients/me/vk-link-codes`
  - protected by client JWT;
  - creates one-time link code;
  - expires in 10 minutes;
  - stores enough metadata for audit: client user/profile id, created_at, expires_at, consumed_at, consuming `vk_user_id`, request id/ip/user agent where applicable;
  - rejects or rotates active codes according to WEB policy.

- `POST /api/v1/bot/vk/exchange-link-code`
  - protected by `BOT_API_TOKEN` / service token;
  - input: `vk_user_id`, `code`;
  - validates service token, code existence, expiry, one-time usage and ownership;
  - binds `ClientProfile.vk_user_id` if policy allows;
  - output: client access token or bot-scoped token/session;
  - records audit event for successful and failed attempts.

### Optional after binding exists

- `POST /api/v1/bot/vk/token`
  - protected by `BOT_API_TOKEN` / service token;
  - input: `vk_user_id`;
  - only works after profile is already bound;
  - returns short-lived client token or bot-scoped token/session for the bound client;
  - rejects unbound, revoked, disabled or ambiguous profiles.

- Admin UI field or endpoint for manual `vk_user_id` binding if internal MVP/manual support is needed.
  - Must be audited and revocable.
  - Must validate uniqueness and prevent accidental collisions.

## 6. Required VK bot changes after WEB contract exists

После появления WEB contract можно планировать отдельный runtime integration PR в VK repo:

- Add config `BOT_API_TOKEN` or separate `WEB_BOT_TOKEN` if WEB binding/exchange should not reuse existing backend gateway token.
- Store issued client token or short-lived session in state/persistence.
- Use `WebApiClient` with client token for:
  - catalog;
  - partner offers;
  - verify session;
  - verification history.
- Add graceful UX when VK user is not linked:
  - «Привяжите VK к личному кабинету bloomclub.ru»;
  - explain where to generate the link code;
  - handle expired/invalid code without exposing internal errors.

## 7. Token/session policy

- Не хранить long-lived JWT in plain memory forever.
- For MVP in-memory token is acceptable only for dev/internal test.
- Production should use short-lived token or refresh/exchange by `vk_user_id` with service auth.
- If using persistent storage later, store minimal binding/session metadata and avoid raw passwords.
- Prefer bot-scoped client session/token with least privilege over full reusable user session if WEB architecture supports it.
- Tokens must have expiry, revocation path and audit trail.

## 8. Acceptance criteria before runtime integration

Каталог/verify можно подключать в VK runtime только когда:

- WEB has binding/exchange endpoint.
- VK bot can obtain valid client token without user password in chat.
- Tests cover unauthenticated/unlinked state.
- No admin token used for client calls.
- `verify_partner_<id>` creates WEB `PrivilegeVerificationSession`.

## 9. Next PR recommendation

Следующий PR после этого docs-only decision record:

1. In WEB repo: implement VK link-code + bot token exchange endpoints.

или, если WEB work ещё не готов:

2. In VK repo: prepare pure parser/mapping helpers without runtime integration.

Приоритетная рекомендация: сначала WEB repo должен предоставить безопасный binding/exchange contract. После этого VK repo сможет подключить `WebApiClient` к catalog/verify без auth shortcuts, admin-token impersonation и хранения пользовательских passwords.

## 10. VK bot runtime foundation added

VK bot now includes a small runtime foundation for the WEB one-time link-code contract:

- user command: `Привязать <код>` with aliases `link <код>` and `код <код>`;
- service calls: `POST /api/v1/bot/vk/exchange-link-code` and `POST /api/v1/bot/vk/token` via `WebApiClient`;
- service auth: existing `BOT_API_TOKEN`, which must match the WEB `BOT_API_TOKEN` for `/api/v1/bot/vk/*` endpoints;
- MVP storage: returned client token and user payload are kept only in in-memory `USER_STATE` as `web_client_token` / `web_client_user`;
- status UX: `Статус привязки` and a passive `WEB-привязка: активна/не активна` line in `🎁 Мои привилегии`.

This foundation intentionally does **not** migrate catalog, verify, subscription, payment or existing `BackendGateway` runtime flows to WEB client-token calls yet. The bot still does not ask for or store WEB passwords.


## 11. VK onboarding button added

VK bot now includes the `💗 Присоединиться к клубу` main-menu button with payload action `join_club`. The handler calls `POST /api/v1/bot/vk/onboard-client` through `WebApiClient` using the existing `BOT_API_TOKEN`, sends `vk_user_id` as a string, and stores the returned client token/user payload in in-memory `USER_STATE` as `web_client_token` / `web_client_user`.

Selected city is passed only when the current `selected_city` has a WEB-known safe slug (`Новосибирск` → `novosibirsk`, `Череповец` → `cherepovets`). Other cities are omitted to avoid onboarding failures while WEB has a smaller city set. If WEB returns 404 for a selected city, the bot retries onboarding once without `selected_city_slug`.

This flow does not ask for, generate, store, or send WEB passwords in VK. It also does **not** activate a subscription, create a payment, or migrate catalog/verify/payment runtime from the existing `BackendGateway` flow.
