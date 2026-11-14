#!/usr/bin/env python3
"""The viewer's server. Standard library only -- no pip install, nothing to break on stage.

    python3 viz/server.py                 # http://127.0.0.1:8765
    python3 viz/server.py --host 0.0.0.0  # reachable from the room (prints the LAN URL)
    python3 viz/server.py --port 9000

Routes
    GET  /                         the viewer
    GET  /api/catalog              every design: sequences, mutations, scores, improvement
    GET  /api/design/<id>          one design
    GET  /api/structure/<id>       its co-fold mmCIF (text/plain, for 3Dmol)
    GET  /api/baseline/structure   1N8Z, the trastuzumab-HER2 crystal
    GET  /api/lanes                which inference lanes can run right now
    GET  /api/overview             what the project produced: axes, stages, every artifact
    GET  /api/price?model&n        what a run would cost, starts nothing
    GET  /api/jobs                 recent JapanFold jobs on this key, live (reads, no spend)
    GET  /api/job/<id>             one job's live status, for the progress panel
    POST /api/predict              {heavy, light, lane, design_id, mode, model}

Only POST /api/predict can spend money, only on lane=japanfold or lane=vm, and only when
the request carries confirm=true. Loading the page bills nothing: everything the viewer
shows on arrival is read from files the pipeline already wrote.
"""

from __future__ import annotations

import argparse
import http.server
import json
import pathlib
import socket
import socketserver
import sys
import threading
import traceback
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import backends as B          # noqa: E402
import catalog as C           # noqa: E402

STATIC = HERE / "static"
_lock = threading.Lock()
_cache: dict = {}


def catalog(refresh: bool = False) -> dict:
    """Cached, because every page load would otherwise re-measure 18 mmCIFs."""
    with _lock:
        if refresh or "catalog" not in _cache:
            _cache["catalog"] = C.load_catalog()
        return _cache["catalog"]


class Handler(http.server.SimpleHTTPRequestHandler):
    server_version = "her2-viewer/1.0"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STATIC), **kw)

    # quieter log: one line, no noise about favicons
    def log_message(self, fmt, *args):
        if "favicon" in (args[0] if args else ""):
            return
        sys.stderr.write(f"  {self.address_string()} {fmt % args}\n")

    # -- helpers ----------------------------------------------------------
    def _send(self, code: int, payload, content_type="application/json"):
        if not isinstance(payload, (bytes, bytearray)):
            payload = json.dumps(payload, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _fail(self, code: int, msg: str, **extra):
        self._send(code, {"error": msg, **extra})

    # -- GET --------------------------------------------------------------
    def do_GET(self):                                          # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        q = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/api/catalog":
                return self._send(200, catalog(refresh="refresh" in q))

            if path == "/api/lanes":
                return self._send(200, B.lane_status())

            if path == "/api/overview":
                # Read-only pass over the repo: no network, nothing billed, so it is safe
                # to leave open on a projector and refresh whenever.
                import overview as O
                return self._send(200, O.build())

            if path == "/api/jobs":
                # Live, but read-only: listing jobs starts nothing and bills nothing.
                import japanfold as J
                try:
                    return self._send(200, {"jobs": J.jobs(
                        int((q.get("limit") or ["10"])[0]))})
                except J.JapanFoldError as exc:
                    return self._fail(502, str(exc))

            if path.startswith("/api/job/"):
                import japanfold as J
                jid = urllib.parse.unquote(path.split("/api/job/", 1)[1])
                try:
                    # wait=0: answer now. The browser polls; it must never hold a socket
                    # open for a minute, which is what the CLI's ?wait=60 is for.
                    return self._send(200, J.job(jid))
                except J.JapanFoldError as exc:
                    return self._fail(502, str(exc))

            if path == "/api/price":
                model = (q.get("model") or ["af2ig"])[0]
                n = int((q.get("n") or ["1"])[0])
                import japanfold as J
                return self._send(200, J.price(model, n))

            if path.startswith("/api/design/"):
                did = urllib.parse.unquote(path.split("/api/design/", 1)[1])
                for d in catalog()["designs"]:
                    if d["design_id"] == did:
                        return self._send(200, d)
                return self._fail(404, f"no design {did!r}")

            if path.startswith("/api/structure/"):
                did = urllib.parse.unquote(path.split("/api/structure/", 1)[1])
                cif = B._cofold_index().get(did)
                if cif is None:
                    # A JapanFold fold may have landed under results/japanfold/.
                    import japanfold as J
                    for cand in sorted(J.OUT_ROOT.glob(f"*/{did}/model.cif")):
                        cif = cand
                        break
                if cif is None:
                    return self._fail(404, f"no structure for {did!r}",
                                      hint="fold it first (lane=japanfold, mode=fold)")
                return self._send(200, pathlib.Path(cif).read_bytes(),
                                  "chemical/x-mmcif")

            if path == "/api/baseline/structure":
                pdb = B.REPO / "data" / "target" / "1n8z.pdb"
                if not pdb.is_file():
                    return self._fail(404, "1n8z.pdb missing")
                return self._send(200, pdb.read_bytes(), "chemical/x-pdb")

            if path in ("/", "/index.html"):
                self.path = "/index.html"
            return super().do_GET()
        except BrokenPipeError:
            return None
        except Exception as exc:                               # noqa: BLE001
            traceback.print_exc()
            return self._fail(500, f"{type(exc).__name__}: {exc}")

    # -- POST -------------------------------------------------------------
    def do_POST(self):                                         # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/predict":
            return self._fail(404, "no such endpoint")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError) as exc:
            return self._fail(400, f"bad JSON: {exc}")

        lane = body.get("lane", "dummy")
        design_id = body.get("design_id")
        heavy = (body.get("heavy") or "").strip()
        light = (body.get("light") or "").strip()

        # Fill the sequences in from the catalog when only an id was given.
        if not heavy and design_id:
            for d in catalog()["designs"]:
                if d["design_id"] == design_id:
                    heavy, light = d["heavy"], d["light"]
                    break
        if not heavy:
            return self._fail(400, "heavy sequence or a known design_id is required")

        # Spending gate. The dummy lane is free; the others bill, so they need consent
        # carried on the request itself -- not a server-side default someone forgot.
        billed = lane in ("japanfold", "vm", "nebius")
        if billed and not body.get("confirm"):
            info = {"error": "this lane starts a billed job; resend with confirm=true",
                    "lane": lane}
            if lane == "japanfold":
                try:
                    import japanfold as J
                    info["price"] = J.price("af2ig" if body.get("mode", "af2ig") == "af2ig"
                                            else body.get("model", "openfold3"), 1)
                except Exception as exc:                       # noqa: BLE001
                    info["price_error"] = str(exc)
            return self._send(402, info)

        kw = {}
        if lane == "japanfold":
            kw = {"mode": body.get("mode", "af2ig"),
                  "model": body.get("model", "openfold3"),
                  "epitope_guidance": bool(body.get("epitope_guidance"))}
        try:
            out = B.predict(heavy, light, lane=lane, design_id=design_id, **kw)
        except ValueError as exc:
            return self._fail(400, str(exc))
        except Exception as exc:                               # noqa: BLE001
            traceback.print_exc()
            return self._fail(500, f"{type(exc).__name__}: {exc}")

        if out.get("lane") == "japanfold":
            with _lock:
                _cache.pop("catalog", None)     # new scores: let the catalog rebuild
        return self._send(200, out)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def lan_ip() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1",
                    help="0.0.0.0 to let others in the room open it")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()

    try:
        cat = catalog()
    except SystemExit as exc:
        print(f"cannot build the catalog: {exc}", file=sys.stderr)
        return 2

    b = cat["baseline"]
    print(f"\n  HER2 design viewer")
    print(f"  {cat['source']['n_designs']} designs, "
          f"{cat['source']['n_with_structure']} with a structure")
    if b.get("available"):
        print(f"  baseline: trastuzumab VH on 1N8Z touches {b['n_epitope_hit']}"
              f"/{len(cat['target']['epitope_residues'])} epitope residues")
    for ln in B.lane_status():
        print(f"  [{'x' if ln['ready'] else ' '}] {ln['lane']:<10} {ln['detail'][:90]}")

    print(f"\n  ->  http://{'127.0.0.1' if a.host in ('0.0.0.0', '') else a.host}:{a.port}")
    if a.host == "0.0.0.0":
        ip = lan_ip()
        if ip:
            print(f"  ->  http://{ip}:{a.port}   (same wifi)")
    print("\n  ctrl-c to stop\n")

    with Server((a.host, a.port), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
