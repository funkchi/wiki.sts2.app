#!/usr/bin/env python3
"""Stage, verify, promote, and record the first-party media cutover in R2.

Drives the upload half of plan_first_party_cutover.py's output through the
deployment gate the replacement plan requires:

    stage           upload every planned object to staging/<version>/<key>
    verify-staging  download each staged object and compare its sha256
    promote         re-upload verified objects to their stable keys
    verify-stable   download each stable object and compare its sha256
    finalize        regenerate data/media-manifest.json from verified objects

Progress is checkpointed in artifacts/generated-media/staging-state.json, so
an interrupted phase resumes where it stopped. Every phase refuses to run
before the previous phase has fully passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

PLAN = Path("artifacts/generated-media/cutover-plan.json")
STATE = Path("artifacts/generated-media/staging-state.json")
MANIFEST = Path("data/media-manifest.json")
BUCKET = "wiki-sts2"
# Namespaces the cutover does not touch; their manifest entries are preserved.
KEPT_NAMESPACES = ("enemies/", "characters/")

PHASES = ["stage", "verify-staging", "promote", "verify-stable", "finalize"]


# R2's S3-compatible API, authenticated by the [r2] profile in
# ~/.aws/credentials. boto3 clients are thread-safe, so one client serves the
# whole worker pool; transient failures retry with backoff.
ENDPOINT = "https://2009c1445d1dcf5da9f3fcc64aaddea1.r2.cloudflarestorage.com"
RETRIES = 4

_s3 = None


def s3():
    global _s3
    if _s3 is None:
        import boto3
        from botocore.config import Config

        _s3 = boto3.Session(profile_name="r2").client(
            "s3",
            endpoint_url=ENDPOINT,
            config=Config(max_pool_connections=64, retries={"max_attempts": 3}),
        )
    return _s3


def with_retries(operation) -> str | None:
    for attempt in range(RETRIES):
        try:
            operation()
            return None
        except Exception as error:  # noqa: BLE001 - report, don't crash the pool
            last = f"{type(error).__name__}: {error}"
            time.sleep(2**attempt)
    return last


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def put(key: str, path: str) -> str | None:
    return with_retries(
        lambda: s3().upload_file(
            path,
            BUCKET,
            key,
            ExtraArgs={
                "ContentType": "image/webp",
                "CacheControl": "public, max-age=604800",
            },
        )
    )


def fetch_sha(key: str) -> tuple[str | None, str | None]:
    result: dict[str, str] = {}

    def fetch() -> None:
        digest = hashlib.sha256()
        body = s3().get_object(Bucket=BUCKET, Key=key)["Body"]
        for chunk in iter(lambda: body.read(1024 * 1024), b""):
            digest.update(chunk)
        result["sha256"] = digest.hexdigest()

    error = with_retries(fetch)
    if error:
        return None, error
    return result["sha256"], None


def load_state(version: str, entries: list[dict]) -> dict:
    if STATE.exists():
        state = json.loads(STATE.read_text())
        if state["version"] == version:
            return state
        raise SystemExit(
            f"state file is for version {state['version']}; "
            f"pass --version {state['version']} to resume or delete {STATE}"
        )
    return {
        "version": version,
        "entries": {
            entry["key"]: {"sha256": entry["sha256"], "path": entry["path"]}
            for entry in entries
        },
    }


def run_phase(
    label: str,
    state: dict,
    work: list[tuple[str, dict]],
    action,
    workers: int,
) -> int:
    lock = Lock()
    failures = 0
    done = 0

    def wrapped(item: tuple[str, dict]) -> tuple[str, str | None]:
        key, record = item
        return key, action(key, record)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(wrapped, item) for item in work]
        for future in as_completed(futures):
            key, error = future.result()
            with lock:
                done += 1
                if error:
                    failures += 1
                    state["entries"][key][f"{label}Error"] = error
                    print(f"error: {key}: {error}", file=sys.stderr)
                else:
                    state["entries"][key].pop(f"{label}Error", None)
                if done % 50 == 0 or done == len(work):
                    STATE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
                    print(f"{label}: {done}/{len(work)} ({failures} failures)", file=sys.stderr)
    STATE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    return failures


def require(state: dict, flag: str, phase: str) -> None:
    missing = [key for key, record in state["entries"].items() if not record.get(flag)]
    if missing:
        raise SystemExit(
            f"{phase} requires every object to have passed the previous phase; "
            f"{len(missing)} have not (first: {missing[0]})"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=PHASES)
    parser.add_argument("--version", required=True, help="staging prefix version, e.g. 2026-07-28")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--plan", type=Path, default=PLAN)
    args = parser.parse_args(argv)

    plan = json.loads(args.plan.read_text())
    if plan.get("errors"):
        raise SystemExit("refusing to act on a cutover plan that has errors")
    entries = plan["uploadEntries"]
    state = load_state(args.version, entries)
    staging = f"staging/{args.version}"

    if args.phase == "stage":
        work = [
            (key, record)
            for key, record in state["entries"].items()
            if not record.get("staged")
        ]

        def stage(key: str, record: dict) -> str | None:
            error = put(f"{staging}/{key}", record["path"])
            if error is None:
                record["staged"] = True
            return error

        failures = run_phase("stage", state, work, stage, args.workers)
        print(f"staged {len(work) - failures}/{len(work)} objects", file=sys.stderr)
        return 1 if failures else 0

    if args.phase == "verify-staging":
        require(state, "staged", args.phase)
        work = [
            (key, record)
            for key, record in state["entries"].items()
            if record.get("stagedVerified") != record["sha256"]
        ]

        def verify(key: str, record: dict) -> str | None:
            digest, error = fetch_sha(f"{staging}/{key}")
            if error:
                return error
            if digest != record["sha256"]:
                return f"staged sha256 {digest} != expected {record['sha256']}"
            record["stagedVerified"] = digest
            return None

        failures = run_phase("verifyStaging", state, work, verify, args.workers)
        print(f"verified {len(work) - failures}/{len(work)} staged objects", file=sys.stderr)
        return 1 if failures else 0

    if args.phase == "promote":
        require(state, "stagedVerified", args.phase)
        work = [
            (key, record)
            for key, record in state["entries"].items()
            if not record.get("promoted")
        ]

        def promote(key: str, record: dict) -> str | None:
            error = put(key, record["path"])
            if error is None:
                record["promoted"] = True
            return error

        failures = run_phase("promote", state, work, promote, args.workers)
        print(f"promoted {len(work) - failures}/{len(work)} objects", file=sys.stderr)
        return 1 if failures else 0

    if args.phase == "verify-stable":
        require(state, "promoted", args.phase)
        work = [
            (key, record)
            for key, record in state["entries"].items()
            if record.get("stableVerified") != record["sha256"]
        ]

        def verify(key: str, record: dict) -> str | None:
            digest, error = fetch_sha(key)
            if error:
                return error
            if digest != record["sha256"]:
                return f"stable sha256 {digest} != expected {record['sha256']}"
            record["stableVerified"] = digest
            return None

        failures = run_phase("verifyStable", state, work, verify, args.workers)
        print(f"verified {len(work) - failures}/{len(work)} stable objects", file=sys.stderr)
        return 1 if failures else 0

    # finalize
    require(state, "stableVerified", args.phase)
    previous = json.loads(MANIFEST.read_text())["items"]
    items = {
        key: value
        for key, value in previous.items()
        if key.startswith(KEPT_NAMESPACES)
    }
    for entry in entries:
        items[entry["key"]] = {
            "source_url": f"first-party:{entry['path']}",
            "sha256": entry["sha256"],
            "size": entry["size"],
        }
    dropped = sorted(key for key in previous if key not in items)
    MANIFEST.write_text(
        json.dumps({"schema_version": 1, "items": dict(sorted(items.items()))}, indent=2)
        + "\n"
    )
    print(
        f"manifest: {len(items)} items ({len(entries)} first-party, "
        f"{len(items) - len(entries)} kept); {len(dropped)} dropped",
        file=sys.stderr,
    )
    for key in dropped:
        print(f"dropped from manifest (object remains in R2): {key}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
