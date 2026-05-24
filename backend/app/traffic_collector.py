# app/traffic_collector.py
import asyncio
import os
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Any
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)
CACHE_PATH = Path(__file__).parent.parent / "traffic_cache.json"

YANDEX_JS_API_KEY = os.getenv("YANDEX_JS_API_KEY")

async def fetch_yandex_traffic_segments(lat=58.60, lon=49.66, zoom=13) -> List[Dict[str, Any]]:
    if not YANDEX_JS_API_KEY:
        logger.error("❌ YANDEX_JS_API_KEY не найден в .env")
        return []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()
        
        # Логируем ошибки консоли
        page.on("console", lambda msg: logger.debug(f"Browser console: {msg.text}"))
        page.on("pageerror", lambda err: logger.error(f"Page error: {err}"))

        try:
            # HTML для API v3
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <script src="https://api-maps.yandex.ru/v3/?apikey={YANDEX_JS_API_KEY}&lang=ru_RU"></script>
            </head>
            <body>
                <div id="map" style="width:100px;height:100px;"></div>
            </body>
            </html>
            """
            
            await page.set_content(html_content)
            
            # Ждём загрузки API v3
            await page.wait_for_function("typeof ymaps3 !== 'undefined'")
            await page.evaluate("await ymaps3.ready")
            
            # Получаем сегменты пробок через v3 API
            segments = await page.evaluate("""
                ({lat, lon, z}) => new Promise(async (resolve) => {
                    try {
                        await ymaps3.ready;
                        const {{ YMap, YMapDefaultSchemeLayer, YMapTrafficLayer }} = ymaps3;
                        
                        const map = new YMap(document.getElementById('map'), {{
                            location: {{ center: [lon, lat], zoom: z }}
                        }});
                        
                        map.addChild(new YMapDefaultSchemeLayer());
                        
                        // Добавляем слой пробок
                        const traffic = new YMapTrafficLayer();
                        map.addChild(traffic);
                        
                        // Ждём загрузки данных
                        await new Promise(r => setTimeout(r, 2000));
                        
                        // В v3 получаем данные через traffic.state или traffic.getFeatures()
                        // Это зависит от версии библиотеки, пробуем оба варианта
                        let features = [];
                        if (traffic.state?.features) {
                            features = traffic.state.features;
                        } else if (traffic.getFeatures) {
                            features = traffic.getFeatures();
                        }
                        
                        const result = features.map(f => {{
                            try {{
                                return {{
                                    level: f.properties?.congestion?.level || 0,
                                    color: f.properties?.congestion?.color || 'gray',
                                    coords: f.geometry?.coordinates || []
                                }};
                            }} catch (e) {{ return null; }}
                        }}).filter(Boolean);
                        
                        resolve(result);
                    }} catch (e) {{
                        console.error('Traffic error:', e);
                        resolve([]);
                    }}
                })
            """, {"lat": lat, "lon": lon, "z": zoom})

            logger.info(f"✅ Получено сегментов: {len(segments)}")
            return segments or []

        except Exception as e:
            logger.error(f"❌ Ошибка Playwright/JS API v3: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
        finally:
            await browser.close()

async def save_traffic_to_cache(segments: List[Dict]):
    data = {"timestamp": time.time(), "segments": segments, "source": "js_api_v3"}
    CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    logger.info(f"💾 Сохранено {len(segments)} сегментов")

async def run_traffic_collector():
    while True:
        logger.info("🔄 Запуск сбора пробок...")
        try:
            segments = await fetch_yandex_traffic_segments()
            if segments:
                await save_traffic_to_cache(segments)
            else:
                logger.warning("⚠️ Пустой ответ от JS API v3")
        except Exception as e:
            logger.error(f"❌ Ошибка цикла: {e}")
        await asyncio.sleep(1800)