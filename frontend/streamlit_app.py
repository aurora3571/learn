import streamlit as st
import requests
import os
import time
from datetime import datetime
import pandas as pd

# ==================== 配置区域 ====================
# 指向 Vercel 上部署的 API（请替换为你的实际域名）
VERCEL_API_URL = "https://learn-self-eight.vercel.app/api"
# ================================================

st.set_page_config(
    page_title="Agent Skills Hub",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS样式
st.markdown("""
<style>
    /* 卡片样式 */
    .skill-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 20px;
        padding: 25px;
        margin: 10px 0;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        transition: transform 0.3s ease, box-shadow 0.3s ease;
        color: white;
        position: relative;
        overflow: hidden;
        height: 100%;
        display: flex;
        flex-direction: column;
    }
    
    .skill-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 40px rgba(0,0,0,0.3);
    }
    
    .skill-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(45deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0) 100%);
        pointer-events: none;
    }
    
    /* 卡片头部 */
    .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 15px;
        border-bottom: 2px solid rgba(255,255,255,0.2);
        padding-bottom: 10px;
    }
    
    .card-title {
        font-size: 1.4rem;
        font-weight: 700;
        margin: 0;
        color: white;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        word-break: break-word;
    }
    
    .card-category {
        background: rgba(255,255,255,0.25);
        padding: 5px 12px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 500;
        backdrop-filter: blur(5px);
        border: 1px solid rgba(255,255,255,0.3);
        white-space: nowrap;
    }
    
    /* 评分徽章 */
    .score-badge {
        background: rgba(255,215,0,0.25);
        border: 2px solid #FFD700;
        border-radius: 50px;
        padding: 8px 15px;
        font-weight: 700;
        font-size: 1.2rem;
        color: #FFD700;
        text-align: center;
        backdrop-filter: blur(5px);
        min-width: 100px;
    }
    
    .score-label {
        font-size: 0.8rem;
        opacity: 0.9;
        display: block;
    }
    
    .score-value {
        font-size: 1.5rem;
        line-height: 1.2;
    }
    
    /* 描述文本 */
    .card-description {
        background: rgba(0,0,0,0.15);
        border-radius: 15px;
        padding: 15px;
        margin: 0;
        font-size: 0.95rem;
        line-height: 1.5;
        border-left: 4px solid rgba(255,255,255,0.5);
        word-break: break-word;
    }
    
    /* 指标网格 */
    .metrics-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
        gap: 10px;
        margin: 15px 0;
    }
    
    .metric-item {
        background: rgba(255,255,255,0.15);
        border-radius: 12px;
        padding: 10px;
        text-align: center;
        backdrop-filter: blur(5px);
        transition: background 0.3s ease;
    }
    
    .metric-item:hover {
        background: rgba(255,255,255,0.25);
    }
    
    .metric-icon {
        font-size: 1.5rem;
        margin-bottom: 5px;
    }
    
    .metric-label {
        font-size: 0.75rem;
        opacity: 0.9;
        margin-bottom: 3px;
    }
    
    .metric-value {
        font-size: 1.2rem;
        font-weight: 700;
    }
    
    /* 卡片底部 */
    .card-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 15px;
        padding-top: 10px;
        border-top: 1px solid rgba(255,255,255,0.2);
        font-size: 0.9rem;
    }
    
    .author-info {
        display: flex;
        align-items: center;
        gap: 5px;
        flex-wrap: wrap;
    }
    
    .github-link {
        background: rgba(255,255,255,0.2);
        color: white;
        text-decoration: none;
        padding: 8px 15px;
        border-radius: 25px;
        font-size: 0.9rem;
        transition: background 0.3s ease;
        display: inline-flex;
        align-items: center;
        gap: 5px;
    }
    
    .github-link:hover {
        background: rgba(255,255,255,0.3);
        color: white;
    }
    
    .last-commit {
        opacity: 0.8;
        font-size: 0.85rem;
        margin-top: 10px;
        text-align: right;
    }
    
    /* 空状态 */
    .empty-state {
        text-align: center;
        padding: 60px;
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        border-radius: 20px;
        margin: 20px 0;
    }
    
    .empty-state-icon {
        font-size: 4rem;
        margin-bottom: 20px;
    }
    
    .empty-state-title {
        font-size: 1.5rem;
        font-weight: 600;
        color: #333;
        margin-bottom: 10px;
    }
    
    .empty-state-text {
        color: #666;
        margin-bottom: 20px;
    }
    
    /* 加载动画 */
    .loading-spinner {
        text-align: center;
        padding: 40px;
    }
    
    /* 同步状态栏 */
    .sync-status-bar {
        background: linear-gradient(90deg, #43e97b 0%, #38f9d7 100%);
        padding: 10px 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        color: white;
        font-weight: 500;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    
    /* 分页控件 */
    .pagination {
        display: flex;
        justify-content: center;
        gap: 10px;
        margin: 30px 0;
    }
    
    .pagination-button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 10px 20px;
        border-radius: 25px;
        cursor: pointer;
        font-weight: 500;
        transition: opacity 0.3s ease;
    }
    
    .pagination-button:hover {
        opacity: 0.9;
    }
    
    .pagination-button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }
    
    .pagination-info {
        padding: 10px 20px;
        background: #f0f2f6;
        border-radius: 25px;
        color: #333;
    }
</style>
""", unsafe_allow_html=True)

# 初始化 session state
if 'sync_status' not in st.session_state:
    st.session_state.sync_status = None
if 'skills_data' not in st.session_state:
    st.session_state.skills_data = None
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = time.strftime("%Y-%m-%d %H:%M:%S")
if 'category' not in st.session_state:
    st.session_state.category = "All"
if 'sort' not in st.session_state:
    st.session_state.sort = "score"
if 'page' not in st.session_state:
    st.session_state.page = 1
if 'page_size' not in st.session_state:
    st.session_state.page_size = 12

# 标题
st.title("🚀 Agent Skills Hub")
st.markdown("### *智能体技能聚合与动态评分平台*")

# 侧边栏
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/null/artificial-intelligence.png", width=80)
    st.markdown("## 控制面板")
    
    # 同步状态显示
    st.markdown("### 🔄 同步状态")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("最后更新", st.session_state.last_refresh.split()[0])
    with col2:
        try:
            status_response = requests.get(f"{VERCEL_API_URL}/sync/status", timeout=5)
            if status_response.status_code == 200:
                status_data = status_response.json()
                sync_status = "🟢 空闲" if not status_data.get('is_syncing') else "🟡 同步中"
                st.metric("当前状态", sync_status)
        except:
            st.metric("当前状态", "⚪ 未知")
    
    # 同步按钮
    if st.button("🔄 立即同步数据", type="primary", use_container_width=True):
        with st.status("正在同步数据...", expanded=True) as status:
            try:
                st.write("📡 连接到 Vercel API...")
                response = requests.post(f"{VERCEL_API_URL}/sync", timeout=5)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('status') == 'busy':
                        st.warning(f"⏳ 同步正在进行中 ({result.get('current_sync', 'unknown')})")
                    else:
                        st.success("✅ 同步任务已启动！")
                        st.info(f"⏱️ 耗时: {result.get('elapsed_seconds', 'N/A')} 秒")
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
    categories = ["All", "Agent", "Tool", "Framework", "Demo", "Other"]
    category = st.selectbox(
        "分类",
        categories,
        index=categories.index(st.session_state.category) if st.session_state.category in categories else 0
    )
    st.session_state.category = category
    
    # 排序方式
    sort_options = {
        "score": "综合评分 ↓",
        "stars": "⭐ Stars ↓",
        "forks": "🍴 Forks ↓",
        "time": "🕐 最近更新 ↓"
    }
    sort = st.selectbox(
        "排序",
        list(sort_options.keys()),
        format_func=lambda x: sort_options[x],
        index=list(sort_options.keys()).index(st.session_state.sort)
    )
    st.session_state.sort = sort
    
    # 每页数量
    page_size = st.select_slider(
        "每页显示",
        options=[6, 12, 24, 48],
        value=st.session_state.page_size
    )
    st.session_state.page_size = page_size
    
    st.divider()
    
    # 快捷操作
    st.markdown("### ⚡ 快捷操作")
    if st.button("重置筛选", use_container_width=True):
        st.session_state.category = "All"
        st.session_state.sort = "score"
        st.session_state.page = 1
        st.session_state.page_size = 12
        st.rerun()
    
    if st.button("查看同步状态", use_container_width=True):
        try:
            status = requests.get(f"{VERCEL_API_URL}/sync/status")
            st.json(status.json())
        except:
            st.error("无法获取同步状态")
    
    st.divider()
    
    # 页脚
    st.markdown("""
    ---
    **📌 说明**
    - 数据来自 GitHub
    - 每小时自动同步
    - 评分算法综合多项指标
    - 点击卡片可访问仓库
    """)

# 主内容区域
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    st.markdown(f"### 📚 技能库 (第 {st.session_state.page} 页)")

with col2:
    # 显示总数（需要从API获取）
    pass

with col3:
    if st.button("🔄 刷新数据"):
        st.rerun()

# 获取数据
params = {
    "page": st.session_state.page,
    "size": st.session_state.page_size,
    "sort": st.session_state.sort
}

if st.session_state.category != "All":
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
            st.metric("总技能数", total)
        with col2:
            st.metric("当前显示", min(len(items), st.session_state.page_size))
        with col3:
            total_pages = (total + st.session_state.page_size - 1) // st.session_state.page_size if total > 0 else 1
            st.metric("总页数", total_pages)
        with col4:
            st.metric("当前页码", st.session_state.page)
        
        st.divider()
        
        if not items:
            # 空状态显示
            st.markdown("""
            <div class="empty-state">
                <div class="empty-state-icon">🔍</div>
                <div class="empty-state-title">暂无数据</div>
                <div class="empty-state-text">点击左侧「立即同步」按钮获取 GitHub 数据</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            # 以卡片网格形式展示
            cols_per_row = 2  # 每行2个卡片
            
            for i in range(0, len(items), cols_per_row):
                cols = st.columns(cols_per_row)
                for j in range(cols_per_row):
                    if i + j < len(items):
                        skill = items[i + j]
                        
                        # 处理时间格式
                        last_commit = skill.get('last_commit', '')
                        if last_commit:
                            if isinstance(last_commit, str):
                                try:
                                    commit_date = datetime.strptime(last_commit[:10], "%Y-%m-%d")
                                    last_commit_str = commit_date.strftime("%Y-%m-%d")
                                except:
                                    last_commit_str = last_commit[:10]
                            else:
                                last_commit_str = str(last_commit)[:10]
                        else:
                            last_commit_str = "未知"
                        
                        # 格式化数字（添加千位分隔符）
                        stars = f"{skill.get('stars', 0):,}"
                        forks = f"{skill.get('forks', 0):,}"
                        open_issues = f"{skill.get('open_issues', 0):,}"
                        closed_issues = f"{skill.get('closed_issues', 0):,}"
                        total_commits = f"{skill.get('total_commits', 0):,}"
                        author_followers = f"{skill.get('author_followers', 0):,}"
                        
                        # 获取描述（截断）
                        description = skill.get('description', 'No description')
                        if description and len(description) > 150:
                            description = description[:150] + "..."
                        
                        # 构建卡片HTML - 确保所有标签正确闭合
                        card_html = f"""
                        <div class="skill-card">
                            <div class="card-header">
                                <h3 class="card-title">{skill.get('name', 'Unknown')}</h3>
                                <span class="card-category">{skill.get('category', 'N/A')}</span>
                            </div>
                            
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 15px;">
                                <div style="flex: 1;">
                                    <div class="card-description">
                                        {description}
                                    </div>
                                </div>
                                <div class="score-badge">
                                    <span class="score-label">综合评分</span>
                                    <span class="score-value">{skill.get('score', 0):.1f}</span>
                                </div>
                            </div>
                            
                            <div class="metrics-grid">
                                <div class="metric-item">
                                    <div class="metric-icon">⭐</div>
                                    <div class="metric-label">Stars</div>
                                    <div class="metric-value">{stars}</div>
                                </div>
                                <div class="metric-item">
                                    <div class="metric-icon">🍴</div>
                                    <div class="metric-label">Forks</div>
                                    <div class="metric-value">{forks}</div>
                                </div>
                                <div class="metric-item">
                                    <div class="metric-icon">🐞</div>
                                    <div class="metric-label">Open Issues</div>
                                    <div class="metric-value">{open_issues}</div>
                                </div>
                                <div class="metric-item">
                                    <div class="metric-icon">✅</div>
                                    <div class="metric-label">Closed</div>
                                    <div class="metric-value">{closed_issues}</div>
                                </div>
                                <div class="metric-item">
                                    <div class="metric-icon">📝</div>
                                    <div class="metric-label">Commits</div>
                                    <div class="metric-value">{total_commits}</div>
                                </div>
                            </div>
                            
                            <div class="card-footer">
                                <div class="author-info">
                                    <span>👤 {skill.get('author', 'Unknown')}</span>
                                    <span style="opacity: 0.8;">({author_followers} followers)</span>
                                </div>
                                <div>
                                    <a href="{skill.get('url', '#')}" target="_blank" class="github-link">
                                        <span>🔗</span> GitHub
                                    </a>
                                </div>
                            </div>
                            
                            <div class="last-commit">
                                🕐 最后提交: {last_commit_str}
                            </div>
                        </div>
                        """
                        
                        with cols[j]:
                            st.markdown(card_html, unsafe_allow_html=True)
        
        # 分页控件
        if total_pages > 1:
            st.markdown("---")
            col1, col2, col3, col4, col5 = st.columns([1, 2, 1, 2, 1])
            
            with col2:
                if st.button("◀ 上一页", disabled=(st.session_state.page <= 1), use_container_width=True):
                    st.session_state.page = max(1, st.session_state.page - 1)
                    st.rerun()
            
            with col3:
                st.markdown(f"<div style='text-align: center; padding: 10px;'>{st.session_state.page} / {total_pages}</div>", unsafe_allow_html=True)
            
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
    st.caption("🚀 Agent Skills Hub | 智能体技能聚合平台")
with col2:
    st.caption(f"🕐 页面刷新: {time.strftime('%Y-%m-%d %H:%M:%S')}")
with col3:
    st.caption("📊 数据源: GitHub API")

# 调试信息（仅在本地开发时显示）
if os.getenv('STREAMLIT_DEBUG') or st.session_state.get('show_debug', False):
    with st.expander("🔧 调试信息"):
        st.json({
            "api_url": VERCEL_API_URL,
            "session_state": {k: str(v) for k, v in st.session_state.items()},
            "params": params,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })