# Content Aggregators (LinQ360)

Two separate concerns:

1. **Published metrics** — source aggregators + `linq360.content_source_aggregator`
   + `GET …/content-engagement` (approved / published item counts and ratings).
2. **Pending moderation inbox** — `linq360.workspace_doctor_dashboard.todays_glance`
   JSON. Drupal owns the live queue. LinQ360 reads that JSON only.

## Identity (pending glance)

Drupal uid (`reviews.user_id`) is the only key. Example `884` often has **no**
`doctors` row and **no** `doctor_linqmd_credentials`. Do **not** look those up
for glance.

| Key | Role |
|-----|------|
| `linqmd_user_id` | Drupal uid. Matches `workspace_doctor_dashboard.user_id`. |
| `doctors.id` | **Not** used for glance. Optional only for published metrics. |
| Workspace user id | **Not** this key. |

`GET /v1/linq360/glance` reads `todays_glance` on
`linq360.workspace_doctor_dashboard` where `user_id` is that Drupal uid.
It does not open Drupal MySQL and does not count the CAEPY `reviews` table.

Sync writes the three pending counts into `todays_glance.content` on every
matching dashboard row. If none exists, sync inserts one row with that
`user_id` so the JSON is stored.

## Tables

### Public source aggregators

| Table | Key | Counted data |
|-------|-----|--------------|
| `blog_comments_aggregator` | `doctor_id` PK | `comment_count` (approved only) |
| `podcast_comments_aggregator` | `doctor_id` PK | `comment_count` (approved only) |
| `reviews_summary_aggregator` | `doctor_id` PK | published `review_count`, `rating_sum`, `avg_rating` (CAEPY doctor required) |
| `reviews_pending_aggregator` | `linqmd_user_id` PK | webhook delta counter (not the LinQ360 read) |

### Main aggregator (published)

`linq360.content_source_aggregator` — one row per `(doctor_id, source)` where
`source ∈ {review, blog, podcast}`. Unique on `(doctor_id, source)`.

### Dashboard glance (pending inbox only)

`linq360.workspace_doctor_dashboard.todays_glance` JSONB (default `{}`).

**Do not** put approved `item_count` / `avg_rating` / `total_item_count` into
`todays_glance`.

```json
{
  "content": {
    "reviews": { "pending_count": 5 },
    "blog_comments": { "pending_count": 0 },
    "podcast_comments": { "pending_count": 0 }
  },
  "appointments": {},
  "requests": {},
  "messages": {},
  "payments": {}
}
```

- Pending is the **full** queue (not today-only). Reject / unpublished is not pending.
- Appointments / requests = present-day only later (leave alone).
- Blog and podcast stay `0` until Practice Hub returns a non-zero count.

## Delta rules

### Published aggregators (only when a CAEPY `doctors` row exists)

| Event | Delta |
|-------|-------|
| Approve & Publish | +1 (+ rating_sum); rating required |
| Unpublish / delete of a published review | −1; rating required |
| Floor | never below 0 |

### Webhook counter (`reviews_pending_aggregator`)

The reviews webhook still adjusts this counter. LinQ360 glance does **not** read it
and does not need one webhook body per review.

| Event | `pending_count` |
|-------|-----------------|
| Submit | +1 |
| Approve & Publish | −1 (published +1 only if CAEPY doctor exists) |
| Reject / hidden while pending | −1 |
| Delete while pending | −1 |
| Floor | never below 0 |

## Service

`ContentAggregatorService`:

- `adjust_blog_comments` / `adjust_podcast_comments` / `adjust_reviews` — published only (**no** glance)
- `adjust_pending_reviews(linqmd_user_id, delta, doctor_id=None)` — webhook counter only (no glance)
- `upsert_pending_glance` / `sync_pending_glance` — write Practice Hub counts into `todays_glance`
- `get_glance(linqmd_user_id)` — read `todays_glance`; all three counts `0` when no dashboard row
- `get_engagement(doctor_id)` — published metrics only

## API paths

App `ROOT_PATH` is typically `/caepy/api` locally.

| Method | Path | Auth |
|--------|------|------|
| GET | `{ROOT_PATH}/v1/linq360/glance?linqmd_user_id={uid}` | **None.** Reads `todays_glance`. Missing dashboard row → all counts `0`. |
| POST | `{ROOT_PATH}/v1/linq360/glance/sync` | **None.** Body `{ "linqmd_user_id": "884" }`. GETs Practice Hub and writes `todays_glance`. Creates the dashboard row when none exists for that `user_id`. |
| GET | `{ROOT_PATH}/v1/linq360/doctors/{doctor_id}/content-engagement` | JWT (`require_authentication`) |
| POST | `{ROOT_PATH}/v1/webhooks/drupal/reviews` | None. Updates the webhook counter only. **Glance does not read that counter.** |

`POST http://127.0.0.1:8000/caepy/api/v1/linq360/glance/sync`

```json
{ "linqmd_user_id": "884" }
```

That calls Practice Hub (not built in this repo yet):

`GET {LINQMD_PRACTICE_HUB_API_URL}/api/linq360/pending-counts/884`

using the existing Practice Hub Basic token and cookie. No Drupal user JWT.
No `DRUPAL_DATABASE_URL`. If Practice Hub fails, the sync returns **502** and
does not change `todays_glance`. The counts are stored only in
`linq360.workspace_doctor_dashboard.todays_glance`.

`GET http://127.0.0.1:8000/caepy/api/v1/linq360/glance?linqmd_user_id=884`

```json
{
  "linqmd_user_id": "884",
  "content": {
    "reviews": { "pending_count": 2 },
    "blog_comments": { "pending_count": 0 },
    "podcast_comments": { "pending_count": 0 }
  }
}
```

Appointments and requests are not in this response.


`POST http://127.0.0.1:8000/caepy/api/v1/webhooks/drupal/reviews`

(`POST /v1/webhooks/...` without `ROOT_PATH` returns **404**.)

## Drupal webhook: reviews

`linqmd_user_id` is required. `doctor_id` is optional.

```json
{
  "action": "submit",
  "linqmd_user_id": "884",
  "review_id": "1079"
}
```

| Action | Pending | Published |
|--------|---------|-----------|
| `submit` | +1 | — |
| `approve` / `publish` | −1 | +1 only if `doctor_id` exists in `doctors` and `rating` is sent |
| `reject` / `deny` / `delete_pending` | −1 | — |
| `unpublish` / `delete` | — | −1 only if that CAEPY doctor exists and `rating` is sent |

### Postman — submit with only `linqmd_user_id`

```http
POST http://127.0.0.1:8000/caepy/api/v1/webhooks/drupal/reviews
Content-Type: application/json

{
  "action": "submit",
  "linqmd_user_id": "884",
  "review_id": "1079"
}
```

No `doctor_id` and no `doctor_linqmd_credentials` row is required.

### Postman — approve when a CAEPY doctor exists

```json
{
  "action": "approve",
  "rating": 5,
  "doctor_id": 12,
  "linqmd_user_id": "884",
  "review_id": "1079"
}
```

## Local test

```bash
python -m alembic upgrade head
```

Optional glance target (`user_id` = Drupal uid, not `doctors.id`):

```sql
INSERT INTO linq360.workspace_doctor_dashboard (workspace_id, user_id, appointments_json, todays_glance)
SELECT 1, 884, '{}'::jsonb, '{}'::jsonb
WHERE NOT EXISTS (
  SELECT 1 FROM linq360.workspace_doctor_dashboard WHERE user_id = 884
);
```

```bash
curl -s -X POST "http://127.0.0.1:8000/caepy/api/v1/webhooks/drupal/reviews" \
  -H "Content-Type: application/json" \
  -d '{"action":"submit","linqmd_user_id":"884","review_id":"1079"}'
```

```sql
SELECT linqmd_user_id, pending_count, doctor_id
FROM reviews_pending_aggregator
WHERE linqmd_user_id = '884';

SELECT user_id, todays_glance->'content' AS content
FROM linq360.workspace_doctor_dashboard
WHERE user_id = 884;
```

`pending_count` is saved even when the dashboard insert was skipped.
Glance `content.reviews` has `pending_count` only (no `item_count` / `avg_rating`).

## Migrations

| Revision | Change |
|----------|--------|
| `013` | Source aggregators + `linq360.content_source_aggregator` |
| `014` | `todays_glance` on `workspace_doctor_dashboard` |
| `015` | `reviews_summary_aggregator.pending_count` (published table; not the inbox key) |
| `016` | `reviews_pending_aggregator` keyed by `linqmd_user_id` |
| `017` | `content_pending_glance` (removed in `018`) |
| `018` | Drop `content_pending_glance`; glance stays on `todays_glance` |

```bash
python -m alembic upgrade head
```
