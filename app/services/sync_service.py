from app.services.github_fetcher import GithubFetcher
from app.services.scorer import Scorer
from app.models import Skill
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

        # 1. 从 GitHub 抓取数据
        for keyword in keywords:
            repos = self.fetcher.search(keyword)
            logger.info(f"Found {len(repos)} repos for keyword: {keyword}")
            for repo in repos:
                try:
                    details = self.fetcher.fetch_repo_details(repo)
                    details["stars"] = repo.get("stargazers_count", 0)
                    details["forks"] = repo.get("forks_count", 0)
                    all_data.append(details)
                except Exception as e:
                    logger.error(f"Error fetching details for {repo.get('name')}: {e}")
                    continue

        logger.info(f"Total fetched items: {len(all_data)}")

        # 2. 计算评分
        scored_data = Scorer(all_data).calculate()
        allowed_fields = Skill.__table__.columns.keys()

        updated_count = 0
        inserted_count = 0
        skipped_count = 0

        # 3. 遍历处理每一条数据
        for item in scored_data:
            try:
                # 过滤字段
                clean_item = {k: v for k, v in item.items() if k in allowed_fields}
                
                if 'name' not in clean_item:
                    logger.warning(f"Item missing name field, skipping: {item}")
                    skipped_count += 1
                    continue

                # 先查询是否存在
                existing_skill = self.db.query(Skill).filter(
                    Skill.name == clean_item["name"]
                ).first()
                
                if existing_skill:
                    # 如果存在，更新所有字段
                    for key, value in clean_item.items():
                        setattr(existing_skill, key, value)
                    updated_count += 1
                    logger.debug(f"Updated: {clean_item['name']}")
                else:
                    # 如果不存在，创建新记录
                    new_skill = Skill(**clean_item)
                    self.db.add(new_skill)
                    inserted_count += 1
                    logger.debug(f"Inserted: {clean_item['name']}")
                    
                # 每处理10条数据提交一次，避免事务过大
                if (inserted_count + updated_count) % 10 == 0:
                    self.db.flush()
                    
            except Exception as e:
                logger.error(f"Error processing item {item.get('name', 'unknown')}: {e}")
                self.db.rollback()
                continue
        
        # 最终提交
        try:
            self.db.commit()
            logger.info(f"✅ Sync completed: {inserted_count} inserted, {updated_count} updated, {skipped_count} skipped")
            return {
                "inserted": inserted_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "total": inserted_count + updated_count
            }
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"IntegrityError during commit: {e}")
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error during commit: {e}")
            raise