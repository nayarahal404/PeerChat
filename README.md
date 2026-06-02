# PeerChat — Secure Decentralized P2P Messaging System

PeerChat is a decentralized peer-to-peer messaging platform written in Python. Each node acts as both a client and server, enabling direct encrypted communication without relying on a centralized backend. **Identity is cryptographically derived from RSA keys, ensuring that your username is uniquely yours.**

The system now supports:

* **Context-Aware Filtering:** Private messages are isolated from Global Chat via a dual-pane UI.
* **Automatic Peer Discovery:** Dynamic network expansion through bootstrap peers.
* **RSA Identity Verification:** Secure challenge-response authentication.
* **Modernized GUI:** Polished PyQt6 interface with dark mode and sidebar navigation.
* **Local Persistence:** Full message history stored and retrieved via SQLite.
* **File Attachments (New):** Direct peer-to-peer file sharing with an intuitive layout and automated local caching.

---

# Features

## Networking & Data Transfer

* Fully decentralized peer-to-peer architecture.
* TCP socket communication with newline-delimited JSON streaming.
* **Robust File Streaming:** Binary files are automatically serialized using Base64 ASCII strings, optimized with buffered socket streams to allow seamless cross-platform delivery without data corruption or packet dropping.
* Automatic peer discovery through bootstrap peers and dynamic peer list exchange.
* Multi-peer simultaneous communication with continuous receive loops.
* **Connectivity Note:** Ensure your **trusted bootstrap peers** are online and reachable on their specified ports to join the network swarm successfully.

## Security

* **RSA Public/Private Keys:** Identity proven via cryptographic signatures.
* **Cryptographic Peer IDs:** Peer IDs are generated as a hash of your RSA Public Key (`Username-Hash`), preventing identity spoofing.
* **Challenge-Response Flow:** Prevents identity theft without ever transmitting private keys or passwords.
* **Key Isolation:** All sensitive `.pem` files are stored in a dedicated `keys/` directory, organized by username.

## Messaging & Sharing

* **Direct Private Messaging:** Target specific peers for 1-on-1 filtered conversations.
* **Global Broadcast:** Message all connected peers in the swarm simultaneously.
* **File Attachments:** WhatsApp-style file sending interface natively integrated next to the input message bar.
* **Automatic Downloads:** Received attachments are automatically buffered, collision-checked to prevent filename overwriting, and stored securely in a local `downloads/` folder.
* **JSON Packet Protocol:** Structured communication payloads for precise text routing and robust file segment mapping.
* **Persistence:** All text messages and file-transfer reference markers are saved locally to `chat_history.db`.

## GUI

* **Modern PyQt6 Interface:** Sidebar for peer selection and a sleek dark-themed chat area.
* **Attachment Button:** A dedicated paperclip attachment icon (📎) mapped directly to your operating system's native file explorer.
* **Enhanced Log Rendering:** Context-aware UI highlighting that dynamically wraps file attachments in custom stylized blocks to differentiate them from standard text messages.
* **Identity Header:** Clear display of your unique cryptographic Peer ID at the top right.
* **Contextual History:** Automatic message retrieval from SQLite based on the selected peer in the sidebar.

---

# Architecture

```text
                ┌───────────────┐
                │   Peer A      │
                └──────┬────────┘
                       │
         ┌─────────────┼─────────────┐
         │                           │
┌────────▼────────┐         ┌────────▼────────┐
│    Peer B       │         │    Peer C       │
└────────┬────────┘         └────────┬────────┘
         │                           │
         └─────────────┬─────────────┘
                       │
                ┌──────▼────────┐
                │    Peer D     │
                └───────────────┘


```

Each peer contains:

* Listener Server & Outgoing Client Connector
* Message Handler & Peer Discovery Engine
* Authentication Layer (RSA)
* Local SQLite Database, Buffered Downloader, & Modern PyQt6 Frontend

---

# Authentication Flow

PeerChat uses cryptographic verification instead of passwords.

```text
1. Connect
      ↓
2. Exchange Public Keys (Identity Packet)
      ↓
3. Generate Random Challenge
      ↓
4. Sign Challenge with Private Key
      ↓
5. Verify Signature using Public Key
      ↓
6. Authenticated Communication Begins


```

---

# Message Protocol

## Chat Packet (Direct/Global)

```json
{
    "type": "chat",
    "data": {
        "sender": "Alice-a1b2c3d4",
        "recipient": "Bob-e5f6g7h8", 
        "message": "Hello, Bob!"
    }
}

```

*If `recipient` is null, the message is treated as a Global Broadcast.*

## File Transfer Packet (New)

```json
{
    "type": "file_transfer",
    "data": {
        "sender": "Alice-a1b2c3d4",
        "recipient": "Bob-e5f6g7h8",
        "file_name": "document.pdf",
        "payload": "JVBERi0xLjQKJbXtr90KMSAwIG9iagogIDw8IC9UeXBlIC9DYXRhbG9nCiAgICAvUGFn..."
    }
}

```

---

# Folder Structure

```text
peerchat/
│
├── main.py             # Entry point (Handles CLI arguments for Port/Username)
├── config.py           # Runtime settings (Username, Peer ID, Port)
│
├── keys/               # Secure storage for RSA keys
│   ├── Alice_private.pem
│   └── Alice_public.pem
│
├── downloads/          # Auto-created folder for received file attachments
│   └── shared_image.png
│
├── gui/
│   ├── app.py          # Start GUI
│   ├── chat_window.py  # Attachment action trigger, UI rendering, & Filtered logic
│   └── signals.py      # Event bus (3-part signaling: Sender, Msg, Recipient)
│
├── network/
│   ├── server.py       # Handshake, Buffered File Writer, Routing & Signal Emission
│   ├── client.py       # Connection, Base64 File Serializer & Transmission logic
│   └── discovery.py    # Global peer registry
│
├── security/
│   ├── keys.py         # Public & private key generation
│   └── crypto.py       # Hashing, and filename management
│   
└── storage/
    └── database.py     # SQLite history (get_history, save_message)

```

---

# Running PeerChat

When setting up a project simulation rather than connecting to an established network, ensure that the bootstrap peers are initialized first.

## Install Dependencies

```bash
pip install pyqt6 cryptography

```

## Running Multiple Instances

To run peers locally, provide the **Port** and **Username** as arguments. The system will automatically generate or load keys for that username.

**Terminal 1 (Alice):**

```bash
python main.py 9000 Alice

```

**Terminal 2 (Bob):**

```bash
python main.py 9001 Bob

```

**Terminal 3 (Charlie):**

```bash
python main.py 9002 Charlie

```
# Bootstrap Peers Configuration

PeerChat relies on a set of bootstrap peers to discover and connect to the network. These peers are currently defined in `network/discovery.py` as:

```python
BOOTSTRAP_PEERS = [
    ("192.168.1.41", 9000),
    ("192.168.1.41", 9001),
    ("127.0.0.1", 9002)
]
```

When deploying PeerChat on a Local Area Network (LAN), you should modify the IP addresses to match the machines that will act as initial bootstrap nodes on your network.

For example, if two peers are running on a machine with LAN IP `192.168.1.50`, you might configure:

```python
BOOTSTRAP_PEERS = [
    ("192.168.1.50", 9000),
    ("192.168.1.50", 9001)
]
```

For local testing on a single machine, you can connect through the localhost bootstrap peer:

```python
("127.0.0.1", 9002)
```

or add additional localhost entries:

```python
BOOTSTRAP_PEERS = [
    ("127.0.0.1", 9000),
    ("127.0.0.1", 9001),
    ("127.0.0.1", 9002)
]
```

At least one bootstrap peer must be online and reachable for new nodes to discover and join the network successfully. Once connected, PeerChat automatically exchanges peer information and expands the network through its peer discovery mechanism.

---

# Planned Improvements

* **E2EE Messaging:** Encrypting message payloads and file buffers natively with RSA Public Keys/AES-GCM before transport serialization.
* **NAT Traversal:** UDP hole punching and STUN support for over-the-internet P2P swarming.
* **Advanced UI:** Unread message indicators and visual file transfer progress bars.

---

# License

MIT License. See `LICENSE` for details.