import streamlit as st
import requests
import os
import time
from datetime import datetime

# ==================== 配置区域 ====================
VERCEL_API_URL = "https://learn-self-eight.vercel.app/api"
# ================================================

st.set_page_config(
    page_title="Agent Skills Hub",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化 session state
if 'sync_status' not in st.session_state:
    st.session_state.sync_status = None
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = time.strftime("%Y-%m-%d %H:%M:%S")
if 'category' not in st.session_state:
    st.session_state.category = "全部"
if 'sort' not in st.session_state:
    st.session_state.sort = "综合评分"
if 'page' not in st.session_state:
    st.session_state.page = 1
if 'page_size' not in st.session_state:
    st.session_state.page_size = 10

# 标题
st.title("🤖 代理技能中心")
st.markdown("### 智能体能聚合与动态评分平台")
st.caption(f"🕐 最后刷新: {st.session_state.last_refresh}")

# 侧边栏
with st.sidebar:

    st.image(
        "https://img.icons8.com/fluency/96/null/artificial-intelligence.png",
        width=80
    )

    st.markdown("## 控制面板")

    # ==================== 同步状态 ====================
    st.markdown("### 🔄 同步状态")

    try:

        status_response = requests.get(
            f"{VERCEL_API_URL}/sync/progress",
            timeout=5
        )

        if status_response.status_code == 200:

            status_data = status_response.json()

            is_syncing = status_data.get("is_syncing", False)
            last_sync = status_data.get("last_sync", None)
            progress = status_data.get("progress", {})

            if is_syncing:

                st.warning("🟡 同步中...")

                if progress:
                    percentage = progress.get("percentage", 0)
                    total = progress.get("total_requests", 0)
                    max_req = progress.get("max_requests", 5000)

                    st.progress(percentage / 100)
                    st.caption(
                        f"📊 API请求: {total}/{max_req} ({percentage}%)"
                    )

            else:
                st.success("🟢 空闲")

            if last_sync:

                try:
                    if "T" in last_sync:
                        sync_time = datetime.strptime(
                            last_sync[:19],
                            "%Y-%m-%dT%H:%M:%S"
                        )

                        st.info(
                            f"📅 上次同步: {sync_time.strftime('%Y-%m-%d %H:%M')}"
                        )
                    else:
                        st.info(f"📅 上次同步: {last_sync}")

                except:
                    st.info(f"📅 上次同步: {last_sync}")

        else:
            st.warning("⚪ 无法获取状态")

    except Exception:
        st.warning("⚪ 状态未知")

    st.divider()

    # ==================== 手动同步 ====================
    if st.button("🔄 立即同步数据", type="primary", use_container_width=True):

        with st.spinner("正在同步数据..."):

            try:

                response = requests.post(
                    f"{VERCEL_API_URL}/sync",
                    timeout=15
                )

                if response.status_code == 200:

                    result = response.json()

                    if result.get("status") == "busy":
                        st.warning("⏳ 同步正在进行中")

                    elif result.get("error"):
                        st.error(result["error"])

                    else:

                        st.success("✅ 同步任务已启动！")

                        st.session_state.last_refresh = time.strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )

                        time.sleep(2)
                        st.rerun()

                else:
                    st.error(f"❌ API 返回错误: {response.status_code}")

            except Exception as e:
                st.error(f"❌ 发生错误: {str(e)}")

    st.divider()

    # ==================== 筛选 ====================
    st.markdown("### 📊 筛选条件")

    categories = ["全部", "Agent", "Tool", "Framework", "Demo", "Other"]

    category = st.selectbox(
        "分类",
        categories,
        index=categories.index(st.session_state.category)
        if st.session_state.category in categories else 0
    )

    st.session_state.category = category

    sort_options = ["综合评分", "Stars", "Forks", "最近更新"]

    sort = st.selectbox(
        "排序",
        sort_options,
        index=sort_options.index(st.session_state.sort)
        if st.session_state.sort in sort_options else 0
    )

    st.session_state.sort = sort

    page_size = st.select_slider(
        "每页显示",
        options=[5, 10, 20, 50],
        value=st.session_state.page_size
    )

    st.session_state.page_size = page_size

    st.divider()

    if st.button("🔄 重置筛选", use_container_width=True):

        st.session_state.category = "全部"
        st.session_state.sort = "综合评分"
        st.session_state.page = 1
        st.session_state.page_size = 10

        st.rerun()

# ==================== 主区域 ====================

col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    st.markdown(f"### 📚 技能库（第 {st.session_state.page} 页）")

with col3:
    if st.button("🔄 刷新数据", use_container_width=True):
        st.rerun()

# ==================== 请求参数 ====================

params = {
    "page": st.session_state.page,
    "size": st.session_state.page_size
}

sort_map = {
    "综合评分": "score",
    "Stars": "stars",
    "Forks": "forks",
    "最近更新": "time"
}

params["sort"] = sort_map.get(st.session_state.sort, "score")

if st.session_state.category != "全部":
    params["category"] = st.session_state.category

total_pages = 1

# ==================== 获取技能数据 ====================

try:

    with st.spinner("🚀 加载技能数据..."):

        response = requests.get(
            f"{VERCEL_API_URL}/skills",
            params=params,
            timeout=15
        )

    if response.status_code == 200:

        data = response.json()

        total = data.get("total", 0)
        items = data.get("items", [])

        total_pages = (
            (total + st.session_state.page_size - 1)
            // st.session_state.page_size
            if total > 0 else 1
        )

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("📊 总技能数", f"{total:,}")

        with col2:
            st.metric("📋 当前显示", len(items))

        with col3:
            st.metric("📄 总页数", total_pages)

        with col4:
            st.metric("📍 当前页码", st.session_state.page)

        st.divider()

        if not items:

            st.info("💡 暂无数据，请点击左侧「立即同步」按钮")

        else:

            for idx, skill in enumerate(items, 1):

                with st.container():

                    col1, col2 = st.columns([3, 1])

                    with col1:
                        st.subheader(f"{idx}. {skill.get('name', 'Unknown')}")
                        st.caption(
                            f"🏷️ 分类: {skill.get('category', 'N/A')}"
                        )

                    with col2:
                        score = skill.get("score", 0)
                        st.metric("综合评分", f"{score:.1f}")

                    description = skill.get("description", "")

                    if description:
                        st.write(description[:200])
                    else:
                        st.write("*暂无描述*")

                    url = skill.get("url")

                    if url:
                        st.markdown(f"🔗 [GitHub仓库]({url})")

                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.markdown(
                            f"⭐ Stars: {skill.get('stars',0):,}"
                        )

                    with col2:
                        st.markdown(
                            f"🍴 Forks: {skill.get('forks',0):,}"
                        )

                    with col3:
                        st.markdown(
                            f"💬 Issues: {skill.get('open_issues',0):,}"
                        )

                    last_commit = skill.get("last_commit")

                    if last_commit:

                        try:

                            if "T" in last_commit:
                                commit_time = datetime.strptime(
                                    last_commit[:19],
                                    "%Y-%m-%dT%H:%M:%S"
                                )

                                last_commit = commit_time.strftime(
                                    "%Y-%m-%d"
                                )

                        except:
                            pass

                        st.caption(f"🕐 最后提交: {last_commit}")

                    st.divider()

    else:

        st.error(
            f"❌ API 请求失败 (HTTP {response.status_code})"
        )

except Exception as e:

    st.error(f"❌ 发生错误: {str(e)}")

# ==================== 分页 ====================

if total_pages > 1:

    col1, col2, col3, col4, col5 = st.columns([1,2,1,2,1])

    with col2:

        if st.button(
            "◀ 上一页",
            disabled=(st.session_state.page <= 1),
            use_container_width=True
        ):

            st.session_state.page -= 1
            st.rerun()

    with col3:

        st.markdown(
            f"<div style='text-align:center'>{st.session_state.page}/{total_pages}</div>",
            unsafe_allow_html=True
        )

    with col4:

        if st.button(
            "下一页 ▶",
            disabled=(st.session_state.page >= total_pages),
            use_container_width=True
        ):

            st.session_state.page += 1
            st.rerun()

# ==================== Footer ====================

st.markdown("---")

col1, col2, col3 = st.columns(3)

with col1:
    st.caption("🤖 Agent Skills Hub")

with col2:
    st.caption(time.strftime("%Y-%m-%d %H:%M:%S"))

with col3:
    st.caption("📊 数据来源: GitHub API")