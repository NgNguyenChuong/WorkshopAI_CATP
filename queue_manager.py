"""Hang doi tai file cho Model Hub.

Gioi han so nguoi tai dong thoi. Nguoi den sau xep hang va poll trang thai.
Thread-safe, khong phu thuoc Flask - chi dung threading + time.
"""

import secrets
import threading
import time
from collections import OrderedDict


# So nguoi duoc tai cung luc. 8-12 la vung hop ly cho 1 AP Wi-Fi.
MAX_CONCURRENT = 40

# Ticket khong poll qua ngan nay giay -> coi nhu da bo di, thu hoi slot.
HEARTBEAT_TIMEOUT = 30

# Ket noi tai bi dut -> giu slot them ngan nay giay de client resume.
RESUME_GRACE = 60


class Ticket:
    __slots__ = ("id", "owner_id", "state", "last_seen", "grace_until", "downloading")

    def __init__(self, owner_id):
        self.id = secrets.token_urlsafe(16)
        self.owner_id = owner_id
        self.state = "waiting"  # waiting | ready
        self.last_seen = time.time()
        self.grace_until = 0.0
        self.downloading = False


class DownloadQueue:
    def __init__(self, max_concurrent=MAX_CONCURRENT):
        self.max_concurrent = max_concurrent
        self._lock = threading.Lock()
        self._tickets = OrderedDict()  # thu tu insert = thu tu xep hang
        self._active = set()

    # ------------------------------------------------------------------
    # Noi bo - chi goi khi dang giu _lock
    # ------------------------------------------------------------------

    def _drop(self, ticket_id):
        self._tickets.pop(ticket_id, None)
        self._active.discard(ticket_id)

    def _sweep(self):
        """Loai bo ticket ma: dong tab luc dang cho, hoac dut ket noi qua lau."""
        now = time.time()
        for ticket_id, ticket in list(self._tickets.items()):
            if ticket.downloading:
                continue
            if now - ticket.last_seen <= HEARTBEAT_TIMEOUT:
                continue
            if now < ticket.grace_until:
                continue
            self._drop(ticket_id)

    def _promote(self):
        """Day nguoi dau hang doi len slot trong."""
        if len(self._active) >= self.max_concurrent:
            return
        for ticket in self._tickets.values():
            if len(self._active) >= self.max_concurrent:
                break
            if ticket.state == "waiting":
                ticket.state = "ready"
                self._active.add(ticket.id)

    def _position(self, ticket):
        if ticket.state == "ready":
            return 0
        position = 0
        for other in self._tickets.values():
            if other.state == "waiting":
                position += 1
                if other.id == ticket.id:
                    return position
        return position

    def _snapshot(self, ticket):
        return {
            "ticket": ticket.id,
            "ready": ticket.state == "ready",
            "downloading": ticket.downloading,
            "position": self._position(ticket),
            "active": len(self._active),
            "waiting": sum(1 for t in self._tickets.values() if t.state == "waiting"),
            "slots": self.max_concurrent,
        }

    # ------------------------------------------------------------------
    # API cong khai
    # ------------------------------------------------------------------

    def join(self, owner_id):
        """Lay ticket. Moi browser client giu mot ticket on dinh khi reload."""
        with self._lock:
            self._sweep()
            for ticket in self._tickets.values():
                if ticket.owner_id == owner_id:
                    ticket.last_seen = time.time()
                    self._promote()
                    return self._snapshot(ticket)

            ticket = Ticket(owner_id)
            self._tickets[ticket.id] = ticket
            self._promote()
            return self._snapshot(ticket)

    def status(self, ticket_id):
        """Vua tra trang thai vua lam heartbeat. Client poll moi 3 giay."""
        with self._lock:
            self._sweep()
            ticket = self._tickets.get(ticket_id)
            if ticket is None:
                return {"expired": True, "ready": False, "position": 0}
            ticket.last_seen = time.time()
            self._promote()
            return self._snapshot(ticket)

    def begin_download(self, ticket_id):
        """True neu duoc phep bat dau tai. Chan 1 ticket mo nhieu ket noi."""
        with self._lock:
            self._sweep()
            ticket = self._tickets.get(ticket_id)
            if ticket is None or ticket.state != "ready" or ticket.downloading:
                return False
            ticket.downloading = True
            ticket.grace_until = 0.0
            ticket.last_seen = time.time()
            return True

    def finish_download(self, ticket_id, complete):
        """Goi khi response dong lai - du tai xong hay client ngat giua chung."""
        with self._lock:
            ticket = self._tickets.get(ticket_id)
            if ticket is None:
                self._promote()
                return
            ticket.downloading = False
            ticket.last_seen = time.time()
            if complete:
                self._drop(ticket_id)
            else:
                ticket.grace_until = time.time() + RESUME_GRACE
            self._promote()

    def leave(self, ticket_id):
        with self._lock:
            ticket = self._tickets.get(ticket_id)
            if ticket is not None and ticket.downloading:
                return False
            self._drop(ticket_id)
            self._promote()
            return ticket is not None

    def stats(self):
        with self._lock:
            self._sweep()
            return {
                "active": len(self._active),
                "waiting": sum(1 for t in self._tickets.values() if t.state == "waiting"),
                "slots": self.max_concurrent,
            }
