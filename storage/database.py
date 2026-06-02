import sqlite3
import hashlib
import config


def get_db_name():
    """Generates a unique database name per instance based on its active port."""
    return f"chat_{config.PORT}.db"


def get_db_connection():
    """Opens a connection and dynamically ensures the schema exists before returning."""
    db_name = get_db_name()
    conn = sqlite3.connect(db_name, check_same_thread=False, timeout=10)

    # Force schema creation verification on the active file context
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_hash TEXT UNIQUE,
        sender TEXT,
        recipient TEXT,
        message TEXT
    )
    """)
    conn.commit()
    return conn


def save_message(sender, message, recipient=None):
    if recipient == "Global Chat":
        recipient = None

    raw_payload = f"{sender}:{recipient or 'Global'}:{message.strip()}"
    msg_hash = hashlib.sha256(raw_payload.encode('utf-8')).hexdigest()

    # Get connection (this automatically ensures the table exists)
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT OR IGNORE INTO messages (msg_hash, sender, message, recipient) VALUES (?, ?, ?, ?)",
            (msg_hash, sender, message, recipient)
        )
        conn.commit()
    except Exception as e:
        print(f"[DB_ERROR] Failed to save message: {e}")
    finally:
        conn.close()


def get_history(target_peer=None):
    # Get connection (this automatically ensures the table exists)
    conn = get_db_connection()
    cursor = conn.cursor()
    my_id = config.PEER_ID

    if target_peer is None or target_peer == "Global Chat":
        cursor.execute("SELECT sender, message FROM messages WHERE recipient IS NULL ORDER BY id ASC")
    else:
        cursor.execute("""
            SELECT sender, message FROM messages 
            WHERE (sender = ? AND recipient = ?) 
            OR (sender = ? AND recipient = ?)
            ORDER BY id ASC
        """, (my_id, target_peer, target_peer, my_id))

    rows = cursor.fetchall()
    conn.close()
    return rows

def get_all_chat_peers():
    """
    Returns every peer we've ever exchanged messages with.
    Used to populate the sidebar even when peers are offline.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    peers = set()

    # People who sent us messages
    cursor.execute("""
        SELECT DISTINCT sender
        FROM messages
        WHERE sender IS NOT NULL
    """)

    for (sender,) in cursor.fetchall():
        if sender and sender != config.PEER_ID:
            peers.add(sender)

    # People we sent messages to
    cursor.execute("""
        SELECT DISTINCT recipient
        FROM messages
        WHERE recipient IS NOT NULL
    """)

    for (recipient,) in cursor.fetchall():
        if recipient and recipient != config.PEER_ID:
            peers.add(recipient)



    conn.close()

    return sorted(peers)