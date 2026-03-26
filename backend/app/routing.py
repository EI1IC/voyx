import osmnx as ox
import networkx as nx

from .config import SPEED_LIMITS, ROAD_PENALTIES
from .graph import get_graph
from .geocoding import geocode_address

def calculate_route(start_addr: str, end_addr: str) -> dict:
    """
    Рассчитывает оптимальный маршрут между двумя адресами.
    
    Args:
        start_addr: Адрес старта
        end_addr: Адрес финиша
        
    Returns:
        dict с данными маршрута (координаты, расстояние, время)
    """
    G, blocked_edges_set = get_graph()
    
    # 1. Геокодирование
    start_coords = geocode_address(start_addr)
    end_coords = geocode_address(end_addr)
    
    # 2. Поиск ближайших узлов
    try:
        orig_node = ox.nearest_nodes(G, X=start_coords[1], Y=start_coords[0])
        dest_node = ox.nearest_nodes(G, X=end_coords[1], Y=end_coords[0])
    except ValueError as e:
        if "scikit-learn must be installed as an optional dependency to search an unprojected graph" in str(e):
            raise RuntimeError(
                "Для работы поиска ближайших узлов требуется пакет scikit-learn. "
                "Установите scikit-learn, например: pip install -r requirements.txt"
            ) from e
        raise

    # 3. Весовая функция с учётом барьеров и штрафов дорог
    def weight(u, v, data):
        for key in G.get_edge_data(u, v).keys():
            if (u, v, key) in blocked_edges_set:
                return float('inf')
        
        length = data.get('length', 0)
        highway = data.get('highway', 'residential')
        if isinstance(highway, list):
            highway = highway[0]
        
        penalty = ROAD_PENALTIES.get(highway, 2.0)
        return length * penalty

    # 4. A* алгоритм
    try:
        path = nx.astar_path(
            G, source=orig_node, target=dest_node, weight=weight,
            heuristic=lambda u, v: ((G.nodes[u]['x'] - G.nodes[v]['x'])**2 + 
                                    (G.nodes[u]['y'] - G.nodes[v]['y'])**2)**0.5
        )
        used_fallback = False
    except nx.NetworkXNoPath:
        path = _fallback_route(G, orig_node, dest_node, blocked_edges_set)
        used_fallback = True

    # 5. Сбор геометрии и метрик
    result = _build_route_result(G, path, start_coords, end_coords, used_fallback)
    result["waypoints"] = [
        {"lat": start_coords[0], "lon": start_coords[1], "address": start_addr},
        {"lat": end_coords[0], "lon": end_coords[1], "address": end_addr}
    ]
    return result

def _fallback_route(G, orig_node, dest_node, blocked_edges_set) -> list:
    """Резервный маршрут с мягким штрафом за барьеры."""
    def fallback_weight(u, v, data):
        length = data.get('length', 0)
        for key in G.get_edge_data(u, v).keys():
            if (u, v, key) in blocked_edges_set:
                return length + 10000
        return length
    
    return nx.astar_path(
        G, source=orig_node, target=dest_node, weight=fallback_weight,
        heuristic=lambda u, v: ((G.nodes[u]['x'] - G.nodes[v]['x'])**2 + 
                                (G.nodes[u]['y'] - G.nodes[v]['y'])**2)**0.5
    )

def _build_route_result(G, path, start_coords, end_coords, used_fallback) -> dict:
    """Собирает итоговый результат маршрута."""
    route_coords = []
    distance_meters = 0
    estimated_time_minutes = 0
    
    for u, v in zip(path[:-1], path[1:]):
        route_coords.append([G.nodes[u]['x'], G.nodes[u]['y']])
        edge_data = G.get_edge_data(u, v, key=0)
        length = edge_data.get('length', 0)
        distance_meters += length
        
        highway_type = edge_data.get('highway', 'residential')
        if isinstance(highway_type, list):
            highway_type = highway_type[0]
        speed_kmh = SPEED_LIMITS.get(highway_type, 30)
        estimated_time_minutes += (length / (speed_kmh / 3.6)) / 60
    
    route_coords.append([G.nodes[path[-1]]['x'], G.nodes[path[-1]]['y']])
    
    return {
        "route": route_coords,
        "distance_km": round(distance_meters / 1000, 2),
        "time_min": round(estimated_time_minutes, 1),
        "start": {"lat": start_coords[0], "lon": start_coords[1]},
        "end": {"lat": end_coords[0], "lon": end_coords[1]},
        "has_barriers": used_fallback
    }

def calculate_multi_point_route(waypoints: list[str]) -> dict:
    """
    Рассчитывает маршрут через несколько точек.
    
    Args:
        waypoints: Список адресов [старт, промежуточная1, ..., финиш]
        
    Returns:
        dict с данными маршрута (объединённые сегменты)
    """
    if len(waypoints) < 2:
        raise ValueError("Минимум 2 точки для маршрута")
    
    G, blocked_edges_set = get_graph()
    
    # Геокодирование всех точек
    coords = []
    for addr in waypoints:
        coords.append(geocode_address(addr))
    
    # Строим маршрут по сегментам
    all_route_coords = []
    total_distance = 0
    total_time = 0
    has_barriers = False
    segments = []
    
    for i in range(len(coords) - 1):
        start_coords = coords[i]
        end_coords = coords[i + 1]
        
        orig_node = ox.nearest_nodes(G, X=start_coords[1], Y=start_coords[0])
        dest_node = ox.nearest_nodes(G, X=end_coords[1], Y=end_coords[0])
        
        def weight(u, v, data):
            for key in G.get_edge_data(u, v).keys():
                if (u, v, key) in blocked_edges_set:
                    return float('inf')
            length = data.get('length', 0)
            highway = data.get('highway', 'residential')
            if isinstance(highway, list):
                highway = highway[0]
            penalty = ROAD_PENALTIES.get(highway, 2.0)
            return length * penalty
        
        try:
            path = nx.astar_path(
                G, source=orig_node, target=dest_node, weight=weight,
                heuristic=lambda u, v: ((G.nodes[u]['x'] - G.nodes[v]['x'])**2 + 
                                        (G.nodes[u]['y'] - G.nodes[v]['y'])**2)**0.5
            )
            segment_barriers = False
        except nx.NetworkXNoPath:
            path = _fallback_route(G, orig_node, dest_node, blocked_edges_set)
            segment_barriers = True
            has_barriers = True
        
        # Собираем геометрию сегмента
        segment_coords = []
        segment_distance = 0
        segment_time = 0
        
        for u, v in zip(path[:-1], path[1:]):
            segment_coords.append([G.nodes[u]['x'], G.nodes[u]['y']])
            edge_data = G.get_edge_data(u, v, key=0)
            length = edge_data.get('length', 0)
            segment_distance += length
            
            highway_type = edge_data.get('highway', 'residential')
            if isinstance(highway_type, list):
                highway_type = highway_type[0]
            speed_kmh = SPEED_LIMITS.get(highway_type, 30)
            segment_time += (length / (speed_kmh / 3.6)) / 60
        
        # Добавляем последнюю точку сегмента
        segment_coords.append([G.nodes[path[-1]]['x'], G.nodes[path[-1]]['y']])
        
        # Объединяем сегменты (убираем дубликат на стыке)
        if i > 0:
            all_route_coords.extend(segment_coords[1:])
        else:
            all_route_coords.extend(segment_coords)
        
        total_distance += segment_distance
        total_time += segment_time
        segments.append({
            "from": waypoints[i],
            "to": waypoints[i + 1],
            "distance_km": round(segment_distance / 1000, 2),
            "time_min": round(segment_time, 1)
        })
    
    return {
        "route": all_route_coords,
        "distance_km": round(total_distance / 1000, 2),
        "time_min": round(total_time, 1),
        "waypoints": [
            {"lat": c[0], "lon": c[1], "address": addr}
            for c, addr in zip(coords, waypoints)
        ],
        "has_barriers": has_barriers,
        "segments": segments
    }