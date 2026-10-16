#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Com Toolbox v0.1 - Modbus TCP server simulator with a web interface.

Start:   python com_toolbox.py
Options: python com_toolbox.py --help

Only the Python standard library is used (Python 3.8 or later).
The page Com_Toolbox.html must be in the same folder as this file.

(c) 2026 Philippe RAYMOND - Licence CC BY-NC-ND 4.0
Official version: phil-legacy.github.io/toolbox
"""

import argparse
import collections
import json
import math
import os
import random
import socket
import socketserver
import struct
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

VERSION = "0.1"
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "Com_Toolbox.html")

TABLES = ("co", "di", "hr", "ir")
TABLE_NAMES = {"co": "Coils", "di": "Discrete inputs", "hr": "Holding registers", "ir": "Input registers"}
WORDS = {"BOOL": 0, "INT": 1, "UINT": 1, "DINT": 2, "UDINT": 2, "REAL": 2}
ORDERS = ("ABCD", "CDAB", "BADC", "DCBA")
# position of the value bytes (A=0 .. D=3) in register byte order
PERM = {"ABCD": (0, 1, 2, 3), "CDAB": (2, 3, 0, 1), "BADC": (1, 0, 3, 2), "DCBA": (3, 2, 1, 0)}
GENS = ("manual", "ramp", "sine", "square", "random", "counter", "follow", "level", "compare")
TICK = 0.05  # generator and sampling period, s


# ----------------------------------------------------------------- encoding
def wrap_int(v, typ):
    """Integers wrap around like in a PLC."""
    try:
        if isinstance(v, float) and not math.isfinite(v):
            v = 0
        v = int(round(v))
    except (TypeError, ValueError, OverflowError):
        v = 0
    if typ == "INT":
        return ((v + 0x8000) & 0xFFFF) - 0x8000
    if typ == "UINT":
        return v & 0xFFFF
    if typ == "DINT":
        return ((v + 0x80000000) & 0xFFFFFFFF) - 0x80000000
    if typ == "UDINT":
        return v & 0xFFFFFFFF
    return v


def value_bytes(v, typ):
    """Value -> bytes A B (C D), most significant first."""
    if typ == "INT":
        return struct.pack(">h", wrap_int(v, typ))
    if typ == "UINT":
        return struct.pack(">H", wrap_int(v, typ))
    if typ == "DINT":
        return struct.pack(">i", wrap_int(v, typ))
    if typ == "UDINT":
        return struct.pack(">I", wrap_int(v, typ))
    if typ == "REAL":
        try:
            return struct.pack(">f", float(v))
        except OverflowError:  # beyond float32: +-INF, like a PLC
            return struct.pack(">f", math.inf if float(v) > 0 else -math.inf)
        except (TypeError, ValueError):
            return struct.pack(">f", 0.0)
    raise ValueError(typ)


def to_regs(v, typ, order):
    b = value_bytes(v, typ)
    if len(b) == 2:
        if order in ("BADC", "DCBA"):
            b = b[::-1]
        return [b[0] << 8 | b[1]]
    p = PERM[order]
    rb = bytes(b[p[i]] for i in range(4))
    return [rb[0] << 8 | rb[1], rb[2] << 8 | rb[3]]


def from_regs(regs, typ, order):
    if typ in ("INT", "UINT"):
        b = bytes([regs[0] >> 8, regs[0] & 255])
        if order in ("BADC", "DCBA"):
            b = b[::-1]
        return struct.unpack(">h" if typ == "INT" else ">H", b)[0]
    rb = bytes([regs[0] >> 8, regs[0] & 255, regs[1] >> 8, regs[1] & 255])
    p = PERM[order]
    vb = bytearray(4)
    for i in range(4):
        vb[p[i]] = rb[i]
    return struct.unpack({"DINT": ">i", "UDINT": ">I", "REAL": ">f"}[typ], bytes(vb))[0]


def jnum(v):
    """JSON cannot carry NaN or INF: send them as strings."""
    if isinstance(v, float):
        if math.isnan(v):
            return "NaN"
        if math.isinf(v):
            return "INF" if v > 0 else "-INF"
        return float("%.7g" % v)
    return v


# ----------------------------------------------------------------- simulator
class Sim:
    def __init__(self):
        self.lock = threading.RLock()
        self.sizes = {t: 10000 for t in TABLES}
        self.mem = {t: [0] * 65536 for t in TABLES}
        self.written = {t: {} for t in TABLES}  # addr -> time of last write by a client
        self.tags = []
        self.byname = {}
        self.gstate = {}
        self.faults = {"offline": False, "delay_ms": 0, "jitter_ms": 0, "drop_pct": 0, "exception": 0, "unit": 0}
        self.frames = collections.deque(maxlen=3000)
        self.fseq = 0
        self.samples = collections.deque(maxlen=int(600 / TICK))
        self.sseq = 0
        self.events = collections.deque(maxlen=500)
        self.eseq = 0
        self.clients = {}
        self.kick_gen = 0
        self.req_total = 0
        self.req_times = collections.deque(maxlen=5000)
        self.t0 = time.time()
        self.status = {"port": None, "listening": False, "error": "", "http": None}

    # ---- events
    def event(self, kind, text):
        with self.lock:
            self.eseq += 1
            self.events.append({"seq": self.eseq, "t": time.time(), "kind": kind, "text": text})

    # ---- tags
    def tag_regs(self, tag):
        return WORDS[tag["type"]]

    def read_tag(self, tag):
        t, a, typ = tag["table"], tag["addr"], tag["type"]
        m = self.mem[t]
        if typ == "BOOL":
            return 1 if m[a] else 0
        n = WORDS[typ]
        return from_regs(m[a:a + n], typ, tag["order"])

    def write_tag(self, tag, v):
        t, a, typ = tag["table"], tag["addr"], tag["type"]
        m = self.mem[t]
        if typ == "BOOL":
            m[a] = 1 if (v and v not in ("0", "false", "FALSE")) else 0
            return
        for i, r in enumerate(to_regs(v, typ, tag["order"])):
            m[a + i] = r

    def set_project(self, data, apply_init):
        errors = []
        tags = []
        names = set()
        raw = data.get("tags", [])
        if not isinstance(raw, list):
            return ["tags must be a list"]
        sizes = data.get("sizes") or {}
        for t in TABLES:
            try:
                s = int(sizes.get(t, self.sizes[t]))
                if 1 <= s <= 65536:
                    self.sizes[t] = s
            except (TypeError, ValueError):
                errors.append("size of %s ignored" % t)
        for i, r in enumerate(raw[:500]):
            try:
                tag = norm_tag(r, self.sizes)
            except ValueError as e:
                errors.append("tag %d (%s): %s" % (i + 1, (r or {}).get("name", "?") if isinstance(r, dict) else "?", e))
                continue
            if tag["name"].lower() in names:
                errors.append("tag %s: duplicate name, ignored" % tag["name"])
                continue
            names.add(tag["name"].lower())
            tags.append(tag)
        with self.lock:
            old = {t["id"]: t for t in self.tags}
            self.tags = tags
            self.byname = {t["name"].lower(): t for t in tags}
            for tag in tags:
                o = old.get(tag["id"])
                moved = (o is None or o["table"] != tag["table"] or o["addr"] != tag["addr"]
                         or o["type"] != tag["type"] or o["order"] != tag["order"])
                if o is None or o["gen"] != tag["gen"]:
                    self.gstate.pop(tag["id"], None)
                if apply_init or moved:
                    self.write_tag(tag, tag["init"])
        return errors

    # ---- generators
    def source(self, name):
        tag = self.byname.get(str(name).lower())
        if tag is None:
            return None
        return self.read_tag(tag)

    def tick(self, now, dt):
        with self.lock:
            el = now - self.t0
            for tag in self.tags:
                g = tag["gen"]
                k = g["kind"]
                if k == "manual":
                    continue
                st = self.gstate.setdefault(tag["id"], {})
                lo, hi = g.get("min", 0.0), g.get("max", 100.0)
                per = max(g.get("period", 10.0), 0.05)
                v = None
                if k == "ramp":
                    v = lo + (hi - lo) * ((el % per) / per)
                elif k == "sine":
                    v = (lo + hi) / 2 + (hi - lo) / 2 * math.sin(2 * math.pi * el / per)
                elif k == "square":
                    v = hi if (el % per) < per / 2 else lo
                elif k == "random":
                    if now >= st.get("next", 0):
                        st["v"] = random.uniform(lo, hi)
                        st["next"] = now + max(g.get("every", 1.0), 0.05)
                    v = st["v"]
                    if tag["type"] == "BOOL":
                        v = 1 if v >= (lo + hi) / 2 else 0
                elif k == "counter":
                    if "next" not in st:
                        st["next"] = now
                        st["v"] = self.read_tag(tag)
                    every = max(g.get("every", 1.0), 0.05)
                    while now >= st["next"]:
                        st["v"] = st["v"] + g.get("step", 1.0)
                        st["next"] += every
                    st["v"] = wrap_int(st["v"], tag["type"]) if tag["type"] not in ("REAL", "BOOL") else st["v"]
                    v = st["v"]
                    if tag["type"] == "BOOL":
                        v = int(st["v"]) & 1
                elif k == "follow":
                    s = self.source(g.get("src", ""))
                    if s is not None:
                        if g.get("invert"):
                            s = 0 if s else 1
                        h = st.setdefault("h", collections.deque())
                        h.append((now, s))
                        lim = now - max(g.get("delay", 0.0), 0.0)
                        while len(h) > 1 and h[1][0] <= lim:
                            h.popleft()
                        v = h[0][1] if h[0][0] <= lim else None
                elif k == "level":
                    if "v" not in st:
                        st["v"] = float(self.read_tag(tag))
                        if not math.isfinite(st["v"]):
                            st["v"] = lo
                    fill = self.source(g.get("src", ""))
                    drain = self.source(g.get("src2", ""))
                    rate = (g.get("up", 5.0) if fill else 0.0) - (g.get("down", 3.0) if drain else 0.0) - g.get("leak", 0.0)
                    st["v"] = min(max(st["v"] + rate * dt, lo), hi)
                    v = st["v"]
                elif k == "compare":
                    s = self.source(g.get("src", ""))
                    if s is not None and isinstance(s, (int, float)) and not (isinstance(s, float) and math.isnan(s)):
                        th, hy = g.get("value", 0.0), abs(g.get("hyst", 0.0))
                        on = st.get("on", False)
                        if g.get("op", ">") == ">":
                            on = s > th if not on else s > th - hy
                        else:
                            on = s < th if not on else s < th + hy
                        st["on"] = on
                        v = 1 if on else 0
                if v is not None:
                    self.write_tag(tag, v)
            self.sseq += 1
            self.samples.append({"seq": self.sseq, "t": now, "v": {t["id"]: jnum(self.read_tag(t)) for t in self.tags}})

    # ---- Modbus
    def process(self, uid, pdu, client):
        """Return (response pdu or None, status, note)."""
        f = self.faults
        if f["unit"] and uid != f["unit"]:
            return None, "ignored", "unit id %d, server answers only %d" % (uid, f["unit"])
        if f["drop_pct"] and random.uniform(0, 100) < f["drop_pct"]:
            return None, "dropped", "fault: no answer"
        fc = pdu[0]

        def exc(code, note=""):
            return bytes([(fc | 0x80) & 0xFF, code]), "exception", note

        if f["exception"]:
            return exc(f["exception"], "fault: forced exception")
        with self.lock:
            if fc in (1, 2, 3, 4):
                if len(pdu) != 5:
                    return exc(3, "bad length")
                addr, qty = struct.unpack(">HH", pdu[1:5])
                tbl = {1: "co", 2: "di", 3: "hr", 4: "ir"}[fc]
                lim = 2000 if fc <= 2 else 125
                if not 1 <= qty <= lim:
                    return exc(3, "quantity %d outside 1..%d" % (qty, lim))
                if addr + qty > self.sizes[tbl]:
                    return exc(2, "%s %d..%d beyond table size %d" % (tbl, addr, addr + qty - 1, self.sizes[tbl]))
                vals = self.mem[tbl][addr:addr + qty]
                if fc <= 2:
                    data = bytearray((qty + 7) // 8)
                    for i, b in enumerate(vals):
                        if b:
                            data[i >> 3] |= 1 << (i & 7)
                else:
                    data = b"".join(struct.pack(">H", r) for r in vals)
                return bytes([fc, len(data)]) + bytes(data), "ok", ""
            if fc in (5, 6):
                if len(pdu) != 5:
                    return exc(3, "bad length")
                addr, val = struct.unpack(">HH", pdu[1:5])
                tbl = "co" if fc == 5 else "hr"
                if fc == 5 and val not in (0, 0xFF00):
                    return exc(3, "coil value must be FF00 or 0000")
                if addr >= self.sizes[tbl]:
                    return exc(2, "%s %d beyond table size %d" % (tbl, addr, self.sizes[tbl]))
                self.mem[tbl][addr] = (1 if val else 0) if fc == 5 else val
                self.written[tbl][addr] = time.time()
                return bytes(pdu), "ok", ""
            if fc in (15, 16):
                if len(pdu) < 6:
                    return exc(3, "bad length")
                addr, qty, bc = struct.unpack(">HHB", pdu[1:6])
                tbl = "co" if fc == 15 else "hr"
                lim = 1968 if fc == 15 else 123
                need = (qty + 7) // 8 if fc == 15 else 2 * qty
                if not 1 <= qty <= lim or bc != need or len(pdu) != 6 + bc:
                    return exc(3, "quantity or byte count invalid")
                if addr + qty > self.sizes[tbl]:
                    return exc(2, "%s %d..%d beyond table size %d" % (tbl, addr, addr + qty - 1, self.sizes[tbl]))
                data = pdu[6:]
                now = time.time()
                for i in range(qty):
                    if fc == 15:
                        self.mem[tbl][addr + i] = (data[i >> 3] >> (i & 7)) & 1
                    else:
                        self.mem[tbl][addr + i] = data[2 * i] << 8 | data[2 * i + 1]
                    self.written[tbl][addr + i] = now
                return bytes([fc]) + pdu[1:5], "ok", ""
        return exc(1, "function code %d not supported" % fc)

    def log_frame(self, client, req, resp, status, note, ms):
        with self.lock:
            self.fseq += 1
            self.req_total += 1
            self.req_times.append(time.time())
            if client in self.clients:
                self.clients[client]["req"] += 1
            self.frames.append({"seq": self.fseq, "t": time.time(), "client": client, "req": req[:300].hex(),
                                "resp": resp[:300].hex() if resp else "", "status": status, "note": note,
                                "ms": round(ms, 1)})

    def state(self, q):
        def gi(k, d=0):
            try:
                return int(q.get(k, [d])[0])
            except (TypeError, ValueError):
                return d
        fs, ss, es = gi("f"), gi("s"), gi("e")
        tbl = q.get("tbl", ["hr"])[0]
        if tbl not in TABLES:
            tbl = "hr"
        start = min(max(gi("start"), 0), 65535)
        count = min(max(gi("count", 100), 0), 400)
        now = time.time()
        with self.lock:
            while self.req_times and self.req_times[0] < now - 2:
                self.req_times.popleft()
            frames = [x for x in self.frames if x["seq"] > fs][-500:]
            samples = [x for x in self.samples if x["seq"] > ss] if ss else list(self.samples)[-int(60 / TICK):]
            events = [x for x in self.events if x["seq"] > es]
            end = min(start + count, 65536)
            wr = self.written[tbl]
            return {
                "version": VERSION, "boot": self.t0,
                "status": dict(self.status, clients=[dict(v, key=k) for k, v in self.clients.items()],
                               req_total=self.req_total, rate=round(len(self.req_times) / 2, 1)),
                "faults": self.faults,
                "sizes": self.sizes,
                "tags": {t["id"]: jnum(self.read_tag(t)) for t in self.tags},
                "mem": {"tbl": tbl, "start": start, "vals": self.mem[tbl][start:end],
                        "recent": [a for a in range(start, end) if now - wr.get(a, 0) < 1.5]},
                "frames": frames, "samples": samples, "events": events,
                "fseq": self.fseq, "sseq": self.sseq, "eseq": self.eseq, "now": now,
            }


def fnum(d, k, default, lo=-1e30, hi=1e30):
    try:
        v = float(d.get(k, default))
    except (TypeError, ValueError):
        raise ValueError("%s is not a number" % k)
    if not math.isfinite(v) or not lo <= v <= hi:
        raise ValueError("%s out of range" % k)
    return v


def norm_tag(r, sizes):
    if not isinstance(r, dict):
        raise ValueError("not an object")
    name = str(r.get("name", "")).strip()
    if not name or len(name) > 40:
        raise ValueError("name empty or too long")
    tbl = r.get("table")
    if tbl not in TABLES:
        raise ValueError("unknown table")
    typ = r.get("type", "BOOL" if tbl in ("co", "di") else "INT")
    if typ not in WORDS:
        raise ValueError("unknown type")
    if (tbl in ("co", "di")) != (typ == "BOOL"):
        raise ValueError("BOOL only in coils and discrete inputs, and only BOOL there")
    order = r.get("order", "ABCD")
    if order not in ORDERS:
        raise ValueError("unknown word order")
    try:
        addr = int(r.get("addr", 0))
    except (TypeError, ValueError):
        raise ValueError("bad address")
    n = max(WORDS[typ], 1)
    if addr < 0 or addr + n > sizes[tbl]:
        raise ValueError("address outside the table (size %d)" % sizes[tbl])
    g = r.get("gen") or {}
    if not isinstance(g, dict):
        raise ValueError("bad generator")
    kind = g.get("kind", "manual")
    if kind not in GENS:
        raise ValueError("unknown generator")
    gen = {"kind": kind}
    for k, d in (("min", 0), ("max", 100), ("period", 10), ("every", 1), ("step", 1), ("delay", 0.5),
                 ("up", 5), ("down", 3), ("leak", 0), ("value", 50), ("hyst", 0)):
        if k in g:
            gen[k] = fnum(g, k, d)
    for k in ("src", "src2", "op"):
        if k in g:
            gen[k] = str(g[k])[:40]
    if "invert" in g:
        gen["invert"] = bool(g["invert"])
    init = r.get("init", 0)
    try:
        init = float(init)
        if not math.isfinite(init):
            init = 0.0
    except (TypeError, ValueError):
        init = 0.0
    return {"id": str(r.get("id", name))[:40], "name": name, "table": tbl, "addr": addr, "type": typ,
            "order": order, "gen": gen, "init": init}


SIM = Sim()


# ----------------------------------------------------------------- Modbus TCP server
class MBServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = os.name != "nt"  # on Windows this would let two programs share the port


class MBHandler(socketserver.BaseRequestHandler):
    def recv_exact(self, n, gen):
        buf = b""
        while len(buf) < n:
            if SIM.kick_gen != gen or SIM.faults["offline"]:
                return None
            try:
                chunk = self.request.recv(n - len(buf))
            except socket.timeout:
                continue
            except OSError:
                return None
            if not chunk:
                return None
            buf += chunk
        return buf

    def handle(self):
        key = "%s:%d" % self.client_address[:2]
        if SIM.faults["offline"]:
            SIM.event("warn", "Connection from %s refused (server offline)" % key)
            return
        gen = SIM.kick_gen
        self.request.settimeout(0.5)
        with SIM.lock:
            SIM.clients[key] = {"since": time.time(), "req": 0}
        SIM.event("info", "Client %s connected" % key)
        why = "closed by the client"
        try:
            while True:
                hdr = self.recv_exact(7, gen)
                if hdr is None:
                    break
                t0 = time.time()
                tid, pid, length, uid = struct.unpack(">HHHB", hdr)
                if pid != 0 or not 2 <= length <= 254:
                    SIM.log_frame(key, hdr, b"", "invalid", "bad MBAP header (protocol %d, length %d)" % (pid, length), 0)
                    why = "invalid frame"
                    break
                pdu = self.recv_exact(length - 1, gen)
                if pdu is None:
                    break
                resp, status, note = SIM.process(uid, pdu, key)
                f = SIM.faults
                delay = f["delay_ms"] + random.uniform(0, f["jitter_ms"])
                if delay > 0:
                    time.sleep(delay / 1000.0)
                adu = b""
                if resp is not None:
                    adu = struct.pack(">HHHB", tid, 0, len(resp) + 1, uid) + resp
                    try:
                        self.request.sendall(adu)
                    except OSError:
                        why = "send failed"
                        SIM.log_frame(key, hdr + pdu, adu, status, note, (time.time() - t0) * 1000)
                        break
                SIM.log_frame(key, hdr + pdu, adu, status, note, (time.time() - t0) * 1000)
            if SIM.kick_gen != gen:
                why = "closed by the simulator"
            elif SIM.faults["offline"]:
                why = "server set offline"
        finally:
            with SIM.lock:
                SIM.clients.pop(key, None)
            SIM.event("info", "Client %s disconnected (%s)" % (key, why))


# ----------------------------------------------------------------- test client
def test_client(p):
    host = str(p.get("host", "127.0.0.1")).strip() or "127.0.0.1"
    port = int(p.get("port", SIM.status["port"] or 502))
    unit = int(p.get("unit", 1)) & 255
    fc = int(p.get("fc", 3))
    addr = int(p.get("addr", 0))
    qty = int(p.get("qty", 1))
    vals = [int(v) for v in (p.get("values") or [])]
    if not 0 <= addr <= 65535 or not 0 <= qty <= 65535 or not 1 <= port <= 65535:
        raise ValueError("address, quantity or port out of range")
    if fc in (1, 2, 3, 4):
        pdu = struct.pack(">BHH", fc, addr, qty)
    elif fc == 5:
        pdu = struct.pack(">BHH", fc, addr, 0xFF00 if (vals and vals[0]) else 0)
    elif fc == 6:
        pdu = struct.pack(">BHH", fc, addr, (vals[0] if vals else 0) & 0xFFFF)
    elif fc == 15:
        bits = (vals + [0] * qty)[:qty]
        data = bytearray((qty + 7) // 8)
        for i, b in enumerate(bits):
            if b:
                data[i >> 3] |= 1 << (i & 7)
        pdu = struct.pack(">BHHB", fc, addr, qty, len(data)) + bytes(data)
    elif fc == 16:
        regs = (vals + [0] * qty)[:qty]
        pdu = struct.pack(">BHHB", fc, addr, qty, 2 * qty) + b"".join(struct.pack(">H", r & 0xFFFF) for r in regs)
    else:
        raise ValueError("function code not supported by the test client")
    test_client.tid = (getattr(test_client, "tid", 0) + 1) & 0xFFFF
    adu = struct.pack(">HHHB", test_client.tid, 0, len(pdu) + 1, unit) + pdu
    t0 = time.time()
    out = {"req": adu.hex(), "resp": "", "ms": 0, "error": ""}
    try:
        with socket.create_connection((host, port), timeout=2) as s:
            s.settimeout(float(p.get("timeout", 1.0)))
            s.sendall(adu)
            buf = b""
            while len(buf) < 7:
                c = s.recv(260)
                if not c:
                    break
                buf += c
            if len(buf) >= 6:
                ln = struct.unpack(">H", buf[4:6])[0]
                while len(buf) < 6 + ln:
                    c = s.recv(260)
                    if not c:
                        break
                    buf += c
            out["resp"] = buf.hex()
            if not buf:
                out["error"] = "connection closed without answer"
    except socket.timeout:
        out["error"] = "timeout: no answer"
    except OSError as e:
        out["error"] = "connection failed: %s" % e
    out["ms"] = round((time.time() - t0) * 1000, 1)
    return out


# ----------------------------------------------------------------- web server
class Web(BaseHTTPRequestHandler):
    server_version = "ComToolbox/" + VERSION

    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, allow_nan=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html", "/Com_Toolbox.html"):
            try:
                with open(PAGE, "rb") as fh:
                    self.send(200, fh.read(), "text/html")
            except OSError:
                self.send(404, "Com_Toolbox.html not found next to com_toolbox.py", "text/plain")
        elif u.path == "/api/state":
            self.send(200, SIM.state(parse_qs(u.query)))
        else:
            self.send(404, "not found", "text/plain")

    def do_POST(self):
        u = urlparse(self.path)
        # the page is the only expected caller: refuse requests from other sites
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and origin.split("//")[-1] != host:
            return self.send(403, {"error": "forbidden origin"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            p = json.loads(self.rfile.read(n) or b"{}") if n else {}
            if not isinstance(p, dict):
                raise ValueError("JSON object expected")
        except (ValueError, OSError) as e:
            return self.send(400, {"error": "bad request: %s" % e})
        try:
            if u.path == "/api/project":
                errs = SIM.set_project(p, bool(p.get("apply_init")))
                return self.send(200, {"ok": True, "errors": errs})
            if u.path == "/api/set":
                with SIM.lock:
                    if "id" in p:
                        tag = next((t for t in SIM.tags if t["id"] == p["id"]), None)
                        if tag is None:
                            return self.send(404, {"error": "unknown tag"})
                        SIM.write_tag(tag, p.get("value", 0))
                        st = SIM.gstate.get(tag["id"])
                        if st is not None and "v" in st:
                            st["v"] = SIM.read_tag(tag)
                    else:
                        t, a, v = p.get("tbl"), int(p.get("addr", -1)), int(p.get("value", 0))
                        if t not in TABLES or not 0 <= a < 65536:
                            return self.send(400, {"error": "bad address"})
                        SIM.mem[t][a] = (1 if v else 0) if t in ("co", "di") else v & 0xFFFF
                return self.send(200, {"ok": True})
            if u.path == "/api/faults":
                f = dict(SIM.faults)
                f["offline"] = bool(p.get("offline", f["offline"]))
                for k, hi in (("delay_ms", 10000), ("jitter_ms", 10000), ("drop_pct", 100)):
                    f[k] = min(max(float(p.get(k, f[k])), 0), hi)
                ex = int(p.get("exception", f["exception"]))
                f["exception"] = ex if ex in (0, 1, 2, 3, 4, 6) else 0
                un = int(p.get("unit", f["unit"]))
                f["unit"] = un if 0 <= un <= 255 else 0
                changes = [k for k in f if f[k] != SIM.faults[k]]
                SIM.faults = f
                if changes:
                    SIM.event("fault", "Faults: " + ", ".join("%s=%s" % (k, f[k]) for k in changes))
                return self.send(200, {"ok": True, "faults": f})
            if u.path == "/api/kick":
                SIM.kick_gen += 1
                SIM.event("warn", "All connections closed by the simulator")
                return self.send(200, {"ok": True})
            if u.path == "/api/reset_memory":
                with SIM.lock:
                    for t in TABLES:
                        SIM.mem[t] = [0] * 65536
                        SIM.written[t] = {}
                    SIM.gstate = {}
                    for tag in SIM.tags:
                        if tag["gen"]["kind"] == "manual":
                            SIM.write_tag(tag, tag["init"])
                SIM.event("info", "Memory reset")
                return self.send(200, {"ok": True})
            if u.path == "/api/clear":
                with SIM.lock:
                    SIM.frames.clear()
                    SIM.events.clear()
                return self.send(200, {"ok": True})
            if u.path == "/api/client":
                return self.send(200, test_client(p))
        except (ValueError, TypeError) as e:
            return self.send(400, {"error": str(e)})
        self.send(404, {"error": "not found"})


# ----------------------------------------------------------------- main
def local_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet is sent
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    ips.discard("0.0.0.0")
    return sorted(ips, key=lambda x: (x.startswith("127."), x))


def ticker():
    last = time.time()
    while True:
        time.sleep(TICK)
        now = time.time()
        try:
            SIM.tick(now, min(now - last, 1.0))
        except Exception as e:  # never let the generators stop the server
            SIM.event("error", "Generator error: %s" % e)
        last = now


def main():
    ap = argparse.ArgumentParser(description="Com Toolbox v%s - Modbus TCP simulator" % VERSION)
    ap.add_argument("--port", type=int, default=502, help="Modbus TCP port (default 502, falls back to 1502)")
    ap.add_argument("--web", type=int, default=8502, help="port of the web page (default 8502)")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    a = ap.parse_args()

    mb = None
    for port in [a.port] + ([1502] if a.port == 502 else []):
        try:
            mb = MBServer(("0.0.0.0", port), MBHandler)
            break
        except OSError as e:
            SIM.status["error"] = "port %d: %s" % (port, e)
            print("Modbus TCP: cannot open port %d (%s)" % (port, e))
    if mb:
        SIM.status.update(port=mb.server_address[1], listening=True, error="" if mb.server_address[1] == a.port else SIM.status["error"])
        threading.Thread(target=mb.serve_forever, daemon=True).start()
    web = None
    for port in range(a.web, a.web + 10):
        try:
            web = ThreadingHTTPServer(("127.0.0.1", port), Web)
            web.daemon_threads = True
            break
        except OSError:
            continue
    if web is None:
        print("No free port for the web page (%d..%d)." % (a.web, a.web + 9))
        sys.exit(1)
    SIM.status["http"] = web.server_address[1]
    SIM.status["ips"] = local_ips()
    threading.Thread(target=ticker, daemon=True).start()
    url = "http://127.0.0.1:%d/" % web.server_address[1]
    print("=" * 60)
    print(" Com Toolbox v%s - Modbus TCP simulator" % VERSION)
    if mb:
        print(" Modbus TCP server listening on port %d" % SIM.status["port"])
        print(" Point your PLC (Modbus TCP client) to one of: %s" % ", ".join(SIM.status["ips"]))
    print(" Interface: %s" % url)
    print(" Stop: Ctrl+C or close this window")
    print("=" * 60)
    SIM.event("info", "Simulator started" + (", Modbus TCP on port %d" % SIM.status["port"] if mb else ", Modbus TCP not available"))
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        web.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
