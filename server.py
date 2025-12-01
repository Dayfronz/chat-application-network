import socket
import threading
import json
import time

ENCODING = "utf-8"
BUFFER_SIZE = 4096
DELIMITER = "\n"  # messages separated by newline


class ChatServer:
    """
    Multi-client chat server that:
    - Assigns each client a unique ID
    - Tracks connected clients
    - Routes direct messages between clients
    - Sends delivery receipts back to senders
    """

    def __init__(self, host="127.0.0.1", port=5555):
        self.host = host
        self.port = port
        self.server_socket = None
        self.clients = {}  # client_id -> {"socket": sock, "address": addr, "name": name}
        self.next_client_id = 1
        self.lock = threading.Lock()
        self.running = False
        self.message_counter = 1

    def start(self):
        """Start the TCP server and begin accepting clients."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Allow quick restart
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)

        self.running = True
        print(f"[SERVER] ChatServer listening on {self.host}:{self.port}")

        try:
            while self.running:
                conn, addr = self.server_socket.accept()
                threading.Thread(
                    target=self.handle_new_client,
                    args=(conn, addr),
                    daemon=True
                ).start()
        except KeyboardInterrupt:
            print("[SERVER] KeyboardInterrupt received, shutting down.")
        finally:
            self.shutdown()

    def shutdown(self):
        """Stop the server and close all sockets."""
        self.running = False
        print("[SERVER] Shutting down...")
        with self.lock:
            for cid, info in list(self.clients.items()):
                try:
                    info["socket"].close()
                except OSError:
                    pass
            self.clients.clear()
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
        print("[SERVER] Shutdown complete.")

    def handle_new_client(self, conn, addr):
        """Assign client ID, send welcome info, then handle messages."""
        with self.lock:
            client_id = f"C{self.next_client_id:03d}"
            self.next_client_id += 1
            self.clients[client_id] = {
                "socket": conn,
                "address": addr,
                "name": client_id  # for now, name == ID
            }
        print(f"[SERVER] New client {client_id} connected from {addr}")

        try:
            # Send welcome packet with this client's ID and current client list
            welcome_msg = {
                "type": "welcome",
                "client_id": client_id,
                "clients": self._client_list_snapshot()
            }
            self.send_json(conn, welcome_msg)

            # Notify others that a new client joined
            self.broadcast_info(f"{client_id} joined the chat.", exclude_id=client_id)

            # Handle messages from this client
            buffer = ""
            while True:
                data = conn.recv(BUFFER_SIZE)
                if not data:
                    break
                buffer += data.decode(ENCODING)
                while DELIMITER in buffer:
                    line, buffer = buffer.split(DELIMITER, 1)
                    if line.strip():
                        self.handle_client_message(client_id, line)
        except (ConnectionResetError, ConnectionAbortedError):
            print(f"[SERVER] Connection lost with {client_id}")
        finally:
            self.remove_client(client_id)

    def handle_client_message(self, client_id, raw_line):
        """Parse and respond to a client's JSON message."""
        try:
            msg = json.loads(raw_line)
        except json.JSONDecodeError:
            print(f"[SERVER] Failed to decode message from {client_id}: {raw_line}")
            return

        msg_type = msg.get("type")
        if msg_type == "chat":
            self.route_chat_message(client_id, msg)
        elif msg_type == "list":
            self.send_client_list(client_id)
        elif msg_type == "exit":
            self.send_info(client_id, "Goodbye!")
            self.remove_client(client_id)
        else:
            self.send_error(client_id, f"Unknown message type: {msg_type}")

    def route_chat_message(self, sender_id, msg):
        """Forward a chat message to the intended recipient."""
        target_id = msg.get("to")
        text = msg.get("text", "")
        reply_to = msg.get("reply_to")
        timestamp = time.time()

        with self.lock:
            target_info = self.clients.get(target_id)
            sender_info = self.clients.get(sender_id)

        if not target_info:
            self.send_error(sender_id, f"Target client {target_id} not found.")
            return

        # Assign a server-side message ID
        with self.lock:
            message_id = self.message_counter
            self.message_counter += 1

        chat_packet = {
            "type": "chat",
            "message_id": message_id,
            "from": sender_id,
            "to": target_id,
            "text": text,
            "timestamp": timestamp,
            "reply_to": reply_to,
        }
        self.send_json(target_info["socket"], chat_packet)

        # Send receipt back to sender
        receipt_packet = {
            "type": "receipt",
            "message_id": message_id,
            "to": target_id,
            "status": "delivered",
            "timestamp": time.time(),
        }
        if sender_info:
            self.send_json(sender_info["socket"], receipt_packet)

    def send_client_list(self, client_id):
        """Send the current client list to the specified client."""
        snapshot = self._client_list_snapshot()
        packet = {
            "type": "client_list",
            "clients": snapshot
        }
        self.send_to_client_id(client_id, packet)

    def _client_list_snapshot(self):
        """Return a simple list of connected clients for sharing."""
        with self.lock:
            return [
                {"client_id": cid, "address": str(info["address"])}
                for cid, info in self.clients.items()
            ]

    def broadcast_info(self, text, exclude_id=None):
        """Send an info message to all clients (except possibly one)."""
        packet = {
            "type": "info",
            "text": text,
            "timestamp": time.time(),
        }
        with self.lock:
            for cid, info in self.clients.items():
                if cid == exclude_id:
                    continue
                try:
                    self.send_json(info["socket"], packet)
                except OSError:
                    pass

    def send_info(self, client_id, text):
        """Send an info message to a single client."""
        packet = {
            "type": "info",
            "text": text,
            "timestamp": time.time(),
        }
        self.send_to_client_id(client_id, packet)

    def send_error(self, client_id, text):
        """Send an error message to a single client."""
        packet = {
            "type": "error",
            "text": text,
            "timestamp": time.time(),
        }
        self.send_to_client_id(client_id, packet)

    def send_to_client_id(self, client_id, packet):
        """Send a JSON packet to a client by ID."""
        with self.lock:
            info = self.clients.get(client_id)
        if not info:
            return
        try:
            self.send_json(info["socket"], packet)
        except OSError:
            pass

    @staticmethod
    def send_json(sock, obj):
        """Send a JSON object followed by DELIMITER."""
        data = json.dumps(obj) + DELIMITER
        sock.sendall(data.encode(ENCODING))

    def remove_client(self, client_id):
        """Remove client from registry and notify others."""
        with self.lock:
            info = self.clients.pop(client_id, None)
        if info:
            try:
                info["socket"].close()
            except OSError:
                pass
            print(f"[SERVER] Client {client_id} disconnected.")
            self.broadcast_info(f"{client_id} left the chat.", exclude_id=client_id)


if __name__ == "__main__":
    server = ChatServer(host="127.0.0.1", port=5555)
    server.start()
