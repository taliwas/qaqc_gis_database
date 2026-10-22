# TopoLab — Survey Data Workbench

A local Streamlit + Plotly application for land surveying, GIS, boundary and topographic datasets, GPS logs and generic tables. Forest green, safety gold and a light neutral UI provide a three-tab workflow with a global sidebar reset.

## Run locally

For this existing Windows workspace, run `powershell -ExecutionPolicy Bypass -File .\Start.ps1` from the project directory. The launcher prefers the project environment and can fall back to Codex's bundled Python with the existing installed packages if the original Python installation is unavailable. `-Check` verifies imports without starting a server. For a fresh machine, follow the installation steps below first.

Use **Python 3.12** (recommended; Python 3.11+ supported). Extract this archive, open a terminal in the extracted `survey-workbench` directory, then:

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

If Python is available as `python` rather than `py`, use `python -m venv .venv` for the first command. No PowerShell activation or execution-policy changes are needed.

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Open **http://localhost:8501**. Press Ctrl+C in the terminal to stop. Dependency installation needs internet access; normal application processing does not require a cloud service or API key. The default binding is localhost. Data is held in the local server session, not sent to a hosted analysis service. Export before closing/restarting.

## Workflow

1. **Import & schema:** Start with 240 synthetic survey records, or drag/drop a CSV, JSON, GeoJSON, XLSX, KML or GPX. Upload parsing immediately shows size, row/column counts and missing-cell counts. Select the worksheet for Excel, then click **Use uploaded dataset**. A rejected upload does not replace existing work.
2. **Configure:** Map coordinates, ID, feature code, boundary flag, parcel/ring group, vertex order, timestamp and geometry using the sidebar. Select projected/local-grid or geographic coordinates and enter a CRS reference. Generic tables need no spatial mapping.
3. **Quality & cleaning:** Inspect highlighted cells and the exportable issue list; search and paginate either original or working records. Preview a cleaning operation, apply it, and undo up to ten actions. Restore the original import without changing the input file. View statistics and download the working CSV/JSON and audit/configuration JSON.
4. **Spatial dashboard:** Select analysis measurements, map color, category and filters. Hover, zoom, pan and download charts. Configure numeric correlation columns, histogram bins, parcel/ring and tolerance bounds.
5. **Reset All / Start Over:** Available above the tabs and in the sidebar; restores the sample and clears imports, cleaning history, mappings and filters. The header control remains available when the sidebar is collapsed.

## Dashboard inventory

| View | Purpose |
|---|---|
| KPI cards | Total filtered points, projected bounding box area, average Z, discrepancies fixed |
| 01 Plan view | XY scatter colored by an arbitrary field |
| 02 Elevation profile | Elevation over acquisition row order |
| 03 Feature distribution | Top 20 selected categories |
| 04 Completeness matrix | Missing cells across the first 300 filtered records |
| 05 Correlation matrix | Pearson correlation of selected numeric fields |
| 06 Measurement histogram | Frequency distribution and selectable bins |
| 07 Boundary enclosure | Parcel/ring plot, geometry validity and projected ring area |
| 08 Variance & tolerance | Boxplot and user-defined acceptable measurement limits |
| 09 Acquisition progress | Cumulative count by timestamp or row sequence |
| 10 3D survey cloud | Measured XYZ points; no inferred terrain surface |
| 11 Column completeness | Percentage of non-null cells per field |

## Import semantics

- **CSV:** UTF-8 (with or without BOM), automatic delimiter detection. Text IDs such as `001` are preserved. Blank cells/whitespace normalize to missing; pandas' standard null tokens are recognized. Numeric-looking strings are parsed for analysis without modifying source fields.
- **JSON:** Array of objects, one record object, or `{ "data": [...] }`. Nested property values are retained as JSON strings.
- **GeoJSON:** Feature/FeatureCollection and standard geometry objects, including multipart and geometry collections. Lines and polygons expand to vertices; `Part_ID` preserves separate parts/rings. Original geometry and properties are retained. Generated coordinate/identity fields take precedence over conflicting property names. Invalid/unrecognized geometry remains as a record for QA when possible.
- **XLSX:** User-selected worksheet, first row as headers. Text-formatted IDs are preserved; Excel display formatting is not interpreted as data.
- **KML:** Placemark coordinate lists (point, line and polygon rings), names and ExtendedData `Data/value`. Each coordinate list gets a separate `Part_ID`. Google `gx:Track` and styling are not interpreted.
- **GPX:** Track points, route points and waypoints, including elevation/time when present. GPX segment/route topology is not used for boundary calculations.
- XML external entities are rejected. Limits are 25 MB, 100,000 output rows and 200 fields. GeoJSON vertex expansion counts toward the row limit. These are practical survey-table limits, not an out-of-core point-cloud engine; LAS/LAZ, CAD and file geodatabases are not supported.

## QA and calculation definitions

- Missing values: null cells across all columns.
- Coordinate validity: mapped X/Y/Z must parse to finite numbers. Geographic X/Y must lie within ±180°/±90°.
- Duplicate IDs: all occurrences of non-null repeated IDs are flagged. ID deduplication explicitly keeps the first occurrence; blank IDs are retained. Exact row deduplication is a separate action.
- Geometry: mapped WKT or GeoJSON geometry strings are checked for parseability, non-empty and Shapely validity. Original geometry strings are not rewritten when vertex coordinates are cleaned; they represent source geometry.
- Outliers: values outside Q1 − k×IQR and Q3 + k×IQR, where k defaults to 1.5 and is configurable. At least four valid observations are required. Spatial removal combines the independently calculated X and Y masks (axis-aligned heuristic, not local-neighbour detection). Legitimate terrain or disconnected survey areas can trigger these flags.
- Imputation: mean/median of finite numeric values or mode of existing values, filling missing cells only. All-null columns cannot be imputed. Imputed XYZ is an estimate and must not be treated as a measured observation.
- Casting: numeric, text, UTC datetime or boolean. Failed non-text conversions become null and are shown in the preview/QA counts.
- Descriptive statistics: finite numeric values only; sample standard deviation (`ddof=1`). Completeness is non-null coverage, not positional correctness.
- Discrepancies fixed: sum of positive issue-count reductions for applied operations, measured under their active QA configuration. Removed records count toward reductions. Undo reverses the associated credit. This is an action-history measure, not unique repaired points or certified accuracy.
- Bounding box area: `(max X − min X) × (max Y − min Y)` in selected projected units squared. It is **not parcel area**. Degrees are never labeled as metres or used for area reporting. There is no CRS transformation or geodesic area calculation.
- Boundaries: flag values true/1/yes/y/boundary are accepted. Map parcel/part and numeric vertex order. Missing groups are retained. With no order field, input row order is used. Dashed closing edges are illustrative; this does not calculate traverse misclosure from bearing/distance observations. Rings are validated separately, and holes are not subtracted from exterior area.
- Elevations retain the source units and vertical datum. Tolerance ranges apply to the selected measurement; a boxplot of elevations does not establish survey accuracy. Use reference residuals when assessing tolerance.
- Charts needing unmapped/unusable fields show guidance. Plan/3D charts sample at most 10,000 records deterministically; the missingness matrix shows 300; other summaries use all filtered records. Rendering is intended for moderate-size tabular surveys.

## Code layout

```text
app.py                 Session state, imports, controls, cleaning UI and exports
ingestion.py           Multi-format parsers and deterministic sample dataset
quality.py             Schema inference, QA rules, cleaning and boundary validity
dashboard.py           Plotly charts and dashboard filters
tests/test_core.py     Import and calculation regression tests
tests/test_app.py      Streamlit rendering, clean/undo/reset smoke tests
.streamlit/config.toml Theme, local binding, telemetry and upload settings
requirements.txt       Runtime/test dependency version ranges
Start.ps1              Windows launcher with environment verification (-Check)
```

Run tests from the project directory:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Streamlit reference: https://docs.streamlit.io/develop/api-reference
Plotly reference: https://plotly.com/python/
