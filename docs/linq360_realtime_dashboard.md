# LinQ360 Realtime Dashboard — What We Built

This document explains the **realtime webhook → debounce → Postgres → WebSocket** work: which files exist, what each function does, and how the pieces connect.

---

## End-to-end flow (short)

```text
Webhook POST /linq360/webhooks/dashboard
        │
        ▼
Authenticate (Bearer JWT → ph_user_id, ws_user_id, workspace_id)
        │
        ▼
Map event_type → dashboard sections (appointments / requests / content / payments)
        │
        ▼
Upsert schedule snapshot into Postgres immediately (if body has counts/schedule)
        │
        ▼
Enqueue debounce by group key (ws_user_id + workspace_id)
        │   (wait DEBOUNCE_WINDOW_MS, default 2000 ms; coalesce bursts)
        ▼
Refresh only affected sections → upsert Postgres again if needed
        │
        ▼
Publish WebSocket to room dashboard:{workspace_id}:{ws_user_id}
```

**Source of truth:** PostgreSQL glance tables.  
**WebSocket:** notifies the frontend after a successful refresh; it does not replace DB storage.  
**Redis:** not used yet (in-memory debounce). Optional later for multi-instance.

---

## Folder map

```text
src/app/linq360/
├── common/                          # Shared bases (DRY) — BaseController, etc.
├── config/
│   └── auth/workspace_auth.py       # Bearer + open-domain gate
└── dashboard/
    ├── config/
    │   ├── routing.py               # HTTP + WS routes
    │   └── dashboard_service.py     # Business: glance, webhook, schedule
    ├── dashboard_controller.py      # HTTP/WS handlers
    ├── dashboard_repository.py      # DB access
    ├── dashboard_response.py        # Glance API envelope helpers
    ├── dashboard_fields.py          # Schema re-exports
    ├── dashboard_content.py         # Pending content block helpers
    └── realtime/                    # ★ Realtime stack (this feature)
        ├── event_map.py
        ├── debounce.py
        ├── refresh_service.py
        ├── ws_hub.py
        └── __init__.py
```

---

## 1. `realtime/event_map.py` — What changed? Which sections?

Maps webhook **event names** to dashboard **sections**, and builds group/room keys.

| Name | Type | What it does |
|------|------|----------------|
| `DashboardSection` | Enum | Sections: `appointments`, `requests`, `content`, `payments` |
| `EVENT_SECTION_MAP` | Dict | e.g. `appointment.created` → appointments only; `review.created` → content |
| `group_key(ws_user_id, workspace_id)` | Function | Returns `(ws_user_id, workspace_id)` — debounce grouping key |
| `room_name(ws_user_id, workspace_id)` | Function | Returns `dashboard:{workspace_id}:{ws_user_id}` — WebSocket room |
| `sections_for_event(event_type)` | Function | Looks up which sections to refresh; empty/`None` → `dashboard.snapshot` (appointments + requests) |
| `merge_sections(*groups)` | Function | Union of several section sets |
| `ws_event_name(sections)` | Function | Picks push event name: `appointments_updated`, `requests_updated`, `content_counts_updated`, `payments_updated`, or `dashboard_updated` |

**Example events**

| `event_type` | Sections refreshed |
|--------------|--------------------|
| `appointment.created` / `.updated` / `.cancelled` / `.completed` | appointments |
| `request.created` / `.accepted` / `.rejected` | requests |
| `review.*` / `comment.*` / `blog_comment.*` / `podcast_comment.*` | content |
| `payment.created` / `.updated` | payments |
| missing / unknown / `dashboard.snapshot` | appointments + requests |

---

## 2. `realtime/debounce.py` — Wait X ms, merge bursts

In-memory coordinator (one process). Window from env `DEBOUNCE_WINDOW_MS` (default **2000**).

| Name | What it does |
|------|----------------|
| `InMemoryDebounceCoordinator` | Holds pending sections per `(ws_user_id, workspace_id)` |
| `__init__(window_ms)` | Sets quiet window |
| `configure(window_ms=…)` | Change window at runtime |
| `set_callback(callback)` | Sets the function to run after the window (wired to refresh) |
| `schedule(ws_user_id, workspace_id, sections, context)` | Start/reset timer; merge sections; store context (token, counts, schedule) |
| `_fire_after_window(key)` | After sleep: call callback; if more events arrived while running, schedule a follow-up |
| `get_debounce_coordinator()` | Process singleton |
| `reset_debounce_coordinator_for_tests()` | Clear singleton in tests |

**Behaviour**

- Same doctor/workspace events within 2s → **one** refresh with **merged** sections.
- Different `ws_user_id` / `workspace_id` → separate timers.
- If a refresh is already running for that key → queue a **follow-up** so the latest state is not lost.

---

## 3. `realtime/refresh_service.py` — After quiet window: refresh + notify

| Name | What it does |
|------|----------------|
| `run_debounced_refresh(ws_user_id, workspace_id, sections, context)` | Opens a DB session; refreshes **only** listed sections; builds glance snapshot; publishes WebSocket |
| `ensure_debounce_wired()` | Sets debounce callback → `run_debounced_refresh` |
| `enqueue_dashboard_event(…)` | Public entry: wire debounce + `schedule(...)` |

**Inside `run_debounced_refresh`**

1. If sections include appointments/requests **and** context has snapshot fields → `upsert_workspace_schedule`.
2. If sections include content **and** Bearer token present → `fetch_pending_counts` + `upsert_pending_glance`.
3. Payments: no external source yet (glance `payments` stays `{}`).
4. Load merged glance → `get_dashboard_ws_hub().publish(...)`.

---

## 4. `realtime/ws_hub.py` — Who is listening?

In-process room registry (single instance).

| Name | What it does |
|------|----------------|
| `DashboardWsHub` | Map of room name → set of WebSocket connections |
| `connect(websocket, ws_user_id, workspace_id)` | Accept socket; join `dashboard:{workspace_id}:{ws_user_id}` |
| `disconnect(websocket, room)` | Leave room; drop empty rooms |
| `publish(ws_user_id, workspace_id, sections, snapshot)` | Send JSON to everyone in that room |
| `get_dashboard_ws_hub()` | Process singleton |
| `reset_dashboard_ws_hub_for_tests()` | Clear singleton in tests |

**Push payload shape**

```json
{
  "event": "dashboard_updated",
  "ws_user_id": 325,
  "workspace_id": 161,
  "sections": ["appointments", "requests"],
  "timestamp": "2026-10-30T12:00:00+00:00",
  "data": { "...glance snapshot..." }
}
```

---

## 5. How the webhook uses all of this

### File: `dashboard/config/dashboard_service.py`

Important method: **`process_dashboard_webhook`**

1. Decode JWT → `ph_user_id`, `workspace_id`, `ws_user_id` (ws_user_id required for grouping).
2. `sections_for_event(event_type)`.
3. Upsert appointments/requests/`todays_schedule` into Postgres **immediately** (authoritative body).
4. `enqueue_dashboard_event(...)` with sections + context (token, counts, schedule).
5. Return current `get_glance(...)` in the HTTP response (client does not wait for the full debounce cycle).

Other useful methods in the same file:

| Method | Role |
|--------|------|
| `get_glance` | Merge doctor content + workspace schedule into glance document |
| `upsert_pending_glance` | Write Drupal pending content into `doctor_dashboard` |
| `sync_pending_glance` | Call Drupal pending-counts, then upsert + return glance |
| `upsert_workspace_schedule` | Write counts + `todays_schedule` on workspace row |
| `get_engagement` | Content engagement rollup (reviews/blog/podcast) |

---

## 6. HTTP / WS entrypoints

### File: `dashboard/dashboard_controller.py`

| Handler | Route (via routing) | Role |
|---------|---------------------|------|
| `get_glance` | `GET /linq360/glance` | Read stored glance |
| `sync_glance` | `POST /linq360/glance/sync` | Pull Drupal pending → store → return glance |
| `dashboard_webhook` | `POST /linq360/webhooks/dashboard` | Schedule upsert + debounce enqueue |
| `dashboard_websocket` | `WS /linq360/ws/dashboard?token=…` | Auth from token; join authorized room only |
| `get_content_engagement` | `GET /linq360/doctors/{id}/content-engagement` | Engagement stats (JWT app user) |

### File: `dashboard/config/routing.py`

Registers the routes above on FastAPI routers (`router` / `public_router`).

### Auth: `config/auth/workspace_auth.py`

| Function | Role |
|----------|------|
| `require_workspace_select_auth` | Require Bearer; parse JWT claims |
| `require_dashboard_webhook_auth` | Bearer **or** trusted Origin/Referer gate; write still needs Bearer for identity |

---

## 7. Supporting dashboard files (not only realtime)

| File | Role |
|------|------|
| `dashboard_repository.py` | `get_*` / `ensure_*` for `workspace_doctor_dashboard` and `doctor_dashboard` |
| `dashboard_content.py` | Build/parse pending content JSON blocks |
| `dashboard_response.py` | Wrap glance data in `{status_code, msg, data}` |
| `dashboard_fields.py` | Re-export pydantic schemas used by routes |

---

## 8. Config / env

| Variable | Where | Meaning |
|----------|--------|---------|
| `DEBOUNCE_WINDOW_MS` | `src/app/core/config.py` + `.env.example` | Quiet window (ms); default `2000` |
| `AI_SUGGESTIONS_OPEN_DOMAINS` | same | Trusted origins for webhook domain gate |

---

## 9. APIs to call (local with `ROOT_PATH=/caepy/api`)

| Method | Path |
|--------|------|
| POST | `/caepy/api/v1/linq360/webhooks/dashboard` |
| GET | `/caepy/api/v1/linq360/glance` |
| POST | `/caepy/api/v1/linq360/glance/sync` |
| WS | `/caepy/api/v1/linq360/ws/dashboard?token=<workspace_select_access_token>` |

Webhook body example:

```json
{
  "event_type": "appointment.created",
  "appointments": 2,
  "requests": 1,
  "todays_schedule": [ /* patient objects */ ]
}
```

Identity (`ph_user_id`, `ws_user_id`, `workspace_id`) comes from the JWT, not the body.

---

## 10. Tests

| File | Covers |
|------|--------|
| `tests/linq360/test_dashboard_realtime.py` | Event map, room key, debounce coalesce, isolation, follow-up while running |
| `tests/services/test_content_aggregator_service.py` | Webhook still upserts schedule immediately |
| `tests/api/test_workspace_auth.py` | Workspace select Bearer auth |

---

## Mental model (one sentence)

**Webhook writes schedule now, groups more work by `ws_user_id` + `workspace_id`, waits ~2 seconds so bursts become one refresh, updates only the sections that event touched, saves Postgres, then pushes that glance to the matching WebSocket room.**
