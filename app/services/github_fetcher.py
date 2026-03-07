import requests
import time
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.config import settings
import logging
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

# 禁用 SSL 警告（可选）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class GithubFetcher:
    BASE_URL = "https://api.github.com"

    _total_requests = 0
    _max_requests = 5000
    _request_lock = threading.RLock()
    _stop_flag = False
    _success_count = 0
    _fail_count = 0

    def __init__(self, max_workers: int = None):
        self.headers = {
            "Authorization": f"token {settings.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Agent-Skills-App/3.0",
            "Connection": "keep-alive",
            "Keep-Alive": "timeout=30, max=1000"
        }

        self.max_workers = max_workers or settings.github_max_workers

        # 创建会话并配置连接池（优化版）
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # 配置重试策略 - 针对 SSL 错误特别处理
        retry_strategy = Retry(
            total=3,  # 增加重试次数
            connect=3,
            read=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        # 配置连接池
        adapter = HTTPAdapter(
            pool_connections=settings.max_connections,
            pool_maxsize=settings.max_connections,
            max_retries=retry_strategy,
            pool_block=False
        )
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)
        
        # 设置会话属性
        self.session.verify = False  # 临时禁用 SSL 验证（解决 EOF 错误）
        self.session.trust_env = False

        self.instance_requests = 0
        self.request_times = []
        
        # 使用队列控制并发
        self.work_queue = threading.Queue()
        self.result_queue = threading.Queue()
        self.queue_lock = threading.Lock()

        # 扩展关键词列表（增加更多相关关键词）
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
            "llm orchestration",
            "agent platform",
            "agentic ai",
            "llm tools",
            "ai agents",
            "autonomous agents"
        ]

    @classmethod
    def get_total_requests(cls):
        with cls._request_lock:
            return cls._total_requests

    @classmethod
    def reset_request_count(cls):
        with cls._request_lock:
            cls._total_requests = 0
            cls._stop_flag = False
            cls._success_count = 0
            cls._fail_count = 0
            logger.info("🔄 Request count reset to 0")

    @classmethod
    def should_stop(cls):
        with cls._request_lock:
            return cls._stop_flag or cls._total_requests >= cls._max_requests

    @classmethod
    def can_make_request(cls):
        with cls._request_lock:
            if cls._stop_flag:
                return False

            if cls._total_requests >= cls._max_requests:
                cls._stop_flag = True
                logger.warning(f"⚠️ Request limit reached: {cls._total_requests}/{cls._max_requests}")
                return False

            return True

    def _increment_request_count(self, success: bool = True):
        with self.__class__._request_lock:
            self.__class__._total_requests += 1
            self.instance_requests += 1
            if success:
                self.__class__._success_count += 1
            else:
                self.__class__._fail_count += 1
            return self.__class__._total_requests

    def _rate_limit_control(self):
        """智能速率控制"""
        now = time.time()
        
        # 清理超过5秒的请求记录
        self.request_times = [t for t in self.request_times if now - t < 5]

        # 动态调整延迟
        if len(self.request_times) > 30:  # 5秒内超过30个请求
            sleep_time = 0.2
        elif len(self.request_times) > 20:
            sleep_time = 0.1
        elif len(self.request_times) > 10:
            sleep_time = 0.05
        else:
            sleep_time = 0.01

        if sleep_time > 0:
            time.sleep(sleep_time)

        self.request_times.append(now)

    def _request(self, url: str, params: Optional[Dict] = None, retry_count: int = 0):
        """优化的请求方法，处理 SSL 错误"""
        if self.should_stop():
            return None

        if not self.can_make_request():
            return None

        max_retries = 3
        retry_delay = 1

        try:
            self._rate_limit_control()
            current_count = self._increment_request_count()

            # 添加随机 User-Agent 轮换
            if random.random() > 0.8:
                self.session.headers.update({
                    "User-Agent": f"Agent-Skills-App/3.0-{random.randint(1000, 9999)}"
                })

            response = self.session.get(
                url,
                params=params,
                timeout=settings.request_timeout,
                stream=False  # 禁用流式响应
            )

            if response.status_code in (403, 429):
                reset_time = int(
                    response.headers.get(
                        "X-RateLimit-Reset",
                        time.time() + 30
                    )
                )
                sleep_time = min(reset_time - int(time.time()), 30)
                
                if sleep_time > 0:
                    logger.warning(f"Rate limited, sleeping for {sleep_time}s")
                    time.sleep(sleep_time)
                
                return self._request(url, params)

            response.raise_for_status()
            
            if current_count % 50 == 0:
                success_rate = self._get_success_rate()
                logger.info(f"📊 Progress: {current_count}/{self._max_requests} "
                          f"(成功率: {success_rate:.1f}%)")
            
            return response

        except requests.exceptions.SSLError as e:
            logger.warning(f"SSL Error (attempt {retry_count + 1}/{max_retries}): {e}")
            if retry_count < max_retries:
                time.sleep(retry_delay * (retry_count + 1))
                return self._request(url, params, retry_count + 1)
            self._increment_request_count(success=False)
            return None

        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Connection Error (attempt {retry_count + 1}/{max_retries}): {e}")
            if retry_count < max_retries:
                time.sleep(retry_delay * (retry_count + 1))
                return self._request(url, params, retry_count + 1)
            self._increment_request_count(success=False)
            return None

        except Exception as e:
            logger.error(f"Request error: {e}")
            self._increment_request_count(success=False)
            return None

    def _get_success_rate(self):
        """获取成功率"""
        with self.__class__._request_lock:
            total = self._success_count + self._fail_count
            if total == 0:
                return 100
            return (self._success_count / total) * 100

    def search(self, keyword: str, page: int = 1, per_page: int = 100):
        """优化的搜索方法"""
        if self.should_stop():
            return []

        url = f"{self.BASE_URL}/search/repositories"

        params = {
            "q": keyword,
            "per_page": min(per_page, 100),
            "page": page,
            "sort": "stars",
            "order": "desc"
        }

        try:
            response = self._request(url, params=params)

            if response:
                data = response.json()
                items = data.get("items", [])
                return items

        except Exception as e:
            logger.error(f"Search error for {keyword}: {e}")

        return []

    def search_batch(self, keywords: List[str], page: int = 1):
        """批量搜索多个关键词"""
        results = []
        
        with ThreadPoolExecutor(max_workers=min(5, self.max_workers)) as executor:
            future_to_keyword = {
                executor.submit(self.search, keyword, page, 100): keyword
                for keyword in keywords
            }
            
            for future in as_completed(future_to_keyword):
                if self.should_stop():
                    break
                    
                try:
                    repos = future.result(timeout=10)
                    if repos:
                        results.extend(repos[:20])  # 每个关键词取20条
                except Exception as e:
                    logger.error(f"Batch search error: {e}")
        
        return results

    def fetch_repo_details_batch(self, repos):
        """优化的批量获取方法"""
        results = []
        
        # 动态计算批次大小
        batch_size = min(15, len(repos))
        
        for i in range(0, len(repos), batch_size):
            if self.should_stop():
                break
                
            batch = repos[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(repos)+batch_size-1)//batch_size}")
            
            # 使用线程池并发获取
            with ThreadPoolExecutor(max_workers=min(8, self.max_workers)) as executor:
                future_to_repo = {
                    executor.submit(self._fetch_single_repo, repo): repo
                    for repo in batch
                }

                for future in as_completed(future_to_repo):
                    if self.should_stop():
                        break

                    try:
                        result = future.result(timeout=8)
                        if result:
                            results.append(result)
                    except Exception as e:
                        logger.error(f"Future error: {e}")

        return results

    def _fetch_single_repo(self, repo):
        """优化的单个仓库获取方法"""
        try:
            owner = repo["owner"]["login"]
            repo_name = repo["name"]

            # 获取仓库信息
            repo_url = f"{self.BASE_URL}/repos/{owner}/{repo_name}"
            repo_response = self._request(repo_url)
            if not repo_response:
                return None

            repo_detail = repo_response.json()

            # 获取最后提交时间（只取最新的一条）
            last_commit = datetime.utcnow()
            try:
                commits_url = f"{self.BASE_URL}/repos/{owner}/{repo_name}/commits"
                commits_response = self._request(
                    commits_url,
                    params={"per_page": 1}
                )

                if commits_response:
                    commits_data = commits_response.json()
                    if commits_data:
                        last_commit = datetime.strptime(
                            commits_data[0]["commit"]["committer"]["date"],
                            "%Y-%m-%dT%H:%M:%SZ"
                        )
            except Exception:
                pass

            # 快速分类
            category = self._fast_category(
                repo_name,
                repo.get("description", "")
            )

            return {
                "name": repo_detail["name"],
                "description": repo_detail.get("description") or "No description",
                "url": repo_detail["html_url"],
                "category": category,
                "stars": repo_detail.get("stargazers_count", 0),
                "forks": repo_detail.get("forks_count", 0),
                "open_issues": repo_detail.get("open_issues_count", 0),
                "closed_issues": 0,
                "total_commits": 1,
                "last_commit": last_commit,
                "author": owner,
                "author_followers": 0
            }

        except Exception as e:
            logger.error(f"Repo fetch error for {repo.get('name')}: {e}")
            return None

    def _fast_category(self, name: str, description: str):
        """快速分类方法"""
        text = f"{name} {description}".lower()

        # 使用集合提高查找速度
        agent_keywords = {"agent", "llm", "ai", "mcp", "gpt", "assistant", "autogpt", "babyagi"}
        tool_keywords = {"tool", "cli", "sdk", "api", "client", "server", "library"}
        framework_keywords = {"framework", "platform", "engine", "core", "infrastructure"}

        words = set(text.split())

        if words & agent_keywords:
            return "Agent"
        if words & tool_keywords:
            return "Tool"
        if words & framework_keywords:
            return "Framework"
        if "demo" in text or "example" in text or "tutorial" in text:
            return "Demo"

        return "Other"

    @classmethod
    def get_request_stats(cls):
        with cls._request_lock:
            percentage = 0
            if cls._max_requests > 0:
                percentage = round(
                    (cls._total_requests / cls._max_requests) * 100,
                    2
                )

            success_rate = 100
            if cls._success_count + cls._fail_count > 0:
                success_rate = round(
                    (cls._success_count / (cls._success_count + cls._fail_count)) * 100,
                    2
                )

            return {
                "total_requests": cls._total_requests,
                "success_count": cls._success_count,
                "fail_count": cls._fail_count,
                "success_rate": success_rate,
                "max_requests": cls._max_requests,
                "remaining": max(0, cls._max_requests - cls._total_requests),
                "percentage": percentage,
                "should_stop": cls._stop_flag
            }

    def __del__(self):
        if hasattr(self, "session"):
            self.session.close()