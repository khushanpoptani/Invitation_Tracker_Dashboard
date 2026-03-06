# FlexGCC Tracker Architecture

## Layered Design
- Presentation: Django templates (`templates/`) with Bootstrap 5.
- Application: Django views (`tracker/views.py`) and forms (`tracker/forms.py`).
- Domain/Data: Django models (`tracker/models.py`) and migrations (`tracker/migrations/0001_initial.py`).
- Persistence: SQLite (`db.sqlite3`).

## Core Entities
- `ConnectionStatus` (lookup table): Pending, Accepted, Rejected.
- `MessageType`: reusable message templates scoped per user.
- `FollowUpMessage`: reusable follow-up templates scoped per user (legacy/admin reference).
- `SentConnection`: sent connection records tied to user and status, including `follow_up_message_1/2/3`.

## Request Flows
1. Auth flow
   - `/login/` -> authenticate user -> redirect to `/`.
2. Dashboard flow
   - `/` -> select one user + optional message id -> compute Sent/Accepted/Pending counts (week/month/overall).
3. Sent Connections flow
   - `/sent-connections/` -> optional user filter -> tabular data.
4. Message Type CRUD flow
   - list/add/edit/delete via `/message-types/...`.
5. Follow Up update flow
   - `/follow-up-messages/` -> search by user + name -> update follow up message 1/2/3.
6. CSV import flow
   - `/upload-csv/` -> select user -> parse CSV -> create `SentConnection` rows with Pending status.
7. Status update flow
   - `/update-status/` -> search by user + name -> click Pending/Accepted/Rejected.
8. User management flow
   - `/users/` -> add/view/edit/deactivate (`is_active=False`).

## URLs
- App routes: `tracker/urls.py`
- Project routes: `flexgcc_tracker/urls.py`

## Notes
- Connection statuses are auto-seeded on migration through `post_migrate` signal in `tracker/apps.py`.
- User selection filters are available on data-heavy pages.
