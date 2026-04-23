import streamlit as st
import pandas as pd
import json
from pyvis.network import Network
import streamlit.components.v1 as components

st.set_page_config(layout="wide", page_title="UCSD DSC Planner", page_icon="🎓")

# --- 自定义 CSS 提升“触感” ---
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        transition: all 0.2s;
    }
    .stButton>button:hover {
        border-color: #184073;
        color: #184073;
        background-color: #f0f4f9;
    }
    div[data-testid="stExpander"] {
        border: none !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        margin-bottom: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# --- 数据加载 ---
@st.cache_data
def load_data():
    with open('dsc_courses.json', 'r', encoding='utf-8') as f:
        return json.load(f)

courses_json = load_data()
df = pd.DataFrame(courses_json)

if "selected_courses" not in st.session_state:
    st.session_state.selected_courses = []

# 扩展关系库：加入一些外部课程关系
edges_db = [
    ("MATH 20C", "DSC 40A"), ("MATH 18", "DSC 40A"),
    ("DSC 10", "DSC 20"), ("DSC 10", "DSC 40A"), ("DSC 10", "DSC 80"),
    ("DSC 20", "DSC 30"), ("DSC 30", "DSC 40B"), ("DSC 40A", "DSC 40B"),
    ("DSC 40B", "DSC 100"), ("DSC 80", "DSC 100"), ("DSC 100", "DSC 102"),
    ("DSC 100", "DSC 104"), ("DSC 80", "DSC 148")
]

# --- 三栏布局 ---
col_left, col_mid, col_right = st.columns([0.28, 0.44, 0.28], gap="medium")

# --- 左栏：目录 ---
with col_left:
    st.markdown("### 📚 课程目录")
    search = st.text_input("🔍 搜索...", placeholder="编号或关键字")
    
    filtered_df = df[df['id'].str.contains(search, case=False)] if search else df
    
    for _, row in filtered_df.iterrows():
        with st.expander(f"**{row['id']}** - {row['name']}"):
            st.write(f"学分: `{row['units']} Units`")
            st.caption(row['description'][:150] + "...")
            if st.button(f"➕ 添加至计划", key=f"add_{row['id']}"):
                if row['id'] not in st.session_state.selected_courses:
                    st.session_state.selected_courses.append(row['id'])
                    st.rerun()

# --- 中栏：计划表与关系树 ---
with col_mid:
    st.markdown("### 📅 我的选课工作台")
    
    if st.session_state.selected_courses:
        plan_df = df[df['id'].isin(st.session_state.selected_courses)]
        total_units = plan_df['units'].sum()
        
        # 展示排课表
        st.dataframe(
            plan_df[['id', 'name', 'units']], 
            hide_index=True, 
            use_container_width=True
        )
        st.markdown(f"**总学分统计: `{total_units}` Units**")
        
        if st.button("🗑️ 清空所有选课"):
            st.session_state.selected_courses = []
            st.rerun()
    else:
        st.info("左侧搜索并添加课程，开启你的排课之旅。")

    st.divider()
    
    # 关系树部分
    st.markdown("### 🌲 依赖链路图")
    # 如果选了课，默认聚焦第一门课
    focus_list = st.session_state.selected_courses if st.session_state.selected_courses else ["DSC 10"]
    focus = st.selectbox("聚焦分析：", focus_list)
    
    # 构建 Network，关闭缩放和拖拽的物理抖动，让它像静态图标
    net = Network(height="350px", width="100%", directed=True, bgcolor="#ffffff")
    
    # 查找关系 (包含外部课程)
    relevant_edges = [e for e in edges_db if e[0] == focus or e[1] == focus]
    nodes = {focus}
    for s, d in relevant_edges:
        nodes.add(s); nodes.add(d)
        
    for n in nodes:
        # 配色方案
        is_external = not n.startswith("DSC")
        if n == focus:
            color, font_color = "#184073", "white" # 聚焦色：深蓝
        elif is_external:
            color, font_color = "#E6B325", "black" # 外部课程：金色
        else:
            color, font_color = "#F0F2F6", "black" # 其他 DSC：浅灰
            
        net.add_node(n, label=n, color=color, font={'color': font_color}, 
                     shape="box", borderWidth=0, margin=10)

    for s, d in relevant_edges:
        net.add_edge(s, d, color="#D3D3D3", width=2)
    
    # 禁用物理模拟和缩放，使其保持静止
    net.toggle_physics(False)
    net.save_graph("tree.html")
    components.html(open("tree.html", 'r').read(), height=360)
    st.caption("注：🟡 金色代表外部先修课（如 MATH/CSE） | 🔵 深蓝为当前课程")

# --- 右栏：AI Advisor ---
with col_right:
    st.markdown("### 🤖 AI 指导")
    from ai_advisor import get_ai_advice
    
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    chat_box = st.container(height=550)
    for m in st.session_state.messages:
        chat_box.chat_message(m["role"]).write(m["content"])
        
    if prompt := st.chat_input("问问 AI 关于这些课的难度..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        chat_box.chat_message("user").write(prompt)
        
        with chat_box.chat_message("assistant"):
            # 自动注入选课背景
            context = f"学生当前计划选修: {st.session_state.selected_courses}。问题: {prompt}"
            res = get_ai_advice(context)
            st.markdown(res)
        st.session_state.messages.append({"role": "assistant", "content": res})