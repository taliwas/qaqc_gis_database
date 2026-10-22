"""Interactive analytical views; chart sampling is disclosed, metrics use all rows."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from quality import numeric, numeric_columns, completeness, boundary_points, boundary_metrics, category_labels

COLORS = ["#24664d", "#c69b22", "#669b83", "#527985", "#a27852", "#79805a", "#ca6653"]


def chart(fig, key):
    fig.update_layout(template="plotly_white", height=345, margin=dict(l=20,r=20,t=25,b=30),
                      font=dict(family="Arial", color="#243e33"), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", colorway=COLORS,
                      legend=dict(orientation="h", y=-.25), hovermode="closest")
    st.plotly_chart(fig, width="stretch", key=key,
                    config={"displaylogo":False,"toImageButtonOptions":{"format":"png","scale":2}})


def panel(title, subtitle):
    st.markdown(f"#### {title}")
    st.caption(subtitle)


def render_dashboard(df, mapping, geographic, units, fixed):
    st.markdown("### Survey intelligence")
    st.caption("Explore the working dataset. Filters affect all dashboard charts and point metrics; the audit total remains session-wide.")
    nums = numeric_columns(df)
    a,b,c = st.columns(3)
    with a:
        measure = st.selectbox("Analysis measurement", nums or [None],
                               index=nums.index(mapping["z"]) if mapping.get("z") in nums else 0,
                               format_func=lambda v: v or "No numeric column", key="dash_measure")
    with b:
        color = st.selectbox("Plan color", [None]+list(df.columns),
                             index=1+list(df.columns).index(mapping["code"]) if mapping.get("code") else 0,
                             format_func=lambda v:v or "Uniform",key="dash_color")
    with c:
        category = st.selectbox("Distribution category", [None]+list(df.columns),
                               index=1+list(df.columns).index(mapping["code"]) if mapping.get("code") else 0,
                               format_func=lambda v:v or "Not mapped",key="dash_category")
    view = df.copy()
    if category:
        categories = sorted(category_labels(view[category]).unique())
        if len(categories)<=200:
            selected = st.multiselect("Include categories (empty = all)",categories,key="dash_filter")
            if selected:
                view = view.loc[category_labels(view[category]).isin(selected)].copy()
        else:
            st.caption("Category filter omitted for >200 distinct values; distributions show the top 20.")
    x,y,z = (mapping.get(k) for k in ("x","y","z"))
    xy_ok = bool(x and y and x != y)
    if xy_ok:
        view[x],view[y] = numeric(view[x]),numeric(view[y])
    if z:
        view[z] = numeric(view[z])
    spatial = view.dropna(subset=[x,y]) if xy_ok else view.iloc[:0]
    if geographic and xy_ok:
        spatial = spatial.loc[spatial[x].abs().le(180) & spatial[y].abs().le(90)]
    metric = st.columns(4)
    metric[0].metric("Survey points", f"{len(view):,}")
    area = (spatial[x].max()-spatial[x].min())*(spatial[y].max()-spatial[y].min()) if len(spatial) else np.nan
    metric[1].metric("Bounding box area" if not geographic else "Bounding area", "N/A · degrees" if geographic else f"{area:,.1f} {units}²" if np.isfinite(area) else "—")
    avg = numeric(view[z]).mean() if z else np.nan
    metric[2].metric("Average elevation",f"{avg:,.3f}" if np.isfinite(avg) else "—")
    metric[3].metric("Discrepancies fixed",str(fixed),help="Net reduction in detected issue entries after each applied cleaning action; deletions are included. Undo reverses its credit.")
    st.caption(f"{len(spatial):,} valid spatial points · {completeness(view):.1f}% non-null cells · Z retains the source vertical units/datum. Bounding box area is not parcel area.")
    if len(spatial)>10000:
        st.info("Plan and 3D plots display a deterministic sample of 10,000 points. Other summaries use all filtered records.")
    plot = spatial.sample(10000,random_state=42).sort_index() if len(spatial)>10000 else spatial
    left,right = st.columns(2)
    with left, st.container(border=True):
        panel("01 / Plan view", "Pan, zoom and hover to inspect survey points.")
        if len(plot):
            plotted = plot.copy()
            if color:
                if color in nums:
                    plotted[color] = numeric(plotted[color])
                else:
                    plotted[color] = category_labels(plotted[color])
            fig = px.scatter(plotted,x=x,y=y,color=color,color_discrete_sequence=COLORS,
                             color_continuous_scale="Viridis",hover_name=mapping.get("id"))
            fig.update_traces(marker_size=7)
            if not geographic:
                fig.update_yaxes(scaleanchor="x",scaleratio=1)
            chart(fig,"plan")
        else:
            st.info("Map distinct X and Y columns with valid numeric coordinates in the sidebar.")
    with right, st.container(border=True):
        panel("02 / Elevation profile", "Acquisition order; breaks retain missing measurements.")
        if z:
            p = pd.DataFrame({"Acquisition row":np.arange(1,len(view)+1),z:numeric(view[z]).to_numpy()})
            chart(px.line(p,x="Acquisition row",y=z),"profile")
        else:
            st.info("Map an elevation column to see the profile.")
    left,right = st.columns(2)
    with left, st.container(border=True):
        panel("03 / Feature distribution", "Top 20 categories, including missing values.")
        if category:
            counts = category_labels(view[category]).value_counts().head(20).rename_axis("Category").reset_index(name="Count")
            chart(px.bar(counts,x="Count",y="Category",orientation="h",color_discrete_sequence=COLORS),"distribution")
        else:
            st.info("Select a distribution category above.")
    with right, st.container(border=True):
        panel("04 / Completeness matrix", "Missing cells by row and column; first 300 filtered records.")
        if len(view):
            fig = go.Figure(go.Heatmap(z=view.head(300).isna().astype(int).to_numpy(),x=list(view.columns),
                                      y=np.arange(1,min(len(view),300)+1),zmin=0,zmax=1,
                                      colorscale=[[0,"#dce9df"],[1,"#c49c25"]],
                                      colorbar=dict(tickvals=[0,1],ticktext=["Present","Missing"])))
            fig.update_yaxes(title="Filtered row",autorange="reversed")
            chart(fig,"missing")
        else:
            st.info("No rows to display.")
    left,right = st.columns(2)
    with left, st.container(border=True):
        panel("05 / Correlation matrix", "Pearson correlation on pairwise valid observations.")
        corr_cols = st.multiselect("Correlation columns", nums, default=nums[:8],key="corr_cols")
        if len(corr_cols)>=2:
            corr = view[corr_cols].apply(numeric).corr(min_periods=3)
            chart(go.Figure(go.Heatmap(z=corr.values,x=corr.columns,y=corr.index,zmin=-1,zmax=1,
                                     colorscale="BrBG",hovertemplate="%{x} / %{y}: %{z:.3f}<extra></extra>")),"correlation")
            st.caption("Blank cells: constant columns or fewer than 3 paired observations. Correlation does not establish accuracy.")
        else:
            st.info("Select at least two numeric columns.")
    with right, st.container(border=True):
        panel("06 / Measurement histogram", "Frequency distribution across the selected measurement.")
        bins = st.slider("Histogram bins",5,80,25,key="bins")
        if measure:
            values = numeric(view[measure]).dropna()
            chart(px.histogram(x=values,nbins=bins,labels={"x":measure},color_discrete_sequence=COLORS),"histogram")
        else:
            st.info("No numeric measurements in this dataset.")
    left,right = st.columns(2)
    with left, st.container(border=True):
        panel("07 / Boundary enclosure", "Flagged vertices, grouped by parcel/part; ordered by the mapped sequence.")
        boundary = boundary_points(spatial,mapping)
        if len(boundary):
            group = mapping.get("group")
            groups = list(boundary.groupby(group,dropna=False)) if group else [("Boundary",boundary)]
            group_index = st.selectbox("Parcel / ring",range(len(groups)),format_func=lambda i:str(groups[i][0]),key="boundary_group")
            name,points = groups[group_index]
            order = mapping.get("order")
            if order:
                points = points.assign(_sort=numeric(points[order])).sort_values("_sort",kind="stable")
            else:
                st.caption("Using imported row order. Map Vertex order for a known boundary sequence.")
            coords = points[[x,y]].to_numpy(dtype=float)
            fig = go.Figure(go.Scatter(x=coords[:,0],y=coords[:,1],mode="lines+markers",name=str(name)))
            if len(coords)>=3 and not np.array_equal(coords[0],coords[-1]):
                fig.add_trace(go.Scatter(x=[coords[-1,0],coords[0,0]],y=[coords[-1,1],coords[0,1]],
                                        mode="lines",line=dict(dash="dash",color="#c49c25"),name="Display closure"))
            if not geographic:
                fig.update_yaxes(scaleanchor="x",scaleratio=1)
            chart(fig,"boundary")
            status,parcel_area = boundary_metrics(coords)
            st.caption(status + (f" · Ring area {parcel_area:,.2f} {units}²" if parcel_area is not None and not geographic else ""))
            st.caption("Display closure is not traverse misclosure. Each ring is shown separately; holes are not subtracted. No certified cadastral assessment.")
        else:
            st.info("Map a boundary flag (true/1/yes) and valid X/Y coordinates.")
    with right, st.container(border=True):
        panel("08 / Variance & tolerance", "Boxplot with 1.5×IQR whiskers; enter a project-specific acceptable range.")
        if measure:
            vals = numeric(view[measure]).dropna()
            fig = px.box(y=vals,points="outliers",labels={"y":measure},color_discrete_sequence=COLORS)
            if st.checkbox("Show tolerance limits",key="show_tolerance"):
                lo = st.number_input("Lower acceptable limit",value=0.0,key="tolerance_lo")
                hi = st.number_input("Upper acceptable limit",value=100.0,key="tolerance_hi")
                if lo>hi:
                    st.error("Lower limit must not exceed upper limit.")
                else:
                    fig.add_hrect(y0=lo,y1=hi,fillcolor="#d3b545",opacity=.15,line_width=0)
                    st.caption(f"{((vals<lo)|(vals>hi)).sum():,} of {len(vals):,} values outside limits.")
            chart(fig,"box")
            st.caption("Dispersion is not positional accuracy. Accuracy requires reference/control residuals; select that field when available.")
        else:
            st.info("Select a numeric measurement.")
    left,right = st.columns(2)
    with left, st.container(border=True):
        panel("09 / Acquisition progress", "Cumulative record count by timestamp or original sequence.")
        time = mapping.get("time")
        if time:
            dates = pd.to_datetime(view[time],errors="coerce",utc=True).dropna().sort_values()
            seq = pd.DataFrame({"Acquired":dates.to_numpy(),"Cumulative points":np.arange(1,len(dates)+1)})
            st.caption(f"{len(view)-len(dates):,} records without valid timestamps omitted.")
        else:
            seq = pd.DataFrame({"Acquired":np.arange(1,len(view)+1),"Cumulative points":np.arange(1,len(view)+1)})
        chart(px.area(seq,x="Acquired",y="Cumulative points",color_discrete_sequence=COLORS),"sequence")
    with right, st.container(border=True):
        panel("10 / 3D survey cloud", "Measured vertices only; rotate to inspect relief without interpolation.")
        if len(plot) and z and z not in (x,y) and plot[z].notna().any():
            chart(px.scatter_3d(plot.dropna(subset=[z]),x=x,y=y,z=z,color=z,color_continuous_scale="Viridis"),"cloud")
        else:
            st.info("Map distinct X, Y and Z columns with valid values.")
    with st.container(border=True):
        panel("11 / Column completeness", "Non-null coverage for every field in the filtered working dataset.")
        coverage = view.notna().mean().mul(100).rename_axis("Column").reset_index(name="Complete (%)")
        fig = px.bar(coverage,x="Column",y="Complete (%)",color_discrete_sequence=COLORS)
        fig.update_yaxes(range=[0,100])
        chart(fig,"coverage")
