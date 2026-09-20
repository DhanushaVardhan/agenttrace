"""Deploy AgentTrace to Render's free tier from the public GitHub repo.

Render builds the Dockerfile server side, straight from the repository, so
this needs neither Docker nor git locally -- just an API key.

    python scripts/deploy_render.py --token rnd_xxx \\
        --repo https://github.com/<user>/agenttrace \\
        --gemini-key AQ.xxx

Standard library only, and deliberately so: on a machine whose HTTPS traffic
is re-signed by antivirus or a VPN, `urllib` validates against the operating
system's trust store, while anything built on `certifi` fails with
CERTIFICATE_VERIFY_FAILED.

Free-tier caveat, stated plainly: the service sleeps after 15 minutes of
inactivity and takes roughly a minute to wake. 750 instance-hours a month is
enough to run one service continuously.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

API = "https://api.render.com/v1"

# Render renamed its instance types; older workspaces still take "free".
PLAN_CANDIDATES = ["free", "starter"]

TERMINAL_OK = {"live"}
TERMINAL_BAD = {"build_failed", "update_failed", "canceled", "deactivated", "pre_deploy_failed"}


class RenderError(RuntimeError):
    pass


def call(token: str, method: str, path: str, payload=None):
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", "agenttrace-deploy")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:600]
        raise RenderError(f"{method} {path} -> HTTP {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise RenderError(f"{method} {path} -> network error: {exc.reason}") from None


def build_payload(name, owner_id, repo, plan, region, gemini_key, branch):
    return {
        "type": "web_service",
        "name": name,
        "ownerId": owner_id,
        "repo": repo,
        "branch": branch,
        "autoDeploy": "yes",
        "serviceDetails": {
            # Both keys are sent: the API renamed "env" to "runtime" and
            # different workspaces are still on different versions.
            "runtime": "docker",
            "env": "docker",
            "plan": plan,
            "region": region,
            "numInstances": 1,
            "healthCheckPath": "/api/health",
            "pullRequestPreviewsEnabled": "no",
            "envSpecificDetails": {
                "dockerfilePath": "./Dockerfile",
                "dockerContext": "./",
            },
        },
        "envVars": [{"key": "GEMINI_API_KEY", "value": gemini_key}],
    }


def find_existing(token: str, name: str):
    services = call(token, "GET", f"/services?name={name}&limit=20")
    for item in services:
        service = item.get("service", item)
        if service.get("name") == name:
            return service
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", required=True, help="Render API key (rnd_...)")
    parser.add_argument("--repo", required=True, help="Public GitHub repo URL")
    parser.add_argument("--gemini-key", required=True)
    parser.add_argument("--name", default="agenttrace")
    parser.add_argument("--branch", default="main")
    parser.add_argument(
        "--region",
        default="singapore",
        help="oregon | frankfurt | ohio | singapore | virginia",
    )
    parser.add_argument("--wait", type=int, default=900, help="Seconds to watch the build")
    args = parser.parse_args()

    token = args.token.strip()

    print("Authenticating with Render...")
    owners = call(token, "GET", "/owners?limit=10")
    if not owners:
        raise RenderError("This API key has no workspaces attached to it.")
    owner = owners[0].get("owner", owners[0])
    owner_id = owner["id"]
    print(f"  workspace: {owner.get('name') or owner_id}")

    existing = find_existing(token, args.name)
    if existing:
        service = existing
        print(f"  service '{args.name}' already exists - redeploying it")
        call(token, "POST", f"/services/{service['id']}/deploys", {"clearCache": "do_not_clear"})
    else:
        service = None
        last_error = ""
        for plan in PLAN_CANDIDATES:
            print(f"  creating service on plan '{plan}' in {args.region}...")
            payload = build_payload(
                args.name, owner_id, args.repo, plan, args.region, args.gemini_key, args.branch
            )
            try:
                created = call(token, "POST", "/services", payload)
                service = created.get("service", created)
                break
            except RenderError as exc:
                last_error = str(exc)
                if "plan" not in last_error.lower():
                    raise
                print(f"    plan '{plan}' rejected, trying the next one")
        if service is None:
            raise RenderError(f"Could not create the service. {last_error}")

    service_id = service["id"]
    url = (service.get("serviceDetails") or {}).get("url") or ""
    print(f"\n  service id: {service_id}")
    if url:
        print(f"  url:        {url}")
    print(f"  dashboard:  https://dashboard.render.com/web/{service_id}")

    # --- watch the build --------------------------------------------------
    print("\nBuilding. First build pulls node and python images, installs faiss")
    print("and runs an npm build, so 5-10 minutes is normal.\n")

    deadline = time.time() + args.wait
    seen = ""
    while time.time() < deadline:
        try:
            deploys = call(token, "GET", f"/services/{service_id}/deploys?limit=1")
        except RenderError as exc:
            print(f"  (status check failed: {exc})")
            time.sleep(20)
            continue

        if not deploys:
            time.sleep(15)
            continue

        deploy = deploys[0].get("deploy", deploys[0])
        status = deploy.get("status", "unknown")
        if status != seen:
            print(f"  [{time.strftime('%H:%M:%S')}] {status}")
            seen = status

        if status in TERMINAL_OK:
            print(f"\nLIVE: {url or 'check the dashboard for the URL'}")
            print("\nThe three sample PDFs are embedded in the background on first boot,")
            print("so give it another 30 seconds before asking the first question.")
            return 0
        if status in TERMINAL_BAD:
            print(f"\nBuild finished as '{status}'.")
            print(f"Read the build log at https://dashboard.render.com/web/{service_id}/logs")
            return 1

        time.sleep(15)

    print("\nStill building when the watch window ran out - that is not a failure.")
    print(f"Follow it at https://dashboard.render.com/web/{service_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RenderError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
