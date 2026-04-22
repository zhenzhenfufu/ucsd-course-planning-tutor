import streamlit as st
import pandas as pd
import json
import os
from pyvis.network import Network
from ai_advisor import get_ai_advice

# --- 1. Page Configuration ---
st.set_page_config(layout="wide", page_title="UCSD Course Architect", page_icon="🔱")

# --- 2. Data Loading ---
@st.cache_data # 2026 性能优化：缓存数据，避免重复读取
def load_data():
    try:
        with open('dsc_courses.json', 'r', encoding='utf-8') as f:
            courses = json.load(f)
        df = pd.DataFrame(courses)
        
        # 清理 ID，去掉 /R 方便匹配
        df['id_clean'] = df['id'].str.replace('/R', '', regex=False)
        return df
    except Exception as e:
        st.error(f"Error loading JSON: {e}")
        return None

df = load_data()
if df is None:
    st.stop()

id_col, name_col, desc_col = 'id', 'name', 'description'
target_id = 'id_clean'

# --- 3. UI Layout ---
col_viz, col_ai = st.columns([0.7, 0.3], gap="large")

with col_viz:
    st.title("🔱 UCSD Academic Path Finder")
    st.markdown("Interactive roadmap for Data Science majors.")
    
    tab1, tab2 = st.tabs(["📊 Course Catalog", "🕸️ Prerequisite Map"])
    
    with tab1:
        st.subheader("Interactive Explorer")
        search = st.text_input("🔍 Search by ID, Title, or Topic")
        
        mask = (df[id_col].str.contains(search, case=False) | 
                df[name_col].str.contains(search, case=False) |
                df[desc_col].str.contains(search, case=False))
        filtered_df = df[mask]
        
        # 2026 语法修正：使用 width='stretch' 代替 use_container_width
        st.dataframe(
            filtered_df[[id_col, name_col, desc_col]],
            column_config={
                id_col: st.column_config.TextColumn("Code", width="small"),
                name_col: st.column_config.TextColumn("Course Title", width="medium"),
                desc_col: st.column_config.TextColumn("Details", width="large"),
            },
            hide_index=True,
            width="stretch" 
        )

    with tab2:
        st.subheader("Visual Roadmap")
        st.caption("Nodes are interactive. Hover to see descriptions.")
        
        net = Network(height="600px", width="100%", bgcolor="#ffffff", font_color="#333", directed=True)
        
        core_nodes = ["DSC 10", "DSC 20", "DSC 30", "DSC 40A", "DSC 40B", "DSC 80", "DSC 100", "DSC 102"]
        
        for c in core_nodes:
            match = df[df[target_id] == c]
            node_desc = match[desc_col].values[0] if not match.empty else "No description available."
            net.add_node(c, label=c, title=node_desc, color="#184073", size=25)
        
        edges = [
            ("DSC 10", "DSC 20"), ("DSC 20", "DSC 30"), 
            ("DSC 30", "DSC 40B"), ("DSC 40A", "DSC 40B"),
            ("DSC 30", "DSC 80"), ("DSC 40B", "DSC 100"),
            ("DSC 80", "DSC 100"), ("DSC 100", "DSC 102")
        ]
        for e in edges:
            net.add_edge(e[0], e[1], color="#cbd5e0", width=2)

        # 2026 语法修正：使用 st.iframe 代替 components.html
        net.save_graph("course_map.html")
        with open("course_map.html", 'r', encoding='utf-8') as f:
            st.iframe(srcdoc=f.read(), height=650)

with col_ai:
    st.subheader("🤖 AI Advisor")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 固定聊天框高度
    chat_box = st.container(height=650)
    for m in st.session_state.messages:
        chat_box.chat_message(m["role"]).write(m["content"])

    if prompt := st.chat_input("Ask about your academic plan..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        chat_box.chat_message("user").write(prompt)
        
        with chat_box.chat_message("assistant"):
            with st.spinner("Analyzing curriculum..."):
                ans = get_ai_advice(prompt)
                st.markdown(ans)
        st.session_state.messages.append({"role": "assistant", "content": ans})