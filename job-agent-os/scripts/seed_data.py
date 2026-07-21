"""Seed database with test user and sample jobs.

Usage:
    python scripts/seed_data.py
"""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from job_agent_os.core.security import hash_password
from job_agent_os.models import Base  # noqa: F401
from job_agent_os.models.job import Job
from job_agent_os.models.user import User
from job_agent_os.settings import get_settings

# Sample jobs data
SAMPLE_JOBS = [
    {
        "title": "Java后端开发工程师",
        "company": "中原银行",
        "company_type": "国企",
        "location": "郑州",
        "industry": "金融",
        "source_platform": "boss",
        "source_url": "https://www.zhipin.com/job_detail/example1.html",
        "raw_description": "负责核心银行系统后端开发，使用Java/Spring Boot技术栈，参与微服务架构设计。",
        "salary_range": "10K-18K",
        "salary_min": 10,
        "salary_max": 18,
        "education_required": "本科",
        "skills_required": ["Java", "Spring Boot", "MySQL", "Redis", "微服务"],
        "job_type": "校招",
    },
    {
        "title": "Python开发工程师",
        "company": "中国移动河南分公司",
        "company_type": "央企",
        "location": "郑州",
        "industry": "通信",
        "source_platform": "guopin",
        "source_url": "https://www.guopin.com/job/example2.html",
        "raw_description": "负责数据平台开发，使用Python进行数据处理和分析，参与AI应用落地。",
        "salary_range": "12K-20K",
        "salary_min": 12,
        "salary_max": 20,
        "education_required": "硕士",
        "skills_required": ["Python", "数据分析", "机器学习", "SQL"],
        "job_type": "校招",
    },
    {
        "title": "前端开发工程师",
        "company": "阿里巴巴",
        "company_type": "民企",
        "location": "杭州",
        "industry": "互联网",
        "source_platform": "boss",
        "source_url": "https://www.zhipin.com/job_detail/example3.html",
        "raw_description": "负责ToB产品前端开发，使用React/TypeScript，参与组件库建设。",
        "salary_range": "18K-30K",
        "salary_min": 18,
        "salary_max": 30,
        "education_required": "本科",
        "skills_required": ["React", "TypeScript", "Node.js", "Webpack"],
        "job_type": "校招",
    },
    {
        "title": "算法工程师",
        "company": "字节跳动",
        "company_type": "民企",
        "location": "北京",
        "industry": "互联网",
        "source_platform": "niuke",
        "source_url": "https://www.nowcoder.com/jobs/example4.html",
        "raw_description": "负责推荐系统算法优化，使用深度学习模型提升推荐效果。",
        "salary_range": "25K-45K",
        "salary_min": 25,
        "salary_max": 45,
        "education_required": "硕士",
        "skills_required": ["Python", "PyTorch", "推荐系统", "NLP", "深度学习"],
        "job_type": "校招",
    },
    {
        "title": "Go后端开发工程师",
        "company": "腾讯",
        "company_type": "民企",
        "location": "深圳",
        "industry": "互联网",
        "source_platform": "boss",
        "source_url": "https://www.zhipin.com/job_detail/example5.html",
        "raw_description": "负责腾讯云产品后端开发，使用Go语言，参与高并发系统设计。",
        "salary_range": "20K-35K",
        "salary_min": 20,
        "salary_max": 35,
        "education_required": "本科",
        "skills_required": ["Go", "分布式系统", "Kubernetes", "MySQL"],
        "job_type": "校招",
    },
]


async def seed_database() -> None:
    """Seed database with test data."""
    settings = get_settings()
    print(f"Connecting to database: {settings.database_url.split('@')[-1]}")

    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            # 1. Create test user
            print("\nSeeding users...")
            test_user = User(
                id=uuid4(),
                username="demo_user",
                email="demo@jobagentos.com",
                password_hash=hash_password("demo123456"),
                phone="13800138000",
                preferences={"theme": "dark", "language": "zh-CN"},
                job_intentions=[
                    {"region": "河南", "direction": "Java", "company_type": "国企"}
                ],
                status="active",
            )
            session.add(test_user)
            await session.flush()
            print(f"  ✓ User created: {test_user.username} ({test_user.email})")

            # 2. Create sample jobs
            print("\nSeeding jobs...")
            for job_data in SAMPLE_JOBS:
                job = Job(
                    id=uuid4(),
                    content_hash=f"seed_{uuid4().hex[:16]}",
                    crawled_at=datetime.now(UTC),
                    **job_data,
                )
                session.add(job)
                print(f"  ✓ Job created: {job.title} @ {job.company}")

            await session.commit()
            print(f"\n✅ Seed complete! Created 1 user + {len(SAMPLE_JOBS)} jobs")
            print("\nTest credentials:")
            print("  Email: demo@jobagentos.com")
            print("  Password: demo123456")

    except Exception as e:
        print(f"\n❌ Seed failed: {e}")
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_database())
