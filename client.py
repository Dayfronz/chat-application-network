import socket
import threading
import json
import time
from datetime import datetime

ENCODING = "utf-8"
BUFFER_SIZE = 4096
DELIMITER = "\n"


class ChatClient:
    """
    Chat client that:
    - Connects to server and receives a unique client_id
    - Supports commands: /list, /msg, /reply, /search, /temp, /exit
    - Tracks local message history and supports search and replies
    - Implements temporary messages that are 'deleted' after a timeout on the client side
    """

    def __init__(self, host="127.0.0.1", port=5555):
        self.host = host
        self.port = port
        self.sock = None
        self.client_id = None
        self.running = False
        self.history = []  # list of dicts: {id, direction, peer, text, timestamp, reply_to, temp_until, deleted}
        self.history_lock = threading.Lock()

    def connect(self):
        """Connect to server and start listener and input threads."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        self.running = True

        # Receive welcome message
        welcome_line = self._recv_line()
        welcome = json.loads(welcome_line)
        if welcome.get("type") != "welcome":
            print("[CLIENT] Unexpected welcome packet:", welcome)
            return
        self.client_id = welcome["client_id"]
        print(f"[CLIENT] Connected as {self.client_id}")
        print("[CLIENT] Currently connected clients:")
        for c in welcome.get("clients", []):
            print(f"  - {c['client_id']} at {c['address']}")

        # Start listener thread
        threading.Thread(target=self.listen_loop, daemon=True).start()
        # Start user input loop (blocking)
        self.input_loop()

    def listen_loop(self):
        """Listen for messages from the server."""
        try:
            buffer = ""
            while self.running:
                data = self.sock.recv(BUFFER_SIZE)
                if not data:
                    print("[CLIENT] Server disconnected.")
                    break
                buffer += data.decode(ENCODING)
                while DELIMITER in buffer:
                    line, buffer = buffer.split(DELIMITER, 1)
                    if line.strip():
                        self.handle_server_message(line)
        except (ConnectionResetError, ConnectionAbortedError):
            print("[CLIENT] Connection lost.")
        finally:
            self.running = False

    def input_loop(self):
        """Handle user input from the terminal."""
        print("\n[CLIENT] Commands:")
        print("  /list                        - Show connected clients")
        print("  /msg <id> <text>             - Send message to client <id>")
        print("  /reply <msg_id> <text>       - Reply to a previous message")
        print("  /search <keyword>            - Search local message history")
        print("  /temp <id> <sec> <text>      - Send temp message that deletes locally after <sec> seconds")
        print("  /exit                        - Exit the chat\n")

        try:
            while self.running:
                user_input = input("> ").strip()
                if not user_input:
                    continue
                if user_input.startswith("/"):
                    self.handle_command(user_input)
                else:
                    print("Please use a command (e.g., /msg, /list, /exit).")
        except (EOFError, KeyboardInterrupt):
            print("\n[CLIENT] Exiting...")
            self.running = False
            self.send_exit()
        finally:
            try:
                self.sock.close()
            except OSError:
                pass

    def handle_command(self, cmd_line):
        """Parse and execute a user command."""
        parts = cmd_line.split(" ", 2)
        cmd = parts[0]

        if cmd == "/list":
            self.send_list_request()

        elif cmd == "/msg" and len(parts) >= 3:
            target_id = parts[1]
            text = parts[2]
            self.send_chat(target_id, text)

        elif cmd == "/reply":
            # /reply <msg_id> <text>
            msg_id_str, _, rest = cmd_line[len("/reply "):].partition(" ")
            if not rest:
                print("Usage: /reply <msg_id> <text>")
                return
            try:
                msg_id = int(msg_id_str)
            except ValueError:
                print("Message ID must be an integer.")
                return
            text = rest
            self.send_reply(msg_id, text)

        elif cmd == "/search" and len(parts) >= 2:
            keyword = cmd_line[len("/search "):].strip()
            if not keyword:
                print("Usage: /search <keyword>")
                return
            self.search_history(keyword)

        elif cmd == "/temp":
            # /temp <id> <sec> <text>
            tokens = cmd_line.split(" ", 3)
            if len(tokens) < 4:
                print("Usage: /temp <id> <sec> <text>")
                return
            target_id = tokens[1]
            try:
                seconds = float(tokens[2])
            except ValueError:
                print("Seconds must be a number.")
                return
            text = tokens[3]
            self.send_temp_message(target_id, text, seconds)

        elif cmd == "/exit":
            self.running = False
            self.send_exit()

        else:
            print("Unknown or malformed command.")

    def send_list_request(self):
        packet = {"type": "list"}
        self._send_json(packet)

    def send_chat(self, target_id, text, reply_to=None, temp_until=None):
        packet = {
            "type": "chat",
            "to": target_id,
            "text": text,
            "reply_to": reply_to,
        }
        self._send_json(packet)
        # Locally record outgoing message with temporary placeholder ID, updated on receipt
        with self.history_lock:
            entry = {
                "id": None,  # will be updated when receipt arrives
                "direction": "out",
                "peer": target_id,
                "text": text,
                "timestamp": time.time(),
                "reply_to": reply_to,
                "temp_until": temp_until,
                "deleted": False,
            }
            self.history.append(entry)

    def send_reply(self, msg_id, text):
        """Reply to a previous message by ID."""
        with self.history_lock:
            target_msg = next((m for m in self.history if m["id"] == msg_id), None)
        if not target_msg:
            print(f"[CLIENT] No message with ID {msg_id} in history.")
            return
        peer = target_msg["peer"]
        self.send_chat(peer, text, reply_to=msg_id)

    def send_temp_message(self, target_id, text, seconds):
        """Send a temporary message that is later 'deleted' locally."""
        temp_until = time.time() + seconds
        self.send_chat(target_id, text, reply_to=None, temp_until=temp_until)
        # spawn a thread to mark deletion after timeout
        threading.Thread(
            target=self._temp_cleanup_worker,
            args=(temp_until, text),
            daemon=True
        ).start()

    def _temp_cleanup_worker(self, temp_until, text):
        """Mark temp message as deleted after timeout."""
        remaining = temp_until - time.time()
        if remaining > 0:
            time.sleep(remaining)
        with self.history_lock:
            for m in self.history:
                if (
                    m["text"] == text
                    and m["temp_until"] == temp_until
                    and not m["deleted"]
                ):
                    m["deleted"] = True
                    break
        print("[CLIENT] (Temp) A message has expired and was removed from local history.")

    def send_exit(self):
        packet = {"type": "exit"}
        try:
            self._send_json(packet)
        except OSError:
            pass

    def handle_server_message(self, raw_line):
        """Process a JSON packet from the server."""
        try:
            msg = json.loads(raw_line)
        except json.JSONDecodeError:
            print("[CLIENT] Failed to decode server message:", raw_line)
            return

        mtype = msg.get("type")
        if mtype == "chat":
            self.handle_chat_message(msg)
        elif mtype == "receipt":
            self.handle_receipt(msg)
        elif mtype == "client_list":
            self.handle_client_list(msg)
        elif mtype == "info":
            print(f"[INFO] {msg.get('text')}")
        elif mtype == "error":
            print(f"[ERROR] {msg.get('text')}")
        else:
            print("[CLIENT] Unknown packet type:", msg)

    def handle_chat_message(self, msg):
        mid = msg.get("message_id")
        sender = msg.get("from")
        text = msg.get("text")
        ts = msg.get("timestamp")
        reply_to = msg.get("reply_to")
        ts_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "?"

        with self.history_lock:
            entry = {
                "id": mid,
                "direction": "in",
                "peer": sender,
                "text": text,
                "timestamp": ts,
                "reply_to": reply_to,
                "temp_until": None,
                "deleted": False,
            }
            self.history.append(entry)

        if reply_to:
            print(f"[{ts_str}] {sender} (reply to #{reply_to}): {text}  [#{mid}]")
        else:
            print(f"[{ts_str}] {sender}: {text}  [#{mid}]")

    def handle_receipt(self, msg):
        mid = msg.get("message_id")
        target = msg.get("to")
        ts = msg.get("timestamp")
        ts_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "?"

        # update outgoing message entry with message id
        with self.history_lock:
            for m in self.history:
                if (
                    m["direction"] == "out"
                    and m["id"] is None
                    and m["peer"] == target
                    and not m["deleted"]
                ):
                    m["id"] = mid
                    break

        print(f"[RECEIPT {ts_str}] Message #{mid} delivered to {target}")

    def handle_client_list(self, msg):
        print("[CLIENT] Connected clients:")
        for c in msg.get("clients", []):
            print(f"  - {c['client_id']} at {c['address']}")

    def search_history(self, keyword):
        """Search local history for keyword and print matches."""
        keyword_lower = keyword.lower()
        print(f"[CLIENT] Searching for '{keyword}'...")
        with self.history_lock:
            matches = [
                m for m in self.history
                if (not m["deleted"] and keyword_lower in m["text"].lower())
            ]
        if not matches:
            print("[CLIENT] No matches found.")
            return
        for m in matches:
            direction = "From" if m["direction"] == "in" else "To"
            peer = m["peer"]
            mid = m["id"]
            ts = m["timestamp"]
            ts_str = (
                datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                if ts else "?"
            )
            print(f"  [#{mid or '?'}] {direction} {peer} at {ts_str}: {m['text']}")

    def _send_json(self, obj):
        data = json.dumps(obj) + DELIMITER
        self.sock.sendall(data.encode(ENCODING))

    def _recv_line(self):
        buffer = ""
        while DELIMITER not in buffer:
            data = self.sock.recv(BUFFER_SIZE)
            if not data:
                raise ConnectionError("Server closed connection during welcome.")
            buffer += data.decode(ENCODING)
        line, _ = buffer.split(DELIMITER, 1)
        return line


if __name__ == "__main__":
    client = ChatClient(host="127.0.0.1", port=5555)
    client.connect()
