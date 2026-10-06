from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urljoin

import aiohttp
from bs4 import BeautifulSoup

BASE = "https://avt.ru"
DATA_FILE = Path("data/catalog.json")
SEED_FILE = Path("data/seed.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ChipTuningCatalog/1.0)",
    "Accept-Language": "ru-RU,ru;q=0.9",
}


def num(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"\d+", text.replace(" ", ""))
    return int(m.group()) if m else None


def parse_page(url: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)
    if not title:
        meta = soup.find("meta", attrs={"property": "og:title"})
        title = meta.get("content", "") if meta else ""
    if not title or "Чип-тюнинг" not in title:
        return None

    title = re.sub(r"^Чип-тюнинг\s+", "", title, flags=re.I).strip()

    # Example:
    # Volkswagen Golf 2012 -> 2017 1.4 TSI 140 hp
    match = re.search(
        r"^(?P<brand>\S+)\s+(?P<model>.*?)\s+"
        r"(?P<year>20\d{2}\s*(?:->|–|-)\s*[^\s]+)\s+"
        r"(?P<engine>.+?)\s+(?P<hp>\d+)\s*hp$",
        title,
        re.I,
    )
    if match:
        brand = match.group("brand")
        model = match.group("model").strip()
        year = match.group("year").strip()
        engine = match.group("engine").strip()
    else:
        parts = title.split()
        brand = parts[0]
        model = " ".join(parts[1:])
        year = ""
        engine = ""

    text = soup.get_text(" ", strip=True)

    # Exact Stage 1 block as currently rendered by AVT.
    power_match = re.search(
        r"Мощность двигателя.*?"
        r"После\s*\+?[\-]?\d+\s*л\.с\..*?"
        r"(?P<before>\d+)\s*л\.с\..*?"
        r"(?P<after>\d+)\s*л\.с\.",
        text,
        re.I,
    )
    torque_match = re.search(
        r"Крутящий момент.*?"
        r"После\s*\+?[\-]?\d+\s*Нм.*?"
        r"(?P<before>\d+)\s*Нм.*?"
        r"(?P<after>\d+)\s*Нм",
        text,
        re.I,
    )

    price_match = re.search(r"Стоимость работ:\s*([\d\s]+)", text, re.I)

    if not power_match:
        return None

    query_id = parse_qs(urlparse(url).query).get("id", [None])[0]
    if not query_id:
        return None

    stock_hp = int(power_match.group("before"))
    stage_hp = int(power_match.group("after"))
    stock_nm = int(torque_match.group("before")) if torque_match else None
    stage_nm = int(torque_match.group("after")) if torque_match else None
    price = num(price_match.group(1)) if price_match else None

    item = {
        "id": f"avt-{query_id}",
        "brand": brand,
        "model": model,
        "year": year,
        "engine": engine,
        "fuel": "Не указано",
        "stock_hp": stock_hp,
        "stage1_hp": stage_hp,
        "stock_nm": stock_nm,
        "stage1_nm": stage_nm,
        "price_rub": price,
        "source_url": url,
        "image_url": None,
        "graph_url": None,
    }

    # Prefer the source image when the page exposes one.
    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        item["image_url"] = urljoin(url, og["content"])

    return item


async def fetch(session: aiohttp.ClientSession, url: str) -> str | None:
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=20),
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None


async def crawl(start_id: int, end_id: int, concurrency: int) -> list[dict]:
    connector = aiohttp.TCPConnector(
        limit=concurrency,
        limit_per_host=concurrency,
        ssl=False,
    )
    timeout = aiohttp.ClientTimeout(total=25)
    sem = asyncio.Semaphore(concurrency)

    async with aiohttp.ClientSession(
        headers=HEADERS,
        connector=connector,
        timeout=timeout,
    ) as session:

        async def one(item_id: int) -> dict | None:
            url = f"{BASE}/catalog/item/?id={item_id}"
            async with sem:
                html = await fetch(session, url)
            return parse_page(url, html) if html else None

        results: list[dict] = []
        batch_size = max(50, concurrency * 5)
        for offset in range(start_id, end_id + 1, batch_size):
            batch_end = min(end_id, offset + batch_size - 1)
            batch = await asyncio.gather(
                *(one(i) for i in range(offset, batch_end + 1))
            )
            results.extend(item for item in batch if item)
            print(f"scanned {batch_end}/{end_id}; found {len(results)}")
        return results


def merge(items: list[dict]) -> None:
    seed = []
    if SEED_FILE.exists():
        seed = json.loads(SEED_FILE.read_text(encoding="utf-8"))

    existing = {}
    if DATA_FILE.exists():
        try:
            existing = {
                str(x["id"]): x
                for x in json.loads(DATA_FILE.read_text(encoding="utf-8"))
            }
        except Exception:
            existing = {}

    for item in seed:
        existing[str(item["id"])] = item
    for item in items:
        existing[str(item["id"])] = item

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(
        existing.values(),
        key=lambda x: (
            str(x.get("brand", "")).lower(),
            str(x.get("model", "")).lower(),
            str(x.get("engine", "")).lower(),
        ),
    )
    DATA_FILE.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"catalog written: {len(ordered)} items")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    items = asyncio.run(crawl(args.start, args.end, args.concurrency))
    merge(items)


if __name__ == "__main__":
    main()
