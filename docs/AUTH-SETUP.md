# Thread — Auth Setup

Complete guide to setting up Thread authentication — from password to API token to MCP bridge config.

## Overview

```mermaid
flowchart LR
    subgraph Setup["One-Time Setup"]
        A[Generate<br/>SECRET_KEY] --> B[Set<br/>Password Hash]
    end
    subgraph Docker["Docker Compose"]
        C[.env] --> D[Container<br/>env vars]
        E[.env.container] --> D
    end
    subgraph Token["Get API Token"]
        F[POST /auth/login<br/>expires_in:0] --> G[Non-expiring<br/>token]
    end
    subgraph Bridge["MCP Bridge"]
        H[.vscode/mcp.json<br/>THREAD_API_TOKEN] --> I[Copilot Chat]
    end
    B --> C
    B --> E
    D --> F
    G --> H
```

## 1. Generate Secret Key

The `THREAD_AUTH_SECRET_KEY` is the HMAC-SHA256 signing key for all tokens. **Must be persistent** — changing it invalidates every existing token.

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# Output: bc4563673ec6e620ae9e682b2bbb92e84155f6b5791a256d6de53d8b54bc7501
```

Save this. You'll need it forever (or until you decide to force-reissue all tokens).

## 2. Set Admin Password

Generate a PBKDF2 password hash:

```bash
python3 -m thread_server.cli.set_password
```

This prompts for a password interactively and outputs:
```
Password (hidden): 
Confirm (hidden): 

=== Generated Hash ===
pbkdf2:sha256:600000$9191c6642315d20a0b369c5dc4727356$d96cb240fefc4eec5dd60420cde0a3089dd321c68decc8b22ba70a8ce3dd42a0

=== Environment Variables ===
THREAD_AUTH_PASSWORD_HASH=pbkdf2:sha256:600000$...$...
THREAD_AUTH_SECRET_KEY=<your secret key>

=== Password Change API ===
curl -X POST http://localhost:5000/api/v1/auth/change-password \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"new_password": "new_secure_password"}'
```

## 3. Configure Docker Compose

### .env (gitignored)

docker-compose auto-reads `.env` for variable substitution. PBKDF2 hashes contain `$` characters — use `$$` to escape:

```bash
THREAD_AUTH_SECRET_KEY=bc4563673ec6e620ae9e682b2bbb92e84155f6b5791a256d6de53d8b54bc7501
THREAD_AUTH_PASSWORD_HASH=pbkdf2:sha256:600000$$9191c6642315d20a0b369c5dc4727356$$d96cb240fefc4eec5dd60420cde0a3089dd321c68decc8b22ba70a8ce3dd42a0
THREAD_AUTH_ENABLED=true
```

### .env.container (gitignored)

Used by `docker-compose.yml`'s `env_file` directive to pass the password hash as-is (no `$` escaping needed):

```bash
THREAD_AUTH_PASSWORD_HASH=pbkdf2:sha256:600000$9191c6642315d20a0b369c5dc4727356$d96cb240fefc4eec5dd60420cde0a3089dd321c68decc8b22ba70a8ce3dd42a0
```

### docker-compose.yml (auth section)

```yaml
services:
  thread:
    environment:
      - THREAD_AUTH_ENABLED=true
      - THREAD_AUTH_SECRET_KEY=${THREAD_AUTH_SECRET_KEY}
      - THREAD_AUTH_PASSWORD_HASH_FILE=/app/data/.password_hash
      - THREAD_AUTH_TOKEN_EXPIRY=86400
    env_file:
      - .env.container
```

## 4. Start & Get API Token

```bash
docker compose up -d
```

Wait for health check, then get a non-expiring API token:

```bash
curl -s -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password":"YOUR_PASSWORD","expires_in":0}'
```

Response:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IlRIUkVBRCJ9.eyJzdWIiOiJhZG1pbiIsImlhdCI6MTc4MjgzNzMyNH0.vv24wZFZIOj6cqlqi82p_xRTXgiXOGOjG4cvraclL70",
  "expires_in": null
}
```

`expires_in: null` means the token never expires. Store this token.

## 5. MCP Bridge Config

Place the API token in `.vscode/mcp.json`:

```json
{
  "servers": {
    "thread": {
      "type": "stdio",
      "command": "/home/brajam/.thread-bridge/.venv/bin/python",
      "args": ["-m", "thread_bridge.bridge"],
      "cwd": "/home/brajam/.thread-bridge",
      "env": {
        "THREAD_SERVER_URL": "http://localhost:5000",
        "THREAD_DEFAULT_SESSION": "thread",
        "THREAD_REQUEST_TIMEOUT": "10",
        "THREAD_API_TOKEN": "eyJhbGciOiJIUzI1NiIsInR5cCI6IlRIUkVBRCJ9.eyJzdWIiOiJhZG1pbiIsImlhdCI6MTc4MjgzNzMyNH0.vv24wZFZIOj6cqlqi82p_xRTXgiXOGOjG4cvraclL70"
      }
    }
  }
}
```

> **Note:** `.vscode/mcp.json` is gitignored — each developer/workspace has their own.

## 6. Verify

```bash
# Health (no auth)
curl http://localhost:5000/api/v1/health

# Auth status
TOKEN="eyJ..."
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/v1/auth/status
# {"authenticated":true,"username":"admin","auth_enabled":true}

# Write test entry
curl -s -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"test entry","priority":5}' \
  http://localhost:5000/api/v1/sessions/thread/entries
```

## Token Lifecycle

```mermaid
flowchart TD
    A[POST /auth/login<br/>password + expires_in] --> B{expires_in?}
    B -->|0| C[Non-expiring token<br/>expires_in: null]
    B -->|N seconds| D[Expiring token<br/>expires_in: N]
    
    C --> E[MCP Bridge uses<br/>THREAD_API_TOKEN]
    D --> F[Client refreshes<br/>before expiry]
    
    G[SECRET_KEY changes] --> H[ALL tokens invalidated]
    I[Password changes] --> J[Existing tokens<br/>still valid]
    K[DELETE /auth/token/<id>] --> L[Single token<br/>revoked]
```

Key behaviors:
- **Changing the password** does NOT invalidate existing tokens. Only changing `THREAD_AUTH_SECRET_KEY` does.
- **Non-expiring tokens** (`expires_in:0`) last until the secret key changes or they're explicitly revoked.
- **Runtime password change** via `POST /api/v1/auth/change-password` writes to `data/.password_hash`. The container reads this file on login — no restart needed.
- **The `$` escaping issue** only affects docker-compose `.env` file. Use `.env.container` with `env_file` for the raw PBKDF2 hash.

## Gotchas

| Issue | Symptom | Fix |
|-------|---------|-----|
| PBKDF2 `$` in `.env` | `WARN: .env file: variable '$<salt>$<hash>' is not set` | Use `$$` escaping or `.env.container` with `env_file` |
| Ephemeral SECRET_KEY | All tokens break on restart | Use persistent key from `secrets.token_hex(32)` |
| auth/status 401 | Token invalid | Check SECRET_KEY didn't change. Regenerate token via login. |
| `set_password` only prints | No file written, no env set | Write hash to `.env` and `.env.container` manually |
