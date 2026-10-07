from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

BASE = "https://avt.ru/catalog/item/?id="
MAX_ID = 15050
UPTUNS_INDEX = "https://uptuns.ru/proekty/chip-tyuning/"
DATA_FILE = Path("data/catalog.json")
SEED_FILE = Path("data/seed.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ChipTuningCatalog/2.1)",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

KNOWN_BRANDS = sorted(
    {
        "Mercedes-Benz", "Land Rover", "Alfa Romeo", "Aston Martin", "Great Wall",
        "Geely", "Genesis", "Haval", "Changan", "Chery", "Citroen", "Chevrolet",
        "Mitsubishi", "Volkswagen", "Rolls-Royce", "Mini", "Lamborghini", "Ferrari",
        "Porsche", "Peugeot", "Renault", "Skoda", "Subaru", "Suzuki", "Toyota",
        "Lexus", "Nissan", "Infiniti", "Hyundai", "Kia", "Volvo", "Ford", "Honda",
        "Mazda", "Opel", "Fiat", "Jeep", "Dodge", "Chrysler", "Bentley", "Jaguar",
        "Isuzu", "SsangYong", "Lada", "Daewoo", "Seat", "Cupra", "Audi", "BMW",
        "Cadillac", "GMC", "Tesla", "Exeed", "Omoda", "JAC", "Jetour", "Kaiyi",
        "Livna", "Moskvich", "Voyah", "Tank", "GAC", "Hongqi", "Datsun", "BYD",
    },
    key=len,
    reverse=True,
)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def brand_split(prefix: str) -> tuple[str, str]:
    prefix = norm(prefix)
    for brand in KNOWN_BRANDS:
        if prefix.lower().startswith(brand.lower()):
            rest = prefix[len(brand):].strip(" -–—:")
            if rest.lower().startswith(brand.lower() + " "):
                rest = rest[len(brand):].strip()
            return brand, rest
    parts = prefix.split()
    return (parts[0] if parts else "Неизвестно", " ".join(parts[1:]))


def normalize_year(text: str) -> str:
    value = norm(text).strip("()")
    value = value.replace(" - ", "–").replace(" — ", "–").replace("-", "–")
    value = re.sub(r"\s*–\s*", "–", value)
    return value


def displacement(text: str) -> str | None:
    match = re.search(r"(?<!\d)(\d[.,]\d)(?!\d)", text or "")
    return match.group(1).replace(",", ".") if match else None


async def fetch_url(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    url: str,
) -> str | None:
    for attempt in range(3):
        try:
            async with sem:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=25),
                    allow_redirects=True,
                ) as response:
                    if response.status != 200:
                        return None
                    return await response.text(errors="ignore")
        except Exception:
            if attempt == 2:
                return None
            await asyncio.sleep(0.8 * (attempt + 1))
    return None


def parse_avt_page(item_id: int, html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    text = norm(" ".join(soup.stripped_strings))

    if "Мощность двигателя" not in text or "Крутящий момент" not in text:
        return None
    if "Чип-тюнинг авто" not in text and "Чип-тюнинг" not in text:
        return None
    if "Стоимость работ" not in text:
        return None

    title_match = re.search(
        r"Главная\s+Чип-тюнинг(?: авто)?\s+(.+?)\s+(\d{2,4})\s*hp\b",
        text,
        re.I,
    )
    if not title_match:
        title_match = re.search(
            r"Чип-тюнинг(?: авто)?\s+(.+?)\s+(\d{2,4})\s*hp\b",
            text,
            re.I,
        )
    if not title_match:
        return None

    prefix = norm(title_match.group(1))
    stock_hp = int(title_match.group(2))

    yr = re.search(
        r"^(?P<vehicle>.+?)\s+(?P<y1>\d{4})\s*(?:->|–>|—>)\s*"
        r"(?P<y2>\d{4}|\.\.\.)\s+(?P<engine>.+)$",
        prefix,
        re.I,
    )
    if not yr:
        return None

    brand, model = brand_split(yr.group("vehicle"))
    model = norm(model)
    engine = norm(yr.group("engine"))
    year = f"{yr.group('y1')}–{yr.group('y2')}"

    power_section = text[text.find("Мощность двигателя"):text.find("Крутящий момент")]
    hpvals = [int(x) for x in re.findall(r"(\d+)\s*л\.с\.", power_section)]
    if len(hpvals) < 2:
        return None
    stage1_hp = hpvals[-1]
    if stage1_hp <= stock_hp:
        return None

    torque_start = text.find("Крутящий момент")
    torque_section = text[torque_start: torque_start + 700]
    nmvals = [int(x) for x in re.findall(r"(\d+)\s*Нм", torque_section)]
    if len(nmvals) < 2:
        return None
    stock_nm, stage1_nm = nmvals[-2], nmvals[-1]
    if stage1_nm <= stock_nm:
        return None

    price_match = re.search(r"Стоимость работ:\s*([\d\s]+)", text)
    price = int(price_match.group(1).replace(" ", "")) if price_match else None

    return {
        "id": f"avt-{item_id}",
        "brand": brand,
        "model": model,
        "year": year,
        "engine": engine,
        "fuel": "Дизель" if re.search(
            r"\b(d|td|tdi|dci|hdi|diesel|cdti|crdi)\b", engine, re.I
        ) else "Бензин",
        "stock_hp": stock_hp,
        "stage1_hp": stage1_hp,
        "stock_nm": stock_nm,
        "stage1_nm": stage1_nm,
        "price_rub": price,
        "source": "AVT",
        "source_url": f"{BASE}{item_id}",
        "image_url": None,
        "graph_url": None,
    }


def parse_uptuns_segment(segment: str, source_url: str) -> dict | None:
    if "Поколение" not in segment or "Мощность двигателя" not in segment:
        return None

    generation = segment.split("Поколение", 1)[1].split("Тип работ", 1)[0].strip()
    if not generation:
        return None

    title = segment.split("Поколение", 1)[0].strip(" |")
    brand_pos = None
    matched_brand = None
    lower = title.lower()
    for brand in KNOWN_BRANDS:
        pos = lower.find(brand.lower())
        if pos >= 0 and (brand_pos is None or pos < brand_pos):
            brand_pos = pos
            matched_brand = brand
    if matched_brand is None:
        return None

    rest = title[brand_pos + len(matched_brand):].strip(" :–—")
    if not rest:
        return None
    # Some Uptuns cards put the work description after a colon.
    rest = rest.split(":", 1)[0].strip()
    if not rest:
        return None

    engine_type = segment.split("Тип двигателя", 1)[1].split("Объем двигателя", 1)[0].strip()
    engine_volume = segment.split("Объем двигателя", 1)[1].split("Мощность двигателя", 1)[0].strip()
    power_text = segment.split("Мощность двигателя", 1)[1].split("Прирост мощности", 1)[0]
    gain_text = segment.split("Прирост мощности", 1)[1]
    torque_gain_text = ""
    if "Прирост крутящего момента" in gain_text:
        gain_text, torque_gain_text = gain_text.split("Прирост крутящего момента", 1)

    stock_match = re.search(r"(\d{2,4})", power_text)
    gain_match = re.search(r"\+\s*(\d{1,3})", gain_text)
    torque_gain_match = re.search(r"\+\s*(\d{1,4})\s*Нм", torque_gain_text)

    if not stock_match or not gain_match:
        return None

    stock_hp = int(stock_match.group(1))
    hp_gain = int(gain_match.group(1))
    if hp_gain <= 0:
        return None

    torque_gain = int(torque_gain_match.group(1)) if torque_gain_match else None

    return {
        "id": f"uptuns-{__import__("hashlib").sha1("|".join([matched_brand, rest, engine_volume, generation]).encode("utf-8")).hexdigest()[:12]}",
        "brand": matched_brand,
        "model": norm(rest),
        "year": normalize_year(generation),
        "engine": norm(engine_volume),
        "fuel": "Дизель" if "дизель" in engine_type.lower() else "Бензин",
        "stock_hp": stock_hp,
        "stage1_hp": stock_hp + hp_gain,
        "stock_nm": None,
        "stage1_nm": None,
        "torque_gain_nm": torque_gain,
        "price_rub": None,
        "source": "UPTUNS",
        "source_url": source_url,
        "image_url": None,
        "graph_url": None,
    }


def parse_uptuns_page(html: str, source_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    text = norm(" ".join(soup.stripped_strings))
    parts = [part.strip() for part in text.split("Подробнее") if "Поколение" in part]
    items: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for part in parts:
        item = parse_uptuns_segment(part, source_url)
        if not item:
            continue
        key = (
            item["brand"].lower(),
            item["model"].lower(),
            item["engine"].lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        items.append(item)

    return items


async def crawl_avt(max_id: int, concurrency: int) -> list[dict]:
    connector = aiohttp.TCPConnector(limit=concurrency, limit_per_host=concurrency, ssl=False)
    sem = asyncio.Semaphore(concurrency)

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        results: list[dict] = []
        ids = list(range(1, max_id + 1))
        for start in range(0, len(ids), concurrency * 20):
            batch = ids[start:start + concurrency * 20]
            pages = await asyncio.gather(
                *(fetch_url(session, sem, f"{BASE}{item_id}") for item_id in batch)
            )
            for item_id, html in zip(batch, pages):
                if not html:
                    continue
                parsed = parse_avt_page(item_id, html)
                if parsed:
                    results.append(parsed)
            print(
                f"AVT scanned {min(start + len(batch), len(ids))}/{len(ids)} "
                f"verified={len(results)}",
                flush=True,
            )
        return results


async def crawl_uptuns(concurrency: int) -> list[dict]:
    sem = asyncio.Semaphore(max(4, min(concurrency, 8)))
    connector = aiohttp.TCPConnector(limit=12, limit_per_host=12, ssl=False)

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        index_html = await fetch_url(session, sem, UPTUNS_INDEX)
        if not index_html:
            print("UPTUNS unavailable; keeping AVT-only catalog.", flush=True)
            return []

        soup = BeautifulSoup(index_html, "lxml")
        links = {UPTUNS_INDEX}
        for anchor in soup.find_all("a", href=True):
            url = urljoin(UPTUNS_INDEX, anchor["href"])
            parsed = urlparse(url)
            if parsed.netloc not in {"uptuns.ru", "www.uptuns.ru"}:
                continue
            if parsed.path.startswith("/proekty/chip-tyuning"):
                links.add(url.split("#", 1)[0])

        # The public section is small; cap discovery so a site navigation glitch
        # cannot turn the catalog build into a full-site crawl.
        urls = sorted(links)[:80]
        print(f"UPTUNS discovered {len(urls)} project pages/sections", flush=True)

        pages = await asyncio.gather(*(fetch_url(session, sem, url) for url in urls))
        results: list[dict] = []
        seen: set[tuple[str, str, str]] = set()

        for url, html in zip(urls, pages):
            if not html:
                continue
            for item in parse_uptuns_page(html, url):
                key = (
                    item["brand"].lower(),
                    item["model"].lower(),
                    item["engine"].lower(),
                )
                if key in seen:
                    continue
                seen.add(key)
                results.append(item)

        print(f"UPTUNS parsed {len(results)} project entries", flush=True)
        return results


def normalized(value: str) -> str:
    value = value.lower().replace("-", " ")
    return re.sub(r"[^a-zа-я0-9]+", " ", value).strip()


def has_avt_equivalent(item: dict, avt_items: list[dict]) -> bool:
    brand = normalized(str(item.get("brand", "")))
    model = normalized(str(item.get("model", "")))
    disp = displacement(str(item.get("engine", "")))

    for avt in avt_items:
        if normalized(str(avt.get("brand", ""))) != brand:
            continue
        avt_model = normalized(str(avt.get("model", "")))
        if model != avt_model and model not in avt_model and avt_model not in model:
            continue
        if disp:
            avt_disp = displacement(str(avt.get("engine", "")))
            if avt_disp and avt_disp != disp:
                continue
        return True
    return False


def write_catalog(avt_items: list[dict], uptuns_items: list[dict]) -> None:
    seed = json.loads(SEED_FILE.read_text(encoding="utf-8")) if SEED_FILE.exists() else []

    # AVT is the primary source. UPTUNS supplements only gaps where AVT does
    # not have the same make/model/displacement, preventing duplicate conflicts.
    merged = {str(x["id"]): x for x in seed}

    for item in avt_items:
        merged[str(item["id"])] = item

    for item in uptuns_items:
        if not has_avt_equivalent(item, avt_items):
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
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    brands = len({x.get("brand") for x in data})
    models = len({(x.get("brand"), x.get("model")) for x in data})
    avt_count = sum(1 for x in data if x.get("source") == "AVT")
    uptuns_count = sum(1 for x in data if x.get("source") == "UPTUNS")
    print(
        f"catalog={len(data)} entries, brands={brands}, models={models}, "
        f"AVT={avt_count}, UPTUNS={uptuns_count}",
        flush=True,
    )

    if len(data) < 1000 or brands < 20:
        raise SystemExit("Verified catalog unexpectedly small; refusing to publish.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-id", type=int, default=MAX_ID)
    parser.add_argument("--concurrency", type=int, default=24)
    args = parser.parse_args()

    avt_items = asyncio.run(crawl_avt(args.max_id, args.concurrency))
    uptuns_items = asyncio.run(crawl_uptuns(args.concurrency))
    write_catalog(avt_items, uptuns_items)


if __name__ == "__main__":
    main()
