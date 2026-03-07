import requests
import time
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.config import settings
import logging
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class GithubFetcher:
    BASE_URL = "https://api.github.com"
    
    # 类变量：全局请求计数
    _total_requests = 0
    _max_requests = 5000  # 从4500修改为5000
    _request_lock = threading.RLock()
    _stop_flag = False  # 停止标志

    def __init__(self, max_workers: int = None):
        self.headers = {
            "Authorization": f"token {settings.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Agent-Skills-App/1.0"
        }
        self.max_workers = max_workers or settings.github_max_workers
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.mount('https://', requests.adapters.HTTPAdapter(
            pool_connections=100,
            pool_maxsize=100,
            max_retries=3,
            pool_block=False
        ))
        
        # 当前实例的请求计数
        self.instance_requests = 0
        self.request_times = []  # 记录请求时间用于速率控制

        # 扩展搜索关键词
        self.keywords = [
            "claude-mcp",
            "agent-tools",
            "codex-skills",
            "ai-agent",
            "llm-agent",
            "langchain agent",
            "autogpt",
            "babyagi",
            "agent-framework",
            "llm-tool",
            "ai assistant",
            "gpt agent",
            "llm skill",
            "function calling",
            "tool use",
            "mcp-server",
            "model-context-protocol",
            "ai agent framework",
            "llm tool calling",
            "agent orchestration",
            "ai assistant framework"
        ]

    @classmethod
    def get_total_requests(cls):
        """获取全局请求总数"""
        with cls._request_lock:
            return cls._total_requests

    @classmethod
    def reset_request_count(cls):
        """重置请求计数"""
        with cls._request_lock:
            cls._total_requests = 0
            cls._stop_flag = False
            logger.info("🔄 Request count reset to 0")

    @classmethod
    def set_max_requests(cls, max_requests: int):
        """设置最大请求数"""
        with cls._request_lock:
            cls._max_requests = max_requests
            logger.info(f"🎯 Max requests set to {max_requests}")

    @classmethod
    def should_stop(cls):
        """检查是否应该停止"""
        with cls._request_lock:
            return cls._stop_flag or cls._total_requests >= cls._max_requests

    @classmethod
    def can_make_request(cls):
        """检查是否可以继续发起请求"""
        with cls._request_lock:
            if cls._stop_flag:
                return False
            remaining = cls._max_requests - cls._total_requests
            can_make = cls._total_requests < cls._max_requests
            if not can_make:
                cls._stop_flag = True
                logger.warning(f"⚠️ Request limit reached: {cls._total_requests}/{cls._max_requests}")
            return can_make

    @classmethod
    def get_remaining_requests(cls):
        """获取剩余可用请求数"""
        with cls._request_lock:
            return max(0, cls._max_requests - cls._total_requests)

    @classmethod
    def get_progress_percentage(cls):
        """获取进度百分比"""
        with cls._request_lock:
            return round((cls._total_requests / cls._max_requests) * 100, 2)

    def _increment_request_count(self):
        """增加请求计数"""
        with self.__class__._request_lock:
            self.__class__._total_requests += 1
            self.instance_requests += 1
            current = self.__class__._total_requests
            remaining = self.__class__._max_requests - current
            percentage = (current / self.__class__._max_requests) * 100
            
            # 每50条或关键节点记录日志
            if current % 50 == 0 or percentage >= 90:
                logger.info(f"📊 Progress: {current}/{self.__class__._max_requests} "
                          f"({percentage:.1f}%) - 剩余: {remaining}")
            
            return current

    def _rate_limit_control(self):
        """速率控制 - 避免触发GitHub限流"""
        now = time.time()
        # 清理超过1分钟的请求记录
        self.request_times = [t for t in self.request_times if now - t < 60]
        
        # 如果1分钟内请求超过50次，适当延迟
        if len(self.request_times) > 50:
            sleep_time = random.uniform(0.5, 1.0)
            logger.debug(f"Rate control: sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        self.request_times.append(now)

    def _request(self, url: str, params: Optional[Dict] = None, retry_count: int = 0) -> Optional[requests.Response]:
        """改进的请求方法，包含请求计数和限制"""
        
        # 检查是否应该停止
        if self.should_stop():
            logger.warning(f"⛔ Stop flag detected, stopping requests")
            return None

        # 检查是否达到请求上限
        if not self.can_make_request():
            remaining = self.get_remaining_requests()
            logger.warning(f"⚠️ 已达到请求上限 ({self.__class__._total_requests}/{self.__class__._max_requests})")
            return None

        max_retries = 2  # 减少重试次数
        retry_delay = 2

        try:
            # 速率控制
            self._rate_limit_control()

            # 记录请求
            current_count = self._increment_request_count()
            
            response = self.session.get(url, params=params, timeout=settings.request_timeout)

            # 处理限流
            if response.status_code in (403, 429):
                reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
                sleep_time = min(reset_time - int(time.time()), 60)  # 最多等待1分钟

                remaining = response.headers.get("X-RateLimit-Remaining", "unknown")
                logger.warning(f"⚠️ Rate limited. Remaining: {remaining}. Sleeping for {sleep_time}s")

                if sleep_time > 0:
                    time.sleep(sleep_time)
                return self._request(url, params, retry_count + 1)

            response.raise_for_status()
            return response

        except Exception as e:
            logger.error(f"Request failed for {url}: {e}")
            if retry_count < max_retries:
                time.sleep(retry_delay * (retry_count + 1))
                return self._request(url, params, retry_count + 1)
            return None

    def search(self, keyword: str, page: int = 1, per_page: int = 50) -> List[Dict[str, Any]]:
        """支持分页的搜索方法"""
        
        # 检查是否应该停止
        if self.should_stop():
            return []

        url = f"{self.BASE_URL}/search/repositories"
        params = {
            "q": keyword,
            "per_page": min(per_page, 100),
            "page": page,
            "sort": "stars",  # 改为按星级排序，获取更高质量的项目
            "order": "desc"
        }

        try:
            logger.info(f"🔍 Searching: {keyword} (page {page})")
            response = self._request(url, params=params)

            if response and response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                logger.info(f"✅ Found {len(items)} repos for '{keyword}'")
                return items
            return []

        except Exception as e:
            logger.error(f"Error searching {keyword}: {e}")
            return []

    def fetch_repo_details_batch(self, repos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量获取仓库详情 - 使用并发加速"""
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_repo = {
                executor.submit(self._fetch_single_repo, repo): repo 
                for repo in repos
            }
            
            for future in as_completed(future_to_repo):
                if self.should_stop():
                    executor.shutdown(wait=False)
                    break
                    
                try:
                    result = future.result(timeout=10)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Error in batch fetch: {e}")
        
        return results

    def _fetch_single_repo(self, repo: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """获取单个仓库详情（供批量调用）"""
        try:
            owner = repo["owner"]["login"]
            repo_name = repo["name"]
            
            # 获取仓库详情
            repo_url = f"{self.BASE_URL}/repos/{owner}/{repo_name}"
            repo_response = self._request(repo_url)
            if not repo_response:
                return None
            repo_detail = repo_response.json()

            # 获取最后提交时间（单个请求）
            last_commit = datetime.utcnow()
            try:
                commits_url = f"{self.BASE_URL}/repos/{owner}/{repo_name}/commits"
                commits_response = self._request(commits_url, params={"per_page": 1})
                if commits_response:
                    commits_data = commits_response.json()
                    if commits_data:
                        last_commit = datetime.strptime(
                            commits_data[0]["commit"]["committer"]["date"],
                            "%Y-%m-%dT%H:%M:%SZ"
                        )
            except Exception as e:
                logger.debug(f"Error fetching commits for {owner}/{repo_name}: {e}")

            # 获取作者关注者数
            author_followers = 0
            try:
                user_url = f"{self.BASE_URL}/users/{owner}"
                user_response = self._request(user_url)
                if user_response:
                    author_followers = user_response.json().get("followers", 0)
            except Exception as e:
                logger.debug(f"Error fetching user for {owner}: {e}")

            # 简化分类
            category = self._simple_category(repo_name, repo.get("description", ""))

            return {
                "name": repo_detail["name"],
                "description": repo_detail.get("description") or "No description",
                "url": repo_detail["html_url"],
                "category": category,
                "stars": repo_detail.get("stargazers_count", 0),
                "forks": repo_detail.get("forks_count", 0),
                "open_issues": repo_detail.get("open_issues_count", 0),
                "closed_issues": 0,  # 简化，不获取
                "total_commits": 1,   # 简化，不获取
                "last_commit": last_commit,
                "author": owner,
                "author_followers": author_followers
            }

        except Exception as e:
            logger.error(f"Error fetching {repo.get('name')}: {e}")
            return None

    def _simple_category(self, name: str, description: str) -> str:
        """简化的分类方法"""
        text = f"{name} {description}".lower()
        
        if any(k in text for k in ["agent", "mcp", "llm", "ai"]):
            return "Agent"
        elif any(k in text for k in ["tool", "cli", "sdk"]):
            return "Tool"
        elif any(k in text for k in ["framework", "platform"]):
            return "Framework"
        elif any(k in text for k in ["demo", "example"]):
            return "Demo"
        return "Other"

    def get_request_stats(self) -> Dict[str, Any]:
        """获取请求统计信息"""
        with self.__class__._request_lock:
            return {
                "total_requests": self.__class__._total_requests,
                "max_requests": self.__class__._max_requests,
                "remaining": max(0, self.__class__._max_requests - self.__class__._total_requests),
                "percentage": round((self.__class__._total_requests / self.__class__._max_requests) * 100, 2),
                "should_stop": self.__class__._stop_flag
            }

    def __del__(self):
        """清理 session"""
        if hasattr(self, 'session'):
            self.session.close()