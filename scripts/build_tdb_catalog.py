from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import re
from collections import deque
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

BASE = "https://www.tuning-database.co.uk"
ROBOTS = f"{BASE}/robots.txt"
DATA_FILE = Path("data/catalog.json")
SEED_FILE = Path("data/seed.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ChipTuningCatalog/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def get_int(pattern: str, text: str, flags: int = re.I) -> int | None:
    m = re.search(pattern, text, flags)
    return int(m.group(1)) if m else None


async def fetch_bytes(session: aiohttp.ClientSession, url: str) -> bytes | None:
    for attempt in range(3):
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=35),
                allow_redirects=True,
            ) as response:
                if response.status != 200:
                    raise RuntimeError(f"{response.status}")
                return await response.read()
        except Exception:
            if attempt == 2:
                return None
            await asyncio.sleep(1.5 * (attempt + 1))
    return None


def decode_payload(data: bytes, url: str) -> str:
    if url.endswith(".gz") or data[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(data)
        except Exception:
            pass
    return data.decode("utf-8", errors="ignore")


async def discover_sitemaps(session: aiohttp.ClientSession) -> list[str]:
    result: set[str] = set()

    robots = await fetch_bytes(session, ROBOTS)
    if robots:
        text = decode_payload(robots, ROBOTS)
        for line in text.splitlines():
            if line.lower().startswith("sitemap:"):
                result.add(line.split(":", 1)[1].strip())

    for candidate in (
        f"{BASE}/sitemap_index.xml",
        f"{BASE}/wp-sitemap.xml",
        f"{BASE}/product-sitemap.xml",
        f"{BASE}/product-sitemap1.xml",
    ):
        result.add(candidate)

    return sorted(result)


async def discover_profile_urls(session: aiohttp.ClientSession) -> list[str]:
    queue = deque(await discover_sitemaps(session))
    seen: set[str] = set()
    profiles: set[str] = set()

    while queue:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)

        raw = await fetch_bytes(session, url)
        if not raw:
            continue

        text = decode_payload(raw, url)
        low = text.lower()

        if "<sitemapindex" in low or "<urlset" in low:
            soup = BeautifulSoup(text, "xml")
            for loc in soup.find_all("loc"):
                target = loc.get_text(strip=True)
                if "/custom-file/" in target:
                    profiles.add(target.rstrip("/") + "/")
                elif target.startswith("http") and target not in seen:
                    queue.append(target)

        # Fallback for non-XML pages / indexes.
        for target in re.findall(
            r"https?://[^\s<\"']+/custom-file/[^\s<\"']+",
            text,
            re.I,
        ):
            profiles.add(target.rstrip("/") + "/")

    return sorted(profiles)


def text_lines(soup: BeautifulSoup) -> list[str]:
    return [
        norm(x)
        for x in soup.stripped_strings
        if norm(x)
    ]


def field_after(label: str, lines: list[str]) -> str | None:
    for i, line in enumerate(lines):
        if line.lower() == label.lower() and i + 1 < len(lines):
            return lines[i + 1]
    return None


def parse_profile(url: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    lines = text_lines(soup)
    text = " ".join(lines)

    h1 = soup.find("h1")
    title = norm(h1.get_text(" ", strip=True) if h1 else "")
    if not title:
        return None

    brand = field_after("Vehicle make", lines)
    model = field_after("Vehicle model", lines)
    year = field_after("Model year", lines)

    if not brand or not model:
        # Fallback from H1: "BMW E46 328i Petrol ... Stage 1"
        bits = title.split()
        brand = brand or (bits[0] if bits else "Unknown")
        model = model or (bits[1] if len(bits) > 1 else "Unknown")

    displacement = field_after("Displacement", lines)
    fuel = field_after("Fuel / Induction", lines)
    engine_code = field_after("OEM engine code", lines)

    factory = re.search(
        r"FACTORY\s*(\d+)\s*hp\s*(\d+)\s*Nm.*?STAGE\s*1\s*(\d+)\s*hp\s*(\d+)\s*Nm",
        text,
        re.I,
    )

    if not factory:
        factory = re.search(
            r"Original reference\s*STAGE\s*1\s*(\d+)\s*hp\s*(\d+)\s*Nm.*?OEM\s*(\d+)\s*hp",
            text,
            re.I,
        )
        if factory:
            stage_hp = int(factory.group(1))
            stage_nm = int(factory.group(2))
            stock_hp = int(factory.group(3))
            # Torque baseline can be recovered from an explicit "+X Nm".
            gain = re.search(r"STAGE\s*1\s*\d+\s*hp\s*\d+\s*Nm\s*\+\d+\s*hp\s*·\s*\+(\d+)\s*Nm", text, re.I)
            stock_nm = stage_nm - int(gain.group(1)) if gain else None
        else:
            return None
    else:
        stock_hp = int(factory.group(1))
        stock_nm = int(factory.group(2))
        stage_hp = int(factory.group(3))
        stage_nm = int(factory.group(4))

    if not stock_hp or not stage_hp:
        return None

    engine = " ".join(x for x in (displacement, fuel, engine_code) if x) or title

    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    return {
        "id": f"tdb-{slug}",
        "brand": brand,
        "model": model,
        "year": year or "",
        "engine": engine,
        "fuel": fuel or "Не указано",
        "stock_hp": stock_hp,
        "stage1_hp": stage_hp,
        "stock_nm": stock_nm,
        "stage1_nm": stage_nm if 'stage_nm' in locals() else None,
        "price_rub": None,
        "source_url": url,
        "image_url": None,
        "graph_url": None,
    }


async def crawl(limit: int, concurrency: int) -> list[dict]:
    connector = aiohttp.TCPConnector(
        limit=concurrency,
        limit_per_host=concurrency,
        ssl=False,
    )

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        urls = await discover_profile_urls(session)
        print(f"profile urls discovered: {len(urls)}", flush=True)
        if limit > 0:
            urls = urls[:limit]

        sem = asyncio.Semaphore(concurrency)

        async def one(url: str) -> dict | None:
            async with sem:
                raw = await fetch_bytes(session, url)
            if not raw:
                return None
            return parse_profile(url, decode_payload(raw, url))

        results: list[dict] = []
        for start in range(0, len(urls), concurrency * 10):
            batch = urls[start:start + concurrency * 10]
            parsed = await asyncio.gather(*(one(url) for url in batch))
            results.extend(x for x in parsed if x)
            print(
                f"profiles parsed: {min(start + len(batch), len(urls))}/{len(urls)} "
                f"valid={len(results)}",
                flush=True,
            )

        return results


def write_catalog(items: list[dict]) -> None:
    seed = json.loads(SEED_FILE.read_text(encoding="utf-8")) if SEED_FILE.exists() else []
    merged = {str(x["id"]): x for x in seed}
    for item in items:
        merged[str(item["id"])] = item

    data = sorted(
        merged.values(),
        key=lambda x: (
            str(x.get("brand", "")).lower(),
            str(x.get("model", "")).lower(),
            str(x.get("engine", "")).lower(),
        ),
    )

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    brands = len({x.get("brand") for x in data})
    models = len({(x.get("brand"), x.get("model")) for x in data})
    print(f"catalog={len(data)} entries, brands={brands}, models={models}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="0 = all profiles")
    parser.add_argument("--concurrency", type=int, default=16)
    args = parser.parse_args()

    items = asyncio.run(crawl(args.limit, args.concurrency))
    write_catalog(items)


if __name__ == "__main__":
    main()
