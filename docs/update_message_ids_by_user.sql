-- Remap message IDs by username in SQLite.
--
-- Target format:
--   sunit   -> S1, S2, S3, ...
--   kandarp -> K1, K2, K3, ...
--   farhana -> F1, F2, F3, ...
--
-- Run with:
--   python manage.py dbshell < docs/update_message_ids_by_user.sql
--
-- Notes:
-- - This updates tracker_messagetype, tracker_followupmessage, and tracker_sentconnection.
-- - message_id is not a foreign key in the schema, so this script keeps the logical references aligned.
-- - Ordering is based on the current numeric suffix when present, otherwise by current message_id and row id.

BEGIN TRANSACTION;

DROP TABLE IF EXISTS temp_message_id_map;

CREATE TEMP TABLE temp_message_id_map (
    user_id INTEGER NOT NULL,
    old_message_id TEXT NOT NULL,
    temp_message_id TEXT NOT NULL,
    new_message_id TEXT NOT NULL,
    PRIMARY KEY (user_id, old_message_id)
);

INSERT INTO temp_message_id_map (user_id, old_message_id, temp_message_id, new_message_id)
WITH ranked_message_types AS (
    SELECT
        mt.user_id,
        mt.message_id AS old_message_id,
        CASE
            WHEN lower(u.username) = 'sunit' THEN 'S'
            WHEN lower(u.username) = 'kandarp' THEN 'K'
            WHEN lower(u.username) = 'farhana' THEN 'F'
        END AS prefix,
        ROW_NUMBER() OVER (
            PARTITION BY mt.user_id
            ORDER BY
                CASE
                    WHEN trim(mt.message_id) GLOB '*[0-9]'
                    THEN CAST(substr(trim(mt.message_id), length(rtrim(trim(mt.message_id), '0123456789')) + 1) AS INTEGER)
                    ELSE 999999999
                END,
                trim(mt.message_id),
                mt.id
        ) AS seq
    FROM tracker_messagetype mt
    INNER JOIN auth_user u
        ON u.id = mt.user_id
    WHERE lower(u.username) IN ('sunit', 'kandarp', 'farhana')
)
SELECT
    user_id,
    old_message_id,
    '__TMP__' || prefix || seq AS temp_message_id,
    prefix || seq AS new_message_id
FROM ranked_message_types;

-- Preview mapping before applying if needed:
-- SELECT u.username, m.old_message_id, m.new_message_id
-- FROM temp_message_id_map m
-- JOIN auth_user u ON u.id = m.user_id
-- ORDER BY u.username, m.new_message_id;

-- Step 1: move target rows to temporary IDs to avoid unique collisions.
UPDATE tracker_messagetype
SET message_id = (
    SELECT m.temp_message_id
    FROM temp_message_id_map m
    WHERE m.user_id = tracker_messagetype.user_id
      AND m.old_message_id = tracker_messagetype.message_id
)
WHERE EXISTS (
    SELECT 1
    FROM temp_message_id_map m
    WHERE m.user_id = tracker_messagetype.user_id
      AND m.old_message_id = tracker_messagetype.message_id
);

UPDATE tracker_followupmessage
SET message_id = (
    SELECT m.temp_message_id
    FROM temp_message_id_map m
    WHERE m.user_id = tracker_followupmessage.user_id
      AND m.old_message_id = tracker_followupmessage.message_id
)
WHERE EXISTS (
    SELECT 1
    FROM temp_message_id_map m
    WHERE m.user_id = tracker_followupmessage.user_id
      AND m.old_message_id = tracker_followupmessage.message_id
);

UPDATE tracker_sentconnection
SET message_id = (
    SELECT m.temp_message_id
    FROM temp_message_id_map m
    WHERE m.user_id = tracker_sentconnection.user_id
      AND m.old_message_id = tracker_sentconnection.message_id
)
WHERE EXISTS (
    SELECT 1
    FROM temp_message_id_map m
    WHERE m.user_id = tracker_sentconnection.user_id
      AND m.old_message_id = tracker_sentconnection.message_id
);

-- Step 2: replace temporary IDs with final IDs.
UPDATE tracker_messagetype
SET message_id = (
    SELECT m.new_message_id
    FROM temp_message_id_map m
    WHERE m.user_id = tracker_messagetype.user_id
      AND m.temp_message_id = tracker_messagetype.message_id
)
WHERE EXISTS (
    SELECT 1
    FROM temp_message_id_map m
    WHERE m.user_id = tracker_messagetype.user_id
      AND m.temp_message_id = tracker_messagetype.message_id
);

UPDATE tracker_followupmessage
SET message_id = (
    SELECT m.new_message_id
    FROM temp_message_id_map m
    WHERE m.user_id = tracker_followupmessage.user_id
      AND m.temp_message_id = tracker_followupmessage.message_id
)
WHERE EXISTS (
    SELECT 1
    FROM temp_message_id_map m
    WHERE m.user_id = tracker_followupmessage.user_id
      AND m.temp_message_id = tracker_followupmessage.message_id
);

UPDATE tracker_sentconnection
SET message_id = (
    SELECT m.new_message_id
    FROM temp_message_id_map m
    WHERE m.user_id = tracker_sentconnection.user_id
      AND m.temp_message_id = tracker_sentconnection.message_id
)
WHERE EXISTS (
    SELECT 1
    FROM temp_message_id_map m
    WHERE m.user_id = tracker_sentconnection.user_id
      AND m.temp_message_id = tracker_sentconnection.message_id
);

-- Final verification:
SELECT u.username, mt.message_id, mt.message
FROM tracker_messagetype mt
JOIN auth_user u ON u.id = mt.user_id
WHERE lower(u.username) IN ('sunit', 'kandarp', 'farhana')
ORDER BY u.username, mt.message_id;

COMMIT;
