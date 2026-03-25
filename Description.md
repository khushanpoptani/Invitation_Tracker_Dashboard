# FlexGCC Tracker Description

## Overview

FlexGCC Tracker is a Django application for managing outreach activity from first send through accepted connection follow ups. It stores sent connection records, reusable message templates, follow up templates, user-level analytics, and operational status updates in a single SQLite-backed system.

The application is designed around a practical workflow:

1. import or review sent connections
2. assign or manage reusable message templates
3. update connection status
4. auto-generate follow ups when a connection is accepted
5. track which follow ups have been sent
6. monitor activity from the dashboard

## Stack

- Framework: Django 5
- Database: SQLite
- UI: Django templates with Bootstrap 5
- Authentication: Django built-in auth views

## Project Structure

### Main Files

- `manage.py`: Django management entry point
- `flexgcc_tracker/settings.py`: project settings
- `flexgcc_tracker/urls.py`: root URL configuration
- `tracker/models.py`: database models
- `tracker/views.py`: business logic and page flows
- `tracker/forms.py`: form definitions
- `tracker/urls.py`: app routes
- `templates/tracker/`: application templates

### Application Layers

- Presentation layer: templates in `templates/`
- Application layer: views and forms in `tracker/`
- Data layer: models and migrations in `tracker/models.py` and `tracker/migrations/`
- Persistence layer: `db.sqlite3`

## Authentication Flow

- `/login/`: user login page
- `/logout/`: user logout
- all tracker pages require login
- after login, the user lands on the dashboard

## Core Data Model

### ConnectionStatus

Lookup table for connection state values.

Seeded values:

- Pending
- Accepted
- Rejected

These statuses are ensured automatically after migrations by `tracker/apps.py`.

### MessageType

Reusable outbound message templates for a user.

Key rules:

- each record has `message_id`, `message`, and `user`
- `message_id` must be unique per user
- records are ordered by user and message ID
- when a sent-connections CSV uses a new `message_format`, the app auto-creates a new `MessageType`

### FollowUpMessage

Reusable follow up template set for a user and `message_id`.

Fields:

- `follow_up_message_1`
- `follow_up_message_2`
- `follow_up_message_3`

Key rules:

- one template set per `user + message_id`
- templates can be created, updated, deleted, or bulk uploaded
- updating a template automatically syncs accepted connections that use the same `user + message_id`

### SentConnection

The main operational record representing a sent outreach attempt.

Important fields:

- `name`
- `profile_link`
- `message`
- `message_id`
- `date`
- `status_date`
- `connection_status`
- `follow_up_message`
- `follow_up_message_1`
- `follow_up_message_2`
- `follow_up_message_3`
- `follow_up_sent_date_1`
- `follow_up_sent_date_2`
- `follow_up_sent_date_3`
- `user`

This model stores both the original outreach record and the generated follow up lifecycle.

## Message ID and Template Behavior

The application uses `message_id` as the shared key between:

- `MessageType`
- `FollowUpMessage`
- `SentConnection`

Current behavior:

- message templates are stored in `MessageType`
- follow up templates are stored in `FollowUpMessage`
- sent connection records store the resolved `message_id`
- when a message ID changes in Message Types, matching sent connections and follow up templates are synced to the new value

## Name Personalization Logic

When follow up messages are generated, the app replaces `$first_name` in template text with a derived first name from the connection’s full name.

Rules used by the app:

- prefixes like `Mr`, `Mrs`, `Ms`, `Dr`, `Prof`, `Sir`, and similar are ignored
- the first usable token longer than 3 characters is preferred
- if that is too short, the app checks later tokens
- if no good candidate exists, it falls back to `there`

## Main Application Pages

### 1. Dashboard

Route:

- `/`

Purpose:

- provide high-level analytics for a selected user
- optionally narrow analytics to a selected message ID
- optionally narrow analytics to a date range

Available metrics:

- Sent counts: week, month, total
- Accepted counts: week, month, total
- Pending counts: week, month, total
- Follow up activity counts: week, month, total

Important behavior:

- active users are shown in the user dropdown
- if no user is selected, the first active user is selected by default
- message ID options are built from the user’s sent connections and message templates
- accepted counts use `status_date` when available, otherwise fall back to the original sent `date`
- follow up activity counts are based on whether follow up sent dates exist

### 2. Sent Connections

Route:

- `/sent-connections/`

Purpose:

- browse the imported and manually processed connection records
- filter operational data
- export filtered results to CSV

Available filters:

- user
- message ID
- connection status
- follow up sent count
- free-text search
- from date
- to date

Search fields include:

- connection name
- profile link
- message
- message ID
- user username
- user first name
- user last name

CSV export includes:

- name
- profile link
- message
- message ID
- sent date
- status date
- status
- follow up sent count
- follow up messages 1 to 3
- follow up sent dates 1 to 3
- user

### 3. Message Types

Routes:

- `/message-types/`
- `/message-types/add/`
- `/message-types/<id>/edit/`
- `/message-types/<id>/delete/`
- `/message-types/next-id/`

Purpose:

- manage reusable outbound message templates per user

Behavior:

- list page supports user filtering
- create page auto-generates the next available message ID for the selected user
- edit page keeps the user fixed and allows message ID updates
- if a message ID changes, the app also updates matching `SentConnection` and `FollowUpMessage` records
- the app blocks updates that would create duplicate follow up template keys for the same user

### 4. Follow Up Templates

Route:

- `/follow-up-messages/`

Purpose:

- manage the follow up template set linked to each message ID

Supported actions:

- create a template set
- update a template set
- delete a template set
- bulk upload template sets by CSV
- filter by user and search text

Important behavior:

- the first active user is selected by default
- search matches `message_id` and follow up template text
- after create or update, accepted connections for the same user and message ID are re-synced
- existing follow up text on a connection is only overwritten if that follow up has not already been marked as sent

Bulk upload CSV format:

```csv
message_id,follow_up_message_1,follow_up_message_2,follow_up_message_3
```

### 5. Upload Sent Connections CSV

Route:

- `/upload-csv/`

Purpose:

- import newly sent outreach records for a selected user

Current required CSV headers:

```csv
name,profile_link,message,message_format,date
```

Import behavior:

- user is selected before upload
- rows are validated for required data and date format
- each new connection is created with status `Pending`
- `message_format` is used to find or create a `MessageType`
- the matching or newly created `message_id` is stored on the sent connection
- follow up fields are empty on import

Supported date parsing includes:

- `YYYY-MM-DD`
- `MM/DD/YYYY`
- `DD/MM/YYYY`
- `YYYY/MM/DD`
- `DD-MM-YYYY`
- `MM-DD-YYYY`

### 6. Update Connection Status

Route:

- `/update-status/`

Purpose:

- search for sent connections and update their status manually

Search inputs:

- user
- name

Status update behavior:

- status can be changed to Pending, Accepted, or Rejected
- `status_date` defaults to today if not provided
- when status becomes `Accepted`, the app looks up the follow up template by `user + message_id`
- if a template is found, follow up messages 1 to 3 are generated automatically
- if no template exists, the status still updates successfully

### 7. Bulk Update Connections

Route:

- `/bulk-update-connections/`

Purpose:

- bulk mark existing sent connections as accepted from a CSV upload

Current required CSV headers:

```csv
Name,Date Added
```

Also supported for reporting:

- `Account`
- `Geography`
- `Outreach activity`
- `Source File`

Behavior:

- user is selected before upload
- rows are matched against existing sent connections by user and case-insensitive name
- matched rows are updated to `Accepted`
- `status_date` is taken from `Date Added`
- if a matching follow up template exists, the app generates follow up messages on the connection
- unmatched rows are stored in session and can be downloaded as a missing-rows CSV

### 8. Follow Up Hub

Route:

- `/follow-ups/`

Purpose:

- manage follow up execution for accepted connections

Only connections with Accepted status appear here.

Available filters:

- user
- search
- follow up sent count
- from date
- to date

Behavior:

- results are limited to accepted connections
- accepted date uses `status_date`, falling back to original `date` if needed
- each follow up can be marked as sent individually
- marking a follow up as sent writes the matching `follow_up_sent_date_1`, `follow_up_sent_date_2`, or `follow_up_sent_date_3`
- filtered results can be downloaded as CSV

### 9. User Management

Routes:

- `/users/`
- `/users/add/`
- `/users/<id>/`
- `/users/<id>/edit/`
- `/users/<id>/inactive/`

Purpose:

- manage application users

Behavior:

- users can be created, viewed, and edited
- deactivation is soft delete using `is_active = False`
- inactive users remain in data history but are excluded from most active-user dropdowns

## End-to-End Operational Flow

This is the clearest way to understand how the app is meant to be used in practice.

### Flow A: Prepare Message Templates

1. Create message types for a user.
2. Each message type receives a user-scoped `message_id`.
3. Create follow up templates for the same message IDs if accepted follow ups are needed.

### Flow B: Import Sent Connections

1. Upload a sent-connections CSV for a user.
2. The app validates the file.
3. Each row becomes a `SentConnection` with Pending status.
4. If the uploaded `message_format` is new, the app creates a new `MessageType`.
5. The resolved `message_id` is stored on the connection.

### Flow C: Accept Connections

1. Update a connection manually from the status page, or use bulk update CSV.
2. When a connection becomes Accepted, the app looks for the matching follow up template.
3. If found, follow up messages 1 to 3 are rendered onto the connection record.
4. `$first_name` placeholders are personalized from the contact name.

### Flow D: Work Follow Ups

1. Open the Follow Up Hub.
2. Filter accepted connections by user, search, follow up count, or dates.
3. Use the generated follow up text.
4. Mark each follow up as sent when completed.
5. The app stores sent dates individually for follow ups 1 to 3.

### Flow E: Monitor Progress

1. Open the dashboard.
2. Filter by user, message ID, and optional date range.
3. Review sent, accepted, pending, and follow up metrics.

## Important Business Rules

- connection statuses are normalized in a separate table
- default statuses are seeded automatically after migrations
- `message_id` is unique per user in Message Types
- follow up templates are unique per user and message ID
- accepted connections are the source of truth for follow up operations
- follow up text is generated from the template and stored directly on the connection
- follow up text that already has a sent date is not overwritten during template sync
- changing a message ID in Message Types also updates linked sent connections and follow up templates
- user deactivation is soft and does not delete historical records

## Supporting CSV Downloads

The app provides sample or export CSV files for:

- sent connections import
- follow up template bulk upload
- bulk accepted-status update
- missing rows from bulk accepted-status update
- filtered sent connections export
- filtered follow up export

## Summary

FlexGCC Tracker is an outreach operations workflow tool. The core idea is simple:

- store sent connection activity
- organize message templates by message ID
- generate follow ups automatically when a connection is accepted
- track follow up completion over time
- give admins and users clear reporting views for daily operations
