import streamlit as st
import requests
import os
import time

# ==================== 配置区域 ====================
# 指向 Vercel 上部署的 API（请替换为你的实际域名）
VERCEL_API_URL = "https://learn-self-eight.vercel.app/api"
# ================================================

st.set_page_config(
    page_title="Agent Skills Hub",
    page_icon="🚀",
    layout="wide"
)

st.title("🚀 Agent Skills 聚合导航与动态评分系统")
st.markdown(f"*API 后端部署在 Vercel，数据源：GitHub*")

# 初始化 session state
if 'sync_status' not in st.session_state:
    st.session_state.sync_status = None
if 'skills_data' not in st.session_state:
    st.session_state.skills_data = None
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = time.strftime("%Y-%m-%d %H:%M:%S")

# ----------------------
# 侧边栏：同步控制
# ----------------------
with st.sidebar:
    st.header("🔄 数据同步")
    
    # 显示最后刷新时间
    st.caption(f"最后更新: {st.session_state.last_refresh}")
    
    if st.button("立即同步 GitHub 数据", type="primary", use_container_width=True):
        with st.status("正在同步数据...", expanded=True) as status:
            try:
                st.write("📡 连接到 Vercel API...")
                
                # 调用 Vercel 上的同步接口
                response = requests.post(
                    f"{VERCEL_API_URL}/sync",
                    timeout=300  # 5分钟超时
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if "error" in result:
                        st.error(f"同步失败: {result['error']}")
                        st.session_state.sync_status = "error"
                    else:
                        st.success(f"✅ 同步成功！")
                        if "elapsed_seconds" in result:
                            st.info(f"⏱️ 耗时: {result['elapsed_seconds']:.2f} 秒")
                        st.session_state.sync_status = "success"
                        st.session_state.last_refresh = time.strftime("%Y-%m-%d %H:%M:%S")
                        
                        # 短暂延迟后刷新数据
                        time.sleep(1)
                        st.rerun()
                else:
                    st.error(f"API 返回错误: {response.status_code}")
                    with st.expander("查看错误详情"):
                        st.code(response.text)
                    st.session_state.sync_status = "error"
                    
            except requests.exceptions.Timeout:
                st.error("⏰ 同步超时，请稍后重试")
                st.session_state.sync_status = "error"
            except requests.exceptions.ConnectionError:
                st.error("🔌 无法连接到 Vercel API，请检查网络")
                st.session_state.sync_status = "error"
            except Exception as e:
                st.error(f"❌ 发生未知错误: {str(e)}")
                st.session_state.sync_status = "error"
    
    st.divider()
    
    # 显示当前连接状态
    st.caption(f"🌐 API 地址: `{VERCEL_API_URL}`")
    
    # 测试 API 连接
    try:
        test_response = requests.get(f"{VERCEL_API_URL}/skills?size=1", timeout=5)
        if test_response.status_code == 200:
            st.success("✅ API 连接正常")
        else:
            st.warning(f"⚠️ API 连接异常 (HTTP {test_response.status_code})")
    except requests.exceptions.ConnectionError:
        st.error("❌ 无法连接到 API 服务器")
    except Exception as e:
        st.error(f"❌ API 连接测试失败: {str(e)}")
    
    st.divider()
    
    # 快捷操作
    st.header("⚡ 快捷操作")
    if st.button("清空所有筛选", use_container_width=True):
        st.session_state.category = "All"
        st.session_state.sort = "score"
        st.session_state.page = 1
        st.rerun()

# ----------------------
# 主界面：查询条件
# ----------------------
col1, col2, col3, col4 = st.columns([2, 2, 1, 1])

with col1:
    # 使用 session state 保持筛选状态
    if 'category' not in st.session_state:
        st.session_state.category = "All"
    category = st.selectbox(
        "📂 分类筛选",
        ["All", "Agent"],
        index=0 if st.session_state.category == "All" else 1,
        key="category_select"
    )
    st.session_state.category = category

with col2:
    if 'sort' not in st.session_state:
        st.session_state.sort = "score"
    sort = st.selectbox(
        "📊 排序方式",
        ["score", "stars", "forks", "time"],
        index=["score", "stars", "forks", "time"].index(st.session_state.sort),
        format_func=lambda x: {
            "score": "综合评分 ↓",
            "stars": "Stars ↓",
            "forks": "Forks ↓",
            "time": "最近更新 ↓"
        }.get(x, x),
        key="sort_select"
    )
    st.session_state.sort = sort

with col3:
    if 'page_size' not in st.session_state:
        st.session_state.page_size = 10
    page_size = st.selectbox(
        "每页数量",
        [10, 20, 50],
        index=[10, 20, 50].index(st.session_state.page_size),
        key="page_size_select"
    )
    st.session_state.page_size = page_size

with col4:
    if 'page' not in st.session_state:
        st.session_state.page = 1
    page = st.number_input(
        "📄 页码",
        min_value=1,
        value=st.session_state.page,
        key="page_input"
    )
    st.session_state.page = page

# ----------------------
# 获取数据
# ----------------------
params = {
    "page": page,
    "size": page_size,
    "sort": sort
}

if category != "All":
    params["category"] = category

try:
    with st.spinner("正在加载数据..."):
        response = requests.get(
            f"{VERCEL_API_URL}/skills",
            params=params,
            timeout=10
        )

    if response.status_code == 200:
        data = response.json()
        
        # 显示统计信息
        total = data.get('total', 0)
        items = data.get('items', [])
        
        # 计算总页数
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        
        col_left, col_right = st.columns([3, 1])
        with col_left:
            st.markdown(f"### 📊 共找到 {total} 个技能项目")
        with col_right:
            st.markdown(f"第 {page} / {total_pages} 页")
        
        if not items:
            if total == 0:
                st.info("💡 暂无数据，请点击左侧「立即同步」按钮获取 GitHub 数据")
            else:
                st.warning("当前页无数据，请尝试其他页码")
        
        # ----------------------
        # 技能卡片展示
        # ----------------------
        for skill in items:
            with st.container():
                # 卡片头部：名称和评分
                col_left, col_right = st.columns([4, 1])
                
                with col_left:
                    st.subheader(f"📦 {skill.get('name', 'Unknown')}")
                    st.caption(f"🏷️ 分类: {skill.get('category', 'N/A')}")
                
                with col_right:
                    score = skill.get('score', 0)
                    st.metric(
                        "综合评分",
                        f"{score:.1f}" if score else "N/A",
                        delta=None
                    )
                
                # 卡片内容
                description = skill.get('description')
                if description:
                    st.write(description[:200] + "..." if len(description) > 200 else description)
                else:
                    st.write("*暂无描述*")
                
                # 链接
                url = skill.get('url', '#')
                if url != '#':
                    st.markdown(f"🔗 [GitHub 仓库]({url})")
                
                # 统计指标
                cols = st.columns(5)
                metrics = [
                    ("⭐ Stars", skill.get('stars', 0)),
                    ("🍴 Forks", skill.get('forks', 0)),
                    ("🐞 Open Issues", skill.get('open_issues', 0)),
                    ("✅ Closed Issues", skill.get('closed_issues', 0)),
                    ("👤 Author", skill.get('author', 'Unknown'))
                ]
                
                for col, (label, value) in zip(cols, metrics):
                    col.metric(label, value)
                
                # 最后一次提交时间
                last_commit = skill.get('last_commit')
                if last_commit:
                    # 格式化时间显示
                    if isinstance(last_commit, str):
                        date_str = last_commit[:10]  # YYYY-MM-DD
                    else:
                        date_str = str(last_commit)
                    st.caption(f"⏱️ 最后提交: {date_str}")
                
                st.divider()
    
    elif response.status_code == 500:
        st.error("🚨 API 内部错误，请查看 Vercel 日志")
        with st.expander("查看详细错误"):
            st.code(response.text)
    
    else:
        st.error(f"❌ API 请求失败 (HTTP {response.status_code})")
        with st.expander("查看响应详情"):
            st.code(response.text)
        
except requests.exceptions.Timeout:
    st.error("⏰ 请求超时，请稍后重试")
except requests.exceptions.ConnectionError:
    st.error("🔌 无法连接到 API 服务器")
except Exception as e:
    st.error(f"❌ 发生未知错误: {str(e)}")
    with st.expander("查看错误详情"):
        st.code(str(e))

# ----------------------
# 分页导航
# ----------------------
if total_pages > 1:
    st.markdown("---")
    cols = st.columns([1, 2, 1, 2, 1])
    
    with cols[1]:
        if st.button("◀ 上一页", disabled=(page <= 1), use_container_width=True):
            st.session_state.page = max(1, page - 1)
            st.rerun()
    
    with cols[3]:
        if st.button("下一页 ▶", disabled=(page >= total_pages), use_container_width=True):
            st.session_state.page = min(total_pages, page + 1)
            st.rerun()

# ----------------------
# 页脚
# ----------------------
st.sidebar.divider()
st.sidebar.caption(
    "### 🚀 Agent Skills Hub\n\n"
    "**后端**: FastAPI on Vercel\n"
    "**数据库**: Neon PostgreSQL\n"
    "**前端**: Streamlit (本地运行)\n\n"
    "---\n"
    "💡 使用说明:\n"
    "1. 点击「立即同步」获取数据\n"
    "2. 使用筛选条件查看技能\n"
    "3. 数据永久保存在云端"
)

# 调试信息（仅在开发环境显示）
if os.getenv('STREAMLIT_DEBUG'):
    with st.sidebar.expander("🔧 调试信息"):
        st.json({
            "api_url": VERCEL_API_URL,
            "session_state": dict(st.session_state),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })