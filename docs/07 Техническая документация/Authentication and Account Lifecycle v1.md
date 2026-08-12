---
aliases:
  - Authentication and Account Lifecycle v1
type: technical-contract
status: implemented-locally
updated: 2026-08-11
---

# Authentication and Account Lifecycle v1

## Статус

Контракт и automated tests реализованы локально. Apple release credential, реальный Apple authorization flow, Apple credential revocation, staging и TestFlight ещё не проверены. Наличие кода в этом документе не означает готовность публичного входа.

## Runtime boundary

`APP_ENV=local|test|staging|production` задаёт режим процесса. При старте staging/production приложение отклоняет небезопасную конфигурацию:

- `APP_DEBUG=true`;
- dogfood bearer auth или `MOBILE_DOGFOOD_TOKEN`;
- loopback/SQLite database;
- не-HTTPS public API;
- отсутствие Apple client ID;
- отсутствие Privacy Policy, Terms и Support URL.

Local Mobile API v1 остаётся только для dogfooding. Production identity никогда не получается из `user_id`, `user_external_id` или другого значения клиента.

## Identity map

```text
Apple identity token
  → signature / kid / issuer / audience / exp / iat / nonce
  → stable Apple subject
  → auth_identities(provider=apple, subject)
  → users.id (internal ownership key)
  → users.public_id (client-safe UUID)
```

`(provider, subject)` глобально уникален. Email и имя сохраняются только из проверенного первого ответа и не стираются последующими Apple claims со значением `null`. Raw Apple identity token не записывается в database или log.

## Challenge and session lifecycle

1. `POST /api/v2/auth/challenge` создаёт случайные state и nonce на десять минут.
2. В database сохраняются только SHA-256 digests state/nonce.
3. `POST /api/v2/auth/apple` проверяет signed token и однократно consume-ит challenge.
4. Server выдаёт случайные opaque access/refresh credentials; в `app_sessions` сохраняются только SHA-256 digests.
5. `POST /api/v2/auth/refresh` создаёт следующую session generation и помечает предыдущую rotated.
6. Повторное использование старого refresh credential считается reuse и отзывает всю device family.
7. `POST /api/v2/auth/logout` отзывает текущую family; `POST /api/v2/auth/revoke-all` — все sessions пользователя.

Missing, expired и revoked access credentials возвращают одинаковый 401 без технических деталей.

## Authenticated API v2

```text
POST   /api/v2/auth/challenge
POST   /api/v2/auth/apple
POST   /api/v2/auth/refresh
POST   /api/v2/auth/logout
POST   /api/v2/auth/revoke-all
GET    /api/v2/me
GET    /api/v2/account/export
DELETE /api/v2/account
GET    /api/v2/onboarding
POST   /api/v2/onboarding/preview
POST   /api/v2/onboarding/apply
```

Все user-owned queries получают internal `user_id` только из bearer session dependency. Extra client identity fields запрещены Pydantic schemas.

## Account export and deletion data map

Authenticated export включает собственный профиль, goals, tasks, routines, resource budget и onboarding previews. Он не включает access/refresh credentials, hashes, Apple subject или внутренние auth records.

`DELETE /api/v2/account` принимает только `{"confirmation":"DELETE"}`. Удаление `users` каскадно удаляет:

- `auth_identities`, `app_sessions`;
- goals, tasks и их goal/routine links;
- routines;
- day plans и plan items;
- pending interactions и message receipts;
- resource budget, onboarding previews и onboarding request receipts.

Чужие строки сохраняются; это покрыто двухпользовательским integration test. Auth challenge не содержит user identity и очищается отдельно по expiry.

Локальное удаление Apple identity mapping реализовано. Обмен Apple authorization code на revocable credential и вызов Apple revoke endpoint ещё не реализованы: до закрытия этого пункта Sign in with Apple нельзя считать App Store-ready.

## Mobile storage boundary

Native SecureStore содержит один versioned envelope:

```text
ai-life-planner.session.v2
→ {version, publicUserId, accessToken, refreshToken}
```

Public user UUID атомарно связан с обоими credentials в той же SecureStore-записи. AsyncStorage не является источником identity: Today cache, capture draft и goals/calendar/onboarding caches используют user-scoped keys, но открыть их offline можно только для `publicUserId` из валидного текущего envelope. Logout, proven revocation и успешное account deletion очищают envelope и известные ключи только связанного пользователя.

Legacy `access-token.v1 + refresh-token.v1` читается как unbound session: stale public scope из AsyncStorage не используется. Новый envelope создаётся одним SecureStore write только после успешного authoritative `/api/v2/me`; malformed или partial legacy/current state fail-closed и не раскрывает чужой cache. SecureStore и startup token reads имеют bounded deadline, а auth epoch с сериализованными secure mutations не разрешает позднему refresh/sign-in перезаписать logout, deletion или более новую account session.

Legacy P0 cache переносится только в явный `dogfood` namespace. Production session никогда не импортирует legacy snapshot/draft. Dogfood token недоступен в production build.

## Verification

Automated locally:

- Apple JWT signature/issuer/audience/expiration/nonce checks with generated RSA JWKS;
- one-use challenge;
- first sign-in and repeat sign-in identity mapping;
- multi-device sessions, rotation and reuse detection;
- logout and revoke-all;
- owned export and cascading deletion;
- onboarding preview/apply ownership and idempotency;
- atomic SecureStore envelope, safe unbound legacy migration, single-flight refresh, auth race suppression and user-scoped cache isolation.

Required outside local environment:

- real Apple release Service/App ID and entitlement;
- native Sign in with Apple on a release build;
- authorization-code exchange and Apple credential revocation;
- staging PostgreSQL migration/rollback;
- TestFlight logout, reinstall, revoked credential and account deletion;
- App Store review instructions and deletion verification.

## Security invariants

- Never log Authorization, Apple token, access/refresh credential, nonce or state.
- Never persist raw credentials server-side.
- Never accept client-selected user identity.
- Never reuse a refresh credential after rotation.
- Never derive offline identity from an AsyncStorage scope or an unbound legacy credential pair.
- Never migrate dogfood data into a production account.
- Never report local automated verification as staging, TestFlight or App Store verification.
