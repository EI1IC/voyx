# app/traffic_screen.py
import asyncio, os, math, logging
from pathlib import Path
from PIL import Image
from playwright.async_api import async_playwright
from playwright_stealth import Stealth  # ✅ Правильный импорт по документации
from .config import BBOX

logger = logging.getLogger(__name__)
IMG_PATH = Path(__file__).parent.parent / "traffic.png"
VIEWPORT = {"width": 1200, "height": 800}

PALETTE = {
    "green":   (0, 180, 0),
    "yellow":  (255, 200, 0),
    "red":     (255, 50, 50),
    "darkred": (150, 0, 0)
}
FACTOR_MAP = {"green": 1.0, "yellow": 1.3, "red": 1.8, "darkred": 2.5, "gray": 1.0}
TOLERANCE = 55

def _geo_to_px(lon, lat, bbox, w, h):
    west, south, east, north = bbox
    x = int((lon - west) / (east - west) * w)
    y = int((1 - (lat - south) / (north - south)) * h)
    return max(0, min(w-1, x)), max(0, min(h-1, y))

def _classify_pixel(rgb):
    r, g, b = rgb
    for name, (tr, tg, tb) in PALETTE.items():
        if abs(r-tr)<TOLERANCE and abs(g-tg)<TOLERANCE and abs(b-tb)<TOLERANCE:
            return name
    return "gray"

def get_edge_factor(u_lon, u_lat, v_lon, v_lat, samples=12):
    if not IMG_PATH.exists():
        return 1.0, "gray"
    
    try:
        img = Image.open(IMG_PATH).convert("RGB")
        if img.size[0] < 500: return 1.0, "gray"
    except Exception:
        return 1.0, "gray"
        
    w, h = img.size
    colors = []
    for i in range(samples):
        t = i / (samples-1) if samples>1 else 0
        lon = u_lon + t*(v_lon-u_lon)
        lat = u_lat + t*(v_lat-u_lat)
        px, py = _geo_to_px(lon, lat, BBOX, w, h)
        colors.append(_classify_pixel(img.getpixel((px, py))))
        
    dominant = max(set(colors), key=colors.count)
    return FACTOR_MAP[dominant], dominant

async def capture_screenshot():
    """Делает скриншот карты с пробками (по официальной доке playwright-stealth)"""
    # ✅ Рекомендуемый паттерн из документации
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            viewport=VIEWPORT,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ru-RU",
            timezone_id="Europe/Moscow"
        )
        page = await context.new_page()
        
        try:
            url = "https://yandex.ru/maps/46/kirov/probki/?ll=49.63%2C58.60&z=14&l=map%2Ctraffic"
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(5000)

            # Закрываем сайдбар
            try:
                await page.click('span.sidebar-toggle-button__icon', timeout=2000)
                await page.wait_for_timeout(500)
            except: pass

            # Проверка на капчу
            has_captcha = await page.query_selector('text="Подтвердите, что вы не робот"') or \
                          await page.query_selector('text="reCAPTCHA"')
            
            if has_captcha:
                logger.warning("⚠️ Яндекс вернул CAPTCHA. Пропускаю обновление, использую текущий traffic.png")
                if not IMG_PATH.exists():
                    logger.error("❌ Файл traffic.png отсутствует. Создай его вручную.")
                await browser.close()
                return

            await page.screenshot(path=str(IMG_PATH), full_page=False)
            logger.info(f"📸 Скриншот успешно сохранён: {IMG_PATH}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка захвата: {e}")
        finally:
            await browser.close()