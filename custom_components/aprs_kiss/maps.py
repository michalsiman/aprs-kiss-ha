"""The user's own offline maps (MBTiles, PMTiles, RMaps SQLiteDB, a ZIP or folder of tiles) for the panel.

The maps live in /config/aprs_kiss/maps: uploaded from the panel (an archive with map files is unpacked
there) or copied in by hand (Samba, the File editor, …). The panel's map reads the tiles from
/api/aprs_kiss/tiles/<key>/{z}/{x}/{y}: Leaflet loads them as plain pictures, which cannot carry Home
Assistant's login, so each map gets a long random key instead (new at every start) and nothing else
can be read there. Reading the files is core.tilemaps, the same as in the app.
"""

from __future__ import annotations

import contextlib
import logging
import secrets
import sqlite3
import struct
import zlib
from pathlib import Path
from typing import Any

import voluptuous as vol
from aiohttp import web

from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .core import tilemaps

_LOGGER = logging.getLogger(__name__)

MIME = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
UPLOAD_CHUNK = 1 << 20


class MapStore:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.folder = Path(hass.config.path(DOMAIN, "maps"))
        self.sources: dict[str, tilemaps.TileSource] = {}  # key -> open map
        self.failed: list[dict[str, str]] = []

    def scan(self) -> None:
        """Open every map in the folder (blocking: in an executor). Maps already open keep their key."""
        self.folder.mkdir(parents=True, exist_ok=True)
        found = tilemaps._maps_in(self.folder) if any(self.folder.iterdir()) else []  # noqa: SLF001
        if found == [self.folder]:
            found = []  # the folder itself is not a map of tiles
        open_paths = {str(s.path): k for k, s in self.sources.items()}
        keep, self.failed = {}, []
        for path in found:
            key = open_paths.get(str(path))
            if key:
                keep[key] = self.sources.pop(key)
                continue
            try:
                keep[secrets.token_hex(16)] = tilemaps.open_source(path)
            except tilemaps.MapError as err:
                self.failed.append({"file": path.name, "error": err.code})
        for source in self.sources.values():  # gone from the folder
            with contextlib.suppress(Exception):
                source.close()
        self.sources = keep

    def listing(self) -> dict[str, Any]:
        maps = []
        for key, s in self.sources.items():
            size = 0
            with contextlib.suppress(OSError):
                size = s.path.stat().st_size if s.path.is_file() else 0
            maps.append({"key": key, "file": s.path.relative_to(self.folder).as_posix(), "name": s.name or s.path.stem,
                         "min_zoom": s.min_zoom, "max_zoom": s.max_zoom, "bounds": s.bounds,
                         "attribution": s.attribution, "size": size,
                         "url": f"/api/{DOMAIN}/tiles/{key}/{{z}}/{{x}}/{{y}}"})
        return {"folder": str(self.folder), "maps": maps, "failed": self.failed}

    def remove(self, file: str) -> None:
        path = (self.folder / file).resolve()
        path.relative_to(self.folder.resolve())  # raises outside the maps folder
        for key, s in list(self.sources.items()):
            if s.path.resolve() == path:
                with contextlib.suppress(Exception):
                    s.close()
                del self.sources[key]
        tilemaps.remove_map(path, self.folder)

    def tile(self, key: str, z: int, x: int, y: int) -> tuple[bytes, str] | None:
        source = self.sources.get(key)
        if source is None:
            return None
        with contextlib.suppress(ValueError, OSError, sqlite3.Error, KeyError, zlib.error, tilemaps.MapError,
                                 struct.error, IndexError):
            data = source.tile(z, x, y)
            if data:
                return data, MIME.get(source.fmt, "application/octet-stream")
        return None

    def close(self) -> None:
        for source in self.sources.values():
            with contextlib.suppress(Exception):
                source.close()
        self.sources = {}


class TileView(HomeAssistantView):
    url = f"/api/{DOMAIN}/tiles/{{key}}/{{z}}/{{x}}/{{y}}"
    name = f"api:{DOMAIN}:tiles"
    requires_auth = False  # pictures for Leaflet; the key (random, per start) is what lets them through

    def __init__(self, store: MapStore) -> None:
        self.store = store

    async def get(self, request: web.Request, key: str, z: str, x: str, y: str) -> web.Response:
        try:
            zi, xi, yi = int(z), int(x), int(y.split(".")[0])
        except ValueError:
            return web.Response(status=404)
        found = await request.app["hass"].async_add_executor_job(self.store.tile, key, zi, xi, yi)
        if found is None:
            return web.Response(status=404)
        data, mime = found
        return web.Response(body=data, content_type=mime, headers={"Cache-Control": "max-age=86400"})


class UploadView(HomeAssistantView):
    """A map file (or a .zip / .7z with maps) from the panel, streamed to the maps folder."""

    url = f"/api/{DOMAIN}/maps/upload"
    name = f"api:{DOMAIN}:maps:upload"
    requires_auth = True

    def __init__(self, store: MapStore) -> None:
        self.store = store

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not request["hass_user"].is_admin:
            return web.json_response({"error": "admin"}, status=403)
        name = Path(request.query.get("name", "map")).name or "map"
        store = self.store
        await hass.async_add_executor_job(store.folder.mkdir, 0o755, True, True)
        part = tilemaps._free_name(store.folder, f".upload-{name}")  # noqa: SLF001
        try:
            out = await hass.async_add_executor_job(part.open, "wb")
            try:
                while chunk := await request.content.read(UPLOAD_CHUNK):
                    await hass.async_add_executor_job(out.write, chunk)
            finally:
                await hass.async_add_executor_job(out.close)
            target = tilemaps._free_name(store.folder, name)  # noqa: SLF001

            def place() -> list[str]:
                part.rename(target)
                try:
                    found = tilemaps.import_file(target, store.folder, keep_in_place=True)
                except tilemaps.MapError:
                    target.unlink(missing_ok=True)
                    raise
                if target.suffix.lower() in (".zip", ".7z") and target not in found:
                    target.unlink(missing_ok=True)  # an archive of map files: unpacked, not kept
                store.scan()
                return [p.name for p in found]

            names = await hass.async_add_executor_job(place)
        except tilemaps.MapError as err:
            return web.json_response({"error": err.code, "detail": str(err)}, status=400)
        except OSError as err:
            return web.json_response({"error": "read", "detail": str(err)}, status=500)
        finally:
            await hass.async_add_executor_job(lambda: part.unlink(missing_ok=True))
        return web.json_response({"added": names})


def register(hass: HomeAssistant) -> MapStore:
    store = MapStore(hass)
    hass.http.register_view(TileView(store))
    hass.http.register_view(UploadView(store))

    @websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/maps"})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_maps(hass, connection, msg):
        await hass.async_add_executor_job(store.scan)
        connection.send_result(msg["id"], store.listing())

    @websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/maps_remove", vol.Required("file"): str})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_maps_remove(hass, connection, msg):
        try:
            await hass.async_add_executor_job(store.remove, msg["file"])
        except (ValueError, OSError) as err:
            connection.send_error(msg["id"], "invalid", str(err))
            return
        connection.send_result(msg["id"], store.listing())

    websocket_api.async_register_command(hass, ws_maps)
    websocket_api.async_register_command(hass, ws_maps_remove)
    hass.async_add_executor_job(store.scan)
    return store
