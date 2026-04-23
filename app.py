import streamlit as st
import pandas as pd
import json
import plotly.graph_objects as go
from pyvis.network import Network
import streamlit.components.v1 as components
from ai_advisor import get_ai_advice

st.set_page_config(layout="wide", page_title="UCSD DSC Course Planner", page_icon="🔱")

# --- UI Customization (English Only) ---
st.markdown("""
    <style>
    .main { background-color: #f9fbfd; }
    .stButton>button { width: 100%; border-radius: 6px; font-weight: 600; }
    .course-card { padding: 15px; border-radius: 10px; background: white; border: 1px solid #eee; }
    </style>
""", unsafe_allow_html=True)

# --- Data Loading ---
@st.cache_data
def load_data():
    with open('dsc_courses.json', 'r', encoding='utf-8') as f:
        return json.load(f)

courses_data = load_data()
df = pd.DataFrame(courses_data)

if "selected_courses" not in st.session_state:
    st.session_state.selected_courses = []

# Hardcoded relationship map (Prerequisites)
edges_db = [
    ("MATH 20C", "DSC 40A"), ("MATH 18", "DSC 40A"),
    ("DSC 10", "DSC 20"), ("DSC 10", "DSC 40A"), ("DSC 10", "DSC 80"),
    ("DSC 20", "DSC 30"), ("DSC 30", "DSC 40B"), ("DSC 40A", "DSC 40B"),
    ("DSC 40B", "DSC 100"), ("DSC 80", "DSC 100"), ("DSC 100", "DSC 102"),
    ("DSC 100", "DSC 104")
]

# --- Helper: Radar Chart ---
def plot_radar(stats, course_id):
    categories = list(stats.keys())
    values = list(stats.values())
    
    # Normalize GPA and Hours for visualization if needed, but here we show raw
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        fillcolor='rgba(24, 64, 115, 0.3)',
        line=dict(color='#184073')
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=False,
        title=f"{course_id} Metrics",
        margin=dict(l=30, r=30, t=30, b=30),
        height=300
    )
    return fig

# --- Layout: Three Columns ---
col_left, col_mid, col_right = st.columns([0.3, 0.4, 0.3], gap="large")

# --- LEFT: Course Catalog ---
with col_left:
    st.subheader("📖 Course Catalog")
    search = st.text_input("Search Code or Topic", placeholder="e.g. DSC 80")
    
    filtered_df = df[df['id'].str.contains(search, case=False)] if search else df
    
    for _, row in filtered_df.iterrows():
        with st.expander(f"**{row['id']}** - {row['units']} Units"):
            st.write(row['name'])
            if st.button(f"Add {row['id']}", key=f"add_{row['id']}"):
                if row['id'] not in st.session_state.selected_courses:
                    st.session_state.selected_courses.append(row['id'])
                    st.rerun()

# --- MIDDLE: Planner & Visualization ---
with col_mid:
    st.subheader("📅 Academic Workspace")
    
    if st.session_state.selected_courses:
        # Display selection table
        plan_df = df[df['id'].isin(st.session_state.selected_courses)]
        st.dataframe(plan_df[['id', 'name', 'units']], hide_index=True, use_container_width=True)
        st.metric("Total Planned Units", f"{plan_df['units'].sum()} Units")
        
        # 6-Dimension Analysis
        st.divider()
        st.subheader("📊 Course Analysis")
        focus = st.selectbox("Select course to analyze:", st.session_state.selected_courses)
        course_stats = df[df['id'] == focus]['stats'].values[0]
        st.plotly_chart(plot_radar(course_stats, focus), use_container_width=True)
        
        # Relationship Tree (Static Style)
        st.subheader("🔗 Dependency Path")
        net = Network(height="300px", width="100%", directed=True, bgcolor="#ffffff")
        
        relevant_edges = [e for e in edges_db if e[0] == focus or e[1] == focus]
        nodes = {focus}
        for s, d in relevant_edges: nodes.update([s, d])
            
        for n in nodes:
            is_focus = (n == focus)
            net.add_node(n, label=n, shape="box", 
                         color="#184073" if is_focus else "#f0f2f6",
                         font={'color': 'white' if is_focus else 'black'})
        for s, d in relevant_edges:
            net.add_edge(s, d, color="#cbd5e0")
        
        # CRITICAL: Disable all interactions for a "Static Image" feel
        net.set_options("""
        var options = {
          "interaction": { "dragNodes": false, "dragView": false, "zoomView": false },
          "physics": { "enabled": false }
        }
        """)
        net.save_graph("tree.html")
        components.html(open("tree.html", 'r').read(), height=320)
        
        if st.button("Clear Plan"):
            st.session_state.selected_courses = []
            st.rerun()
    else:
        st.info("Your study plan is empty. Add courses from the left.")

# --- RIGHT: AI Advisor ---
with col_right:
    st.subheader("🤖 AI Degree Advisor")
    if "messages" not in st.session_state: st.session_state.messages = []
    
    chat_container = st.container(height=600)
    for m in st.session_state.messages:
        chat_container.chat_message(m["role"]).write(m["content"])
        
    if prompt := st.chat_input("Ask about course difficulty..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        chat_container.chat_message("user").write(prompt)
        
        with chat_container.chat_message("assistant"):
            # Provide context of selected courses to AI
            context = f"Current Plan: {st.session_state.selected_courses}. Question: {prompt}"
            ans = get_ai_advice(context)
            st.markdown(ans)
        st.session_state.messages.append({"role": "assistant", "content": ans})