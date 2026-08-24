import socket
import threading
from datetime import datetime
import json
import re
import os

PROXY_HOST     = '0.0.0.0'
PROXY_PORT     = 25630
SERVER_ADDRESS = 'madeswara.mc-syncara.my.id'
SERVER_PORT    = 25653

LOGS_DIR       = 'logs'
DATABASE_DIR   = 'database'
CREDS_FILE     = os.path.join(DATABASE_DIR, 'creds.json')

HARI_INDONESIA = {
    'Monday'   : 'Senin',
    'Tuesday'  : 'Selasa',
    'Wednesday': 'Rabu',
    'Thursday' : 'Kamis',
    'Friday'   : 'Jumat',
    'Saturday' : 'Sabtu',
    'Sunday'   : 'Minggu'
}

class Color:
    RED     = '\033[91m'
    GREEN   = '\033[92m'
    YELLOW  = '\033[93m'
    BLUE    = '\033[94m'
    CYAN    = '\033[96m'
    WHITE   = '\033[97m'
    MAGENTA = '\033[95m'
    RESET   = '\033[0m'
    BOLD    = '\033[1m'

def ensure_dirs():
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(DATABASE_DIR, exist_ok=True)

def get_log_filename() -> str:
    now      = datetime.now()
    tanggal  = now.strftime('%d')
    hari_en  = now.strftime('%A')
    hari_id  = HARI_INDONESIA.get(hari_en, hari_en)
    tahun    = now.strftime('%Y')
    bulan    = now.strftime('%m')
    filename = f"logs-{tanggal}-{hari_id}-{bulan}-{tahun}.json"
    return os.path.join(LOGS_DIR, filename)

def log_print(message: str, color=Color.WHITE):
    print(f"{color}{message}{Color.RESET}")

file_locks      = {}
file_locks_lock = threading.Lock()

def get_file_lock(filepath: str) -> threading.Lock:
    with file_locks_lock:
        if filepath not in file_locks:
            file_locks[filepath] = threading.Lock()
        return file_locks[filepath]

def load_json_file(filepath: str, default) -> dict | list:
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        log_print(f"[ERROR] Gagal load {filepath}: {e}", Color.RED)
    return default() if callable(default) else default

def save_json_file(filepath: str, data):
    try:
        temp = filepath + '.tmp'
        with open(temp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(temp, filepath)
    except Exception as e:
        log_print(f"[ERROR] Gagal save {filepath}: {e}", Color.RED)

def default_logs() -> dict:
    now     = datetime.now()
    hari_en = now.strftime('%A')
    hari_id = HARI_INDONESIA.get(hari_en, hari_en)
    return {
        "info": {
            "tanggal"     : now.strftime('%d-%m-%Y'),
            "hari"        : hari_id,
            "dibuat_pada" : now.isoformat()
        },
        "logs": []
    }

def default_creds() -> dict:
    return {
        "metadata": {
            "created_at"       : datetime.now().isoformat(),
            "last_updated"     : datetime.now().isoformat(),
            "total_connections": 0
        },
        "players": {}
    }

def logs_append(line: str):
    log_file = get_log_filename()
    lock     = get_file_lock(log_file)
    with lock:
        data = load_json_file(log_file, default_logs)
        data["logs"].append(line)
        save_json_file(log_file, data)

def log_event_login(username: str, ip: str, port: int, session_id: str):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] LOGIN | User: {username} | IP: {ip}:{port} | Session: {session_id}"
    logs_append(line)

def log_event_logout(username: str, ip: str, session_id: str, duration_sec: int):
    ts      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    h, rem  = divmod(duration_sec, 3600)
    m, s    = divmod(rem, 60)
    line    = f"[{ts}] LOGOUT | User: {username} | IP: {ip} | Durasi: {h:02d}:{m:02d}:{s:02d} | Session: {session_id}"
    logs_append(line)

def log_event_chat(username: str, ip: str, session_id: str, message: str):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] CHAT | {username} ({ip}) | {message}"
    logs_append(line)

def log_event_command(username: str, ip: str, session_id: str, command: str):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] COMMAND | {username} ({ip}) | {command}"
    logs_append(line)

def creds_add_login(username: str, ip: str, port: int) -> str:
    session_id = f"{username}_{ip}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    timestamp  = datetime.now().isoformat()
    ip_entry   = f"{ip}:{port}"

    lock = get_file_lock(CREDS_FILE)
    with lock:
        data    = load_json_file(CREDS_FILE, default_creds)
        data["metadata"]["total_connections"] += 1
        data["metadata"]["last_updated"] = datetime.now().isoformat()

        players = data.setdefault("players", {})

        if username not in players:
            players[username] = {
                "username"      : username,
                "first_seen"    : timestamp,
                "last_seen"     : timestamp,
                "total_sessions": 0,
                "ip_addresses"  : [],
                "total_messages": 0,
                "total_commands": 0,
                "sessions"      : []
            }

        player = players[username]
        player["last_seen"]      = timestamp
        player["total_sessions"] += 1

        if ip_entry not in player["ip_addresses"]:
            player["ip_addresses"].append(ip_entry)

        player["sessions"].append({
            "session_id"  : session_id,
            "ip"          : ip,
            "port"        : port,
            "login_time"  : timestamp,
            "logout_time" : None,
            "duration_sec": None,
            "messages"    : [],
            "commands"    : []
        })

        save_json_file(CREDS_FILE, data)

    return session_id

def creds_add_logout(session_id: str, username: str, duration_sec: int):
    timestamp = datetime.now().isoformat()

    lock = get_file_lock(CREDS_FILE)
    with lock:
        data = load_json_file(CREDS_FILE, default_creds)

        if username in data.get("players", {}):
            player = data["players"][username]
            player["last_seen"] = timestamp

            for session in player.get("sessions", []):
                if session["session_id"] == session_id:
                    session["logout_time"]  = timestamp
                    session["duration_sec"] = duration_sec
                    break

        data["metadata"]["last_updated"] = datetime.now().isoformat()
        save_json_file(CREDS_FILE, data)

def creds_add_chat(session_id: str, username: str, message: str):
    timestamp = datetime.now().isoformat()

    lock = get_file_lock(CREDS_FILE)
    with lock:
        data = load_json_file(CREDS_FILE, default_creds)

        if username in data.get("players", {}):
            player = data["players"][username]
            player["total_messages"] += 1

            for session in player.get("sessions", []):
                if session["session_id"] == session_id:
                    session["messages"].append({
                        "timestamp": timestamp,
                        "message"  : message
                    })
                    break

        data["metadata"]["last_updated"] = datetime.now().isoformat()
        save_json_file(CREDS_FILE, data)

def creds_add_command(session_id: str, username: str, command: str):
    timestamp = datetime.now().isoformat()

    lock = get_file_lock(CREDS_FILE)
    with lock:
        data = load_json_file(CREDS_FILE, default_creds)

        if username in data.get("players", {}):
            player = data["players"][username]
            player["total_commands"] += 1

            for session in player.get("sessions", []):
                if session["session_id"] == session_id:
                    session["commands"].append({
                        "timestamp": timestamp,
                        "command"  : command
                    })
                    break

        data["metadata"]["last_updated"] = datetime.now().isoformat()
        save_json_file(CREDS_FILE, data)

def resolve_address(address: str) -> str | None:
    try:
        socket.inet_aton(address)
        return address
    except socket.error:
        try:
            ip = socket.gethostbyname(address)
            log_print(f"[INFO] Domain '{address}' -> {ip}", Color.CYAN)
            return ip
        except socket.gaierror:
            log_print(f"[ERROR] Tidak dapat resolve: {address}", Color.RED)
            return None

def read_varint(data: bytes, offset: int = 0):
    result = 0
    shift  = 0
    while shift < 35:
        if offset >= len(data):
            return None, offset
        byte    = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, offset
        shift += 7
    return None, offset

def read_string_raw(data: bytes, offset: int = 0):
    length, new_offset = read_varint(data, offset)
    if length is None or length < 0 or length > 32767:
        return None, None, offset
    if new_offset + length > len(data):
        return None, None, offset
    raw = data[new_offset:new_offset + length]
    try:
        text = raw.decode('utf-8', errors='replace')
        return raw, text, new_offset + length
    except Exception:
        return None, None, offset

def split_packets(data: bytes):
    packets = []
    offset  = 0
    while offset < len(data):
        start               = offset
        pkt_len, new_offset = read_varint(data, offset)
        if pkt_len is None:
            packets.append(data[offset:])
            break
        if pkt_len <= 0:
            offset = new_offset
            continue
        end = new_offset + pkt_len
        if end > len(data):
            packets.append(data[start:])
            break
        packets.append(data[new_offset:end])
        offset = end
    return packets

COMMAND_PATTERN = re.compile(r'^/[a-zA-Z][a-zA-Z0-9_]*(\s.*)?$')

SYSTEM_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'^com\.mojang',
        r'^net\.minecraft',
        r'^java\.lang',
        r'^org\.',
        r'^\{.*\}$',
        r'^\[.*\]$',
        r'https?://',
        r'\\u[0-9a-fA-F]{4}',
    ]
]

def has_too_many_special_chars(text: str) -> bool:
    if not text:
        return True
    letter_count = sum(1 for c in text if c.isalpha())
    total        = len(text)
    if total > 3 and letter_count / total < 0.20:
        return True
    non_ascii = sum(1 for c in text if ord(c) > 127)
    if non_ascii > total * 0.3:
        return True
    return False

def is_real_chat_message(text: str) -> bool:
    if not text:
        return False
    if len(text) < 1 or len(text) > 256:
        return False
    if text.startswith('/'):
        return False
    if not any(c.isalpha() for c in text):
        return False
    if any(ord(c) < 32 for c in text):
        return False
    if '\x00' in text or '\ufffd' in text:
        return False
    for pattern in SYSTEM_PATTERNS:
        if pattern.search(text):
            return False
    if has_too_many_special_chars(text):
        return False
    readable = sum(1 for c in text if c.isalnum() or c == ' ')
    if readable < 2:
        return False
    return True

def is_real_command(text: str) -> bool:
    if not text or not text.startswith('/'):
        return False
    if len(text) < 2 or len(text) > 256:
        return False
    if any(ord(c) < 32 for c in text):
        return False
    if '\x00' in text or '\ufffd' in text:
        return False
    if not COMMAND_PATTERN.match(text):
        return False
    return True

def extract_strings_from_packet(packet_body: bytes) -> list[str]:
    results = []
    seen    = set()

    for start_offset in range(len(packet_body)):
        length, str_start = read_varint(packet_body, start_offset)
        if length is None or length <= 0 or length > 512:
            continue
        if str_start + length > len(packet_body):
            continue
        raw = packet_body[str_start:str_start + length]
        if b'\x00' in raw:
            continue
        try:
            text = raw.decode('utf-8', errors='strict')
        except UnicodeDecodeError:
            continue
        if text in seen:
            continue
        if text.startswith('/'):
            if is_real_command(text):
                seen.add(text)
                results.append(text)
        else:
            if is_real_chat_message(text):
                seen.add(text)
                results.append(text)

    return results

def try_extract_chat_from_packet(packet_body: bytes) -> list[str]:
    if len(packet_body) < 2:
        return []

    found  = []
    pkt_id, id_end = read_varint(packet_body, 0)
    if pkt_id is None:
        return []

    try:
        raw, text, _ = read_string_raw(packet_body, id_end)
        if text and '\ufffd' not in text and '\x00' not in text:
            if text.startswith('/') and is_real_command(text):
                found.append(text)
            elif is_real_chat_message(text):
                found.append(text)
    except Exception:
        pass

    for s in extract_strings_from_packet(packet_body):
        if s not in found:
            found.append(s)

    return found

USERNAME_REGEX     = re.compile(r'^[a-zA-Z0-9_]{3,16}$')
USERNAME_BLACKLIST = {
    'localhost', 'minecraft', 'client', 'server',
    'java', 'version', 'release', 'snapshot',
    'com', 'net', 'org', 'www', 'http', 'https',
    'true', 'false', 'null', 'void', 'class',
    'public', 'private', 'static', 'final',
    'forge', 'fabric', 'optifine', 'sodium',
    'play', 'join', 'login', 'register',
}

def extract_username_from_data(data: bytes) -> str | None:
    candidates = []

    for pkt in split_packets(data):
        if len(pkt) < 2:
            continue
        for start_offset in range(len(pkt)):
            length, str_start = read_varint(pkt, start_offset)
            if length is None or length < 3 or length > 16:
                continue
            if str_start + length > len(pkt):
                continue
            raw = pkt[str_start:str_start + length]
            try:
                text = raw.decode('utf-8', errors='strict')
                if USERNAME_REGEX.match(text) and text.lower() not in USERNAME_BLACKLIST:
                    candidates.append(text)
            except UnicodeDecodeError:
                pass

    try:
        decoded = data.decode('latin-1', errors='replace')
        for word in re.findall(r'[a-zA-Z0-9_]{3,16}', decoded):
            if (USERNAME_REGEX.match(word)
                    and word.lower() not in USERNAME_BLACKLIST
                    and not word.isdigit()):
                candidates.append(word)
    except Exception:
        pass

    if not candidates:
        return None

    seen, unique = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    valid = [c for c in unique
             if 3 <= len(c) <= 16
             and not c.isdigit()
             and USERNAME_REGEX.match(c)]

    return valid[0] if valid else None

class ConnectionState:
    def __init__(self, addr: tuple):
        self.addr         = addr
        self.ip           = addr[0]
        self.port         = addr[1]
        self.username     = f"Unknown_{addr[0]}"
        self.username_set = False
        self.login_time   = datetime.now()
        self.session_id   = None
        self.lock         = threading.Lock()
        self.recent_texts = []
        self.MAX_RECENT   = 50

    def set_username(self, name: str) -> bool:
        with self.lock:
            if not self.username_set and name:
                self.username     = name
                self.username_set = True
                return True
        return False

    def is_duplicate(self, text: str) -> bool:
        with self.lock:
            if text in self.recent_texts:
                return True
            self.recent_texts.append(text)
            if len(self.recent_texts) > self.MAX_RECENT:
                self.recent_texts.pop(0)
            return False

def handle_c2s_data(data: bytes, state: ConnectionState):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not state.username_set:
        username = extract_username_from_data(data)
        if username:
            if state.set_username(username):
                state.session_id = creds_add_login(
                    username = username,
                    ip       = state.ip,
                    port     = state.port
                )
                log_event_login(
                    username   = username,
                    ip         = state.ip,
                    port       = state.port,
                    session_id = state.session_id
                )
                msg = (f"[{timestamp}] LOGIN | "
                       f"User: {username} | "
                       f"IP: {state.ip}:{state.port}")
                log_print(f"\n{'='*60}", Color.CYAN)
                log_print(msg, Color.CYAN)
                log_print(f"{'='*60}", Color.CYAN)

    if not state.username_set:
        return

    seen_this_packet = set()
    found_texts      = []

    for pkt_body in split_packets(data):
        if len(pkt_body) < 2:
            continue
        for text in try_extract_chat_from_packet(pkt_body):
            if text and text not in seen_this_packet:
                seen_this_packet.add(text)
                found_texts.append(text)

    for text in found_texts:
        if state.is_duplicate(text):
            continue

        if text.startswith('/'):
            msg = (f"[{timestamp}] COMMAND | "
                   f"{state.username} ({state.ip}) | {text}")
            log_print(f"⚡ {msg}", Color.YELLOW)
            log_event_command(
                username   = state.username,
                ip         = state.ip,
                session_id = state.session_id,
                command    = text
            )
            if state.session_id:
                creds_add_command(
                    session_id = state.session_id,
                    username   = state.username,
                    command    = text
                )
        else:
            msg = (f"[{timestamp}] CHAT | "
                   f"{state.username} ({state.ip}) | {text}")
            log_print(f"💬 {msg}", Color.GREEN)
            log_event_chat(
                username   = state.username,
                ip         = state.ip,
                session_id = state.session_id,
                message    = text
            )
            if state.session_id:
                creds_add_chat(
                    session_id = state.session_id,
                    username   = state.username,
                    message    = text
                )

def handle_s2c_data(data: bytes, state: ConnectionState):
    pass

def forward_data(source: socket.socket,
                 destination: socket.socket,
                 direction: str,
                 state: ConnectionState):
    try:
        while True:
            try:
                data = source.recv(65536)
            except Exception:
                break
            if not data:
                break

            if direction == "c2s":
                handle_c2s_data(data, state)
            else:
                handle_s2c_data(data, state)

            try:
                destination.sendall(data)
            except Exception:
                break

    except Exception as e:
        log_print(f"[ERROR] forward_data ({direction}): {e}", Color.RED)

    finally:
        if state.username_set:
            timestamp    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            duration_sec = int((datetime.now() - state.login_time).total_seconds())
            h, rem       = divmod(duration_sec, 3600)
            m, s         = divmod(rem, 60)

            msg = (f"[{timestamp}] LOGOUT | "
                   f"{state.username} ({state.ip}) | "
                   f"Durasi: {h:02d}:{m:02d}:{s:02d}")
            log_print(f"\n{'='*60}", Color.RED)
            log_print(msg, Color.RED)
            log_print(f"{'='*60}\n", Color.RED)

            log_event_logout(
                username     = state.username,
                ip           = state.ip,
                session_id   = state.session_id,
                duration_sec = duration_sec
            )
            if state.session_id:
                creds_add_logout(
                    session_id   = state.session_id,
                    username     = state.username,
                    duration_sec = duration_sec
                )

        for sock in [source, destination]:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass

def handle_client(client_socket: socket.socket, addr: tuple):
    server_socket = None
    state         = ConnectionState(addr)

    try:
        server_ip = resolve_address(SERVER_ADDRESS)
        if not server_ip:
            client_socket.close()
            return

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        server_socket.connect((server_ip, SERVER_PORT))
        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        log_print(
            f"[CONNECT] {addr[0]}:{addr[1]} -> {SERVER_ADDRESS}:{SERVER_PORT}",
            Color.MAGENTA
        )

        t1 = threading.Thread(
            target = forward_data,
            args   = (client_socket, server_socket, "c2s", state),
            daemon = True
        )
        t2 = threading.Thread(
            target = forward_data,
            args   = (server_socket, client_socket, "s2c", state),
            daemon = True
        )
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    except ConnectionRefusedError:
        log_print(f"[ERROR] Server menolak koneksi dari {addr[0]}", Color.RED)
    except Exception as e:
        log_print(f"[ERROR] handle_client: {e}", Color.RED)
    finally:
        for sock in [client_socket, server_socket]:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

def main():
    ensure_dirs()

    if not os.path.exists(CREDS_FILE):
        save_json_file(CREDS_FILE, default_creds())

    log_file = get_log_filename()
    if not os.path.exists(log_file):
        save_json_file(log_file, default_logs())

    proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        proxy.bind((PROXY_HOST, PROXY_PORT))
        proxy.listen(100)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hari_id   = HARI_INDONESIA.get(datetime.now().strftime('%A'), '')

        log_print("="*60, Color.BOLD)
        log_print("  MINECRAFT PROXY LOGGER", Color.BOLD)
        log_print("="*60, Color.BOLD)
        log_print(f"  Started  : {timestamp} ({hari_id})", Color.WHITE)
        log_print(f"  Proxy    : {PROXY_HOST}:{PROXY_PORT}", Color.WHITE)
        log_print(f"  Target   : {SERVER_ADDRESS}:{SERVER_PORT}", Color.WHITE)
        log_print(f"  Logs     : {log_file}", Color.WHITE)
        log_print(f"  Creds    : {CREDS_FILE}", Color.WHITE)
        log_print("="*60, Color.BOLD)
        log_print("  Tracking : LOGIN | LOGOUT | CHAT | COMMAND", Color.GREEN)
        log_print("="*60 + "\n", Color.BOLD)

        while True:
            try:
                client, addr = proxy.accept()
                threading.Thread(
                    target = handle_client,
                    args   = (client, addr),
                    daemon = True
                ).start()
            except KeyboardInterrupt:
                log_print("\n[INFO] Proxy dihentikan.", Color.YELLOW)
                break
            except Exception as e:
                log_print(f"[ERROR] Accept: {e}", Color.RED)

    except PermissionError:
        log_print(f"[ERROR] Port {PROXY_PORT} butuh akses root/admin", Color.RED)
    except OSError as e:
        log_print(f"[ERROR] Bind gagal: {e}", Color.RED)
    finally:
        proxy.close()

if __name__ == '__main__':
    main()
