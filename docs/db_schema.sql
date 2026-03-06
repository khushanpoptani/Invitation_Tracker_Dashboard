-- FlexGCC Tracker schema (SQLite-oriented)

CREATE TABLE connection_status (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE message_type (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id VARCHAR(100) NOT NULL,
  message TEXT NOT NULL,
  user_id INTEGER NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE (message_id, user_id),
  FOREIGN KEY (user_id) REFERENCES auth_user(id) ON DELETE CASCADE
);

CREATE TABLE follow_up_message (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  follow_up_message_id VARCHAR(100) NOT NULL,
  message TEXT NOT NULL,
  user_id INTEGER NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE (follow_up_message_id, user_id),
  FOREIGN KEY (user_id) REFERENCES auth_user(id) ON DELETE CASCADE
);

CREATE TABLE sent_connection (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(255) NOT NULL,
  profile_link VARCHAR(200) NOT NULL DEFAULT '',
  message TEXT NOT NULL DEFAULT '',
  message_id VARCHAR(100) NOT NULL DEFAULT '',
  date DATE NOT NULL,
  connection_status_id INTEGER NOT NULL,
  follow_up_message_id INTEGER NULL,
  follow_up_message_1 TEXT NOT NULL DEFAULT '',
  follow_up_message_2 TEXT NOT NULL DEFAULT '',
  follow_up_message_3 TEXT NOT NULL DEFAULT '',
  user_id INTEGER NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY (connection_status_id) REFERENCES connection_status(id) ON DELETE RESTRICT,
  FOREIGN KEY (follow_up_message_id) REFERENCES follow_up_message(id) ON DELETE SET NULL,
  FOREIGN KEY (user_id) REFERENCES auth_user(id) ON DELETE CASCADE
);
