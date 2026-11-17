# Content Aggregators (LinQ360)

Two separate concerns:

1. **Published metrics** — source aggregators + `linq360.content_source_aggregator`
   + `GET …/content-engagement` (approved / published item counts and ratings).
2. **Pending moderation inbox badge** — content in `doctor_dashboard.todays_glance`,
   workspace cards on `workspace_doctor_dashboard`; filled by Practice Hub pull-sync.

## Pending counts flow (counts only)

```text
Workspace login → identity_access_token
        ↓
CAEPY POST /v1/linq360/glance/sync   (Bearer identity)
        ↓
Drupal GET /api/linq360/pending-counts
        ↓
doctor_dashboard.todays_glance
        ↓
CAEPY GET /v1/linq360/glance/content   (Bearer identity) — content only

workspace select → workspace_access_token_main
        ↓
CAEPY GET /v1/linq360/glance/appointments   (Bearer select)
WS /ws/dashboard?token=<select>

Appointment system POST /webhooks/dashboard
  no Bearer; body: ph_user_id, ws_user_id, workspace_id, schedule
```

- CAEPY does **not** implement `GET /api/linq360/pending-counts`.
- No `user_id` in URL or body for glance GET/sync; doctor comes from the token.
- Sync stores Drupal content counts + ids; GET merges both tables.
- `payments` is always `{}` (not stored).
- Workspace row is unique on `(ws_user_id, ph_user_id, workspace_id)`.
- Glance `appointments` comes from `appointment_json` as `{ "todays_schedule": [ ... ] }`.

## Identity (pending glance)

From the workspace select JWT:

**`doctor_dashboard`:** `id` · `ph_user_id` · `ws_user_id` · `todays_glance` (content only)

**`workspace_doctor_dashboard`:** `appointment_id` · `ph_user_id` · `ws_user_id` · `workspace_id` · `appointments` · `requests` · `appointment_json`  
(`appointment_json` = `{ "todays_schedule": [ ... ] }`)

| Token claim | Column | Example |
|-------------|--------|---------|
| `workspace_id` | `workspace_doctor_dashboard.workspace_id` | `161` |
| `user_id` | `ws_user_id` (both tables) | `325` |
| `appointment_doctor_id` | `ph_user_id` (both tables) | `892` |

Content is looked up by `ph_user_id`. Workspace cards/schedule by `(ws_user_id, ph_user_id, workspace_id)`.

## Tables

### Glance (read path for badge counts)

| Table | What GET reads |
|-------|----------------|
| `linq360.doctor_dashboard.todays_glance` | `content` (pending reviews / blog / podcast) |
| `linq360.workspace_doctor_dashboard.requests` | `requests` |
| `linq360.workspace_doctor_dashboard.appointment_json` | `appointments` → `{ todays_schedule: [...] }` |

### Pending counter tables (webhook deltas; not the glance read)

| Table | Key | Role |
|-------|-----|------|
| `reviews_aggregator` | `user_id` | ±1 on review webhooks |
| `blog_comment_stats` | `(blog_id, doctor_id)` | ±1 on blog comment events |
| `podcast_comment_stats` | `(podcast_id, doctor_id)` | ±1 on podcast comment events |

These stay in sync on status changes. **Glance badge counts come from Practice Hub sync**, not from summing these on GET.

### Published aggregators

| Table | Key | Counted data |
|-------|-----|--------------|
| `blog_comments_aggregator` | `doctor_id` | approved `comment_count` |
| `podcast_comments_aggregator` | `doctor_id` | approved `comment_count` |
| `reviews_summary_aggregator` | `doctor_id` | published ratings |

## API paths

| Method | Path | Auth |
|--------|------|------|
| POST | `{ROOT_PATH}/v1/linq360/glance/sync` | `Authorization: Bearer <workspace_select_token>`. Pulls Drupal pending-counts, writes glance under `appointment_doctor_id`. |
| GET | `{ROOT_PATH}/v1/linq360/glance` | Same Bearer token. Reads stored glance (no query `linqmd_user_id`). |
| POST | `{ROOT_PATH}/v1/webhooks/drupal/reviews` | None. Status + aggregator deltas. |
| POST | `{ROOT_PATH}/v1/webhooks/drupal/comments` | None. Blog comment status + stats. |
| POST | `{ROOT_PATH}/v1/webhooks/drupal/podcast-comments` | None. Podcast status + stats. |

## Local test

1. Ensure `LINQMD_PRACTICE_HUB_API_URL` points at Drupal (e.g. `http://localhost/linqmd`).
2. Get a workspace select token (login → workspaces → select). Decode it: `appointment_doctor_id` is the Drupal uid (e.g. `892`).
3. Sync:
```http
POST /caepy/api/v1/linq360/glance/sync
Authorization: Bearer <workspace_select_access_token>
```
4. Get counts (same token, no query uid):
```http
GET /caepy/api/v1/linq360/glance
Authorization: Bearer <workspace_select_access_token>
```
