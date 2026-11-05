"""Camera scanner engine: OpenCV for capture, Pyzbar for barcode decoding."""
import threading
import time

import cv2
import numpy as np

try:
    from pyzbar import pyzbar
except Exception:  # pyzbar or the zbar library is missing
    pyzbar = None


def decode_frame(frame):
    """Return list of (text, type, rect) found in a BGR frame."""
    if pyzbar is None:
        return []
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    out = []
    for b in pyzbar.decode(gray):
        out.append((b.data.decode("utf-8", "ignore"), b.type, b.rect))
    return out


def decode_image_bytes(data):
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    return [] if img is None else [c[0] for c in decode_frame(img)]


def placeholder(text):
    img = np.full((480, 640, 3), 30, np.uint8)
    cv2.putText(img, text, (40, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    ok, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


class Scanner:
    def __init__(self, camera_index=0, cooldown=2.0):
        self.camera_index = camera_index
        self.cooldown = cooldown
        self.running = False
        self.error = None
        self._thread = None
        self._frame = placeholder("Scanner stopped")
        self._events = []
        self._next_id = 1
        self._last_seen = {}
        self._lock = threading.Lock()

    def start(self):
        if self.running:
            return
        if pyzbar is None:
            self.error = "pyzbar / zbar not installed"
            self._frame = placeholder("pyzbar not available")
            return
        self.error = None
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)
        self._frame = placeholder("Scanner stopped")

    def _loop(self):
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            self.error = f"Cannot open camera {self.camera_index}"
            self._frame = placeholder("Camera not found")
            self.running = False
            return
        n = 0
        while self.running:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            n += 1
            if n % 2 == 0:  # decode every 2nd frame to save CPU
                for text, kind, r in decode_frame(frame):
                    cv2.rectangle(frame, (r.left, r.top), (r.left + r.width, r.top + r.height), (0, 212, 255), 3)
                    cv2.putText(frame, text, (r.left, max(r.top - 8, 15)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 212, 255), 2)
                    self._register(text, kind)
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                self._frame = buf.tobytes()
        cap.release()

    def _register(self, code, kind):
        now = time.time()
        if now - self._last_seen.get(code, 0) < self.cooldown:
            self._last_seen[code] = now
            return
        self._last_seen[code] = now
        self.push(code, kind)

    def push(self, code, kind="MANUAL"):
        with self._lock:
            self._events.append({"id": self._next_id, "barcode": code, "type": kind, "time": time.time()})
            self._next_id += 1
            self._events = self._events[-50:]

    def events_since(self, since):
        with self._lock:
            last = self._next_id - 1
            if since is None:
                return last, []
            return last, [e for e in self._events if e["id"] > since]

    def mjpeg(self):
        while True:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + self._frame + b"\r\n")
            time.sleep(0.04)


scanner = Scanner()
