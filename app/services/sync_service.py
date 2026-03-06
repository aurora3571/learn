from app.services.github_fetcher import GithubFetcher
from app.services.scorer import Scorer
from app.models import Skill
from sqlalchemy.orm import Session


class SyncService:

    def __init__(self, db: Session):
        self.db = db
        self.fetcher = GithubFetcher()

    # 在 app/services/sync_service.py 中修改 sync 方法

def sync(self):
    keywords = ["claude-mcp", "agent-tools", "codex-skills", "ai-agent", "llm-agent"]
    all_data = []

    # 1. 从 GitHub 抓取数据
    for keyword in keywords:
        repos = self.fetcher.search(keyword)
        for repo in repos:
            details = self.fetcher.fetch_repo_details(repo)
            # 确保关键数字字段正确
            details["stars"] = repo.get("stargazers_count", 0)
            details["forks"] = repo.get("forks_count", 0)
            all_data.append(details)

    # 2. 计算评分
    scored_data = Scorer(all_data).calculate()

    # 3. 获取数据库表允许的字段
    allowed_fields = Skill.__table__.columns.keys()
    
    updated_count = 0
    inserted_count = 0

    # 4. 遍历处理每一条数据
    for item in scored_data:
        # 过滤掉 Scorer 产生的临时字段（如 *_norm）
        clean_item = {k: v for k, v in item.items() if k in allowed_fields}
        
        # 关键修复：先查询是否存在
        existing_skill = self.db.query(Skill).filter(
            Skill.name == clean_item["name"]
        ).first()
        
        if existing_skill:
            # 如果存在，则更新所有字段
            for key, value in clean_item.items():
                setattr(existing_skill, key, value)
            updated_count += 1
        else:
            # 如果不存在，则创建新记录
            new_skill = Skill(**clean_item)
            self.db.add(new_skill)
            inserted_count += 1
    
    # 5. 提交事务（只有这一步会写入数据库）
    self.db.commit()
    
    # 6. 打印统计信息（会显示在 Vercel 日志中）
    print(f"✅ 同步完成: 新增 {inserted_count} 条, 更新 {updated_count} 条")