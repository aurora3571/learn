from sqlalchemy import Column, Integer, String, Float, DateTime
from app.database import Base


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, unique=True)
    description = Column(String)
    url = Column(String)
    category = Column(String)

    stars = Column(Integer)
    forks = Column(Integer)
    open_issues = Column(Integer)
    closed_issues = Column(Integer)
    total_commits = Column(Integer)

    last_commit = Column(DateTime)

    author = Column(String)
    author_followers = Column(Integer)

    score = Column(Float)