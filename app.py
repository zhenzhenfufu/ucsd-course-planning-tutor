import streamlit as st
import pandas as pd
import json
from pyvis.network import Network
from ai_advisor import get_ai_advice

st.set_page_config(layout="wide", page_title="UCSD Course Architect")

# --- 数据加载 (带错误检查) ---
@st.cache_data
def load_data():
    try:
        with open('dsc_courses.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        df = pd.DataFrame(data)
        # 核心修复：确保 ID 存在并清理
        if 'id' in df.columns:
            df['id_clean'] = df['id'].astype(str).str.replace('/R', '', regex=False)
            return df
        else:
            st.error("JSON must contain an 'id' field.")
            return None
    except Exception as e:
        st.error(f"File error: {e}")
        return None

df = load_data()

if df is not None:
    col_viz, col_ai = st.columns([0.7, 0.3], gap="large")

    with col_viz:
        st.title("🔱 UCSD Path Finder")
        tab1, tab2 = st.tabs(["📊 Catalog", "🕸️ Map"])
        
        with tab1:
            search = st.text_input("🔍 Search")
            mask = df.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)
            # 2026 语法：width="stretch"
            st.dataframe(df[mask][['id', 'name', 'description']], hide_index=True, width="stretch")

        with tab2:
            net = Network(height="600px", width="100%", bgcolor="#ffffff", directed=True)
            core = ["DSC 10", "DSC 20", "DSC 30", "DSC 40A", "DSC 40B", "DSC 80"]
            for c in core:
                match = df[df['id_clean'] == c]
                desc = match['description'].values[0] if not match.empty else ""
                net.add_node(c, label=c, title=desc, color="#184073")
            net.add_edge("DSC 10", "DSC 20")
            net.add_edge("DSC 20", "DSC 30")
            
            # --- 之前的代码: net.save_graph("course_map.html") ---
        
        # 2026 标准修复方案：
        net.save_graph("course_map.html")
        with open("course_map.html", 'r', encoding='utf-8') as f:
            html_content = f.read()
            
        # 使用更为通用的 st.components.v1.html 的 2026 替代方案
        # 或者直接使用 st.html (Streamlit 1.50+ 新增)
        try:
            st.html(html_content) 
        except Exception:
            # 如果 st.html 不行，用这个绝对兼容的 iframe 写法
            import streamlit.components.v1 as components
            components.html(html_content, height=660, scrolling=True)

    with col_ai:
        st.subheader("🤖 AI Advisor")
        if "messages" not in st.session_state: st.session_state.messages = []
        
        container = st.container(height=600)
        for m in st.session_state.messages: 
            container.chat_message(m["role"]).write(m["content"])

        if prompt := st.chat_input("Ask a question..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            container.chat_message("user").write(prompt)
            with container.chat_message("assistant"):
                ans = get_ai_advice(prompt)
                st.markdown(ans)
            st.session_state.messages.append({"role": "assistant", "content": ans})