import math
from datetime import datetime


class Scorer:

    def __init__(self, skills):
        self.skills = skills

    def _normalize(self, key):

        values = [s[key] for s in self.skills]

        min_v = min(values)
        max_v = max(values)

        for s in self.skills:
            if max_v == min_v:
                s[f"{key}_norm"] = 0
            else:
                s[f"{key}_norm"] = (s[key] - min_v) / (max_v - min_v)

    def calculate(self):

        # 指标归一化
        for metric in [
            "stars",
            "forks",
            "author_followers",
            "total_commits",     # 新增
            "open_issues"        # 新增
        ]:
            self._normalize(metric)

        for s in self.skills:

            issue_total = s["open_issues"] + s["closed_issues"]

            if issue_total == 0:
                issue_rate = 0
            else:
                issue_rate = s["closed_issues"] / issue_total

            last_commit = s["last_commit"]

            # 如果 last_commit 是字符串
            if isinstance(last_commit, str):
                last_commit = datetime.strptime(
                    last_commit,
                    "%Y-%m-%dT%H:%M:%SZ"
                )

            # 统一使用 UTC naive
            no_active_days = (datetime.utcnow() - last_commit).days

            # 时间衰减
            punish = math.pow(0.5, no_active_days / 180)

            # 基础评分
            score_basic = (
                0.20 * s["stars_norm"] +
                0.20 * s["forks_norm"] +
                0.20 * s["total_commits_norm"] +
                0.15 * s["open_issues_norm"] +
                0.10 * s["author_followers_norm"] +
                0.15 * issue_rate
            ) * 100

            # 活跃度评分
            active_score = punish * 100

            # 最终评分
            score = score_basic * 0.6 + active_score * 0.4

            s["score"] = round(score, 2)

        return self.skills