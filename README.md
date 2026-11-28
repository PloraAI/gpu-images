# GPU Images

Front-thumbnail image asset collection and automated downloader for **JascalAI/gpu-database**, sourced from **TechPowerUp** (`tpucdn.com` and `techpowerup.com`).

## Overview

This repository stores GPU thumbnail assets (`front-thumb/{tpu_id}.jpg`) mapped by `tpu_id` alongside the Python automation script used to fetch and populate missing thumbnails.

How the downloader works:
1. Checks if `gpu_database.json` exists locally; if missing, it downloads `all.json` from [`JascalAI/gpu-database`](https://github.com/JascalAI/gpu-database/blob/main/data/all.json) and saves it as `gpu_database.json`.
2. Iterates through unique `tpu_id` values and skips any file already present in `front-thumb/`.
3. Downloads the primary thumbnail from `https://tpucdn.com/gpu-specs/images-new/c/{id}-front-thumb.jpg`.
4. If unavailable, falls back in order to:
   - TechPowerUp brand desktop placeholder (`https://www.techpowerup.com/gpudb/placeholder_{brand}_desktop` / `.jpg`)
   - TechPowerUp brand laptop placeholder (`https://www.techpowerup.com/gpudb/placeholder_{brand}_laptop` / `.jpg`)
   - Local fallback image at `templates/placeholder.jpg`

## Project Structure

```text
.
├── main.py                  # Async image downloader & fallback script
├── gpu_database.json        # Local GPU dataset (auto-downloaded if absent)
├── templates/
│   └── placeholder.jpg      # Local fallback image when remote assets are missing
└── front-thumb/
    └── {tpu_id}.jpg            # Output GPU thumbnails keyed by tpu_id
```

## Installation

1. Clone the repository:

```bash
git clone [https://github.com/JascalAI/gpu-images.git](https://github.com/JascalAI/gpu-images.git)
cd gpu-images
```

2. Create and activate a virtual environment, then install `httpx`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install httpx
```

## Usage

Make sure `templates/placeholder.jpg` is in place if you want local fallback coverage, then run:

```bash
python main.py
```

The script resumes automatically on subsequent runs by skipping existing non-empty files in `front-thumb/` and prints a summary breakdown (`skipped`, `downloaded`, `placeholder_desktop`, `placeholder_laptop`, `placeholder_local`) upon completion.

## Data Source & Related Repository

- **Specifications Database:** [`JascalAI/gpu-database`](https://github.com/JascalAI/gpu-database)
- **Image & Specs Source:** TechPowerUp GPU Database (`techpowerup.com` / `tpucdn.com`)