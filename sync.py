#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def describe_http_error(response: requests.Response) -> str:
    text = response.text.strip()
    if not text:
        return ""
    try:
        payload = response.json()
    except ValueError:
        detail = text
    else:
        if isinstance(payload, list) and payload and all(isinstance(item, str) for item in payload):
            detail = ": ".join(payload[:2])
        elif isinstance(payload, dict):
            error = payload.get("ERROR") or payload.get("error")
            message = payload.get("MESSAGE") or payload.get("message")
            if error and message:
                detail = f"{error}: {message}"
            elif error:
                detail = str(error)
            else:
                detail = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        else:
            detail = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    detail = " ".join(detail.split())
    if len(detail) > 500:
        detail = detail[:497] + "..."
    return detail


@dataclass
class Settings:
    librenms_url: str
    librenms_token: str
    librenms_device_filter: str
    librenms_device_order: str
    librenms_device_url_template: str
    glpi_url: str
    glpi_verify_tls: bool
    glpi_auth_method: str
    glpi_username: str
    glpi_password: str
    glpi_user_token: str
    glpi_app_token: str
    glpi_profile_id: int | None
    glpi_entity_id: int | None
    glpi_default_itemtype: str
    glpi_type_map: dict[str, str]
    state_file: Path
    request_timeout: int
    log_level: str
    dry_run: bool
    only_host: str
    preserve_existing_comment: bool
    comment_marker: str
    comment_include_raw_json: bool

    @classmethod
    def from_env(cls) -> "Settings":
        type_map_raw = os.environ.get(
            "GLPI_TYPE_MAP",
            "server=Computer,network=NetworkEquipment,firewall=NetworkEquipment",
        )
        type_map: dict[str, str] = {}
        for pair in type_map_raw.split(","):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            type_map[key.strip().lower()] = value.strip()

        entity_id_raw = os.environ.get("GLPI_ENTITY_ID", "").strip()
        entity_id = int(entity_id_raw) if entity_id_raw else None
        profile_id_raw = os.environ.get("GLPI_PROFILE_ID", "").strip()
        profile_id = int(profile_id_raw) if profile_id_raw else None

        return cls(
            librenms_url=os.environ["LIBRENMS_URL"].rstrip("/"),
            librenms_token=os.environ["LIBRENMS_TOKEN"],
            librenms_device_filter=os.environ.get("LIBRENMS_DEVICE_FILTER", "active"),
            librenms_device_order=os.environ.get("LIBRENMS_DEVICE_ORDER", "hostname ASC"),
            librenms_device_url_template=os.environ.get("LIBRENMS_DEVICE_URL_TEMPLATE", "").strip(),
            glpi_url=os.environ["GLPI_URL"].rstrip("/"),
            glpi_verify_tls=env_bool("GLPI_VERIFY_TLS", True),
            glpi_auth_method=os.environ.get("GLPI_AUTH_METHOD", "basic").strip().lower(),
            glpi_username=os.environ.get("GLPI_USERNAME", ""),
            glpi_password=os.environ.get("GLPI_PASSWORD", ""),
            glpi_user_token=os.environ.get("GLPI_USER_TOKEN", ""),
            glpi_app_token=os.environ.get("GLPI_APP_TOKEN", ""),
            glpi_profile_id=profile_id,
            glpi_entity_id=entity_id,
            glpi_default_itemtype=os.environ.get("GLPI_DEFAULT_ITEMTYPE", "NetworkEquipment"),
            glpi_type_map=type_map,
            state_file=Path(os.environ.get("STATE_FILE", "/var/lib/librenms-glpi-sync/state.json")),
            request_timeout=int(os.environ.get("REQUEST_TIMEOUT", "30")),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            dry_run=env_bool("DRY_RUN", False),
            only_host=os.environ.get("ONLY_HOST", "").strip(),
            preserve_existing_comment=env_bool("PRESERVE_EXISTING_COMMENT", True),
            comment_marker=os.environ.get("COMMENT_MARKER", "LibreNMS sync").strip() or "LibreNMS sync",
            comment_include_raw_json=env_bool("COMMENT_INCLUDE_RAW_JSON", False),
        )


class LibreNMSClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Auth-Token": settings.librenms_token,
                "User-Agent": "librenms-glpi-sync/1.0",
            }
        )

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.get(
            f"{self.settings.librenms_url}/api/v0{path}",
            params=params,
            timeout=self.settings.request_timeout,
        )
        response.raise_for_status()
        return response.json()

    def list_devices(self) -> list[dict[str, Any]]:
        data = self.get(
            "/devices",
            params={
                "type": self.settings.librenms_device_filter,
                "order": self.settings.librenms_device_order,
            },
        )
        devices = data.get("devices", [])
        if self.settings.only_host:
            host = self.settings.only_host
            devices = [
                d
                for d in devices
                if d.get("hostname") == host or d.get("sysName") == host or str(d.get("device_id")) == host
            ]
        return devices

    def get_device(self, host_or_id: str | int) -> dict[str, Any]:
        data = self.get(f"/devices/{quote(str(host_or_id), safe='')}")
        devices = data.get("devices", [])
        if not devices:
            raise RuntimeError(f"LibreNMS device not found: {host_or_id}")
        return devices[0]

    def get_availability(self, host_or_id: str | int) -> dict[str, Any]:
        data = self.get(f"/devices/{quote(str(host_or_id), safe='')}/availability")
        labels = {86400: "24h", 604800: "7d", 2592000: "30d", 31536000: "1y"}
        result: dict[str, Any] = {}
        for item in data.get("availability", []):
            duration = item.get("duration")
            label = labels.get(duration, str(duration))
            result[label] = item.get("availability_perc")
        return result


class GLPIClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "librenms-glpi-sync/1.0",
            }
        )
        if settings.glpi_app_token:
            self.session.headers["App-Token"] = settings.glpi_app_token
        self.session_token: str | None = None

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        headers = dict(kwargs.pop("headers", {}))
        if self.session_token:
            headers["Session-Token"] = self.session_token
        response = self.session.request(
            method,
            f"{self.settings.glpi_url}{path}",
            headers=headers,
            verify=self.settings.glpi_verify_tls,
            timeout=self.settings.request_timeout,
            **kwargs,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = describe_http_error(response)
            if detail:
                raise requests.HTTPError(
                    f"{exc}. GLPI response: {detail}",
                    request=response.request,
                    response=response,
                ) from exc
            raise
        return response

    def init_session(self) -> None:
        auth_method = self.settings.glpi_auth_method
        if auth_method == "basic":
            if not self.settings.glpi_username or not self.settings.glpi_password:
                raise RuntimeError("GLPI basic auth selected but GLPI_USERNAME/GLPI_PASSWORD is missing")
            response = self._request(
                "GET",
                "/apirest.php/initSession/",
                auth=(self.settings.glpi_username, self.settings.glpi_password),
            )
        elif auth_method == "token":
            if not self.settings.glpi_user_token:
                raise RuntimeError("GLPI token auth selected but GLPI_USER_TOKEN is missing")
            headers = {"Authorization": f"user_token {self.settings.glpi_user_token}"}
            response = self._request("GET", "/apirest.php/initSession/", headers=headers)
        else:
            raise RuntimeError(f"Unsupported GLPI_AUTH_METHOD: {auth_method}")

        data = response.json()
        if isinstance(data, dict) and "session_token" in data:
            self.session_token = data["session_token"]
            return
        raise RuntimeError(f"Unexpected initSession response: {data}")

    def set_active_entity(self) -> None:
        if self.settings.glpi_entity_id is None:
            return
        self._request(
            "POST",
            "/apirest.php/changeActiveEntities/",
            json={"entities_id": self.settings.glpi_entity_id, "is_recursive": True},
        )
        logging.info("Using GLPI active entity %s", self.settings.glpi_entity_id)

    def set_active_profile(self) -> None:
        if self.settings.glpi_profile_id is None:
            return
        self._request(
            "POST",
            "/apirest.php/changeActiveProfile/",
            json={"profiles_id": self.settings.glpi_profile_id},
        )
        logging.info("Using GLPI active profile %s", self.settings.glpi_profile_id)

    def kill_session(self) -> None:
        if not self.session_token:
            return
        try:
            self._request("GET", "/apirest.php/killSession/")
        except Exception as exc:  # noqa: BLE001
            logging.warning("Failed to close GLPI session cleanly: %s", exc)
        finally:
            self.session_token = None

    def find_by_name(self, itemtype: str, name: str) -> dict[str, Any] | None:
        response = self._request(
            "GET",
            f"/apirest.php/{itemtype}/",
            params={"searchText[name]": name, "range": "0-50"},
        )
        data = response.json()
        if isinstance(data, list):
            items = data
        else:
            items = data.get("data", []) or data.get("items", [])
        for item in items:
            if item.get("name") == name:
                return item
        return None

    def get_item(self, itemtype: str, item_id: int) -> dict[str, Any]:
        response = self._request("GET", f"/apirest.php/{itemtype}/{item_id}")
        return response.json()

    def create_item(self, itemtype: str, payload: dict[str, Any]) -> int:
        response = self._request(
            "POST",
            f"/apirest.php/{itemtype}/",
            headers={"Content-Type": "application/json"},
            json={"input": payload},
        )
        data = response.json()
        if isinstance(data, dict) and "id" in data:
            return int(data["id"])
        raise RuntimeError(f"Unexpected GLPI create response: {data}")

    def update_item(self, itemtype: str, item_id: int, payload: dict[str, Any]) -> None:
        body = {"input": {"id": item_id, **payload}}
        self._request(
            "PATCH",
            f"/apirest.php/{itemtype}/{item_id}",
            headers={"Content-Type": "application/json"},
            json=body,
        )


def choose_name(device: dict[str, Any]) -> str:
    for key in ("sysName", "hostname"):
        value = (device.get(key) or "").strip()
        if value:
            return value
    return f"device-{device['device_id']}"


def build_librenms_url(settings: Settings, device: dict[str, Any]) -> str:
    template = settings.librenms_device_url_template
    if not template:
        return ""
    try:
        return template.format(
            device_id=device.get("device_id", ""),
            hostname=device.get("hostname", ""),
            sysName=device.get("sysName", ""),
        )
    except Exception:  # noqa: BLE001
        logging.warning("Could not render LIBRENMS_DEVICE_URL_TEMPLATE, skipping URL")
        return ""


def build_sync_block(settings: Settings, device: dict[str, Any], availability: dict[str, Any]) -> str:
    status_text = "up" if str(device.get("status")) == "1" else "down"
    timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    librenms_url = build_librenms_url(settings, device)

    lines = [
        f"[{settings.comment_marker} START]",
        f"device_id: {device.get('device_id', '')}",
        f"hostname: {device.get('hostname', '')}",
        f"sysName: {device.get('sysName', '')}",
        f"sysDescr: {device.get('sysDescr', '')}",
        f"type: {device.get('type', '')}",
        f"hardware: {device.get('hardware', '')}",
        f"version: {device.get('version', '')}",
        f"location: {device.get('location', '')}",
        f"status: {status_text}",
        f"status_reason: {device.get('status_reason', '')}",
        f"availability_24h: {availability.get('24h', '')}",
        f"availability_7d: {availability.get('7d', '')}",
        f"availability_30d: {availability.get('30d', '')}",
        f"availability_1y: {availability.get('1y', '')}",
    ]
    if librenms_url:
        lines.append(f"librenms_url: {librenms_url}")
    lines.append(f"last_sync: {timestamp}")
    if settings.comment_include_raw_json:
        lines.append("raw_json: " + json.dumps(device, ensure_ascii=False, sort_keys=True))
    lines.append(f"[{settings.comment_marker} END]")
    return "\n".join(lines)


def merge_comment(existing: str, block: str, marker: str, preserve_existing: bool) -> str:
    if not preserve_existing:
        return block

    start_marker = f"[{marker} START]"
    end_marker = f"[{marker} END]"
    text = existing or ""
    start = text.find(start_marker)
    end = text.find(end_marker)

    if start != -1 and end != -1 and end >= start:
        end += len(end_marker)
        before = text[:start].rstrip()
        after = text[end:].lstrip()
        parts = [p for p in (before, block, after) if p]
        return "\n\n".join(parts)

    if text.strip():
        return text.rstrip() + "\n\n" + block
    return block


def map_itemtype(settings: Settings, device: dict[str, Any]) -> str:
    device_type = (device.get("type") or "").strip().lower()
    return settings.glpi_type_map.get(device_type, settings.glpi_default_itemtype)


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def build_payload(settings: Settings, itemtype: str, existing_item: dict[str, Any] | None, device: dict[str, Any], availability: dict[str, Any]) -> dict[str, Any]:
    name = choose_name(device)
    existing_comment = ""
    if existing_item:
        existing_comment = existing_item.get("comment", "") or ""
    block = build_sync_block(settings, device, availability)
    payload: dict[str, Any] = {
        "name": name,
        "comment": merge_comment(existing_comment, block, settings.comment_marker, settings.preserve_existing_comment),
    }
    if settings.glpi_entity_id is not None and not existing_item:
        payload["entities_id"] = settings.glpi_entity_id
    return payload


def sync_device(settings: Settings, librenms: LibreNMSClient, glpi: GLPIClient, state: dict[str, Any], base_device: dict[str, Any]) -> None:
    device_id = str(base_device["device_id"])
    full = librenms.get_device(device_id)
    availability = librenms.get_availability(device_id)
    itemtype = map_itemtype(settings, full)
    name = choose_name(full)

    existing_item: dict[str, Any] | None = None
    glpi_id: int | None = None
    glpi_itemtype = itemtype

    if device_id in state:
        glpi_id = int(state[device_id]["glpi_id"])
        glpi_itemtype = state[device_id].get("itemtype", itemtype)
        try:
            existing_item = glpi.get_item(glpi_itemtype, glpi_id)
        except Exception as exc:  # noqa: BLE001
            logging.warning("State hit failed for device_id=%s (%s), falling back to search", device_id, exc)
            existing_item = None
            glpi_id = None
            glpi_itemtype = itemtype

    if existing_item is None:
        found = glpi.find_by_name(itemtype, name)
        if found:
            glpi_id = int(found["id"])
            glpi_itemtype = itemtype
            existing_item = glpi.get_item(glpi_itemtype, glpi_id)

    payload = build_payload(settings, glpi_itemtype, existing_item, full, availability)

    if settings.dry_run:
        action = "UPDATE" if glpi_id is not None else "CREATE"
        logging.info("DRY RUN %s %s %s", action, glpi_itemtype, name)
    elif glpi_id is not None:
        glpi.update_item(glpi_itemtype, glpi_id, payload)
        logging.info("UPDATED %s:%s <- %s", glpi_itemtype, glpi_id, name)
    else:
        glpi_id = glpi.create_item(glpi_itemtype, payload)
        logging.info("CREATED %s:%s <- %s", glpi_itemtype, glpi_id, name)

    if glpi_id is not None:
        state[device_id] = {"glpi_id": glpi_id, "itemtype": glpi_itemtype, "name": name}


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )


def main() -> int:
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    if not settings.glpi_verify_tls:
        requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
        logging.warning("GLPI_VERIFY_TLS=false. Use this only when you understand the TLS risk.")

    librenms = LibreNMSClient(settings)
    glpi = GLPIClient(settings)
    state = load_state(settings.state_file)
    failures = 0

    glpi.init_session()
    try:
        glpi.set_active_profile()
        glpi.set_active_entity()
        devices = librenms.list_devices()
        logging.info("Found %s LibreNMS devices to process", len(devices))
        for device in devices:
            try:
                sync_device(settings, librenms, glpi, state, device)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                logging.exception(
                    "Failed to sync device_id=%s hostname=%s: %s",
                    device.get("device_id"),
                    device.get("hostname") or device.get("sysName"),
                    exc,
                )
        if not settings.dry_run:
            save_state(settings.state_file, state)
    finally:
        glpi.kill_session()

    if failures:
        logging.error("Done with %s failed device(s)", failures)
        return 1

    logging.info("Done")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
