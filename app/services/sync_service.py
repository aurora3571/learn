from app.services.github_fetcher import GithubFetcher
from app.services.scorer import Scorer
from app.models import Skill
from sqlalchemy.orm import Session


class SyncService:

    def __init__(self, db: Session):
        self.db = db
        self.fetcher = GithubFetcher()

    def sync(self):

        keywords = [
            "claude-mcp",
            "agent-tools",
            "codex-skills",
            "ai-agent",
            "llm-agent"
        ]

        all_data = []

        for keyword in keywords:

            repos = self.fetcher.search(keyword)

            for repo in repos:

                details = self.fetcher.fetch_repo_details(repo)

                # 强制确保 stars forks 正确
                details["stars"] = repo.get("stargazers_count", 0)
                details["forks"] = repo.get("forks_count", 0)

                all_data.append(details)

        scored_data = Scorer(all_data).calculate()

        # 获取数据库字段
        allowed_fields = Skill.__table__.columns.keys()

        for item in scored_data:

            # 过滤 scorer 产生的 *_norm 字段
            clean_item = {
                k: v for k, v in item.items()
                if k in allowed_fields
            }

            skill = self.db.query(Skill).filter(
                Skill.name == clean_item["name"]
            ).first()

            if not skill:

                skill = Skill(**clean_item)

                self.db.add(skill)
            else:

                for key, value in clean_item.items():
                    setattr(skill, key, value)

        self.db.commit()