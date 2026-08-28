"""One observed public asset through production I/O; stdin only, no browser/AI.

Main supplies a locator already observed in an approved original page. It never
appears in argv, logs, a manifest, or retained output. This checks the downloader
and media probe, not the full worker/backend ownership chain or platform extractor.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from tools.enrichment_worker_protocol import EnrichmentError, strict_json
from tools.product_media import MediaDownloader, MediaError, MediaProbe, MediaStaging

MAX_BYTES = 6 * 1024 * 1024


async def run(value: dict) -> dict:
    if (
        type(value) is not dict
        or set(value) != {"platform", "kind", "url"}
        or type(value["platform"]) is not str
        or value["platform"] not in {"dy", "wb", "ks", "xhs", "toutiao"}
        or type(value["kind"]) is not str
        or value["kind"] not in {"image", "video"}
        or type(value["url"]) is not str
        or not 0 < len(value["url"]) <= 8192
    ):
        return {"outcome": "invalid_input"}
    result = {"platform": value["platform"], "kind": value["kind"]}
    with tempfile.TemporaryDirectory(prefix="longtian-live-media.") as path:
        root = Path(path).resolve()
        root.chmod(0o700)
        request_id = str(uuid4())
        operation = root / request_id.replace("-", "")
        operation.mkdir(mode=0o700)
        staging = MediaStaging(root, request_id)
        downloader = MediaDownloader(
            platform=value["platform"], max_total_bytes=MAX_BYTES
        )
        try:
            descriptor = await downloader.download(value["url"], staging)
            metadata = await MediaProbe(os.environ.get("MEDIACRAWLER_FFPROBE")).inspect(
                staging,
                descriptor["handle"],
                value["kind"],
                descriptor["declared_mime"],
            )
            result.update(
                outcome="ready",
                byte_size=descriptor["byte_size"],
                metadata=metadata,
            )
        except MediaError as error:
            result["outcome"] = error.code
        except EnrichmentError:
            result["outcome"] = "staging_unavailable"
        finally:
            try:
                await downloader.close()
            finally:
                staging.close(keep=False)
        result["owned_operation_empty"] = not tuple(operation.iterdir())
    result["temporary_root_removed"] = not root.exists()
    return result


def main() -> None:
    try:
        encoded = sys.stdin.buffer.read(16385)
        if len(encoded) > 16384:
            result = {"outcome": "invalid_input"}
        else:
            result = asyncio.run(run(strict_json(encoded)))
    except Exception:
        # Never expose exception messages carrying source URLs or temp paths.
        result = {"outcome": "probe_internal_error"}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
