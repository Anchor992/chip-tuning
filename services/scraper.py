from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

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
    "User-Agent": "ChipTuningCatalogBot/1.0",
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
    match = re.search(r"-?\d+(?:[.,]\d+)?", text.replace(" ", ""))
    if not match:
        return None
    return int(float(match.group(0).replace(",", ".")))


def _extract_pair(text: str, unit: str) -> tuple[int | None, int | None]:
    values = [int(x) for x in re.findall(r"\d{2,4}", text) if 20 <= int(x) <= 2000]
    if len(values) < 2:
        return None, None
    return values[-2], values[-1]


def _extract_power_pair(soup: BeautifulSoup) -> tuple[int | None, int | None]:
    text = soup.get_text(" ", strip=True)
    section = re.search(r"Мощность двигателя(.{0,700})", text, re.I)
    return _extract_pair(section.group(1), "л.с.") if section else _extract_pair(text, "л.с.")


def _extract_torque_pair(soup: BeautifulSoup) -> tuple[int | None, int | None]:
    text = soup.get_text(" ", strip=True)
    section = re.search(r"Крутящий момент(.{0,700})", text, re.I)
    return _extract_pair(section.group(1), "Нм") if section else _extract_pair(text, "Нм")


def _parse_title(title: str) -> tuple[str, str, str, str]:
    cleaned = re.sub(r"^Чип-тюнинг\s+", "", title, flags=re.I).strip()
    parts = cleaned.split()
    if not parts:
        return "Unknown", "Unknown", "", ""
    brand = parts[0]
    rest = parts[1:]
    hp_index = next((i for i, p in enumerate(rest) if p.lower().replace("л.с.", "") == "hp"), None)
    if hp_index is not None:
        rest = rest[:hp_index]
    year_index = next((i for i, p in enumerate(rest) if re.fullmatch(r"20\d{2}", p)), None)
    year = ""
    if year_index is not None:
        year = rest[year_index]
    model = rest[0] if rest else "Unknown"
    engine = " ".join(rest[1:]) if len(rest) > 1 else ""
    return brand, model, year, engine


def _find_image(soup: BeautifulSoup, base_url: str) -> str | None:
    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        return urljoin(base_url, og["content"])
    for image in soup.find_all("img"):
        source = image.get("src") or image.get("data-src")
        if source and any(ext in source.lower() for ext in (".png", ".jpg", ".jpeg", ".webp")):
            return urljoin(base_url, source)
    return None


async def fetch(session: aiohttp.ClientSession, url: str) -> str | None:
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=20),
            allow_redirects=True,
        ) as response:
            if response.status != 200:
                return None
            return await response.text()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None


def _valid_item_url(url: str) -> bool:
    parsed = urlparse(url)
    return "/catalog/item/" in parsed.path and bool(parse_qs(parsed.query).get("id"))


async def discover_avt_links(session: aiohttp.ClientSession) -> list[str]:
    links: set[str] = set()

    html = await fetch(session, AVT_CATALOG)
    if html:
        soup = BeautifulSoup(html, "lxml")
        for anchor in soup.find_all("a", href=True):
            url = urljoin(AVT_CATALOG, anchor["href"])
            if _valid_item_url(url):
                links.add(url)

    for source_url in ("https://avt.ru/sitemap.xml", "https://avt.ru/robots.txt"):
        body = await fetch(session, source_url)
        if not body:
            continue

        if source_url.endswith("robots.txt"):
            sitemap_urls = []
            for line in body.splitlines():
                if line.lower().startswith("sitemap:"):
                    sitemap_urls.append(line.split(":", 1)[1].strip())
            for sitemap_url in sitemap_urls:
                xml = await fetch(session, sitemap_url)
                if not xml:
                    continue
                xml_soup = BeautifulSoup(xml, "xml")
                for loc in xml_soup.find_all("loc"):
                    value = loc.get_text(strip=True)
                    if _valid_item_url(value):
                        links.add(value)
        else:
            xml_soup = BeautifulSoup(body, "xml")
            for loc in xml_soup.find_all("loc"):
                value = loc.get_text(strip=True)
                if _valid_item_url(value):
                    links.add(value)

    return sorted(links)


async def parse_avt_item(session: aiohttp.ClientSession, url: str) -> dict | None:
    html = await fetch(session, url)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    title_node = soup.find("h1")
    title = title_node.get_text(" ", strip=True) if title_node else ""

    if not title:
        meta = soup.find("meta", attrs={"property": "og:title"})
        title = meta.get("content", "") if meta else ""

    if not title:
        return None

    brand, model, year, engine = _parse_title(title)
    stock_hp, stage1_hp = _extract_power_pair(soup)
    stock_nm, stage1_nm = _extract_torque_pair(soup)

    page_text = soup.get_text(" ", strip=True)
    price_match = re.search(r"Стоимость работ:\s*([\d\s]+)", page_text, re.I)
    price = _num(price_match.group(1)) if price_match else None

    query_id = parse_qs(urlparse(url).query).get("id", [None])[0]
    item_id = f"avt-{query_id}" if query_id else url

    if stock_hp is None or stage1_hp is None:
        return None

    return {
        "id": item_id,
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


async def scrape_avt(limit: int = 150) -> list[dict]:
    connector = aiohttp.TCPConnector(limit=6, ssl=False)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        links = (await discover_avt_links(session))[:limit]
        if not links:
            return []

        semaphore = asyncio.Semaphore(5)

        async def parse_one(url: str):
            async with semaphore:
                return await parse_avt_item(session, url)

        results = await asyncio.gather(*(parse_one(url) for url in links))
        return [item for item in results if item]


async def scrape_adact_prices() -> dict[str, int]:
    prices: dict[str, int] = {}
    connector = aiohttp.TCPConnector(limit=2, ssl=False)

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        for url in ADACT_PRICE_PAGES:
            html = await fetch(session, url)
            if not html:
                continue
            text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
            for brand in BRANDS:
                match = re.search(
                    rf"\b{re.escape(brand)}\s*\|?\s*от\s*([\d\s]+)\s*руб",
                    text,
                    re.I,
                )
                if match:
                    value = _num(match.group(1))
                    if value:
                        prices[brand.lower()] = value
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

    live_items = await scrape_avt()
    seed_items = json.loads(SEED_FILE.read_text(encoding="utf-8"))

    if live_items:
        prices = await scrape_adact_prices()
        live_items = apply_adact_prices(live_items, prices)
        merged = {item["id"]: item for item in seed_items}
        merged.update({item["id"]: item for item in live_items})
        items = list(merged.values())
    else:
        items = seed_items

    CATALOG_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return items


def load_catalog() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if CATALOG_FILE.exists():
        try:
            return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    return json.loads(SEED_FILE.read_text(encoding="utf-8"))
