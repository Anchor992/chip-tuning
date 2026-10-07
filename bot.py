from __future__ import annotations

import asyncio
import io
import json
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from PIL import Image, ImageDraw, ImageFont
import re

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("chip-tuning")

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

BASE_DIR = Path(__file__).resolve().parent
SEED_FILE = BASE_DIR / "data" / "seed.json"

def load_catalog_data() -> list[dict]:
    data_file = BASE_DIR / "data" / "catalog.json"
    candidate = data_file if data_file.exists() else SEED_FILE
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Could not load catalog from {candidate}: {exc}") from exc


CATALOG = load_catalog_data()

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
router = Router()
dp.include_router(router)

BTN_CATALOG = "🚗 Каталог"
BTN_SEARCH = "🔎 Поиск"
BTN_HELP = "ℹ️ Помощь"

search_users: set[int] = set()


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CATALOG), KeyboardButton(text=BTN_SEARCH)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def safe_id(value: str) -> str:
    import hashlib
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def display_model_name(item: dict) -> str:
    model = " ".join(str(item.get("model", "")).split()).strip()
    if not model:
        return "Неизвестная модель"
    model = re.sub(
        r"\s+\d+(?:[\s.,]+\d+)(?:\s*(?:tsi|tfsi|tdi|fsi|tfs|mpi|gdi|thp|vti|jts|tbi|cdti|crdi|dci|hdi|d4d|d5|turbo|bi[- ]?turbo|biturbo|ps|hp|kw|i|t|d|l))?.*$",
        "",
        model,
        flags=re.I,
    )
    model = re.sub(r"\s+\d+(?:ps|hp|kw)\b.*$", "", model, flags=re.I)
    return model.strip(" -_/") or "Неизвестная модель"


def brands_keyboard() -> InlineKeyboardMarkup:
    brands = sorted({str(item["brand"]) for item in CATALOG}, key=str.lower)
    rows = []
    for i in range(0, len(brands), 2):
        rows.append([
            InlineKeyboardButton(
                text=brand[:40],
                callback_data=f"brand:{safe_id(brand)}",
            )
            for brand in brands[i:i + 2]
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def models_keyboard(brand: str, page: int = 0) -> InlineKeyboardMarkup:
    grouped: dict[str, dict] = {}
    for item in CATALOG:
        if str(item["brand"]) != brand:
            continue
        model = display_model_name(item)
        grouped.setdefault(model, item)

    models = sorted(grouped.items(), key=lambda x: x[0].lower())
    page_size = 20
    total_pages = max(1, (len(models) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    current = models[page * page_size:(page + 1) * page_size]

    rows = [
        [
            InlineKeyboardButton(
                text=model[:45],
                callback_data=f"modelid:{safe_id(str(item['id']))}",
            )
        ]
        for model, item in current
    ]

    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"models:{safe_id(brand)}:{page-1}",
            )
        )
    nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"models:{safe_id(brand)}:{page+1}",
            )
        )
    rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ К маркам", callback_data="brands")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def engines_keyboard(items: list[dict], brand: str, model_key: str, page: int = 0) -> InlineKeyboardMarkup:
    page_size = 20
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    current = items[page * page_size:(page + 1) * page_size]

    rows = []
    for item in current:
        label = f'{item["engine"]} · {item["stock_hp"]}→{item["stage1_hp"]} л.с.'
        rows.append([
            InlineKeyboardButton(
                text=label[:55],
                callback_data=f"carid:{safe_id(str(item['id']))}",
            )
        ])

    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"engines:{model_key}:{page-1}",
            )
        )
    nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"engines:{model_key}:{page+1}",
            )
        )
    rows.append(nav)
    rows.append([
        InlineKeyboardButton(
            text="⬅️ К моделям",
            callback_data=f"modelsback:{safe_id(brand)}",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fmt_price(value) -> str:
    if not value:
        return "уточняется"
    return f"{int(value):,}".replace(",", " ") + " ₽"


def car_caption(item: dict) -> str:
    hp_gain = int(item["stage1_hp"]) - int(item["stock_hp"])
    torque = "—"
    if item.get("stock_nm") is not None and item.get("stage1_nm") is not None:
        nm_gain = int(item["stage1_nm"]) - int(item["stock_nm"])
        torque = (
            f'{item["stock_nm"]} → {item["stage1_nm"]} Нм '
            f'(<b>+{nm_gain} Нм</b>)'
        )

    return (
        f'🚗 <b>{item["brand"]} {item["model"]}</b>\n'
        f'📅 {item.get("year") or "—"}\n'
        f'⚙️ {item.get("engine") or "—"}\n\n'
        f'🏁 <b>Stage 1</b>\n'
        f'Мощность: <b>{item["stock_hp"]} → {item["stage1_hp"]} л.с.</b> '
        f'(<b>+{hp_gain} л.с.</b>)\n'
        f'Крутящий момент: {torque}\n'
        f'💰 Ориентировочная цена: <b>{fmt_price(item.get("price_rub"))}</b>\n\n'
        '⚠️ Значения ориентировочные и зависят от конкретного автомобиля и его состояния.'
    )


def graph_image(item: dict) -> BufferedInputFile:
    width, height = 1200, 760
    image = Image.new("RGB", (width, height), (15, 17, 22))
    draw = ImageDraw.Draw(image)

    try:
        title_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42
        )
        section_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30
        )
        value_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28
        )
        small_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22
        )
    except OSError:
        title_font = section_font = value_font = small_font = ImageFont.load_default()

    title = f'{item["brand"]} {item["model"]} — Stage 1'
    draw.text((48, 30), title, font=title_font, fill=(245, 245, 245))

    hp0, hp1 = int(item["stock_hp"]), int(item["stage1_hp"])
    nm0 = item.get("stock_nm")
    nm1 = item.get("stage1_nm")

    panels = [
        ("МОЩНОСТЬ", "л.с.", hp0, hp1, 70, 185, 520),
    ]
    if nm0 is not None and nm1 is not None:
        panels.append(("КРУТЯЩИЙ МОМЕНТ", "Нм", int(nm0), int(nm1), 650, 185, 1100))

    for label, unit, before, after, x_left, x_top, x_right in panels:
        draw.rounded_rectangle(
            (x_left, x_top, x_right, 665),
            radius=24,
            outline=(70, 75, 85),
            width=2,
            fill=(20, 23, 29),
        )
        draw.text((x_left + 28, x_top + 24), label, font=section_font, fill=(235, 235, 235))

        chart_left = x_left + 58
        chart_right = x_right - 58
        chart_bottom = 590
        chart_top = x_top + 100
        max_value = max(before, after)
        min_value = max(1, int(max_value * 0.55))

        def y_for(value: int) -> int:
            span = max(1, max_value - min_value)
            return chart_bottom - int(
                (value - min_value) / span * (chart_bottom - chart_top)
            )

        bar_width = 115
        gap = 85
        x1 = chart_left + 30
        x2 = x1 + bar_width + gap

        for x, value, caption in (
            (x1, before, "СТОК"),
            (x2, after, "STAGE 1"),
        ):
            y = y_for(value)
            draw.rounded_rectangle(
                (x, y, x + bar_width, chart_bottom),
                radius=12,
                fill=(57, 122, 242),
            )
            draw.text(
                (x + bar_width // 2, y - 42),
                f"{value} {unit}",
                anchor="mm",
                font=value_font,
                fill=(250, 250, 250),
            )
            draw.text(
                (x + bar_width // 2, chart_bottom + 32),
                caption,
                anchor="mm",
                font=small_font,
                fill=(210, 210, 215),
            )

        gain = after - before
        draw.text(
            ((x1 + x2 + bar_width) // 2, chart_bottom - 5),
            f"+{gain} {unit}",
            anchor="mm",
            font=value_font,
            fill=(120, 220, 150),
        )

    out = io.BytesIO()
    image.save(out, format="PNG")
    return BufferedInputFile(out.getvalue(), filename="stage1.png")


def find_item(item_id: str) -> dict | None:
    for item in CATALOG:
        if str(item.get("id")) == item_id:
            return item
    return None


def find_brand_by_hash(value: str) -> str | None:
    for item in CATALOG:
        brand = str(item["brand"])
        if safe_id(brand) == value:
            return brand
    return None


def find_model_by_id_hash(value: str) -> tuple[str, str] | None:
    for item in CATALOG:
        if safe_id(str(item.get("id", ""))) == value:
            return str(item["brand"]), display_model_name(item)
    return None


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        "👋 <b>Chip Tuning</b>\n\n"
        "Каталог Stage 1 с характеристиками до/после.\n\n"
        "Выберите действие:",
        reply_markup=main_menu(),
    )


@router.message(Command("ping"))
async def ping(message: Message) -> None:
    await message.answer("🟢 Бот работает.")


@router.message(Command("list"))
@router.message(F.text == BTN_CATALOG)
async def catalog(message: Message) -> None:
    await message.answer(
        "🚗 <b>Выберите марку:</b>",
        reply_markup=brands_keyboard(),
    )


@router.callback_query(F.data == "brands")
async def all_brands(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.edit_text(
        "🚗 <b>Выберите марку:</b>",
        reply_markup=brands_keyboard(),
    )


@router.callback_query(F.data.startswith("brand:"))
async def choose_brand(call: CallbackQuery) -> None:
    await call.answer()
    brand = find_brand_by_hash(call.data.split(":", 1)[1])
    if not brand:
        await call.message.answer("Марка не найдена. Откройте каталог заново.")
        return

    await call.message.edit_text(
        f"🚗 <b>{brand}</b>\n\nВыберите модель:",
        reply_markup=models_keyboard(brand, 0),
    )


@router.callback_query(F.data == "noop")
async def noop_callback(call: CallbackQuery) -> None:
    await call.answer()


@router.callback_query(F.data.startswith("models:"))
async def models_page(call: CallbackQuery) -> None:
    await call.answer()
    _, brand_hash, page_text = call.data.split(":", 2)
    brand = find_brand_by_hash(brand_hash)
    if not brand:
        await call.message.answer("Марка не найдена.")
        return
    await call.message.edit_text(
        f"🚗 <b>{brand}</b>\n\nВыберите модель:",
        reply_markup=models_keyboard(brand, int(page_text)),
    )


@router.callback_query(F.data.startswith("modelsback:"))
async def models_back(call: CallbackQuery) -> None:
    await call.answer()
    brand = find_brand_by_hash(call.data.split(":", 1)[1])
    if not brand:
        await call.message.answer("Марка не найдена.")
        return
    await call.message.edit_text(
        f"🚗 <b>{brand}</b>\n\nВыберите модель:",
        reply_markup=models_keyboard(brand, 0),
    )


@router.callback_query(F.data.startswith("engines:"))
async def engines_page(call: CallbackQuery) -> None:
    await call.answer()
    _, model_hash, page_text = call.data.split(":", 2)
    pair = find_model_by_id_hash(model_hash)
    if not pair:
        await call.message.answer("Модель не найдена.")
        return
    brand, model = pair
    items = [
        item for item in CATALOG
        if str(item["brand"]) == brand and display_model_name(item) == model
    ]
    await call.message.edit_text(
        f"🚗 <b>{brand} {model}</b>\n\nВыберите двигатель:",
        reply_markup=engines_keyboard(items, brand, model_hash, int(page_text)),
    )


@router.callback_query(F.data.startswith("modelid:"))
async def choose_model(call: CallbackQuery) -> None:
    await call.answer()
    model_id_hash = call.data.split(":", 1)[1]
    pair = find_model_by_id_hash(model_id_hash)
    if not pair:
        await call.message.answer("Модель не найдена. Откройте каталог заново.")
        return

    brand, model = pair
    items = [
        item for item in CATALOG
        if str(item["brand"]) == brand and display_model_name(item) == model
    ]

    await call.message.edit_text(
        f"🚗 <b>{brand} {model}</b>\n\nВыберите двигатель:",
        reply_markup=engines_keyboard(items, brand, model_id_hash, 0),
    )


@router.callback_query(F.data.startswith("carid:"))
async def choose_car(call: CallbackQuery) -> None:
    await call.answer()
    key = call.data.split(":", 1)[1]
    item = next((x for x in CATALOG if safe_id(str(x.get("id", ""))) == key), None)
    if not item:
        await call.message.answer("Карточка не найдена.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🌐 Открыть источник",
                    url=item["source_url"],
                )
            ]
        ]
    )
    await call.message.answer_photo(
        photo=graph_image(item),
        caption=car_caption(item),
        reply_markup=keyboard,
    )


@router.message(F.text == BTN_SEARCH)
async def start_search(message: Message) -> None:
    search_users.add(message.from_user.id)
    await message.answer("🔎 Напишите марку, модель или двигатель.")


@router.message(Command("search"))
async def command_search(message: Message) -> None:
    search_users.add(message.from_user.id)
    await message.answer("🔎 Напишите марку, модель или двигатель.")


@router.message(F.text == BTN_HELP)
async def help_message(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>Команды</b>\n\n"
        "/start — главное меню\n"
        "/list — каталог\n"
        "/search — поиск\n"
        "/ping — проверка работы бота"
    )


@router.message(Command("reload"))
async def reload_catalog_command(message: Message) -> None:
    global CATALOG
    try:
        data_file = BASE_DIR / "data" / "catalog.json"
        if data_file.exists():
            CATALOG = json.loads(data_file.read_text(encoding="utf-8"))
            await message.answer(f"🔄 Каталог перезагружен: <b>{len(CATALOG)}</b> позиций.")
        else:
            await message.answer("Каталог пока не собран. Используется резервный список.")
    except Exception as exc:
        log.exception("catalog reload failed")
        await message.answer(f"Не удалось перечитать каталог: {type(exc).__name__}")


@router.message()
async def text_search(message: Message) -> None:
    if message.from_user.id not in search_users:
        return

    search_users.discard(message.from_user.id)
    query = (message.text or "").strip().lower()
    if len(query) < 2:
        await message.answer("Введите минимум 2 символа.")
        return

    matches = []
    for item in CATALOG:
        haystack = " ".join(
            str(item.get(key, ""))
            for key in ("brand", "model", "year", "engine")
        ).lower()
        if query in haystack:
            matches.append(item)

    if not matches:
        await message.answer("Ничего не найдено.")
        return

    rows = []
    for item in matches[:30]:
        label = f'{item["brand"]} {item["model"]} · {item["engine"]}'
        rows.append([
            InlineKeyboardButton(
                text=label[:55],
                callback_data=f'car:{item["id"]}',
            )
        ])

    await message.answer(
        f"🔎 Найдено: <b>{len(matches)}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def main() -> None:
    me = await bot.get_me()
    log.info("Telegram authorization OK: @%s (id=%s)", me.username, me.id)

    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Webhook removed; polling starts.")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
