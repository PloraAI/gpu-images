import asyncio
import json
import re
import shutil
from pathlib import Path
import httpx

BASE_DIR = Path(__file__).resolve().parent
JSON_PATH = BASE_DIR / "gpu_database.json"
REMOTE_JSON_URL = (
    "https://raw.githubusercontent.com/PloraAI/gpu-database/refs/heads/main/data/all.json"
)
OUT_DIR = BASE_DIR / "front-thumb"
LOCAL_PLACEHOLDER = BASE_DIR / "templates" / "placeholder.jpg"

CONCURRENCY = 10
TIMEOUT = 15.0
MAX_RETRIES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
    "Referer": "https://www.techpowerup.com/gpu-specs/",
    "Connection": "keep-alive",
}


async def ensure_database_json() -> None:
    if JSON_PATH.exists() and JSON_PATH.stat().st_size > 0:
        return

    print(f"{JSON_PATH.name} bulunamadı, indiriliyor: {REMOTE_JSON_URL}")
    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        resp = await client.get(REMOTE_JSON_URL)
        resp.raise_for_status()
        tmp_path = JSON_PATH.with_suffix(".json.part")
        tmp_path.write_bytes(resp.content)
        tmp_path.replace(JSON_PATH)

    print(f"{JSON_PATH.name} kaydedildi ({JSON_PATH.stat().st_size} byte).")


def normalize_id(tpu_id: str | None) -> str | None:
    if not tpu_id or not isinstance(tpu_id, str):
        return None
    cleaned = tpu_id.strip().lower()
    match = re.fullmatch(r"c(\d+)", cleaned)
    return match.group(1) if match else None


def normalize_brand(manufacturer: str | None) -> str:
    if not manufacturer or not isinstance(manufacturer, str):
        return "unknown"
    brand = manufacturer.strip().lower()
    brand = re.sub(r"[^a-z0-9]+", "_", brand).strip("_")
    return brand or "unknown"


def is_valid_image(content: bytes, content_type: str) -> bool:
    if not content or len(content) < 64:
        return False
    ct = content_type.lower()
    if "text/html" in ct or "text/plain" in ct or content[:5].lower() == b"<!doc":
        return False

    # Signature control for JPEG, PNG, GIF, WEBP
    is_jpeg = content[:2] == b"\xff\xd8"
    is_png = content[:8] == b"\x89PNG\r\n\x1a\n"
    is_gif = content[:6] in (b"GIF87a", b"GIF89a")
    is_webp = len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"

    return is_jpeg or is_png or is_gif or is_webp or "image/" in ct


async def fetch_image(client: httpx.AsyncClient, url: str) -> bytes | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(url)

            if resp.status_code == 404:
                return None

            if resp.status_code in (429, 500, 502, 503, 504):
                await asyncio.sleep(attempt * 1.5)
                continue

            resp.raise_for_status()
            content = resp.content
            content_type = resp.headers.get("content-type", "")

            if is_valid_image(content, content_type):
                return content
            return None

        except (httpx.TimeoutException, httpx.TransportError):
            if attempt == MAX_RETRIES:
                return None
            await asyncio.sleep(attempt * 1.0)
        except httpx.HTTPError:
            return None

    return None


def write_bytes_atomic(dest: Path, content: bytes) -> None:
    tmp_path = dest.with_suffix(".jpg.part")
    tmp_path.write_bytes(content)
    tmp_path.replace(dest)


def copy_local_placeholder(dest: Path) -> bool:
    if not LOCAL_PLACEHOLDER.exists() or LOCAL_PLACEHOLDER.stat().st_size == 0:
        return False
    tmp_path = dest.with_suffix(".jpg.part")
    shutil.copyfile(LOCAL_PLACEHOLDER, tmp_path)
    tmp_path.replace(dest)
    return True


async def process_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    num_id: str,
    brand: str,
    stats: dict[str, int],
) -> None:
    dest = OUT_DIR / f"c{num_id}.jpg"

    if dest.exists() and dest.stat().st_size > 0:
        stats["skipped"] += 1
        return

    async with sem:
        # 1. Main image
        main_url = f"https://tpucdn.com/gpu-specs/images-new/c/{num_id}-front-thumb.jpg"
        content = await fetch_image(client, main_url)
        if content is not None:
            write_bytes_atomic(dest, content)
            stats["downloaded"] += 1
            return

        # 2. Brand desktop placeholder
        desktop_url = f"https://www.techpowerup.com/gpudb/placeholder_{brand}_desktop"
        content = await fetch_image(client, desktop_url)
        if content is None:
            content = await fetch_image(client, f"{desktop_url}.jpg")
        if content is not None:
            write_bytes_atomic(dest, content)
            stats["placeholder_desktop"] += 1
            return

        # 3. Brand laptop placeholder
        laptop_url = f"https://www.techpowerup.com/gpudb/placeholder_{brand}_laptop"
        content = await fetch_image(client, laptop_url)
        if content is None:
            content = await fetch_image(client, f"{laptop_url}.jpg")
        if content is not None:
            write_bytes_atomic(dest, content)
            stats["placeholder_laptop"] += 1
            return

        # 4. Local templates/placeholder.jpg
        if copy_local_placeholder(dest):
            stats["placeholder_local"] += 1
        else:
            stats["missing_local_template"] += 1


async def main() -> None:
    await ensure_database_json()

    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("The JSON root structure must be a list ([{...}, {...}]).")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    targets: list[tuple[str, str]] = []
    seen: set[str] = set()
    invalid_ids = 0

    for item in data:
        if not isinstance(item, dict):
            continue
        num_id = normalize_id(item.get("tpu_id"))
        if not num_id:
            invalid_ids += 1
            continue
        if num_id not in seen:
            seen.add(num_id)
            brand = normalize_brand(item.get("manufacturer"))
            targets.append((num_id, brand))

    stats = {
        "downloaded": 0,
        "skipped": 0,
        "placeholder_desktop": 0,
        "placeholder_laptop": 0,
        "placeholder_local": 0,
        "missing_local_template": 0,
    }

    sem = asyncio.Semaphore(CONCURRENCY)
    limits = httpx.Limits(
        max_connections=CONCURRENCY * 2,
        max_keepalive_connections=CONCURRENCY,
    )

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=TIMEOUT,
        limits=limits,
        follow_redirects=True,
    ) as client:
        tasks = [
            process_one(client, sem, num_id, brand, stats)
            for num_id, brand in targets
        ]
        for idx, coro in enumerate(asyncio.as_completed(tasks), start=1):
            await coro
            if idx % 250 == 0 or idx == len(tasks):
                print(f"[{idx}/{len(tasks)}] -> {stats}")

    print("\nDone!")
    print(f"Unique ID count          : {len(targets)}")
    print(f"Invalid tpu_id           : {invalid_ids}")
    print(f"Already there (skipped)  : {stats['skipped']}")
    print(f"Downloaded (front-thumb) : {stats['downloaded']}")
    print(f"Desktop placeholder      : {stats['placeholder_desktop']}")
    print(f"Laptop placeholder       : {stats['placeholder_laptop']}")
    print(f"Local placeholder.jpg    : {stats['placeholder_local']}")
    print(f"Local template not found : {stats['missing_local_template']}")


if __name__ == "__main__":
    asyncio.run(main())