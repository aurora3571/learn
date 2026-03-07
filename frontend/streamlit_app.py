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
if 'last_sync_result' not in st.session_state:
    st.session_state.last_sync_result = None
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
        # 同时获取状态和进度
        status_response = requests.get(
            f"{VERCEL_API_URL}/sync/status",
            timeout=5
        )
        
        progress_response = requests.get(
            f"{VERCEL_API_URL}/sync/progress",
            timeout=5
        )

        if status_response.status_code == 200:

            status_data = status_response.json()
            progress_data = progress_response.json() if progress_response.status_code == 200 else {}

            is_syncing = status_data.get("is_syncing", False)
            last_sync = status_data.get("last_sync_time", None)
            max_items = status_data.get("max_items", 5000)
            
            progress = progress_data.get("progress", {}) if progress_data else {}

            # 创建两列布局显示状态
            col_status, col_count = st.columns(2)
            
            with col_status:
                if is_syncing:
                    st.warning("🟡 同步中")
                else:
                    st.success("🟢 空闲")
            
            with col_count:
                if progress:
                    st.metric(
                        "请求进度", 
                        f"{progress.get('total_requests', 0)}/{progress.get('max_requests', 5000)}"
                    )
            
            # 进度条
            if is_syncing and progress:
                percentage = progress.get('percentage', 0)
                st.progress(percentage / 100)
                
                # 显示剩余请求数
                remaining = progress.get('remaining', 0)
                st.caption(f"⏳ 剩余请求: {remaining}")
            
            # 显示上次同步结果
            if st.session_state.last_sync_result and not is_syncing:
                result = st.session_state.last_sync_result
                if result.get('inserted', 0) > 0 or result.get('updated', 0) > 0:
                    st.success(
                        f"📊 上次同步: +{result.get('inserted', 0)} 新, "
                        f"{result.get('updated', 0)} 更新"
                    )
            
            # 上次同步时间
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

    except Exception as e:
        st.warning(f"⚪ 状态未知")

    st.divider()

    # ==================== 手动同步 ====================
    if st.button("🔄 立即同步数据", type="primary", use_container_width=True):

        with st.spinner("正在同步数据..."):

            try:

                response = requests.post(
                    f"{VERCEL_API_URL}/sync",
                    timeout=30  # 增加超时时间
                )

                if response.status_code == 200:

                    result = response.json()

                    if result.get("status") == "busy":
                        st.warning("⏳ 同步正在进行中")

                    elif result.get("error"):
                        st.error(f"❌ 同步失败: {result['error']}")

                    else:
                        # 保存同步结果到 session state
                        st.session_state.last_sync_result = result
                        
                        # 显示同步结果
                        inserted = result.get('inserted', 0)
                        updated = result.get('updated', 0)
                        total = result.get('total_fetched', 0)
                        api_stats = result.get('api_stats', {})
                        
                        st.success(f"✅ 同步完成！")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.info(f"📊 新增: {inserted} 条")
                            st.info(f"🔄 更新: {updated} 条")
                        with col2:
                            if api_stats:
                                st.info(f"📡 API请求: {api_stats.get('total_requests', 0)}")
                                st.info(f"💾 总计: {total} 条")
                        
                        st.session_state.last_refresh = time.strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        
                        # 等待数据写入数据库
                        time.sleep(3)
                        st.rerun()

                else:
                    st.error(f"❌ API 返回错误: {response.status_code}")

            except requests.exceptions.Timeout:
                st.error("⏰ 请求超时，请稍后重试")
                
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

    # ==================== 快捷操作 ====================
    if st.button("🔄 重置筛选", use_container_width=True):

        st.session_state.category = "全部"
        st.session_state.sort = "综合评分"
        st.session_state.page = 1
        st.session_state.page_size = 10

        st.rerun()
    
    st.divider()
    
    # ==================== 调试工具 ====================
    with st.expander("🔧 调试工具"):
        if st.button("检查数据变化", use_container_width=True):
            try:
                # 获取当前数据统计
                debug_response = requests.get(
                    f"{VERCEL_API_URL}/debug/sync-info",
                    timeout=5
                )
                
                if debug_response.status_code == 200:
                    debug_data = debug_response.json()
                    db_info = debug_data.get('database', {})
                    
                    st.success("📊 当前数据统计")
                    st.json({
                        "总记录数": db_info.get('total_records', 0),
                        "分类统计": db_info.get('categories', []),
                        "最新技能": db_info.get('latest_skills', [])[:3]
                    })
                else:
                    st.error("无法获取调试信息")
                    
            except Exception as e:
                st.error(f"调试失败: {e}")

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

                    # 描述
                    description = skill.get("description", "")
                    if description:
                        st.write(description[:200] + ('...' if len(description) > 200 else ''))
                    else:
                        st.write("*暂无描述*")

                    # GitHub链接
                    url = skill.get("url")
                    if url:
                        st.markdown(f"🔗 [GitHub仓库]({url})")

                    # 作者信息
                    author = skill.get('author', 'Unknown')
                    followers = skill.get('author_followers', 0)
                    st.caption(f"👤 作者: {author} | 关注者: {followers:,}")

                    # 使用5列布局展示所有指标
                    col1, col2, col3, col4, col5 = st.columns(5)

                    with col1:
                        stars = skill.get('stars', 0)
                        st.markdown(f"**⭐ Stars:** {stars:,}")

                    with col2:
                        forks = skill.get('forks', 0)
                        st.markdown(f"**🍴 Forks:** {forks:,}")

                    with col3:
                        open_issues = skill.get('open_issues', 0)
                        st.markdown(f"**🐞 开放问题:** {open_issues:,}")

                    with col4:
                        closed_issues = skill.get('closed_issues', 0)
                        st.markdown(f"**✅ 已解决:** {closed_issues:,}")

                    with col5:
                        commits = skill.get('total_commits', 0)
                        st.markdown(f"**📝 提交次数:** {commits:,}")

                    # 最后提交时间
                    last_commit = skill.get("last_commit")
                    if last_commit:
                        try:
                            if isinstance(last_commit, str):
                                if "T" in last_commit:
                                    commit_time = datetime.strptime(
                                        last_commit[:19],
                                        "%Y-%m-%dT%H:%M:%S"
                                    )
                                    last_commit = commit_time.strftime("%Y-%m-%d %H:%M")
                                else:
                                    last_commit = last_commit[:10]
                        except:
                            pass
                        st.caption(f"🕐 最后提交: {last_commit}")

                    st.divider()

    else:
        st.error(f"❌ API 请求失败 (HTTP {response.status_code})")
        with st.expander("查看错误详情"):
            st.code(response.text)

except requests.exceptions.Timeout:
    st.error("⏰ 请求超时，请稍后重试")
except requests.exceptions.ConnectionError:
    st.error("🔌 无法连接到 API 服务器")
except Exception as e:
    st.error(f"❌ 发生错误: {str(e)}")
    with st.expander("查看错误详情"):
        st.code(str(e))

# ==================== 分页 ====================

if total_pages > 1:

    col1, col2, col3, col4, col5 = st.columns([1, 2, 1, 2, 1])

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
            f"<div style='text-align:center; padding:10px; background:#f0f2f6; border-radius:10px;'>{st.session_state.page}/{total_pages}</div>",
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
    st.caption("🤖 Agent Skills Hub | 最大请求: 5000次")

with col2:
    st.caption(f"🕐 {time.strftime('%Y-%m-%d %H:%M:%S')}")

with col3:
    st.caption("📊 数据来源: GitHub API")