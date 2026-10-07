from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup

BASE = "https://avt.ru/catalog/item/?id="
MAX_ID = 15050
DATA_FILE = Path("data/catalog.json")
SEED_FILE = Path("data/seed.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ChipTuningCatalog/2.0)",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

# Longest-first matching keeps multi-word makes intact.
KNOWN_BRANDS = sorted(
    {
        "Mercedes-Benz",
        "Land Rover",
        "Alfa Romeo",
        "Aston Martin",
        "Great Wall",
        "Geely",
        "Genesis",
        "Haval",
        "Changan",
        "Chery",
        "Citroen",
        "Chevrolet",
        "Mitsubishi",
        "Volkswagen",
        "Rolls-Royce",
        "Mini",
        "Lamborghini",
        "Ferrari",
        "Porsche",
        "Peugeot",
        "Renault",
        "Skoda",
        "Subaru",
        "Suzuki",
        "Toyota",
        "Lexus",
        "Nissan",
        "Infiniti",
        "Hyundai",
        "Kia",
        "Volvo",
        "Ford",
        "Honda",
        "Mazda",
        "Opel",
        "Fiat",
        "Jeep",
        "Dodge",
        "Chrysler",
        "Bentley",
        "Jaguar",
        "Isuzu",
        "SsangYong",
        "Lada",
        "Daewoo",
        "Seat",
        "Cupra",
        "Audi",
        "BMW",
        "Cadillac",
        "GMC",
        "Tesla",
        "Exeed",
        "Omoda",
        "JAC",
        "Jetour",
        "Kaiyi",
        "Livna",
        "Moskvich",
        "Voyah",
        "Tank",
        "GAC",
        "Hongqi",
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
            rest = prefix[len(brand):].strip(" -–—")
            # AVT sometimes repeats the make: "Mazda Mazda 3".
            if rest.lower().startswith(brand.lower() + " "):
                rest = rest[len(brand):].strip()
            return brand, rest
    parts = prefix.split()
    return (parts[0] if parts else "Неизвестно", " ".join(parts[1:]))


async def fetch_page(
    session: aiohttp.ClientSession, sem: asyncio.Semaphore, item_id: int
) -> tuple[int, str] | None:
    url = f"{BASE}{item_id}"
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
                    return item_id, await response.text(errors="ignore")
        except Exception:
            if attempt == 2:
                return None
            await asyncio.sleep(0.8 * (attempt + 1))
    return None


def parse_page(item_id: int, html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    text = norm(" ".join(soup.stripped_strings))

    if "Мощность двигателя" not in text or "Крутящий момент" not in text:
        return None
    if "Чип-тюнинг авто" not in text and "Чип-тюнинг" not in text:
        return None
    if "Стоимость работ" not in text:
        return None

    # Vehicle title lives immediately after the breadcrumb.
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
    title_stock_hp = int(title_match.group(2))

    # Example: "Audi A3 8Y - 2020 -> 2024 1.4 TFSI"
    # and "Mazda Mazda 3 2013 -> ... 2.0 i".
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

    # Keep the source's year range intact.
    year = f"{yr.group('y1')}–{yr.group('y2')}"

    # Exact Stage 1 numbers from AVT's own page.
    power_section = text[text.find("Мощность двигателя"):text.find("Крутящий момент")]
    hpvals = [int(x) for x in re.findall(r"(\d+)\s*л\.с\.", power_section)]
    if len(hpvals) < 2:
        return None
    stock_hp = title_stock_hp
    stage1_hp = hpvals[-1]
    if stage1_hp == stock_hp:
        return None

    torque_start = text.find("Крутящий момент")
    torque_section = text[torque_start: torque_start + 700]
    nmvals = [int(x) for x in re.findall(r"(\d+)\s*Нм", torque_section)]
    if len(nmvals) < 2:
        return None
    stock_nm = nmvals[-2]
    stage1_nm = nmvals[-1]
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
        "fuel": "Дизель" if re.search(r"\b(d|td|tdi|dci|hdi|diesel|cdti|crdi)\b", engine, re.I) else "Бензин",
        "stock_hp": stock_hp,
        "stage1_hp": stage1_hp,
        "stock_nm": stock_nm,
        "stage1_nm": stage1_nm,
        "price_rub": price,
        "source_url": f"{BASE}{item_id}",
        "image_url": None,
        "graph_url": None,
    }


async def crawl(max_id: int, concurrency: int) -> list[dict]:
    connector = aiohttp.TCPConnector(
        limit=concurrency,
        limit_per_host=concurrency,
        ssl=False,
    )
    sem = asyncio.Semaphore(concurrency)

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        results: list[dict] = []
        ids = list(range(1, max_id + 1))
        for start in range(0, len(ids), concurrency * 20):
            batch = ids[start:start + concurrency * 20]
            pages = await asyncio.gather(
                *(fetch_page(session, sem, item_id) for item_id in batch)
            )
            for page in pages:
                if not page:
                    continue
                item_id, html = page
                parsed = parse_page(item_id, html)
                if parsed:
                    results.append(parsed)
            print(
                f"AVT scanned {min(start + len(batch), len(ids))}/{len(ids)} "
                f"verified={len(results)}",
                flush=True,
            )
        return results


def write_catalog(items: list[dict]) -> None:
    seed = json.loads(SEED_FILE.read_text(encoding="utf-8")) if SEED_FILE.exists() else []

    # Prefer freshly parsed AVT values. Seed remains only as a safety net.
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

    if len(data) < 1000 or brands < 20:
        raise SystemExit("AVT catalog unexpectedly small; refusing to publish.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-id", type=int, default=MAX_ID)
    parser.add_argument("--concurrency", type=int, default=24)
    args = parser.parse_args()

    items = asyncio.run(crawl(args.max_id, args.concurrency))
    write_catalog(items)


if __name__ == "__main__":
    main()
