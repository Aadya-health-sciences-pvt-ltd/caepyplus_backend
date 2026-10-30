# LinQ360 — Frontend Developer Handbook

Wire **Today-at-a-Glance** with these CAEPY APIs:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/linq360/glance/sync` | Fresh pending content → save → return glance |
| `GET` | `/linq360/glance` | Read last stored glance |
| `POST` | `/linq360/webhooks/dashboard` | Appointment webhook: upsert schedule → debounce refresh by `ws_user_id`+`workspace_id` → return glance |
| `WS` | `/linq360/ws/dashboard?token=…` | Realtime room `dashboard:{workspace_id}:{ws_user_id}` after debounced upsert |

---

## Where this continues from

Practice Hub (Drupal) already has:

```http
GET {PRACTICE_HUB}/api/linq360/pending-counts
Authorization: Bearer <workspace_select_access_token>
```

That API returns pending reviews / blog comments / podcast comments (counts + id arrays).

**From there, CAEPY continues** — the frontend only talks to CAEPY:

```text
1. Portal login → select doctor workspace
       → workspace_select_access_token
       (JWT: appointment_doctor_id = Drupal doctor uid)

2. Frontend → POST /linq360/glance/sync  (Bearer token)
              CAEPY calls Drupal pending-counts,
              stores content in doctor_dashboard.todays_glance,
              returns merged GlanceResponse

3. Appointment system → POST /linq360/webhooks/dashboard
              (Bearer + body: appointments, requests, todays_schedule)
              CAEPY stores workspace counts/schedule, then runs pending sync,
              returns full glance envelope

4. Later     → GET /linq360/glance
              content          ← doctor_dashboard.todays_glance
              appointments     ← int count
              requests         ← int count
              todays_schedule  ← patient array
              payments         ← {}
```

```text
Drupal pending-counts ──► sync ──┐
                                 ├──► Postgres ──► GET glance / webhook response
Appointment webhook ─────────────┘
```

---

## Base URL

With `ROOT_PATH=/caepy/api` (default local setup), LinQ360 routes are:

```text
http://127.0.0.1:8000/caepy/api/v1/linq360/...
```

| Method | Full path |
|--------|-----------|
| `POST` | `/caepy/api/v1/linq360/glance/sync` |
| `GET` | `/caepy/api/v1/linq360/glance` |
| `POST` | `/caepy/api/v1/linq360/webhooks/dashboard` |

---

## Auth

```http
Authorization: Bearer <workspace_select_access_token>
```

| JWT claim | Meaning |
|-----------|---------|
| `appointment_doctor_id` | Drupal doctor uid (required) |
| `workspace_id` | Portal workspace id |
| `user_id` | Portal user id |

No doctor uid in URL or body — it comes from the token. Bad / missing token → **401**.

---

## APIs

### Sync

```http
POST {BASE}/linq360/glance/sync
Authorization: Bearer <workspace_select_access_token>
```

No body, no query params. Returns glance JSON below.

| Status | When |
|--------|------|
| `200` | OK |
| `401` | Bad token |
| `502` | Practice Hub failed |
| `404` | Rare: cannot store row |

### Get

```http
GET {BASE}/linq360/glance
Authorization: Bearer <workspace_select_access_token>
```

No query params. Empty store → zeros / `[]` with **200**.

| Status | When |
|--------|------|
| `200` | OK |
| `401` | Bad token |

### Dashboard webhook (appointments + requests + schedule)

```http
POST {BASE}/linq360/webhooks/dashboard
Authorization: Bearer <workspace_select_access_token>
Origin: https://dev1.linqmd.com
Content-Type: application/json
```

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

Identity comes from the Bearer JWT only (`appointment_doctor_id` → `ph_user_id`, `workspace_id`, `user_id` → `ws_user_id`). Body does **not** send those three ids.

Optional `event_type` maps to dashboard sections (appointments / requests / content / payments). Default snapshot refreshes appointments + requests. Schedule is upserted immediately; further section refresh is **debounced** (`DEBOUNCE_WINDOW_MS`, default 2000) grouped by `ws_user_id` + `workspace_id`, then pushed on WebSocket.

Auth gate (Nest-style): trusted `Origin`/`Referer` listed in `AI_SUGGESTIONS_OPEN_DOMAINS` **or** Bearer. A successful write still requires Bearer so the doctor/workspace can be resolved. Response is the same glance envelope (`msg`: `Dashboard webhook processed successfully`).

### Dashboard WebSocket

```http
WS {BASE}/linq360/ws/dashboard?token=<workspace_select_access_token>
```

Server joins room `dashboard:{workspace_id}:{ws_user_id}` from the JWT (client cannot pick the room). After debounced upsert, server sends JSON like `{ "event": "dashboard_updated", "sections": [...], "timestamp": "...", "data": { ...glance } }`.

| Status | When |
|--------|------|
| `200` | OK |
| `401` | Missing/bad Bearer (domain-only is not enough for identity) |
| `502` | Practice Hub sync failed |
| `422` | Invalid body |

---

## Response (sync, get, and webhook — same envelope)

Read glance fields from **`response.data`**.

```json
{
  "status_code": 200,
  "msg": "Glance retrieved successfully",
  "data": {
    "content": {
      "reviews": {
        "pending_count": 2,
        "review_id": [101, 102]
      },
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
}
```

| Field | Use |
|-------|-----|
| `status_code` | `200` on success |
| `msg` | GET: `Glance retrieved successfully`; sync: `Glance synced successfully` |
| `data.content.*` | Pending content badges + ids |
| `data.appointments` | Integer count for dashboard appointments badge |
| `data.requests` | Integer count for dashboard requests badge |
| `data.todays_schedule` | Patient detail array for today’s schedule |
| `data.payments` | `{}` until filled |

```ts
type ScheduleItem = {
  patient_meta_code: string;
  appointment_type: string;
  patient_name: string;
  first_name: string;
  last_name: string;
  consultation_type: string;
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
```

---

## When to call which

| Situation | Call |
|-----------|------|
| First load after workspace select | `POST …/glance/sync` |
| Switched doctor (new token) | `POST …/glance/sync` |
| Need fresh numbers | `POST …/glance/sync` |
| Soft refresh of last stored | `GET …/glance` |

---

## Sequence (sync)

```text
Frontend          CAEPY                    Practice Hub
   │                │                            │
   │ POST /glance/sync                           │
   │ Bearer ws_token                             │
   │───────────────►│                            │
   │                │ GET …/pending-counts       │
   │                │ Bearer ws_token            │
   │                │───────────────────────────►│
   │                │◄────── pending JSON ───────│
   │                │ save doctor_dashboard      │
   │                │   .todays_glance (content) │
   │◄── GlanceResponse ──│                       │
```

GET reads `doctor_dashboard` + `workspace_doctor_dashboard` and merges the same shape.

---

## Errors

| HTTP | Action |
|------|--------|
| `401` | Refresh / re-select workspace token |
| `502` | Show refresh failed; optional fallback to `GET /glance` |
| `404` | Dashboard not ready for this doctor |

Missing ids → `[]`. Missing counts → `0`.

---

## curl

```bash
curl -s -X POST "{BASE}/linq360/glance/sync" \
  -H "Authorization: Bearer YOUR_WORKSPACE_SELECT_TOKEN" \
  -H "Accept: application/json"

curl -s "{BASE}/linq360/glance" \
  -H "Authorization: Bearer YOUR_WORKSPACE_SELECT_TOKEN" \
  -H "Accept: application/json"
```
