from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

AVT_CATALOG = "https://avt.ru/catalog/"
ADACT_PRICE_PAGES = [
    "https://msk.adact2.ru/price",
    "https://ufa.adact2.ru/price",
    "https://omsk.adact2.ru/price",
]
DATA_DIR = Path("data")
CATALOG_FILE = DATA_DIR / "catalog.json"
SEED_FILE = DATA_DIR / "seed.json"

HEADERS = {
    "User-Agent": "ChipTuningCatalogBot/1.0 (+catalog updater)",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
}

BRANDS = [
    "Audi", "BMW", "Chery", "Changan", "Chevrolet", "Citroen", "Ford",
    "Geely", "Genesis", "Haval", "Honda", "Hyundai", "Kia", "Lada",
    "Mazda", "Mercedes-Benz", "Mitsubishi", "Nissan", "Opel", "Peugeot",
    "Renault", "Skoda", "Subaru", "Suzuki", "Toyota", "Volkswagen", "Volvo",
]


def _num(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"(-?\d+(?:[.,]\d+)?)", text.replace(" ", ""))
    if not m:
        return None
    return int(float(m.group(1).replace(",", ".")))


def _extract_power_pair(soup: BeautifulSoup) -> tuple[int | None, int | None]:
    text = soup.get_text(" ", strip=True)
    m = re.search(
        r"Мощность двигателя.*?До.*?После\s*\+?\s*([+-]?\d+)\s*л\.с\..*?"
        r"(\d+)\s*л\.с\..*?(\d+)\s*л\.с\.",
        text,
        re.I,
    )
    if m:
        return int(m.group(2)), int(m.group(3))

    # Fallback: look around Stage 1 block.
    vals = re.findall(r"(\d{2,4})\s*л\.с\.", text)
    if len(vals) >= 2:
        return int(vals[-2]), int(vals[-1])
    return None, None


def _extract_torque_pair(soup: BeautifulSoup) -> tuple[int | None, int | None]:
    text = soup.get_text(" ", strip=True)
    m = re.search(
        r"Крутящий момент.*?До.*?После\s*\+?\s*([+-]?\d+)\s*Нм.*?"
        r"(\d+)\s*Нм.*?(\d+)\s*Нм",
        text,
        re.I,
    )
    if m:
        return int(m.group(2)), int(m.group(3))

    vals = re.findall(r"(\d{2,4})\s*Нм", text)
    if len(vals) >= 2:
        return int(vals[-2]), int(vals[-1])
    return None, None


def _parse_title(title: str) -> tuple[str, str, str, str]:
    # Typical AVT title:
    # Чип-тюнинг Volkswagen Golf 2012 -> 2017 1.4 TFSI 150 hp
    title = re.sub(r"^Чип-тюнинг\s+", "", title, flags=re.I).strip()
    m = re.match(
        r"(?P<brand>\S+)\s+(?P<model>.+?)\s+(?P<year>\d{4}\s*(?:->|–|-)\s*[^\s]+)?\s*(?P<engine>.+?)\s+(?P<hp>\d+)\s*hp$",
        title,
        re.I,
    )
    if m:
        return m.group("brand"), m.group("model"), m.group("year") or "", m.group("engine")
    parts = title.split()
    brand = parts[0] if parts else "Unknown"
    return brand, " ".join(parts[1:]), "", ""


def _find_image(soup: BeautifulSoup, base: str) -> str | None:
    candidates = []
    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        candidates.append(og["content"])
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src:
            candidates.append(src)
    for src in candidates:
        src = urljoin(base, src)
        low = src.lower()
        if any(x in low for x in (".png", ".jpg", ".jpeg", ".webp")):
            return src
    return None


async def fetch(session: aiohttp.ClientSession, url: str) -> str | None:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30), allow_redirects=True) as r:
            if r.status != 200:
                return None
            return await r.text()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None


async def discover_avt_links(session: aiohttp.ClientSession) -> list[str]:
    links: set[str] = set()

    # Main catalogue page.
    html = await fetch(session, AVT_CATALOG)
    if html:
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            href = urljoin(AVT_CATALOG, a["href"])
            if "/catalog/item/" in href:
                links.add(href)

        # Some catalogue pages expose item IDs in inline JSON/scripts.
        for match in re.findall(r'https?://[^\'"]+/catalog/item/\?id=\d+', html):
            links.add(match)

    # Sitemap is useful because AVT's catalogue can be rendered dynamically.
    for sitemap_url in ("https://avt.ru/sitemap.xml", "https://avt.ru/robots.txt"):
        sitemap = await fetch(session, sitemap_url)
        if not sitemap:
            continue
        for loc in re.findall(r"<loc>\s*(https?://[^<]+/catalog/item/\?id=\d+)\s*</loc>", sitemap, re.I):
            links.add(loc)
        for loc in re.findall(r"(?im)^\s*Sitemap:\s*(https?://\S+)", sitemap):
            if loc.endswith("sitemap.xml"):
                child = await fetch(session, loc)
                if child:
                    for item_url in re.findall(r"<loc>\s*(https?://[^<]+/catalog/item/\?id=\d+)\s*</loc>", child, re.I):
                        links.add(item_url)

    return sorted(links)


async def parse_avt_item(session: aiohttp.ClientSession, url: str) -> dict | None:
    html = await fetch(session, url)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    title_node = soup.find("h1")
    title = title_node.get_text(" ", strip=True) if title_node else ""
    if not title:
        og_title = soup.find("meta", attrs={"property": "og:title"})
        title = og_title.get("content", "") if og_title else ""
    if not title:
        return None

    brand, model, year, engine = _parse_title(title)
    stock_hp, stage1_hp = _extract_power_pair(soup)
    stock_nm, stage1_nm = _extract_torque_pair(soup)

    price = None
    text = soup.get_text(" ", strip=True)
    pm = re.search(r"Стоимость работ:\s*([\d\s]+)", text, re.I)
    if pm:
        price = _num(pm.group(1))

    item_id = re.search(r"[?&]id=(\d+)", url)
    ident = f"avt-{item_id.group(1)}" if item_id else url

    if stock_hp is None or stage1_hp is None:
        return None

    return {
        "id": ident,
        "brand": brand,
        "model": model,
        "year": year,
        "engine": engine,
        "fuel": "Не указано",
        "stock_hp": stock_hp,
        "stage1_hp": stage1_hp,
        "stock_nm": stock_nm,
        "stage1_nm": stage1_nm,
        "price_rub": price,
        "source_url": url,
        "image_url": _find_image(soup, url),
        "graph_url": None,
    }


async def scrape_avt(limit: int = 250) -> list[dict]:
    connector = aiohttp.TCPConnector(limit=8, ssl=False)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        links = await discover_avt_links(session)
        if not links:
            return []

        # Avoid hammering the source; catalogue refresh is intentionally conservative.
        links = links[:limit]
        sem = asyncio.Semaphore(6)

        async def one(url: str):
            async with sem:
                return await parse_avt_item(session, url)

        results = await asyncio.gather(*(one(u) for u in links))
        return [x for x in results if x and x.get("stock_hp") and x.get("stage1_hp")]


async def scrape_adact_prices() -> dict[str, int]:
    prices: dict[str, int] = {}
    connector = aiohttp.TCPConnector(limit=3, ssl=False)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        for url in ADACT_PRICE_PAGES:
            html = await fetch(session, url)
            if not html:
                continue
            soup = BeautifulSoup(html, "lxml")
            text = soup.get_text(" ", strip=True)
            for brand in BRANDS:
                pattern = rf"\b{re.escape(brand)}\s*\|?\s*от\s*([\d\s]+)\s*руб"
                m = re.search(pattern, text, re.I)
                if m:
                    prices[brand.lower()] = _num(m.group(1)) or 0
            if prices:
                break
    return prices


def apply_adact_prices(items: list[dict], prices: dict[str, int]) -> list[dict]:
    for item in items:
        if not item.get("price_rub"):
            item["price_rub"] = prices.get(str(item.get("brand", "")).lower())
    return items


async def refresh_catalog() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fresh = await scrape_avt()

    if fresh:
        prices = await scrape_adact_prices()
        fresh = apply_adact_prices(fresh, prices)
        # Keep a small amount of known seed data if the live catalogue temporarily
        # omits it; live data wins by ID.
        seed = json.loads(SEED_FILE.read_text(encoding="utf-8"))
        by_id = {x["id"]: x for x in seed}
        by_id.update({x["id"]: x for x in fresh})
        items = list(by_id.values())
        CATALOG_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        return items

    if CATALOG_FILE.exists():
        return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))

    seed = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    CATALOG_FILE.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
    return seed


def load_catalog() -> list[dict]:
    if CATALOG_FILE.exists():
        try:
            return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return json.loads(SEED_FILE.read_text(encoding="utf-8"))
