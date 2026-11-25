# LinQ360 — Frontend / Integration Handbook

Precise contract for **Today-at-a-Glance**: every endpoint with **Local + Dev** URLs, **which access token** to send, WebSocket, webhook, daily schedule clear (ops), responses, tables, and end-to-end flow.

---

## Base URL

`ROOT_PATH=/caepy/api` on both local and dev. Path after host is the same.

| Env | CAEPY base (`{BASE}`) |
|-----|------------------------|
| **Local** | `http://127.0.0.1:8000/caepy/api/v1/linq360` |
| **Dev** | `https://dev1.caepy.linqmd.com/caepy/api/v1/linq360` |

Path-only form (same for both): `{BASE}` = `/caepy/api/v1/linq360`.

| Method | Path | Who calls | Purpose | Token |
|--------|------|-----------|---------|-------|
| `POST` | `{BASE}/glance/sync` | Frontend | Pull Practice Hub pending content → Postgres | `identity_access_token` |
| `GET` | `{BASE}/glance/content` | Frontend | Read stored **content** only | `identity_access_token` |
| `GET` | `{BASE}/glance/appointments` | Frontend | Read stored **appointments** only | `workspace_access_token_main` |
| `POST` | `{BASE}/webhooks/dashboard` | Appointment backend | Upsert schedule; debounce; return appointments | **none** (ids in body) |
| `WS` | `{BASE}/ws/dashboard?token=…` | Frontend | Realtime appointment pushes | `workspace_access_token_main` |
| `GET` | `{BASE}/doctors/{doctor_id}/content-engagement` | App | Published engagement rollup | Caepy JWT / identity |

**Removed:** merged `GET {BASE}/glance` — use `/glance/content` and `/glance/appointments`.

### Full URLs + which token (copy/paste)

| API | Token (client variable) | Local | Dev |
|-----|-------------------------|-------|-----|
| `POST /glance/sync` | `identity_access_token` | `http://127.0.0.1:8000/caepy/api/v1/linq360/glance/sync` | `https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/glance/sync` |
| `GET /glance/content` | `identity_access_token` | `http://127.0.0.1:8000/caepy/api/v1/linq360/glance/content` | `https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/glance/content` |
| `GET /glance/appointments` | `workspace_access_token_main` | `http://127.0.0.1:8000/caepy/api/v1/linq360/glance/appointments` | `https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/glance/appointments` |
| `POST /webhooks/dashboard` | **none** (body ids) | `http://127.0.0.1:8000/caepy/api/v1/linq360/webhooks/dashboard` | `https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/webhooks/dashboard` |
| `WS /ws/dashboard` | `workspace_access_token_main` (query `token`) | `ws://127.0.0.1:8000/caepy/api/v1/linq360/ws/dashboard?token=…` | `wss://dev1.caepy.linqmd.com/caepy/api/v1/linq360/ws/dashboard?token=…` |
| `GET /doctors/{id}/content-engagement` | Caepy JWT **or** LinQ360 `identity_access_token` (auth inside linq360; Caepy app `rbac` unchanged) | `http://127.0.0.1:8000/caepy/api/v1/linq360/doctors/{id}/content-engagement` | `https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/doctors/{id}/content-engagement` |

**How you get the tokens**

| Client variable | From API | Response field |
|-----------------|----------|----------------|
| `identity_access_token` | `POST /v1/auth/workspace/login` | `data.access_token` |
| `workspace_access_token_main` | `POST /v1/auth/workspace/select` | `data.access_token` |
| `caepy_access_token` | Caepy app login | app JWT |

Do **not** use the select token on content sync/GET. Do **not** use the identity token on appointments GET/WS.

### Practice Hub (called by CAEPY on sync — not by frontend)

| Env | Practice Hub pending-counts |
|-----|-------------------------------|
| Config | `LINQMD_PRACTICE_HUB_API_URL` (ECS / `.env`) |
| Demo / current | `GET https://demo.linqmd.com/api/linq360/pending-counts` |

See [`linq360_auth_tokens.md`](./linq360_auth_tokens.md). Internals: [`linq360_realtime_dashboard.md`](./linq360_realtime_dashboard.md).

---

## Auth

### Identity token — content sync + content GET

```http
Authorization: Bearer <identity_access_token>
```

From login `access_token`. Used by `POST /glance/sync` and `GET /glance/content`.

### Select token — appointments GET + WS

```http
Authorization: Bearer <workspace_access_token_main>
```

From select `access_token`. Used by `GET /glance/appointments` and WS `?token=`.

### Webhook — no Bearer

Identity in JSON body: `ph_user_id`, `ws_user_id`, `workspace_id` (required). When `AI_SUGGESTIONS_OPEN_DOMAINS` is set, Origin/Referer must match.

### Content-engagement (LinQ360 route only)

```http
Authorization: Bearer <caepy_access_token>
# or LinQ360 identity (resolved inside linq360/, not via Caepy rbac):
Authorization: Bearer <identity_access_token>
```

Caepy app routes (`/v1/doctors/*`, admin, etc.) stay on **Caepy JWT** only — this branch does not change `src/app/core/rbac.py` / Caepy `_decode_jwt` flow.

---

## End-to-end flow

```text
1. Login → identity_access_token
2. POST /glance/sync + GET /glance/content  (identity)
3. Select workspace → workspace_access_token_main
4. GET /glance/appointments + WS ?token=  (select)
5. Appointment system POST /webhooks/dashboard  (no Bearer; body ids)
```

```text
  Drupal ──► POST /glance/sync ──► doctor_dashboard ──► GET /glance/content
  Appt   ──► POST /webhooks/…  ──► workspace_doctor_dashboard ──► GET /glance/appointments
                                                              └──► WS push
```

### How sync vs debounce works (important)

| Data | When it updates |
|------|-----------------|
| `appointments` / `requests` / `todays_schedule` from webhook body | **Immediately** on webhook (body is authoritative) |
| Pending content (reviews / blog / podcast) | `POST /glance/sync`, or webhook `event_type` → **content** (Drupal pull after debounce) |
| Debounce (~2s, `DEBOUNCE_WINDOW_MS`) | Same `ws_user_id` + `workspace_id` → one background refresh + one WS push |
| Continuous full sync on every event | **No** — only mapped sections |

**Webhook rule:** for appointment/request/`dashboard.snapshot` events, send the **current full snapshot** of `appointments`, `requests`, and `todays_schedule` (omitted fields default to `0` / `[]` and overwrite). Content-only events do **not** rewrite schedule rows.

---

## 1) POST `/glance/sync`

Pull Practice Hub pending counts and store **content** in Postgres.

### Access token

| | |
|-|-|
| **Required token** | `identity_access_token` |
| **Header** | `Authorization: Bearer <identity_access_token>` |
| **Where from** | Login → `data.access_token` |
| **Wrong token** | Do **not** use `workspace_access_token_main` |

### How to call

| | Local | Dev |
|-|-------|-----|
| Method | `POST` | `POST` |
| URL | `http://127.0.0.1:8000/caepy/api/v1/linq360/glance/sync` | `https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/glance/sync` |
| Body | empty | empty |
| Auth | `identity_access_token` | `identity_access_token` |

**Local**
```bash
curl -X POST "http://127.0.0.1:8000/caepy/api/v1/linq360/glance/sync" \
  -H "Authorization: Bearer <identity_access_token>" \
  -H "Accept: application/json"
```

**Dev**
```bash
curl -X POST "https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/glance/sync" \
  -H "Authorization: Bearer <identity_access_token>" \
  -H "Accept: application/json"
```

### Headers

```http
Authorization: Bearer <identity_access_token>
Accept: application/json
```

### Body

None (empty). Doctor comes from JWT `ph_user_id` / `appointment_doctor_id` (no workspace select required).

### What CAEPY does

```text
1. Decode identity JWT → ph_user_id (fallback appointment_doctor_id / ws / email)
2. GET {LINQMD_PRACTICE_HUB_API_URL}/api/linq360/pending-counts
   Authorization: Bearer <same identity token>
3. Parse Practice Hub envelope → data.content
4. Upsert linq360.doctor_dashboard.todays_glance
5. Return content-only envelope (`content` + `payments`)
```

### Practice Hub response (upstream)

```json
{
  "status_code": 200,
  "msg": "Pending counts retrieved successfully",
  "data": {
    "content": {
      "reviews": { "pending_count": 1, "review_id": [1091] },
      "blog_comments": {
        "pending_count": 1,
        "comment_id": [1],
        "blog_id": [2]
      },
      "podcast_comments": {
        "pending_count": 1,
        "comment_id": [1],
        "podcast_id": [1]
      },
      "total_pending_counts": 3
    },
    "payments": {},
    "requests": 0,
    "appointments": 0,
    "todays_schedule": []
  }
}
```

CAEPY stores **only** `data.content` into `doctor_dashboard.todays_glance`.  
Practice Hub `appointments` / `requests` / `todays_schedule` on this response are **ignored** for schedule — those come from `POST /webhooks/dashboard`.

### Success response `200` (CAEPY → frontend)

```json
{
  "status_code": 200,
  "msg": "Glance synced successfully",
  "data": {
    "content": {
      "reviews": { "pending_count": 1, "review_id": [1091] },
      "blog_comments": {
        "pending_count": 1,
        "comment_id": [1],
        "blog_id": [2]
      },
      "podcast_comments": {
        "pending_count": 1,
        "comment_id": [1],
        "podcast_id": [1]
      },
      "total_pending_counts": 3
    },
    "appointments": 0,
    "requests": 0,
    "payments": {},
    "todays_schedule": []
  }
}
```

If `content` counts are all `0` after a successful Practice Hub call, the deployed CAEPY build is missing the `data.content` unwrap — redeploy the pending-counts parser fix.

### Errors

| HTTP | Meaning |
|------|---------|
| `401` | Bad / missing token |
| `404` | Cannot store dashboard for this doctor uid |
| `502` | Practice Hub pending-counts failed (e.g. Cloudflare **522**, timeout, non-200) |

---

## 2a) GET `/glance/content`

Read stored **content** only (no Practice Hub call).

### Access token

| | |
|-|-|
| **Required token** | `identity_access_token` |
| **Header** | `Authorization: Bearer <identity_access_token>` |
| **Where from** | Login → `data.access_token` |
| **Wrong token** | Do **not** use `workspace_access_token_main` |

### How to call

| | Local | Dev |
|-|-------|-----|
| Method | `GET` | `GET` |
| URL | `http://127.0.0.1:8000/caepy/api/v1/linq360/glance/content` | `https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/glance/content` |
| Auth | `identity_access_token` | `identity_access_token` |

**Local**
```bash
curl "http://127.0.0.1:8000/caepy/api/v1/linq360/glance/content" \
  -H "Authorization: Bearer <identity_access_token>" \
  -H "Accept: application/json"
```

**Dev**
```bash
curl "https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/glance/content" \
  -H "Authorization: Bearer <identity_access_token>" \
  -H "Accept: application/json"
```

### Headers

```http
Authorization: Bearer <identity_access_token>
Accept: application/json
```

### Success response `200`

```json
{
  "status_code": 200,
  "msg": "Glance content retrieved successfully",
  "data": {
    "content": {
      "reviews": {},
      "blog_comments": {},
      "podcast_comments": {},
      "total_pending_counts": 0
    },
    "payments": {}
  }
}
```

Empty store → zeros / empty arrays with **200**.

### Errors

| HTTP | Meaning |
|------|---------|
| `401` | Bad / missing `identity_access_token` |

---

## 2b) GET `/glance/appointments`

Read stored **appointments** only (schedule + badge counts).

### Access token

| | |
|-|-|
| **Required token** | `workspace_access_token_main` |
| **Header** | `Authorization: Bearer <workspace_access_token_main>` |
| **Where from** | Select workspace → `data.access_token` |
| **Wrong token** | Do **not** use `identity_access_token` |

### How to call

| | Local | Dev |
|-|-------|-----|
| Method | `GET` | `GET` |
| URL | `http://127.0.0.1:8000/caepy/api/v1/linq360/glance/appointments` | `https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/glance/appointments` |
| Auth | `workspace_access_token_main` | `workspace_access_token_main` |

**Local**
```bash
curl "http://127.0.0.1:8000/caepy/api/v1/linq360/glance/appointments" \
  -H "Authorization: Bearer <workspace_access_token_main>" \
  -H "Accept: application/json"
```

**Dev**
```bash
curl "https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/glance/appointments" \
  -H "Authorization: Bearer <workspace_access_token_main>" \
  -H "Accept: application/json"
```

### Headers

```http
Authorization: Bearer <workspace_access_token_main>
Accept: application/json
```

### Body / query

None. Workspace / doctor come from the select JWT (`workspace_id`, `ws_user_id`, `ph_user_id` / `appointment_doctor_id`).

### Success response `200`

```json
{
  "status_code": 200,
  "msg": "Glance appointments retrieved successfully",
  "data": {
    "appointments": 2,
    "requests": 1,
    "todays_schedule": []
  }
}
```

Empty store (or after daily clear, before next webhook) → zeros / `[]` with **200**.

### Errors

| HTTP | Meaning |
|------|---------|
| `401` | Bad / missing `workspace_access_token_main` |

---

## 3) POST `/webhooks/dashboard`

Appointment backend → CAEPY. Upserts schedule; debounces section refresh; returns appointments glance.

### Access token

| | |
|-|-|
| **Required token** | **None** — do **not** send Bearer |
| **Identity** | JSON body: `ph_user_id`, `ws_user_id`, `workspace_id` (all required) |
| **Optional gate** | If `AI_SUGGESTIONS_OPEN_DOMAINS` is set, `Origin` / `Referer` must match |
| **Who calls** | Appointment / Practice Hub backend — **not** the doctor app |

### How to call

| | Local | Dev |
|-|-------|-----|
| Method | `POST` | `POST` |
| URL | `http://127.0.0.1:8000/caepy/api/v1/linq360/webhooks/dashboard` | `https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/webhooks/dashboard` |
| Body | JSON (full snapshot — see below) | JSON (full snapshot — see below) |
| Auth | **none** (ids in body); Origin/Referer if open-domains set | same |

**Local**
```bash
curl -X POST "http://127.0.0.1:8000/caepy/api/v1/linq360/webhooks/dashboard" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "Origin: https://dev1.linqmd.com" \
  -d '{
    "ph_user_id": 893,
    "ws_user_id": 327,
    "workspace_id": 161,
    "event_type": "appointment.created",
    "appointments": 2,
    "requests": 1,
    "todays_schedule": [{
      "patient_meta_code": "PAT-001",
      "appointment_type": "BOOKING",
      "patient_name": "Rajesh Kumar",
      "first_name": "Rajesh",
      "last_name": "Kumar",
      "consultation_type": "in-person",
      "time_slot": "10:30 AM"
    }]
  }'
```

**Dev**
```bash
curl -X POST "https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/webhooks/dashboard" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "Origin: https://dev1.linqmd.com" \
  -d '{
    "ph_user_id": 893,
    "ws_user_id": 327,
    "workspace_id": 161,
    "event_type": "appointment.created",
    "appointments": 2,
    "requests": 1,
    "todays_schedule": [{
      "patient_meta_code": "PAT-001",
      "appointment_type": "BOOKING",
      "patient_name": "Rajesh Kumar",
      "first_name": "Rajesh",
      "last_name": "Kumar",
      "consultation_type": "in-person",
      "time_slot": "10:30 AM"
    }]
  }'
```

### Headers

```http
Content-Type: application/json
Accept: application/json
Origin: https://dev1.linqmd.com
```

No Bearer. Required body fields: `ph_user_id`, `ws_user_id`, `workspace_id`.

### Body

```json
{
  "ph_user_id": 893,
  "ws_user_id": 327,
  "workspace_id": 161,
  "event_type": "appointment.created",
  "appointments": 2,
  "requests": 1,
  "todays_schedule": [
    {
      "patient_meta_code": "PAT-001",
      "appointment_type": "BOOKING",
      "patient_name": "Rajesh Kumar",
      "first_name": "Rajesh",
      "last_name": "Kumar",
      "consultation_type": "in-person",
      "time_slot": "10:30 AM"
    }
  ]
}
```

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `ph_user_id` | int | **Yes** | Drupal / Practice Hub doctor uid |
| `ws_user_id` | int | **Yes** | Portal user (debounce + WS room) |
| `workspace_id` | int | **Yes** | Portal workspace |
| `event_type` | string \| null | No | Maps to sections; omit → appointments + requests |
| `appointments` | int | No (default `0`) | Badge count — full current value |
| `requests` | int | No (default `0`) | Badge count — full current value |
| `todays_schedule` | array | No (default `[]`) | **Full** patient list for today (replace, not patch) |

#### `todays_schedule[]` item

| Field | Allowed values |
|-------|----------------|
| `patient_meta_code` | string |
| `appointment_type` | `REQUEST` \| `BOOKING` \| `CALL` \| `WALK_IN` |
| `patient_name` | string |
| `first_name` | string |
| `last_name` | string |
| `consultation_type` | `in-person` \| `teleconsultation` |
| `time_slot` | string |

#### `event_type` → sections (after debounce)

| `event_type` | Sections |
|--------------|----------|
| `appointment.created` | appointments |
| `appointment.updated` | appointments |
| `appointment.cancelled` | appointments |
| `appointment.completed` | appointments |
| `request.created` | requests |
| `request.accepted` | requests |
| `request.rejected` | requests |
| `review.created` / `review.updated` | content |
| `comment.created` / `comment.updated` | content |
| `blog_comment.created` | content |
| `podcast_comment.created` | content |
| `payment.created` / `payment.updated` | payments (glance still `{}`) |
| `dashboard.snapshot`, omitted, or unknown | appointments + requests |

Content events: after the quiet window CAEPY re-pulls Drupal pending counts, upserts `doctor_dashboard`, then WS-pushes.

### Success response `200`

```json
{
  "status_code": 200,
  "msg": "Dashboard webhook processed successfully",
  "data": { /* GlanceData — schedule already applied */ }
}
```

After ~`DEBOUNCE_WINDOW_MS` (default **2000**), server may push the same glance shape on WebSocket.

### Errors

| HTTP | Meaning |
|------|---------|
| `401` | Origin/Referer failed open-domain allowlist (when configured) |
| `400` | Missing/invalid `workspace_id` or `ws_user_id` in body |
| `404` | Cannot store dashboard row (non-numeric `ph_user_id`) |
| `422` | Invalid body / enum values |
| `502` | Upstream failure (rare on schedule-only path) |

---

## 4) WebSocket `/ws/dashboard`

Realtime appointment pushes after webhook debounce.

### Access token

| | |
|-|-|
| **Required token** | `workspace_access_token_main` |
| **Where** | Query string `?token=<workspace_access_token_main>` (raw JWT or `Bearer <jwt>`) |
| **Where from** | Select workspace → `data.access_token` |
| **Wrong token** | Do **not** use `identity_access_token` |

### How to call

| | Local | Dev |
|-|-------|-----|
| Protocol | `ws://` | `wss://` |
| URL | `ws://127.0.0.1:8000/caepy/api/v1/linq360/ws/dashboard?token=<workspace_access_token_main>` | `wss://dev1.caepy.linqmd.com/caepy/api/v1/linq360/ws/dashboard?token=<workspace_access_token_main>` |
| Body | none (server pushes) | none (server pushes) |
| Auth | `token` query = `workspace_access_token_main` | same |

**Local (browser)**
```js
const ws = new WebSocket(
  `ws://127.0.0.1:8000/caepy/api/v1/linq360/ws/dashboard?token=${encodeURIComponent(token)}`
);
ws.onmessage = (ev) => console.log(JSON.parse(ev.data));
```

**Dev (browser)**
```js
const ws = new WebSocket(
  `wss://dev1.caepy.linqmd.com/caepy/api/v1/linq360/ws/dashboard?token=${encodeURIComponent(token)}`
);
ws.onmessage = (ev) => console.log(JSON.parse(ev.data));
```

| Query | Required | Notes |
|-------|----------|--------|
| `token` | Yes | Raw JWT or `Bearer <jwt>` |

Room is **server-assigned**: `dashboard:{workspace_id}:{ws_user_id}` from the token.

| Close code | Meaning |
|------------|---------|
| `4401` | Missing/invalid token |
| `4403` | Token missing `user_id` or `workspace_id` |

### Server → client message (after debounced refresh)

```json
{
  "event": "dashboard_updated",
  "ws_user_id": 325,
  "workspace_id": 161,
  "sections": ["appointments", "requests"],
  "timestamp": "2026-10-30T12:00:00+00:00",
  "data": { /* same shape as REST response.data */ }
}
```

| `event` value | When |
|---------------|------|
| `appointments_updated` | Only appointments section |
| `requests_updated` | Only requests |
| `content_counts_updated` | Only content |
| `payments_updated` | Only payments |
| `dashboard_updated` | Multiple sections |

Frontend should treat `data` like `GET /glance/appointments` → `response.data`, then re-render badges/schedule.

---

## Response shapes (by endpoint)

**Content** — `POST /glance/sync`, `GET /glance/content` (`identity_access_token`):

```json
{
  "content": {
    "reviews": { "pending_count": 2, "review_id": [101, 102] },
    "blog_comments": {
      "pending_count": 1,
      "comment_id": [55],
      "blog_id": [12]
    },
    "podcast_comments": {
      "pending_count": 0,
      "comment_id": [],
      "podcast_id": []
    },
    "total_pending_counts": 3
  },
  "payments": {}
}
```

**Appointments** — `GET /glance/appointments`, webhook response, WS `data` (`workspace_access_token_main` on GET/WS):

```json
{
  "appointments": 1,
  "requests": 0,
  "todays_schedule": [
    {
      "patient_meta_code": "PAT-001",
      "appointment_type": "BOOKING",
      "patient_name": "Rajesh Kumar",
      "first_name": "Rajesh",
      "last_name": "Kumar",
      "consultation_type": "in-person",
      "time_slot": "10:30 AM"
    }
  ]
}
```

| Field | Source table / column | Returned by |
|-------|------------------------|-------------|
| `content` | `linq360.doctor_dashboard.todays_glance` | content sync/GET |
| `payments` | Always `{}` for now | content sync/GET |
| `appointments` | `workspace_doctor_dashboard.appointments` → int | appointments GET / webhook / WS |
| `requests` | `workspace_doctor_dashboard.requests` → int | appointments GET / webhook / WS |
| `todays_schedule` | `workspace_doctor_dashboard.appointment_json.todays_schedule` | appointments GET / webhook / WS |

### TypeScript

```ts
type ScheduleItem = {
  patient_meta_code: string;
  appointment_type: "REQUEST" | "BOOKING" | "CALL" | "WALK_IN";
  patient_name: string;
  first_name: string;
  last_name: string;
  consultation_type: "in-person" | "teleconsultation";
  time_slot: string;
};

/** POST /glance/sync + GET /glance/content — identity_access_token */
type ContentGlanceData = {
  content: {
    reviews: { pending_count: number; review_id: number[] };
    blog_comments: {
      pending_count: number;
      comment_id: number[];
      blog_id: number[];
    };
    podcast_comments: {
      pending_count: number;
      comment_id: number[];
      podcast_id: number[];
    };
    total_pending_counts: number;
  };
  payments: Record<string, unknown>;
};

/** GET /glance/appointments + webhook + WS — select token on GET/WS */
type AppointmentsGlanceData = {
  appointments: number;
  requests: number;
  todays_schedule: ScheduleItem[];
};

type ContentGlanceApiResponse = {
  status_code: number;
  msg: string;
  data: ContentGlanceData;
};

type AppointmentsGlanceApiResponse = {
  status_code: number;
  msg: string;
  data: AppointmentsGlanceData;
};

type DashboardWsMessage = {
  event: string;
  ws_user_id: number;
  workspace_id: number;
  sections: string[];
  timestamp: string;
  data: AppointmentsGlanceData;
};
```

---

## When frontend should call what

| Situation | Call | Token |
|-----------|------|-------|
| After login (first paint) | `POST /glance/sync` then `GET /glance/content` | `identity_access_token` |
| Soft refresh of stored content | `GET /glance/content` | `identity_access_token` |
| Need fresh pending content | `POST /glance/sync` | `identity_access_token` |
| After workspace select | `GET /glance/appointments` + open **WS** | `workspace_access_token_main` |
| Soft refresh of schedule | `GET /glance/appointments` | `workspace_access_token_main` |
| Switched workspace/doctor | New select token → reconnect **WS** + appointments GET; content uses identity | both as above |
| Live schedule/badge updates | Listen on **WS** (appointment system hits webhook) | `workspace_access_token_main` |

Frontend does **not** call `/webhooks/dashboard` — that is the appointment backend.  
**Removed:** merged `GET /glance` — use the two GETs above.

---

## 5) GET `/doctors/{doctor_id}/content-engagement`

Published engagement metrics (not Today-at-a-Glance).

### Access token

| | |
|-|-|
| **Required token** | `caepy_access_token` **or** `identity_access_token` (when `WORKSPACE_JWT_SECRET` is configured) |
| **Header** | `Authorization: Bearer <token>` |
| **Wrong token** | Do **not** use `workspace_access_token_main` |

### How to call

| | Local | Dev |
|-|-------|-----|
| Method | `GET` | `GET` |
| URL | `http://127.0.0.1:8000/caepy/api/v1/linq360/doctors/{doctor_id}/content-engagement` | `https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/doctors/{doctor_id}/content-engagement` |
| Path param | `doctor_id` = CAEPY doctor id | same |
| Body | none | none |
| Auth | Caepy JWT or identity | same |

**Local (Caepy JWT)**
```bash
curl "http://127.0.0.1:8000/caepy/api/v1/linq360/doctors/42/content-engagement" \
  -H "Authorization: Bearer <caepy_access_token>" \
  -H "Accept: application/json"
```

**Local (identity, if WORKSPACE_JWT_SECRET set)**
```bash
curl "http://127.0.0.1:8000/caepy/api/v1/linq360/doctors/42/content-engagement" \
  -H "Authorization: Bearer <identity_access_token>" \
  -H "Accept: application/json"
```

**Dev (Caepy JWT)**
```bash
curl "https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/doctors/42/content-engagement" \
  -H "Authorization: Bearer <caepy_access_token>" \
  -H "Accept: application/json"
```

**Dev (identity)**
```bash
curl "https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/doctors/42/content-engagement" \
  -H "Authorization: Bearer <identity_access_token>" \
  -H "Accept: application/json"
```

### Headers

```http
Authorization: Bearer <caepy_access_token>
# or: Authorization: Bearer <identity_access_token>
Accept: application/json
```

### Body / query

None. `doctor_id` is the path param (CAEPY doctor id).

### Success response `200`

```json
{
  "doctor_id": 42,
  "sources": [
    {
      "source": "review",
      "item_count": 10,
      "avg_rating": 4.5,
      "rating_sum": 45.0
    },
    { "source": "blog", "item_count": 3 },
    { "source": "podcast", "item_count": 1 }
  ],
  "total_item_count": 14
}
```

`avg_rating` / `rating_sum` appear on `source: "review"` only.
### Errors

| HTTP | Meaning |
|------|---------|
| `401` | Missing/invalid CAEPY JWT |
| `403` | Not allowed for this doctor |
| `404` | Doctor not found |

---

## Database tables (Postgres schema `linq360`)

### `doctor_dashboard` — pending content only

| Column | Type | Notes |
|--------|------|--------|
| `id` | int PK | |
| `ph_user_id` | int unique | Drupal doctor uid |
| `ws_user_id` | int nullable | Portal user |
| `todays_glance` | jsonb | Content block (reviews / blog / podcast) |

### `workspace_doctor_dashboard` — schedule + badge counts

| Column | Type | Notes |
|--------|------|--------|
| `appointment_id` | int PK | |
| `ph_user_id` | int | Drupal doctor uid |
| `ws_user_id` | int nullable | Portal user |
| `workspace_id` | int | Portal workspace |
| `appointments` | jsonb | Stored as `{"count": N}` |
| `requests` | jsonb | Stored as `{"count": N}` |
| `appointment_json` | jsonb | `{"todays_schedule": [ … ]}` |

**Unique row:** `(ws_user_id, ph_user_id, workspace_id)`  
Same trio → upsert. Same doctor, different `workspace_id` → new row.

### How GET merges

```text
content          ← doctor_dashboard.todays_glance          (identity GETs)
appointments     ← as_count(workspace.appointments)       (select GET / WS)
requests         ← as_count(workspace.requests)
todays_schedule  ← workspace.appointment_json.todays_schedule
payments         ← {}
```

---

## 6) Daily clear of `workspace_doctor_dashboard` (ops)

Schedule data is **today-only**. At the start of each IST day, CAEPY deletes all rows in `linq360.workspace_doctor_dashboard` so yesterday’s patients/counts cannot linger. Content in `doctor_dashboard` is **not** cleared.

### Access token

This is a **CLI / ops job**, not an HTTP API. No Bearer token. No frontend call.

### What runs

| | |
|-|-|
| **Script** | `python scripts/clear_linq360_workspace_dashboard.py` |
| **Service** | `DashboardService.clear_all_workspace_dashboards()` |
| **SQL effect** | `DELETE` all rows from `linq360.workspace_doctor_dashboard` |
| **Leaves alone** | `linq360.doctor_dashboard` (pending content) |
| **When** | **00:00 Asia/Kolkata (IST)** every day |
| **How scheduled** | External cron / ECS Scheduled Task / EventBridge / Windows Task Scheduler (timezone = IST) |
| **Refill** | Next `POST /webhooks/dashboard` with a **full** `todays_schedule` snapshot recreates the row |

### Local (manual run)

From repo root, with `DATABASE_URL` pointing at your local DB:

```bash
python scripts/clear_linq360_workspace_dashboard.py
```

Expect log lines like `workspace_doctor_dashboard_cleared deleted=N` and exit code `0`.

### Dev / prod (scheduled)

```text
# Example cron (scheduler timezone must be Asia/Kolkata)
0 0 * * *  cd /path/to/caepyplus_backend && python scripts/clear_linq360_workspace_dashboard.py
```

On ECS: Scheduled Task at `00:00` with timezone `Asia/Kolkata`, same command, same task role / `DATABASE_URL` as the API.

### After clear — what frontend sees

| Call | Token | Result until next webhook |
|------|-------|---------------------------|
| `GET /glance/appointments` | `workspace_access_token_main` | `appointments: 0`, `requests: 0`, `todays_schedule: []` (**200**) |
| `GET /glance/content` | `identity_access_token` | Unchanged (content still present) |
| WS | `workspace_access_token_main` | No automatic push from the clear job; next webhook may push after debounce |

### Flow

```text
00:00 IST  →  clear script  →  workspace_doctor_dashboard empty
                │
                ▼
GET /glance/appointments  →  empty schedule (OK for new day)
                │
                ▼
Appointment system POST /webhooks/dashboard  (full today's snapshot)
                │
                ▼
ensure_workspace_dashboard + upsert  →  today's schedule visible again
```

### Why no “recovery” pull in CAEPY

CAEPY does **not** have an API to list all of today’s appointments for a doctor. Schedule is push-only via webhook. Cleanup-only is enough when the appointment system keeps sending **full** snapshots after midnight / on first event of the day.

### Debounce note (related)

WS does **not** refresh every 2 seconds. `DEBOUNCE_WINDOW_MS` (default **2000**) is a quiet window **after a webhook**: coalesce events for the same `ws_user_id` + `workspace_id`, then one background refresh + one WS push. No events → no push.

---

## Config (ops / env)

| Env | Example / default | Meaning |
|-----|-------------------|---------|
| `ROOT_PATH` | `/caepy/api` | Prefix before `/v1/linq360` (local + dev) |
| `LINQMD_PRACTICE_HUB_API_URL` | `https://demo.linqmd.com` | Practice Hub base for pending-counts |
| `DEBOUNCE_WINDOW_MS` | `2000` | Quiet window after webhook before background refresh + WS push |
| `AI_SUGGESTIONS_OPEN_DOMAINS` | `["https://dev1.linqmd.com","https://app.linqmd.com"]` | Trusted Origins for webhook domain gate (**no** Bearer on webhook) |
| `WORKSPACE_JWT_SECRET` | same as portal `AUTH_JWT_SECRET` | Verify identity / select JWTs |

Sync URL CAEPY calls:

```text
{LINQMD_PRACTICE_HUB_API_URL}/api/linq360/pending-counts
→ https://demo.linqmd.com/api/linq360/pending-counts
```

Must be set on **ECS** for dev (laptop `.env` does not affect `dev1.caepy.linqmd.com`).

Redis is **not** required for debounce today (in-memory, single instance).

---

## curl cheat sheet (all endpoints)

Set tokens once:

```bash
# From login / select responses — never log raw tokens in shared chats
IDENTITY="<identity_access_token>"   # login data.access_token
SELECT="<workspace_access_token_main>"  # select data.access_token
```

### Local

```bash
BASE="http://127.0.0.1:8000/caepy/api/v1/linq360"

# Content sync — identity
curl -s -X POST "$BASE/glance/sync" \
  -H "Authorization: Bearer $IDENTITY" -H "Accept: application/json"

# Content GET — identity
curl -s "$BASE/glance/content" \
  -H "Authorization: Bearer $IDENTITY" -H "Accept: application/json"

# Appointments GET — select
curl -s "$BASE/glance/appointments" \
  -H "Authorization: Bearer $SELECT" -H "Accept: application/json"

# Webhook — no Bearer; body ids
curl -s -X POST "$BASE/webhooks/dashboard" \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -H "Origin: https://dev1.linqmd.com" \
  -d '{"ph_user_id":893,"ws_user_id":327,"workspace_id":161,"event_type":"appointment.created","appointments":2,"requests":1,"todays_schedule":[]}'

# Content engagement — Caepy JWT or identity
curl -s "$BASE/doctors/42/content-engagement" \
  -H "Authorization: Bearer $IDENTITY" -H "Accept: application/json"

# Daily clear (ops CLI — no HTTP token)
python scripts/clear_linq360_workspace_dashboard.py
```

### Dev

```bash
BASE="https://dev1.caepy.linqmd.com/caepy/api/v1/linq360"

curl -s -X POST "$BASE/glance/sync" \
  -H "Authorization: Bearer $IDENTITY" -H "Accept: application/json"

curl -s "$BASE/glance/content" \
  -H "Authorization: Bearer $IDENTITY" -H "Accept: application/json"

curl -s "$BASE/glance/appointments" \
  -H "Authorization: Bearer $SELECT" -H "Accept: application/json"

curl -s -X POST "$BASE/webhooks/dashboard" \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -H "Origin: https://dev1.linqmd.com" \
  -d '{"ph_user_id":893,"ws_user_id":327,"workspace_id":161,"event_type":"appointment.created","appointments":2,"requests":1,"todays_schedule":[]}'

curl -s "$BASE/doctors/42/content-engagement" \
  -H "Authorization: Bearer $IDENTITY" -H "Accept: application/json"
```

### WebSocket (browser)

```js
// token = workspace_access_token_main from select
const token = workspace_access_token_main;

// Local
const wsLocal = new WebSocket(
  `ws://127.0.0.1:8000/caepy/api/v1/linq360/ws/dashboard?token=${encodeURIComponent(token)}`
);

// Dev
const wsDev = new WebSocket(
  `wss://dev1.caepy.linqmd.com/caepy/api/v1/linq360/ws/dashboard?token=${encodeURIComponent(token)}`
);

wsDev.onmessage = (ev) => {
  const msg = JSON.parse(ev.data); // DashboardWsMessage
  // render msg.data like GET /glance/appointments → response.data
};
```

---

## Sequence diagrams

### Sync (frontend)

```text
Frontend                CAEPY                          Practice Hub
   │                      │                                 │
   │ POST {BASE}/glance/sync (empty body)                   │
   │ Authorization: Bearer <identity_access_token>          │
   │─────────────────────►│                                 │
   │                      │ GET {PH}/api/linq360/pending-counts
   │                      │ Authorization: Bearer <same identity>
   │                      │────────────────────────────────►│
   │                      │◄── { status_code, data.content }│
   │                      │ upsert doctor_dashboard         │
   │◄── content glance    │                                 │

Local BASE = http://127.0.0.1:8000/caepy/api/v1/linq360
Dev   BASE = https://dev1.caepy.linqmd.com/caepy/api/v1/linq360
PH         = https://demo.linqmd.com   (LINQMD_PRACTICE_HUB_API_URL)
```

### Webhook + debounce + WS

```text
Appt system             CAEPY                      Frontend (WS)
   │                      │                            │
   │ POST /webhooks/dashboard                          │
   │ NO Bearer; body ph/ws/workspace + full schedule   │
   │─────────────────────►│ upsert schedule NOW        │
   │                      │ enqueue debounce           │
   │◄── appointments glance                            │
   │                      │ ~2s quiet (same ws+workspace)
   │                      │ refresh sections → upsert  │
   │                      │───────────────────────────►│ WS JSON push
   │                      │   (select token on WS)     │
```

### Daily clear (ops)

```text
Cron (00:00 IST)        CAEPY CLI                     Postgres
   │                      │                              │
   │ run clear script     │                              │
   │─────────────────────►│ DELETE workspace_doctor_dashboard
   │                      │─────────────────────────────►│
   │                      │ doctor_dashboard untouched   │
   │◄── exit 0            │                              │
```

---

## Errors (frontend actions)

| HTTP / WS | Action |
|-----------|--------|
| `401` on content | Refresh / re-login → new `identity_access_token` |
| `401` / close `4401` on appointments/WS | Re-select workspace → new `workspace_access_token_main`; reconnect WS |
| `403` / close `4403` | Token missing workspace/user claims |
| `502` (incl. PH **522**) | Practice Hub unreachable from CAEPY; check `LINQMD_PRACTICE_HUB_API_URL` on ECS; soft fallback `GET /glance/content` |
| `404` | Dashboard not ready for this doctor |
| `422` | Fix webhook body / enum values |
| Sync `200` but content all zeros | Confirm PH returns non-zero for that identity token |

Missing id arrays → `[]`. Missing counts → `0`.
