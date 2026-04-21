import streamlit as st
import pandas as pd
import json
import os
from pyvis.network import Network
import streamlit.components.v1 as components
from ai_advisor import get_ai_advice

# --- 1. Page Configuration ---
st.set_page_config(layout="wide", page_title="UCSD Course Architect", page_icon="🔱")

# --- 2. Data Loading & Cleaning ---
try:
    with open('dsc_courses.json', 'r', encoding='utf-8') as f:
        courses = json.load(f)
    df = pd.DataFrame(courses)
    
    # 这里的键名必须和你的 JSON 完全对齐
    id_col = 'id'          # 对应 "DSC 10/R"
    name_col = 'name'      # 对应 "Principles of Data Science (4)"
    desc_col = 'description'
    
    # 清理 ID，去掉 /R 方便连线匹配
    df['id_clean'] = df[id_col].str.replace('/R', '', regex=False)
    target_id = 'id_clean'
    
except Exception as e:
    st.error(f"Error loading JSON: {e}. Please check your file format.")
    st.stop()

# --- 3. UI Layout ---
col_viz, col_ai = st.columns([0.7, 0.3], gap="large")

with col_viz:
    st.title("🔱 UCSD Academic Path Finder")
    st.markdown("Interactive roadmap for Data Science majors.")
    
    tab1, tab2 = st.tabs(["📊 Course Catalog", "🕸️ Prerequisite Map"])
    
    with tab1:
        st.subheader("Interactive Explorer")
        search = st.text_input("🔍 Search by ID, Title, or Topic")
        
        # 搜索逻辑
        mask = (df[id_col].str.contains(search, case=False) | 
                df[name_col].str.contains(search, case=False) |
                df[desc_col].str.contains(search, case=False))
        filtered_df = df[mask]
        
        st.dataframe(
            filtered_df[[id_col, name_col, desc_col]],
            column_config={
                id_col: st.column_config.TextColumn("Code", width="small"),
                name_col: st.column_config.TextColumn("Course Title", width="medium"),
                desc_col: st.column_config.TextColumn("Details", width="large"),
            },
            hide_index=True,
            use_container_width=True
        )

    with tab2:
        st.subheader("Visual Roadmap")
        st.caption("Nodes are interactive. Hover to see descriptions.")
        
        net = Network(height="600px", width="100%", bgcolor="#ffffff", font_color="#333", directed=True)
        
        # 定义核心拓扑路径
        core_nodes = ["DSC 10", "DSC 20", "DSC 30", "DSC 40A", "DSC 40B", "DSC 80", "DSC 100", "DSC 102"]
        
        for c in core_nodes:
            # 匹配详情
            match = df[df[target_id] == c]
            node_desc = match[desc_col].values[0] if not match.empty else "No description available."
            net.add_node(c, label=c, title=node_desc, color="#184073", size=25)
        
        # 定义课程依赖关系
        edges = [
            ("DSC 10", "DSC 20"), ("DSC 20", "DSC 30"), 
            ("DSC 30", "DSC 40B"), ("DSC 40A", "DSC 40B"),
            ("DSC 30", "DSC 80"), ("DSC 40B", "DSC 100"),
            ("DSC 80", "DSC 100"), ("DSC 100", "DSC 102")
        ]
        for e in edges:
            net.add_edge(e[0], e[1], color="#cbd5e0", width=2)

        # 保存并嵌入
        net.save_graph("course_map.html")
        with open("course_map.html", 'r', encoding='utf-8') as f:
            components.html(f.read(), height=650)

with col_ai:
    st.subheader("🤖 AI Advisor")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    chat_box = st.container(height=600)
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