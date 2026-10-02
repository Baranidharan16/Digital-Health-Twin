"""Phone connection endpoints: pairing, claim, Health Connect sync, devices."""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Any

from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse

from backend.app.api.deps import Container, get_container
from backend.app.config import REPO_ROOT
from backend.app.services.devices import ClaimIn, DeviceAuthError, DeviceSyncIn, PairingIn
from backend.app.services.twin_service import TwinNotFoundError

router = APIRouter(prefix="/api", tags=["phone"])

# Put the Android app here (see docs/mobile.md) and the website offers it for download.
APK_CANDIDATES = (
    REPO_ROOT / "downloads" / "health-twin.apk",
    REPO_ROOT / "mobile" / "android" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk",
)


def apk_path() -> Path | None:
    return next((p for p in APK_CANDIDATES if p.is_file()), None)


def lan_addresses() -> list[str]:
    """Best-effort list of this computer's IPv4 addresses on the local network."""
    found: list[str] = []
    try:  # the address the OS would use to reach the internet (no packet is sent)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    seen: list[str] = []
    for ip in found:
        if ip not in seen and not ip.startswith("127.") and not ip.startswith("169.254."):
            seen.append(ip)
    return seen


def _port(request: Request) -> int:
    env = os.environ.get("DHT_PUBLIC_PORT")
    if env and env.isdigit():
        return int(env)
    return request.url.port or (443 if request.url.scheme == "https" else 80)


def _is_private(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return host in ("localhost",) or host.endswith(".local")


def is_public(request: Request) -> bool:
    """True when the website was opened through a public address (a deployment), not localhost or the LAN."""
    host = request.url.hostname or ""
    return bool(host) and not _is_private(host)


def server_urls(request: Request) -> list[str]:
    public = os.environ.get("DHT_PUBLIC_URL", "").strip().rstrip("/")
    if public:  # set explicitly (Docker on a laptop, or a deployment)
        return [public]
    host = request.url.hostname or ""
    if is_public(request):
        # Deployed (Render, a VPS...): the address in the browser works for the phone too, from any network.
        scheme = request.url.scheme
        port = request.url.port
        default = (scheme == "https" and port in (None, 443)) or (scheme == "http" and port in (None, 80))
        return [f"{scheme}://{host}" if default else f"{scheme}://{host}:{port}"]
    port = _port(request)
    # In development the page is served by Vite (5173); the phone must talk to the API port.
    if port == 5173:
        port = 8000
    urls = [f"http://{ip}:{port}" for ip in lan_addresses()]
    if host and host not in ("localhost", "127.0.0.1") and not any(host in u for u in urls):
        urls.insert(0, f"http://{host}:{port}")
    return urls


@router.get("/system/network", summary="Addresses a phone on the same Wi-Fi can use to reach this server")
def network(request: Request) -> dict[str, Any]:
    return {
        "server_urls": server_urls(request),
        "port": _port(request),
        "public": is_public(request) or bool(os.environ.get("DHT_PUBLIC_URL")),
        "apk_available": apk_path() is not None,
    }


@router.get("/devices/app.apk", summary="Download the Android companion app, if it has been built")
def download_apk() -> FileResponse:
    path = apk_path()
    if path is None:
        raise HTTPException(status_code=404, detail="APK not built yet; see docs/mobile.md")
    return FileResponse(path, media_type="application/vnd.android.package-archive", filename="health-twin.apk")


@router.post("/devices/pairing", summary="Create a 6-digit pairing code (valid 10 minutes)")
def create_pairing(body: PairingIn, request: Request, c: Container = Depends(get_container)) -> dict[str, Any]:
    pairing = c.devices.create_pairing(body.display_name, body.age_years)
    urls = server_urls(request)
    pairing["server_urls"] = urls
    pairing["deep_link"] = f"healthtwin://pair?server={urls[0] if urls else ''}&code={pairing['code']}"
    return pairing


@router.post("/devices/claim", summary="Phone exchanges a pairing code for a device token")
def claim(body: ClaimIn, c: Container = Depends(get_container)) -> dict[str, Any]:
    try:
        return c.devices.claim(body.code, body.device_name)
    except DeviceAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else None


@router.post("/devices/sync", summary="Phone uploads Health Connect records (Bearer device token)")
def sync(
    body: DeviceSyncIn,
    authorization: str | None = Header(default=None),
    c: Container = Depends(get_container),
) -> dict[str, Any]:
    try:
        device = c.devices.authenticate(_bearer(authorization))
    except DeviceAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc), headers={"WWW-Authenticate": "Bearer"}) from exc
    try:
        return c.devices.sync(device, body)
    except TwinNotFoundError as exc:
        raise HTTPException(status_code=410, detail="this phone's twin was deleted; pair again") from exc


@router.get("/devices/me", summary="Phone checks its own pairing")
def me(authorization: str | None = Header(default=None), c: Container = Depends(get_container)) -> dict[str, Any]:
    try:
        device = c.devices.authenticate(_bearer(authorization))
    except DeviceAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"device_id": device.id, "twin_id": device.twin_id, "name": device.name, "last_sync": device.last_sync}


@router.get("/devices", summary="List connected phones")
def list_devices(c: Container = Depends(get_container)) -> list[dict[str, Any]]:
    return c.devices.list_devices()


@router.delete("/devices/{device_id}", summary="Disconnect a phone (its token stops working)")
def revoke(device_id: int, c: Container = Depends(get_container)) -> dict[str, Any]:
    try:
        c.devices.revoke(device_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"revoked": device_id}
