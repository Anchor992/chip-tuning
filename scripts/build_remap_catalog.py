from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

BASE = "https://remappingdata.com"
MAKES_INDEX = f"{BASE}/vehicle-manufacturers/"
DATA_FILE = Path("data/catalog.json")
SEED_FILE = Path("data/seed.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ChipTuningCatalog/1.0)",
    "Accept-Language": "en-GB,en;q=0.9",
}


def norm_num(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"\d{1,4}", text.replace(",", ""))
    return int(match.group()) if match else None


def clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def looks_like_make(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.endswith("remappingdata.com") and re.fullmatch(
        r"/make/[a-z0-9-]+/", parsed.path
    ) is not None


def looks_like_engine(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.endswith("remappingdata.com") and parsed.path.startswith("/engine/")


def extract_links(html: str, base_url: str, predicate) -> set[str]:
    soup = BeautifulSoup(html, "lxml")
    out = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"]).split("#", 1)[0]
        if predicate(url):
            out.add(url)
    return out


async def fetch(session: aiohttp.ClientSession, url: str) -> str | None:
    candidates = [
        url,
        "https://r.jina.ai/http://" + url[len("https://"):],
        "https://r.jina.ai/https://" + url[len("https://"):],
    ]

    for candidate in candidates:
        for attempt in range(2):
            try:
                async with session.get(
                    candidate,
                    timeout=aiohttp.ClientTimeout(total=35),
                    allow_redirects=True,
                ) as response:
                    if response.status == 200:
                        body = await response.text()
                        if len(body) > 1000:
                            return body
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt == 0:
                    await asyncio.sleep(1)
                continue

    return None


def page_numbers(html: str) -> set[int]:
    values = {1}
    for value in re.findall(r"[?&]mmpage=(\d+)", html):
        values.add(int(value))
    return values


async def discover_make_pages(session: aiohttp.ClientSession, make_url: str) -> list[str]:
    first = await fetch(session, make_url)
    if not first:
        return []

    pages = max(page_numbers(first))
    return [make_url if n == 1 else f"{make_url}?mmpage={n}" for n in range(1, pages + 1)]


async def discover_engine_urls(session: aiohttp.ClientSession, make_url: str) -> set[str]:
    pages = await discover_make_pages(session, make_url)
    if not pages:
        return set()

    sem = asyncio.Semaphore(8)

    async def one(url: str) -> set[str]:
        async with sem:
            html = await fetch(session, url)
        if not html:
            return set()
        return extract_links(html, url, looks_like_engine)

    results = await asyncio.gather(*(one(url) for url in pages))
    urls = set().union(*results)
    return urls


def parse_engine_title(title: str) -> tuple[str, str, str, str]:
    title = clean_spaces(title)
    parts = title.split()
    if not parts:
        return "Unknown", "Unknown", "", ""

    brand = parts[0]
    rest = parts[1:]

    # Remove terminal power and year fragments from the title.
    rest = re.sub(r"\b\d{2,4}\s*HP\b.*$", "", " ".join(rest), flags=re.I).strip()
    rest = re.sub(r"\b\d{4}\s*$", "", rest).strip()
    rest = re.sub(r"\b\d{4}\s*[-–]\s*\d{4}\s*$", "", rest).strip()

    tokens = rest.split()
    markers = re.compile(
        r"^(?:\d+(?:\.\d+)?[A-Za-z]*|V\d|I\d|"
        r"TFSI|TSI|TDI|CDI|CRDI|HDI|HDi|dCi|GDI|MPI|"
        r"EcoBoost|PureTech|BlueHDi|Skyactiv|VTEC|VVT[- ]?i|"
        r"Bi-Turbo|Twin-Turbo|Turbo|Kompressor|"
        r"JTD|Multijet|MJet|D-4D|T-Jet)$",
        re.I,
    )

    split_at = None
    for index, token in enumerate(tokens):
        if markers.match(token):
            split_at = index
            break

    if split_at is None:
        model = " ".join(tokens) if tokens else "Unknown"
        engine = " ".join(tokens) if tokens else ""
    else:
        model = " ".join(tokens[:split_at]) or "Unknown"
        engine = " ".join(tokens[split_at:])

    return brand, model, "", engine


def parse_engine_page(url: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    title = clean_spaces(h1.get_text(" ", strip=True) if h1 else "")
    if not title:
        return None

    stock_hp = re.search(r"STANDARD\s+(\d+)\s+BHP", html, re.I)
    stage_hp = re.search(r"TUNED\s*[→-]?\s*(\d+)\s+BHP", html, re.I)
    stock_nm = re.search(r"STANDARD\s+(\d+)\s+NM", html, re.I)
    stage_nm = re.search(r"TUNED\s*[→-]?\s*(\d+)\s+NM", html, re.I)

    if not stock_hp or not stage_hp:
        text = soup.get_text(" ", strip=True)
        stock_hp = re.search(r"STANDARD\s+(\d+)\s+BHP", text, re.I)
        stage_hp = re.search(r"TUNED\s*[→-]?\s*(\d+)\s+BHP", text, re.I)
        stock_nm = re.search(r"STANDARD\s+(\d+)\s+NM", text, re.I)
        stage_nm = re.search(r"TUNED\s*[→-]?\s*(\d+)\s+NM", text, re.I)

    if not stock_hp or not stage_hp:
        return None

    brand, model, year, engine = parse_engine_title(title)

    slug = url.rstrip("/").rsplit("/", 1)[-1]
    item_id = "remap-" + slug

    return {
        "id": item_id,
        "brand": brand,
        "model": model,
        "year": year,
        "engine": engine or title,
        "fuel": "Не указано",
        "stock_hp": int(stock_hp.group(1)),
        "stage1_hp": int(stage_hp.group(1)),
        "stock_nm": int(stock_nm.group(1)) if stock_nm else None,
        "stage1_nm": int(stage_nm.group(1)) if stage_nm else None,
        "price_rub": None,
        "source_url": url,
        "image_url": None,
        "graph_url": None,
    }


async def crawl(concurrency: int) -> list[dict]:
    connector = aiohttp.TCPConnector(
        limit=concurrency,
        limit_per_host=concurrency,
        ssl=False,
    )

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        index_html = await fetch(session, MAKES_INDEX)
        if not index_html:
            raise RuntimeError("Could not fetch RemappingData manufacturers index")

        make_urls = sorted(extract_links(index_html, MAKES_INDEX, looks_like_make))
        print(f"makes discovered: {len(make_urls)}", flush=True)

        make_sem = asyncio.Semaphore(6)

        async def discover_one(make_url: str) -> set[str]:
            async with make_sem:
                urls = await discover_engine_urls(session, make_url)
            print(f"make done: {make_url} -> {len(urls)} engines", flush=True)
            return urls

        engine_sets = await asyncio.gather(*(discover_one(url) for url in make_urls))
        engine_urls = sorted(set().union(*engine_sets))
        print(f"engine pages discovered: {len(engine_urls)}", flush=True)

        sem = asyncio.Semaphore(concurrency)

        async def parse_one(url: str) -> dict | None:
            async with sem:
                html = await fetch(session, url)
            if not html:
                return None
            return parse_engine_page(url, html)

        results: list[dict] = []
        for start in range(0, len(engine_urls), concurrency * 10):
            batch = engine_urls[start:start + concurrency * 10]
            parsed = await asyncio.gather(*(parse_one(url) for url in batch))
            results.extend(item for item in parsed if item)
            print(
                f"engines parsed: {min(start + len(batch), len(engine_urls))}/{len(engine_urls)} "
                f"valid={len(results)}",
                flush=True,
            )

        return results


def write_catalog(items: list[dict]) -> None:
    seed = json.loads(SEED_FILE.read_text(encoding="utf-8")) if SEED_FILE.exists() else []

    merged: dict[str, dict] = {}
    for item in seed:
        merged[str(item["id"])] = item
    for item in items:
        merged[str(item["id"])] = item

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

    brands = len({str(x.get("brand", "")) for x in ordered})
    models = len({
        (str(x.get("brand", "")), str(x.get("model", "")))
        for x in ordered
    })
    print(
        f"catalog written: {len(ordered)} engine entries, {brands} brands, {models} models",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    items = asyncio.run(crawl(args.concurrency))
    write_catalog(items)


if __name__ == "__main__":
    main()
