# Local iPhone dogfooding

This setup keeps PostgreSQL, FastAPI, Ollama, and the bearer token on the Mac. Only the authenticated FastAPI port is exposed through an ephemeral Cloudflare Quick Tunnel. The tunnel URL is written to ignored `mobile/.env.local`; the token stays in ignored root `.env` and iOS SecureStore.

## Start after a reboot

From the repository root, use one command and keep that Terminal window open:

```bash
./scripts/dogfood/start.sh
```

The launcher starts PostgreSQL, applies migrations, starts and warms Ollama when the local `.env` selects it, runs FastAPI, obtains a fresh Cloudflare Quick Tunnel URL, updates ignored `mobile/.env.local`, checks HTTPS health, and finally shows the Expo QR in LAN mode.

Press `Ctrl+C` once in that window to stop Expo, FastAPI, and the Quick Tunnel started by the launcher. PostgreSQL stays in Docker so the next launch is quick. If a previous combined launcher was suspended or left behind after its Terminal window closed, running the same command again stops that exact recorded stack and starts a fresh one. Unrelated processes on ports `8000` or `8081` are never killed automatically.

The launcher stops before backend startup when macOS reports an active VPN. Expo Go uses the local network for Metro, so disable VPN on both the Mac and iPhone and run the same command again. For an intentional diagnostic run, use `DOGFOOD_ALLOW_VPN=1 ./scripts/dogfood/start.sh`; normal dogfooding should keep VPN off.

The component scripts remain available for diagnosis:

```bash
./scripts/dogfood/start-backend.sh
./scripts/dogfood/start-tunnel.sh
./scripts/dogfood/start-mobile.sh
```

## iPhone token

Copy the token without printing it:

```bash
./scripts/dogfood/copy-token.sh
```

In the app, open **Профиль → Данные и доступ**, paste the token, and tap **Подключить**. The native app stores it through Expo SecureStore.

## Check the live stack

With backend and tunnel running:

```bash
./scripts/dogfood/check.sh
```

This checks tunneled health, authenticated Today serialization, missing/invalid token rejection, and rejection of a client-provided user identity. It never prints the bearer token.
