import streamlit as st
import pandas as pd
import json
import os
from pyvis.network import Network
from ai_advisor import get_ai_advice

# --- 1. Page Configuration ---
st.set_page_config(layout="wide", page_title="UCSD Course Architect", page_icon="🔱")

# --- 2. Data Loading (Cached for 2026 Speed) ---
@st.cache_data
def load_catalog():
    with open('dsc_courses.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    df['id_clean'] = df['id'].str.replace('/R', '', regex=False)
    return df

df = load_catalog()

# --- 3. UI Layout ---
col_viz, col_ai = st.columns([0.7, 0.3], gap="large")

with col_viz:
    st.title("🔱 UCSD Academic Path Finder")
    st.markdown("Interactive roadmap for Data Science majors.")
    
    tab1, tab2 = st.tabs(["📊 Catalog", "🕸️ Prerequisite Map"])
    
    with tab1:
        search = st.text_input("🔍 Search courses (e.g., DSC 10, Machine Learning)")
        mask = (df['id'].str.contains(search, case=False) | 
                df['description'].str.contains(search, case=False))
        
        # 修正：2026 语法使用 width='stretch'
        st.dataframe(df[mask][['id', 'name', 'description']], hide_index=True, width='stretch')

    with tab2:
        st.subheader("Visual Roadmap")
        net = Network(height="600px", width="100%", bgcolor="#ffffff", directed=True)
        
        # 核心课程节点
        core = ["DSC 10", "DSC 20", "DSC 30", "DSC 40A", "DSC 40B", "DSC 80"]
        for c in core:
            match = df[df['id_clean'] == c]
            desc = match['description'].values[0] if not match.empty else ""
            net.add_node(c, label=c, title=desc, color="#184073")
        
        # 依赖线
        net.add_edge("DSC 10", "DSC 20")
        net.add_edge("DSC 20", "DSC 30")
        net.add_edge("DSC 40A", "DSC 40B")

        net.save_graph("course_map.html")
        with open("course_map.html", 'r', encoding='utf-8') as f:
            # 修正：2026 语法使用 st.iframe 代替 components.html
            st.iframe(srcdoc=f.read(), height=650)

with col_ai:
    st.subheader("🤖 AI Advisor")
    if "messages" not in st.session_state:
        st.session_state.messages = []

    chat_box = st.container(height=600)
    for m in st.session_state.messages:
        chat_box.chat_message(m["role"]).write(m["content"])

    if prompt := st.chat_input("Ask your advisor..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        chat_box.chat_message("user").write(prompt)
        
        with chat_box.chat_message("assistant"):
            with st.spinner("Consulting catalog..."):
                ans = get_ai_advice(prompt)
                st.markdown(ans)
        st.session_state.messages.append({"role": "assistant", "content": ans})