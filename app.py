"""TopoLab · local survey data workbench. Run: streamlit run app.py"""
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import json
import math

import numpy as np
import pandas as pd
import streamlit as st
import base64
from pathlib import Path

from ingestion import sample_data, load_data
from quality import infer_columns, numeric, numeric_columns, detect_issues, clean, completeness, category_labels
from dashboard import render_dashboard

st.set_page_config(page_title="SETIA TopoLab | Survey Workbench", page_icon="📐",layout="wide")
st.markdown("""<style>
 .block-container {padding-top:2rem; max-width:1600px;}
 [data-testid="stSidebar"] {border-right:1px solid #d6dfd3;}
 h1,h2,h3 {letter-spacing:-.035em;}
 [data-testid="stMetric"] {background:#fff;border:1px solid #dce4d8;border-top:3px solid #c9aa32;
 border-radius:10px;padding:15px 18px;}
 .eyebrow {color:#436750;font-size:12px;letter-spacing:.19em;font-weight:700;}
 .hero {background:#173e30;color:#f6f8ed;border-radius:16px;padding:25px 30px;margin-bottom:22px;
 background-image:repeating-radial-gradient(ellipse at 95% 130%,transparent 0 23px,#ffffff09 24px 25px);}
 .hero h1 {color:#f6f8ed;font-size:2.6rem;margin:0;}
 .hero p {color:#c6d8cb;margin:8px 0 0;}
 .hero .eyebrow {color:#e4c853;}
 [data-baseweb="tab-list"] {gap:12px;}
 [data-baseweb="tab"] {padding:12px 16px;}
 @media(max-width:750px){.block-container{padding:1rem;} .hero{padding:18px;}.hero h1{font-size:2rem;}}
 </style>""",unsafe_allow_html=True)


def install(df, name, size=0, note=""):
    # Reset controls before widgets are instantiated on the next rerun.
    for key in list(st.session_state):
        if key.startswith(("map_","dash_","corr_","boundary_","page_","clean_","cast_","impute_","tolerance_")) or key in ("coord_mode","unit","crs"):
            del st.session_state[key]
    st.session_state.raw = df.copy(deep=True)
    st.session_state.working = df.copy(deep=True)
    st.session_state.name,st.session_state.size,st.session_state.note = name,size,note
    st.session_state.audit,st.session_state.history = [],[]
    st.session_state.fixed = 0
    st.session_state.preview = None
    st.session_state.revision = 0


def reset():
    for key in list(st.session_state):
        del st.session_state[key]


if "working" not in st.session_state:
    install(sample_data(),"Land Surveying Dataset · sample",note="Synthetic projected coordinates in metres, not an identified CRS. Includes intentional missing values, a duplicate ID and an elevation outlier.")
ss = st.session_state

with st.sidebar:
    st.markdown("## ⌖ SETIA-TopoLab")
    st.caption("SURVEY DATA WORKBENCH")
    st.button("↺ Reset All / Start Over",on_click=reset,width="stretch",help="Discard this session and restore the sample, including all mapping and filter defaults.")
    st.divider()
    st.markdown("**Coordinate configuration**")
    inferred = infer_columns(ss.working)
    default_geo = inferred.get("x") and str(inferred["x"]).lower() in ("longitude","lon","long")
    mode = st.selectbox("Coordinate system",["Projected / local grid","Geographic (longitude / latitude)"],index=1 if default_geo else 0,key="coord_mode")
    geographic = mode.startswith("Geographic")
    units = st.selectbox("Horizontal units",["m","ft","units"],disabled=geographic,key="unit")
    st.text_input("CRS / EPSG reference (metadata only)",value="EPSG:4326" if geographic else "Unknown / local grid",key="crs")
    st.caption("No automatic reprojection. Geographic area is intentionally unavailable.")
    names = {"x":"X / Easting / Longitude","y":"Y / Northing / Latitude","z":"Z / Elevation","id":"Point ID","code":"Feature code","boundary":"Boundary flag","group":"Parcel / part group","order":"Vertex order","time":"Acquisition time","geometry":"Geometry / WKT"}
    mapping = {}
    options = [None]+list(ss.working.columns)
    with st.expander("Field mapping",expanded=True):
        for key,label in names.items():
            mapping[key] = st.selectbox(label,options,index=options.index(inferred.get(key)),
                                       format_func=lambda v:v if v is not None else "Not mapped",key="map_"+key)
    factor = st.slider("Outlier IQR multiplier",1.0,5.0,1.5,.25,key="iqr")
    st.caption("IQR flags are review candidates. They are not proof of a survey error.")

logo_path = Path(__file__).resolve().parent / "assets" / "company_logo.png"
logo_base64 = base64.b64encode(logo_path.read_bytes()).decode("utf-8")

st.markdown(
    f"""
    <style>
        .brand-header {{
            display: flex;
            align-items: center;
            gap: 20px;
        }}

        .brand-logo {{
            width: 90px;
            height: 90px;
            object-fit: contain;
            flex-shrink: 0;
        }}

        .brand-header h1 {{
            margin: 0;
            line-height: 1.15;
        }}

        @media (max-width: 600px) {{
            .brand-logo {{
                width: 58px;
                height: 58px;
            }}

            .brand-header {{
                gap: 12px;
            }}

            .brand-header h1 {{
                font-size: 1.7rem;
            }}
        }}
    </style>

    <div class="hero">
        <div class="brand-header">
            <img
                class="brand-logo"
                src="data:image/png;base64,{logo_base64}"
                alt="SETIA company logo"
            />
            <div>
                <div class="eyebrow">SURVEY DATA WORKBENCH</div>
                <h1>SETIA-TopoLab</h1>
            </div>
        </div>
        <p>Import, inspect and explore your survey data in one workspace.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
top = st.columns([3,1])
top[0].caption(f"ACTIVE DATASET  /  {ss.name}")
top[1].caption(f"{len(ss.working):,} records · {len(ss.working.columns)} fields")
top[1].button("Reset All / Start Over", key="header_reset", on_click=reset,
              help="Restore the sample and clear this session.", width="stretch")
if mapping["x"] and mapping["x"]==mapping["y"]:
    st.warning("X and Y must map to distinct columns for spatial views.")
issues = detect_issues(ss.working,mapping,factor,geographic)
tab1,tab2,tab3 = st.tabs(["01  Import & schema","02  Quality & cleaning","03  Spatial dashboard"])

with tab1:
    st.markdown("### Bring your field data into focus")
    left,right = st.columns([1.3,1])
    with left, st.container(border=True):
        st.markdown("#### Import a dataset")
        upload = st.file_uploader("Drop a file or browse",type=["csv","json","geojson","xlsx","kml","gpx"],key="upload")
        st.caption("25 MB · 100,000 rows · 200 columns. Excel supports worksheet selection. CSV uses UTF-8 and delimiter detection.")
        sheet = 0
        upload_ok = True
        if upload:
            st.caption(f"Ready: {upload.name} · {upload.size/1024:,.1f} KB")
            if upload.name.lower().endswith(".xlsx"):
                try:
                    with pd.ExcelFile(BytesIO(upload.getvalue()),engine="openpyxl") as workbook:
                        sheet = st.selectbox("Worksheet",workbook.sheet_names,key="sheet")
                except Exception as exc:
                    st.error(f"Cannot read Excel workbook: {exc}")
                    upload_ok = False
            signature = hashlib.sha256(upload.getvalue()).hexdigest()+str(sheet)
            # Immediate parsing with a staging preview; existing work survives a failed import.
            if upload_ok and ss.get("staged_signature")!=signature:
                try:
                    staged,note = load_data(upload.name,upload.getvalue(),sheet)
                    ss.staged = (staged,note)
                    ss.staged_signature = signature
                    ss.staged_error = None
                except Exception as exc:
                    ss.staged = None
                    ss.staged_signature = signature
                    ss.staged_error = str(exc)
            if upload_ok and ss.get("staged_error"):
                st.error(ss.staged_error)
            elif upload_ok and ss.get("staged") is not None:
                staged,note = ss.staged
                st.success(f"Parsed successfully · {len(staged):,} rows × {len(staged.columns)} columns")
                st.dataframe(pd.DataFrame({"Column":staged.columns,"Type":staged.dtypes.astype(str).values,"Missing":staged.isna().sum().values}),hide_index=True,width="stretch")
                if st.button("Use uploaded dataset",type="primary"):
                    install(staged,upload.name,upload.size,note)
                    st.rerun()
        if st.button("Load sample surveying dataset",width="stretch"):
            install(sample_data(),"Land Surveying Dataset · sample",note="Synthetic projected metre coordinates with intentional QA issues.")
            st.rerun()
    with right, st.container(border=True):
        st.markdown("#### Schema readiness")
        statuses = []
        for key,label in names.items():
            col = mapping[key]
            valid = numeric(ss.working[col]).notna().sum() if col and key in ("x","y","z") else ss.working[col].notna().sum() if col else 0
            statuses.append({"Role":label,"Column":col or "Not mapped","Valid / present":int(valid),"Status":"Ready" if col and valid else "Optional / needs mapping"})
        st.dataframe(pd.DataFrame(statuses),hide_index=True,width="stretch")
        st.info(ss.note or "Tabular data retained as imported. Use the field mapping controls for spatial analysis.")
        st.caption(f"Imported size: {ss.size/1024:,.1f} KB" if ss.size else "Built-in sample dataset")
        st.download_button("Download sample CSV",sample_data().to_csv(index=False).encode(),"land_survey_sample.csv","text/csv")
    st.markdown("#### Import preview · original records")
    st.dataframe(ss.raw.head(25),width="stretch",hide_index=True)

with tab2:
    st.markdown("### Inspect, resolve, verify")
    cards = st.columns(4)
    cards[0].metric("Completeness",f"{completeness(ss.working):.1f}%")
    cards[1].metric("Issue entries",f"{len(issues):,}")
    cards[2].metric("Affected records",f"{issues.Row.nunique():,}")
    cards[3].metric("Cleaning actions",str(len(ss.audit)))
    st.caption("A record can contain multiple issue entries. Completeness measures non-null cells; numeric validity is checked separately.")
    with st.expander("Detected issues",expanded=True):
        st.dataframe(issues,width="stretch",hide_index=True,height=230)
        st.download_button("Export issues CSV",issues.to_csv(index=False).encode(),"survey_issues.csv","text/csv")
    st.markdown("#### Dataset explorer")
    controls = st.columns([1,2,1,1])
    source = controls[0].selectbox("View",["Working copy","Original import"],key="data_source")
    query = controls[1].text_input("Search all fields",key="table_search")
    size = controls[2].selectbox("Rows per page",[25,50,100,250],key="page_size")
    table = (ss.working if source=="Working copy" else ss.raw).copy()
    if query:
        mask = table.astype(str).apply(lambda s:s.str.contains(query,case=False,regex=False)).any(axis=1)
        table = table.loc[mask]
    pages = max(1,math.ceil(len(table)/size))
    if ss.get("page_number",1)>pages:
        ss.page_number = pages
    page = controls[3].number_input("Page",1,pages,key="page_number")
    window = table.iloc[(page-1)*size:page*size]
    if source=="Working copy":
        flagged = {(int(r.Row)-1,r.Column) for r in issues.itertuples()}
        def highlight(frame):
            return pd.DataFrame([["background-color:#fae7b0;color:#533e0b" if (i,c) in flagged else "" for c in frame.columns] for i in frame.index],index=frame.index,columns=frame.columns)
        st.dataframe(window.style.apply(highlight,axis=None),width="stretch")
    else:
        st.dataframe(window,width="stretch")
    st.caption(f"Page {page}/{pages} · {len(table):,} matching records · Yellow cells have detected issues. Table sorting applies to the displayed page.")
    with st.container(border=True):
        st.markdown("#### Cleaning station")
        st.caption("Preview an explicit operation, then apply it to the working copy. Original records remain available. Undo retains the last 10 actions.")
        cols = st.columns(3)
        action = cols[0].selectbox("Operation",["Drop duplicate rows","Drop duplicate Point IDs","Impute missing values","Remove elevation outliers","Remove spatial outliers","Cast column"],key="clean_action")
        column,method = None,"Median"
        if action=="Drop duplicate Point IDs":
            column = mapping["id"]
            cols[1].caption(f"ID column: {column or 'not mapped'} · first occurrence retained; missing IDs retained.")
        elif action=="Remove elevation outliers":
            column = mapping["z"]
            cols[1].caption(f"Elevation column: {column or 'not mapped'}")
        elif action in ("Impute missing values","Cast column"):
            column = cols[1].selectbox("Target column",list(ss.working.columns),key="clean_column")
            choices = ["Mean","Median","Mode"] if action=="Impute missing values" else ["Numeric","Text","Datetime","Boolean"]
            method = cols[2].selectbox("Method / type",choices,key="clean_method")
        if action=="Impute missing values":
            st.warning("Imputed coordinates/elevations are estimates, not surveyed observations. This action fills missing cells only; invalid nonempty values require correction or a type cast first.")
        if action=="Cast column":
            st.caption("Unparseable values become null. Boolean accepts true/false, yes/no and 1/0. Datetimes normalize to UTC.")
        signature = json.dumps([ss.revision,action,column,method,factor,mapping,geographic],sort_keys=True)
        if st.button("Preview fix",type="primary"):
            try:
                if action in ("Drop duplicate Point IDs","Remove elevation outliers") and not column:
                    raise ValueError("Map the required column in the sidebar first.")
                if action=="Remove spatial outliers" and not (mapping["x"] and mapping["y"]):
                    raise ValueError("Map both X and Y columns first.")
                proposal = clean(ss.working,action,column,method,factor,mapping)
                after = detect_issues(proposal,mapping,factor,geographic)
                ss.preview = {"signature":signature,"data":proposal,"before":len(issues),"after":len(after),"action":action,"column":column,"method":method}
            except Exception as exc:
                ss.preview = None
                st.error(str(exc))
        preview = ss.preview
        if preview and preview["signature"]==signature:
            st.info(f"Records: {len(ss.working):,} → {len(preview['data']):,} · Issue entries: {preview['before']:,} → {preview['after']:,}")
            st.dataframe(preview["data"].head(12),hide_index=True,width="stretch")
            if st.button("Apply this fix",disabled=preview["data"].equals(ss.working)):
                ss.history.append((ss.working.copy(deep=True),list(ss.audit),ss.fixed))
                ss.history = ss.history[-10:]
                credit = max(0,preview["before"]-preview["after"])
                ss.audit.append({"UTC":datetime.now(timezone.utc).isoformat(),"Action":action,"Column":column,"Method":method,
                                 "Rows before":len(ss.working),"Rows after":len(preview["data"]),"Issues before":preview["before"],"Issues after":preview["after"],"Fixed credit":credit})
                ss.fixed += credit
                ss.working = preview["data"]
                ss.revision += 1
                ss.preview = None
                st.rerun()
        back,restore = st.columns(2)
        if back.button("Undo last fix",disabled=not ss.history,width="stretch"):
            ss.working,ss.audit,ss.fixed = ss.history.pop()
            ss.revision += 1
            ss.preview = None
            st.rerun()
        if restore.button("Restore original import",disabled=not ss.audit,width="stretch"):
            ss.working = ss.raw.copy(deep=True)
            ss.audit,ss.history,ss.fixed,ss.preview = [],[],0,None
            ss.revision += 1
            st.rerun()
    st.markdown("#### Statistical summary")
    nums = numeric_columns(ss.working)
    if nums:
        statistics = ss.working[nums].apply(numeric).agg(["count","mean","median","std","min","max"]).T
        st.dataframe(statistics,width="stretch")
        st.caption("Standard deviation uses ddof=1 (sample). Invalid/non-finite measurements are excluded; numeric-looking text is parsed for analysis without altering source records.")
    else:
        st.info("No numeric columns available; categorical datasets remain supported.")
    if mapping["code"]:
        st.dataframe(category_labels(ss.working[mapping["code"]]).value_counts().rename_axis("Feature code").reset_index(name="Records"),hide_index=True)
    with st.expander("Audit trail & exports"):
        st.dataframe(pd.DataFrame(ss.audit),hide_index=True,width="stretch")
        st.download_button("Download cleaned CSV",ss.working.to_csv(index=False).encode(),"survey_cleaned.csv","text/csv")
        st.download_button("Download cleaned JSON",ss.working.to_json(orient="records",date_format="iso",indent=2),"survey_cleaned.json","application/json")
        metadata = {"source":ss.name,"crs":ss.crs,"horizontal_units":"degrees" if geographic else units,"mapping":mapping,"iqr_multiplier":factor,"actions":ss.audit}
        st.download_button("Download audit & configuration",json.dumps(metadata,indent=2),"survey_audit.json","application/json")

with tab3:
    render_dashboard(ss.working,mapping,geographic,units,ss.fixed)
st.caption("TopoLab · Local processing · Survey / GIS / Civil engineering · Export your work before closing the session.")
