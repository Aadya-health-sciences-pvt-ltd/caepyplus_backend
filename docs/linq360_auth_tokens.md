# LinQ360 / Practice Hub — Caepy token contract

Aligned with Practice Hub Drupal Linq360: HS256 identity via `workspace_jwt_secret`
(`WORKSPACE_JWT_SECRET` / `AUTH_JWT_SECRET`). **Do not log raw tokens or PHI.**

## Flow

| Step | Method / path | Client stores as | Used for |
|------|---------------|------------------|----------|
| Login | `POST /v1/auth/workspace/login` | `identity_access_token` ← `data.access_token` | Content sync/GET, Practice Hub, doctor CRUD |
| Workspaces (when appointments need a workspace) | `GET /v1/auth/workspace/linq360/workspaces` | — | Bearer = identity |
| Select | `POST /v1/auth/workspace/select` | `workspace_access_token_main` ← `data.access_token` | Appointments GET + WS only |

API response field names remain `access_token` / `refresh_token`.

## Which Caepy routes use which token

| Route | Token |
|-------|--------|
| `POST /v1/linq360/glance/sync` | `identity_access_token` |
| `GET /v1/linq360/glance/content` | `identity_access_token` |
| `GET /v1/linq360/glance/appointments` | `workspace_access_token_main` |
| `POST /v1/linq360/webhooks/dashboard` | **none** — `ph_user_id`, `ws_user_id`, `workspace_id` in body |
| `WS /v1/linq360/ws/dashboard?token=` | `workspace_access_token_main` |
| `GET /v1/linq360/doctors/{id}/content-engagement` | Caepy JWT **or** LinQ360 `identity_access_token` (checked inside linq360; Caepy `rbac` unchanged) |
| `/v1/doctors/*` (Caepy app) | Caepy JWT only — **not** altered for LinQ360 |

**Removed:** merged `GET /v1/linq360/glance`. Use the two GETs above.

## Daily clear (ops — not an HTTP route)

| Item | Detail |
|------|--------|
| Command | `python scripts/clear_linq360_workspace_dashboard.py` |
| When | `00:00 Asia/Kolkata` |
| Effect | Deletes all `workspace_doctor_dashboard` rows |
| Does not clear | `doctor_dashboard` |
| Token | None (CLI) |
| Refill | Next full `POST /webhooks/dashboard` snapshot |

Full local/dev curls + token matrix: [`linq360_frontend_handbook.md`](./linq360_frontend_handbook.md).

## Response shapes

**Content** (`/glance/content`, `/glance/sync`):

```json
{ "content": { "...": "..." }, "payments": {} }
```

**Appointments** (`/glance/appointments`, webhook):

```json
{ "appointments": 2, "requests": 1, "todays_schedule": [] }
```

## Webhook body (no Bearer)

```json
{
  "ph_user_id": 893,
  "ws_user_id": 327,
  "workspace_id": 161,
  "event_type": "appointment.created",
  "appointments": 2,
  "requests": 1,
  "todays_schedule": []
}
```

When `AI_SUGGESTIONS_OPEN_DOMAINS` is set, Origin/Referer must match; Bearer is never required.

## Postman / env vars

| Variable | Set from |
|----------|----------|
| `identity_access_token` | Login `access_token` |
| `workspace_access_token_main` | Select `access_token` only |
| `WORKSPACE_JWT_SECRET` | Same secret as portal `AUTH_JWT_SECRET` |

Collection: [`postman/linq360-auth.postman_collection.json`](../postman/linq360-auth.postman_collection.json).
