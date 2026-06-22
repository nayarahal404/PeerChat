import socket, threading, time, config, os
import random
import base64
from network.protocol import create_packet
from network.discover import connected_peers, known_peers, BOOTSTRAP_PEERS, add_known_peer, network_lock

DISCOVERY_INTERVAL = 30

MAX_PEERS = 12
GOSSIP_FANOUT = 2
GOSSIP_PEER_SAMPLE = 5
RETRY_COOLDOWN = 60

private_key, public_key = None, None


# FIX 1: Dynamically detect this machine's actual LAN IP address (same as server)
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


def init_client_keys():
    global private_key, public_key
    from security.keys import ensure_keys_exist, load_private_key, load_public_key
    ensure_keys_exist()
    private_key, public_key = load_private_key(), load_public_key()


def connect_to_peer(ip, port, receive_loop):
    port, my_port = int(port), int(config.PORT)

    # FIX 2: Block connections to yourself if the target IP is localhost OR your own LAN IP
    if port == my_port and ip in ("127.0.0.1", MY_LAN_IP):
        return

    with network_lock:
        if (ip, port) in connected_peers: return

    # FIX 3: Maintain the race-condition delay for local debugging instances, checking both loopbacks
    if my_port > port and ip in ("127.0.0.1", MY_LAN_IP):
        time.sleep(0.2)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        sock.connect((ip, port))
        sock.settimeout(None)

        threading.Thread(target=receive_loop, args=(sock,), daemon=True).start()

        from security.keys import public_key_to_pem
        sock.sendall(create_packet("identity", {
            "peer_id": config.PEER_ID, "public_key": public_key_to_pem(public_key), "listening_port": my_port
        }))
    except:
        pass


def handle_challenge(sock, challenge):
    from security.crypto import sign_message
    signature = sign_message(private_key, challenge)
    try:
        sock.sendall(create_packet("challenge_response", {"signature": signature.hex()}))
    except:
        pass


def send_chat_message(message, target_peer_id=None):
    from network.protocol import create_packet
    from network.discover import network_lock, peer_ids, authenticated_peers
    import config

    # Generate tracking unique hash for delivery indicators
    msg_id = f"{config.PEER_ID}_{time.time_ns()}"

    packet = create_packet("chat", {
        "msg_id": msg_id,
        "sender": config.PEER_ID,
        "recipient": target_peer_id,
        "message": message
    })

    sent_peers = set()

    with network_lock:
        active_sockets = [sock for sock in authenticated_peers if sock in peer_ids]

        for sock in active_sockets:
            p_id = peer_ids[sock]

            if target_peer_id and p_id != target_peer_id:
                continue

            if p_id in sent_peers:
                continue

            try:
                sock.sendall(packet)
                sent_peers.add(p_id)
            except:
                pass

    return msg_id


last_attempts = {}


def send_file_attachment(file_path, target_peer_id=None):
    from network.protocol import create_packet
    from network.discover import network_lock, peer_ids, authenticated_peers
    import config

    if not os.path.exists(file_path):
        return None, None

    file_name = os.path.basename(file_path)

    # Read and encode file to base64 string
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    base64_data = base64.b64encode(file_bytes).decode('utf-8')

    # Generate tracking unique hash for delivery indicators
    msg_id = f"{config.PEER_ID}_{time.time_ns()}"

    packet = create_packet("file_transfer", {
        "msg_id": msg_id,
        "sender": config.PEER_ID,
        "recipient": target_peer_id,
        "file_name": file_name,
        "payload": base64_data
    })

    sent_peers = set()

    with network_lock:
        active_sockets = [sock for sock in authenticated_peers if sock in peer_ids]

        for sock in active_sockets:
            p_id = peer_ids[sock]

            if target_peer_id and p_id != target_peer_id:
                continue

            if p_id in sent_peers:
                continue

            try:
                sock.sendall(packet)
                sent_peers.add(p_id)
            except:
                pass

    return file_name, msg_id  # Return to GUI for local rendering and status tracking


def start_discovery_loop(receive_loop):
    def loop():
        # ---------------------------------
        # Add bootstrap peers once
        # ---------------------------------
        for ip, port in BOOTSTRAP_PEERS:
            # FIX 4: Ensure bootstrap filters skip self if bootstrap addresses match your own LAN IP
            if int(port) == int(config.PORT) and ip in ("127.0.0.1", MY_LAN_IP):
                continue
            add_known_peer(ip, port)

        # ---------------------------------
        # Main discovery loop
        # ---------------------------------
        while True:
            try:
                with network_lock:
                    known = list(known_peers)
                    connected = list(connected_peers)

                print(
                    f"[DISCOVERY] "
                    f"known={len(known)} "
                    f"connected={len(connected)}"
                )

                current_connections = len(connected)
                if current_connections < MAX_PEERS:
                    candidates = [
                        peer for peer in known
                        if peer not in connected
                    ]

                    random.shuffle(candidates)
                    needed = MAX_PEERS - current_connections

                    print(
                        f"[DISCOVERY] "
                        f"Need {needed} more peer(s)"
                    )

                    for ip, port in candidates[:needed]:
                        peer = (ip, port)
                        now = time.time()

                        if peer in last_attempts:
                            elapsed = now - last_attempts[peer]
                            if elapsed < RETRY_COOLDOWN:
                                print(
                                    f"[DISCOVERY] "
                                    f"Cooldown active for "
                                    f"{ip}:{port}"
                                )
                                continue
                        last_attempts[peer] = now
                        print(
                            f"[DISCOVERY] "
                            f"Connecting to "
                            f"{ip}:{port}"
                        )
                        try:
                            connect_to_peer(
                                ip,
                                port,
                                receive_loop
                            )
                        except Exception as e:
                            print(
                                f"[DISCOVERY] "
                                f"Connection failed "
                                f"{ip}:{port} -> {e}"
                            )

                # ---------------------------------
                # Gossip discovery
                # ---------------------------------
                from network.discover import get_all_connections

                all_socks = get_all_connections()
                if all_socks:
                    gossip_targets = random.sample(
                        all_socks,
                        min(
                            GOSSIP_FANOUT,
                            len(all_socks)
                        )
                    )
                    packet = create_packet(
                        "peer_request",
                        {"sample_size": GOSSIP_PEER_SAMPLE}
                    )
                    print(
                        f"[DISCOVERY] "
                        f"Gossiping to "
                        f"{len(gossip_targets)} peer(s)"
                    )
                    for sock in gossip_targets:
                        try:
                            peername = sock.getpeername()
                            print(
                                f"[DISCOVERY] -> "
                                f"Requesting "
                                f"{GOSSIP_PEER_SAMPLE} "
                                f"peer(s) from "
                                f"{peername[0]}:"
                                f"{peername[1]}"
                            )
                            sock.sendall(packet)
                        except Exception as e:
                            print(
                                f"[DISCOVERY] "
                                f"Gossip send failed: "
                                f"{e}"
                            )
                else:
                    print("[DISCOVERY] No active sockets")

            except Exception as e:
                print(f"[DISCOVERY] Loop error: {e}")

            time.sleep(DISCOVERY_INTERVAL)

    threading.Thread(
        target=loop,
        daemon=True
    ).start()