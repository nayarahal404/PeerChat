import socket, threading, secrets, config, os , base64
from network.protocol import parse_packet, create_packet
from network.discover import (
    connected_peers, authenticated_peers, peer_public_keys, pending_challenges,
    peer_ids, add_known_peer, remove_connection, network_lock,
    register_authenticated_connection, get_authenticated_peer_addresses
)
from storage.database import save_message
from security.keys import pem_to_public_key
from security.crypto import verify_signature

# FIX 1: Change HOST to '0.0.0.0' so the server listens on all network interfaces (WiFi, Ethernet, and localhost)
LISTEN_HOST = "0.0.0.0"


# FIX 2: Dynamically detect this machine's actual LAN IP address (e.g., 192.168.1.5)
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # This doesn't actually connect or send data, it just forces the OS to pick the active network interface
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "127.0.0.1"
    finally:
        s.close()
    return local_ip


MY_LAN_IP = get_local_ip()
print(f"[SYSTEM] Detected local LAN IP: {MY_LAN_IP}")


def push_routing_table(target_sock):
    peers = [[ip, port] for ip, port in get_authenticated_peer_addresses()]
    # FIX 3: Push our actual LAN IP to peers instead of 127.0.0.1
    peers.append([MY_LAN_IP, int(config.PORT)])
    try:
        target_sock.sendall(create_packet("peer_response", {"peers": peers}))
    except:
        pass


def broadcast_new_peer(new_ip, new_port, exception_sock):
    packet = create_packet("peer_response", {"peers": [[new_ip, int(new_port)]]})
    with network_lock:
        all_socks = list(authenticated_peers)
    for sock in all_socks:
        if sock != exception_sock:
            try:
                sock.sendall(packet)
            except:
                pass


def receive_loop(conn):
    f = conn.makefile('rb')
    remote_listening_addr, temp_peer_id = None, None

    while True:
        try:
            line = f.readline()
            if not line: break
            packet = parse_packet(line)
            p_type, p_data = packet["type"], packet["data"]

            if p_type == "identity":
                temp_peer_id = p_data["peer_id"]
                remote_listening_addr = (conn.getpeername()[0], int(p_data["listening_port"]))

                # FIX 4: Prevent connecting to yourself by checking against your actual LAN IP and localhost
                if remote_listening_addr[1] == int(config.PORT):
                    if remote_listening_addr[0] in ("127.0.0.1", MY_LAN_IP):
                        break

                with network_lock:
                    peer_public_keys[conn] = pem_to_public_key(p_data["public_key"])
                challenge = secrets.token_hex(16)
                with network_lock:
                    pending_challenges[conn] = challenge
                conn.sendall(create_packet("challenge", {"challenge": challenge}))

            elif p_type == "challenge_response":
                with network_lock:
                    ch, pub = pending_challenges.get(conn), peer_public_keys.get(conn)
                if ch and pub and verify_signature(
                        pub,
                        ch,
                        bytes.fromhex(p_data["signature"])
                ):

                    if remote_listening_addr and temp_peer_id:
                        peer_ip = remote_listening_addr[0]
                        peer_port = remote_listening_addr[1]

                        register_authenticated_connection(
                            peer_ip,
                            peer_port,
                            conn,
                            temp_peer_id
                        )

                        print(
                            f"[AUTH] SUCCESS | "
                            f"PEER={temp_peer_id} | "
                            f"IP={peer_ip} | "
                            f"PORT={peer_port}"
                        )

                        conn.sendall(
                            create_packet(
                                "peer_welcome",
                                {
                                    "peer_id": config.PEER_ID,
                                    "listening_port": int(config.PORT)
                                }
                            )
                        )

                        push_routing_table(conn)

                        broadcast_new_peer(
                            peer_ip,
                            peer_port,
                            conn
                        )
                else:
                    break

            elif p_type == "peer_welcome":
                register_authenticated_connection(conn.getpeername()[0], int(p_data["listening_port"]), conn,
                                                  p_data["peer_id"])

            elif p_type == "challenge":
                from network.client import handle_challenge
                handle_challenge(conn, p_data["challenge"])

            elif p_type == "chat":
                with network_lock:
                    authenticated = conn in authenticated_peers
                if not authenticated:
                    continue

                msg_id = p_data.get("msg_id")
                sender = p_data["sender"]
                recipient = p_data.get("recipient")
                message = p_data["message"]

                if sender == config.PEER_ID:
                    continue

                save_message(sender, message, recipient)
                from gui.signals import event_bus
                event_bus.message_received.emit(sender, message, recipient)

                # Send delivery acknowledgement back to original sender node
                if msg_id:
                    try:
                        conn.sendall(create_packet("msg_ack", {"msg_id": msg_id, "status": "delivered"}))
                    except:
                        pass

            elif p_type == "peer_request":
                with network_lock:
                    authenticated = conn in authenticated_peers
                if authenticated: push_routing_table(conn)

            elif p_type == "file_transfer":
                with network_lock:
                    authenticated = conn in authenticated_peers
                if not authenticated:
                    continue

                msg_id = p_data.get("msg_id")
                sender = p_data["sender"]
                recipient = p_data.get("recipient")
                file_name = p_data["file_name"]
                payload = p_data["payload"]

                if sender == config.PEER_ID:
                    continue

                # Reconstruct and save file
                os.makedirs("downloads", exist_ok=True)

                # Deduplicate filename if it exists
                save_path = os.path.join("downloads", file_name)
                counter = 1
                base, ext = os.path.splitext(file_name)
                while os.path.exists(save_path):
                    save_path = os.path.join("downloads", f"{base}_{counter}{ext}")
                    counter += 1

                try:
                    with open(save_path, "wb") as f:
                        f.write(base64.b64decode(payload))
                except Exception as e:
                    print(f"[SERVER] Failed to write file: {e}")
                    continue

                # Build a display message for DB and GUI
                display_msg = f"📎 Sent a file: {os.path.basename(save_path)}"

                # Save to database and alert GUI via event bus
                save_message(sender, display_msg, recipient)
                from gui.signals import event_bus
                event_bus.message_received.emit(sender, display_msg, recipient)

                # Send delivery acknowledgement back to original sender node
                if msg_id:
                    try:
                        conn.sendall(create_packet("msg_ack", {"msg_id": msg_id, "status": "delivered"}))
                    except:
                        pass

            # Handle Incoming Delivery Acknowledgements from peers
            elif p_type == "msg_ack":
                ack_id = p_data.get("msg_id")
                status = p_data.get("status")
                from gui.signals import event_bus
                event_bus.message_status_updated.emit(ack_id, status)

            elif p_type == "peer_response":
                from network.client import connect_to_peer
                for ip, port in p_data.get("peers", []):
                    port = int(port)

                    # FIX 5: Skip self-routing updates if the ip matches localhost or your LAN IP
                    if port == int(config.PORT) and ip in ("127.0.0.1", MY_LAN_IP):
                        continue

                    with network_lock:
                        connected = (ip, port) in connected_peers
                    if not connected:
                        add_known_peer(ip, port)
                        connect_to_peer(ip, port, receive_loop)
        except:
            break
    remove_connection(conn)


def start_server(port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # FIX 6: Bind to LISTEN_HOST ('0.0.0.0') instead of the hardcoded localhost
    server.bind((LISTEN_HOST, port))
    server.listen()
    from network.client import start_discovery_loop
    start_discovery_loop(receive_loop)
    while True:
        try:
            conn, _ = server.accept()
            threading.Thread(target=receive_loop, args=(conn,), daemon=True).start()
        except:
            pass