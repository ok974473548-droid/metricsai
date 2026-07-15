import reflex as rx
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder
import json
from datetime import datetime, timedelta
from openai import OpenAI
import sqlite3
import hashlib

# ==================== STYLES ====================
DARK_BG = "#0B0F19"
CARD_BG = "rgba(255, 255, 255, 0.02)"
BORDER = "rgba(255, 255, 255, 0.06)"
TEXT_PRIMARY = "#F8FAFC"
TEXT_SECONDARY = "#94A3B8"
TEXT_MUTED = "#64748B"
ACCENT_POSITIVE = "#34D399"
ACCENT_NEGATIVE = "#F87171"
ACCENT_WARNING = "#FBBF24"

base_style = {
    "font_family": "Inter, system-ui, sans-serif",
    "background_color": DARK_BG,
    "color": TEXT_PRIMARY,
}

def glass_card():
    return {
        "background": CARD_BG,
        "backdrop_filter": "blur(20px)",
        "border": f"1px solid {BORDER}",
        "border_radius": "16px",
        "padding": "1.5rem",
        "box_shadow": "0 4px 24px rgba(0, 0, 0, 0.2)",
        "transition": "all 0.3s ease",
        "_hover": {"border_color": "rgba(255,255,255,0.12)"},
    }

def metric_card():
    return {
        "background": CARD_BG,
        "backdrop_filter": "blur(20px)",
        "border": f"1px solid {BORDER}",
        "border_radius": "16px",
        "padding": "1.25rem",
        "transition": "all 0.3s ease",
        "_hover": {"border_color": "rgba(255,255,255,0.12)", "background": "rgba(255,255,255,0.04)"},
    }

def btn_primary():
    return {
        "background": TEXT_PRIMARY,
        "color": DARK_BG,
        "border_radius": "10px",
        "padding": "0.6rem 1.5rem",
        "font_weight": "600",
        "font_size": "0.85rem",
        "_hover": {"transform": "translateY(-1px)", "box_shadow": "0 4px 16px rgba(248, 250, 252, 0.2)"},
    }

def btn_secondary():
    return {
        "background": "rgba(255,255,255,0.06)",
        "color": TEXT_PRIMARY,
        "border": f"1px solid {BORDER}",
        "border_radius": "10px",
        "padding": "0.6rem 1.5rem",
        "font_weight": "600",
        "font_size": "0.85rem",
        "_hover": {"background": "rgba(255,255,255,0.1)"},
    }

# ==================== DB ====================
def init_db():
    conn = sqlite3.connect("metricsai.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS shared_dashboards (id TEXT PRIMARY KEY, created_at TEXT, data_json TEXT, white_label TEXT)")
    conn.commit()
    conn.close()

init_db()

def save_shared_dashboard(dashboard_id, data_json, white_label):
    conn = sqlite3.connect("metricsai.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO shared_dashboards (id, created_at, data_json, white_label) VALUES (?, ?, ?, ?)",
              (dashboard_id, datetime.now().isoformat(), data_json, white_label))
    conn.commit()
    conn.close()

def load_shared_dashboard(dashboard_id):
    conn = sqlite3.connect("metricsai.db")
    c = conn.cursor()
    c.execute("SELECT data_json, white_label FROM shared_dashboards WHERE id = ?", (dashboard_id,))
    row = c.fetchone()
    conn.close()
    return row if row else (None, None)

# ==================== DATA UTILS ====================
def generate_sample_data():
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", "2025-06-30", freq="D")
    n = len(dates)
    users = [f"user_{i:04d}" for i in range(500)]
    channels = ["organic", "instagram", "google", "facebook", "email", "tiktok", "referral"]
    events = ["impression", "click", "visit", "add_to_cart", "purchase"]
    df = pd.DataFrame({
        "date": np.random.choice(dates, n),
        "user_id": np.random.choice(users, n),
        "revenue": np.where(np.random.random(n) > 0.7, np.random.exponential(200, n).round(2), 0),
        "channel": np.random.choice(channels, n, p=[0.25, 0.15, 0.20, 0.15, 0.10, 0.10, 0.05]),
        "event_type": np.random.choice(events, n, p=[0.35, 0.20, 0.20, 0.10, 0.15]),
        "marketing_cost": np.random.choice([0, 0, 0, 30, 50, 80, 120, 200], n),
    })
    return df.sort_values("date").reset_index(drop=True)

def df_to_records(df):
    return df.to_dict("records")

def records_to_df(records):
    return pd.DataFrame(records)

def calculate_metrics(df):
    metrics = {}
    metrics["total_users"] = int(df["user_id"].nunique()) if "user_id" in df.columns else len(df)
    metrics["total_revenue"] = float(df["revenue"].sum()) if "revenue" in df.columns else 0.0
    metrics["total_orders"] = int(len(df[df["revenue"] > 0])) if "revenue" in df.columns else len(df)
    metrics["arpu"] = metrics["total_revenue"] / metrics["total_users"] if metrics["total_users"] > 0 else 0.0
    metrics["aov"] = metrics["total_revenue"] / metrics["total_orders"] if metrics["total_orders"] > 0 else 0.0
    if "channel" in df.columns and "marketing_cost" in df.columns:
        channel_stats = df.groupby("channel").agg({"user_id": "nunique", "marketing_cost": "sum"}).reset_index()
        channel_stats["cac"] = channel_stats["marketing_cost"] / channel_stats["user_id"]
        metrics["cac_by_channel"] = channel_stats.to_dict("records")
        metrics["avg_cac"] = float(channel_stats["cac"].mean())
    else:
        metrics["avg_cac"] = 0.0
        metrics["cac_by_channel"] = []
    if "date" in df.columns and "user_id" in df.columns and "revenue" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        user_revenue = df.groupby("user_id")["revenue"].sum()
        metrics["ltv"] = float(user_revenue.mean() * 2.0)
    else:
        metrics["ltv"] = metrics["arpu"] * 3.0
    metrics["ltv_cac_ratio"] = metrics["ltv"] / metrics["avg_cac"] if metrics["avg_cac"] > 0 else 0.0
    if "date" in df.columns:
        df["month"] = df["date"].dt.to_period("M").astype(str)
        monthly = df.groupby("month").agg({"revenue": "sum", "user_id": "nunique"}).reset_index()
        monthly["arpu"] = monthly["revenue"] / monthly["user_id"]
        metrics["monthly_trend"] = monthly.to_dict("records")
    else:
        metrics["monthly_trend"] = []
    if "event_type" in df.columns:
        funnel_order = ["impression", "click", "visit", "add_to_cart", "purchase", "order"]
        funnel_counts = df["event_type"].value_counts().to_dict()
        funnel_data = []
        for step in funnel_order:
            if step in funnel_counts:
                funnel_data.append({"step": step.upper(), "users": int(funnel_counts[step])})
        if not funnel_data:
            for k, v in funnel_counts.items():
                funnel_data.append({"step": k.upper(), "users": int(v)})
        metrics["funnel"] = funnel_data
    else:
        metrics["funnel"] = []
    return metrics

def plotly_to_json(fig):
    return json.loads(json.dumps(fig, cls=PlotlyJSONEncoder))

# ==================== STATE ====================
class State(rx.State):
    # Data
    data_records: list = []
    has_data: bool = False

    # White-label
    company_name: str = "MetricsAI"
    logo_text: str = "MetricsAI"

    # Metrics
    metrics: dict = {}

    # Charts
    revenue_chart: dict = {}
    arpu_chart: dict = {}
    funnel_chart: dict = {}
    channel_chart: dict = {}

    # Share
    share_url: str = ""
    is_public: bool = False

    # AI
    ai_insights: str = ""
    ai_loading: bool = False

    # Navigation
    current_page: str = "dashboard"

    def load_sample_data(self):
        df = generate_sample_data()
        self.data_records = df_to_records(df)
        self.has_data = True
        self._recalculate_all()

    def _recalculate_all(self):
        if not self.has_data:
            return
        df = records_to_df(self.data_records)
        self.metrics = calculate_metrics(df)
        self._build_charts(df)

    def _build_charts(self, df):
        # Revenue trend
        if self.metrics.get("monthly_trend"):
            monthly_df = pd.DataFrame(self.metrics["monthly_trend"])
            fig = px.line(monthly_df, x="month", y="revenue", template="plotly_dark")
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color=TEXT_SECONDARY, margin=dict(l=20, r=20, t=40, b=20),
                showlegend=False
            )
            fig.update_traces(line_color="#F8FAFC")
            self.revenue_chart = plotly_to_json(fig)

        # ARPU
        if self.metrics.get("monthly_trend"):
            monthly_df = pd.DataFrame(self.metrics["monthly_trend"])
            fig = px.bar(monthly_df, x="month", y="arpu", template="plotly_dark")
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color=TEXT_SECONDARY, margin=dict(l=20, r=20, t=40, b=20),
                showlegend=False
            )
            fig.update_traces(marker_color="#94A3B8")
            self.arpu_chart = plotly_to_json(fig)

        # Funnel
        if self.metrics.get("funnel"):
            funnel_df = pd.DataFrame(self.metrics["funnel"])
            fig = px.funnel(funnel_df, x="users", y="step", template="plotly_dark")
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color=TEXT_SECONDARY, margin=dict(l=20, r=20, t=20, b=20),
                showlegend=False
            )
            fig.update_traces(marker_color=["#F8FAFC", "#CBD5E1", "#94A3B8", "#64748B", "#475569"])
            self.funnel_chart = plotly_to_json(fig)

        # Channel revenue
        if "channel" in df.columns:
            channel_df = df.groupby("channel")["revenue"].sum().reset_index().sort_values("revenue", ascending=True)
            fig = px.bar(channel_df, x="revenue", y="channel", orientation="h", template="plotly_dark")
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color=TEXT_SECONDARY, margin=dict(l=20, r=20, t=20, b=20),
                showlegend=False
            )
            fig.update_traces(marker_color="#F8FAFC")
            self.channel_chart = plotly_to_json(fig)

    def share_dashboard(self):
        if not self.has_data:
            return
        dashboard_id = hashlib.sha256(str(datetime.now().timestamp()).encode()).hexdigest()[:12]
        data_json = json.dumps(self.data_records)
        white_label = json.dumps({"company_name": self.company_name, "logo_text": self.logo_text})
        save_shared_dashboard(dashboard_id, data_json, white_label)
        self.share_url = f"/dashboard/{dashboard_id}"

    def generate_ai_insights(self):
        if not self.has_data:
            return
        self.ai_loading = True
        self.ai_insights = "⏳ Анализирую метрики..."

        # Note: In production, use async background task
        # For demo, we simulate
        m = self.metrics
        prompt = f"""Users: {m.get('total_users')}
Revenue: {m.get('total_revenue'):,.2f}
ARPU: {m.get('arpu'):,.2f}
LTV: {m.get('ltv'):,.2f}
LTV/CAC: {m.get('ltv_cac_ratio'):.2f}

Дай 3-4 кратких практических инсайта на русском."""

        try:
            # Try to use OpenAI if key available
            client = OpenAI(api_key=self._get_openai_key())
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Ты — senior product analyst. Дай краткие практические инсайты."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=600
            )
            self.ai_insights = response.choices[0].message.content
        except Exception:
            # Fallback demo insights
            self.ai_insights = """🧠 AI Product Analyst

1. **LTV/CAC ratio ({ltv_cac:.1f}x)** — {ltv_status}. При healthy ratio > 3x можно масштабировать маркетинг.

2. **ARPU {arpu:,.0f} ₽** — анализируйте ARPU по каналам. Возможно, некоторые каналы приносят пользователей с низкой монетизацией.

3. **Выручка {revenue:,.0f} ₽** — отслеживайте динамику ежемесячно. Рекомендуем настроить alerts на падение > 15%.

4. **Сегментация** — проведите RFM-анализ для персонализации маркетинговых кампаний.""".format(
                ltv_cac=m.get("ltv_cac_ratio", 0),
                ltv_status="ниже нормы" if m.get("ltv_cac_ratio", 0) < 3 else "в норме",
                arpu=m.get("arpu", 0),
                revenue=m.get("total_revenue", 0)
            )
        self.ai_loading = False

    def _get_openai_key(self):
        # In Reflex, you can use environment variables or secrets
        import os
        return os.environ.get("OPENAI_API_KEY", "")

    def set_page(self, page: str):
        self.current_page = page

    def handle_upload(self, files: list):
        if not files:
            return
        # Reflex file upload returns bytes
        # For demo, we load sample data instead
        self.load_sample_data()

# ==================== COMPONENTS ====================
def sidebar() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(State.logo_text, font_size="1.4rem", font_weight="800", color=TEXT_PRIMARY, letter_spacing="-0.03em"),
            rx.divider(border_color=BORDER, margin_y="1rem"),
            rx.vstack(
                rx.button("📊 Дашборд", on_click=State.set_page("dashboard"), width="100%", style=btn_secondary() if State.current_page != "dashboard" else btn_primary()),
                rx.button("📥 Источники", on_click=State.set_page("sources"), width="100%", style=btn_secondary() if State.current_page != "sources" else btn_primary()),
                rx.button("📈 Тренды", on_click=State.set_page("trends"), width="100%", style=btn_secondary() if State.current_page != "trends" else btn_primary()),
                rx.button("🔻 Воронка", on_click=State.set_page("funnel"), width="100%", style=btn_secondary() if State.current_page != "funnel" else btn_primary()),
                rx.button("🎯 RFM", on_click=State.set_page("rfm"), width="100%", style=btn_secondary() if State.current_page != "rfm" else btn_primary()),
                rx.button("⚖️ A/B", on_click=State.set_page("ab"), width="100%", style=btn_secondary() if State.current_page != "ab" else btn_primary()),
                rx.button("🤖 AI", on_click=State.set_page("ai"), width="100%", style=btn_secondary() if State.current_page != "ai" else btn_primary()),
                rx.button("📄 Экспорт", on_click=State.set_page("export"), width="100%", style=btn_secondary() if State.current_page != "export" else btn_primary()),
                spacing="2",
                width="100%",
                align="stretch",
            ),
            rx.spacer(),
            rx.text("MetricsAI v2.0 on Reflex", font_size="0.7rem", color=TEXT_MUTED),
            spacing="4",
            align="stretch",
            height="100vh",
            padding="1.5rem",
            width="240px",
        ),
        background="linear-gradient(180deg, #0B0F19 0%, #111827 100%)",
        border_right=f"1px solid {BORDER}",
        position="fixed",
        left="0",
        top="0",
        height="100vh",
        z_index="100",
    )

def metric_box(label: str, value: str, delta: str = "", delta_positive: bool = True) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(label, font_size="0.75rem", color=TEXT_MUTED, font_weight="500", text_transform="uppercase", letter_spacing="0.08em"),
            rx.text(value, font_size="1.8rem", font_weight="700", color=TEXT_PRIMARY, letter_spacing="-0.02em"),
            rx.cond(
                delta != "",
                rx.text(delta, font_size="0.8rem", font_weight="600", color=rx.cond(delta_positive, ACCENT_POSITIVE, ACCENT_NEGATIVE)),
                rx.text(""),
            ),
            spacing="1",
            align="start",
        ),
        **metric_card(),
    )

def page_dashboard() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("Дашборд", font_size="2.2rem", font_weight="800", color=TEXT_PRIMARY, letter_spacing="-0.03em"),
            rx.text("Ключевые метрики в реальном времени", font_size="0.95rem", color=TEXT_MUTED),
            rx.divider(border_color=BORDER, margin_y="1.5rem"),

            # Share button
            rx.cond(
                State.has_data,
                rx.hstack(
                    rx.button("🔗 Поделиться дашбордом", on_click=State.share_dashboard, style=btn_primary()),
                    rx.cond(
                        State.share_url != "",
                        rx.hstack(
                            rx.input(value=State.share_url, is_read_only=True, width="300px", background="rgba(255,255,255,0.03)", border=f"1px solid {BORDER}", color=TEXT_PRIMARY, font_family="monospace", font_size="0.8rem"),
                            rx.button("📋 Копировать", on_click=rx.set_clipboard(State.share_url), style=btn_secondary()),
                            spacing="2",
                        ),
                        rx.text(""),
                    ),
                    spacing="4",
                    margin_bottom="1rem",
                ),
                rx.text(""),
            ),

            # Metrics
            rx.cond(
                State.has_data,
                rx.grid(
                    metric_box("Выручка", f"{State.metrics.get('total_revenue', 0):,.0f} ₽"),
                    metric_box("Пользователей", f"{State.metrics.get('total_users', 0):,}"),
                    metric_box("ARPU", f"{State.metrics.get('arpu', 0):,.0f} ₽"),
                    metric_box("AOV", f"{State.metrics.get('aov', 0):,.0f} ₽"),
                    metric_box("LTV (est.)", f"{State.metrics.get('ltv', 0):,.0f} ₽"),
                    metric_box("LTV / CAC", f"{State.metrics.get('ltv_cac_ratio', 0):.1f}x"),
                    columns="6",
                    spacing="4",
                    width="100%",
                ),
                rx.center(
                    rx.vstack(
                        rx.text("Нет данных", font_size="1.2rem", color=TEXT_SECONDARY),
                        rx.button("🎲 Загрузить демо-данные", on_click=State.load_sample_data, style=btn_primary()),
                        spacing="4",
                        padding="4rem",
                    ),
                    width="100%",
                ),
            ),

            # Charts
            rx.cond(
                State.has_data,
                rx.vstack(
                    rx.grid(
                        rx.box(
                            rx.text("📈 Динамика выручки", font_size="1.1rem", font_weight="700", color=TEXT_PRIMARY, margin_bottom="1rem"),
                            rx.cond(
                                State.revenue_chart,
                                rx.plotly(data=State.revenue_chart, layout={"autosize": True}, width="100%", height="300px"),
                                rx.text("Нет данных", color=TEXT_MUTED),
                            ),
                            **glass_card(),
                        ),
                        rx.box(
                            rx.text("🎯 ARPU по месяцам", font_size="1.1rem", font_weight="700", color=TEXT_PRIMARY, margin_bottom="1rem"),
                            rx.cond(
                                State.arpu_chart,
                                rx.plotly(data=State.arpu_chart, layout={"autosize": True}, width="100%", height="300px"),
                                rx.text("Нет данных", color=TEXT_MUTED),
                            ),
                            **glass_card(),
                        ),
                        columns="2",
                        spacing="4",
                        width="100%",
                        margin_top="1.5rem",
                    ),
                    rx.box(
                        rx.text("🎯 Выручка по каналам", font_size="1.1rem", font_weight="700", color=TEXT_PRIMARY, margin_bottom="1rem"),
                        rx.cond(
                            State.channel_chart,
                            rx.plotly(data=State.channel_chart, layout={"autosize": True}, width="100%", height="300px"),
                            rx.text("Нет данных", color=TEXT_MUTED),
                        ),
                        **glass_card(),
                        width="100%",
                        margin_top="1.5rem",
                    ),
                    spacing="0",
                    width="100%",
                ),
                rx.text(""),
            ),
            spacing="0",
            width="100%",
            padding="2rem",
        ),
        margin_left="240px",
        min_height="100vh",
        background=DARK_BG,
    )

def page_sources() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("Источники данных", font_size="2.2rem", font_weight="800", color=TEXT_PRIMARY, letter_spacing="-0.03em"),
            rx.text("Загрузите данные из любого источника", font_size="0.95rem", color=TEXT_MUTED),
            rx.divider(border_color=BORDER, margin_y="1.5rem"),
            rx.box(
                rx.vstack(
                    rx.text("📁 CSV / Excel", font_size="1.1rem", font_weight="700", color=TEXT_PRIMARY),
                    rx.text("Загрузка файла (в demo-режиме загружаются демо-данные)", font_size="0.85rem", color=TEXT_MUTED),
                    rx.button("🎲 Загрузить демо-данные", on_click=State.load_sample_data, style=btn_primary()),
                    rx.cond(
                        State.has_data,
                        rx.text(f"✅ Загружено записей", font_size="0.9rem", color=ACCENT_POSITIVE),
                        rx.text(""),
                    ),
                    spacing="4",
                    align="start",
                ),
                **glass_card(),
                width="100%",
            ),
            rx.box(
                rx.vstack(
                    rx.text("🔗 Google Sheets", font_size="1.1rem", font_weight="700", color=TEXT_PRIMARY),
                    rx.input(placeholder="URL Google Sheets (public)", width="100%", background="rgba(255,255,255,0.03)", border=f"1px solid {BORDER}", color=TEXT_PRIMARY),
                    rx.button("Загрузить", on_click=State.load_sample_data, style=btn_secondary()),
                    spacing="3",
                    align="start",
                ),
                **glass_card(),
                width="100%",
                margin_top="1rem",
            ),
            spacing="0",
            width="100%",
            padding="2rem",
        ),
        margin_left="240px",
        min_height="100vh",
        background=DARK_BG,
    )

def page_funnel() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("Воронка конверсии", font_size="2.2rem", font_weight="800", color=TEXT_PRIMARY, letter_spacing="-0.03em"),
            rx.divider(border_color=BORDER, margin_y="1.5rem"),
            rx.cond(
                State.has_data,
                rx.box(
                    rx.cond(
                        State.funnel_chart,
                        rx.plotly(data=State.funnel_chart, layout={"autosize": True}, width="100%", height="400px"),
                        rx.text("Нет данных для воронки", color=TEXT_MUTED),
                    ),
                    **glass_card(),
                    width="100%",
                ),
                rx.center(
                    rx.button("🎲 Загрузить демо-данные", on_click=State.load_sample_data, style=btn_primary()),
                    padding="4rem",
                ),
            ),
            spacing="0",
            width="100%",
            padding="2rem",
        ),
        margin_left="240px",
        min_height="100vh",
        background=DARK_BG,
    )

def page_ai() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("AI-инсайты", font_size="2.2rem", font_weight="800", color=TEXT_PRIMARY, letter_spacing="-0.03em"),
            rx.text("Искусственный интеллект анализирует ваши метрики", font_size="0.95rem", color=TEXT_MUTED),
            rx.divider(border_color=BORDER, margin_y="1.5rem"),
            rx.cond(
                State.has_data,
                rx.vstack(
                    rx.button("✨ Сгенерировать инсайты", on_click=State.generate_ai_insights, style=btn_primary()),
                    rx.cond(
                        State.ai_insights != "",
                        rx.box(
                            rx.markdown(State.ai_insights, color=TEXT_SECONDARY, line_height="1.7"),
                            background="rgba(255,255,255,0.02)",
                            border_left="3px solid #F8FAFC",
                            border_radius="0 12px 12px 0",
                            padding="1.25rem",
                            margin_top="1rem",
                            width="100%",
                        ),
                        rx.text(""),
                    ),
                    spacing="4",
                    width="100%",
                ),
                rx.center(
                    rx.button("🎲 Загрузить демо-данные", on_click=State.load_sample_data, style=btn_primary()),
                    padding="4rem",
                ),
            ),
            spacing="0",
            width="100%",
            padding="2rem",
        ),
        margin_left="240px",
        min_height="100vh",
        background=DARK_BG,
    )

def page_trends() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("Тренды и сравнение", font_size="2.2rem", font_weight="800", color=TEXT_PRIMARY, letter_spacing="-0.03em"),
            rx.text("Сравнение периодов и прогнозирование", font_size="0.95rem", color=TEXT_MUTED),
            rx.divider(border_color=BORDER, margin_y="1.5rem"),
            rx.cond(
                State.has_data,
                rx.box(
                    rx.text("Прогнозирование и сравнение периодов будет здесь", color=TEXT_SECONDARY),
                    **glass_card(),
                    width="100%",
                ),
                rx.center(
                    rx.button("🎲 Загрузить демо-данные", on_click=State.load_sample_data, style=btn_primary()),
                    padding="4rem",
                ),
            ),
            spacing="0",
            width="100%",
            padding="2rem",
        ),
        margin_left="240px",
        min_height="100vh",
        background=DARK_BG,
    )

def page_rfm() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("RFM-анализ", font_size="2.2rem", font_weight="800", color=TEXT_PRIMARY, letter_spacing="-0.03em"),
            rx.text("Сегментация клиентов", font_size="0.95rem", color=TEXT_MUTED),
            rx.divider(border_color=BORDER, margin_y="1.5rem"),
            rx.cond(
                State.has_data,
                rx.box(
                    rx.text("RFM-анализ будет здесь", color=TEXT_SECONDARY),
                    **glass_card(),
                    width="100%",
                ),
                rx.center(
                    rx.button("🎲 Загрузить демо-данные", on_click=State.load_sample_data, style=btn_primary()),
                    padding="4rem",
                ),
            ),
            spacing="0",
            width="100%",
            padding="2rem",
        ),
        margin_left="240px",
        min_height="100vh",
        background=DARK_BG,
    )

def page_ab() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("A/B калькулятор", font_size="2.2rem", font_weight="800", color=TEXT_PRIMARY, letter_spacing="-0.03em"),
            rx.text("Статистическая значимость", font_size="0.95rem", color=TEXT_MUTED),
            rx.divider(border_color=BORDER, margin_y="1.5rem"),
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.vstack(
                            rx.text("Вариант A", font_size="1.1rem", font_weight="700", color=TEXT_PRIMARY),
                            rx.input(placeholder="Конверсии A", type_="number", default_value="120", background="rgba(255,255,255,0.03)", border=f"1px solid {BORDER}", color=TEXT_PRIMARY),
                            rx.input(placeholder="Посетители A", type_="number", default_value="1000", background="rgba(255,255,255,0.03)", border=f"1px solid {BORDER}", color=TEXT_PRIMARY),
                            spacing="3",
                            align="start",
                        ),
                        rx.vstack(
                            rx.text("Вариант B", font_size="1.1rem", font_weight="700", color=TEXT_PRIMARY),
                            rx.input(placeholder="Конверсии B", type_="number", default_value="150", background="rgba(255,255,255,0.03)", border=f"1px solid {BORDER}", color=TEXT_PRIMARY),
                            rx.input(placeholder="Посетители B", type_="number", default_value="1000", background="rgba(255,255,255,0.03)", border=f"1px solid {BORDER}", color=TEXT_PRIMARY),
                            spacing="3",
                            align="start",
                        ),
                        spacing="8",
                        width="100%",
                    ),
                    rx.button("🚀 Рассчитать", style=btn_primary()),
                    spacing="4",
                    align="start",
                    width="100%",
                ),
                **glass_card(),
                width="100%",
            ),
            spacing="0",
            width="100%",
            padding="2rem",
        ),
        margin_left="240px",
        min_height="100vh",
        background=DARK_BG,
    )

def page_export() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("Экспорт", font_size="2.2rem", font_weight="800", color=TEXT_PRIMARY, letter_spacing="-0.03em"),
            rx.text("Скачайте данные в любом формате", font_size="0.95rem", color=TEXT_MUTED),
            rx.divider(border_color=BORDER, margin_y="1.5rem"),
            rx.cond(
                State.has_data,
                rx.hstack(
                    rx.button("⬇️ CSV", style=btn_secondary()),
                    rx.button("⬇️ Excel", style=btn_secondary()),
                    rx.button("⬇️ JSON", style=btn_secondary()),
                    rx.button("🖨️ PDF", style=btn_secondary()),
                    spacing="4",
                ),
                rx.center(
                    rx.button("🎲 Загрузить демо-данные", on_click=State.load_sample_data, style=btn_primary()),
                    padding="4rem",
                ),
            ),
            spacing="0",
            width="100%",
            padding="2rem",
        ),
        margin_left="240px",
        min_height="100vh",
        background=DARK_BG,
    )

def page_public_dashboard() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(State.logo_text, font_size="1.4rem", font_weight="800", color=TEXT_PRIMARY),
                rx.badge("Public", color_scheme="green", variant="subtle"),
                spacing="4",
            ),
            rx.text("Дашборд", font_size="2.2rem", font_weight="800", color=TEXT_PRIMARY, letter_spacing="-0.03em", margin_top="1rem"),
            rx.divider(border_color=BORDER, margin_y="1.5rem"),
            rx.cond(
                State.has_data,
                rx.grid(
                    metric_box("Выручка", f"{State.metrics.get('total_revenue', 0):,.0f} ₽"),
                    metric_box("Пользователей", f"{State.metrics.get('total_users', 0):,}"),
                    metric_box("ARPU", f"{State.metrics.get('arpu', 0):,.0f} ₽"),
                    metric_box("AOV", f"{State.metrics.get('aov', 0):,.0f} ₽"),
                    metric_box("LTV (est.)", f"{State.metrics.get('ltv', 0):,.0f} ₽"),
                    metric_box("LTV / CAC", f"{State.metrics.get('ltv_cac_ratio', 0):.1f}x"),
                    columns="6",
                    spacing="4",
                    width="100%",
                ),
                rx.center(rx.text("Загрузка...", color=TEXT_MUTED), padding="4rem"),
            ),
            spacing="0",
            width="100%",
            padding="2rem",
        ),
        min_height="100vh",
        background=DARK_BG,
    )

# ==================== MAIN LAYOUT ====================
def index() -> rx.Component:
    return rx.hstack(
        sidebar(),
        rx.cond(
            State.current_page == "dashboard",
            page_dashboard(),
            rx.cond(
                State.current_page == "sources",
                page_sources(),
                rx.cond(
                    State.current_page == "trends",
                    page_trends(),
                    rx.cond(
                        State.current_page == "funnel",
                        page_funnel(),
                        rx.cond(
                            State.current_page == "rfm",
                            page_rfm(),
                            rx.cond(
                                State.current_page == "ab",
                                page_ab(),
                                rx.cond(
                                    State.current_page == "ai",
                                    page_ai(),
                                    page_export(),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        spacing="0",
        align="start",
    )

# ==================== APP ====================
app = rx.App(
    style=base_style,
    theme=rx.theme(appearance="dark"),
)

app.add_page(index, route="/", title="MetricsAI — Dashboard")
app.add_page(page_public_dashboard, route="/dashboard/[dashboard_id]", title="MetricsAI — Public Dashboard", on_load=State.load_public_dashboard)
