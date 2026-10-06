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

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("chip-tuning")

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

BASE_DIR = Path(__file__).resolve().parent
SEED_FILE = BASE_DIR / "data" / "seed.json"

try:
    CATALOG = json.loads(SEED_FILE.read_text(encoding="utf-8"))
except Exception as exc:
    raise RuntimeError(f"Could not load {SEED_FILE}: {exc}") from exc

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


def models_keyboard(brand: str) -> InlineKeyboardMarkup:
    models = sorted(
        {str(item["model"]) for item in CATALOG if str(item["brand"]) == brand},
        key=str.lower,
    )
    rows = [
        [
            InlineKeyboardButton(
                text=model[:45],
                callback_data=f"model:{safe_id(brand + '|' + model)}",
            )
        ]
        for model in models
    ]
    rows.append([
        InlineKeyboardButton(text="⬅️ К маркам", callback_data="brands")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def engines_keyboard(items: list[dict], brand: str) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        label = (
            f'{item["engine"]} · '
            f'{item["stock_hp"]}→{item["stage1_hp"]} л.с.'
        )
        rows.append([
            InlineKeyboardButton(
                text=label[:55],
                callback_data=f"car:{item['id']}",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text="⬅️ К моделям",
            callback_data=f"brand:{safe_id(brand)}",
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
    width, height = 1000, 600
    image = Image.new("RGB", (width, height), (18, 20, 24))
    draw = ImageDraw.Draw(image)

    try:
        title_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34
        )
        value_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28
        )
    except OSError:
        title_font = value_font = ImageFont.load_default()

    draw.text(
        (40, 30),
        f'{item["brand"]} {item["model"]} — Stage 1',
        font=title_font,
        fill=(245, 245, 245),
    )

    hp_stock = int(item["stock_hp"])
    hp_stage = int(item["stage1_hp"])
    max_hp = max(hp_stock, hp_stage)
    base_y = 500
    top_y = 140
    bar_width = 170

    def bar_height(value: int) -> int:
        return int((value / max_hp) * (base_y - top_y))

    for x, value, label in (
        (220, hp_stock, "Сток"),
        (520, hp_stage, "Stage 1"),
    ):
        h = bar_height(value)
        y = base_y - h
        draw.rectangle((x, y, x + bar_width, base_y), fill=(55, 125, 255))
        draw.text((x + 25, y - 40), f"{value} л.с.", font=value_font, fill="white")
        draw.text((x + 25, base_y + 20), label, font=value_font, fill=(220, 220, 220))

    if item.get("stock_nm") is not None and item.get("stage1_nm") is not None:
        draw.text(
            (40, 550),
            f'Нм: {item["stock_nm"]} → {item["stage1_nm"]}',
            font=value_font,
            fill=(255, 190, 100),
        )

    output = io.BytesIO()
    image.save(output, format="PNG")
    return BufferedInputFile(output.getvalue(), filename="stage1.png")


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


def find_model_by_hash(value: str) -> tuple[str, str] | None:
    for item in CATALOG:
        brand = str(item["brand"])
        model = str(item["model"])
        if safe_id(brand + "|" + model) == value:
            return brand, model
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
        reply_markup=models_keyboard(brand),
    )


@router.callback_query(F.data.startswith("model:"))
async def choose_model(call: CallbackQuery) -> None:
    await call.answer()
    pair = find_model_by_hash(call.data.split(":", 1)[1])
    if not pair:
        await call.message.answer("Модель не найдена. Откройте каталог заново.")
        return

    brand, model = pair
    items = [
        item for item in CATALOG
        if str(item["brand"]) == brand and str(item["model"]) == model
    ]

    await call.message.edit_text(
        f"🚗 <b>{brand} {model}</b>\n\nВыберите двигатель:",
        reply_markup=engines_keyboard(items, brand),
    )


@router.callback_query(F.data.startswith("car:"))
async def choose_car(call: CallbackQuery) -> None:
    await call.answer()
    item = find_item(call.data.split(":", 1)[1])
    if not item:
        await call.message.answer("Карточка не найдена.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🌐 Открыть источник AVT",
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
