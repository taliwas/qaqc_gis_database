"""Survey QA rules and explicit, independently testable cleaning operations."""
import json
import numpy as np
import pandas as pd
from shapely import wkt
from shapely.geometry import shape, Polygon


ALIASES = {
    "x": ["easting", "x", "longitude", "lon", "long"],
    "y": ["northing", "y", "latitude", "lat"],
    "z": ["elevation", "z", "height", "altitude", "rl"],
    "id": ["point_id", "pointid", "id", "point"],
    "code": ["feature_code", "code", "feature", "type"],
    "boundary": ["boundary_flag", "boundary"],
    "group": ["part_id", "parcel_id", "lot_id"],
    "order": ["vertex_order", "sequence", "order"],
    "time": ["timestamp", "time", "date"],
    "geometry": ["geometry", "wkt", "geom"],
}


def infer_columns(df):
    lookup = {str(c).strip().lower(): c for c in df.columns}
    return {key: next((lookup[a] for a in aliases if a in lookup), None) for key, aliases in ALIASES.items()}


def numeric(s):
    # Float analysis supports nullable integers and booleans in IQR arithmetic.
    return pd.to_numeric(s, errors="coerce").astype(float).replace([np.inf, -np.inf], np.nan)


def numeric_columns(df):
    return [c for c in df
            if not pd.api.types.is_datetime64_any_dtype(df[c])
            and not pd.api.types.is_bool_dtype(df[c])
            and numeric(df[c]).notna().any()]


def category_labels(s):
    """Render nullable numeric/boolean categories without dtype-invalid fills."""
    return s.astype("string").fillna("(missing)")


def outlier_mask(s, factor=1.5):
    v = numeric(s)
    q1, q3 = v.quantile([.25, .75])
    if v.notna().sum()<4 or pd.isna(q1):
        return pd.Series(False, index=s.index)
    return (v < q1-factor*(q3-q1)) | (v > q3+factor*(q3-q1))


def valid_geometry(value):
    if pd.isna(value):
        return True
    try:
        text = str(value).strip()
        geom = shape(json.loads(text)) if text.startswith("{") else wkt.loads(text)
        return not geom.is_empty and geom.is_valid
    except Exception:
        return False


def detect_issues(df, mapping, factor=1.5, geographic=False):
    rows = []
    def add(mask, col, issue, severity="Warning"):
        for idx in df.index[mask]:
            rows.append({"Row": int(idx)+1, "Column": col, "Issue": issue,
                         "Severity": severity, "Value": str(df.at[idx,col])})
    for c in df:
        add(df[c].isna(), c, "Missing value")
    for c in dict.fromkeys(mapping.get(k) for k in ("x", "y", "z") if mapping.get(k)):
        add(df[c].notna() & numeric(df[c]).isna(), c, "Non-numeric / non-finite coordinate", "Error")
    idcol = mapping.get("id")
    if idcol:
        add(df[idcol].notna() & df[idcol].duplicated(keep=False), idcol, "Duplicate Point ID", "Error")
    z = mapping.get("z")
    if z:
        add(outlier_mask(df[z], factor), z, "Elevation IQR outlier")
    if geographic:
        for key, limit in (("x",180),("y",90)):
            c = mapping.get(key)
            if c:
                add(numeric(df[c]).abs()>limit,c,"Coordinate outside geographic range","Error")
    gc = mapping.get("geometry")
    if gc:
        add(~df[gc].map(valid_geometry),gc,"Invalid / empty geometry","Error")
    for key in ("x", "y"):
        c = mapping.get(key)
        if c:
            add(outlier_mask(df[c],factor),c,"Spatial axis IQR outlier")
    return pd.DataFrame(rows, columns=["Row","Column","Issue","Severity","Value"])


def clean(df, action, column=None, method="Median", factor=1.5, mapping=None):
    result = df.copy(deep=True)
    if action == "Drop duplicate rows":
        result = result.drop_duplicates()
    elif action == "Drop duplicate Point IDs":
        if not column:
            raise ValueError("Map a Point ID column first.")
        result = result.loc[~(result[column].notna() & result[column].duplicated())]
    elif action == "Impute missing values":
        if method in ("Median","Mean"):
            values = numeric(result[column])
            if not values.notna().any():
                raise ValueError("No valid values available to calculate a fill value.")
            fill = values.median() if method=="Median" else values.mean()
        else:
            modes = result[column].mode()
            fill = modes.iloc[0] if len(modes) else np.nan
        if pd.isna(fill):
            raise ValueError("No valid values available to calculate a fill value.")
        # Object accommodates fractional estimates in nullable integer fields,
        # while preserving existing nonempty values, including invalid text.
        with pd.option_context("future.no_silent_downcasting", True):
            result[column] = result[column].astype(object).fillna(fill).infer_objects(copy=False)
    elif action == "Remove elevation outliers":
        result = result.loc[~outlier_mask(result[column],factor)]
    elif action == "Remove spatial outliers":
        mask = pd.Series(False,index=result.index)
        for key in ("x","y"):
            c = (mapping or {}).get(key)
            if c:
                mask |= outlier_mask(result[c],factor)
        result = result.loc[~mask]
    elif action == "Cast column":
        if method=="Numeric":
            result[column] = numeric(result[column])
        elif method=="Text":
            result[column] = result[column].astype("string")
        elif method=="Datetime":
            result[column] = pd.to_datetime(result[column],errors="coerce",utc=True)
        elif method=="Boolean":
            result[column] = result[column].astype("string").str.lower().str.strip().map({"true":True,"false":False,"1":True,"0":False,"yes":True,"no":False}).astype("boolean")
    return result.reset_index(drop=True)


def boundary_points(df, mapping):
    b = mapping.get("boundary")
    if not b:
        return df.iloc[0:0].copy()
    mask = df[b].astype(str).str.lower().str.strip().isin(["true","1","1.0","yes","y","boundary"])
    return df.loc[mask].copy()


def boundary_metrics(points):
    if len(points)<3:
        return "Fewer than 3 vertices", None
    poly = Polygon(points)
    if not poly.is_valid or poly.area == 0:
        return "Invalid / self-intersecting / zero-area ring", None
    return "Valid ring geometry", poly.area


def completeness(df):
    return 100*df.notna().to_numpy().mean() if df.size else 0.0
