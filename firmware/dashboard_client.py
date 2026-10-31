"""
dashboard_client.py
OBJ04: sends telemetry and live thermal frames to the FastAPI dashboard.

Speed design (measured: ~2.9 s per upload with urequests -> ~0.4 s with this):
  * The server address is looked up ONCE, not on every upload.
  * ONE HTTP/1.1 keep-alive connection is opened and reused for every upload.
  * The frame JSON is built directly with 0.1 C precision (smaller, faster).

HTTPS:
  * Set DASHBOARD_USE_TLS = True (or DASHBOARD_PORT = 443) in config.py to use HTTPS.
  * If the server answers plain HTTP with a redirect to https:// (HTTP 301/308),
    the client switches to HTTPS on port 443 automatically and retries.
  * The TLS handshake happens once per connection; after that uploads are as fast as HTTP.
    The server certificate is not verified (the Pico has no CA store) - the link is
    encrypted, but this is acceptable only for this academic prototype.

If the connection drops, it reconnects automatically on the next upload.
Public functions keep the same names and return values as before.
"""

import socket
import time
import config

try:
    import ssl
except ImportError:          # firmware without TLS support
    ssl = None

TIMEOUT_S = getattr(config, "HTTP_TIMEOUT_S", 6)


def _wrap_tls(sock, host):
    """Wrap a connected socket in TLS (MicroPython and CPython)."""
    if ssl is None:
        raise OSError("this firmware has no ssl module")
    if hasattr(ssl, "SSLContext"):
        proto = getattr(ssl, "PROTOCOL_TLS_CLIENT", 0)
        ctx = ssl.SSLContext(proto)
        if hasattr(ctx, "check_hostname"):
            ctx.check_hostname = False
        ctx.verify_mode = getattr(ssl, "CERT_NONE", 0)
        return ctx.wrap_socket(sock, server_hostname=host)
    return ssl.wrap_socket(sock, server_hostname=host)


class KeepAliveClient:
    def __init__(self, host, port, use_tls=False):
        self.host = host
        self.port = port
        self.use_tls = use_tls or port == 443
        self.addr = None
        self.sock = None
        self.rfile = None
        self.reconnects = 0
        self.last_error = ""
        self.stage = ""
        self.location = ""

    # ---------------------------------------------------------------- connection
    def _resolve(self):
        self.stage = "dns lookup"
        t = time.ticks_ms()
        self.addr = socket.getaddrinfo(self.host, self.port, 0, socket.SOCK_STREAM)[0][-1]
        print("HTTP: {} -> {} ({} ms)".format(self.host, self.addr, time.ticks_diff(time.ticks_ms(), t)))

    def _connect(self):
        self.close()
        if self.addr is None:
            self._resolve()
        self.stage = "connect"
        t = time.ticks_ms()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(TIMEOUT_S)
        s.connect(self.addr)
        if self.use_tls:
            self.stage = "tls handshake"
            s = _wrap_tls(s, self.host)
        self.sock = s
        # MicroPython sockets (plain and TLS) have readline/read; CPython needs a file wrapper.
        self.rfile = s if hasattr(s, "readline") else s.makefile("rb")
        self.reconnects += 1
        print("HTTP: connected{} ({} ms)".format(" with TLS" if self.use_tls else "",
                                                 time.ticks_diff(time.ticks_ms(), t)))

    def close(self):
        for obj in (self.rfile, self.sock):
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
        self.sock = None
        self.rfile = None

    # ---------------------------------------------------------------- I/O
    def _write_all(self, data):
        send = getattr(self.sock, "sendall", None)
        if send is not None:
            send(data)
            return
        mv = memoryview(data)
        while len(mv):
            n = self.sock.write(mv)
            if n is None:
                n = len(mv)
            mv = mv[n:]

    def _readline(self):
        line = self.rfile.readline()
        if not line:
            raise OSError("connection closed by server")
        return line.rstrip(b"\r\n")

    def _readn(self, n):
        data = b""
        while len(data) < n:
            chunk = self.rfile.read(n - len(data))
            if not chunk:
                raise OSError("connection closed by server")
            data += chunk
        return data

    def _read_response(self):
        parts = self._readline().split(b" ")
        status = int(parts[1].decode()) if len(parts) > 1 else 0
        length = 0
        chunked = False
        keep_alive = True
        self.location = ""
        while True:
            line = self._readline()
            if not line:
                break
            if b":" not in line:
                continue
            name, value = line.split(b":", 1)
            name = name.strip().lower()
            value = value.strip()
            if name == b"content-length":
                length = int(value.decode())
            elif name == b"transfer-encoding" and value.lower() == b"chunked":
                chunked = True
            elif name == b"connection" and value.lower() == b"close":
                keep_alive = False
            elif name == b"location":
                self.location = value.decode()
        if chunked:
            while True:
                size = int(self._readline().split(b";")[0].decode(), 16)
                if size == 0:
                    self._readline()
                    break
                self._readn(size + 2)
        elif length:
            self._readn(length)
        if not keep_alive:
            self.close()
        return status

    # ---------------------------------------------------------------- request
    def post_json(self, path, body, extra_headers=""):
        """POST a JSON string. Returns the HTTP status code, or 0 on failure."""
        if isinstance(body, str):
            body = body.encode()
        for attempt in range(2):
            head = ("POST {} HTTP/1.1\r\n"
                    "Host: {}\r\n"
                    "Content-Type: application/json\r\n"
                    "Content-Length: {}\r\n"
                    "Connection: keep-alive\r\n"
                    "{}\r\n").format(path, self.host, len(body), extra_headers).encode()
            try:
                if self.sock is None:
                    self._connect()
                self.stage = "send"
                self._write_all(head + body)
                self.stage = "wait for reply"
                status = self._read_response()
            except Exception as e:
                self.last_error = "{} failed at {}: {!r}".format(path, self.stage, e)
                print("HTTP:", self.last_error)
                self.close()
                if self.stage in ("dns lookup", "connect", "tls handshake"):
                    self.addr = None      # look the address up again next time
                    return 0              # no point retrying straight away
                continue                  # stale keep-alive connection: retry once on a new one

            # Server redirects plain HTTP to HTTPS -> switch over once and retry.
            if status in (301, 302, 307, 308) and self.location.startswith("https://") and not self.use_tls:
                print("HTTP: server redirects to HTTPS ({}) - switching to HTTPS on port 443".format(self.location))
                self.close()
                self.use_tls = True
                self.port = 443
                self.addr = None
                continue

            if not 200 <= status < 300:
                self.last_error = "{} reply: HTTP {}{}".format(
                    path, status, (" -> " + self.location) if self.location else "")
            return status
        return 0


_client = KeepAliveClient(config.DASHBOARD_HOST, config.DASHBOARD_PORT,
                          getattr(config, "DASHBOARD_USE_TLS", False))


def _auth_header():
    token = getattr(config, "DEVICE_API_TOKEN", "")
    return "Authorization: Bearer {}\r\n".format(token) if token else ""


def _num(v):
    return "null" if v is None else "{:.1f}".format(float(v))


def _text(v):
    """JSON string (or null) for short device text such as the firmware version."""
    if v is None:
        return "null"
    return '"' + str(v).replace("\\", "/").replace('"', "'") + '"'


def _int(v):
    return "null" if v is None else str(int(v))


def post_telemetry(state, max_thermal_c, ambient_c, suppression_active,
                   firmware=None, rssi_dbm=None, uptime_s=None, free_memory=None):
    """Posts the device state (plus optional health details). True on HTTP 2xx. Never raises."""
    body = ('{{"state":"{}","max_thermal_c":{},"ambient_c":{},'
            '"suppression_active":{},"classification_source":"firmware",'
            '"firmware":{},"rssi_dbm":{},"uptime_s":{},"free_memory":{}}}').format(
        state, _num(max_thermal_c), _num(ambient_c),
        "true" if suppression_active else "false",
        _text(firmware), _int(rssi_dbm), _int(uptime_s), _int(free_memory))
    status = _client.post_json(config.DASHBOARD_ENDPOINT, body, _auth_header())
    return 200 <= status < 300


def post_thermal_frame(frame, ambient_c=None):
    """Posts the 768-value (32x24) frame at 0.1 C precision. True on HTTP 2xx."""
    pixels = ",".join(["{:.1f}".format(v) for v in frame])
    body = ('{{"width":32,"height":24,"pixels":[{}],"ambient_c":{},'
            '"sensor_temperature_c":null,"source":"hardware"}}').format(pixels, _num(ambient_c))
    status = _client.post_json(config.DASHBOARD_FRAME_ENDPOINT, body, _auth_header())
    return 200 <= status < 300


def last_error():
    """Why the most recent failed upload failed ("" if none yet)."""
    return _client.last_error


def connection_stats():
    """Number of TCP connections opened so far (should stay at 1 when healthy)."""
    return _client.reconnects


def close():
    _client.close()
    