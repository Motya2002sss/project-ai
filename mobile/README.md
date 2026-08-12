# AI Life Planner mobile

Expo/React Native iOS client for the live Today P0 vertical slice.

## Run locally

Requirements: Node.js LTS, npm, a running backend, and either Expo Go on an iPhone or Xcode Simulator.

For the configured physical-iPhone dogfood stack, run one command from the repository root:

```bash
./scripts/dogfood/start.sh
```

Keep that Terminal window open and scan its Expo QR. `Ctrl+C` stops Expo, FastAPI, and the temporary HTTPS tunnel together.

For manual mobile-only development:

```bash
cd mobile
npm install
cp .env.example .env.local
npm start
```

Press `i` for iOS Simulator, or scan the QR code with the iPhone Camera/Expo Go. SDK 54 is intentionally used for current physical-device Expo Go compatibility.

## Connect the backend

1. Configure the backend outside Git with matching values:

```dotenv
MOBILE_DOGFOOD_TOKEN=<local secret>
MOBILE_DOGFOOD_USER_EXTERNAL_ID=mobile:dogfood
```

2. Set only the non-secret URL in `mobile/.env.local`:

```dotenv
EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
EXPO_PUBLIC_ENABLE_DOGFOOD=true
```

`127.0.0.1` is suitable for iOS Simulator. A physical iPhone must use an HTTPS URL reachable from the device.
The explicit dogfood flag is accepted only when `NODE_ENV=development`; omitting it keeps the local bearer flow locked.

3. Open **Профиль → Данные и доступ**, enter the matching bearer token once, and tap **Подключить**. Native builds store it in iOS Keychain through Expo SecureStore; the token is never an `EXPO_PUBLIC_*` value.

4. Check the backend before opening Today:

```bash
curl http://127.0.0.1:8000/health
curl -H "Authorization: Bearer $MOBILE_DOGFOOD_TOKEN" \
  http://127.0.0.1:8000/api/v1/today
```

## Checks

```bash
npm test
npm run typecheck
npm run lint
npx expo export --platform web
```

The web export is a local visual-QA harness only. Production data never falls back to fixtures; explicit state fixtures live under `src/dev/fixtures` and are guarded by `__DEV__` routes.
