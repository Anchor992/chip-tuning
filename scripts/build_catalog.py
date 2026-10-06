from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

import aiohttp
from bs4 import BeautifulSoup

BASE = "https://avt.ru"
CATALOG = f"{BASE}/catalog/"
DATA_FILE = Path("data/catalog.json")
SEED_FILE = Path("data/seed.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}


def clean_num(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"\d+", value.replace(" ", ""))
    return int(m.group()) if m else None


def valid_item_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.netloc.endswith("avt.ru") and "/catalog/item/" in parsed.path and bool(
            parse_qs(parsed.query).get("id")
        )
    except Exception:
        return False


def item_id_from_url(url: str) -> int | None:
    try:
        value = parse_qs(urlparse(url).query).get("id", [None])[0]
        return int(value) if value else None
    except Exception:
        return None


def extract_item_links(html: str, base_url: str) -> set[str]:
    soup = BeautifulSoup(html, "lxml")
    links: set[str] = set()
    for a in soup.find_all("a", href=True):
        u = urljoin(base_url, a["href"])
        if valid_item_url(u):
            links.add(u.split("#", 1)[0])
    # Also catch URLs embedded in JSON/script blocks.
    for raw in re.findall(r"https?://[^\s\"']+/catalog/item/\?id=\d+", html):
        if valid_item_url(raw):
            links.add(raw)
    return links


def parse_item(url: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")

    title_node = soup.find("h1")
    title = title_node.get_text(" ", strip=True) if title_node else ""
    if not title:
        meta = soup.find("meta", attrs={"property": "og:title"})
        title = meta.get("content", "") if meta else ""

    if not title or "Чип-тюнинг" not in title:
        return None

    title_clean = re.sub(r"^Чип-тюнинг\s+", "", title, flags=re.I).strip()

    match = re.match(
        r"(?P<brand>\S+)\s+"
        r"(?P<model>.*?)\s+"
        r"(?P<year>20\d{2}(?:\s*->\s*[^\s]+)?(?:\s*-\s*\s*[^\s]+)?)\s+"
        r"(?P<engine>.+?)\s+(?P<hp>\d+)\s*hp$",
        title_clean,
        re.I,
    )

    if match:
        brand = match.group("brand").strip()
        model = match.group("model").strip()
        year = match.group("year").strip()
        engine = match.group("engine").strip()
    else:
        parts = title_clean.split()
        brand = parts[0] if parts else "Unknown"
        model = " ".join(parts[1:]) if len(parts) > 1 else "Unknown"
        year = ""
        engine = ""

    text = soup.get_text(" ", strip=True)

    power = re.search(
        r"Мощность двигателя.*?"
        r"После\s*\+?[-]?\s*\d+\s*л\.с\..*?"
        r"(?P<stock>\d+)\s*л\.с\..*?"
        r"(?P<stage>\d+)\s*л\.с\.",
        text,
        re.I | re.S,
    )
    if not power:
        return None

    torque = re.search(
        r"Крутящий момент.*?"
        r"После\s*\+?[-]?\s*\d+\s*Нм.*?"
        r"(?P<stock>\d+)\s*Нм.*?"
        r"(?P<stage>\d+)\s*Нм",
        text,
        re.I | re.S,
    )

    price = re.search(r"Стоимость работ:\s*([\d\s]+)", text, re.I)
    iid = item_id_from_url(url)
    if iid is None:
        return None

    image_url = None
    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        image_url = urljoin(url, og["content"])

    return {
        "id": f"avt-{iid}",
        "brand": brand,
        "model": model,
        "year": year,
        "engine": engine,
        "fuel": "Не указано",
        "stock_hp": int(power.group("stock")),
        "stage1_hp": int(power.group("stage")),
        "stock_nm": int(torque.group("stock")) if torque else None,
        "stage1_nm": int(torque.group("stage")) if torque else None,
        "price_rub": clean_num(price.group(1)) if price else None,
        "source_url": url,
        "image_url": image_url,
        "graph_url": None,
    }


async def fetch(session: aiohttp.ClientSession, url: str) -> str | None:
    candidates = [url]
    if url.startswith("https://avt.ru/"):
        candidates.append("https://r.jina.ai/http://" + url[len("https://"):])
        candidates.append("https://r.jina.ai/https://" + url[len("https://"):])

    for candidate in candidates:
        try:
            async with session.get(
                candidate,
                timeout=aiohttp.ClientTimeout(total=25),
                allow_redirects=True,
            ) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    if text:
                        return text
        except (aiohttp.ClientError, asyncio.TimeoutError):
            continue
    return None


async def discover_from_sitemaps(session: aiohttp.ClientSession) -> set[str]:
    found: set[str] = set()
    queue: deque[str] = deque([
        f"{BASE}/sitemap.xml",
        f"{BASE}/robots.txt",
        CATALOG,
    ])
    seen: set[str] = set()

    while queue:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)

        body = await fetch(session, url)
        if not body:
            continue

        low = body.lower()
        if "robots.txt" in url:
            for line in body.splitlines():
                if line.lower().startswith("sitemap:"):
                    target = line.split(":", 1)[1].strip()
                    if target and target not in seen:
                        queue.append(target)
        elif "<sitemapindex" in low or "<urlset" in low:
            soup = BeautifulSoup(body, "xml")
            for loc in soup.find_all("loc"):
                target = loc.get_text(strip=True)
                if valid_item_url(target):
                    found.add(target)
                elif target and target not in seen:
                    queue.append(target)
        else:
            found.update(extract_item_links(body, url))

    return found


async def crawl(start_id: int, end_id: int, concurrency: int) -> list[dict]:
    connector = aiohttp.TCPConnector(limit=concurrency, limit_per_host=concurrency, ssl=False)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        links = await discover_from_sitemaps(session)

        # Start from known working cards and follow "other modifications" links.
        seeds = [
            12579, 13791, 14297, 14321, 14338, 14240, 14606, 14125, 4206
        ]
        for iid in seeds:
            if start_id <= iid <= end_id:
                links.add(f"{BASE}/catalog/item/?id={iid}")

        queue = deque(sorted(links))
        seen: set[str] = set()
        items: dict[str, dict] = {}
        sem = asyncio.Semaphore(concurrency)

        async def visit(url: str) -> tuple[str, dict | None, set[str]]:
            async with sem:
                html = await fetch(session, url)
            if not html:
                return url, None, set()
            return url, parse_item(url, html), extract_item_links(html, url)

        while queue and len(seen) < max(20000, (end_id - start_id + 1)):
            batch = []
            while queue and len(batch) < concurrency * 4:
                url = queue.popleft()
                iid = item_id_from_url(url)
                if not iid or iid < start_id or iid > end_id or url in seen:
                    continue
                seen.add(url)
                batch.append(url)

            if not batch:
                continue

            results = await asyncio.gather(*(visit(url) for url in batch))
            for url, item, discovered in results:
                if item:
                    items[item["id"]] = item
                for new_url in discovered:
                    iid = item_id_from_url(new_url)
                    if iid and start_id <= iid <= end_id and new_url not in seen:
                        queue.append(new_url)

            if len(seen) % 100 < len(batch):
                print(f"visited={len(seen)} found={len(items)} queue={len(queue)}", flush=True)

            # If sitemap/graph discovery is sparse, fall back to a bounded ID sweep.
            if not queue and len(items) < 20:
                sweep = range(start_id, min(end_id, start_id + 5000) + 1)
                ids = [i for i in sweep if f"{BASE}/catalog/item/?id={i}" not in seen]
                for offset in range(0, len(ids), concurrency * 4):
                    part = ids[offset:offset + concurrency * 4]
                    res = await asyncio.gather(
                        *(visit(f"{BASE}/catalog/item/?id={i}") for i in part)
                    )
                    for url, item, discovered in res:
                        if item:
                            items[item["id"]] = item
                    if len(items) >= 20:
                        break

        return list(items.values())


def write_catalog(items: list[dict]) -> None:
    seed = json.loads(SEED_FILE.read_text(encoding="utf-8")) if SEED_FILE.exists() else []
    merged: dict[str, dict] = {str(x["id"]): x for x in seed}
    merged.update({str(x["id"]): x for x in items})
    ordered = sorted(
        merged.values(),
        key=lambda x: (
            str(x.get("brand", "")).lower(),
            str(x.get("model", "")).lower(),
            str(x.get("engine", "")).lower(),
        ),
    )
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    brands = len({str(x["brand"]) for x in ordered})
    print(f"catalog={len(ordered)} items, {brands} brands", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=16000)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    items = asyncio.run(crawl(args.start, args.end, args.concurrency))
    write_catalog(items)


if __name__ == "__main__":
    main()
