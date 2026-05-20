# config.py
HOST = "0.0.0.0"  # Ensures server binds to all available network adapters
USERNAME = ""
PORT = 9000

PEER_ID = None

# FIX: Update these to match the real LAN IP addresses and ports of your network nodes.
# When running across multiple machines, they can even share the same port (e.g., 9000)
# because they live on different IP addresses.
KNOWN_PEERS = [
    ("192.168.1.41", 9001),  # Example LAN IP for Laptop A
    ("192.168.1.41", 9002)   # Example LAN IP for Desktop B
]