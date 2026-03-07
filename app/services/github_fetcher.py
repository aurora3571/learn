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

    _total_requests = 0
    _max_requests = 5000
    _request_lock = threading.RLock()
    _stop_flag = False

    def __init__(self, max_workers: int = None):
        self.headers = {
            "Authorization": f"token {settings.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Agent-Skills-App/1.0"
        }

        self.max_workers = max_workers or settings.github_max_workers

        self.session = requests.Session()
        self.session.headers.update(self.headers)

        self.instance_requests = 0
        self.request_times = []

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
            "llm-tool"
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
                return False

            return True

    @classmethod
    def get_remaining_requests(cls):
        with cls._request_lock:
            return max(0, cls._max_requests - cls._total_requests)

    def _increment_request_count(self):
        with self.__class__._request_lock:
            self.__class__._total_requests += 1
            self.instance_requests += 1
            return self.__class__._total_requests

    def _rate_limit_control(self):
        now = time.time()

        self.request_times = [
            t for t in self.request_times if now - t < 60
        ]

        if len(self.request_times) > 50:
            sleep_time = random.uniform(0.5, 1.0)
            time.sleep(sleep_time)

        self.request_times.append(now)

    def _request(self, url: str, params: Optional[Dict] = None):
        if self.should_stop():
            return None

        if not self.can_make_request():
            return None

        try:

            self._rate_limit_control()

            self._increment_request_count()

            response = self.session.get(
                url,
                params=params,
                timeout=settings.request_timeout
            )

            if response.status_code in (403, 429):

                reset_time = int(
                    response.headers.get(
                        "X-RateLimit-Reset",
                        time.time() + 60
                    )
                )

                sleep_time = min(
                    reset_time - int(time.time()),
                    60
                )

                if sleep_time > 0:
                    time.sleep(sleep_time)

                return self._request(url, params)

            response.raise_for_status()

            return response

        except Exception as e:
            logger.error(f"Request error: {e}")
            return None

    def search(self, keyword: str, page: int = 1, per_page: int = 50):

        if self.should_stop():
            return []

        url = f"{self.BASE_URL}/search/repositories"

        params = {
            "q": keyword,
            "per_page": per_page,
            "page": page,
            "sort": "stars",
            "order": "desc"
        }

        response = self._request(url, params=params)

        if response:
            data = response.json()
            return data.get("items", [])

        return []

    def fetch_repo_details_batch(self, repos):

        results = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:

            futures = [
                executor.submit(self._fetch_single_repo, repo)
                for repo in repos
            ]

            for future in as_completed(futures):

                if self.should_stop():
                    break

                result = future.result()

                if result:
                    results.append(result)

        return results

    def _fetch_single_repo(self, repo):

        try:

            owner = repo["owner"]["login"]
            repo_name = repo["name"]

            repo_url = f"{self.BASE_URL}/repos/{owner}/{repo_name}"

            repo_response = self._request(repo_url)

            if not repo_response:
                return None

            repo_detail = repo_response.json()

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

            category = self._simple_category(
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
            logger.error(f"Repo fetch error: {e}")
            return None

    def _simple_category(self, name: str, description: str):

        text = f"{name} {description}".lower()

        if any(k in text for k in ["agent", "llm", "ai"]):
            return "Agent"

        if any(k in text for k in ["tool", "cli"]):
            return "Tool"

        if "framework" in text:
            return "Framework"

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

            return {
                "total_requests": cls._total_requests,
                "max_requests": cls._max_requests,
                "remaining": max(
                    0,
                    cls._max_requests - cls._total_requests
                ),
                "percentage": percentage,
                "should_stop": cls._stop_flag
            }

    def __del__(self):
        if hasattr(self, "session"):
            self.session.close()