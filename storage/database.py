import sqlite3
import hashlib
import config


def get_db_name():
    """Generates a unique database name per instance based on its active port."""
    return f"chat_{config.USERNAME}.db"


def get_db_connection():
    """Opens a connection and ensures schema exists."""
    db_name = get_db_name()
    conn = sqlite3.connect(db_name, check_same_thread=False, timeout=10)

    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_hash TEXT UNIQUE,
        sender TEXT,
        recipient TEXT,
        message TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        is_read INTEGER DEFAULT 0
    )
    """)

    try:
        cursor.execute("ALTER TABLE messages ADD COLUMN is_read INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    conn.commit()
    return conn


def save_message(sender, message, recipient=None):
    if recipient == "Global Chat":
        recipient = None

    raw_payload = f"{sender}:{recipient or 'Global'}:{message.strip()}"
    msg_hash = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT OR IGNORE INTO messages 
            (msg_hash, sender, message, recipient) 
            VALUES (?, ?, ?, ?)
        """, (msg_hash, sender, message, recipient))

        conn.commit()
    except Exception as e:
        print(f"[DB_ERROR] Failed to save message: {e}")
    finally:
        conn.close()


def get_history(target_peer=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    my_id = config.PEER_ID

    if target_peer is None or target_peer == "Global Chat":
        cursor.execute("""
            SELECT sender, message, timestamp, is_read
            FROM messages
            WHERE recipient IS NULL
            ORDER BY id ASC
        """)
    else:
        cursor.execute("""
            SELECT sender, message, timestamp, is_read
            FROM messages
            WHERE (sender = ? AND recipient = ?)
               OR (sender = ? AND recipient = ?)
            ORDER BY id ASC
        """, (my_id, target_peer, target_peer, my_id))

    rows = cursor.fetchall()
    conn.close()
    return rows


def get_all_chat_peers():
    conn = get_db_connection()
    cursor = conn.cursor()

    peers = set()
    cursor.execute("SELECT sender, recipient FROM messages")

    for sender, recipient in cursor.fetchall():
        if sender and sender != config.PEER_ID:
            peers.add(sender)
        if recipient and recipient != config.PEER_ID:
            peers.add(recipient)

    conn.close()
    return sorted(peers)


def get_unread_count(target_peer=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    my_id = config.PEER_ID

    if target_peer is None or target_peer == "Global Chat":
        cursor.execute("""
            SELECT COUNT(*) FROM messages
            WHERE recipient IS NULL AND is_read = 0
        """)
    else:
        cursor.execute("""
            SELECT COUNT(*) FROM messages
            WHERE ((sender = ? AND recipient = ?) OR (sender = ? AND recipient = ?))
            AND is_read = 0
            AND sender != ?
        """, (target_peer, my_id, my_id, target_peer, my_id))

    count = cursor.fetchone()[0]
    conn.close()
    return count


def mark_as_read(target_peer=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    my_id = config.PEER_ID

    if target_peer is None or target_peer == "Global Chat":
        cursor.execute("""
            UPDATE messages SET is_read = 1
            WHERE recipient IS NULL AND is_read = 0
        """)
    else:
        cursor.execute("""
            UPDATE messages SET is_read = 1
            WHERE ((sender = ? AND recipient = ?) OR (sender = ? AND recipient = ?))
            AND is_read = 0
            AND sender != ?
        """, (target_peer, my_id, my_id, target_peer, my_id))

    conn.commit()
    conn.close()
