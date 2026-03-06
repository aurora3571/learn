import streamlit as st
import requests
import os

# 根据环境设置 API 基础 URL
if os.getenv("VERCEL_ENV") == "production":
    # 生产环境使用相对路径
    API_BASE = "/api"
else:
    # 本地开发环境
    API_BASE = "http://127.0.0.1:8000/api"

st.set_page_config(page_title="Agent Skills Hub", layout="wide")

st.title("🚀 Agent Skills 聚合导航与动态评分系统")

# ----------------------
# 同步按钮
# ----------------------

if st.button("🔄 同步 GitHub 数据"):
    with st.spinner("正在抓取 GitHub 数据..."):
        try:
            r = requests.post(f"{API_BASE}/sync", timeout=300)
            if r.status_code == 200:
                result = r.json()
                if "error" in result:
                    st.error(f"同步失败: {result['error']}")
                else:
                    st.success(f"同步完成！耗时: {result.get('elapsed_seconds', 0):.2f}秒")
            else:
                st.error(f"同步失败，状态码: {r.status_code}")
        except Exception as e:
            st.error(f"请求异常: {str(e)}")

st.divider()

# ----------------------
# 查询条件
# ----------------------

col1, col2, col3 = st.columns(3)

with col1:
    category = st.selectbox(
        "分类筛选",
        ["All", "Agent"]
    )

with col2:
    sort = st.selectbox(
        "排序方式",
        ["score", "stars", "forks", "time"]
    )

with col3:
    page = st.number_input(
        "页码",
        min_value=1,
        value=1
    )

# ----------------------
# API 请求
# ----------------------

params = {
    "page": page,
    "size": 10,
    "sort": sort
}

if category != "All":
    params["category"] = category

try:
    response = requests.get(
        f"{API_BASE}/skills",
        params=params,
        timeout=30
    )

    if response.status_code != 200:
        st.error(f"API 请求失败: {response.status_code}")
        st.stop()

    data = response.json()

    st.write(f"### 共 {data['total']} 个 Skills")

    st.divider()

    # ----------------------
    # Skills 卡片展示
    # ----------------------

    for skill in data["items"]:
        with st.container():
            col1, col2 = st.columns([4, 1])

            with col1:
                st.subheader(skill["name"])
                st.write(skill.get("description", "No description"))
                st.markdown(f"[🔗 GitHub 地址]({skill['url']})")

            with col2:
                st.metric("综合评分", skill.get("score", 0))

            col3, col4, col5 = st.columns(3)

            with col3:
                st.write(f"⭐ Stars: {skill.get('stars', 0)}")

            with col4:
                st.write(f"🍴 Forks: {skill.get('forks', 0)}")

            with col5:
                st.write(f"🏷 分类: {skill.get('category', 'Unknown')}")

            st.divider()
except Exception as e:
    st.error(f"获取数据失败: {str(e)}")