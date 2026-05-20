# main.py
import sys
import threading
import time
import socket
import config

from network.server import start_server
from network.client import init_client_keys
from security.keys import ensure_keys_exist
from gui.app import start_gui

# Helper to log the local network context visually on startup
def get_runtime_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "127.0.0.1"
    finally:
        s.close()
    return local_ip

def start_network(my_port):
    """Launches the localized binding instance safely."""
    server_thread = threading.Thread(target=start_server, args=(my_port,), daemon=True)
    server_thread.start()
    print(f"[MAIN] Server process bound and running on listening port: {my_port}")

    time.sleep(1)
    print(f"[MAIN] Background peer discovery system fully deployed.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python main.py <port> <username>")
        sys.exit(1)

    # Global runtime configurations assigned immediately upon execution
    config.PORT = int(sys.argv[1])
    config.USERNAME = sys.argv[2]

    # Storing node structural ID parameters safely
    node_id = ensure_keys_exist()
    config.PEER_ID = node_id

    current_lan_ip = get_runtime_lan_ip()

    print(f"--- PeerChat Network Mode ---")
    print(f"User Identification: {config.USERNAME}")
    print(f"Cryptographic ID:    {config.PEER_ID}")
    print(f"Local Network IP:    {current_lan_ip}") # Added for clear LAN visibility
    print(f"Listening Port:      {config.PORT}")
    print(f"-----------------------------")

    init_client_keys()

    network_thread = threading.Thread(target=start_network, args=(config.PORT,), daemon=True)
    network_thread.start()

    # Pass primary application execution over to GUI execution framework
    start_gui()