# FlexGCC Tracker Description

## Overview

FlexGCC Tracker is a Django and SQLite based internal tracking system for managing:

- sent connection requests
- reusable message types
- follow up templates
- accepted connection follow up workflows
- user level analytics and administration

The application is built with Django views, HTML templates, and Bootstrap for the UI. It supports login, dashboard analytics, CSV uploads, status updates, follow up generation, and user management.

This document combines:

- the original tracker requirements
- the later functional updates
- the current implemented architecture
- the updated database schema required by the tracker

## Technology Stack

- Framework: Django
- UI: HTML Templates
- Styling: Bootstrap
- Database: SQLite

## Core Modules

### 1. Authentication

- Login page for authenticated access
- Successful login redirects users to the dashboard
- Logged in user details are shown in the application layout

### 2. Dashboard

Dashboard provides analytics for a selected user and optionally for a selected message ID.

Current analytics include:

- Sent connections this week, this month, and overall
- Accepted connections this week, this month, and overall
- Pending connections this week, this month, and overall
- Follow up activity counts
- Date range filtering

Business behavior:

- User dropdown is available on dashboard
- Message ID dropdown is available for the selected user
- Counts update based on selected user, selected message ID, and optional date filters

### 3. Sent Connections

This page displays connection records in tabular format.

Supported filters:

- user
- search bar
- message ID
- status
- follow up sent count
- date range

Supported actions:

- view connection records
- searchable message ID dropdown with message preview
- download filtered CSV
- navigate to CSV upload page

Tracked fields include:

- name
- profile link
- sent message
- message ID
- sent date
- status
- status date
- follow up messages 1, 2, and 3
- follow up sent dates
- user

### 4. Message Types

This module manages reusable outbound message templates per user.

Supported actions:

- add
- edit
- delete
- filter by user
- view full message in popup modal

Rules:

- `message_id` must be unique per user
- when new message types are auto-created during CSV upload, the next available message ID is assigned

### 5. Follow Up Templates

This is the newer follow up template management page for a specific `message_id`.

Supported actions:

- create follow up templates
- update follow up templates
- view templates
- delete templates
- bulk upload templates by CSV
- auto filtering by selected user and search text

Template structure:

- one record per `user + message_id`
- each template record stores:
  - `follow_up_message_1`
  - `follow_up_message_2`
  - `follow_up_message_3`

Template variable support:

- `$first_name` placeholder is supported
- when generating follow ups for a connection:
  - name prefixes like `Mr`, `Mrs`, `Dr`, `Prof` are ignored
  - first usable token longer than 3 characters is preferred
  - if first name is too short, a later or last token longer than 3 characters is used
  - fallback word is `there`

### 6. Upload Sent Connections CSV

This page imports sent connection records for a selected user.

Current implementation behavior:

- user is selected before upload
- imported rows are created in `SentConnection`
- connection status defaults to `Pending`
- follow up template foreign key is initially null
- message type may be auto-created if the uploaded message format does not already exist for the user

Current implemented sample format:

```csv
name,profile_link,message,message_format,date
```

Originally requested later format:

```csv
name,profile_link,message,message_id,date
```

Requested business rule:

- default `connection_status` should be Pending
- `follow_up_message_id` should be null by default
- follow up content should be handled as `follow_up_message_1`, `follow_up_message_2`, `follow_up_message_3`

### 7. Update Connection Status

This page updates connection status by searching records by user and name.

Supported actions:

- search sent connections by user and name
- update status using Pending, Accepted, Rejected buttons/options
- set status date

Rules:

- status date defaults to current date if not provided
- date can be modified before saving
- when status changes to `Accepted`:
  - matching follow up template is searched by `user + message_id`
  - follow up messages 1, 2, and 3 are generated automatically into the connection record
  - existing sent follow up dates are preserved

### 8. Bulk Update Connections

This page supports bulk updating accepted connections from a CSV file.

Current behavior:

- upload CSV for a selected user
- match records by name
- parse accepted date from file
- update matching connections to `Accepted`
- apply follow up templates automatically where available
- keep a downloadable list of missing rows not found in tracker

### 9. Follow Ups Page

This is the operational follow up page for accepted connections.

Purpose:

- show latest accepted connections
- display prefilled follow up messages 1, 2, and 3
- support copy action
- support sent action to record follow up sent dates

Supported filters:

- user
- follow up sent count: none, 1, 2, 3
- date range
- search bar
- download filtered data

Rules:

- only accepted connections appear here
- follow up sent button updates `follow_up_sent_date_1`, `follow_up_sent_date_2`, or `follow_up_sent_date_3`

### 10. User Management

This page manages application users.

Supported actions:

- add
- edit
- view
- deactivate instead of hard delete

User behavior:

- inactive users are excluded from most operational dropdown filters

## Functional Flows

### Flow 1. Login

1. User opens login page.
2. User authenticates.
3. System redirects to dashboard.

### Flow 2. Dashboard Analysis

1. User opens dashboard.
2. User selects a user.
3. User optionally selects a message ID.
4. System calculates sent, accepted, pending, and follow up metrics.
5. User can further narrow results by date range.

### Flow 3. Sent Connections Review

1. User opens Sent Connections page.
2. User filters by user, search text, message ID, status, follow up count, or dates.
3. System shows matching records.
4. User can export filtered data.

### Flow 4. Message Type Management

1. User opens Message Types page.
2. User filters by user.
3. User adds, edits, deletes, or views a message type.

### Flow 5. Follow Up Template Management

1. User opens Follow Up Templates page.
2. User selects a user.
3. Filters work automatically without a search button.
4. User manages follow up templates for a specific message ID.
5. User can bulk upload template records.
6. Updated templates are synced to accepted connections for the same user and message ID.

### Flow 6. CSV Upload

1. User opens Upload Sent Connections CSV page.
2. User selects a user.
3. User downloads sample CSV if needed.
4. User uploads CSV file.
5. System validates columns and dates.
6. System creates sent connection records with Pending status.

### Flow 7. Status Update

1. User opens Update Connection Status page.
2. User selects a user and searches by name.
3. Matching sent connections are displayed.
4. User updates status and status date.
5. If status becomes Accepted, follow up messages are generated automatically.

### Flow 8. Follow Up Operations

1. User opens Follow Ups page.
2. User filters accepted connections.
3. User copies follow up message 1, 2, or 3.
4. User marks the corresponding follow up as sent.
5. System stores the sent date.

### Flow 9. User Administration

1. Admin opens Users page.
2. Admin adds, edits, or views users.
3. Admin can mark users inactive instead of deleting them.

## Architecture

## Application Layers

### Presentation Layer

- Django templates in `templates/`
- Bootstrap based UI
- login, dashboard, tables, forms, popups, and operational pages

### Application Layer

- Django views in `tracker/views.py`
- Form classes in `tracker/forms.py`
- request handling, filtering, CSV processing, and follow up generation logic

### Domain Layer

- Django models in `tracker/models.py`
- business rules for statuses, message types, follow up templates, and sent connections

### Persistence Layer

- SQLite database
- migrations in `tracker/migrations/`

## Main Entities

### ConnectionStatus

Lookup table for connection state values:

- Pending
- Accepted
- Rejected

### MessageType

Stores reusable outbound message templates for a user.

### FollowUpMessage

Stores up to three follow up templates for a `message_id` and user.

### SentConnection

Stores actual sent connection records and their lifecycle data.

## Database Schema

The current database design should use the following core tables.

### 1. `connection_status`

Purpose:

- lookup table for connection statuses

Fields:

- `id` INTEGER PRIMARY KEY
- `name` VARCHAR(50) UNIQUE NOT NULL

Seed values:

- Pending
- Accepted
- Rejected

### 2. `message_type`

Purpose:

- stores reusable outbound message templates per user

Fields:

- `id` INTEGER PRIMARY KEY
- `message_id` VARCHAR(100) NOT NULL
- `message` TEXT NOT NULL
- `user_id` INTEGER NOT NULL
- `created_at` DATETIME NOT NULL
- `updated_at` DATETIME NOT NULL

Constraints:

- unique (`message_id`, `user_id`)

Foreign keys:

- `user_id` -> Django auth user

### 3. `follow_up_message`

Purpose:

- stores follow up template sets for a specific message ID and user

Fields:

- `id` INTEGER PRIMARY KEY
- `message_id` VARCHAR(100) NOT NULL
- `follow_up_message_1` TEXT NOT NULL DEFAULT ''
- `follow_up_message_2` TEXT NOT NULL DEFAULT ''
- `follow_up_message_3` TEXT NOT NULL DEFAULT ''
- `user_id` INTEGER NOT NULL
- `created_at` DATETIME NOT NULL
- `updated_at` DATETIME NOT NULL

Constraints:

- unique (`message_id`, `user_id`)

Foreign keys:

- `user_id` -> Django auth user

### 4. `sent_connection`

Purpose:

- stores all sent connection records and operational follow up data

Fields:

- `id` INTEGER PRIMARY KEY
- `name` VARCHAR(255) NOT NULL
- `profile_link` VARCHAR(200) NOT NULL DEFAULT ''
- `message` TEXT NOT NULL DEFAULT ''
- `message_id` VARCHAR(100) NOT NULL DEFAULT ''
- `date` DATE NOT NULL
- `status_date` DATE NULL
- `connection_status_id` INTEGER NOT NULL
- `follow_up_message_id` INTEGER NULL
- `follow_up_message_1` TEXT NOT NULL DEFAULT ''
- `follow_up_message_2` TEXT NOT NULL DEFAULT ''
- `follow_up_message_3` TEXT NOT NULL DEFAULT ''
- `follow_up_sent_date_1` DATE NULL
- `follow_up_sent_date_2` DATE NULL
- `follow_up_sent_date_3` DATE NULL
- `user_id` INTEGER NOT NULL
- `created_at` DATETIME NOT NULL
- `updated_at` DATETIME NOT NULL

Foreign keys:

- `connection_status_id` -> `connection_status.id`
- `follow_up_message_id` -> `follow_up_message.id`
- `user_id` -> Django auth user

## Relationship Summary

- one user can have many message types
- one user can have many follow up template sets
- one user can have many sent connections
- one connection status can be used by many sent connections
- one follow up template can be referenced by many sent connections
- one `message_type` record and one `follow_up_message` record can share the same `message_id` for the same user

## Important Business Rules

- connection status is normalized in a separate lookup table
- `message_id` is unique per user in `message_type`
- follow up template set is unique per user and `message_id`
- when a connection becomes Accepted, follow up messages are generated automatically from the matching follow up template
- generated follow up text replaces `$first_name` dynamically from the connection name
- follow up sent dates are stored separately for follow ups 1, 2, and 3
- user deactivation is soft behavior through `is_active = false`

## Notes on Requirement Evolution

The tracker requirements evolved during implementation. The most important changes are:

- follow up handling moved from a single follow up message reference to three follow up messages per connection
- status updates now store a dedicated `status_date`
- accepted connections drive the follow up operational workflow
- a separate Follow Ups page was introduced for copy and sent actions
- Message Types now support popup viewing
- Sent Connections now include search and downloadable filtered export

There is one notable mismatch between the latest requested upload format and the currently implemented upload behavior:

- latest request mentions upload columns using `message_id`
- current implementation still expects `message_format` and auto-creates `message_id`

If needed, this document can also be used as the baseline for aligning code, schema, and UI with the final approved business requirements.
