import requests
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.config import settings
import logging
import random

logger = logging.getLogger(__name__)


class GithubFetcher:
    BASE_URL = "https://api.github.com"

    def __init__(self, max_workers: int = 5):
        self.headers = {
            "Authorization": f"token {settings.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Agent-Skills-App/1.0"
        }
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.headers.update(self.headers)

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
            "model-context-protocol"
        ]

    def _request(self, url: str, params: Optional[Dict] = None, retry_count: int = 0) -> Optional[requests.Response]:
        """改进的请求方法，更好的错误处理"""
        max_retries = 3
        retry_delay = 5

        try:
            # 随机延迟避免限流
            if retry_count > 0:
                time.sleep(retry_delay * retry_count)

            response = self.session.get(url, params=params, timeout=15)

            # 处理限流
            if response.status_code in (403, 429):
                reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
                sleep_time = min(reset_time - int(time.time()), 300)  # 最多等待5分钟

                # 检查剩余配额
                remaining = response.headers.get("X-RateLimit-Remaining", "unknown")
                logger.warning(f"Rate limited. Remaining: {remaining}. Sleeping for {sleep_time}s")

                if sleep_time > 0:
                    time.sleep(sleep_time)
                return self._request(url, params, retry_count + 1)  # 重试

            response.raise_for_status()
            return response

        except requests.exceptions.SSLError as e:
            logger.error(f"SSL Error for {url}: {e}")
            if retry_count < max_retries:
                logger.info(f"Retrying ({retry_count + 1}/{max_retries})...")
                time.sleep(retry_delay * (retry_count + 1))
                return self._request(url, params, retry_count + 1)
            return None

        except requests.exceptions.Timeout:
            logger.error(f"Timeout for {url}")
            if retry_count < max_retries:
                logger.info(f"Retrying ({retry_count + 1}/{max_retries})...")
                time.sleep(retry_delay)
                return self._request(url, params, retry_count + 1)
            return None

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection Error for {url}: {e}")
            if retry_count < max_retries:
                logger.info(f"Retrying ({retry_count + 1}/{max_retries})...")
                time.sleep(retry_delay * 2)
                return self._request(url, params, retry_count + 1)
            return None

        except requests.exceptions.HTTPError as e:
            if response.status_code == 502:
                logger.error(f"Bad Gateway (502) for {url}")
                if retry_count < max_retries:
                    logger.info(f"Retrying ({retry_count + 1}/{max_retries})...")
                    time.sleep(retry_delay * 2)
                    return self._request(url, params, retry_count + 1)
            return None

        except Exception as e:
            logger.error(f"Request failed for {url}: {e}")
            if retry_count < max_retries:
                logger.info(f"Retrying ({retry_count + 1}/{max_retries})...")
                time.sleep(retry_delay)
                return self._request(url, params, retry_count + 1)
            return None

    def search(self, keyword: str, page: int = 1, per_page: int = 100) -> List[Dict[str, Any]]:
        """支持分页的搜索方法"""
        url = f"{self.BASE_URL}/search/repositories"
        params = {
            "q": keyword,
            "per_page": min(per_page, 100),
            "page": page,
            "sort": "updated",  # 按更新时间排序，获取最新项目
            "order": "desc"
        }

        try:
            logger.info(f"Searching GitHub for: {keyword} (page {page})")
            response = self._request(url, params=params)

            if response and response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                total_count = data.get("total_count", 0)
                logger.info(f"Found {len(items)} repos for '{keyword}', total available: {total_count}")
                return items
            else:
                logger.warning(f"No results for {keyword} (page {page})")
                return []

        except Exception as e:
            logger.error(f"Error searching {keyword} (page {page}): {e}")
            return []

    def get_total_commits(self, owner: str, repo: str) -> int:
        """获取总提交数"""
        try:
            # 使用 GitHub 的 statistics API
            url = f"{self.BASE_URL}/repos/{owner}/{repo}/stats/contributors"
            response = self._request(url)

            if response and response.status_code == 200:
                contributors = response.json()
                if isinstance(contributors, list):
                    total = sum(c.get('total', 0) for c in contributors)
                    return max(total, 1)

            # 如果 stats API 失败，尝试获取 commits 总数
            url = f"{self.BASE_URL}/repos/{owner}/{repo}/commits"
            params = {"per_page": 1, "page": 1}
            response = self._request(url, params=params)

            if response and "Link" in response.headers:
                link = response.headers["Link"]
                if 'rel="last"' in link:
                    last_page = link.split('rel="last"')[0].split("&page=")[-1].split(">")[0]
                    try:
                        return int(last_page)
                    except:
                        pass

            return 1

        except Exception as e:
            logger.error(f"Error getting total commits for {owner}/{repo}: {e}")
            return 1

    def fetch_repo_details(self, repo: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """获取单个仓库的详细信息"""
        try:
            owner = repo["owner"]["login"]
            repo_name = repo["name"]

            logger.info(f"Fetching details for {owner}/{repo_name}")

            # 获取仓库详情
            repo_url = f"{self.BASE_URL}/repos/{owner}/{repo_name}"
            repo_response = self._request(repo_url)
            if not repo_response or repo_response.status_code != 200:
                logger.error(f"Failed to fetch repo details for {owner}/{repo_name}")
                return None
            repo_detail = repo_response.json()

            # 获取 closed issues 数量
            closed_issues = 0
            try:
                issues_url = f"{self.BASE_URL}/repos/{owner}/{repo_name}/issues"
                issues_params = {"state": "closed", "per_page": 1, "page": 1}
                issues_response = self._request(issues_url, params=issues_params)

                if issues_response and issues_response.status_code == 200:
                    if "Link" in issues_response.headers:
                        link = issues_response.headers["Link"]
                        if 'rel="last"' in link:
                            last_page = link.split('rel="last"')[0].split("&page=")[-1].split(">")[0]
                            try:
                                closed_issues = int(last_page)
                            except:
                                closed_issues = len(issues_response.json()) if issues_response.json() else 0
                    else:
                        closed_issues = len(issues_response.json()) if issues_response.json() else 0
            except Exception as e:
                logger.error(f"Error fetching issues for {owner}/{repo_name}: {e}")

            # 获取最后提交时间
            last_commit = datetime.utcnow()
            try:
                commits_url = f"{self.BASE_URL}/repos/{owner}/{repo_name}/commits"
                commits_params = {"per_page": 1}
                commits_response = self._request(commits_url, params=commits_params)

                if commits_response and commits_response.status_code == 200:
                    commits_data = commits_response.json()
                    if commits_data and len(commits_data) > 0:
                        commit_data = commits_data[0]
                        last_commit = datetime.strptime(
                            commit_data["commit"]["committer"]["date"],
                            "%Y-%m-%dT%H:%M:%SZ"
                        )
            except Exception as e:
                logger.error(f"Error fetching commits for {owner}/{repo_name}: {e}")

            # 获取作者信息
            author_followers = 0
            try:
                user_url = f"{self.BASE_URL}/users/{owner}"
                user_response = self._request(user_url)
                if user_response and user_response.status_code == 200:
                    author_info = user_response.json()
                    author_followers = author_info.get("followers", 0)
            except Exception as e:
                logger.error(f"Error fetching user info for {owner}: {e}")

            # 获取总提交数
            total_commits = 1
            try:
                total_commits = self.get_total_commits(owner, repo_name)
            except Exception as e:
                logger.error(f"Error getting total commits for {owner}/{repo_name}: {e}")

            # 确定分类
            category = self._determine_category(repo_detail, repo_name, repo.get("description", ""))

            result = {
                "name": repo_detail["name"],
                "description": repo_detail.get("description") or "No description",
                "url": repo_detail["html_url"],
                "category": category,
                "stars": repo_detail.get("stargazers_count", 0),
                "forks": repo_detail.get("forks_count", 0),
                "open_issues": repo_detail.get("open_issues_count", 0),
                "closed_issues": closed_issues,
                "total_commits": total_commits,
                "last_commit": last_commit,
                "author": owner,
                "author_followers": author_followers
            }

            logger.info(f"Successfully fetched details for {owner}/{repo_name}: "
                       f"stars={result['stars']}, commits={total_commits}")

            return result

        except Exception as e:
            logger.error(f"Error in fetch_repo_details for {repo.get('name', 'unknown')}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _determine_category(self, repo_detail: Dict, name: str, description: str) -> str:
        """根据仓库信息确定分类"""
        name_lower = name.lower()
        desc_lower = description.lower() if description else ""

        # 关键词映射
        categories = {
            "Agent": ["agent", "mcp", "claude", "gpt", "llm", "ai", "assistant", "model-context"],
            "Tool": ["tool", "cli", "library", "sdk", "api", "client", "server"],
            "Framework": ["framework", "platform", "engine", "core", "infrastructure"],
            "Demo": ["demo", "example", "tutorial", "sample", "template"],
            "Other": []
        }

        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword in name_lower or keyword in desc_lower:
                    return category

        return "Other"

    def __del__(self):
        """清理 session"""
        if hasattr(self, 'session'):
            self.session.close()