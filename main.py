from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional
import asyncio

from app import calculate_route, calculate_multi_point_route, init_graph

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Инициализация приложения...")
    init_graph()
    yield
    print("🛑 Завершение работы...")

app = FastAPI(title="Маршрутизация Киров", lifespan=lifespan)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

class RouteRequest(BaseModel):
    start_address: str
    end_address: str
    waypoints: Optional[List[str]] = []  # ✅ Новые промежуточные точки

class MultiPointRequest(BaseModel):
    waypoints: List[str]  # ✅ Все точки маршрута

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/route")
async def calculate_route_api(req: RouteRequest):
    """Простой маршрут: старт → финиш."""
    try:
        if req.waypoints:
            # ✅ Многоточечный маршрут
            all_points = [req.start_address] + req.waypoints + [req.end_address]
            result = await asyncio.to_thread(
                calculate_multi_point_route,
                all_points
            )
        else:
            # ✅ Простой маршрут
            result = await asyncio.to_thread(
                calculate_route,
                req.start_address,
                req.end_address
            )
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/route/multi")
async def calculate_multi_route_api(req: MultiPointRequest):
    """Многоточечный маршрут: точка1 → точка2 → ... → точкаN."""
    try:
        result = await asyncio.to_thread(
            calculate_multi_point_route,
            req.waypoints
        )
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)