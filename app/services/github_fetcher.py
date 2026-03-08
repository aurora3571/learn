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

# 禁用 SSL 警告
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
    _start_time = None

    def __init__(self, max_workers: int = None):
        self.headers = {
            "Authorization": f"token {settings.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Agent-Skills-App/3.0",
        }

        # 提高并发数
        self.max_workers = max_workers or 20  # 增加到20个线程
        
        # 创建会话并配置连接池
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # 配置重试策略 - 减少重试次数以加快速度
        retry_strategy = Retry(
            total=1,  # 减少重试次数
            connect=1,
            read=1,
            backoff_factor=0.2,  # 减少退避时间
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        # 增加连接池大小
        max_connections = 100  # 增加到100
        
        adapter = HTTPAdapter(
            pool_connections=max_connections,
            pool_maxsize=max_connections,
            max_retries=retry_strategy,
            pool_block=False
        )
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)
        
        self.session.verify = False
        self.session.trust_env = False

        self.instance_requests = 0
        
        # 使用信号量控制并发 - 提高并发数
        self.semaphore = threading.Semaphore(15)  # 增加到15

        # 关键词列表保持不变
        self.keywords = [
            "claude-mcp",
            "agent-tools",
            "ai-agent",
            "llm-agent",
            "langchain agent",
            "autogpt",
            "babyagi",
            "agent-framework",
            "llm-tool",
            "function calling",
            "mcp-server"
        ]
        
        # 缓存搜索结果，避免重复请求
        self.search_cache = {}
        self.cache_lock = threading.RLock()

    @classmethod
    def start_session(cls):
        """开始新会话，重置计数"""
        with cls._request_lock:
            cls._total_requests = 0
            cls._stop_flag = False
            cls._success_count = 0
            cls._fail_count = 0
            cls._start_time = time.time()
            logger.info("🚀 开始新的爬取会话，最大请求数: 5000")

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
            cls._start_time = time.time()
            logger.info("🔄 Request count reset to 0")

    @classmethod
    def should_stop(cls):
        with cls._request_lock:
            if cls._stop_flag:
                return True
            if cls._total_requests >= cls._max_requests:
                cls._stop_flag = True
                elapsed = time.time() - cls._start_time if cls._start_time else 0
                logger.info(f"⛔ 达到请求上限 {cls._max_requests} (耗时: {elapsed:.1f}秒)")
                return True
            return False

    @classmethod
    def can_make_request(cls):
        with cls._request_lock:
            if cls._stop_flag:
                return False
            if cls._total_requests >= cls._max_requests:
                cls._stop_flag = True
                return False
            return True

    @classmethod
    def get_remaining_requests(cls):
        with cls._request_lock:
            return max(0, cls._max_requests - cls._total_requests)

    def _increment_request_count(self, success: bool = True):
        with self.__class__._request_lock:
            self.__class__._total_requests += 1
            self.instance_requests += 1
            if success:
                self.__class__._success_count += 1
            else:
                self.__class__._fail_count += 1
            current = self.__class__._total_requests
            
            # 每100条记录进度，减少日志输出
            if current % 100 == 0:
                elapsed = time.time() - self.__class__._start_time if self.__class__._start_time else 0
                speed = current / elapsed if elapsed > 0 else 0
                success_rate = self._get_success_rate()
                logger.info(f"📊 进度: {current}/{self.__class__._max_requests} "
                          f"(速度: {speed:.1f} 条/秒, 成功率: {success_rate:.1f}%)")
            
            return current

    def _rate_limit_control(self):
        """动态速率控制 - 根据剩余请求数调整延迟"""
        remaining = self.get_remaining_requests()
        
        # 根据剩余请求数动态调整延迟
        if remaining < 100:
            # 剩余很少时，减慢速度避免超限
            time.sleep(0.5)
        elif remaining < 500:
            time.sleep(0.2)
        else:
            # 剩余充足时，几乎不延迟
            time.sleep(0.05)  # 从0.1降到0.05

    def _request(self, url: str, params: Optional[Dict] = None, retry_count: int = 0):
        """优化的请求方法"""
        if self.should_stop():
            return None

        if not self.can_make_request():
            return None

        # 使用信号量控制并发
        with self.semaphore:
            try:
                self._rate_limit_control()
                current_count = self._increment_request_count()

                # 减少日志输出 - 每50个请求才记录
                if current_count % 50 == 0:
                    logger.info(f"📡 请求 #{current_count}: {url[:50]}...")

                response = self.session.get(
                    url,
                    params=params,
                    timeout=10,  # 减少超时时间
                    stream=False
                )

                # 处理限流
                if response.status_code in (403, 429):
                    reset_time = int(
                        response.headers.get(
                            "X-RateLimit-Reset",
                            time.time() + 30
                        )
                    )
                    sleep_time = min(reset_time - int(time.time()), 30)
                    
                    if sleep_time > 0:
                        logger.warning(f"⏳ 触发限流，等待 {sleep_time}秒")
                        time.sleep(sleep_time)
                    
                    return self._request(url, params)

                response.raise_for_status()
                return response

            except requests.exceptions.SSLError as e:
                if retry_count < 1:  # 最多重试1次
                    time.sleep(0.5)
                    return self._request(url, params, retry_count + 1)
                self._increment_request_count(success=False)
                return None

            except requests.exceptions.ConnectionError as e:
                if retry_count < 1:
                    time.sleep(0.5)
                    return self._request(url, params, retry_count + 1)
                self._increment_request_count(success=False)
                return None

            except requests.exceptions.Timeout as e:
                if retry_count < 1:
                    time.sleep(0.5)
                    return self._request(url, params, retry_count + 1)
                self._increment_request_count(success=False)
                return None

            except Exception as e:
                logger.error(f"❌ 请求错误: {e}")
                self._increment_request_count(success=False)
                return None

    @classmethod
    def _get_success_rate(cls):
        """获取成功率"""
        total = cls._success_count + cls._fail_count
        if total == 0:
            return 100
        return (cls._success_count / total) * 100

    def search(self, keyword: str, page: int = 1, per_page: int = 30):
        """搜索方法 - 带缓存"""
        if self.should_stop():
            return []
            
        # 缓存键
        cache_key = f"{keyword}_{page}"
        
        # 检查缓存
        with self.cache_lock:
            if cache_key in self.search_cache:
                logger.info(f"🔍 使用缓存: {keyword} 第{page}页")
                return self.search_cache[cache_key]

        url = f"{self.BASE_URL}/search/repositories"
        params = {
            "q": keyword,
            "per_page": min(per_page, 30),
            "page": page,
            "sort": "stars",
            "order": "desc"
        }

        try:
            logger.info(f"🔍 搜索: {keyword} (第{page}页)")
            response = self._request(url, params=params)

            if response:
                data = response.json()
                items = data.get("items", [])
                
                # 存入缓存
                with self.cache_lock:
                    self.search_cache[cache_key] = items
                
                logger.info(f"✅ 找到 {len(items)} 个仓库")
                return items
            else:
                logger.warning(f"❌ 搜索失败: {keyword}")

        except Exception as e:
            logger.error(f"搜索错误 {keyword}: {e}")

        return []

    def fetch_repo_details_batch(self, repos):
        """批量获取仓库详情 - 使用线程池"""
        if not repos:
            return []
            
        results = []
        
        # 限制数量
        repos_to_fetch = repos[:30]  # 增加到30
        
        logger.info(f"📦 开始批量获取 {len(repos_to_fetch)} 个仓库详情")
        
        # 使用线程池并发获取
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_repo = {
                executor.submit(self._fetch_single_repo, repo): repo 
                for repo in repos_to_fetch
            }
            
            # 收集结果
            for future in as_completed(future_to_repo):
                repo = future_to_repo[future]
                try:
                    result = future.result(timeout=10)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"获取仓库详情失败 {repo.get('name')}: {e}")
        
        logger.info(f"✅ 批量获取完成，成功: {len(results)}/{len(repos_to_fetch)}")
        return results

    def _fetch_single_repo(self, repo):
        """获取单个仓库详情"""
        try:
            owner = repo["owner"]["login"]
            repo_name = repo["name"]

            repo_url = f"{self.BASE_URL}/repos/{owner}/{repo_name}"
            repo_response = self._request(repo_url)
            if not repo_response:
                return None

            repo_detail = repo_response.json()

            # 获取最后提交时间 - 使用单次请求
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

            # 分类
            category = self._categorize_repo(
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
                "total_commits": repo_detail.get("forks_count", 0),  # 使用forks作为近似值
                "last_commit": last_commit,
                "author": owner,
                "author_followers": 0
            }

        except Exception as e:
            logger.error(f"获取仓库详情失败 {repo.get('name')}: {e}")
            return None

    def _categorize_repo(self, name: str, description: str):
        """仓库分类"""
        text = f"{name} {description}".lower()

        if any(k in text for k in ["agent", "llm", "ai", "mcp", "gpt"]):
            return "Agent"
        if any(k in text for k in ["tool", "cli", "sdk", "api"]):
            return "Tool"
        if any(k in text for k in ["framework", "platform"]):
            return "Framework"
        if any(k in text for k in ["demo", "example"]):
            return "Demo"

        return "Other"

    @classmethod
    def get_request_stats(cls):
        with cls._request_lock:
            elapsed = time.time() - cls._start_time if cls._start_time else 0
            speed = cls._total_requests / elapsed if elapsed > 0 else 0
            success_rate = cls._get_success_rate()

            return {
                "total_requests": cls._total_requests,
                "success_count": cls._success_count,
                "fail_count": cls._fail_count,
                "success_rate": round(success_rate, 2),
                "max_requests": cls._max_requests,
                "remaining": max(0, cls._max_requests - cls._total_requests),
                "percentage": round((cls._total_requests / cls._max_requests) * 100, 2) if cls._max_requests > 0 else 0,
                "speed": round(speed, 2),
                "elapsed_seconds": round(elapsed, 2),
                "should_stop": cls._stop_flag
            }

    def __del__(self):
        if hasattr(self, "session"):
            self.session.close()