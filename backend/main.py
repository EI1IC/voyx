# backend/main.py
import os
import sys
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения из backend/.env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Добавляем путь к модулям
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# ✅ Импорты из app (без YandexRouterClient)
from app.routing import calculate_route, calculate_multi_point_route
from app.graph import init_graph
from app.traffic_collector import run_traffic_collector, fetch_yandex_traffic_segments, save_traffic_to_cache

# Глобальный флаг состояния сбора пробок
traffic_collector_task: Optional[asyncio.Task] = None
last_traffic_update: Optional[float] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация и завершение работы приложения"""
    logger.info("🚀 Инициализация приложения...")
    
    # Инициализация графа (загрузка OSM, если нужно)
    init_graph()
    
    # ✅ Запуск фонового сбора пробок каждые 30 минут
    global traffic_collector_task
    traffic_collector_task = asyncio.create_task(run_traffic_collector())
    logger.info("🔄 Фоновый сбор пробок запущен")
    
    yield
    
    # Завершение работы
    logger.info("🛑 Завершение работы...")
    
    # Отмена фонового задачи
    if traffic_collector_task and not traffic_collector_task.done():
        traffic_collector_task.cancel()
        try:
            await traffic_collector_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Маршрутизация Киров",
    description="API для оптимизации курьерских маршрутов с учётом пробок (Playwright + OSM)",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware для фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене ограничить до домена фронтенда
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RouteRequest(BaseModel):
    start_address: str
    end_address: str
    waypoints: Optional[List[str]] = []
    use_traffic: bool = True  # ✅ Учитывать пробки из кэша


class MultiPointRequest(BaseModel):
    waypoints: List[str]
    use_traffic: bool = True


class TrafficRefreshResponse(BaseModel):
    status: str
    segments_count: int
    timestamp: float


@app.post("/api/route")
async def calculate_route_api(req: RouteRequest):
    """
    Рассчитывает маршрут: старт → [промежуточные] → финиш.
    
    Параметры:
    - start_address: адрес начала
    - end_address: адрес конца
    - waypoints: опциональные промежуточные точки
    - use_traffic: учитывать ли пробки из кэша (по умолчанию true)
    """
    try:
        if req.waypoints:
            # Многоточечный маршрут
            all_points = [req.start_address] + req.waypoints + [req.end_address]
            result = calculate_multi_point_route(
                all_points,
                use_traffic=req.use_traffic
            )
        else:
            # Простой маршрут
            result = calculate_route(
                req.start_address,
                req.end_address,
                use_traffic=req.use_traffic
            )
        
        return {"status": "success", "data": result}
    
    except ValueError as e:
        logger.warning(f"⚠️ Ошибка валидации: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Ошибка в /api/route: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@app.post("/api/route/multi")
async def calculate_multi_route_api(req: MultiPointRequest):
    """
    Рассчитывает многоточечный маршрут: точка1 → точка2 → ... → точкаN.
    """
    try:
        result = calculate_multi_point_route(
            req.waypoints,
            use_traffic=req.use_traffic
        )
        return {"status": "success", "data": result}
    
    except ValueError as e:
        logger.warning(f"⚠️ Ошибка валидации: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Ошибка в /api/route/multi: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@app.post("/api/traffic/refresh")
async def refresh_traffic_data():
    """
    Ручной запуск сбора данных о пробках.
    Полезно для тестирования и принудительного обновления кэша.
    """
    try:
        logger.info("🔄 Ручной запуск сбора пробок...")
        segments = await fetch_yandex_traffic_segments(lat=58.60, lon=49.66)
        
        if segments:
            await save_traffic_to_cache(segments)
            global last_traffic_update
            import time
            last_traffic_update = time.time()
            
            return TrafficRefreshResponse(
                status="success",
                segments_count=len(segments),
                timestamp=last_traffic_update
            )
        else:
            logger.warning("⚠️ Не получено сегментов от Яндекса")
            raise HTTPException(status_code=502, detail="Не удалось получить данные о пробках")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении пробок: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка сбора: {str(e)}")


@app.get("/api/traffic/status")
async def traffic_status():
    """
    Возвращает статус системы сбора пробок.
    """
    import time
    from pathlib import Path
    
    cache_path = Path(__file__).parent.parent / "traffic_cache.json"
    cache_exists = cache_path.exists()
    cache_age = None
    
    if cache_exists:
        import json
        try:
            data = json.loads(cache_path.read_text())
            cache_age = time.time() - data.get("timestamp", 0)
        except:
            cache_exists = False
    
    return {
        "collector_running": traffic_collector_task is not None and not traffic_collector_task.done(),
        "cache_exists": cache_exists,
        "cache_age_seconds": round(cache_age, 1) if cache_age else None,
        "last_update": last_traffic_update,
        "next_auto_update_in_seconds": 1800 - (cache_age or 1800) if cache_age else 1800
    }


@app.get("/health")
async def health_check():
    """Проверка работоспособности API"""
    import time
    from pathlib import Path
    
    cache_path = Path(__file__).parent.parent / "traffic_cache.json"
    traffic_fresh = False
    
    if cache_path.exists():
        try:
            import json
            data = json.loads(cache_path.read_text())
            if time.time() - data.get("timestamp", 0) < 3600:  # < 1 часа
                traffic_fresh = True
        except:
            pass
    
    return {
        "status": "ok",
        "graph_loaded": True,
        "traffic_cache": "fresh" if traffic_fresh else "stale/missing",
        "collector_active": traffic_collector_task is not None and not traffic_collector_task.done()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )