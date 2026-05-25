"""
shapes.py
=========
Loads the Guwahati road network shapefile, reprojects from UTM Zone 46N
(EPSG:32646) to WGS84 (EPSG:4326), and extracts corridor geometries
for use as map layers in the Streamlit dashboard.

The shapefile (RoadGuwahati.shp) must be present at DATA_DIR.
On Streamlit Cloud the file is committed to the repo under data/.
On local Mac it is read from the same relative path.
"""

import os
import numpy as np
import geopandas as gpd
import pandas as pd
from shapely.geometry import box, LineString, MultiLineString
from functools import lru_cache
from typing import Optional

from .config import CORRIDORS

# ── Path ──────────────────────────────────────────────────────────────────────
_HERE     = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(_HERE, "..", "data")
SHP_PATH  = os.path.join(DATA_DIR, "RoadGuwahati.shp")

# ── Road type filter ──────────────────────────────────────────────────────────
# ROAD_TYPE 1 = national highway / major arterial (PWD classified)
# ROAD_TYPE 2 = state road / major urban road
# Keep only 1 and 2 for the corridor base layer; omit lanes and bye-lanes
DISPLAY_ROAD_TYPES = {"1", "2"}   # stored as strings in the shapefile

# ── Corridor bounding boxes (WGS84) ──────────────────────────────────────────
# Generous buffers around each corridor to clip the road network
_CORRIDOR_BBOX = {
    "GS_ROAD":             box(91.660, 26.110, 91.835, 26.205),
    "NH37":                box(91.650, 26.095, 91.845, 26.160),
    "BASISTHA_DISPUR":     box(91.785, 26.110, 91.805, 26.150),
    "GANESHGURI_GAMESVLG": box(91.782, 26.108, 91.795, 26.155),
}

# ── Named road filters for each corridor ─────────────────────────────────────
_CORRIDOR_ROAD_NAMES = {
    "GS_ROAD":             ["G.S. ROAD", "GS ROAD", "GANESHGURI FLY OVER"],
    "NH37":                ["N.H. - 37", "NATIONAL HIGHWAY 37", "NH_SERVICE LANE",
                            "NATIONAL HIGHWAY-37", "NH_FLYOVER"],
    "BASISTHA_DISPUR":     ["BASISTHA", "SURVEY", "DISPUR"],
    "GANESHGURI_GAMESVLG": ["HATIGAON", "BHETAPARA", "GAMES VILLAGE"],
}


@lru_cache(maxsize=1)
def _load_full_network() -> gpd.GeoDataFrame:
    """
    Load and reproject the full road network once; cache in memory.
    Filters to display road types only.
    """
    if not os.path.exists(SHP_PATH):
        raise FileNotFoundError(
            f"Shapefile not found at {SHP_PATH}. "
            "Place RoadGuwahati.shp and companions in the data/ folder."
        )
    gdf = gpd.read_file(SHP_PATH)
    gdf = gdf[gdf["ROAD_TYPE"].isin(DISPLAY_ROAD_TYPES)].copy()
    gdf = gdf.to_crs(epsg=4326)
    return gdf


def get_corridor_layer(corridor_key: str) -> gpd.GeoDataFrame:
    """
    Return the road network clipped to the corridor bounding box,
    with named corridor roads highlighted.

    Parameters
    ----------
    corridor_key : "GS_ROAD" or "NH37"

    Returns
    -------
    gpd.GeoDataFrame (EPSG:4326) with extra column:
        is_primary  bool — True for the main corridor road
    """
    gdf  = _load_full_network()
    bbox = _CORRIDOR_BBOX.get(corridor_key)
    if bbox is None:
        raise ValueError(f"Unknown corridor key: {corridor_key}")

    clipped = gdf[gdf.geometry.intersects(bbox)].copy()

    names = _CORRIDOR_ROAD_NAMES.get(corridor_key, [])
    clipped["is_primary"] = clipped["Final_Road"].str.upper().apply(
        lambda x: any(n.upper() in str(x) for n in names)
    )
    return clipped.reset_index(drop=True)


def get_stop_geodataframe(corridor_key: str) -> gpd.GeoDataFrame:
    """
    Convert the stop list from config into a GeoDataFrame of Point geometries.

    Returns
    -------
    gpd.GeoDataFrame with columns: id, name, lat, lng, geometry (EPSG:4326)
    """
    stops = CORRIDORS[corridor_key]["stops"]
    valid = [s for s in stops if s["lat"] is not None]
    df = pd.DataFrame(valid)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["lng"], df["lat"]),
        crs="EPSG:4326",
    )
    return gdf


def corridor_geojson(corridor_key: str) -> dict:
    """
    Return the corridor road layer as a GeoJSON-compatible dict.
    Suitable for passing to pydeck / folium / plotly mapbox layers.

    Structure
    ---------
    {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": ..., "road_type": ..., "is_primary": ...},
                "geometry": { ... }
            }, ...
        ]
    }
    """
    layer = get_corridor_layer(corridor_key)
    return layer[["Final_Road", "ROAD_TYPE", "is_primary", "geometry"]] \
               .__geo_interface__


def stops_geojson(corridor_key: str) -> dict:
    """Return stop points as a GeoJSON FeatureCollection."""
    return get_stop_geodataframe(corridor_key).__geo_interface__


def network_bounds(corridor_key: str) -> dict:
    """
    Return map bounds for the corridor as {min_lat, max_lat, min_lng, max_lng}.
    Used to set the initial map viewport in the Streamlit app.
    """
    stops = CORRIDORS[corridor_key]["stops"]
    valid = [s for s in stops if s["lat"] is not None]
    lats  = [s["lat"] for s in valid]
    lngs  = [s["lng"] for s in valid]
    pad   = 0.01
    return {
        "min_lat": min(lats) - pad,
        "max_lat": max(lats) + pad,
        "min_lng": min(lngs) - pad,
        "max_lng": max(lngs) + pad,
        "center_lat": np.mean(lats),
        "center_lng": np.mean(lngs),
    }
