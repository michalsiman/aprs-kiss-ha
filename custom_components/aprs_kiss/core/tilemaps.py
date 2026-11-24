"""Map files the user imports for the offline map: a better (topographic, …) map than the bundled one.

Raster tile maps in open formats, from wherever the user gets them (made with MOBAC, QGIS, GDAL,
MapTiler, bought, …):

- MBTiles (.mbtiles): tiles in an SQLite file, the most common one;
- PMTiles (.pmtiles): tiles in one plain file, version 3;
- SQLiteDB (.sqlitedb): the RMaps format used by OsmAnd and Locus;
- a ZIP of tile pictures, z/x/y.png (osmdroid / MOBAC "OSMdroid ZIP", any folder above z is fine),
  and the same as a folder (what a 7z of tiles becomes once unpacked).

The pictures can be PNG, JPEG or WebP. Vector tiles (vector MBTiles/PMTiles, Mapsforge .map) are not
supported: they need a renderer the app does not have.

The map library loads tiles from an address, so a small web server on 127.0.0.1 hands them out; it
only reads from the files and is reachable from this device only.
"""

from __future__ import annotations

import contextlib
import gzip
import logging
import math
import re
import shutil
import sqlite3
import struct
import subprocess
import threading
import zipfile
import zlib
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

MAP_SUFFIXES = (".mbtiles", ".pmtiles", ".sqlitedb")
ARCHIVE_SUFFIXES = (".zip", ".7z")
PICTURE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}


class MapError(Exception):
    """A file that is not a map the app can show; the message says why (in English, for the log)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code  # "vector", "unknown", "empty", "no7z", "read"


def sniff(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


@dataclass
class TileSource:
    path: Path
    name: str = ""
    fmt: str = "png"
    min_zoom: int = 0
    max_zoom: int = 18
    bounds: tuple[float, float, float, float] | None = None  # west, south, east, north
    attribution: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def tile(self, z: int, x: int, y: int) -> bytes | None:
        raise NotImplementedError

    def close(self) -> None:
        pass

    def describe(self) -> str:
        return f"{self.name or self.path.name} (zoom {self.min_zoom}–{self.max_zoom})"


def _bounds(text: str | None) -> tuple[float, float, float, float] | None:
    try:
        w, s, e, n = (float(v) for v in str(text).split(","))
    except (TypeError, ValueError):
        return None
    if -180 <= w < e <= 180 and -90 <= s < n <= 90:
        return w, s, e, n
    return None


def _check_format(fmt: str | None, sample: bytes | None) -> str:
    fmt = (fmt or "").lower().strip()
    if fmt in ("pbf", "mvt", "vector"):
        raise MapError("vector")
    if fmt in MIME:
        return "jpg" if fmt == "jpeg" else fmt
    found = sniff(sample or b"")
    if found:
        return found
    if sample and (sample[:2] == b"\x1f\x8b" or sample[:1] == b"\x1a"):
        raise MapError("vector")  # gzipped protobuf: vector tiles
    raise MapError("unknown", f"tile format {fmt!r}")


class MBTiles(TileSource):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        try:
            meta = dict(self.db.execute("SELECT name, value FROM metadata").fetchall())
        except sqlite3.Error:
            meta = {}
        row = self.db.execute("SELECT tile_data FROM tiles LIMIT 1").fetchone()
        if row is None:
            raise MapError("empty")
        self.fmt = _check_format(meta.get("format"), bytes(row[0]))
        self.name = meta.get("name") or path.stem
        self.attribution = re.sub(r"<[^>]+>", "", meta.get("attribution") or "")
        lo, hi = self.db.execute("SELECT MIN(zoom_level), MAX(zoom_level) FROM tiles").fetchone()
        self.min_zoom, self.max_zoom = int(lo), int(hi)
        self.bounds = _bounds(meta.get("bounds"))

    def tile(self, z: int, x: int, y: int) -> bytes | None:
        with self._lock:  # MBTiles rows count from the bottom (TMS)
            row = self.db.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                                  (z, x, (1 << z) - 1 - y)).fetchone()
        return bytes(row[0]) if row else None

    def close(self) -> None:
        self.db.close()


class SQLiteDB(TileSource):
    """RMaps/OsmAnd/Locus: tiles(x, y, z, s, image) where z is 17 - zoom, unless OsmAnd's info table
    says the numbering is plain ("tilenumbering" not BigPlanet)."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        self.inverted, self.flip_y = True, False
        with contextlib.suppress(sqlite3.Error):
            cur = self.db.execute("SELECT * FROM info LIMIT 1")
            names = [d[0].lower() for d in cur.description]
            info = dict(zip(names, cur.fetchone() or ()))
            if "tilenumbering" in info:
                self.inverted = str(info["tilenumbering"] or "").lower() in ("bigplanet", "")
            self.flip_y = str(info.get("inverted_y") or "0") not in ("0", "", "false")
        row = self.db.execute("SELECT image FROM tiles LIMIT 1").fetchone()
        if row is None:
            raise MapError("empty")
        self.fmt = _check_format(None, bytes(row[0]))
        self.name = path.stem
        lo, hi = self.db.execute("SELECT MIN(z), MAX(z) FROM tiles").fetchone()
        self.min_zoom, self.max_zoom = sorted((self._zoom(int(lo)), self._zoom(int(hi))))

    def _zoom(self, stored: int) -> int:
        return 17 - stored if self.inverted else stored

    def tile(self, z: int, x: int, y: int) -> bytes | None:
        if self.flip_y:
            y = (1 << z) - 1 - y
        with self._lock:
            row = self.db.execute("SELECT image FROM tiles WHERE x=? AND y=? AND z=?",
                                  (x, y, self._zoom(z))).fetchone()  # 17 - z is its own inverse
        return bytes(row[0]) if row else None

    def close(self) -> None:
        self.db.close()


def zxy_to_tileid(z: int, x: int, y: int) -> int:
    """PMTiles v3 tile id: the tiles of all lower zooms, then the Hilbert curve position."""
    acc = ((1 << (z * 2)) - 1) // 3
    a = z - 1
    while a >= 0:
        s = 1 << a
        rx, ry = s & x, s & y
        acc += ((3 * rx) ^ ry) << a
        if ry == 0:
            if rx != 0:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        a -= 1
    return acc


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if b < 0x80:
            return value, pos
        shift += 7


def _directory(data: bytes) -> list[tuple[int, int, int, int]]:
    """[(tile_id, run_length, length, offset)]"""
    n, pos = _varint(data, 0)
    ids, runs, lengths, offsets = [], [], [], []
    last = 0
    for _ in range(n):
        v, pos = _varint(data, pos)
        last += v
        ids.append(last)
    for target in (runs, lengths):
        for _ in range(n):
            v, pos = _varint(data, pos)
            target.append(v)
    for i in range(n):
        v, pos = _varint(data, pos)
        offsets.append(offsets[i - 1] + lengths[i - 1] if v == 0 and i > 0 else v - 1)
    return list(zip(ids, runs, lengths, offsets))


class PMTiles(TileSource):
    TYPES = {1: "mvt", 2: "png", 3: "jpg", 4: "webp", 5: "avif"}

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.file = open(path, "rb")  # noqa: SIM115 - kept open while the map is used
        head = self.file.read(127)
        if len(head) < 127 or head[:7] != b"PMTiles" or head[7] != 3:
            raise MapError("unknown", "not PMTiles version 3")
        (self.root_off, self.root_len, meta_off, meta_len, self.leaf_off, _leaf_len, self.data_off,
         _data_len) = struct.unpack_from("<8Q", head, 8)
        self.internal, self.tile_comp, kind = head[97], head[98], head[99]
        if kind not in (2, 3, 4):
            raise MapError("vector" if kind == 1 else "unknown", f"tile type {kind}")
        self.fmt = self.TYPES[kind]
        self.min_zoom, self.max_zoom = head[100], head[101]
        w, s, e, n = (v / 1e7 for v in struct.unpack_from("<4i", head, 102))
        self.bounds = _bounds(f"{w},{s},{e},{n}")
        self.name = path.stem
        with contextlib.suppress(Exception):
            import json
            meta = json.loads(self._read(meta_off, meta_len, self.internal) or b"{}")
            self.name = meta.get("name") or self.name
            self.attribution = re.sub(r"<[^>]+>", "", meta.get("attribution") or "")
        self._dirs: dict[tuple[int, int], list] = {}

    def _read(self, offset: int, length: int, compression: int = 1) -> bytes:
        with self._lock:
            self.file.seek(offset)
            data = self.file.read(length)
        if compression == 2:
            return gzip.decompress(data)
        if compression not in (0, 1):
            raise MapError("unknown", f"compression {compression}")
        return data

    def _dir(self, offset: int, length: int) -> list:
        key = (offset, length)
        if key not in self._dirs:
            if len(self._dirs) > 64:
                self._dirs.clear()
            self._dirs[key] = _directory(self._read(offset, length, self.internal))
        return self._dirs[key]

    def tile(self, z: int, x: int, y: int) -> bytes | None:
        tid = zxy_to_tileid(z, x, y)
        offset, length = self.root_off, self.root_len
        for _depth in range(4):
            entries = self._dir(offset, length)
            lo, hi, found = 0, len(entries) - 1, None
            while lo <= hi:  # the last entry with tile_id <= tid
                mid = (lo + hi) // 2
                if entries[mid][0] <= tid:
                    found, lo = entries[mid], mid + 1
                else:
                    hi = mid - 1
            if found is None:
                return None
            start, run, size, off = found
            if run == 0:  # a leaf directory
                offset, length = self.leaf_off + off, size
                continue
            if tid >= start + run:
                return None
            return self._read(self.data_off + off, size, self.tile_comp)
        return None

    def close(self) -> None:
        self.file.close()


_TILE_PATH = re.compile(r"(?:^|.*/)(\d{1,2})/(\d+)/(\d+)\.(png|jpe?g|webp)(?:\.tile)?$", re.IGNORECASE)


def _tile_index(names) -> tuple[dict[tuple[int, int, int], str], str]:
    index, fmt = {}, ""
    for name in names:
        m = _TILE_PATH.match(name.replace("\\", "/"))
        if m:
            z, x, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if z <= 24 and x < (1 << z) and y < (1 << z):
                index[(z, x, y)] = name
                fmt = fmt or m.group(4).lower()
    if not index:
        raise MapError("empty")
    return index, ("jpg" if fmt == "jpeg" else fmt)


def _bounds_of(index) -> tuple[float, float, float, float] | None:
    top = max(z for z, _, _ in index)
    xs = [x for z, x, _ in index if z == top]
    ys = [y for z, _, y in index if z == top]
    n = 1 << top

    def lat(y: float) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))

    return _bounds(f"{min(xs) / n * 360 - 180},{lat(max(ys) + 1)},{(max(xs) + 1) / n * 360 - 180},{lat(min(ys))}")


class ZipTiles(TileSource):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.zip = zipfile.ZipFile(path)
        self.index, self.fmt = _tile_index(self.zip.namelist())
        zooms = [z for z, _, _ in self.index]
        self.min_zoom, self.max_zoom = min(zooms), max(zooms)
        self.bounds = _bounds_of(self.index)
        self.name = path.stem

    def tile(self, z: int, x: int, y: int) -> bytes | None:
        name = self.index.get((z, x, y))
        if name is None:
            return None
        with self._lock:
            return self.zip.read(name)

    def close(self) -> None:
        self.zip.close()


class FolderTiles(TileSource):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        names = [str(p.relative_to(path)) for p in path.rglob("*") if p.suffix.lower() in PICTURE_SUFFIXES]
        self.index, self.fmt = _tile_index(names)
        zooms = [z for z, _, _ in self.index]
        self.min_zoom, self.max_zoom = min(zooms), max(zooms)
        self.bounds = _bounds_of(self.index)
        self.name = path.name

    def tile(self, z: int, x: int, y: int) -> bytes | None:
        name = self.index.get((z, x, y))
        return (self.path / name).read_bytes() if name else None


def open_source(path: str | Path) -> TileSource:
    path = Path(path)
    try:
        if path.is_dir():
            return FolderTiles(path)
        with open(path, "rb") as f:
            head = f.read(16)
        if head.startswith(b"PMTiles"):
            return PMTiles(path)
        if head.startswith(b"SQLite format 3"):
            db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                tables = {r[0].lower() for r in db.execute("SELECT name FROM sqlite_master")}
                cols = {r[1].lower() for r in db.execute("PRAGMA table_info(tiles)")}
            finally:
                db.close()
            if "tile_data" in cols or "map" in tables:
                return MBTiles(path)
            if "image" in cols:
                return SQLiteDB(path)
            raise MapError("unknown", "SQLite without tiles")
        if head.startswith(b"PK"):
            return ZipTiles(path)
    except MapError:
        raise
    except (OSError, sqlite3.Error, zipfile.BadZipFile, struct.error, ValueError, IndexError) as err:
        raise MapError("read", str(err)) from err
    raise MapError("unknown", path.suffix)


# ─── importing: what is picked becomes one or more map paths ──────────────────


def _seven_zip() -> str | None:
    for name in ("7z", "7zz", "7za", r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe",
                 "/opt/homebrew/bin/7zz", "/usr/local/bin/7zz", "/opt/homebrew/bin/7z", "/usr/local/bin/7z"):
        found = shutil.which(name) or (name if Path(name).is_file() else None)
        if found:
            return found
    return None


def _free_name(folder: Path, name: str) -> Path:
    target = folder / name
    stem, suffix, n = target.stem, target.suffix, 2
    while target.exists():
        target = folder / f"{stem}-{n}{suffix}"
        n += 1
    return target


def _maps_in(folder: Path) -> list[Path]:
    found = sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in MAP_SUFFIXES)
    if found:
        return found
    with contextlib.suppress(MapError):
        FolderTiles(folder)
        return [folder]
    return []


def import_file(source: str | Path, maps_dir: Path, keep_in_place: bool) -> list[Path]:
    """Make a picked file usable as maps; the paths to open. Raises MapError.

    keep_in_place: on a computer a map file is used where it is (no copy of gigabytes); on a phone
    the picker hands over its own temporary copy, which is moved into the app's folder.
    An archive with map files in it is unpacked into maps_dir; a ZIP of tile pictures is used as it is.
    """
    source = Path(source)
    maps_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()

    def keep(path: Path) -> Path:
        if keep_in_place:
            return path
        target = _free_name(maps_dir, path.name)
        shutil.move(str(path), target)
        return target

    if suffix == ".7z":
        tool = _seven_zip()
        if tool is None:
            raise MapError("no7z")
        out = _free_name(maps_dir, source.stem)
        out.mkdir()
        result = subprocess.run([tool, "x", "-y", f"-o{out}", str(source)], capture_output=True, timeout=3600)
        if result.returncode != 0:
            shutil.rmtree(out, ignore_errors=True)
            raise MapError("read", result.stderr.decode(errors="replace")[-300:])
        found = _maps_in(out)
        if not found:
            shutil.rmtree(out, ignore_errors=True)
            raise MapError("empty")
        for path in found:
            open_source(path).close()  # raises for what cannot be shown
        if not keep_in_place:
            with contextlib.suppress(OSError):
                source.unlink()
        return found

    if suffix == ".zip":
        try:
            with zipfile.ZipFile(source) as z:
                inner = [n for n in z.namelist() if Path(n).suffix.lower() in MAP_SUFFIXES and not n.endswith("/")]
                if inner:
                    found = []
                    for name in inner:
                        target = _free_name(maps_dir, Path(name).name)
                        with z.open(name) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst, 1 << 20)
                        try:
                            open_source(target).close()
                        except MapError:
                            target.unlink(missing_ok=True)
                            raise
                        found.append(target)
                    if not keep_in_place:
                        source.unlink(missing_ok=True)
                    return found
        except zipfile.BadZipFile as err:
            raise MapError("read", str(err)) from err
    open_source(source).close()  # a map file or a ZIP of tiles: check it can be shown
    return [keep(source)]


def remove_map(path: str | Path, maps_dir: Path) -> None:
    """Forget a map; delete it only when it lives in the app's own maps folder."""
    path = Path(path)
    with contextlib.suppress(ValueError, OSError):
        path.resolve().relative_to(maps_dir.resolve())
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        parent = path.parent
        while parent.resolve() != maps_dir.resolve() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


# ─── the little web server the map reads the tiles from ──────────────────────


class TileServer:
    """http://127.0.0.1:PORT/<key>/{z}/{x}/{y} for each open map; nothing else is served."""

    def __init__(self) -> None:
        self.sources: dict[str, TileSource] = {}
        self._server: ThreadingHTTPServer | None = None
        self._generation = 0

    @property
    def port(self) -> int:
        if self._server is None:
            self._start()
        return self._server.server_address[1]

    def _start(self) -> None:
        sources = self.sources

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parts = self.path.split("?")[0].strip("/").split("/")
                data, fmt = None, "png"
                if len(parts) == 4 and parts[0] in sources:
                    source = sources[parts[0]]
                    with contextlib.suppress(ValueError, OSError, sqlite3.Error, KeyError, zlib.error,
                                             MapError, struct.error, IndexError):
                        z, x, y = int(parts[1]), int(parts[2]), int(parts[3].split(".")[0])
                        data, fmt = source.tile(z, x, y), source.fmt
                if data is None:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", MIME.get(fmt, "application/octet-stream"))
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")  # the web build asks from another port
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_args) -> None:
                pass

        class Server(ThreadingHTTPServer):
            daemon_threads = True

            def handle_error(self, request, client_address) -> None:
                pass  # the map gave up on a tile (panned away): nothing to report

        self._server = Server(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, name="aprs_kiss_tiles", daemon=True).start()

    def set_maps(self, paths: list[str]) -> tuple[list[tuple[str, TileSource]], list[tuple[str, MapError]]]:
        """Open these maps (closing the old ones); ([(url, source)], [(path, error)])."""
        for source in self.sources.values():
            with contextlib.suppress(Exception):
                source.close()
        self.sources.clear()
        self._generation += 1
        opened, failed = [], []
        for i, path in enumerate(paths):
            try:
                source = open_source(path)
            except MapError as err:
                failed.append((path, err))
                continue
            key = f"m{self._generation}x{i}"
            self.sources[key] = source
            opened.append((f"http://127.0.0.1:{self.port}/{key}/{{z}}/{{x}}/{{y}}", source))
        return opened, failed

    def close(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        for source in self.sources.values():
            with contextlib.suppress(Exception):
                source.close()
        self.sources.clear()
