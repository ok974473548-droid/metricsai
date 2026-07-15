import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
from datetime import datetime, timedelta
from openai import OpenAI
from operator import attrgetter
from io import BytesIO
import json

st.set_page_config(page_title="MetricsAI v2.0", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; color: #E2E8F0; }
[data-testid="stAppViewContainer"] { background: linear-gradient(180deg, #0B0F19 0%, #0F172A 100%); background-attachment: fixed; }
[data-testid="stHeader"] { background: rgba(11, 15, 25, 0.9); backdrop-filter: blur(20px); border-bottom: 1px solid rgba(255,255,255,0.05); }
.block-container { padding: 2rem 3rem; max-width: 1400px; }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #0B0F19 0%, #111827 100%); border-right: 1px solid rgba(255,255,255,0.05); }
.glass-card { background: rgba(255, 255, 255, 0.02); backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 16px; padding: 1.5rem; box-shadow: 0 4px 24px rgba(0, 0, 0, 0.2); transition: all 0.3s ease; }
.glass-card:hover { border-color: rgba(255,255,255,0.12); box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3); }
.metric-container { background: rgba(255, 255, 255, 0.02); backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 16px; padding: 1.25rem; text-align: left; transition: all 0.3s ease; }
.metric-container:hover { border-color: rgba(255,255,255,0.12); background: rgba(255,255,255,0.04); }
.metric-value { font-size: 1.8rem; font-weight: 700; color: #F8FAFC; letter-spacing: -0.02em; line-height: 1.2; }
.metric-label { font-size: 0.75rem; color: #64748B; font-weight: 500; margin-top: 0.25rem; text-transform: uppercase; letter-spacing: 0.08em; }
.metric-delta { font-size: 0.8rem; font-weight: 600; margin-top: 0.5rem; }
.metric-delta.positive { color: #34D399; }
.metric-delta.negative { color: #F87171; }
.metric-delta.neutral { color: #94A3B8; }
.stButton > button { background: #F8FAFC !important; border: none !important; border-radius: 10px !important; padding: 0.6rem 1.5rem !important; font-weight: 600 !important; color: #0B0F19 !important; font-size: 0.85rem !important; transition: all 0.2s ease !important; }
.stButton > button:hover { transform: translateY(-1px); box-shadow: 0 4px 16px rgba(248, 250, 252, 0.2) !important; }
.stButton > button[kind="secondary"] { background: rgba(255,255,255,0.06) !important; color: #E2E8F0 !important; border: 1px solid rgba(255,255,255,0.08) !important; }
.stButton > button[kind="secondary"]:hover { background: rgba(255,255,255,0.1) !important; }
[data-testid="stFileUploader"] { background: rgba(255,255,255,0.02) !important; border: 1px dashed rgba(255,255,255,0.1) !important; border-radius: 12px !important; padding: 1.5rem !important; }
[data-testid="stFileUploader"]:hover { border-color: rgba(255,255,255,0.2) !important; background: rgba(255,255,255,0.03) !important; }
.ai-insight { background: rgba(255, 255, 255, 0.02); border-left: 3px solid #F8FAFC; border-radius: 0 12px 12px 0; padding: 1.25rem; margin: 0.75rem 0; }
.ai-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; font-weight: 600; font-size: 0.85rem; color: #F8FAFC; text-transform: uppercase; letter-spacing: 0.05em; }
hr { border: none; height: 1px; background: rgba(255,255,255,0.06); margin: 1.5rem 0; }
.stTabs [data-baseweb="tab-list"] { gap: 4px; background: rgba(255,255,255,0.02); border-radius: 12px; padding: 4px; }
.stTabs [data-baseweb="tab"] { background: transparent; border-radius: 8px; padding: 0.6rem 1.25rem; color: #64748B; font-weight: 500; font-size: 0.85rem; border: none; }
.stTabs [aria-selected="true"] { background: rgba(255,255,255,0.06) !important; color: #F8FAFC !important; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: rgba(11,15,25,0.5); }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 3px; }
.title-gradient { font-size: 2.2rem; font-weight: 800; color: #F8FAFC; letter-spacing: -0.03em; margin-bottom: 0.25rem; }
.subtitle { color: #64748B; font-size: 0.95rem; font-weight: 400; }
.badge { display: inline-block; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08); border-radius: 20px; padding: 0.2rem 0.6rem; font-size: 0.7rem; font-weight: 600; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.06em; }
.section-title { font-size: 1.1rem; font-weight: 700; color: #F8FAFC; margin-bottom: 1rem; letter-spacing: -0.01em; }
</style>
""", unsafe_allow_html=True)

if 'data' not in st.session_state:
    st.session_state.data = None
if 'white_label' not in st.session_state:
    st.session_state.white_label = {'company_name': 'MetricsAI', 'logo_text': 'MetricsAI'}

def init_db():
    conn = sqlite3.connect('metricsai.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS uploads (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, source_type TEXT, upload_date TEXT, rows INTEGER, cols INTEGER, metrics_summary TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, report_name TEXT, created_date TEXT, report_data TEXT)')
    conn.commit()
    conn.close()
init_db()

def save_upload(filename, source_type, rows, cols, summary):
    conn = sqlite3.connect('metricsai.db')
    c = conn.cursor()
    c.execute('INSERT INTO uploads (filename, source_type, upload_date, rows, cols, metrics_summary) VALUES (?, ?, ?, ?, ?, ?)', (filename, source_type, datetime.now().isoformat(), rows, cols, summary))
    conn.commit()
    conn.close()

@st.cache_resource
def get_ai_client():
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
    except:
        api_key = None
    if not api_key:
        return None
    return OpenAI(api_key=api_key)

def generate_insights(metrics_text, client, prompt_type="general"):
    if not client:
        return "⚠️ OpenAI API ключ не настроен. Добавьте OPENAI_API_KEY в Secrets."
    system_prompts = {
        "general": "Ты — senior product analyst. Дай 3-4 конкретных, практических инсайта на основе метрик. Используй маркетинговую терминологию. Ответ на русском языке, кратко и по делу.",
        "anomalies": "Ты — data scientist. Проанализируй аномалии в метриках и объясни возможные причины. Дай конкретные рекомендации. Ответ на русском.",
        "rfm": "Ты — CRM-аналитик. Проанализируй RFM-сегментацию клиентов. Дай рекомендации по маркетингу для каждого сегмента. Ответ на русском."
    }
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompts.get(prompt_type, system_prompts["general"])},
                {"role": "user", "content": f"Проанализируй данные:\n{metrics_text}"}
            ],
            temperature=0.7,
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Ошибка AI: {str(e)}"

def load_csv(file): return pd.read_csv(file)
def load_excel(file): return pd.read_excel(file)
def load_json(file): return pd.read_json(file)

def load_google_sheets(url):
    try:
        if '/edit' in url:
            url = url.replace('/edit', '/export?format=csv')
        elif 'export?format=csv' not in url:
            url = url + '/export?format=csv'
        return pd.read_csv(url)
    except Exception as e:
        st.error(f"Ошибка загрузки Google Sheets: {e}")
        return None

def generate_sample_data():
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', '2025-06-30', freq='D')
    n = len(dates)
    users = [f'user_{i:04d}' for i in range(500)]
    channels = ['organic', 'instagram', 'google', 'facebook', 'email', 'tiktok', 'referral']
    events = ['impression', 'click', 'visit', 'add_to_cart', 'purchase']
    df = pd.DataFrame({
        'date': np.random.choice(dates, n),
        'user_id': np.random.choice(users, n),
        'revenue': np.where(np.random.random(n) > 0.7, np.random.exponential(200, n).round(2), 0),
        'channel': np.random.choice(channels, n, p=[0.25, 0.15, 0.20, 0.15, 0.10, 0.10, 0.05]),
        'event_type': np.random.choice(events, n, p=[0.35, 0.20, 0.20, 0.10, 0.15]),
        'marketing_cost': np.random.choice([0, 0, 0, 30, 50, 80, 120, 200], n),
        'product_category': np.random.choice(['electronics', 'clothing', 'food', 'home', 'sports'], n)
    })
    return df.sort_values('date').reset_index(drop=True)

def calculate_metrics(df, prev_df=None):
    metrics = {}
    metrics['total_users'] = df['user_id'].nunique() if 'user_id' in df.columns else len(df)
    metrics['total_revenue'] = df['revenue'].sum() if 'revenue' in df.columns else 0
    metrics['total_orders'] = len(df[df['revenue'] > 0]) if 'revenue' in df.columns else len(df)
    metrics['arpu'] = metrics['total_revenue'] / metrics['total_users'] if metrics['total_users'] > 0 else 0
    metrics['aov'] = metrics['total_revenue'] / metrics['total_orders'] if metrics['total_orders'] > 0 else 0
    if 'channel' in df.columns and 'marketing_cost' in df.columns:
        channel_stats = df.groupby('channel').agg({'user_id': 'nunique', 'marketing_cost': 'sum'}).reset_index()
        channel_stats['cac'] = channel_stats['marketing_cost'] / channel_stats['user_id']
        metrics['cac_by_channel'] = channel_stats
        metrics['avg_cac'] = channel_stats['cac'].mean()
    else:
        metrics['avg_cac'] = 0; metrics['cac_by_channel'] = None
    if 'date' in df.columns and 'user_id' in df.columns and 'revenue' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        user_revenue = df.groupby('user_id')['revenue'].sum()
        metrics['ltv'] = user_revenue.mean() * 2.0
    else:
        metrics['ltv'] = metrics['arpu'] * 3
    metrics['ltv_cac_ratio'] = metrics['ltv'] / metrics['avg_cac'] if metrics['avg_cac'] > 0 else 0
    if prev_df is not None and 'revenue' in prev_df.columns:
        prev_revenue = prev_df['revenue'].sum()
        metrics['revenue_delta'] = ((metrics['total_revenue'] - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else 0
    else:
        metrics['revenue_delta'] = None
    if 'date' in df.columns:
        df['month'] = df['date'].dt.to_period('M').astype(str)
        monthly = df.groupby('month').agg({'revenue': 'sum', 'user_id': 'nunique'}).reset_index()
        monthly['arpu'] = monthly['revenue'] / monthly['user_id']
        metrics['monthly_trend'] = monthly
    else:
        metrics['monthly_trend'] = None
    if 'event_type' in df.columns:
        funnel_order = ['impression', 'click', 'visit', 'add_to_cart', 'purchase', 'order']
        funnel_counts = df['event_type'].value_counts().to_dict()
        funnel_data = []
        for step in funnel_order:
            if step in funnel_counts: funnel_data.append({'step': step.upper(), 'users': funnel_counts[step]})
        if not funnel_data:
            for k, v in funnel_counts.items(): funnel_data.append({'step': k.upper(), 'users': v})
        metrics['funnel'] = pd.DataFrame(funnel_data) if funnel_data else None
    else:
        metrics['funnel'] = None
    if 'date' in df.columns and 'user_id' in df.columns:
        df['order_month'] = df['date'].dt.to_period('M')
        df['cohort'] = df.groupby('user_id')['order_month'].transform('min')
        cohort_data = df.groupby(['cohort', 'order_month']).agg({'user_id': 'nunique'}).reset_index()
        cohort_data['period'] = (cohort_data['order_month'] - cohort_data['cohort']).apply(attrgetter('n'))
        cohort_table = cohort_data.pivot(index='cohort', columns='period', values='user_id')
        cohort_sizes = cohort_table.iloc[:, 0]
        retention = cohort_table.divide(cohort_sizes, axis=0)
        metrics['retention'] = retention
    else:
        metrics['retention'] = None
    return metrics

def rfm_analysis(df):
    if 'date' not in df.columns or 'user_id' not in df.columns or 'revenue' not in df.columns:
        return None
    df['date'] = pd.to_datetime(df['date'])
    snapshot_date = df['date'].max() + timedelta(days=1)
    rfm = df.groupby('user_id', as_index=False).agg(
        recency=('date', lambda x: (snapshot_date - x.max()).days),
        monetary=('revenue', 'sum'),
        frequency=('user_id', 'size')
    )
    rfm['R'] = pd.qcut(rfm['recency'], 5, labels=[5,4,3,2,1])
    rfm['F'] = pd.qcut(rfm['frequency'].rank(method='first'), 5, labels=[1,2,3,4,5])
    rfm['M'] = pd.qcut(rfm['monetary'], 5, labels=[1,2,3,4,5])
    rfm['RFM_Score'] = rfm['R'].astype(str) + rfm['F'].astype(str) + rfm['M'].astype(str)
    def segment(row):
        if row['RFM_Score'] in ['555', '554', '544', '545', '454', '455', '445']: return 'Champions'
        elif row['RFM_Score'] in ['543', '444', '435', '355', '354', '345', '344', '335']: return 'Loyal Customers'
        elif row['RFM_Score'] in ['512', '511', '422', '421', '412', '411', '311']: return 'New Customers'
        elif row['RFM_Score'] in ['553', '551', '552', '541', '542', '533', '532', '531', '452', '451']: return 'Potential Loyalists'
        elif row['RFM_Score'] in ['155', '154', '144', '214', '215', '115', '114']: return 'At Risk'
        elif row['RFM_Score'] in ['155', '254', '245', '244', '253', '252', '243', '242', '235', '234']: return 'Cannot Lose Them'
        elif row['RFM_Score'] in ['331', '321', '231', '241', '251']: return 'Hibernating'
        else: return 'Others'
    rfm['Segment'] = rfm.apply(segment, axis=1)
    return rfm

def detect_anomalies(df):
    if 'date' not in df.columns or 'revenue' not in df.columns: return None
    df['date'] = pd.to_datetime(df['date'])
    daily = df.groupby('date')['revenue'].sum().reset_index()
    daily['zscore'] = (daily['revenue'] - daily['revenue'].mean()) / daily['revenue'].std()
    daily['anomaly'] = np.abs(daily['zscore']) > 2
    daily['anomaly_type'] = daily.apply(lambda x: 'spike' if x['zscore'] > 2 else ('drop' if x['zscore'] < -2 else 'normal'), axis=1)
    return daily

def ab_test_calculator(conv_a, n_a, conv_b, n_b, confidence=0.95):
    p_a = conv_a / n_a if n_a > 0 else 0
    p_b = conv_b / n_b if n_b > 0 else 0
    se = np.sqrt(p_a * (1 - p_a) / n_a + p_b * (1 - p_b) / n_b)
    z = (p_b - p_a) / se if se > 0 else 0
    z_critical = 1.96 if confidence == 0.95 else 2.58
    is_significant = abs(z) > z_critical
    uplift = ((p_b - p_a) / p_a * 100) if p_a > 0 else 0
    return {'p_a': p_a, 'p_b': p_b, 'uplift': uplift, 'z_score': z, 'is_significant': is_significant, 'confidence': confidence}

def create_pdf_report(metrics, df, rfm_df=None):
    try:
        from fpdf import FPDF
    except ImportError:
        return None
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, 'MetricsAI Report', 0, 1, 'C')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 10, f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}', 0, 1, 'C')
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Key Metrics', 0, 1)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 8, f'Total Users: {metrics["total_users"]:,}', 0, 1)
    pdf.cell(0, 8, f'Total Revenue: {metrics["total_revenue"]:,.2f}', 0, 1)
    pdf.cell(0, 8, f'ARPU: {metrics["arpu"]:,.2f}', 0, 1)
    pdf.cell(0, 8, f'AOV: {metrics["aov"]:,.2f}', 0, 1)
    pdf.cell(0, 8, f'LTV (est.): {metrics["ltv"]:,.2f}', 0, 1)
    pdf.cell(0, 8, f'LTV/CAC Ratio: {metrics["ltv_cac_ratio"]:.2f}x', 0, 1)
    pdf.ln(10)
    if rfm_df is not None:
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, 'RFM Segments', 0, 1)
        pdf.set_font('Arial', '', 10)
        segments = rfm_df['Segment'].value_counts()
        for seg, count in segments.items():
            pdf.cell(0, 8, f'{seg}: {count} users', 0, 1)
    return pdf.output(dest='S').encode('latin-1')

# ==================== SIDEBAR ====================
with st.sidebar:
    st.markdown(f'<div style="font-size: 1.4rem; font-weight: 800; color: #F8FAFC; letter-spacing: -0.03em; margin-bottom: 1.5rem;">{st.session_state.white_label["logo_text"]}</div>', unsafe_allow_html=True)
    page = st.radio("Навигация", ["📥 Источники данных", "📊 Дашборд", "📈 Тренды и сравнение", "🔻 Воронка", "👥 Когорты", "🎯 RFM-анализ", "⚖️ A/B калькулятор", "🤖 AI-инсайты", "📄 Экспорт"], label_visibility="collapsed")
    st.markdown("<hr>", unsafe_allow_html=True)
    with st.expander("⚙️ White-label"):
        st.session_state.white_label['company_name'] = st.text_input("Company Name", st.session_state.white_label['company_name'])
        st.session_state.white_label['logo_text'] = st.text_input("Logo Text", st.session_state.white_label['logo_text'])
    st.markdown("<div style='position: fixed; bottom: 1rem; left: 1rem; color: #475569; font-size: 0.7rem;'>MetricsAI v2.0<br>Built for HSE FCS</div>", unsafe_allow_html=True)

# ==================== PAGE: DATA SOURCES ====================
if page == "📥 Источники данных":
    st.markdown(f'<div class="title-gradient">{st.session_state.white_label["company_name"]}</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Загрузите данные из любого источника</div>', unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    source_tabs = st.tabs(["📁 CSV / Excel", "🔗 Google Sheets", "📝 JSON", "✏️ Ручной ввод", "🎲 Демо-данные"])
    with source_tabs[0]:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Загрузите CSV или Excel", type=['csv', 'xlsx', 'xls'])
        if uploaded_file is not None:
            if uploaded_file.name.endswith('.csv'):
                df = load_csv(uploaded_file); source = "CSV"
            else:
                df = load_excel(uploaded_file); source = "Excel"
            st.session_state.data = df
            save_upload(uploaded_file.name, source, len(df), len(df.columns), f"Loaded {len(df)} rows")
            st.success(f"✅ Загружено {len(df):,} строк из {source}")
            st.dataframe(df.head(10), use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with source_tabs[1]:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        gs_url = st.text_input("URL Google Sheets (public)", placeholder="https://docs.google.com/spreadsheets/d/...")
        if gs_url and st.button("Загрузить"):
            df = load_google_sheets(gs_url)
            if df is not None:
                st.session_state.data = df
                save_upload("google_sheets", "Google Sheets", len(df), len(df.columns), f"Loaded {len(df)} rows")
                st.success(f"✅ Загружено {len(df):,} строк из Google Sheets")
                st.dataframe(df.head(10), use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with source_tabs[2]:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        json_file = st.file_uploader("Загрузите JSON", type=['json'])
        if json_file is not None:
            df = load_json(json_file)
            st.session_state.data = df
            save_upload(json_file.name, "JSON", len(df), len(df.columns), f"Loaded {len(df)} rows")
            st.success(f"✅ Загружено {len(df):,} строк из JSON")
            st.dataframe(df.head(10), use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with source_tabs[3]:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("Введите данные в формате CSV (первая строка — заголовки):")
        manual_data = st.text_area("Данные", height=200, placeholder="date,user_id,revenue\n2024-01-01,user_001,150.00\n...")
        if st.button("Загрузить ручной ввод") and manual_data:
            try:
                df = pd.read_csv(BytesIO(manual_data.encode()))
                st.session_state.data = df
                save_upload("manual_input", "Manual", len(df), len(df.columns), f"Loaded {len(df)} rows")
                st.success(f"✅ Загружено {len(df):,} строк")
                st.dataframe(df.head(10), use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Ошибка парсинга: {e}")
        st.markdown('</div>', unsafe_allow_html=True)
    with source_tabs[4]:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("Сгенерировать демо-данные за 2.5 года (1000+ строк)")
        if st.button("🎲 Сгенерировать демо-данные"):
            with st.spinner("Генерация..."):
                df = generate_sample_data()
                st.session_state.data = df
                save_upload("sample_data", "Demo", len(df), len(df.columns), f"Generated {len(df)} rows")
                st.success(f"✅ Сгенерировано {len(df):,} строк демо-данных")
                st.dataframe(df.head(10), use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

# ==================== PAGE: DASHBOARD ====================
elif page == "📊 Дашборд":
    if st.session_state.data is None:
        st.warning("⚠️ Сначала загрузите данные в разделе 'Источники данных'")
    else:
        df = st.session_state.data.copy()
        metrics = calculate_metrics(df)
        st.markdown('<div class="title-gradient">Дашборд</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle">Ключевые метрики в реальном времени</div>', unsafe_allow_html=True)
        st.markdown("<hr>", unsafe_allow_html=True)
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        with m1:
            delta = f"{metrics['revenue_delta']:+.1f}%" if metrics['revenue_delta'] is not None else "—"
            delta_class = "positive" if metrics['revenue_delta'] and metrics['revenue_delta'] > 0 else "negative" if metrics['revenue_delta'] and metrics['revenue_delta'] < 0 else "neutral"
            st.markdown(f'<div class="metric-container"><div class="metric-label">Выручка</div><div class="metric-value">{metrics["total_revenue"]:,.0f} ₽</div><div class="metric-delta {delta_class}">{delta}</div></div>', unsafe_allow_html=True)
        with m2:
            st.markdown(f'<div class="metric-container"><div class="metric-label">Пользователей</div><div class="metric-value">{metrics["total_users"]:,}</div></div>', unsafe_allow_html=True)
        with m3:
            st.markdown(f'<div class="metric-container"><div class="metric-label">ARPU</div><div class="metric-value">{metrics["arpu"]:,.0f} ₽</div></div>', unsafe_allow_html=True)
        with m4:
            st.markdown(f'<div class="metric-container"><div class="metric-label">AOV</div><div class="metric-value">{metrics["aov"]:,.0f} ₽</div></div>', unsafe_allow_html=True)
        with m5:
            st.markdown(f'<div class="metric-container"><div class="metric-label">LTV (est.)</div><div class="metric-value">{metrics["ltv"]:,.0f} ₽</div></div>', unsafe_allow_html=True)
        with m6:
            ratio = metrics['ltv_cac_ratio']
            ratio_color = "#34D399" if ratio > 3 else "#FBBF24" if ratio > 1 else "#F87171"
            st.markdown(f'<div class="metric-container"><div class="metric-label">LTV / CAC</div><div class="metric-value" style="color: {ratio_color};">{ratio:.1f}x</div></div>', unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if metrics['monthly_trend'] is not None:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                st.markdown('<div class="section-title">📈 Динамика выручки</div>', unsafe_allow_html=True)
                fig = px.line(metrics['monthly_trend'], x='month', y='revenue', template='plotly_dark', color_discrete_sequence=['#F8FAFC'])
                fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#94A3B8', margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                st.markdown('</div>', unsafe_allow_html=True)
            with col2:
                st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                st.markdown('<div class="section-title">🎯 ARPU по месяцам</div>', unsafe_allow_html=True)
                fig = px.bar(metrics['monthly_trend'], x='month', y='arpu', template='plotly_dark', color_discrete_sequence=['#94A3B8'])
                fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#94A3B8', margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                st.markdown('</div>', unsafe_allow_html=True)
        if 'channel' in df.columns:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">🎯 Выручка по каналам</div>', unsafe_allow_html=True)
            channel_revenue = df.groupby('channel')['revenue'].sum().reset_index().sort_values('revenue', ascending=True)
            fig = px.bar(channel_revenue, x='revenue', y='channel', orientation='h', template='plotly_dark', color_discrete_sequence=['#F8FAFC'])
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#94A3B8', margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            st.markdown('</div>', unsafe_allow_html=True)

# ==================== PAGE: TRENDS ====================
elif page == "📈 Тренды и сравнение":
    if st.session_state.data is None:
        st.warning("⚠️ Сначала загрузите данные")
    else:
        df = st.session_state.data.copy()
        st.markdown('<div class="title-gradient">Тренды и сравнение</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle">Сравнение периодов и прогнозирование</div>', unsafe_allow_html=True)
        st.markdown("<hr>", unsafe_allow_html=True)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df['year_month'] = df['date'].dt.to_period('M').astype(str)
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">⚖️ Сравнение периодов</div>', unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                period_a = st.selectbox("Период A", sorted(df['year_month'].unique()), index=0)
            with col2:
                period_b = st.selectbox("Период B", sorted(df['year_month'].unique()), index=len(sorted(df['year_month'].unique()))-1)
            df_a = df[df['year_month'] == period_a]
            df_b = df[df['year_month'] == period_b]
            if len(df_a) > 0 and len(df_b) > 0:
                rev_a = df_a['revenue'].sum() if 'revenue' in df_a.columns else 0
                rev_b = df_b['revenue'].sum() if 'revenue' in df_b.columns else 0
                users_a = df_a['user_id'].nunique() if 'user_id' in df_a.columns else len(df_a)
                users_b = df_b['user_id'].nunique() if 'user_id' in df_b.columns else len(df_b)
                c1, c2, c3, c4 = st.columns(4)
                rev_delta = ((rev_b - rev_a) / rev_a * 100) if rev_a > 0 else 0
                users_delta = ((users_b - users_a) / users_a * 100) if users_a > 0 else 0
                with c1:
                    st.markdown(f'<div class="metric-container"><div class="metric-label">Выручка A</div><div class="metric-value">{rev_a:,.0f} ₽</div></div>', unsafe_allow_html=True)
                with c2:
                    st.markdown(f'<div class="metric-container"><div class="metric-label">Выручка B</div><div class="metric-value">{rev_b:,.0f} ₽</div></div>', unsafe_allow_html=True)
                with c3:
                    delta_class = "positive" if rev_delta > 0 else "negative"
                    st.markdown(f'<div class="metric-container"><div class="metric-label">Δ Выручка</div><div class="metric-value {delta_class}">{rev_delta:+.1f}%</div></div>', unsafe_allow_html=True)
                with c4:
                    delta_class = "positive" if users_delta > 0 else "negative"
                    st.markdown(f'<div class="metric-container"><div class="metric-label">Δ Пользователи</div><div class="metric-value {delta_class}">{users_delta:+.1f}%</div></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">🔮 Прогнозирование (3 месяца)</div>', unsafe_allow_html=True)
            monthly = df.groupby('year_month')['revenue'].sum().reset_index()
            monthly['idx'] = range(len(monthly))
            if len(monthly) >= 3:
                x = monthly['idx'].values
                y = monthly['revenue'].values
                n = len(x)
                slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (n * np.sum(x**2) - np.sum(x)**2)
                intercept = (np.sum(y) - slope * np.sum(x)) / n
                future_idx = list(range(n, n + 3))
                future_revenue = [slope * i + intercept for i in future_idx]
                future_months = [f"M+{i-n+1}" for i in future_idx]
                forecast_df = pd.DataFrame({'month': list(monthly['year_month']) + future_months, 'revenue': list(monthly['revenue']) + future_revenue, 'type': ['actual'] * n + ['forecast'] * 3})
                fig = px.line(forecast_df, x='month', y='revenue', color='type', template='plotly_dark', color_discrete_map={'actual': '#F8FAFC', 'forecast': '#94A3B8'})
                fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#94A3B8', margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            st.markdown('</div>', unsafe_allow_html=True)

# ==================== PAGE: FUNNEL ====================
elif page == "🔻 Воронка":
    if st.session_state.data is None:
        st.warning("⚠️ Сначала загрузите данные")
    else:
        df = st.session_state.data.copy()
        metrics = calculate_metrics(df)
        st.markdown('<div class="title-gradient">Воронка конверсии</div>', unsafe_allow_html=True)
        st.markdown("<hr>", unsafe_allow_html=True)
        if metrics['funnel'] is not None:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            fig = px.funnel(metrics['funnel'], x='users', y='step', template='plotly_dark', color_discrete_sequence=['#F8FAFC', '#CBD5E1', '#94A3B8', '#64748B', '#475569'])
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#94A3B8', margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            st.markdown('</div>', unsafe_allow_html=True)
            if len(metrics['funnel']) > 1:
                st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                st.markdown('<div class="section-title">📉 Конверсия между этапами</div>', unsafe_allow_html=True)
                funnel_df = metrics['funnel'].copy()
                funnel_df['conversion'] = funnel_df['users'].pct_change() * 100
                funnel_df['conversion'] = funnel_df['conversion'].fillna(100)
                conv_cols = st.columns(len(funnel_df) - 1)
                for i, (_, row) in enumerate(funnel_df.iloc[1:].iterrows()):
                    with conv_cols[i]:
                        prev_step = funnel_df.iloc[i]['step']
                        st.markdown(f'<div class="metric-container" style="padding: 1rem;"><div class="metric-value" style="font-size: 1.3rem;">{row["conversion"]:.1f}%</div><div class="metric-label">{prev_step} → {row["step"]}</div></div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("Добавьте колонку 'event_type' для анализа воронки")

# ==================== PAGE: COHORTS ====================
elif page == "👥 Когорты":
    if st.session_state.data is None:
        st.warning("⚠️ Сначала загрузите данные")
    else:
        df = st.session_state.data.copy()
        metrics = calculate_metrics(df)
        st.markdown('<div class="title-gradient">Когортный анализ</div>', unsafe_allow_html=True)
        st.markdown("<hr>", unsafe_allow_html=True)
        if metrics['retention'] is not None:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            fig = px.imshow(metrics['retention'].values, labels=dict(x='Период (мес)', y='Когорта', color='Retention'), x=[f'M{i}' for i in range(len(metrics['retention'].columns))], y=[str(c) for c in metrics['retention'].index], template='plotly_dark', color_continuous_scale='Greys', aspect='auto')
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#94A3B8', margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            st.markdown('</div>', unsafe_allow_html=True)
            avg_retention = metrics['retention'].mean()
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">📉 Средний Retention</div>', unsafe_allow_html=True)
            fig2 = px.line(x=avg_retention.index, y=avg_retention.values, template='plotly_dark', color_discrete_sequence=['#F8FAFC'])
            fig2.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#94A3B8', margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False})
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("Добавьте 'date' и 'user_id' для когортного анализа")

# ==================== PAGE: RFM ====================
elif page == "🎯 RFM-анализ":
    if st.session_state.data is None:
        st.warning("⚠️ Сначала загрузите данные")
    else:
        df = st.session_state.data.copy()
        st.markdown('<div class="title-gradient">RFM-анализ</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle">Сегментация клиентов по Recency, Frequency, Monetary</div>', unsafe_allow_html=True)
        st.markdown("<hr>", unsafe_allow_html=True)
        rfm = rfm_analysis(df)
        if rfm is not None:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">📊 Распределение сегментов</div>', unsafe_allow_html=True)
            segments = rfm['Segment'].value_counts().reset_index()
            segments.columns = ['Segment', 'Count']
            fig = px.bar(segments, x='Count', y='Segment', orientation='h', template='plotly_dark', color_discrete_sequence=['#F8FAFC'])
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#94A3B8', margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">👥 Топ сегментов</div>', unsafe_allow_html=True)
            segment_stats = rfm.groupby('Segment').agg({'recency': 'mean', 'frequency': 'mean', 'monetary': 'mean'}).round(1).reset_index()
            segment_stats.columns = ['Сегмент', 'Средняя давность (дн)', 'Средняя частота', 'Средний чек']
            st.dataframe(segment_stats, use_container_width=True, hide_index=True)
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">🤖 AI-анализ RFM</div>', unsafe_allow_html=True)
            if st.button("✨ Сгенерировать AI-рекомендации по RFM"):
                with st.spinner("Анализирую сегменты..."):
                    client = get_ai_client()
                    rfm_text = segment_stats.to_string(index=False)
                    insights = generate_insights(rfm_text, client, "rfm")
                    st.markdown(f'<div class="ai-insight"><div class="ai-header">🧠 AI CRM Analyst</div><div style="color: #E2E8F0; line-height: 1.7;">{insights.replace(chr(10), "<br>")}</div></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("Для RFM нужны колонки: date, user_id, revenue")

# ==================== PAGE: A/B TEST ====================
elif page == "⚖️ A/B калькулятор":
    st.markdown('<div class="title-gradient">A/B калькулятор</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Статистическая значимость разницы конверсий</div>', unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="section-title">🅰️ Вариант A (Control)</div>', unsafe_allow_html=True)
        conv_a = st.number_input("Конверсии A", min_value=0, value=120)
        n_a = st.number_input("Посетители A", min_value=1, value=1000)
    with col2:
        st.markdown('<div class="section-title">🅱️ Вариант B (Test)</div>', unsafe_allow_html=True)
        conv_b = st.number_input("Конверсии B", min_value=0, value=150)
        n_b = st.number_input("Посетители B", min_value=1, value=1000)
    confidence = st.selectbox("Уровень доверия", [0.90, 0.95, 0.99], index=1)
    if st.button("🚀 Рассчитать"):
        result = ab_test_calculator(conv_a, n_a, conv_b, n_b, confidence)
        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f'<div class="metric-container"><div class="metric-label">Конверсия A</div><div class="metric-value">{result["p_a"]:.2%}</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="metric-container"><div class="metric-label">Конверсия B</div><div class="metric-value">{result["p_b"]:.2%}</div></div>', unsafe_allow_html=True)
        with c3:
            delta_class = "positive" if result["uplift"] > 0 else "negative"
            st.markdown(f'<div class="metric-container"><div class="metric-label">Uplift</div><div class="metric-value {delta_class}">{result["uplift"]:+.1f}%</div></div>', unsafe_allow_html=True)
        with c4:
            sig_color = "#34D399" if result["is_significant"] else "#F87171"
            sig_text = "✅ Да" if result["is_significant"] else "❌ Нет"
            st.markdown(f'<div class="metric-container"><div class="metric-label">Значимость ({confidence:.0%})</div><div class="metric-value" style="color: {sig_color};">{sig_text}</div></div>', unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f'<div class="glass-card"><div style="color: #94A3B8; font-size: 0.9rem;">Z-score: <b>{result["z_score"]:.3f}</b> | Критическое значение: ±{1.96 if confidence==0.95 else 2.58 if confidence==0.99 else 1.645}</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ==================== PAGE: AI INSIGHTS ====================
elif page == "🤖 AI-инсайты":
    if st.session_state.data is None:
        st.warning("⚠️ Сначала загрузите данные")
    else:
        df = st.session_state.data.copy()
        metrics = calculate_metrics(df)
        st.markdown('<div class="title-gradient">AI-инсайты</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle">Искусственный интеллект анализирует ваши метрики</div>', unsafe_allow_html=True)
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">🧠 Общий анализ метрик</div>', unsafe_allow_html=True)
        if st.button("✨ Сгенерировать инсайты"):
            with st.spinner("Анализирую..."):
                client = get_ai_client()
                metrics_text = f"Total Users: {metrics['total_users']}\nTotal Revenue: {metrics['total_revenue']:,.2f}\nARPU: {metrics['arpu']:,.2f}\nAOV: {metrics['aov']:,.2f}\nLTV: {metrics['ltv']:,.2f}\nAvg CAC: {metrics['avg_cac']:,.2f}\nLTV/CAC: {metrics['ltv_cac_ratio']:.2f}"
                if metrics['cac_by_channel'] is not None:
                    metrics_text += '\nCAC by Channel:\n'
                    for _, row in metrics['cac_by_channel'].iterrows():
                        metrics_text += f"- {row['channel']}: CAC={row['cac']:,.2f}, Users={row['user_id']}\n"
                insights = generate_insights(metrics_text, client, "general")
                st.markdown(f'<div class="ai-insight"><div class="ai-header">🧠 AI Product Analyst</div><div style="color: #E2E8F0; line-height: 1.7;">{insights.replace(chr(10), "<br>")}</div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">🚨 Обнаружение аномалий</div>', unsafe_allow_html=True)
        if st.button("🔍 Найти аномалии"):
            with st.spinner("Сканирую данные..."):
                anomalies = detect_anomalies(df)
                if anomalies is not None:
                    anomaly_count = anomalies['anomaly'].sum()
                    if anomaly_count > 0:
                        st.markdown(f'<div style="color: #F87171; font-weight: 600; margin-bottom: 1rem;">⚠️ Обнаружено {int(anomaly_count)} аномальных дней</div>', unsafe_allow_html=True)
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=anomalies['date'], y=anomalies['revenue'], mode='lines', name='Выручка', line=dict(color='#475569', width=1)))
                        anomalies_df = anomalies[anomalies['anomaly']]
                        fig.add_trace(go.Scatter(x=anomalies_df['date'], y=anomalies_df['revenue'], mode='markers', name='Аномалии', marker=dict(color='#F87171', size=8)))
                        fig.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#94A3B8', margin=dict(l=20, r=20, t=20, b=20), showlegend=False)
                        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                        client = get_ai_client()
                        anomaly_text = anomalies_df[['date', 'revenue', 'zscore']].to_string(index=False)
                        insights = generate_insights(f"Аномальные дни:\n{anomaly_text}", client, "anomalies")
                        st.markdown(f'<div class="ai-insight"><div class="ai-header">🧠 AI Data Scientist</div><div style="color: #E2E8F0; line-height: 1.7;">{insights.replace(chr(10), "<br>")}</div></div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div style="color: #34D399; font-weight: 600;">✅ Аномалий не обнаружено</div>', unsafe_allow_html=True)
                else:
                    st.info("Нужны колонки 'date' и 'revenue'")
        st.markdown('</div>', unsafe_allow_html=True)

# ==================== PAGE: EXPORT ====================
elif page == "📄 Экспорт":
    if st.session_state.data is None:
        st.warning("⚠️ Сначала загрузите данные")
    else:
        df = st.session_state.data.copy()
        metrics = calculate_metrics(df)
        rfm = rfm_analysis(df)
        st.markdown('<div class="title-gradient">Экспорт отчётов</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle">Скачайте данные в любом формате</div>', unsafe_allow_html=True)
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">📥 Сырые данные</div>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        with col1:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("⬇️ CSV", csv, "metricsai_data.csv", "text/csv", use_container_width=True)
        with col2:
            excel_buffer = BytesIO()
            df.to_excel(excel_buffer, index=False)
            st.download_button("⬇️ Excel", excel_buffer.getvalue(), "metricsai_data.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        with col3:
            json_str = df.to_json(orient='records', force_ascii=False)
            st.download_button("⬇️ JSON", json_str.encode('utf-8'), "metricsai_data.json", "application/json", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        if rfm is not None:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">🎯 RFM-данные</div>', unsafe_allow_html=True)
            rfm_csv = rfm.to_csv(index=False).encode('utf-8')
            st.download_button("⬇️ RFM CSV", rfm_csv, "metricsai_rfm.csv", "text/csv", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">📄 PDF-отчёт</div>', unsafe_allow_html=True)
        if st.button("🖨️ Сгенерировать PDF"):
            with st.spinner("Генерация PDF..."):
                pdf_bytes = create_pdf_report(metrics, df, rfm)
                if pdf_bytes:
                    st.download_button("⬇️ Скачать PDF", pdf_bytes, "metricsai_report.pdf", "application/pdf", use_container_width=True)
                else:
                    st.info("PDF-генерация требует fpdf2. Добавьте в requirements: fpdf2")
        st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)
st.markdown(f'<div style="text-align: center; color: #475569; font-size: 0.75rem;">{st.session_state.white_label["company_name"]} © 2025 — Built for product & marketing analytics</div>', unsafe_allow_html=True)
