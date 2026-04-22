import streamlit as st
import pandas as pd
import json
import os
from pyvis.network import Network
from ai_advisor import get_ai_advice

# --- 1. Config ---
st.set_page_config(layout="wide", page_title="UCSD Course Architect", page_icon="🔱")

# --- 2. Data ---
@st.cache_data
def load_data():
    with open('dsc_courses.json', 'r', encoding='utf-8') as f:
        df = pd.DataFrame(json.load(f))
    df['id_clean'] = df['id'].str.replace('/R', '', regex=False)
    return df

df = load_data()

# --- 3. UI ---
col_viz, col_ai = st.columns([0.7, 0.3], gap="large")

with col_viz:
    st.title("🔱 UCSD Academic Path Finder")
    
    tab1, tab2 = st.tabs(["📊 Catalog", "🕸️ Map"])
    
    with tab1:
        search = st.text_input("🔍 Search courses...")
        filtered = df[df['id'].str.contains(search, case=False) | df['description'].str.contains(search, case=False)]
        # 修正：width="stretch" 代替 use_container_width
        st.dataframe(filtered[['id', 'name', 'description']], hide_index=True, width="stretch")

    with tab2:
        net = Network(height="600px", width="100%", bgcolor="#ffffff", directed=True)
        core = ["DSC 10", "DSC 20", "DSC 30", "DSC 40A", "DSC 40B", "DSC 80"]
        for c in core:
            match = df[df['id_clean'] == c]
            desc = match['description'].values[0] if not match.empty else ""
            net.add_node(c, label=c, title=desc, color="#184073")
        
        edges = [("DSC 10", "DSC 20"), ("DSC 20", "DSC 30"), ("DSC 40A", "DSC 40B")]
        for e in edges: net.add_edge(e[0], e[1])

        net.save_graph("course_map.html")
        with open("course_map.html", 'r', encoding='utf-8') as f:
            # 修正：st.iframe 代替 components.html
            st.iframe(srcdoc=f.read(), height=650)

with col_ai:
    st.subheader("🤖 AI Advisor")
    if "messages" not in st.session_state: st.session_state.messages = []
    
    container = st.container(height=600)
    for m in st.session_state.messages: container.chat_message(m["role"]).write(m["content"])

    if prompt := st.chat_input("Ask a question..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        container.chat_message("user").write(prompt)
        with container.chat_message("assistant"):
            ans = get_ai_advice(prompt)
            st.markdown(ans)
        st.session_state.messages.append({"role": "assistant", "content": ans})