# LinQ360 — Frontend / Integration Handbook

Precise contract for **Today-at-a-Glance**: REST APIs, WebSocket, headers, bodies, responses, tables, and end-to-end flow.

---

## Base URL

With `ROOT_PATH=/caepy/api` (local default):

```text
http://127.0.0.1:8000/caepy/api/v1/linq360
```

Below, `{BASE}` = `/caepy/api/v1/linq360`.

| Method | Path | Who calls | Purpose |
|--------|------|-----------|---------|
| `POST` | `{BASE}/glance/sync` | Frontend | Pull Drupal pending content → save → return glance |
| `GET` | `{BASE}/glance` | Frontend | Read last stored glance (no Drupal call) |
| `POST` | `{BASE}/webhooks/dashboard` | Appointment backend | Upsert schedule/counts; debounce refresh; return glance |
| `WS` | `{BASE}/ws/dashboard?token=…` | Frontend | Realtime pushes after debounced refresh |
| `GET` | `{BASE}/doctors/{doctor_id}/content-engagement` | App (CAEPY JWT) | Published engagement rollup (not glance) |

Glance / webhook / WS use the **workspace select** token. Content-engagement uses the **CAEPY app JWT**.

Internals (debounce files, functions): [`linq360_realtime_dashboard.md`](./linq360_realtime_dashboard.md).

---

## Auth

### Workspace select token (glance, sync, webhook, WS)

```http
Authorization: Bearer <workspace_select_access_token>
```

WebSocket: same token as query `?token=` (see WS section).

| JWT claim | CAEPY uses as | Required |
|-----------|---------------|----------|
| `appointment_doctor_id` | `ph_user_id` / glance doctor key | Yes (always) |
| `user_id` | `ws_user_id` | Yes for webhook debounce + WS room |
| `workspace_id` | `workspace_id` | Yes for workspace row + WS room |

**Do not** put `ph_user_id` / `ws_user_id` / `workspace_id` in the webhook JSON — identity is JWT-only.

Missing/invalid Bearer → **401** (HTTP) or WS close **4401**.

Webhook also accepts trusted `Origin` / `Referer` from `AI_SUGGESTIONS_OPEN_DOMAINS`, but **Bearer is still required** for identity.

### CAEPY JWT (content-engagement only)

```http
Authorization: Bearer <caepy_access_token>
```

Caller must be the doctor themselves, or `ADMIN` / `OPERATION` / `CONTENT_CREATOR`.

---

## End-to-end flow

```text
1. Portal login → select doctor workspace
      → workspace_select_access_token
      JWT: appointment_doctor_id, user_id, workspace_id

2. Frontend opens WS
      WS {BASE}/ws/dashboard?token=<token>
      Server joins room dashboard:{workspace_id}:{ws_user_id}
      (room from JWT only — client cannot pick room)

3. Frontend first load
      POST {BASE}/glance/sync
      → CAEPY calls Drupal GET …/pending-counts
      → saves doctor_dashboard.todays_glance
      → returns full glance envelope

4. Soft re-read
      GET {BASE}/glance
      → merge doctor_dashboard + workspace_doctor_dashboard
      → no Drupal call

5. Appointment system pushes schedule
      POST {BASE}/webhooks/dashboard
      → upsert appointments/requests/todays_schedule NOW
      → enqueue debounce (group: ws_user_id + workspace_id)
      → HTTP returns current glance immediately
      → after ~2s quiet window: refresh mapped sections → upsert → WS push

6. Frontend receives WS JSON
      { event, sections, timestamp, data: <same glance shape as REST data> }
```

```text
                    ┌─────────────────────┐
  Drupal pending ──►│ POST /glance/sync   │──► doctor_dashboard.todays_glance
                    └─────────────────────┘
                                                    │
                    ┌─────────────────────┐         │ merge
  Appointment ─────►│ POST /webhooks/…    │──► workspace_doctor_dashboard
  system            │  + debounce + WS    │         │
                    └─────────────────────┘         ▼
                                              GET /glance
                                              WS push (data)
```

### How sync vs debounce works (important)

| Data | When it updates |
|------|-----------------|
| `appointments` / `requests` / `todays_schedule` from webhook body | **Immediately** on webhook (body is authoritative) |
| Pending content (reviews / blog / podcast) | `POST /glance/sync`, or webhook `event_type` → **content** (Drupal pull after debounce) |
| Debounce (~2s, `DEBOUNCE_WINDOW_MS`) | Same `ws_user_id` + `workspace_id` → one background refresh + one WS push |
| Continuous full sync on every event | **No** — only mapped sections |

**Webhook rule:** always send the **current full snapshot** of `appointments`, `requests`, and `todays_schedule`. Omitted fields default to `0` / `[]` and **overwrite** stored values.

---

## 1) POST `/glance/sync`

Pull Drupal pending counts and store content.

### Headers

```http
Authorization: Bearer <workspace_select_access_token>
Accept: application/json
```

### Body

None (empty).

### Success response `200`

```json
{
  "status_code": 200,
  "msg": "Glance synced successfully",
  "data": { /* GlanceData — see Shared glance shape */ }
}
```

### Errors

| HTTP | Meaning |
|------|---------|
| `401` | Bad / missing token |
| `404` | Cannot store dashboard for this doctor uid |
| `502` | Practice Hub pending-counts failed |

---

## 2) GET `/glance`

Read last stored merge (no Drupal call).

### Headers

```http
Authorization: Bearer <workspace_select_access_token>
Accept: application/json
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

### Headers

```http
Authorization: Bearer <workspace_select_access_token>
Content-Type: application/json
Accept: application/json
Origin: https://dev1.linqmd.com
```

`Origin` / `Referer` may match `AI_SUGGESTIONS_OPEN_DOMAINS`, but **Bearer is still required** so JWT can identify the doctor/workspace.

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

### Connect

```text
ws://127.0.0.1:8000/caepy/api/v1/linq360/ws/dashboard?token=<workspace_select_access_token>
```

(Use `wss://` in production.)

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
| After workspace select (first paint) | Open **WS**, then `POST /glance/sync` |
| Soft refresh of last stored | `GET /glance` |
| Need fresh pending content | `POST /glance/sync` |
| Switched doctor (new token) | Reconnect **WS** with new token + `POST /glance/sync` |
| Live schedule/badge updates | Listen on **WS** (appointment system hits webhook) |

Frontend does **not** call `/webhooks/dashboard` — that is the appointment backend.

---

## 5) GET `/doctors/{doctor_id}/content-engagement`

Published engagement metrics (not Today-at-a-Glance).

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

| Env | Default | Meaning |
|-----|---------|---------|
| `DEBOUNCE_WINDOW_MS` | `2000` | Quiet window before background refresh + WS push |
| `AI_SUGGESTIONS_OPEN_DOMAINS` | `[]` | Trusted Origins for webhook domain gate (Bearer still required) |
| `ROOT_PATH` | `/caepy/api` | API prefix before `/v1/linq360` |

Redis is **not** required for debounce today (in-memory, single instance).

---

## curl examples

```bash
BASE="http://127.0.0.1:8000/caepy/api/v1/linq360"
TOKEN="YOUR_WORKSPACE_SELECT_TOKEN"

# Sync pending content
curl -s -X POST "$BASE/glance/sync" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json"

# Read stored glance
curl -s "$BASE/glance" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json"

# Appointment webhook (backend → CAEPY)
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
const ws = new WebSocket(
  `ws://127.0.0.1:8000/caepy/api/v1/linq360/ws/dashboard?token=${encodeURIComponent(token)}`
);
ws.onmessage = (ev) => {
  const msg = JSON.parse(ev.data); // DashboardWsMessage
  // render msg.data like GET /glance
};
```

---

## Sequence diagrams

### Sync (frontend)

```text
Frontend                CAEPY                     Practice Hub
   │                      │                            │
   │ POST /glance/sync    │                            │
   │ Authorization: Bearer│                            │
   │─────────────────────►│                            │
   │                      │ GET /api/linq360/pending-counts
   │                      │ Authorization: Bearer      │
   │                      │───────────────────────────►│
   │                      │◄──── pending JSON ─────────│
   │                      │ save doctor_dashboard      │
   │◄── GlanceApiResponse │                            │
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
| `502` | Show sync failed; optional fallback `GET /glance` |
| `404` | Dashboard not ready for this doctor |
| `422` | Fix webhook body / enum values |

Missing id arrays → `[]`. Missing counts → `0`.
