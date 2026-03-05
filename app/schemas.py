from pydantic import BaseModel
from typing import List
from datetime import datetime


class SkillResponse(BaseModel):

    name: str
    description: str
    url: str
    category: str

    stars: int
    forks: int

    open_issues: int
    closed_issues: int

    total_commits: int

    last_commit: datetime

    author: str
    author_followers: int

    score: float

    class Config:
        orm_mode = True


class SkillListResponse(BaseModel):

    total: int
    items: List[SkillResponse]

    class Config:
        orm_mode = True