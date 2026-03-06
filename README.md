# FlexGCC Tracker (Django + SQLite)

A Django-based tracker for sent connections, message templates, follow-up updates, and connection-status tracking with dashboard analytics.

## Stack
- Django 5
- HTML templates
- Bootstrap 5
- SQLite

## Implemented Flows
1. Login page (`/login/`) and redirect to dashboard.
2. Dashboard (`/`) with filters:
   - User dropdown
   - Message ID dropdown (for selected user)
   - Metrics for Sent/Accepted/Pending connections across week/month/overall
3. Sent Connections listing with user filter (`/sent-connections/`).
4. Message Types CRUD with user filter (`/message-types/`).
5. Follow Up Messages update page (`/follow-up-messages/`) to search by user + name and update `follow_up_message_1/2/3`.
6. CSV upload for Sent Connections with selected user (`/upload-csv/`) and sample CSV download (`/upload-csv/sample/`).
7. Connection status update by searching name and choosing Pending/Accepted/Rejected (`/update-status/`).
8. User management: add/edit/view and mark inactive (`/users/`).

## Data Model (Django)
- `ConnectionStatus`
  - `id`, `name`
  - Seeded values: Pending, Accepted, Rejected
- `MessageType`
  - `id`, `message_id`, `message`, `user_id`, timestamps
- `FollowUpMessage`
  - `id`, `follow_up_message_id`, `message`, `user_id`, timestamps
- `SentConnection`
  - `id`, `name`, `profile_link`, `message`, `message_id`, `date`, `connection_status_id`, `follow_up_message_id`, `follow_up_message_1`, `follow_up_message_2`, `follow_up_message_3`, `user_id`, timestamps

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install django
python3 manage.py migrate
python3 manage.py createsuperuser
python3 manage.py runserver
```

Open [http://127.0.0.1:8000/login/](http://127.0.0.1:8000/login/)

## CSV Format for Sent Connections
Required headers:
```csv
name,profile_link,message,message_id,date
```
Notes:
- `connection_status` is always set to `Pending` during CSV import.
- Optional columns supported: `follow_up_message_1`, `follow_up_message_2`, `follow_up_message_3`.
- Supported date examples: `YYYY-MM-DD`, `MM/DD/YYYY`, `DD/MM/YYYY`.
