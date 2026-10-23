# LinQ360 — Frontend Developer Handbook

Wire **Today-at-a-Glance** pending badges with these two CAEPY APIs:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/linq360/glance/sync` | Fresh pending data → save → return glance |
| `GET` | `/linq360/glance` | Read last stored glance |

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
              CAEPY calls Drupal pending-counts, stores todays_glance,
              returns GlanceResponse

3. Later     → GET /linq360/glance
              CAEPY returns stored todays_glance
```

```text
Drupal pending-counts  →  CAEPY (sync + store)  →  Frontend (sync / get)
```

---

## Base URL

```text
{ROOT_PATH}/api/v1/linq360/...
```

| Environment | Example |
|-------------|---------|
| Local | `http://localhost:8000/api/v1` |
| `ROOT_PATH=/caepy` | `http://host/caepy/api/v1` |

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

---

## Response (sync and get — same)

```json
{
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
  "appointments": {},
  "requests": {},
  "payments": {}
}
```

| Field | Use |
|-------|-----|
| `content.reviews.*` | Reviews badge + ids |
| `content.blog_comments.*` | Blog comments badge + ids |
| `content.podcast_comments.*` | Podcast comments badge + ids |
| `content.total_pending_counts` | Sum of the three |
| `appointments` / `requests` / `payments` | `{}` for now |

```ts
type GlanceResponse = {
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
  appointments: Record<string, unknown>;
  requests: Record<string, unknown>;
  payments: Record<string, unknown>;
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
   │                │ save todays_glance         │
   │◄── GlanceResponse ──│                       │
```

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
