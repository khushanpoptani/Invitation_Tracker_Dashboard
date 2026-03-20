import os
import sqlite3
import sys
from pathlib import Path


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "flexgcc_tracker.settings")

    import django

    django.setup()

    from django.conf import settings

    db_path = Path(settings.DATABASES["default"]["NAME"]).resolve()

    if not db_path.exists():
        print(f"Database file not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    sql = """
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

    COMMIT;
    """

    print(f"Using SQLite database: {db_path}")

    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(sql)

        cursor = connection.execute(
            """
            SELECT u.username, mt.message_id, mt.message
            FROM tracker_messagetype mt
            JOIN auth_user u ON u.id = mt.user_id
            WHERE lower(u.username) IN ('sunit', 'kandarp', 'farhana')
            ORDER BY u.username, mt.message_id
            """
        )
        rows = cursor.fetchall()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print("Message ID update completed.")
    print("")
    print("Updated message_type rows:")
    for username, message_id, message in rows:
        preview = " ".join((message or "").split())
        if len(preview) > 80:
            preview = preview[:77] + "..."
        print(f"- {username}: {message_id} -> {preview}")


if __name__ == "__main__":
    main()
