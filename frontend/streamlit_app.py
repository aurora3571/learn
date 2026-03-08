import streamlit as st
import requests
import os
import time
from datetime import datetime
import json

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
if 'current_task_id' not in st.session_state:
    st.session_state.current_task_id = None
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = False

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
        # 获取队列信息
        queue_response = requests.get(f"{VERCEL_API_URL}/sync/queue", timeout=5)
        
        if queue_response.status_code == 200:
            queue_data = queue_response.json()
            
            is_processing = queue_data.get("is_processing", False)
            queue_size = queue_data.get("queue_size", 0)
            current_task = queue_data.get("current_task")
            
            # 显示状态
            col_status, col_queue = st.columns(2)
            
            with col_status:
                if is_processing:
                    st.warning("🟡 同步中")
                elif queue_size > 0:
                    st.info("🟠 队列中")
                else:
                    st.success("🟢 空闲")
            
            with col_queue:
                st.metric("队列长度", queue_size)
            
            # 如果正在同步，显示当前任务进度
            if is_processing and current_task:
                st.progress(current_task.get("progress", 0) / 100)
                st.caption(f"📊 {current_task.get('message', '同步中...')}")
                
                # 显示API请求进度
                api_stats = current_task.get('api_stats', {})
                if api_stats:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("API请求", f"{api_stats.get('total_requests', 0)}/{api_stats.get('max_requests', 5000)}")
                    with col2:
                        st.metric("速度", f"{api_stats.get('speed', 0)}/秒")
            
            # 显示上次同步时间
            status_response = requests.get(f"{VERCEL_API_URL}/sync/status", timeout=5)
            if status_response.status_code == 200:
                status_data = status_response.json()
                last_sync = status_data.get("last_sync_time")
                
                if last_sync:
                    try:
                        if "T" in last_sync:
                            sync_time = datetime.strptime(last_sync[:19], "%Y-%m-%dT%H:%M:%S")
                            st.info(f"📅 上次同步: {sync_time.strftime('%Y-%m-%d %H:%M')}")
                    except:
                        st.info(f"📅 上次同步: {last_sync}")
            
            # 自动刷新选项
            if is_processing or queue_size > 0:
                st.checkbox("🔄 自动刷新进度", key="auto_refresh", value=True)
                
                if st.session_state.auto_refresh:
                    time.sleep(2)
                    st.rerun()

        else:
            st.warning("⚪ 无法获取状态")

    except Exception as e:
        st.warning(f"⚪ 状态未知")

    st.divider()

    # ==================== 手动同步 ====================
    
    # 确定按钮状态和文本
    button_disabled = is_processing
    button_text = "⏳ 同步进行中..." if is_processing else "🔄 立即同步数据"
    
    if st.button(button_text, type="primary", use_container_width=True, disabled=button_disabled):
        with st.spinner("正在创建同步任务..."):
            try:
                response = requests.post(f"{VERCEL_API_URL}/sync", timeout=30)

                if response.status_code == 200:
                    result = response.json()
                    
                    if result.get("status") == "task_created":
                        task_id = result.get("task_id")
                        st.session_state.current_task_id = task_id
                        
                        queue_position = result.get("queue_position")
                        queue_size = result.get("queue_size")
                        
                        if queue_position and queue_position > 1:
                            st.info(f"⏳ 任务已加入队列，位置: {queue_position}/{queue_size}")
                        else:
                            st.success("✅ 同步任务已创建，正在执行...")
                        
                        # 显示任务信息
                        with st.expander("查看任务详情"):
                            st.json({
                                "task_id": task_id,
                                "queue_position": queue_position,
                                "queue_size": queue_size,
                                "is_processing": result.get("is_processing")
                            })
                        
                        # 等待一下然后刷新
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.warning(result.get("message", "未知响应"))

                else:
                    st.error(f"❌ API 返回错误: {response.status_code}")

            except requests.exceptions.Timeout:
                st.error("⏰ 请求超时，请稍后重试")
            except Exception as e:
                st.error(f"❌ 发生错误: {str(e)}")

    # 如果有当前任务，显示任务追踪
    if st.session_state.current_task_id and is_processing:
        st.divider()
        st.markdown("### 📋 当前任务")
        
        try:
            task_response = requests.get(f"{VERCEL_API_URL}/sync/task/{st.session_state.current_task_id}", timeout=5)
            if task_response.status_code == 200:
                task_data = task_response.json()
                
                st.progress(task_data.get("progress", 0) / 100)
                st.caption(task_data.get("message", ""))
                
                if task_data.get("is_completed"):
                    st.success("✅ 任务完成")
                    if task_data.get("result"):
                        result = task_data.get("result")
                        st.info(f"📊 新增: {result.get('inserted', 0)}, 更新: {result.get('updated', 0)}")
                    
                    # 清除任务ID
                    if st.button("清除任务记录"):
                        st.session_state.current_task_id = None
                        st.rerun()
                        
                elif task_data.get("is_failed"):
                    st.error(f"❌ 任务失败: {task_data.get('error')}")
                    
        except Exception as e:
            st.error(f"获取任务状态失败: {e}")

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
    
    # ==================== 任务队列 ====================
    with st.expander("📋 任务队列"):
        try:
            tasks_response = requests.get(f"{VERCEL_API_URL}/sync/tasks?limit=5", timeout=5)
            if tasks_response.status_code == 200:
                tasks_data = tasks_response.json()
                tasks = tasks_data.get("tasks", [])
                
                if tasks:
                    for task in tasks:
                        status = task.get("status")
                        if status == "completed":
                            st.success(f"✅ {task.get('created_at', '')[:16]}")
                        elif status == "running":
                            st.warning(f"🔄 {task.get('created_at', '')[:16]} - {task.get('progress', 0)}%")
                        elif status == "failed":
                            st.error(f"❌ {task.get('created_at', '')[:16]}")
                        elif status in ["queued", "waiting"]:
                            st.info(f"⏳ {task.get('created_at', '')[:16]} (位置: {task.get('queue_position', '?')})")
                else:
                    st.caption("暂无任务记录")
            else:
                st.caption("无法获取任务列表")
        except Exception as e:
            st.caption("获取任务列表失败")
    
    # ==================== 调试工具 ====================
    with st.expander("🔧 调试工具"):
        if st.button("检查数据变化", use_container_width=True):
            try:
                debug_response = requests.get(f"{VERCEL_API_URL}/debug/sync-info", timeout=5)
                
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
        response = requests.get(f"{VERCEL_API_URL}/skills", params=params, timeout=15)

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
                        st.caption(f"🏷️ 分类: {skill.get('category', 'N/A')}")

                    with col2:
                        score = skill.get("score", 0)
                        st.metric("综合评分", f"{score:.1f}")

                    description = skill.get("description", "")
                    if description:
                        st.write(description[:200] + ('...' if len(description) > 200 else ''))
                    else:
                        st.write("*暂无描述*")

                    url = skill.get("url")
                    if url:
                        st.markdown(f"🔗 [GitHub仓库]({url})")

                    author = skill.get('author', 'Unknown')
                    followers = skill.get('author_followers', 0)
                    st.caption(f"👤 作者: {author} | 关注者: {followers:,}")

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