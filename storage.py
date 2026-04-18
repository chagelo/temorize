#!/usr/bin/env python3

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DB_PATH = Path.home() / ".temorize" / "temorize.db"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def connect(db_path):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    return conn


def init_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            parent_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(slug, parent_id)
        );

        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_path TEXT NOT NULL,
            topic TEXT NOT NULL,
            topic_display_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_ingested_at TEXT NOT NULL,
            UNIQUE(source_type, source_path)
        );

        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            provider_item_id TEXT NOT NULL DEFAULT '',
            primary_topic_id INTEGER REFERENCES topics(id),
            secondary_topic_id INTEGER REFERENCES topics(id),
            topic TEXT NOT NULL,
            topic_display_name TEXT NOT NULL,
            item_type TEXT NOT NULL,
            content TEXT NOT NULL,
            answer TEXT NOT NULL DEFAULT '',
            source_ref TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            priority REAL NOT NULL DEFAULT 1.0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_seen_at TEXT,
            last_ingested_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_items_active
        ON items(status, topic, item_type, priority);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_items_source_provider
        ON items(source_id, provider_item_id);

        CREATE TABLE IF NOT EXISTS feedback_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    ensure_column(conn, "items", "provider_item_id", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "items", "primary_topic_id", "INTEGER REFERENCES topics(id)")
    ensure_column(conn, "items", "secondary_topic_id", "INTEGER REFERENCES topics(id)")
    ensure_column(conn, "items", "last_ingested_at", "TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_type_path ON sources(source_type, source_path)")
    conn.execute("UPDATE items SET provider_item_id = id WHERE provider_item_id = ''")
    conn.execute(
        """
        UPDATE items
        SET last_ingested_at = COALESCE(last_ingested_at, updated_at, created_at)
        WHERE last_ingested_at IS NULL
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_items_source_provider
        ON items(source_id, provider_item_id)
        """
    )
    conn.commit()


def ensure_column(conn, table_name, column_name, column_def):
    existing_columns = {
        row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in existing_columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")


def build_storage_item_id(source_id, provider_item_id):
    return f"src{source_id}:{provider_item_id}"


def slugify_topic(name):
    text = (name or "").strip().lower()
    cleaned = []
    last_dash = False
    for char in text:
        if char.isalnum():
            cleaned.append(char)
            last_dash = False
        else:
            if not last_dash:
                cleaned.append("-")
                last_dash = True
    slug = "".join(cleaned).strip("-")
    return slug or "topic"


def upsert_topic(conn, name, parent_id=None, status="active"):
    topic_name = (name or "").strip()
    if not topic_name:
        raise RuntimeError("Topic name cannot be empty.")

    now = utc_now()
    slug = slugify_topic(topic_name)
    existing = conn.execute(
        "SELECT id, name, slug, parent_id FROM topics WHERE slug = ? AND parent_id IS ?",
        (slug, parent_id),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE topics SET name = ?, status = ?, updated_at = ? WHERE id = ?",
            (topic_name, status, now, existing["id"]),
        )
        conn.commit()
        return existing["id"]

    cursor = conn.execute(
        """
        INSERT INTO topics (name, slug, parent_id, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (topic_name, slug, parent_id, status, now, now),
    )
    conn.commit()
    return cursor.lastrowid


def find_topic_by_slug(conn, slug, parent_id=None, statuses=("active", "candidate")):
    placeholders = ",".join("?" for _ in statuses)
    row = conn.execute(
        f"""
        SELECT id, name, slug, parent_id, status
        FROM topics
        WHERE slug = ? AND parent_id IS ? AND status IN ({placeholders})
        ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, id
        LIMIT 1
        """,
        (slug, parent_id, *statuses),
    ).fetchone()
    return dict(row) if row else None


def list_topics(conn, statuses=("active",)):
    placeholders = ",".join("?" for _ in statuses)
    rows = conn.execute(
        f"""
        SELECT
            child.id,
            child.name,
            child.slug,
            child.parent_id,
            parent.name AS parent_name,
            parent.slug AS parent_slug,
            child.status
        FROM topics AS child
        LEFT JOIN topics AS parent ON child.parent_id = parent.id
        WHERE child.status IN ({placeholders})
        ORDER BY COALESCE(parent.name, child.name), child.name
        """,
        statuses,
    ).fetchall()
    return [dict(row) for row in rows]


def build_topic_labels(conn, primary_topic_id=None, secondary_topic_id=None):
    if primary_topic_id is None:
        return "unassigned", "Unassigned"

    primary = conn.execute(
        "SELECT id, name, slug FROM topics WHERE id = ?",
        (primary_topic_id,),
    ).fetchone()
    if primary is None:
        return "unassigned", "Unassigned"

    if secondary_topic_id is None:
        return primary["slug"], primary["name"]

    secondary = conn.execute(
        "SELECT id, name, slug FROM topics WHERE id = ?",
        (secondary_topic_id,),
    ).fetchone()
    if secondary is None:
        return primary["slug"], primary["name"]

    return f"{primary['slug']}/{secondary['slug']}", f"{primary['name']} / {secondary['name']}"


def upsert_source(conn, source_type, source_path, topic="", topic_display_name=""):
    now = utc_now()
    existing = conn.execute(
        """
        SELECT id FROM sources
        WHERE source_type = ? AND source_path = ?
        ORDER BY id
        LIMIT 1
        """,
        (source_type, source_path),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE sources
            SET topic = COALESCE(NULLIF(topic, ''), ?),
                topic_display_name = COALESCE(NULLIF(topic_display_name, ''), ?),
                last_ingested_at = ?
            WHERE id = ?
            """,
            (topic, topic_display_name, now, existing["id"]),
        )
        conn.commit()
        return existing["id"]

    cursor = conn.execute(
        """
        INSERT INTO sources (
            source_type, source_path, topic, topic_display_name, created_at, last_ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (source_type, source_path, topic, topic_display_name, now, now),
    )
    conn.commit()
    return cursor.lastrowid


def upsert_items(conn, source_id, items, item_topic_assignments=None):
    now = utc_now()
    item_topic_assignments = item_topic_assignments or {}
    for item in items:
        provider_item_id = item["id"]
        storage_item_id = build_storage_item_id(source_id, provider_item_id)
        topic_assignment = item_topic_assignments.get(provider_item_id, {})
        primary_topic_id = topic_assignment.get("primary_topic_id")
        secondary_topic_id = topic_assignment.get("secondary_topic_id")
        topic_slug, topic_display_name = build_topic_labels(
            conn,
            primary_topic_id=primary_topic_id,
            secondary_topic_id=secondary_topic_id,
        )
        existing = conn.execute(
            "SELECT id, created_at, priority, status FROM items WHERE id = ?",
            (storage_item_id,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE items
                SET source_id = ?, provider_item_id = ?, primary_topic_id = ?, secondary_topic_id = ?,
                    topic = ?, topic_display_name = ?,
                    item_type = ?, content = ?, answer = ?, source_ref = ?,
                    updated_at = ?, last_ingested_at = ?
                WHERE id = ?
                """,
                (
                    source_id,
                    provider_item_id,
                    primary_topic_id,
                    secondary_topic_id,
                    topic_slug,
                    topic_display_name,
                    item["presentation_mode"],
                    item["prompt"],
                    item.get("answer", ""),
                    item.get("source", ""),
                    now,
                    now,
                    storage_item_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO items (
                    id, source_id, provider_item_id, primary_topic_id, secondary_topic_id, topic, topic_display_name,
                    item_type, content, answer, source_ref, status, priority,
                    created_at, updated_at, last_ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 1.0, ?, ?, ?)
                """,
                (
                    storage_item_id,
                    source_id,
                    provider_item_id,
                    primary_topic_id,
                    secondary_topic_id,
                    topic_slug,
                    topic_display_name,
                    item["presentation_mode"],
                    item["prompt"],
                    item.get("answer", ""),
                    item.get("source", ""),
                    now,
                    now,
                    now,
                ),
            )
    conn.commit()


def add_feedback_event(conn, item_id, event_type):
    conn.execute(
        "INSERT INTO feedback_events (item_id, event_type, created_at) VALUES (?, ?, ?)",
        (item_id, event_type, utc_now()),
    )
    conn.commit()


def mark_seen(conn, item_id):
    now = utc_now()
    conn.execute("UPDATE items SET last_seen_at = ?, updated_at = ? WHERE id = ?", (now, now, item_id))
    add_feedback_event(conn, item_id, "shown")


def lower_priority(conn, item_id):
    now = utc_now()
    conn.execute(
        """
        UPDATE items
        SET priority = CASE
            WHEN priority <= 0.1 THEN 0.1
            ELSE MAX(priority * 0.5, 0.1)
        END,
            updated_at = ?
        WHERE id = ?
        """,
        (now, item_id),
    )
    add_feedback_event(conn, item_id, "lower_priority")


def delete_item(conn, item_id):
    now = utc_now()
    conn.execute(
        "UPDATE items SET status = 'deleted', updated_at = ? WHERE id = ?",
        (now, item_id),
    )
    add_feedback_event(conn, item_id, "delete")


def load_active_items(conn, topics=None, mode="mixed", limit=5):
    clauses = ["status = 'active'"]
    params = []

    if topics:
        topic_list = [topic.strip() for topic in topics.split(",") if topic.strip()]
        if topic_list:
            placeholders = ",".join("?" for _ in topic_list)
            clauses.append(f"topic IN ({placeholders})")
            params.extend(topic_list)

    if mode != "mixed":
        clauses.append("item_type = ?")
        params.append(mode)

    params.append(limit * 5)
    rows = conn.execute(
        f"""
        SELECT id, topic, topic_display_name, item_type, content, answer, source_ref, priority, last_seen_at
        FROM items
        WHERE {' AND '.join(clauses)}
        ORDER BY priority DESC, COALESCE(last_seen_at, '') ASC, RANDOM()
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]
