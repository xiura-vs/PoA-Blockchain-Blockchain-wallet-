"""
p2p.py - minimal TCP peer-to-peer layer (stdlib only).

Wire format: one JSON object per line:
  {"id": "<random>", "type": "tx|block|hello|get_blocks|blocks",
   "data": {...}, "from": <sender's listening port>, "gossip": true|false}

- Each node LISTENS on its port (inbound sockets: we only read from these)
- Each node DIALS every peer (outbound sockets: we only write to these)
- Gossip messages are deduplicated by id and forwarded only if the
  application layer (on_message) says the content was valid.
"""

import json
import os
import socket
import threading
import time
import uuid
from collections import OrderedDict

MAX_LINE = 10_000_000       # bytes; a longer line drops the connection
SEND_TIMEOUT = 2.0


class SeenCache:
    """Bounded set of message ids we've already processed."""
    def __init__(self, cap=20000):
        self.cap, self.d, self.lock = cap, OrderedDict(), threading.Lock()

    def add(self, key) -> bool:
        """True if the key is new."""
        with self.lock:
            if key in self.d:
                return False
            self.d[key] = 1
            if len(self.d) > self.cap:
                self.d.popitem(last=False)
            return True


class P2P:
    def __init__(self, name, port, peer_ports, on_message, on_connect=None, host="127.0.0.1"):
        self.name, self.host, self.port = name, host, port
        self.peer_addrs = [(host, p) for p in peer_ports if p != port]
        self.on_message = on_message          # fn(msg) -> bool  (True = valid, relay it)
        self.on_connect = on_connect          # fn(addr)
        self.out = {}                         # addr -> socket (outbound)
        self.out_lock = threading.Lock()
        self.inbound = []
        self.inbound_lock = threading.Lock()
        self.seen = SeenCache()
        self.running = False
        self.server = None

    # ---- lifecycle ---------------------------------------------------------
    def start(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if os.name != "nt":   # on Windows SO_REUSEADDR would allow port hijacking
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.host, self.port))
        srv.listen(16)
        srv.settimeout(0.5)
        self.server = srv
        self.running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._connect_loop, daemon=True).start()

    def stop(self):
        self.running = False
        socks = []
        if self.server:
            socks.append(self.server)
        with self.out_lock:
            socks += list(self.out.values())
            self.out.clear()
        with self.inbound_lock:
            socks += self.inbound
            self.inbound = []
        for s in socks:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass

    def connected(self) -> int:
        with self.out_lock:
            return len(self.out)

    # ---- inbound -----------------------------------------------------------
    def _accept_loop(self):
        while self.running:
            try:
                conn, _ = self.server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            conn.settimeout(None)             # blocking reads
            with self.inbound_lock:
                self.inbound.append(conn)
            threading.Thread(target=self._reader, args=(conn,), daemon=True).start()

    def _reader(self, conn):
        f = conn.makefile("rb")
        try:
            while self.running:
                line = f.readline(MAX_LINE + 1)
                if not line or not line.endswith(b"\n"):
                    break                     # EOF, or line too long -> drop peer
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue                  # garbage line: ignore
                if isinstance(msg, dict):
                    self._handle(msg)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _handle(self, msg):
        mid, mtype = msg.get("id"), msg.get("type")
        if not isinstance(mid, str) or not isinstance(mtype, str):
            return
        gossip = msg.get("gossip") is True
        if gossip and not self.seen.add(mid):
            return                            # already processed -> stops gossip loops
        try:
            forward = self.on_message(msg)
        except Exception as e:                # a bad message must never kill the node
            print(f"[{self.name}] handler error: {type(e).__name__}: {e}", flush=True)
            forward = False
        if gossip and forward:
            self._send_all(msg)

    # ---- outbound ----------------------------------------------------------
    def _connect_loop(self):
        while self.running:
            for addr in self.peer_addrs:
                with self.out_lock:
                    if addr in self.out:
                        continue
                try:
                    s = socket.create_connection(addr, timeout=1.0)
                    s.settimeout(SEND_TIMEOUT)
                except OSError:
                    continue
                with self.out_lock:
                    self.out[addr] = s
                if self.on_connect:
                    try:
                        self.on_connect(addr)
                    except Exception:
                        pass
            time.sleep(1.0)

    def _send_line(self, addr, line: bytes) -> bool:
        with self.out_lock:
            s = self.out.get(addr)
            if s is None:
                return False
            try:
                s.sendall(line)
                return True
            except OSError:
                try:
                    s.close()
                except OSError:
                    pass
                del self.out[addr]            # connect loop will redial
                return False

    @staticmethod
    def _encode(msg) -> bytes:
        return (json.dumps(msg, separators=(",", ":")) + "\n").encode()

    def _send_all(self, msg):
        line = self._encode(msg)
        for addr in self.peer_addrs:
            self._send_line(addr, line)

    # ---- public API --------------------------------------------------------
    def broadcast(self, mtype, data, gossip=True):
        msg = {"id": uuid.uuid4().hex, "type": mtype, "data": data,
               "from": self.port, "gossip": gossip}
        if gossip:
            self.seen.add(msg["id"])          # don't process our own message when it echoes back
        self._send_all(msg)

    def send_to_port(self, port, mtype, data) -> bool:
        """Direct (non-gossip) message. Only to peers we know (no reflection to random ports)."""
        addr = (self.host, port) if type(port) is int else None
        if addr not in self.peer_addrs:
            return False
        msg = {"id": uuid.uuid4().hex, "type": mtype, "data": data,
               "from": self.port, "gossip": False}
        return self._send_line(addr, self._encode(msg))