import requests
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.config import settings
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

logger = logging.getLogger(__name__)


class GithubFetcher:
    BASE_URL = "https://api.github.com"

    def __init__(self, max_workers: int = 10):
        self.headers = {
            "Authorization": f"token {settings.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _request(self, url: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """改进的请求方法，支持参数和更好的限流处理"""
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                response = self.session.get(url, params=params, timeout=10)

                # 处理限流
                if response.status_code in (403, 429):
                    reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
                    sleep_time = max(reset_time - int(time.time()), 5)
                    logger.warning(f"Rate limited, sleeping for {sleep_time}s")
                    time.sleep(sleep_time)
                    continue

                response.raise_for_status()
                return response

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                else:
                    raise

        raise Exception(f"Failed after {max_retries} attempts")

    def search(self, keyword: str, page: int = 1, per_page: int = 100) -> List[Dict[str, Any]]:
        """支持分页的搜索方法"""
        url = f"{self.BASE_URL}/search/repositories"
        params = {
            "q": keyword,
            "per_page": min(per_page, 100),  # GitHub 最大每页100
            "page": page,
            "sort": "stars",  # 按星级排序，获取更高质量的项目
            "order": "desc"
        }

        try:
            response = self._request(url, params=params)
            return response.json().get("items", [])
        except Exception as e:
            logger.error(f"Error searching {keyword} (page {page}): {e}")
            return []

    def get_total_commits(self, owner: str, repo: str) -> int:
        """通过 API 获取总提交数（优化版本）"""
        try:
            url = f"{self.BASE_URL}/repos/{owner}/{repo}/commits"
            params = {"per_page": 1, "page": 1}
            response = self._request(url, params=params)

            # 尝试从 Link header 获取总页数
            if "Link" in response.headers:
                link = response.headers["Link"]
                if 'rel="last"' in link:
                    last_page = link.split('rel="last"')[0].split("&page=")[-1].split(">")[0]
                    try:
                        return int(last_page)
                    except:
                        pass

            # 如果无法从 header 获取，尝试获取总数
            if "total_count" in response.headers.get("X-Total-Count", ""):
                return int(response.headers["X-Total-Count"])

            # 默认返回
            return 1

        except Exception as e:
            logger.error(f"Error getting total commits for {owner}/{repo}: {e}")
            return 1

    def fetch_repo_details_batch(self, repos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量获取仓库详情（并发处理）"""
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_repo = {
                executor.submit(self._fetch_single_repo, repo): repo
                for repo in repos
            }

            for future in as_completed(future_to_repo):
                repo = future_to_repo[future]
                try:
                    result = future.result(timeout=30)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Error fetching repo {repo.get('name')}: {e}")

        return results

    def _fetch_single_repo(self, repo: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """获取单个仓库的详细信息"""
        try:
            owner = repo["owner"]["login"]
            repo_name = repo["name"]

            # 并发获取多个API
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                # 提交多个任务
                repo_future = executor.submit(
                    self._request,
                    f"{self.BASE_URL}/repos/{owner}/{repo_name}"
                )

                issues_future = executor.submit(
                    self._request,
                    f"{self.BASE_URL}/repos/{owner}/{repo_name}/issues",
                    {"state": "closed", "per_page": 1}
                )

                commits_future = executor.submit(
                    self._request,
                    f"{self.BASE_URL}/repos/{owner}/{repo_name}/commits",
                    {"per_page": 1}
                )

                user_future = executor.submit(
                    self._request,
                    f"{self.BASE_URL}/users/{owner}"
                )

                # 获取结果
                repo_detail = repo_future.result().json()
                closed_issues_resp = issues_future.result().json()
                commits_resp = commits_future.result().json()
                author_info = user_future.result().json()

            # 处理最后提交时间
            if commits_resp and len(commits_resp) > 0:
                last_commit = datetime.strptime(
                    commits_resp[0]["commit"]["committer"]["date"],
                    "%Y-%m-%dT%H:%M:%SZ"
                )
            else:
                last_commit = datetime.utcnow()

            # 获取总提交数
            total_commits = self.get_total_commits(owner, repo_name)

            return {
                "name": repo_detail["name"],
                "description": repo_detail.get("description") or "No description",
                "url": repo_detail["html_url"],
                "category": "Agent",

                "stars": repo_detail.get("stargazers_count", 0),
                "forks": repo_detail.get("forks_count", 0),

                "open_issues": repo_detail.get("open_issues_count", 0),
                "closed_issues": len(closed_issues_resp),

                "total_commits": total_commits,
                "last_commit": last_commit,

                "author": owner,
                "author_followers": author_info.get("followers", 0)
            }

        except Exception as e:
            logger.error(f"Error in _fetch_single_repo for {repo.get('name')}: {e}")
            return None

    def fetch_repo_details(self, repo: Dict[str, Any]) -> Dict[str, Any]:
        """保持原有接口，但使用新的实现"""
        result = self._fetch_single_repo(repo)
        if result is None:
            raise Exception(f"Failed to fetch repo details for {repo.get('name')}")
        return result

    def __del__(self):
        """清理 session"""
        if hasattr(self, 'session'):
            self.session.close()