"""
Phase 5 — Streamlit Dashboard
Run: streamlit run streamlit_app/app.py
Deploy: push to GitHub → connect to share.streamlit.io
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
import sys

# Add parent dir so we can import phases
sys.path.insert(0, str(Path(__file__).parent.parent))

st.set_page_config(
    page_title="D2C Analytics — Organic Incense",
    page_icon="🪔",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: #f8f9ff;
        border: 1px solid #e0e4f0;
        border-radius: 10px;
        padding: 16px 20px;
        text-align: center;
    }
    .metric-label { font-size: 12px; color: #666; margin-bottom: 4px; }
    .metric-value { font-size: 26px; font-weight: 600; color: #2c3e50; }
    .metric-delta { font-size: 12px; margin-top: 4px; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { padding: 8px 20px; border-radius: 8px; }
    h1 { color: #1a1a2e; }
    h2 { color: #16213e; }
    .block-container { padding-top: 1.5rem; }
    div[data-testid="stSidebarNav"] { display: none; }
</style>
""", unsafe_allow_html=True)

COLORS = {
    "D2C":    "#3266ad",
    "Amazon": "#e07b39",
    "total":  "#534AB7",
    "city":   "#1D9E75",
    "repeat": "#D85A30",
}

CLEAN   = Path(__file__).parent.parent / "data" / "clean"
RAW_DIR = Path(__file__).parent.parent / "data" / "raw"


# ── Data loading ────────────────────────────────────────────────────────────────
@st.cache_data
def load_orders():
    try:
        df = pd.read_csv(CLEAN / "master_orders.csv", parse_dates=["order_date"])
        return df
    except FileNotFoundError:
        return pd.DataFrame()

@st.cache_data
def load_lines():
    try:
        return pd.read_csv(CLEAN / "master_lines.csv")
    except FileNotFoundError:
        return pd.DataFrame()

@st.cache_data
def load_forecast():
    try:
        return pd.read_csv(CLEAN / "forecast.csv")
    except FileNotFoundError:
        return pd.DataFrame()

@st.cache_data
def load_segments():
    try:
        return pd.read_csv(CLEAN / "customer_segments.csv")
    except FileNotFoundError:
        return pd.DataFrame()


# ── Sidebar ─────────────────────────────────────────────────────────────────────
def sidebar(orders):
    st.sidebar.image("https://via.placeholder.com/200x60/534AB7/FFFFFF?text=D2C+Analytics",
                     use_container_width=True)
    st.sidebar.title("Filters")

    # File upload
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Upload new data**")
    uploaded = st.sidebar.file_uploader(
        "Shopify or Amazon export (.xlsx)",
        type=["xlsx", "csv"],
        accept_multiple_files=True,
        help="Drop your new monthly exports here — dashboard refreshes automatically"
    )
    if uploaded:
        for f in uploaded:
            save_path = RAW_DIR / f.name
            with open(save_path, "wb") as out:
                out.write(f.getbuffer())
        if st.sidebar.button("Process new files"):
            import subprocess
            subprocess.run(["python", "phase1_pipeline.py"], cwd=Path(__file__).parent.parent)
            subprocess.run(["python", "phase2_analysis.py"], cwd=Path(__file__).parent.parent)
            subprocess.run(["python", "phase4_forecast.py"], cwd=Path(__file__).parent.parent)
            st.cache_data.clear()
            st.rerun()

    st.sidebar.markdown("---")

    if orders.empty:
        return None, None, None

    # Channel filter
    channels = ["All"] + sorted(orders["channel"].unique().tolist())
    sel_channel = st.sidebar.selectbox("Channel", channels)

    # Date range
    min_date = orders["order_date"].min().date()
    max_date = orders["order_date"].max().date()
    date_range = st.sidebar.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    # City filter
    top_cities = orders["city"].value_counts().head(20).index.tolist()
    sel_cities = st.sidebar.multiselect("Cities (top 20)", top_cities,
                                         default=[], placeholder="All cities")

    return sel_channel, date_range, sel_cities


def filter_orders(orders, channel, date_range, cities):
    df = orders.copy()
    if channel != "All":
        df = df[df["channel"] == channel]
    if len(date_range) == 2:
        df = df[(df["order_date"].dt.date >= date_range[0]) &
                (df["order_date"].dt.date <= date_range[1])]
    if cities:
        df = df[df["city"].isin(cities)]
    return df


# ── KPI metrics ─────────────────────────────────────────────────────────────────
def show_kpis(df):
    total_rev  = df["order_total"].sum()
    total_ord  = len(df)
    aov        = total_rev / total_ord if total_ord else 0
    customers  = df["email"].nunique() if "email" in df.columns else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Revenue",  f"₹{total_rev:,.0f}")
    c2.metric("Total Orders",   f"{total_ord:,}")
    c3.metric("Avg Order Value",f"₹{aov:,.0f}")
    c4.metric("Unique Customers",f"{customers:,}")

    seg = load_segments()
    if not seg.empty and "order_count" in seg.columns:
        repeat = (seg["order_count"] > 1).mean() * 100
        c5.metric("Repeat Rate", f"{repeat:.1f}%")
    else:
        c5.metric("Repeat Rate", "—")


# ── Page: Overview ──────────────────────────────────────────────────────────────
def page_overview(df):
    st.header("Monthly Revenue Trend")

    if df.empty:
        st.warning("No data found. Upload your files in the sidebar.")
        return

    monthly = (df.groupby(["Month", "channel"])
               .agg(revenue=("order_total", "sum"), orders=("order_id", "count"))
               .reset_index())

    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=("Revenue by channel (₹)", "Order count"),
        vertical_spacing=0.15,
        row_heights=[0.6, 0.4]
    )

    for ch in monthly["channel"].unique():
        sub = monthly[monthly["channel"] == ch].sort_values("Month")
        fig.add_trace(
            go.Bar(name=ch, x=sub["Month"], y=sub["revenue"],
                   marker_color=COLORS.get(ch, "#888")),
            row=1, col=1
        )

    tot = df.groupby("Month")["order_total"].sum().reset_index()
    tot_ord = df.groupby("Month")["order_id"].count().reset_index()
    tot_ord.columns = ["Month", "orders"]
    fig.add_trace(
        go.Scatter(x=tot_ord["Month"], y=tot_ord["orders"], mode="lines+markers",
                   name="Orders", line=dict(color=COLORS["total"], width=2.5),
                   marker=dict(size=6)),
        row=2, col=1
    )

    fig.update_layout(barmode="stack", height=560, showlegend=True,
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(tickangle=45)
    fig.update_yaxes(tickprefix="₹", tickformat=",", row=1, col=1)
    st.plotly_chart(fig, use_container_width=True)

    # MoM table
    with st.expander("Monthly breakdown table"):
        pivot = (df.groupby(["Month", "channel"])["order_total"].sum()
                 .unstack(fill_value=0).reset_index())
        pivot["Total"] = pivot.iloc[:, 1:].sum(axis=1)
        pivot["MoM %"] = pivot["Total"].pct_change() * 100
        st.dataframe(pivot.style.format({
            c: "₹{:,.0f}" for c in pivot.columns if c not in ["Month", "MoM %"]
        } | {"MoM %": "{:+.1f}%"}), use_container_width=True)


# ── Page: City ──────────────────────────────────────────────────────────────────
def page_city(df):
    st.header("City & State Analysis")
    if df.empty:
        return

    col1, col2 = st.columns(2)

    city = (df.groupby("city")
            .agg(revenue=("order_total", "sum"), orders=("order_id", "count"))
            .sort_values("revenue", ascending=False)
            .reset_index().head(15))

    with col1:
        fig = px.bar(city, x="revenue", y="city", orientation="h",
                     title="Top 15 cities by revenue",
                     color_discrete_sequence=[COLORS["city"]])
        fig.update_layout(yaxis={"autorange": "reversed"},
                          xaxis_tickprefix="₹", xaxis_tickformat=",",
                          plot_bgcolor="rgba(0,0,0,0)", height=480)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig2 = px.bar(city, x="orders", y="city", orientation="h",
                      title="Top 15 cities by order count",
                      color_discrete_sequence=[COLORS["total"]])
        fig2.update_layout(yaxis={"autorange": "reversed"},
                           plot_bgcolor="rgba(0,0,0,0)", height=480)
        st.plotly_chart(fig2, use_container_width=True)

    # State level
    state = (df.groupby("state")
             .agg(revenue=("order_total", "sum"), orders=("order_id", "count"))
             .sort_values("revenue", ascending=False).reset_index())
    st.subheader("Revenue by state")
    fig3 = px.treemap(state.head(20), path=["state"], values="revenue",
                      color="revenue",
                      color_continuous_scale=["#E6F1FB", "#0C447C"])
    fig3.update_layout(height=380)
    st.plotly_chart(fig3, use_container_width=True)


# ── Page: Products ──────────────────────────────────────────────────────────────
def page_products(lines):
    st.header("Product Performance")
    if lines.empty:
        st.info("Load line-level data to see product breakdown.")
        return

    prod = (lines.groupby("product_name")
            .agg(revenue=("line_revenue", "sum"), units=("quantity", "sum"))
            .sort_values("revenue", ascending=False).reset_index())
    prod["avg_price"] = (prod["revenue"] / prod["units"]).round(0)
    prod["share"]     = (prod["revenue"] / prod["revenue"].sum() * 100).round(1)

    col1, col2 = st.columns([3, 2])

    with col1:
        top15 = prod.head(15).copy()
        top15["short_name"] = top15["product_name"].str.slice(0, 45)
        fig = px.bar(top15, x="revenue", y="short_name", orientation="h",
                     title="Top 15 products by revenue",
                     color="revenue",
                     color_continuous_scale=["#EEEDFE", "#3C3489"])
        fig.update_layout(yaxis={"autorange": "reversed"},
                          xaxis_tickprefix="₹", xaxis_tickformat=",",
                          plot_bgcolor="rgba(0,0,0,0)", height=520,
                          showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        top5_pie = prod.head(5)
        others   = pd.DataFrame([{"product_name": "Others",
                                   "revenue": prod.iloc[5:]["revenue"].sum()}])
        pie_data = pd.concat([top5_pie[["product_name", "revenue"]], others])
        fig2 = px.pie(pie_data, values="revenue", names="product_name",
                      title="Revenue share — top 5 + others",
                      color_discrete_sequence=px.colors.qualitative.Pastel)
        fig2.update_traces(textposition="inside", textinfo="percent+label")
        fig2.update_layout(height=380, showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

    # Monthly trend for top 5
    st.subheader("Monthly trend — top 5 products")
    top5_names = prod.head(5)["product_name"].tolist()
    top5_lines = lines[lines["product_name"].isin(top5_names)].copy()
    monthly_prod = (top5_lines.groupby(["Month", "product_name"])["line_revenue"]
                    .sum().reset_index())
    fig3 = px.line(monthly_prod, x="Month", y="line_revenue", color="product_name",
                   markers=True)
    fig3.update_layout(xaxis_tickangle=45, yaxis_tickprefix="₹", yaxis_tickformat=",",
                       plot_bgcolor="rgba(0,0,0,0)", height=360)
    st.plotly_chart(fig3, use_container_width=True)


# ── Page: Repeat Purchase ────────────────────────────────────────────────────────
def page_repeat(orders):
    st.header("Repeat Purchase & Customer Retention")

    d2c = orders[orders["channel"] == "D2C"].copy() if "channel" in orders.columns else orders.copy()
    d2c = d2c.dropna(subset=["email"])

    if d2c.empty:
        st.info("No D2C customer email data found.")
        return

    cust = (d2c.groupby("email")
            .agg(orders=("order_id", "count"), spend=("order_total", "sum"),
                 first=("order_date", "min"), last=("order_date", "max"))
            .reset_index())
    cust["days_between"] = (cust["last"] - cust["first"]).dt.days
    cust["segment"] = pd.cut(cust["orders"], bins=[0,1,2,5,9999],
                              labels=["One-time","Returning","Loyal","Champion"])

    col1, col2 = st.columns(2)

    with col1:
        seg_count = cust["segment"].value_counts().reset_index()
        seg_count.columns = ["segment", "count"]
        fig = px.pie(seg_count, values="count", names="segment",
                     title=f"Customer segments (total: {len(cust):,})",
                     color="segment",
                     color_discrete_map={
                         "One-time": "#3266ad", "Returning": "#e07b39",
                         "Loyal": "#2a9d6f", "Champion": "#534AB7"
                     },
                     hole=0.45)
        fig.update_layout(height=360)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        repeat = cust[cust["orders"] > 1]
        if len(repeat) > 0:
            fig2 = px.histogram(repeat, x="days_between", nbins=20,
                                title="Days between first and last order (repeat buyers)",
                                color_discrete_sequence=[COLORS["repeat"]])
            fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)", height=360,
                               xaxis_title="Days", yaxis_title="Customers")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Not enough repeat buyers yet to plot distribution.")

    # Cohort analysis
    st.subheader("Monthly cohort retention")
    d2c["cohort"] = d2c.groupby("email")["order_date"].transform("min").dt.to_period("M").astype(str)
    d2c["order_month"] = d2c["order_date"].dt.to_period("M").astype(str)
    cohort_size = d2c.groupby("cohort")["email"].nunique()
    cohort_data = (d2c.groupby(["cohort", "order_month"])["email"].nunique()
                   .div(cohort_size, level="cohort") * 100).round(1).reset_index()
    cohort_data.columns = ["cohort", "month", "retention"]
    cohort_pivot = cohort_data.pivot_table(index="cohort", columns="month",
                                            values="retention").fillna(0)

    fig3 = px.imshow(cohort_pivot, text_auto=".0f",
                     color_continuous_scale=["#f8f9ff", "#3266ad"],
                     aspect="auto",
                     labels={"color": "Retention %"},
                     title="Cohort retention heatmap (%)")
    fig3.update_layout(height=max(250, len(cohort_pivot) * 40 + 100))
    st.plotly_chart(fig3, use_container_width=True)

    # Segment LTV table
    st.subheader("LTV by segment")
    ltv = (cust.groupby("segment")
           .agg(customers=("email", "count"),
                avg_orders=("orders", "mean"),
                avg_ltv=("spend", "mean"),
                avg_aov=("spend", lambda x: x.mean() / cust.loc[x.index, "orders"].mean()))
           .reset_index())
    ltv["avg_orders"] = ltv["avg_orders"].round(1)
    ltv["avg_ltv"]    = ltv["avg_ltv"].round(0)
    st.dataframe(ltv, use_container_width=True)


# ── Page: Forecast ───────────────────────────────────────────────────────────────
def page_forecast(orders):
    st.header("Sales Forecast")

    monthly = orders.groupby("Month")["order_total"].sum().reset_index()
    monthly.columns = ["Month", "actual"]
    monthly = monthly.sort_values("Month")

    fc = load_forecast()

    col1, col2 = st.columns([3, 1])

    with col1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=monthly["Month"], y=monthly["actual"],
            mode="lines+markers", name="Actual",
            line=dict(color=COLORS["D2C"], width=2.5),
            marker=dict(size=6)
        ))

        if not fc.empty:
            fig.add_trace(go.Scatter(
                x=fc["Month"], y=fc["holt_forecast"],
                mode="lines+markers", name="Forecast (Holt's)",
                line=dict(color=COLORS["Amazon"], width=2.5, dash="dash"),
                marker=dict(size=7, symbol="diamond")
            ))

            if "prophet_yhat" in fc.columns:
                fig.add_trace(go.Scatter(
                    x=fc["Month"], y=fc["prophet_yhat"],
                    mode="lines+markers", name="Prophet forecast",
                    line=dict(color=COLORS["city"], width=1.8),
                    marker=dict(size=5)
                ))
                x_fill = list(fc["Month"]) + list(fc["Month"])[::-1]
                y_fill = list(fc["prophet_upper"]) + list(fc["prophet_lower"])[::-1]
                fig.add_trace(go.Scatter(
                    x=x_fill, y=y_fill, fill="toself",
                    fillcolor="rgba(29,158,117,0.12)", line=dict(color="rgba(0,0,0,0)"),
                    name="Prophet 80% CI", showlegend=True
                ))

            # Add vertical divider line
            last_actual = monthly["Month"].iloc[-1]
            fig.add_vline(x=last_actual, line_dash="dot", line_color="#888",
                          annotation_text="  Forecast start", annotation_position="top right")

        fig.update_layout(
            xaxis_tickangle=45,
            yaxis_tickprefix="₹", yaxis_tickformat=",",
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            height=420, legend=dict(orientation="h", y=1.1),
            title="Revenue forecast — actual vs predicted"
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        if not fc.empty:
            st.subheader("Forecast")
            for _, row in fc.iterrows():
                st.metric(row["Month"], f"₹{int(row['holt_forecast']):,}")
        else:
            st.info("Run phase4_forecast.py to generate forecasts.")

    # Model info
    if not fc.empty:
        with st.expander("Model details"):
            st.markdown("""
**Holt's double exponential smoothing**
- Captures level + trend in the data
- Parameters (α, β) optimised via grid search to minimise RMSE
- Best for: short series, clear trends, no strong seasonality

**Prophet** (if installed)
- Handles changepoints, holiday effects, seasonality automatically
- Provides confidence intervals
- Best for: 18+ months of data, festival-driven spikes (Diwali, Navratri)

**Improving accuracy over time**
- More months = tighter confidence intervals
- Add Indian festival dates as Prophet regressors for better seasonal fit
- Consider separating D2C and Amazon forecasts once each has 12+ months
            """)
            st.dataframe(fc, use_container_width=True)


# ── Main ─────────────────────────────────────────────────────────────────────────
def main():
    orders = load_orders()
    lines  = load_lines()

    channel, date_range, cities = sidebar(orders)

    if orders.empty:
        st.title("🪔 D2C Analytics Dashboard")
        st.warning("""
**No data loaded yet.**

1. Place your files in `data/raw/`:
   - Shopify orders export: `orders_export_*.xlsx`
   - Amazon MTR report: `Amazon_report_*.xlsx`
2. Run the pipeline:
   ```
   python phase1_pipeline.py
   python phase2_analysis.py
   python phase4_forecast.py
   ```
3. Refresh this page.

Or use the sidebar file uploader to upload and process files directly.
        """)
        return

    filtered = filter_orders(orders, channel, date_range, cities)

    st.title("🪔 D2C Organic Incense — Analytics Dashboard")
    st.caption(f"Showing {len(filtered):,} orders · {channel} channel · "
               f"{date_range[0] if len(date_range)==2 else ''} to "
               f"{date_range[1] if len(date_range)==2 else ''}")

    show_kpis(filtered)
    st.markdown("---")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Monthly trends", "City breakdown", "Products", "Repeat purchase", "Forecast"
    ])

    with tab1:
        page_overview(filtered)
    with tab2:
        page_city(filtered)
    with tab3:
        page_products(lines)
    with tab4:
        page_repeat(filtered)
    with tab5:
        page_forecast(orders)


if __name__ == "__main__":
    main()
