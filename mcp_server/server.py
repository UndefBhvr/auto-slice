#!/usr/bin/env python3
"""
MCP Server for managing emotional segments.
Maintains a list of identified segments and provides CRUD operations.
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime


@dataclass
class Segment:
    id: str
    start: float
    end: float
    summary: str
    title: str
    created_at: str
    selected: bool = False

    def to_dict(self):
        return asdict(self)


class SegmentStore:
    def __init__(self):
        self._segments: list[Segment] = []
        self._lock = threading.Lock()
        self._id_counter = 0

    def add_segment(self, start: float, end: float, summary: str, title: str) -> Segment:
        # Ensure all strings are proper unicode
        if isinstance(summary, bytes):
            summary = summary.decode('utf-8', errors='replace')
        if isinstance(title, bytes):
            title = title.decode('utf-8', errors='replace')

        with self._lock:
            self._id_counter += 1
            segment = Segment(
                id=f"seg_{self._id_counter}_{int(datetime.now().timestamp())}",
                start=float(start),
                end=float(end),
                summary=str(summary),
                title=str(title),
                created_at=datetime.now().isoformat(),
                selected=False
            )
            self._segments.append(segment)
            return segment

    def add_segments_batch(self, segments: list[dict]) -> list[Segment]:
        with self._lock:
            results = []
            for seg in segments:
                self._id_counter += 1
                # Ensure proper encoding
                summary = seg.get("summary", "")
                title = seg.get("title", "")
                if isinstance(summary, bytes):
                    summary = summary.decode('utf-8', errors='replace')
                if isinstance(title, bytes):
                    title = title.decode('utf-8', errors='replace')

                segment = Segment(
                    id=f"seg_{self._id_counter}_{int(datetime.now().timestamp())}",
                    start=float(seg.get("start", 0)),
                    end=float(seg.get("end", 0)),
                    summary=str(summary),
                    title=str(title),
                    created_at=datetime.now().isoformat(),
                    selected=False
                )
                self._segments.append(segment)
                results.append(segment)
            return results

    def get_all_segments(self) -> list[Segment]:
        with self._lock:
            return list(self._segments)

    def get_selected_segments(self) -> list[Segment]:
        with self._lock:
            return [s for s in self._segments if s.selected]

    def set_selections_by_indices(self, indices: set[int]):
        """Set selection status by list indices."""
        with self._lock:
            for i, seg in enumerate(self._segments):
                seg.selected = (i in indices)

    def toggle_selection(self, segment_id: str) -> Optional[Segment]:
        with self._lock:
            for seg in self._segments:
                if seg.id == segment_id:
                    seg.selected = not seg.selected
                    return seg
            return None

    def update_segment(self, segment_id: str, **kwargs) -> Optional[Segment]:
        with self._lock:
            for seg in self._segments:
                if seg.id == segment_id:
                    for key, value in kwargs.items():
                        if hasattr(seg, key):
                            setattr(seg, key, value)
                    return seg
            return None

    def delete_segment(self, segment_id: str) -> bool:
        with self._lock:
            for i, seg in enumerate(self._segments):
                if seg.id == segment_id:
                    self._segments.pop(i)
                    return True
            return False

    def clear_all(self):
        with self._lock:
            self._segments.clear()


class MCPRequestHandler(BaseHTTPRequestHandler):
    store = None  # Will be set externally

    def _send_json(self, status: int, data: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/segments":
            selected_only = query.get("selected", ["false"])[0] == "true"
            segments = self.store.get_selected_segments() if selected_only else self.store.get_all_segments()
            self._send_json(200, {"segments": [s.to_dict() for s in segments]})

        elif path == "/health":
            self._send_json(200, {"status": "ok"})

        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else "{}"
        data = json.loads(body) if body else {}

        if path == "/segments":
            segment = self.store.add_segment(
                start=data["start"],
                end=data["end"],
                summary=data["summary"],
                title=data["title"]
            )
            self._send_json(201, {"segment": segment.to_dict()})

        elif path == "/segments/batch":
            segments = self.store.add_segments_batch(data.get("segments", []))
            self._send_json(201, {"segments": [s.to_dict() for s in segments]})

        elif path == "/segments/clear":
            self.store.clear_all()
            self._send_json(200, {"status": "cleared"})

        elif path == "/submit":
            # Submit selected segments to UI (triggers UI update)
            selected = self.store.get_selected_segments()
            self._send_json(200, {
                "submitted": True,
                "count": len(selected),
                "segments": [s.to_dict() for s in selected]
            })

        else:
            self._send_json(404, {"error": "Not found"})

    def do_PATCH(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else "{}"
        data = json.loads(body) if body else {}

        segment_id = query.get("id", [None])[0]

        if path == "/segments/toggle" and segment_id:
            segment = self.store.toggle_selection(segment_id)
            if segment:
                self._send_json(200, {"segment": segment.to_dict()})
            else:
                self._send_json(404, {"error": "Segment not found"})

        elif path == "/segments" and segment_id:
            segment = self.store.update_segment(segment_id, **data)
            if segment:
                self._send_json(200, {"segment": segment.to_dict()})
            else:
                self._send_json(404, {"error": "Segment not found"})

        else:
            self._send_json(404, {"error": "Not found"})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        segment_id = query.get("id", [None])[0]

        if path == "/segments" and segment_id:
            deleted = self.store.delete_segment(segment_id)
            if deleted:
                self._send_json(200, {"status": "deleted"})
            else:
                self._send_json(404, {"error": "Segment not found"})
        else:
            self._send_json(404, {"error": "Not found"})

    def log_message(self, format, *args):
        print(f"[MCP Server] {args[0]}")


def run_server(host: str = "127.0.0.1", port: int = 8765):
    store = SegmentStore()
    MCPRequestHandler.store = store

    server = HTTPServer((host, port), MCPRequestHandler)
    print(f"[MCP Server] Running on http://{host}:{port}")
    print("[MCP Server] Endpoints:")
    print("  GET  /segments          - List all segments")
    print("  GET  /segments?selected=true - List selected segments")
    print("  POST /segments          - Add a single segment")
    print("  POST /segments/batch    - Add multiple segments")
    print("  POST /segments/clear    - Clear all segments")
    print("  POST /submit            - Submit selected segments")
    print("  PATCH /segments?id=xxx  - Update segment")
    print("  PATCH /segments/toggle?id=xxx - Toggle segment selection")
    print("  DELETE /segments?id=xxx - Delete segment")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[MCP Server] Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    run_server()