"""Loss-aware tabular and geospatial import; no network access."""
from io import BytesIO
import json
from pathlib import Path

import numpy as np
import pandas as pd
from defusedxml import ElementTree as ET
from shapely.geometry import shape

MAX_ROWS = 100_000


def sample_data():
    rng = np.random.default_rng(41)
    n = 240
    x, y = rng.uniform(0, 300, n), rng.uniform(0, 200, n)
    df = pd.DataFrame({
        "Point_ID": [f"SGS-{i+1:04d}" for i in range(n)],
        "Easting": np.round(620000+x, 3), "Northing": np.round(175000+y, 3),
        "Elevation": np.round(34 + x*.022 + y*.015 + rng.normal(0, .3, n), 3),
        "Feature_Code": rng.choice(["Tree", "Utility", "Edge of Pavement", "Spot Height"], n),
        "Boundary_Flag": False, "Parcel_ID": "LOT-101", "Vertex_Order": np.arange(1,n+1),
        "Quality_Score": np.round(rng.uniform(80, 100, n), 1),
        "Timestamp": pd.date_range("2026-10-21 08:30", periods=n, freq="30s").astype(str),
    })
    df.loc[:3, ["Easting", "Northing"]] = [[620000,175000],[620300,175000],[620300,175200],[620000,175200]]
    df.loc[:3, "Boundary_Flag"] = True
    df.loc[:3, "Feature_Code"] = "Boundary"
    df.loc[8, "Easting"] = np.nan
    df.loc[[12, 19], "Elevation"] = np.nan
    df.loc[21, "Point_ID"] = df.loc[20, "Point_ID"]
    df.loc[35, "Elevation"] = 115
    return df


def scalar(value):
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value


def geometry_vertices(geom, prefix="0"):
    """Yield vertices with part/ring identity; never silently replace geometry with centroid."""
    typ = geom.get("type", "")
    c = geom.get("coordinates", [])
    if typ == "Point":
        yield prefix, 1, c, False
    elif typ in ("LineString", "MultiPoint"):
        for i, point in enumerate(c):
            yield prefix, i+1, point, False
    elif typ == "Polygon":
        for ring, coords in enumerate(c):
            for i, point in enumerate(coords):
                yield f"{prefix}/ring-{ring}", i+1, point, True
    elif typ in ("MultiLineString", "MultiPolygon"):
        child = "LineString" if typ == "MultiLineString" else "Polygon"
        for i, coords in enumerate(c):
            yield from geometry_vertices({"type": child, "coordinates": coords}, f"{prefix}/{i}")
    elif typ == "GeometryCollection":
        for i, child in enumerate(geom.get("geometries", [])):
            yield from geometry_vertices(child, f"{prefix}/{i}")
    else:
        raise ValueError(f"Unsupported geometry type: {typ}")


def geojson_rows(obj):
    features = obj.get("features", []) if obj.get("type") == "FeatureCollection" else [obj]
    rows = []
    for fi, feature in enumerate(features):
        geom = feature.get("geometry") if feature.get("type") == "Feature" else feature
        props = {str(k): scalar(v) for k,v in (feature.get("properties") or {}).items()}
        base = {**props, "Source_Feature": str(feature.get("id", fi+1)), "geometry": json.dumps(geom)}
        try:
            vertices = list(geometry_vertices(geom)) if geom else []
        except (ValueError, TypeError, AttributeError):
            vertices = []
        if not vertices:
            rows.append(base)
        for part, order, p, boundary in vertices:
            if not isinstance(p, (list, tuple)) or len(p) < 2:
                rows.append(base)
                continue
            rows.append({**base, "Point_ID": f"{fi+1}:{part}:{order}", "Longitude": p[0],
                         "Latitude": p[1], "Elevation": p[2] if len(p)>2 else None,
                         "Part_ID": f"{fi+1}:{part}", "Vertex_Order": order, "Boundary_Flag": boundary})
            if len(rows)>MAX_ROWS:
                raise ValueError(f"Vertex expansion exceeds {MAX_ROWS:,} rows.")
    return pd.DataFrame(rows)


def xml_rows(content, ext):
    root = ET.fromstring(content)
    rows = []
    if ext == ".gpx":
        for i, p in enumerate(e for e in root.iter() if e.tag.split("}")[-1] in ("trkpt", "rtept", "wpt")):
            props = {c.tag.split("}")[-1]: c.text for c in p}
            rows.append({"Point_ID": props.get("name") or f"GPS-{i+1}", "Longitude": p.get("lon"),
                         "Latitude": p.get("lat"), "Elevation": props.get("ele"),
                         "Timestamp": props.get("time"), "Feature_Code": p.tag.split("}")[-1]})
    else:
        placemarks = root.findall(".//{*}Placemark")
        for pi, pm in enumerate(placemarks):
            props = {"Feature_Code": pm.findtext("{*}name", default="KML")}
            for item in pm.findall(".//{*}Data"):
                props[item.get("name", "data")] = item.findtext("{*}value")
            for ci, coords in enumerate(pm.findall(".//{*}coordinates")):
                boundary = any(coords in list(r.iter()) for r in pm.findall(".//{*}LinearRing"))
                for vi, token in enumerate((coords.text or "").split()):
                    p = token.split(",")
                    if len(p)<2:
                        raise ValueError("KML coordinate must contain longitude,latitude[,elevation].")
                    rows.append({**props, "Point_ID": f"KML-{pi+1}-{ci+1}-{vi+1}",
                                 "Longitude": p[0], "Latitude": p[1], "Elevation": p[2] if len(p)>2 else None,
                                 "Part_ID": f"{pi+1}:{ci+1}", "Vertex_Order": vi+1, "Boundary_Flag": boundary})
    return pd.DataFrame(rows)


def load_data(name, content, sheet=0):
    if len(content)>25*1024*1024:
        raise ValueError("File exceeds the 25 MB limit.")
    ext = Path(name).suffix.lower()
    note = ""
    if ext == ".csv":
        df = pd.read_csv(BytesIO(content), sep=None, engine="python", dtype=object, encoding="utf-8-sig")
    elif ext == ".xlsx":
        df = pd.read_excel(BytesIO(content), sheet_name=sheet, engine="openpyxl", dtype=object)
    elif ext in (".json", ".geojson"):
        obj = json.loads(content.decode("utf-8-sig"))
        if isinstance(obj, dict) and obj.get("type") in ("FeatureCollection", "Feature", "Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon", "GeometryCollection"):
            df = geojson_rows(obj)
            note = "Geometry expanded into vertices; feature properties and original geometry retained. Part_ID separates rings and parts. GeoJSON XY assumes WGS84 longitude/latitude; legacy CRS is not reprojected."
        else:
            if isinstance(obj, dict) and isinstance(obj.get("data"), list):
                obj = obj["data"]
            if isinstance(obj, dict):
                obj = [obj]
            if not isinstance(obj, list) or not all(isinstance(v, dict) for v in obj):
                raise ValueError("JSON must contain an array of records, an object, or {data: [...]}.")
            df = pd.DataFrame([{str(k): scalar(v) for k,v in r.items()} for r in obj])
    elif ext in (".kml", ".gpx"):
        df = xml_rows(content, ext)
        note = "WGS84 longitude/latitude. KML rings/lines become ordered vertices; GPX track, route and waypoint records become points. Altitudes retain source values and datum."
    else:
        raise ValueError("Supported formats: CSV, JSON, GeoJSON, XLSX, KML, GPX.")
    if df.empty or not len(df.columns):
        raise ValueError("No records found in the selected file/sheet.")
    if len(df)>MAX_ROWS or len(df.columns)>200:
        raise ValueError("Limit: 100,000 records and 200 columns per dataset.")
    df.columns = [str(c) for c in df.columns]
    if df.columns.duplicated().any():
        raise ValueError("Duplicate column names must be renamed before import.")
    # Blank strings are missing; original nonblank text and identifiers are preserved.
    with pd.option_context("future.no_silent_downcasting", True):
        df = df.replace(r"^\s*$", np.nan, regex=True).reset_index(drop=True)
    return df, note
