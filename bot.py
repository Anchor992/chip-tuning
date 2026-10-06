from __future__ import annotations

import asyncio
import io
import logging
import hashlib
import os
import re
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    BufferedInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from PIL import Image, ImageDraw, ImageFont

from services.scraper import load_catalog, refresh_catalog

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("chip-tuning-bot")

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

CATALOG: list[dict] = []
SEARCH_MODE: set[int] = set()

BTN_CATALOG = "🚗 Каталог"
BTN_SEARCH = "🔎 Поиск"
BTN_REFRESH = "🔄 Обновить данные"
BTN_HELP = "ℹ️ Помощь"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CATALOG), KeyboardButton(text=BTN_SEARCH)],
            [KeyboardButton(text=BTN_REFRESH), KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )


def brands_kb() -> InlineKeyboardMarkup:
    brands = sorted({str(x.get("brand", "Неизвестно")) for x in CATALOG}, key=str.lower)
    rows = []
    for i in range(0, len(brands), 2):
        row = []
        for brand in brands[i:i + 2]:
            row.append(InlineKeyboardButton(text=brand, callback_data=f"brand:{brand}"))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _model_key(brand: str, model: str) -> str:
    return hashlib.sha1(f"{brand}|{model}".encode("utf-8")).hexdigest()[:10]


def models_kb(brand: str) -> InlineKeyboardMarkup:
    models = sorted(
        {str(x.get("model", "")) for x in CATALOG if str(x.get("brand")) == brand},
        key=str.lower,
    )
    rows = [
        [InlineKeyboardButton(text=m[:40], callback_data=f"model:{_model_key(brand, m)}")]
        for m in models
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Все марки", callback_data="brands")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cars_kb(items: list[dict], back: str) -> InlineKeyboardMarkup:
    rows = []
    for x in items:
        label = f'{x["model"]} · {x["engine"]} · {x["stock_hp"]}→{x["stage1_hp"]} л.с.'
        rows.append([InlineKeyboardButton(text=label[:60], callback_data=f"car:{x['id']}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fmt_price(v) -> str:
    if not v:
        return "уточняется"
    return f"{int(v):,}".replace(",", " ") + " ₽"


def car_text(x: dict) -> str:
    hp1 = int(x["stage1_hp"]) - int(x["stock_hp"])
    nm1 = None
    if x.get("stock_nm") is not None and x.get("stage1_nm") is not None:
        nm1 = int(x["stage1_nm"]) - int(x["stock_nm"])

    torque = "—"
    if x.get("stock_nm") is not None and x.get("stage1_nm") is not None:
        torque = f'{x["stock_nm"]} → {x["stage1_nm"]} Нм <b>(+{nm1} Нм)</b>'

    return (
        f'🚗 <b>{x["brand"]} {x["model"]}</b>\n'
        f'📅 {x.get("year") or "—"}\n'
        f'⚙️ {x.get("engine") or "—"}\n\n'
        f'🏁 <b>Stage 1</b>\n'
        f'Мощность: <b>{x["stock_hp"]} → {x["stage1_hp"]} л.с.</b> '
        f'(+{hp1} л.с.)\n'
        f'Крутящий момент: {torque}\n\n'
        f'💰 Ориентировочная цена: <b>{fmt_price(x.get("price_rub"))}</b>\n\n'
        f'⚠️ Значения ориентировочные. Точный результат зависит от конкретного автомобиля, '
        f'ПО и состояния двигателя.'
    )


def make_graph(x: dict) -> BufferedInputFile:
    w, h = 1100, 650
    img = Image.new("RGB", (w, h), (18, 20, 24))
    d = ImageDraw.Draw(img)

    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except OSError:
        font_big = font = font_small = ImageFont.load_default()

    title = f'{x["brand"]} {x["model"]} — Stage 1'
    d.text((55, 35), title, font=font_big, fill=(245, 245, 245))

    left, right, top, bottom = 100, 1000, 140, 550
    d.line((left, top, left, bottom), fill=(100, 105, 115), width=2)
    d.line((left, bottom, right, bottom), fill=(100, 105, 115), width=2)

    hp0, hp1 = int(x["stock_hp"]), int(x["stage1_hp"])
    nm0, nm1 = x.get("stock_nm"), x.get("stage1_nm")
    values = [hp0, hp1] + ([int(nm0), int(nm1)] if nm0 and nm1 else [])
    vmax = max(values) * 1.18
    vmin = min(values) * 0.82

    def y(v: int) -> int:
        return int(bottom - (v - vmin) / (vmax - vmin) * (bottom - top))

    # HP bars
    bx = [190, 410]
    bar_w = 130
    for xpos, val, label in [(bx[0], hp0, "Сток"), (bx[1], hp1, "Stage 1")]:
        yy = y(val)
        d.rectangle((xpos, yy, xpos + bar_w, bottom), fill=(55, 125, 255))
        d.text((xpos + 18, yy - 40), f"{val} л.с.", font=font, fill=(245, 245, 245))
        d.text((xpos + 18, bottom + 20), label, font=font_small, fill=(210, 210, 210))

    # Torque line
    if nm0 is not None and nm1 is not None:
        y0, y1 = y(int(nm0)), y(int(nm1))
        d.line((680, y0, 900, y1), fill=(255, 180, 70), width=8)
        d.ellipse((665, y0 - 12, 695, y0 + 12), fill=(255, 180, 70))
        d.ellipse((885, y1 - 12, 915, y1 + 12), fill=(255, 180, 70))
        d.text((640, y0 - 50), f"{nm0} Нм", font=font_small, fill=(255, 200, 110))
        d.text((860, y1 - 50), f"{nm1} Нм", font=font_small, fill=(255, 200, 110))
        d.text((675, bottom + 20), "Нм: сток → Stage 1", font=font_small, fill=(210, 210, 210))

    out = io.BytesIO()
    img.save(out, format="PNG")
    return BufferedInputFile(out.getvalue(), filename="stage1.png")


def find_car(car_id: str) -> dict | None:
    return next((x for x in CATALOG if str(x.get("id")) == car_id), None)


async def show_car(message: Message, x: dict):
    text = car_text(x)
    graph = make_graph(x)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Открыть источник AVT", url=x["source_url"])]
        ]
    )
    await message.answer_photo(graph, caption=text, reply_markup=kb)


@router.message(CommandStart())
async def start(message: Message):
    global CATALOG
    if not CATALOG:
        CATALOG = load_catalog()
        asyncio.create_task(silent_refresh())
    await message.answer(
        "👋 <b>Chip Tuning</b>\n\n"
        "Каталог прошивок и ориентировочных результатов Stage 1.\n"
        "Выберите действие ниже:",
        reply_markup=main_menu(),
    )


@router.message(Command("list"))
@router.message(F.text == BTN_CATALOG)
async def catalog(message: Message):
    if not CATALOG:
        await message.answer("Каталог ещё загружается. Попробуйте через несколько секунд.")
        return
    await message.answer("🚗 <b>Выберите марку:</b>", reply_markup=brands_kb())


@router.callback_query(F.data == "brands")
async def cb_brands(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text("🚗 <b>Выберите марку:</b>", reply_markup=brands_kb())


@router.callback_query(F.data.startswith("brand:"))
async def cb_brand(call: CallbackQuery):
    await call.answer()
    brand = call.data.split(":", 1)[1]
    await call.message.edit_text(
        f"🚗 <b>{brand}</b>\n\nВыберите модель:",
        reply_markup=models_kb(brand),
    )


@router.callback_query(F.data.startswith("model:"))
async def cb_model(call: CallbackQuery):
    await call.answer()
    key = call.data.split(":", 1)[1]
    pairs = {
        _model_key(str(x.get("brand", "")), str(x.get("model", ""))): (
            str(x.get("brand", "")), str(x.get("model", ""))
        )
        for x in CATALOG
    }
    pair = pairs.get(key)
    if not pair:
        await call.message.answer("Модель не найдена. Откройте каталог заново.")
        return
    brand, model = pair
    items = [x for x in CATALOG if str(x.get("brand")) == brand and str(x.get("model")) == model]
    await call.message.edit_text(
        f"🚗 <b>{brand} {model}</b>\n\nВыберите двигатель:",
        reply_markup=cars_kb(items, f"brand:{brand}"),
    )



@router.callback_query(F.data.startswith("car:"))
async def cb_car(call: CallbackQuery):
    await call.answer()
    x = find_car(call.data.split(":", 1)[1])
    if not x:
        await call.message.answer("Карточка не найдена. Обновите каталог.")
        return
    await show_car(call.message, x)


@router.message(F.text == BTN_SEARCH)
async def search_start(message: Message):
    SEARCH_MODE.add(message.from_user.id)
    await message.answer("🔎 Напишите марку, модель или двигатель для поиска.")


@router.message(F.text == BTN_REFRESH)
async def refresh_cmd(message: Message):
    await message.answer("🔄 Обновляю каталог. Это может занять немного времени.")
    global CATALOG
    try:
        CATALOG = await refresh_catalog()
        await message.answer(f"Готово. В каталоге <b>{len(CATALOG)}</b> автомобилей.")
    except Exception:
        log.exception("refresh failed")
        await message.answer("Не удалось обновить данные. Оставил последнюю рабочую версию каталога.")


@router.message(F.text == BTN_HELP)
async def help_cmd(message: Message):
    await message.answer(
        "ℹ️ <b>Команды</b>\n\n"
        "/start — главное меню\n"
        "/list — каталог\n"
        "/search — поиск\n\n"
        "Данные AVT используются как источник характеристик Stage 1. "
        "Цены являются ориентировочными и могут меняться."
    )


@router.message(Command("search"))
async def search_command(message: Message):
    SEARCH_MODE.add(message.from_user.id)
    await message.answer("🔎 Напишите марку, модель или двигатель для поиска.")


@router.message()
async def text_search(message: Message):
    uid = message.from_user.id
    if uid not in SEARCH_MODE:
        return

    query = (message.text or "").strip().lower()
    SEARCH_MODE.discard(uid)
    if len(query) < 2:
        await message.answer("Введите хотя бы 2 символа.")
        return

    items = []
    for x in CATALOG:
        hay = " ".join(
            str(x.get(k, "")) for k in ("brand", "model", "year", "engine")
        ).lower()
        if query in hay:
            items.append(x)

    if not items:
        await message.answer("Ничего не нашёл. Попробуйте другое название.")
        return

    items = items[:30]
    await message.answer(
        f"🔎 Найдено: <b>{len(items)}</b>",
        reply_markup=cars_kb(items, "brands"),
    )


async def silent_refresh():
    global CATALOG
    try:
        CATALOG = await refresh_catalog()
        log.info("catalog refreshed: %s items", len(CATALOG))
    except Exception:
        log.exception("initial catalog refresh failed")


async def periodic_refresh():
    while True:
        await asyncio.sleep(12 * 60 * 60)
        await silent_refresh()


async def main():
    global CATALOG
    CATALOG = load_catalog()
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(silent_refresh())
    asyncio.create_task(periodic_refresh())
    log.info("starting bot with %s catalog items", len(CATALOG))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
