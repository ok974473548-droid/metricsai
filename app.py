import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sqlite3
from datetime import datetime
from openai import OpenAI
from operator import attrgetter

st.set_page_config(page_title="MetricsAI — Product & Marketing Analytics", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; color: #E2E8F0; }
[data-testid="stAppViewContainer"] { background: linear-gradient(135deg, #0F172A 0%, #1E1B4B 50%, #312E81 100%); background-attachment: fixed; }
[data-testid="stHeader"] { background: rgba(15, 23, 42, 0.8); backdrop-filter: blur(20px); }
.block-container { padding: 2rem 3rem; max-width: 1400px; }
.glass-card { background: rgba(255,255,255,0.03); backdrop-filter: blur(20px); border: 1px solid rgba(255,255,255,0.08); border-radius: 24px; padding: 1.5rem; box-shadow: 0 8px 32px rgba(0,0,0,0.3); transition: all 0.3s ease; }
.glass-card:hover { border-color: rgba(139,92,246,0.3); box-shadow: 0 12px 48px rgba(139,92,246,0.15); transform: translateY(-2px); }
.metric-container { background: linear-gradient(135deg, rgba(139,92,246,0.1) 0%, rgba(59,130,246,0.1) 100%); backdrop-filter: blur(20px); border: 1px solid rgba(139,92,246,0.15); border-radius: 20px; padding: 1.5rem; text-align: center; transition: all 0.3s ease; }
.metric-container:hover { border-color: rgba(139,92,246,0.4); box-shadow: 0 0 30px rgba(139,92,246,0.2); }
.metric-value { font-size: 2.2rem; font-weight: 800; background: linear-gradient(135deg, #C084FC 0%, #60A5FA 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.metric-label { font-size: 0.85rem; color: #94A3B8; font-weight: 500; margin-top: 0.5rem; text-transform: uppercase; letter-spacing: 0.05em; }
.stButton > button { background: linear-gradient(135deg, #8B5CF6 0%, #3B82F6 100%) !important; border: none !important; border-radius: 12px !important; padding: 0.75rem 2rem !important; font-weight: 600 !important; color: white !important; box-shadow: 0 4px 20px rgba(139,92,246,0.4) !important; transition: all 0.3s ease !important; }
.stButton > button:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(139,92,246,0.6) !important; }
[data-testid="stFileUploader"] { background: rgba(255,255,255,0.02) !important; border: 2px dashed rgba(139,92,246,0.3) !important; border-radius: 20px !important; padding: 2rem !important; }
[data-testid="stFileUploader"]:hover { border-color: rgba(139,92,246,0.6) !important; background: rgba(139,92,246,0.05) !important; }
.ai-insight { background: linear-gradient(135deg, rgba(139,92,246,0.08) 0%, rgba(59,130,246,0.08) 100%); border-left: 4px solid #8B5CF6; border-radius: 0 16px 16px 0; padding: 1.5rem; margin: 1rem 0; backdrop-filter: blur(10px); }
.ai-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; font-weight: 700; color: #C084FC; }
hr { border: none; height: 1px; background: linear-gradient(90deg, transparent, rgba(139,92,246,0.3), transparent); margin: 2rem 0; }
.stTabs [data-baseweb="tab-list"] { gap: 8px; background: rgba(255,255,255,0.02); border-radius: 16px; padding: 6px; }
.stTabs [data-baseweb="tab"] { background: transparent; border-radius: 12px; padding: 0.75rem 1.5rem; color: #94A3B8; font-weight: 500; border: none; }
.stTabs [aria-selected="true"] { background: linear-gradient(135deg, rgba(139,92,246,0.2), rgba(59,130,246,0.2)) !important; color: #E2E8F0 !important; border: 1px solid rgba(139,92,246,0.3) !important; }
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: rgba(15,23,42,0.5); }
::-webkit-scrollbar-thumb { background: linear-gradient(180deg, #8B5CF6, #3B82F6); border-radius: 4px; }
.title-gradient { font-size: 3rem; font-weight: 800; background: linear-gradient(135deg, #C084FC 0%, #60A5FA 50%, #22D3EE 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin-bottom: 0.5rem; }
.subtitle { color: #94A3B8; font-size: 1.1rem; font-weight: 400; }
.badge { display: inline-block; background: rgba(139,92,246,0.15); border: 1px solid rgba(139,92,246,0.3); border-radius: 20px; padding: 0.25rem 0.75rem; font-size: 0.75rem; font-weight: 600; color: #C084FC; text-transform: uppercase; letter-spacing: 0.05em; }
</style>
""", unsafe_allow_html=True)

def init_db():
    conn = sqlite3.connect('metricsai.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS uploads (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, upload_date TEXT, rows INTEGER, metrics_summary TEXT)')
    conn.commit()
    conn.close()
init_db()

def save_upload(filename, rows, metrics_summary):
    conn = sqlite3.connect('metricsai.db')
    c = conn.cursor()
    c.execute('INSERT INTO uploads (filename, upload_date, rows, metrics_summary) VALUES (?, ?, ?, ?)', (filename, datetime.now().isoformat(), rows, metrics_summary))
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

def generate_insights(metrics_text, client):
    if not client:
        return "⚠️ OpenAI API ключ не настроен. Добавьте OPENAI_API_KEY в Secrets."
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты — senior product analyst. Дай 3-4 конкретных, практических инсайта на основе метрик. Используй маркетинговую терминологию. Ответ на русском языке, кратко и по делу."},
                {"role": "user", "content": f"Проанализируй метрики и дай рекомендации:\n{metrics_text}"}
            ],
            temperature=0.7,
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Ошибка AI: {str(e)}"

def calculate_metrics(df):
    metrics = {}
    metrics['total_users'] = df['user_id'].nunique() if 'user_id' in df.columns else len(df)
    metrics['total_revenue'] = df['revenue'].sum() if 'revenue' in df.columns else 0
    metrics['total_orders'] = len(df)
    metrics['arpu'] = metrics['total_revenue'] / metrics['total_users'] if metrics['total_users'] > 0 else 0
    metrics['aov'] = metrics['total_revenue'] / metrics['total_orders'] if metrics['total_orders'] > 0 else 0
    if 'channel' in df.columns and 'marketing_cost' in df.columns:
        channel_stats = df.groupby('channel').agg({'user_id': 'nunique', 'marketing_cost': 'sum'}).reset_index()
        channel_stats['cac'] = channel_stats['marketing_cost'] / channel_stats['user_id']
        metrics['cac_by_channel'] = channel_stats
        metrics['avg_cac'] = channel_stats['cac'].mean()
    else:
        metrics['avg_cac'] = 0
        metrics['cac_by_channel'] = None
    if 'date' in df.columns and 'user_id' in df.columns and 'revenue' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        user_revenue = df.groupby('user_id')['revenue'].sum()
        metrics['ltv'] = user_revenue.mean() * 1.5
    else:
        metrics['ltv'] = metrics['arpu'] * 3
    metrics['ltv_cac_ratio'] = metrics['ltv'] / metrics['avg_cac'] if metrics['avg_cac'] > 0 else 0
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
            if step in funnel_counts:
                funnel_data.append({'step': step.upper(), 'users': funnel_counts[step]})
        if not funnel_data:
            for k, v in funnel_counts.items():
                funnel_data.append({'step': k.upper(), 'users': v})
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

col1, col2 = st.columns([3, 1])
with col1:
    st.markdown('<div class="title-gradient">MetricsAI</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">AI-powered analytics for product & marketing metrics. Upload your data — get insights instantly.</div>', unsafe_allow_html=True)
with col2:
    st.markdown('<div style="text-align: right; padding-top: 1rem;"><span class="badge">Beta</span></div>', unsafe_allow_html=True)
st.markdown('<hr>', unsafe_allow_html=True)

st.markdown('<div class="glass-card">', unsafe_allow_html=True)
uploaded_file = st.file_uploader('📁 Загрузите CSV с данными (колонки: date, user_id, revenue, channel, event_type, marketing_cost)', type=['csv'])
with st.expander('💡 Нет данных? Скачать тестовый CSV'):
    sample_data = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=1000, freq='D').tolist(),
        'user_id': np.random.choice([f'user_{i}' for i in range(200)], 1000),
        'revenue': np.random.exponential(150, 1000).round(2),
        'channel': np.random.choice(['organic', 'instagram', 'google', 'facebook', 'email'], 1000),
        'event_type': np.random.choice(['impression', 'click', 'visit', 'add_to_cart', 'purchase'], 1000, p=[0.4, 0.25, 0.15, 0.1, 0.1]),
        'marketing_cost': np.random.choice([0, 0, 0, 50, 80, 120, 200], 1000)
    })
    st.download_button(label='⬇️ Скачать sample_data.csv', data=sample_data.to_csv(index=False).encode('utf-8'), file_name='sample_data.csv', mime='text/csv')
st.markdown('</div>', unsafe_allow_html=True)

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    date_col = next((c for c in df.columns if 'date' in c.lower()), None)
    if date_col and date_col != 'date':
        df = df.rename(columns={date_col: 'date'})
    user_col = next((c for c in df.columns if any(x in c.lower() for x in ['user', 'customer', 'client'])), None)
    if user_col and user_col != 'user_id':
        df = df.rename(columns={user_col: 'user_id'})
    revenue_col = next((c for c in df.columns if any(x in c.lower() for x in ['revenue', 'amount', 'sum', 'price', 'value'])), None)
    if revenue_col and revenue_col != 'revenue':
        df = df.rename(columns={revenue_col: 'revenue'})

    st.markdown('<br>', unsafe_allow_html=True)
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('### 📋 Предпросмотр данных')
    st.dataframe(df.head(10), use_container_width=True, hide_index=True)
    st.markdown(f"<span style='color: #94A3B8; font-size: 0.9rem;'>Всего строк: <b>{len(df):,}</b> | Колонок: <b>{len(df.columns)}</b></span>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    metrics = calculate_metrics(df)
    summary = f"Users: {metrics['total_users']}, Revenue: {metrics['total_revenue']:,.0f}, ARPU: {metrics['arpu']:,.2f}"
    save_upload(uploaded_file.name, len(df), summary)

    st.markdown('<br>', unsafe_allow_html=True)
    st.markdown('## 📊 Ключевые метрики')
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.markdown(f'<div class="metric-container"><div class="metric-value">{metrics["total_users"]:,}</div><div class="metric-label">Пользователей</div></div>', unsafe_allow_html=True)
    with m2:
        st.markdown(f'<div class="metric-container"><div class="metric-value">{metrics["total_revenue"]:,.0f} ₽</div><div class="metric-label">Выручка</div></div>', unsafe_allow_html=True)
    with m3:
        st.markdown(f'<div class="metric-container"><div class="metric-value">{metrics["arpu"]:,.0f} ₽</div><div class="metric-label">ARPU</div></div>', unsafe_allow_html=True)
    with m4:
        st.markdown(f'<div class="metric-container"><div class="metric-value">{metrics["ltv"]:,.0f} ₽</div><div class="metric-label">LTV (est.)</div></div>', unsafe_allow_html=True)
    with m5:
        ratio = metrics['ltv_cac_ratio']
        ratio_color = "#4ADE80" if ratio > 3 else "#FBBF24" if ratio > 1 else "#F87171"
        st.markdown(f'<div class="metric-container"><div class="metric-value" style="color: {ratio_color} !important; -webkit-text-fill-color: {ratio_color} !important;">{ratio:.1f}x</div><div class="metric-label">LTV / CAC</div></div>', unsafe_allow_html=True)

    st.markdown('<hr>', unsafe_allow_html=True)
    tab1, tab2, tab3, tab4 = st.tabs(['📈 Тренды', '🔻 Воронка', '👥 Когорты', '🤖 AI-инсайты'])

    with tab1:
        if metrics['monthly_trend'] is not None:
            col1, col2 = st.columns(2)
            with col1:
                fig = px.line(metrics['monthly_trend'], x='month', y='revenue', title='Динамика выручки', template='plotly_dark', color_discrete_sequence=['#8B5CF6'])
                fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#E2E8F0', title_font_size=16, title_font_color='#C084FC')
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                fig2 = px.bar(metrics['monthly_trend'], x='month', y='arpu', title='ARPU по месяцам', template='plotly_dark', color_discrete_sequence=['#3B82F6'])
                fig2.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#E2E8F0', title_font_size=16, title_font_color='#60A5FA')
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Добавьте колонку 'date'")

    with tab2:
        if metrics['funnel'] is not None:
            fig = px.funnel(metrics['funnel'], x='users', y='step', template='plotly_dark', color_discrete_sequence=['#8B5CF6', '#7C3AED', '#6D28D9', '#5B21B6', '#4C1D95'])
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#E2E8F0', title_font_size=16, title_font_color='#C084FC')
            st.plotly_chart(fig, use_container_width=True)
            if len(metrics['funnel']) > 1:
                st.markdown('### Конверсия между этапами')
                funnel_df = metrics['funnel'].copy()
                funnel_df['conversion'] = funnel_df['users'].pct_change() * 100
                funnel_df['conversion'] = funnel_df['conversion'].fillna(100)
                conv_cols = st.columns(len(funnel_df) - 1)
                for i, (_, row) in enumerate(funnel_df.iloc[1:].iterrows()):
                    with conv_cols[i]:
                        prev_step = funnel_df.iloc[i]['step']
                        st.markdown(f'<div class="metric-container" style="padding: 1rem;"><div class="metric-value" style="font-size: 1.5rem;">{row["conversion"]:.1f}%</div><div class="metric-label">{prev_step} → {row["step"]}</div></div>', unsafe_allow_html=True)
        else:
            st.info("Добавьте колонку 'event_type'")

    with tab3:
        if metrics['retention'] is not None:
            fig = px.imshow(metrics['retention'].values, labels=dict(x='Период (мес)', y='Когорта', color='Retention'),
                           x=[f'M{i}' for i in range(len(metrics['retention'].columns))], y=[str(c) for c in metrics['retention'].index],
                           template='plotly_dark', color_continuous_scale='Purples', aspect='auto')
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#E2E8F0', title_font_size=16, title_font_color='#C084FC')
            st.plotly_chart(fig, use_container_width=True)
            avg_retention = metrics['retention'].mean()
            st.markdown('### Средний Retention по периодам')
            fig2 = px.line(x=avg_retention.index, y=avg_retention.values, template='plotly_dark', color_discrete_sequence=['#22D3EE'])
            fig2.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#E2E8F0', xaxis_title='Период (мес)', yaxis_title='Retention Rate', title_font_color='#22D3EE')
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Добавьте 'date' и 'user_id'")

    with tab4:
        st.markdown('### 🤖 AI-анализ метрик')
        st.markdown('<div style="color: #94A3B8; margin-bottom: 1rem;">Нажмите кнопку ниже, чтобы получить персонализированные рекомендации от AI.</div>', unsafe_allow_html=True)
        if st.button('✨ Сгенерировать AI-инсайты', key='ai_btn'):
            with st.spinner('Анализирую метрики...'):
                client = get_ai_client()
                metrics_text = f"Total Users: {metrics['total_users']}\nTotal Revenue: {metrics['total_revenue']:,.2f}\nARPU: {metrics['arpu']:,.2f}\nAOV: {metrics['aov']:,.2f}\nLTV: {metrics['ltv']:,.2f}\nAvg CAC: {metrics['avg_cac']:,.2f}\nLTV/CAC: {metrics['ltv_cac_ratio']:.2f}"
                if metrics['cac_by_channel'] is not None:
                    metrics_text += '\nCAC by Channel:\n'
                    for _, row in metrics['cac_by_channel'].iterrows():
                        metrics_text += f"- {row['channel']}: CAC={row['cac']:,.2f}, Users={row['user_id']}\n"
                insights = generate_insights(metrics_text, client)
                st.markdown(f'<div class="ai-insight"><div class="ai-header">🧠 AI Product Analyst</div><div style="color: #E2E8F0; line-height: 1.7;">{insights.replace(chr(10), "<br>")}</div></div>', unsafe_allow_html=True)

    if 'channel' in df.columns:
        st.markdown('<hr>', unsafe_allow_html=True)
        st.markdown('## 🎯 Анализ по каналам')
        col1, col2 = st.columns(2)
        with col1:
            channel_revenue = df.groupby('channel')['revenue'].sum().reset_index().sort_values('revenue', ascending=True)
            fig = px.bar(channel_revenue, x='revenue', y='channel', orientation='h', template='plotly_dark', color_discrete_sequence=['#8B5CF6'])
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#E2E8F0')
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            if metrics['cac_by_channel'] is not None:
                fig = px.scatter(metrics['cac_by_channel'], x='user_id', y='cac', size='marketing_cost', color='channel', template='plotly_dark', title='CAC vs Пользователи')
                fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#E2E8F0')
                st.plotly_chart(fig, use_container_width=True)

st.markdown('<br><br>', unsafe_allow_html=True)
st.markdown('<hr>', unsafe_allow_html=True)
st.markdown('<div style="text-align: center; color: #64748B; font-size: 0.8rem;">MetricsAI © 2025 — Built for product & marketing analytics</div>', unsafe_allow_html=True)
