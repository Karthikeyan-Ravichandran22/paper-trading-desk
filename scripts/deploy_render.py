#!/usr/bin/env python3
"""Create/deploy paper-trading-desk on Render free tier via API."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.render.com/v1"
REPO = "https://github.com/Karthikeyan-Ravichandran22/paper-trading-desk"


def req(method: str, path: str, token: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        raise SystemExit(f"Render API {method} {path} failed ({e.code}): {err}") from e


def main() -> None:
    token = os.environ.get("RENDER_API_KEY") or os.environ.get("RENDER_TOKEN")
    if not token:
        raise SystemExit("RENDER_API_KEY missing")

    # Owner / credentials for Angel One from local env (never printed)
    env_vars = [
        {"key": "TRADING_MODE", "value": "PAPER"},
        {"key": "LIVE_TRADING_ENABLED", "value": "false"},
        {"key": "USE_DEMO_MARKET_DATA", "value": "false"},
        {"key": "SECRET_KEY", "generateValue": True},
        {"key": "DEFAULT_STARTING_CAPITAL", "value": "100000"},
        {"key": "DATABASE_URL", "value": "sqlite+aiosqlite:///./data/paper_trading.db"},
        {"key": "ANGEL_API_KEY", "value": os.environ.get("ANGEL_API_KEY", "")},
        {"key": "ANGEL_CLIENT_CODE", "value": os.environ.get("ANGEL_CLIENT_CODE", "")},
        {"key": "ANGEL_PASSWORD", "value": os.environ.get("ANGEL_PASSWORD", "")},
        {"key": "ANGEL_TOTP_SECRET", "value": os.environ.get("ANGEL_TOTP_SECRET", "")},
    ]

    status, owners = req("GET", "/owners", token)
    owner_list = owners if isinstance(owners, list) else owners.get("owner", owners)
    # API returns list of {owner:{...}} or similar
    owner_id = None
    if isinstance(owners, list) and owners:
        item = owners[0]
        owner_id = (item.get("owner") or item).get("id")
    if not owner_id:
        raise SystemExit(f"Could not resolve Render owner id: {owners}")

    payload = {
        "type": "web_service",
        "name": "paper-trading-desk",
        "ownerId": owner_id,
        "repo": REPO,
        "branch": "main",
        "autoDeploy": "yes",
        "serviceDetails": {
            "env": "docker",
            "plan": "free",
            "region": "oregon",
            "dockerfilePath": "./Dockerfile.web",
            "dockerContext": ".",
            "healthCheckPath": "/health",
            "envVars": env_vars,
        },
    }

    # If service exists, just return it
    _, services = req("GET", "/services?limit=50", token)
    existing = None
    for row in services if isinstance(services, list) else []:
        svc = row.get("service") or row
        if svc.get("name") == "paper-trading-desk":
            existing = svc
            break

    if existing:
        service = existing
        print(json.dumps({"action": "exists", "service": {"id": service.get("id"), "url": service.get("serviceDetails", {}).get("url") or service.get("url")}}))
    else:
        _, created = req("POST", "/services", token, payload)
        service = created.get("service") or created
        print(json.dumps({"action": "created", "id": service.get("id")}))

    sid = service.get("id")
    # Poll deploy
    for _ in range(60):
        _, detail = req("GET", f"/services/{sid}", token)
        svc = detail.get("service") or detail
        details = svc.get("serviceDetails") or {}
        url = details.get("url") or svc.get("url")
        deploys = None
        try:
            _, deploys = req("GET", f"/services/{sid}/deploys?limit=1", token)
        except SystemExit:
            pass
        state = None
        if isinstance(deploys, list) and deploys:
            state = (deploys[0].get("deploy") or deploys[0]).get("status")
        print(json.dumps({"id": sid, "url": url, "deploy_status": state}), flush=True)
        if state in ("live", "succeeded", "successful") or (url and state is None):
            if url:
                print(f"PUBLIC_URL=https://{url}" if not str(url).startswith("http") else f"PUBLIC_URL={url}")
                return
        if state in ("build_failed", "update_failed", "canceled", "deactivated"):
            raise SystemExit(f"Deploy failed: {state}")
        time.sleep(15)

    raise SystemExit("Timed out waiting for Render deploy")


if __name__ == "__main__":
    main()
