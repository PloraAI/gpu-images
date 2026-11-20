from collections import defaultdict
import json
import re
from pathlib import Path

JSON_PATH = Path("all.json")
IMG_DIR = Path("front-thumb")
OUT_JSON = Path("missing_gpus.json")


def normalize_id(tpu_id: str | None) -> str | None:
    if not tpu_id or not isinstance(tpu_id, str):
        return None
    m = re.fullmatch(r"c(\d+)", tpu_id.strip().lower())
    return m.group(1) if m else None


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("JSON kök yapısı liste olmalı.")

    missing_items = []
    grouped: dict[str, dict] = defaultdict(lambda: {"count": 0, "sample": None})
    seen_ids: set[str] = set()

    for item in data:
        if not isinstance(item, dict):
            continue
        num_id = normalize_id(item.get("tpu_id"))
        if not num_id or num_id in seen_ids:
            continue
        seen_ids.add(num_id)

        img_path = IMG_DIR / f"c{num_id}.jpg"
        if not (img_path.exists() and img_path.stat().st_size > 0):
            raw_mfr = item.get("manufacturer")
            mfr = raw_mfr.strip() if isinstance(raw_mfr, str) and raw_mfr.strip() else "unknown"
            name = item.get("name") or item.get("tpu_id") or f"c{num_id}"

            entry = {
                "tpu_id": f"c{num_id}",
                "manufacturer": mfr,
                "name": name,
                "url": f"https://tpucdn.com/gpu-specs/images-new/c/{num_id}-front-thumb.jpg",
            }
            missing_items.append(entry)

            grouped[mfr]["count"] += 1
            if grouped[mfr]["sample"] is None:
                grouped[mfr]["sample"] = name

    OUT_JSON.write_text(
        json.dumps(missing_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # En çok eksik olan üreticiden aza doğru sırala
    sorted_groups = sorted(
        grouped.items(),
        key=lambda kv: kv[1]["count"],
        reverse=True,
    )

    print(f"Toplam indirilemeyen: {len(missing_items)}\n")
    for mfr, info in sorted_groups:
        print(f"{mfr} ({info['count']} tane) - {info['sample']}")


if __name__ == "__main__":
    main()