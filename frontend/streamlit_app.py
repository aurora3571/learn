import streamlit as st
import requests
import os
import time
from datetime import datetime

# ==================== 配置区域 ====================
# 指向 Vercel 上部署的 API
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
    st.image("https://img.icons8.com/fluency/96/null/artificial-intelligence.png", width=80)
    st.markdown("## 控制面板")
    
    # 同步状态显示
    st.markdown("### 🔄 同步状态")
    try:
        status_response = requests.get(f"{VERCEL_API_URL}/sync/status", timeout=5)
        if status_response.status_code == 200:
            status_data = status_response.json()
            is_syncing = status_data.get('is_syncing', False)
            last_sync = status_data.get('last_sync_time', '未知')
            max_items = status_data.get('max_items', 5000)
            
            if is_syncing:
                st.warning("🟡 同步中...")
                # 获取同步进度
                try:
                    progress_response = requests.get(f"{VERCEL_API_URL}/sync/progress", timeout=5)
                    if progress_response.status_code == 200:
                        progress_data = progress_response.json()
                        progress = progress_data.get('progress', {})
                        if progress:
                            percentage = progress.get('percentage', 0)
                            total = progress.get('total_requests', 0)
                            max_req = progress.get('max_requests', 5000)
                            st.progress(percentage / 100)
                            st.caption(f"📊 API请求: {total}/{max_req} ({percentage}%)")
                except:
                    pass
            else:
                st.success("🟢 空闲")
            
            if last_sync and last_sync != '未知':
                # 格式化时间显示
                try:
                    if 'T' in last_sync:
                        sync_time = datetime.strptime(last_sync[:19], "%Y-%m-%dT%H:%M:%S")
                        st.info(f"📅 上次同步: {sync_time.strftime('%Y-%m-%d %H:%M')}")
                    else:
                        st.info(f"📅 上次同步: {last_sync}")
                except:
                    st.info(f"📅 上次同步: {last_sync[:10]} {last_sync[11:16] if len(last_sync) > 10 else ''}")
        else:
            st.warning("⚪ 无法获取状态")
    except Exception as e:
        st.warning(f"⚪ 状态未知")
    
    st.divider()
    
    # 同步按钮
    if st.button("🔄 立即同步数据", type="primary", use_container_width=True):
        with st.spinner("正在同步数据..."):
            try:
                response = requests.post(f"{VERCEL_API_URL}/sync", timeout=5)
                if response.status_code == 200:
                    result = response.json()
                    if result.get('status') == 'busy':
                        st.warning("⏳ 同步正在进行中")
                    else:
                        st.success("✅ 同步任务已启动！")
                        st.info(f"⏱️ 目标数量: {result.get('total_fetched', 'N/A')} 条")
                        st.session_state.last_refresh = time.strftime("%Y-%m-%d %H:%M:%S")
                        time.sleep(2)
                        st.rerun()
                else:
                    st.error(f"❌ API 返回错误: {response.status_code}")
            except Exception as e:
                st.error(f"❌ 发生错误: {str(e)}")
    
    st.divider()
    
    # 筛选条件
    st.markdown("### 📊 筛选条件")
    
    # 分类筛选
    categories = ["全部", "Agent", "Tool", "Framework", "Demo", "Other"]
    category = st.selectbox(
        "分类",
        categories,
        index=categories.index(st.session_state.category) if st.session_state.category in categories else 0
    )
    st.session_state.category = category
    
    # 排序方式
    sort_options = ["综合评分", "Stars", "Forks", "最近更新"]
    sort = st.selectbox(
        "排序",
        sort_options,
        index=sort_options.index(st.session_state.sort) if st.session_state.sort in sort_options else 0
    )
    st.session_state.sort = sort
    
    # 每页数量
    page_size = st.select_slider(
        "每页显示",
        options=[5, 10, 20, 50],
        value=st.session_state.page_size
    )
    st.session_state.page_size = page_size
    
    st.divider()
    
    # 快捷操作
    if st.button("🔄 重置筛选", use_container_width=True):
        st.session_state.category = "全部"
        st.session_state.sort = "综合评分"
        st.session_state.page = 1
        st.session_state.page_size = 10
        st.rerun()
    
    st.divider()
    
    # 页脚
    st.markdown("""
    ---
    **📌 说明**
    - 数据来源：GitHub
    - 自动同步：每小时
    - 评分算法：综合多项指标
    - 最大数量：5000条
    - 请求限制：达到5000次自动停止
    """)

# 主内容区域
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    st.markdown(f"### 📚 技能库（第 {st.session_state.page} 页）")

with col3:
    if st.button("🔄 刷新数据", use_container_width=True):
        st.rerun()

# 获取数据
params = {
    "page": st.session_state.page,
    "size": st.session_state.page_size,
}

# 映射排序参数
sort_map = {
    "综合评分": "score",
    "Stars": "stars",
    "Forks": "forks",
    "最近更新": "time"
}
params["sort"] = sort_map.get(st.session_state.sort, "score")

if st.session_state.category != "全部":
    params["category"] = st.session_state.category

try:
    with st.spinner("🚀 加载技能数据..."):
        response = requests.get(
            f"{VERCEL_API_URL}/skills",
            params=params,
            timeout=15
        )

    if response.status_code == 200:
        data = response.json()
        total = data.get('total', 0)
        items = data.get('items', [])
        
        # 显示统计信息
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📊 总技能数", f"{total:,}")
        with col2:
            st.metric("📋 当前显示", len(items))
        with col3:
            total_pages = (total + st.session_state.page_size - 1) // st.session_state.page_size if total > 0 else 1
            st.metric("📄 总页数", total_pages)
        with col4:
            st.metric("📍 当前页码", st.session_state.page)
        
        st.divider()
        
        if not items:
            st.info("💡 暂无数据，请点击左侧「立即同步」按钮获取 GitHub 数据")
            
            # 显示示例说明
            with st.expander("📖 使用说明"):
                st.markdown("""
                **首次使用步骤：**
                1. 点击左侧「立即同步数据」按钮
                2. 等待同步完成（约1-2分钟）
                3. 刷新页面查看数据
                
                **数据说明：**
                - 每次同步最多获取5000条数据
                - 自动同步每小时执行一次
                - 评分基于多项指标计算
                - API请求达到5000次自动停止
                """)
        else:
            # 以卡片形式展示，使用Streamlit原生组件
            for idx, skill in enumerate(items, 1):
                with st.container():
                    # 使用列布局创建卡片效果
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.subheader(f"{idx}. {skill.get('name', 'Unknown')}")
                        st.caption(f"🏷️ 分类: {skill.get('category', 'N/A')}")
                    
                    with col2:
                        score = skill.get('score', 0)
                        st.metric("综合评分", f"{score:.1f}")
                    
                    # 描述
                    description = skill.get('description', '暂无描述')
                    if description:
                        st.write(description[:200] + ('...' if len(description) > 200 else ''))
                    else:
                        st.write("*暂无描述*")
                    
                    # GitHub链接
                    url = skill.get('url', '#')
                    if url and url != '#':
                        st.markdown(f"🔗 [GitHub仓库]({url})")
                    
                    # 作者信息
                    author = skill.get('author', 'Unknown')
                    followers = skill.get('author_followers', 0)
                    st.caption(f"👤 作者: {author} | 关注者: {followers:,}")
                    
                    # 使用列布局展示各个字段（以 key: value 形式）
                    col1, col2, col3, col4, col5 = st.columns(5)
                    
                    with col1:
                        stars = skill.get('stars', 0)
                        st.markdown(f"**Star:** {stars:,}")
                    
                    with col2:
                        forks = skill.get('forks', 0)
                        st.markdown(f"**Fork:** {forks:,}")
                    
                    with col3:
                        open_issues = skill.get('open_issues', 0)
                        st.markdown(f"**Open Issue:** {open_issues:,}")
                    
                    with col4:
                        closed_issues = skill.get('closed_issues', 0)
                        st.markdown(f"**Closed Issue:** {closed_issues:,}")
                    
                    with col5:
                        commits = skill.get('total_commits', 0)
                        st.markdown(f"**Commit:** {commits:,}")
                    
                    # 最后提交时间
                    last_commit = skill.get('last_commit', '')
                    if last_commit:
                        if isinstance(last_commit, str):
                            try:
                                if 'T' in last_commit:
                                    commit_date = datetime.strptime(last_commit[:19], "%Y-%m-%dT%H:%M:%S")
                                    last_commit_str = commit_date.strftime("%Y-%m-%d %H:%M")
                                else:
                                    last_commit_str = last_commit[:10]
                            except:
                                last_commit_str = last_commit[:10]
                        else:
                            last_commit_str = str(last_commit)[:10]
                        st.caption(f"🕐 最后提交: {last_commit_str}")
                    
                    st.divider()
        
        # 分页控件
        if total_pages > 1:
            col1, col2, col3, col4, col5 = st.columns([1, 2, 1, 2, 1])
            
            with col2:
                if st.button("◀ 上一页", disabled=(st.session_state.page <= 1), use_container_width=True):
                    st.session_state.page = max(1, st.session_state.page - 1)
                    st.rerun()
            
            with col3:
                st.markdown(f"<div style='text-align: center; padding: 10px; background: #f0f2f6; border-radius: 10px;'>{st.session_state.page} / {total_pages}</div>", unsafe_allow_html=True)
            
            with col4:
                if st.button("下一页 ▶", disabled=(st.session_state.page >= total_pages), use_container_width=True):
                    st.session_state.page = min(total_pages, st.session_state.page + 1)
                    st.rerun()
    
    else:
        st.error(f"❌ API 请求失败 (HTTP {response.status_code})")
        with st.expander("查看错误详情"):
            st.code(response.text)

except requests.exceptions.Timeout:
    st.error("⏰ 请求超时，请稍后重试")
except requests.exceptions.ConnectionError:
    st.error("🔌 无法连接到 API 服务器")
except Exception as e:
    st.error(f"❌ 发生未知错误: {str(e)}")
    with st.expander("查看错误详情"):
        st.code(str(e))

# 底部信息
st.markdown("---")
col1, col2, col3 = st.columns(3)
with col1:
    st.caption("🤖 代理技能中心 | Agent Skills Hub")
with col2:
    st.caption(f"🕐 {time.strftime('%Y-%m-%d %H:%M:%S')}")
with col3:
    st.caption("📊 数据来源: GitHub API | 最大请求: 5000次")

# 调试信息（仅在本地开发时显示）
if os.getenv('STREAMLIT_DEBUG'):
    with st.expander("🔧 调试信息"):
        st.json({
            "api_url": VERCEL_API_URL,
            "session_state": {k: str(v) for k, v in st.session_state.items()},
            "params": params,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })