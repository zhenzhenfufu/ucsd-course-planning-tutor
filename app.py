import streamlit as st
from ai_advisor import get_ai_advice

# 1. 网页配置：加上小图标和侧边栏
st.set_page_config(page_title="UCSD Course AI", page_icon="🔱")

# 侧边栏：放一些酷酷的信息
with st.sidebar:
    st.image("https://ucsd.edu/common/templates/images/ucsd-logo.png", width=200)
    st.title("项目设置")
    st.info("当前数据源：UCSD DSC Catalog")
    if st.button("刷新课程数据"):
        st.write("正在重新抓取数据...")
        # 这里以后可以调用 scraper.py 的函数

# 2. 主界面
st.title("🔱 UCSD DSC 选课助手")
st.caption("基于 Gemini 2.5 Flash 驱动的智能课程规划工具")

# 使用对话气泡的形式展示（可选）
if "messages" not in st.session_state:
    st.session_state.messages = []

# 显示之前的对话记录
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 接收用户输入
if prompt := st.chat_input("询问关于 DSC 课程的问题..."):
    # 在聊天界面显示用户的问题
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 生成 AI 回答
    with st.chat_message("assistant"):
        with st.spinner("AI 正在思考..."):
            answer = get_ai_advice(prompt)
            st.markdown(answer)
    
    st.session_state.messages.append({"role": "assistant", "content": answer})