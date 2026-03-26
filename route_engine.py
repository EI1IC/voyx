import os
import osmnx as ox
import networkx as nx
import geopandas as gpd
from shapely.geometry import LineString, Point
from functools import lru_cache

# ==============================================================================
# КОНФИГУРАЦИЯ
# ==============================================================================

ox.settings.log_console = False
ox.settings.use_cache = True
ox.settings.timeout = 180

GRAPH_FILENAME = "kirov_road_network.graphml"
BARRIERS_FILENAME = "kirov_barriers.geojson"
BARRIER_TOLERANCE = 7

# Было (только скорости):
SPEED_LIMITS = {
    'motorway': 90, 'trunk': 70, 'primary': 60,
    'secondary': 50, 'tertiary': 40, 'residential': 30,
    'service': 20, 'living_street': 20
}

# Стало (добавляем множители стоимости):
ROAD_PENALTIES = {
    'motorway': 1.0,    # ✅ Предпочтительно
    'trunk': 1.0,
    'primary': 1.1,
    'secondary': 1.2,
    'tertiary': 1.3,
    'residential': 3.0,  # ⚠️ Штраф x2.5 (заходим только в начале/конце)
    'living_street': 3.0, # ⚠️ Штраф x3.0
    'service': 3.0,      # ⚠️ Штраф x3.0 (дворовые проезды)
    'unclassified': 1.5
}

# Глобальные переменные (кэшируются при старте)
_G = None
_BLOCKED_EDGES = None
_BLOCKED_EDGES_SET = None  # ✅ Для быстрого поиска O(1)

# ==============================================================================
# 1. ГЕОКОДИРОВАНИЕ С КЭШЕМ
# ==============================================================================

@lru_cache(maxsize=1000)
def geocode_address(address_query, city="Kirov, Russia"):
    if "Киров" in address_query or "Kirov" in address_query:
        full_query = address_query
    else:
        full_query = f"{address_query}, {city}"
    
    try:
        location = ox.geocode(full_query)
        return float(location[0]), float(location[1])
    except Exception as e:
        raise ValueError(f"Не удалось найти адрес '{address_query}': {str(e)}")

# ==============================================================================
# 2. УПРАВЛЕНИЕ ГРАФОМ
# ==============================================================================

def init_graph():
    """Инициализация графа ПРИ СТАРТЕ приложения (один раз!)."""
    global _G, _BLOCKED_EDGES, _BLOCKED_EDGES_SET
    
    bbox = (49.586059, 58.581278, 49.682658, 58.616069)
    custom_filter = (
        '["highway"]["area"!~"yes"]'
        '["highway"!~"footway|path|cycleway|bridleway|steps|corridor|elevator|pedestrian|track"]'
    )

    # Загрузка или создание графа
    if not os.path.exists(GRAPH_FILENAME):
        print("📥 Загрузка графа дорожной сети...")
        _G = ox.graph_from_bbox(
            bbox=bbox, 
            custom_filter=custom_filter, 
            network_type="drive", 
            simplify=False,  # Упрощение графа
            retain_all=False,
            truncate_by_edge=True
        )
        _G = ox.distance.add_edge_lengths(_G)
        ox.save_graphml(_G, filepath=GRAPH_FILENAME)
        print(f"✅ Граф сохранён: {len(_G.nodes)} узлов, {len(_G.edges)} рёбер")
    else:
        print("📂 Загрузка графа из файла...")
        _G = ox.load_graphml(filepath=GRAPH_FILENAME)
        print(f"✅ Граф загружён: {len(_G.nodes)} узлов, {len(_G.edges)} рёбер")

    # Загрузка барьеров
    if not os.path.exists(BARRIERS_FILENAME):
        print("🚧 Загрузка барьеров...")
        barriers_gdf = ox.features_from_bbox(bbox=bbox, tags={'barrier': True})
        barrier_types = ['gate', 'lift_gate', 'swing_gate', 'sliding_gate', 'barrier', 'bollard', 'chain']
        if 'barrier' in barriers_gdf.columns:
            barriers_gdf = barriers_gdf[barriers_gdf['barrier'].isin(barrier_types)]
        barriers_gdf.to_file(BARRIERS_FILENAME, driver='GeoJSON')
        print(f"✅ Барьеры сохранены: {len(barriers_gdf)}")
    else:
        barriers_gdf = gpd.read_file(BARRIERS_FILENAME)
        print(f"✅ Барьеры загружены: {len(barriers_gdf)}")

    # ✅ Привязка барьеров ТОЛЬКО ПРИ СТАРТЕ
    print("🔗 Привязка барьеров к графу...")
    _G, _BLOCKED_EDGES = map_barriers_to_graph(_G, barriers_gdf)
    
    # ✅ Конвертируем в set для быстрого поиска O(1) вместо O(n)
    _BLOCKED_EDGES_SET = set(_BLOCKED_EDGES)
    
    print(f"✅ Заблокировано рёбер: {len(_BLOCKED_EDGES_SET)}")
    print("✅ Система готова к работе")

def get_graph():
    """Возвращает кэшированный граф и заблокированные рёбра."""
    if _G is None:
        init_graph()
    return _G, _BLOCKED_EDGES_SET

# ==============================================================================
# 3. ПРИВЯЗКА БАРЬЕРОВ (оптимизирована)
# ==============================================================================

def map_barriers_to_graph(G, barriers_gdf, tolerance=BARRIER_TOLERANCE):
    """Привязывает барьеры к рёбрам графа."""
    blocked_edges = set()
    
    if barriers_gdf is None or len(barriers_gdf) == 0:
        return G, blocked_edges

    barriers_proj = barriers_gdf.to_crs("EPSG:3857").copy()
    _ = barriers_proj.sindex

    print(f"   Обработка {len(G.edges)} рёбер...")
    
    for u, v, key, data in G.edges(keys=True, data=True):
        # Получаем геометрию ребра
        if 'geometry' in data and data['geometry'] is not None:
            edge_geom = data['geometry']
        else:
            node_u, node_v = G.nodes[u], G.nodes[v]
            edge_geom = LineString([(node_u['x'], node_u['y']), (node_v['x'], node_v['y'])])

        edge_gdf = gpd.GeoDataFrame(geometry=[edge_geom], crs="EPSG:4326")
        edge_geom_proj = edge_gdf.to_crs("EPSG:3857").geometry.iloc[0]
        search_box = edge_geom_proj.buffer(tolerance).bounds
        candidates = list(barriers_proj.sindex.intersection(search_box))

        for idx in candidates:
            barrier = barriers_proj.iloc[idx]
            if isinstance(barrier.geometry, Point):
                dist = edge_geom_proj.distance(barrier.geometry)
                if dist <= tolerance:
                    blocked_edges.add((u, v, key))
                    G.edges[u, v, key]['has_barrier'] = True
                    G.edges[u, v, key]['barrier_type'] = barrier.get('barrier', 'unknown')
    
    return G, blocked_edges

# ==============================================================================
# 4. РАСЧЁТ МАРШРУТА (оптимизирован)
# ==============================================================================

def calculate_route(start_addr, end_addr):
    """Основная функция для веб-запроса."""
    G, blocked_edges_set = get_graph()  # ✅ Берём из кэша
    
    # 1. Геокодирование (с кэшем)
    start_coords = geocode_address(start_addr)
    end_coords = geocode_address(end_addr)
    
    # 2. Поиск ближайших узлов
    orig_node = ox.nearest_nodes(G, X=start_coords[1], Y=start_coords[0])
    dest_node = ox.nearest_nodes(G, X=end_coords[1], Y=end_coords[0])
    
    # 3. Весовая функция (быстрая проверка через set)
    def weight(u, v, data):
        for key in G.get_edge_data(u, v).keys():
            if (u, v, key) in blocked_edges_set:
                return float('inf')
        
        length = data.get('length', 0)
        highway = data.get('highway', 'residential')
        if isinstance(highway, list):
            highway = highway[0]
        
        # Получаем штраф (по умолчанию 2.0 для неизвестных)
        penalty = ROAD_PENALTIES.get(highway, 2.0)
        
        return length * penalty

    # 4. A* алгоритм с эвристикой
    try:
        path = nx.astar_path(
            G, 
            source=orig_node, 
            target=dest_node, 
            weight=weight,
            heuristic=lambda u, v: ((G.nodes[u]['x'] - G.nodes[v]['x'])**2 + 
                                    (G.nodes[u]['y'] - G.nodes[v]['y'])**2)**0.5
        )
        used_fallback = False
    except nx.NetworkXNoPath:
        def fallback_weight(u, v, data):
            length = data.get('length', 0)
            for key in G.get_edge_data(u, v).keys():
                if (u, v, key) in blocked_edges_set:
                    return length + 10000
            return length
        
        path = nx.astar_path(
            G, source=orig_node, target=dest_node,
            weight=fallback_weight,
            heuristic=lambda u, v: ((G.nodes[u]['x'] - G.nodes[v]['x'])**2 + 
                                    (G.nodes[u]['y'] - G.nodes[v]['y'])**2)**0.5
        )
        used_fallback = True

    # 5. Сбор геометрии и метрик
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