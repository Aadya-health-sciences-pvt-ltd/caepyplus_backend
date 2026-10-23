# Content Aggregators (LinQ360)

Two separate concerns:

1. **Published metrics** — source aggregators + `linq360.content_source_aggregator`
   + `GET …/content-engagement` (approved / published item counts and ratings).
2. **Pending moderation inbox badge** — `todays_glance` JSON, filled by pulling
   Practice Hub pending counts (old pull-sync flow).

## Pending counts flow (counts only)

```text
Workspace login → workspaces → workspace select
        ↓  Bearer workspace_select_access_token
        ↓  (appointment_doctor_id = Drupal uid, e.g. 892)
CAEPY POST /v1/linq360/glance/sync
  Authorization: Bearer <workspace_select_token>
        ↓
Drupal GET /api/linq360/pending-counts   (no user_id; doctor from token)
        ↓
write pending counts + id arrays into todays_glance for uid 892
        ↓
CAEPY GET /v1/linq360/glance
  Authorization: Bearer <same workspace_select_token>
```

- CAEPY does **not** implement `GET /api/linq360/pending-counts`.
- No `user_id` in URL or body for glance GET/sync; doctor comes from the token.
- Sync stores Drupal counts and id arrays; GET returns that stored JSON.
- `payments` / `requests` / `appointments` stay empty objects on glance.

## Identity (pending glance)

From the workspace select JWT:

Dashboard columns (order):

`appointment_id` · `appointment_json` · `workspace_id` · `ws_user_id` · `ph_user_id` · `todays_glance`

| Token claim | Dashboard column | Example |
|-------------|------------------|---------|
| `workspace_id` | `workspace_id` | `161` |
| `user_id` | `ws_user_id` | `325` |
| `appointment_doctor_id` | `ph_user_id` (Practice Hub / Drupal uid) | `892` |

Glance is looked up by `ph_user_id`.

## Tables

### Glance (read path for badge counts)

`linq360.workspace_doctor_dashboard.todays_glance` — written by sync from Drupal.

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
