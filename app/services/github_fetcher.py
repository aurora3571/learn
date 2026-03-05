import requests
import time
from datetime import datetime
from typing import Dict, Any, List
from app.config import settings


class GithubFetcher:

    BASE_URL = "https://api.github.com"

    def __init__(self):
        self.headers = {
            "Authorization": f"token {settings.github_token}"
        }

    def _request(self, url: str) -> Dict[str, Any]:
        while True:
            response = requests.get(url, headers=self.headers)
            if response.status_code in (403, 429):
                reset = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
                sleep_time = max(reset - int(time.time()), 10)
                time.sleep(sleep_time)
                continue
            response.raise_for_status()
            return response

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}/search/repositories?q={keyword}&per_page=20"
        return self._request(url).json().get("items", [])

    def get_total_commits(self, owner: str, repo: str) -> int:

        # 通过 Link Header 获取 commit 总数

        url = f"{self.BASE_URL}/repos/{owner}/{repo}/commits?per_page=1"
        response = self._request(url)

        if "Link" not in response.headers:
            return 1

        link = response.headers["Link"]
        if 'rel="last"' not in link:
            return 1

        last_page = link.split('rel="last"')[0].split("&page=")[-1].split(">")[0]
        try:
            return int(last_page)
        except:
            return 1

    def fetch_repo_details(self, repo: Dict[str, Any]) -> Dict[str, Any]:

        owner = repo["owner"]["login"]
        repo_name = repo["name"]

        # 使用 Repos API 获取完整仓库信息
        repo_detail_url = f"{self.BASE_URL}/repos/{owner}/{repo_name}"
        repo_detail = self._request(repo_detail_url).json()

        # closed issues
        issues_url = f"{self.BASE_URL}/repos/{owner}/{repo_name}/issues?state=closed&per_page=1"
        closed_issues = len(self._request(issues_url).json())

        # commits
        commits_url = f"{self.BASE_URL}/repos/{owner}/{repo_name}/commits?per_page=1"
        commits_resp = self._request(commits_url).json()
        if commits_resp:
            last_commit = datetime.strptime(
                commits_resp[0]["commit"]["committer"]["date"],
                "%Y-%m-%dT%H:%M:%SZ"
            )
        else:
            last_commit = datetime.utcnow()

        # total commits
        total_commits = self.get_total_commits(owner, repo_name)

        # author
        user_url = f"{self.BASE_URL}/users/{owner}"
        author_info = self._request(user_url).json()

        return {
            "name": repo_detail["name"],
            "description": repo_detail.get("description") or "No description",
            "url": repo_detail["html_url"],
            "category": "Agent",

            "stars": repo_detail.get("stargazers_count", 0),
            "forks": repo_detail.get("forks_count", 0),

            "open_issues": repo_detail.get("open_issues_count", 0),
            "closed_issues": closed_issues,

            "total_commits": total_commits,
            "last_commit": last_commit,

            "author": owner,
            "author_followers": author_info.get("followers", 0)
        }