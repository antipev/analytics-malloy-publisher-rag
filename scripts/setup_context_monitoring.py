#!/usr/bin/env python3
"""Create the uptime check and alert policy for the RAG context endpoint.

Why an uptime check and not a metric alert: the signal we care about is inside the
response body (`contexts_indexed == contexts_expected`), and Cloud Run exposes no
metric for it. An uptime check can assert on the body cheaply, from outside the
project, exactly like a user would.

Two objects, both idempotent by display name:

  uptimeCheckConfigs   GET https://<service>/context/healthz every 60 s, must
                       contain `"missing":[]` in the body
  alertPolicies        fires when that check fails twice in a row, notifies the
                       existing email channel

Usage:
  scripts/setup_context_monitoring.py --project my-1-st-project-training
  scripts/setup_context_monitoring.py --dry-run          # print, create nothing
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

BASE = "https://monitoring.googleapis.com/v3/projects/{project}"
CHECK_NAME = "malloy-publisher RAG context coverage"
POLICY_NAME = "RAG context coverage — malloy_getContext has every context"


def token() -> str:
    tok = os.environ.get("ACCESS_TOKEN")
    if tok:
        return tok
    try:
        return subprocess.run(["gcloud", "auth", "print-access-token"], check=True,
                              capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        sys.exit(f"cannot get an access token from gcloud: {exc}")


def call(method: str, url: str, body=None, dry_run=False):
    if dry_run and method != "GET":
        print(f"[dry-run] {method} {url}\n{json.dumps(body, indent=2)}")
        return None
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token()}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        sys.exit(f"{method} {url} -> HTTP {exc.code}\n{detail}")


def existing(url: str, key: str, display_name: str):
    for item in (call("GET", url) or {}).get(key, []):
        if item.get("displayName") == display_name:
            return item
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=os.environ.get("PROJECT_ID",
                                                        "my-1-st-project-training"))
    ap.add_argument("--service-url", default=os.environ.get("SERVICE_URL", ""),
                    help="Cloud Run URL (default: read from the service)")
    ap.add_argument("--service", default="malloy-publisher-mcp")
    ap.add_argument("--region", default="northamerica-northeast1")
    ap.add_argument("--channel", default="",
                    help="notification channel resource name (default: first email channel)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    url = args.service_url
    if not url:
        url = subprocess.run(["gcloud", "run", "services", "describe", args.service,
                              "--project", args.project, "--region", args.region,
                              "--format", "value(status.url)"],
                             check=True, capture_output=True, text=True).stdout.strip()
    host = url.split("//", 1)[-1].strip("/")
    print(f"service host: {host}")

    base = BASE.format(project=args.project)
    checks_url = f"{base}/uptimeCheckConfigs"
    check = existing(checks_url, "uptimeCheckConfigs", CHECK_NAME)
    if check:
        print(f"uptime check exists: {check['name']}")
    else:
        check = call("POST", checks_url, {
            "displayName": CHECK_NAME,
            "period": "60s",
            "timeout": "10s",
            "httpCheck": {
                "requestMethod": "GET",
                "path": "/context/healthz",
                "port": 443,
                "useSsl": True,
                "validateSsl": True,
            },
            "monitoredResource": {
                "type": "uptime_url",
                "labels": {"project_id": args.project, "host": host},
            },
            # The body is the signal: contexts_indexed == contexts_expected is printed
            # as an empty `missing` list, so a 200 with a stale index still fails.
            "contentMatchers": [{"content": '"missing":[]', "matcher": "CONTAINS_STRING"}],
            "selectedRegions": ["USA", "EUROPE", "ASIA_PACIFIC"],
        }, args.dry_run)
        if check:
            print(f"uptime check created: {check['name']}")
    check_id = (check or {}).get("name", "").rsplit("/", 1)[-1]

    channel = args.channel
    if not channel:
        channels = (call("GET", f"{base}/notificationChannels") or {}).get(
            "notificationChannels", [])
        email = [c["name"] for c in channels if c.get("type") == "email"]
        channel = email[0] if email else ""
        print(f"notification channel: {channel or '<none found - policy will have none>'}")

    policies_url = f"{base}/alertPolicies"
    if existing(policies_url, "alertPolicies", POLICY_NAME):
        print(f"alert policy exists: {POLICY_NAME}")
        return 0

    policy = {
        "displayName": POLICY_NAME,
        "combiner": "OR",
        "conditions": [{
            "displayName": "uptime check failing on /context/healthz",
            "conditionThreshold": {
                "filter": ('metric.type="monitoring.googleapis.com/uptime_check/check_passed"'
                           ' AND resource.type="uptime_url"'
                           f' AND metric.labels.check_id="{check_id}"'),
                "comparison": "COMPARISON_GT",
                "thresholdValue": 0,
                "duration": "300s",
                "trigger": {"count": 2},
                "aggregations": [{
                    "alignmentPeriod": "300s",
                    "perSeriesAligner": "ALIGN_NEXT_OLDER",
                    "crossSeriesReducer": "REDUCE_COUNT_FALSE",
                    "groupByFields": ["resource.label.host"],
                }],
            },
        }],
        "alertStrategy": {"autoClose": "1800s"},
        "documentation": {
            "mimeType": "text/markdown",
            "content": ("malloy_getContext is answering without a full RAG context: "
                        "/context/healthz no longer reports \"missing\":[]. Run "
                        "scripts/verify_context_coverage.py against the service, then see "
                        "DEPLOYMENT.md, section 'Context health, probes and token rotation'."),
        },
    }
    if channel:
        policy["notificationChannels"] = [channel]
    call("POST", policies_url, policy, args.dry_run)
    print(f"alert policy created: {POLICY_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
