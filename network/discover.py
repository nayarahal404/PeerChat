import threading
import socket
import config

network_lock = threading.Lock()
authenticated_peers = set()
peer_public_keys = {}
pending_challenges = {}
known_peers = set()
connected_peers = {}  # {(ip, port): socket}
peer_ids = {}


# FIX 1: Dynamically track this machine's LAN IP to prevent self-targeting
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "127.0.0.1"
    finally:
        s.close()
    return local_ip


MY_LAN_IP = get_local_ip()

BOOTSTRAP_PEERS = [("192.168.1.41", 9000), ("192.168.1.41", 9001), ("127.0.0.1", 9002)]


def add_known_peer(ip, port):
    # FIX 3: Prevent adding yourself to the known peer list via localhost OR your active LAN IP
    if int(port) == int(config.PORT) and ip in ("127.0.0.1", MY_LAN_IP):
        return

    with network_lock:
        known_peers.add((ip, int(port)))


def register_authenticated_connection(ip, port, sock, peer_id):
    with network_lock:
        if (ip, port) in connected_peers:
            old_sock = connected_peers[(ip, port)]
            if old_sock != sock:
                try:
                    authenticated_peers.discard(old_sock)
                    for d in [peer_ids, peer_public_keys, pending_challenges]: d.pop(old_sock, None)
                    old_sock.close()
                except:
                    pass
        connected_peers[(ip, port)] = sock
        authenticated_peers.add(sock)
        peer_ids[sock] = peer_id
    add_known_peer(ip, port)


def remove_connection(sock):
    with network_lock:
        try:
            authenticated_peers.discard(sock)
            for d in [peer_ids, peer_public_keys, pending_challenges]: d.pop(sock, None)
            for addr, s in list(connected_peers.items()):
                if s == sock: del connected_peers[addr]
            sock.close()
        except:
            pass


def get_all_connections():
    with network_lock: return list(connected_peers.values())


def get_authenticated_peer_addresses():
    with network_lock: return list(connected_peers.keys())