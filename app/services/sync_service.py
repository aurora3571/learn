from app.services.github_fetcher import GithubFetcher
from app.services.scorer import Scorer
from app.models import Skill
from sqlalchemy.orm import Session


class SyncService:

    def __init__(self, db: Session):
        self.db = db
        self.fetcher = GithubFetcher()

    def sync(self):  # 确保这个方法名是 sync
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
                details["stars"] = repo.get("stargazers_count", 0)
                details["forks"] = repo.get("forks_count", 0)
                all_data.append(details)

        scored_data = Scorer(all_data).calculate()
        allowed_fields = Skill.__table__.columns.keys()

        updated_count = 0
        inserted_count = 0

        for item in scored_data:
            clean_item = {k: v for k, v in item.items() if k in allowed_fields}
            
            existing_skill = self.db.query(Skill).filter(
                Skill.name == clean_item["name"]
            ).first()
            
            if existing_skill:
                for key, value in clean_item.items():
                    setattr(existing_skill, key, value)
                updated_count += 1
            else:
                new_skill = Skill(**clean_item)
                self.db.add(new_skill)
                inserted_count += 1
        
        self.db.commit()
        print(f"✅ Synced: {inserted_count} inserted, {updated_count} updated")