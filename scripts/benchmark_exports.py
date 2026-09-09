"""Read-only v4/v5 benchmark; prompts for a key without saving or printing it.

Example:
    uv run python scripts/benchmark_exports.py 2003 108958 --output benchmark.json
    # For a reporter, also pass --provider-id 64.
"""
from __future__ import annotations

import argparse
import getpass
import json
import statistics
import time
from pathlib import Path

import reportnet
from reportnet._util import zip_to_frames


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataflow_id", type=int)
    parser.add_argument("dataset_id", type=int)
    parser.add_argument("--provider-id", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = []
    with reportnet.ReportnetClient(api_key=getpass.getpass("Reportnet API key: ")) as client:
        expected = {t.name for t in client.get_schema(dataset_id=args.dataset_id).tables}
        # Sequential jobs with reversed second-pair order; timings include queueing.
        for version in (4, 5, 5, 4):
            started = time.perf_counter()
            handle = client.etl_export(
                dataflow_id=args.dataflow_id,
                dataset_id=args.dataset_id,
                provider_id=args.provider_id,
                version=version,
            )
            handle.wait(poll_interval=2, timeout=600)
            ready = time.perf_counter()
            # result() polls once again before downloading; included in download_seconds.
            payload = handle.result(timeout=600)
            downloaded = time.perf_counter()
            times = []
            for _ in range(5):
                parse_started = time.perf_counter()
                frames = zip_to_frames(payload)
                times.append(time.perf_counter() - parse_started)
            if set(frames) != expected:
                raise RuntimeError(f"Export tables {set(frames)} differ from schema {expected}")
            row = {
                "dataset_id": args.dataset_id,
                "version": version,
                "job_id": handle.job_id,
                "job_seconds": ready - started,
                "download_seconds": downloaded - ready,
                "bytes": len(payload),
                "parse_median_seconds": statistics.median(times),
                "tables": {name: list(frame.shape) for name, frame in frames.items()},
            }
            results.append(row)
            args.output.write_text(json.dumps(results, indent=2) + "\n")
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
