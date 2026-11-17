# LinQ360 — Frontend / Integration Handbook

Precise contract for **Today-at-a-Glance**: REST APIs, WebSocket, headers, bodies, responses, tables, and end-to-end flow.

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

### Full URLs (copy/paste)

| API | Local | Dev |
|-----|-------|-----|
| Sync | `POST …/glance/sync` | same path on `dev1.caepy.linqmd.com` |
| Content GET | `GET …/glance/content` | same |
| Appointments GET | `GET …/glance/appointments` | same |
| Webhook | `POST …/webhooks/dashboard` | same |
| WebSocket | `ws(s)://…/ws/dashboard?token=…` | same |

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

### CAEPY JWT / identity (content-engagement + doctor CRUD)

```http
Authorization: Bearer <caepy_access_token>
# or, when WORKSPACE_JWT_SECRET is configured:
Authorization: Bearer <identity_access_token>
```

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

### How to call

| | Local | Dev |
|-|-------|-----|
| Method | `POST` | `POST` |
| URL | `http://127.0.0.1:8000/caepy/api/v1/linq360/glance/sync` | `https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/glance/sync` |
| Body | empty | empty |
| Auth | identity Bearer | identity Bearer |

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

Read stored **content** only (no Practice Hub call). Identity token.

### How to call

| | Local | Dev |
|-|-------|-----|
| Method | `GET` | `GET` |
| URL | `http://127.0.0.1:8000/caepy/api/v1/linq360/glance/content` | `https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/glance/content` |
| Auth | identity Bearer | identity Bearer |

```bash
curl "http://127.0.0.1:8000/caepy/api/v1/linq360/glance/content" \
  -H "Authorization: Bearer <identity_access_token>" \
  -H "Accept: application/json"
```

### Headers

```http
Authorization: Bearer <identity_access_token>
Accept: application/json
```

### Response `data`

```json
{ "content": { "reviews": {}, "blog_comments": {}, "podcast_comments": {}, "total_pending_counts": 0 }, "payments": {} }
```

## 2b) GET `/glance/appointments`

Read stored **appointments** only. Workspace select token.

### How to call

| | Local | Dev |
|-|-------|-----|
| Method | `GET` | `GET` |
| URL | `http://127.0.0.1:8000/caepy/api/v1/linq360/glance/appointments` | `https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/glance/appointments` |
| Auth | `workspace_access_token_main` | same |

```bash
curl "http://127.0.0.1:8000/caepy/api/v1/linq360/glance/appointments" \
  -H "Authorization: Bearer <workspace_access_token_main>" \
  -H "Accept: application/json"
```

### Headers

```http
Authorization: Bearer <workspace_access_token_main>
Accept: application/json
```

### Response `data`

```json
{ "appointments": 2, "requests": 1, "todays_schedule": [] }
```

### Body / query

None.

### Success response `200`

```json
{
  "status_code": 200,
  "msg": "Glance retrieved successfully",
  "data": { /* GlanceData */ }
}
```

Empty store → zeros / `[]` with **200**.

### Errors

| HTTP | Meaning |
|------|---------|
| `401` | Bad / missing token |

---

## 3) POST `/webhooks/dashboard`

Appointment backend → CAEPY. Upserts schedule; debounces section refresh; returns glance.

### How to call

| | Local | Dev |
|-|-------|-----|
| Method | `POST` | `POST` |
| URL | `http://127.0.0.1:8000/caepy/api/v1/linq360/webhooks/dashboard` | `https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/webhooks/dashboard` |
| Body | JSON (see below) | JSON (see below) |
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
| `event_type` | string \| null | No | Maps to sections; omit → appointments + requests |
| `appointments` | int | No (default `0`) | Badge count |
| `requests` | int | No (default `0`) | Badge count |
| `todays_schedule` | array | No (default `[]`) | Patient rows |

#### `todays_schedule[]` item

| Field | Allowed values |
|-------|----------------|
| `patient_meta_code` | string |
| `appointment_type` | `REQUEST` \| `BOOKING` \| `CALL` |
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
| `401` | Bad/missing Bearer or missing `user_id` on token |
| `404` | Cannot store dashboard row |
| `422` | Invalid body |
| `502` | Upstream failure (rare on schedule-only path) |

---

## 4) WebSocket `/ws/dashboard`

### How to call

| | Local | Dev |
|-|-------|-----|
| Protocol | `ws://` | `wss://` |
| URL | `ws://127.0.0.1:8000/caepy/api/v1/linq360/ws/dashboard?token=<workspace_access_token_main>` | `wss://dev1.caepy.linqmd.com/caepy/api/v1/linq360/ws/dashboard?token=<workspace_access_token_main>` |
| Body | none (server pushes) | none (server pushes) |
| Auth | `token` query (`workspace_access_token_main`) | same |

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

Frontend should treat `data` like `GET /glance` → `response.data`, then re-render badges/schedule.

---

## Shared glance shape (`response.data` / WS `data`)

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
  "appointments": 1,
  "requests": 0,
  "payments": {},
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

| Field | Source table / column |
|-------|------------------------|
| `content` | `linq360.doctor_dashboard.todays_glance` |
| `appointments` | `workspace_doctor_dashboard.appointments` → int count |
| `requests` | `workspace_doctor_dashboard.requests` → int count |
| `todays_schedule` | `workspace_doctor_dashboard.appointment_json.todays_schedule` |
| `payments` | Always `{}` for now |

### TypeScript

```ts
type ScheduleItem = {
  patient_meta_code: string;
  appointment_type: "REQUEST" | "BOOKING" | "CALL";
  patient_name: string;
  first_name: string;
  last_name: string;
  consultation_type: "in-person" | "teleconsultation";
  time_slot: string;
};

type GlanceData = {
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
  appointments: number;
  requests: number;
  payments: Record<string, unknown>;
  todays_schedule: ScheduleItem[];
};

type GlanceApiResponse = {
  status_code: number;
  msg: string;
  data: GlanceData;
};

type DashboardWsMessage = {
  event: string;
  ws_user_id: number;
  workspace_id: number;
  sections: string[];
  timestamp: string;
  data: GlanceData;
};
```

---

## When frontend should call what

| Situation | Call |
|-----------|------|
| After login (first paint) | `POST /glance/sync` with **identity** token; open **WS** only after select (appointments) |
| Soft refresh of last stored | `GET /glance` |
| Need fresh pending content | `POST /glance/sync` |
| Switched doctor (new token) | Reconnect **WS** with new token + `POST /glance/sync` |
| Live schedule/badge updates | Listen on **WS** (appointment system hits webhook) |

Frontend does **not** call `/webhooks/dashboard` — that is the appointment backend.

---

## 5) GET `/doctors/{doctor_id}/content-engagement`

Published engagement metrics (not Today-at-a-Glance).

### How to call

| | Local | Dev |
|-|-------|-----|
| Method | `GET` | `GET` |
| URL | `http://127.0.0.1:8000/caepy/api/v1/linq360/doctors/{doctor_id}/content-engagement` | `https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/doctors/{doctor_id}/content-engagement` |
| Path param | `doctor_id` = CAEPY doctor id | same |
| Body | none | none |
| Auth | **CAEPY app JWT** or **identity_access_token** (if `WORKSPACE_JWT_SECRET` set) | same |

**Local**
```bash
curl "http://127.0.0.1:8000/caepy/api/v1/linq360/doctors/42/content-engagement" \
  -H "Authorization: Bearer <caepy_access_token>" \
  -H "Accept: application/json"
```

**Dev**
```bash
curl "https://dev1.caepy.linqmd.com/caepy/api/v1/linq360/doctors/42/content-engagement" \
  -H "Authorization: Bearer <caepy_access_token>" \
  -H "Accept: application/json"
```

### Headers

```http
Authorization: Bearer <caepy_access_token>
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
content          ← doctor_dashboard.todays_glance
appointments     ← as_count(workspace.appointments)
requests         ← as_count(workspace.requests)
todays_schedule  ← workspace.appointment_json.todays_schedule
payments         ← {}
```

---

## Config (ops / env)

| Env | Example / default | Meaning |
|-----|-------------------|---------|
| `ROOT_PATH` | `/caepy/api` | Prefix before `/v1/linq360` (local + dev) |
| `LINQMD_PRACTICE_HUB_API_URL` | `https://demo.linqmd.com` | Practice Hub base for pending-counts |
| `DEBOUNCE_WINDOW_MS` | `2000` | Quiet window before background refresh + WS push |
| `AI_SUGGESTIONS_OPEN_DOMAINS` | `["https://dev1.linqmd.com","https://app.linqmd.com"]` | Trusted Origins for webhook domain gate (Bearer still required) |

Sync URL CAEPY calls:

```text
{LINQMD_PRACTICE_HUB_API_URL}/api/linq360/pending-counts
→ https://demo.linqmd.com/api/linq360/pending-counts
```

Must be set on **ECS** for dev (laptop `.env` does not affect `dev1.caepy.linqmd.com`).

Redis is **not** required for debounce today (in-memory, single instance).

---

## curl examples

### Local

```bash
BASE="http://127.0.0.1:8000/caepy/api/v1/linq360"
TOKEN="YOUR_WORKSPACE_SELECT_TOKEN"

curl -s -X POST "$BASE/glance/sync" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json"

curl -s "$BASE/glance" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json"
```

### Dev

```bash
BASE="https://dev1.caepy.linqmd.com/caepy/api/v1/linq360"
TOKEN="YOUR_WORKSPACE_SELECT_TOKEN"

curl -s -X POST "$BASE/glance/sync" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json"

curl -s "$BASE/glance" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json"
```

### Webhook (appointment backend → CAEPY)

```bash
# Local or Dev: set BASE accordingly
curl -s -X POST "$BASE/webhooks/dashboard" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Origin: https://dev1.linqmd.com" \
  -d '{
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

WebSocket (browser):

```js
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
  // render msg.data like GET /glance
};
```

---

## Sequence diagrams

### Sync (frontend)

```text
Frontend                CAEPY                          Practice Hub
   │                      │                                 │
   │ POST {BASE}/glance/sync (empty body)                   │
   │ Authorization: Bearer│                                 │
   │─────────────────────►│                                 │
   │                      │ GET {PH}/api/linq360/pending-counts
   │                      │ Authorization: Bearer           │
   │                      │────────────────────────────────►│
   │                      │◄── { status_code, data.content }│
   │                      │ unwrap data.content             │
   │                      │ upsert doctor_dashboard         │
   │◄── GlanceApiResponse │                                 │

Local BASE = http://127.0.0.1:8000/caepy/api/v1/linq360
Dev   BASE = https://dev1.caepy.linqmd.com/caepy/api/v1/linq360
PH         = https://demo.linqmd.com   (LINQMD_PRACTICE_HUB_API_URL)
```

### Webhook + debounce + WS

```text
Appt system             CAEPY                      Frontend (WS)
   │                      │                            │
   │ POST /webhooks/dashboard                          │
   │ Bearer + JSON body   │                            │
   │─────────────────────►│ upsert schedule NOW        │
   │                      │ enqueue debounce           │
   │◄── GlanceApiResponse │                            │
   │                      │ ~2s quiet (same ws+workspace)
   │                      │ refresh sections → upsert  │
   │                      │───────────────────────────►│ WS JSON push
```

---

## Errors (frontend actions)

| HTTP / WS | Action |
|-----------|--------|
| `401` / close `4401` | Re-select workspace; refresh token; reconnect WS |
| `403` / close `4403` | Token missing workspace/user claims |
| `502` (incl. PH **522**) | Practice Hub unreachable from CAEPY; check `LINQMD_PRACTICE_HUB_API_URL` on ECS; optional fallback `GET /glance` |
| `404` | Dashboard not ready for this doctor |
| `422` | Fix webhook body / enum values |
| Sync `200` but content all zeros | Deploy pending-counts `data.content` unwrap; confirm PH returns non-zero for that token |

Missing id arrays → `[]`. Missing counts → `0`.
