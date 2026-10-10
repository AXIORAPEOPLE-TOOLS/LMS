from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import Department, User
from app.modules.knowledge.models import KnowledgeCategory
from testkit import UserFactory


@dataclass
class Hub:
    support: Department
    hr: Department
    support_cat: KnowledgeCategory
    support_sops: KnowledgeCategory
    hr_cat: KnowledgeCategory
    meera: User  # support lead (manager), owner
    anil: User  # backup (manager)
    dev: User  # manager in another team
    admin: User  # knowledge admin
    head: User  # support function head


@pytest.fixture
async def hub(session: AsyncSession, make_user: UserFactory) -> Hub:
    support, hr = Department(name="Support"), Department(name="HR")
    session.add_all([support, hr])
    await session.commit()
    head = await make_user("function_head", full_name="Sunita Head", department_id=support.id)
    support_cat = KnowledgeCategory(name="Support", position=0, head_id=head.id)
    hr_cat = KnowledgeCategory(name="HR", position=1)
    session.add_all([support_cat, hr_cat])
    await session.flush()
    support_sops = KnowledgeCategory(name="Support SOPs", parent_id=support_cat.id)
    session.add(support_sops)
    await session.commit()
    return Hub(
        support=support, hr=hr, support_cat=support_cat, support_sops=support_sops, hr_cat=hr_cat,
        meera=await make_user("manager", full_name="Meera Kapoor", department_id=support.id),
        anil=await make_user("manager", full_name="Anil Rao", department_id=support.id),
        dev=await make_user("manager", full_name="Dev Patel", department_id=hr.id),
        admin=await make_user("knowledge_admin", full_name="Kavya Admin"),
        head=head,
    )
