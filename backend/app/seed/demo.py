"""Demo company (sheets 15-19 style). Everything here is invented test data.

Sign in with any of these (password: Demo@1234):
  admin@example.com    L&D admin, knowledge admin, expert, reviewer
  manager@example.com  Admissions team manager
  asha@example.com     Admissions Counsellor (the learner from the UI deck)
  meera@example.com    Support lead, subject expert, knowledge owner
"""

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.modules.assessments.models import SkillTest, TestInvite, TestQuestion
from app.modules.certificates.models import Certificate
from app.modules.gamification.models import Badge, Challenge, PointEntry, UserBadge
from app.modules.identity.models import Department, User
from app.modules.knowledge.models import (
    KnowledgeCategory,
    KnowledgeItem,
    KnowledgeListRow,
    KnowledgeReview,
    KnowledgeVersion,
)
from app.modules.learning.models import Assignment, Course, CourseQuestion, Invitation, Lesson, LiveSession
from app.modules.pathways.models import Pathway, PathwayItem
from app.modules.skills.models import CareerMove, JobRole, RoleSkill, Skill, SkillLevel
from app.modules.workflows.defaults import ensure_default_workflows
from app.shared.clock import today, utcnow

PASSWORD = "Demo@1234"

DEPARTMENTS = ["Admissions", "Support", "Partnerships", "Student Success", "Engineering", "People", "Finance", "Sales"]

SKILLS: list[tuple[str, str, str, bool]] = [
    ("ADM-COUN", "Admissions counselling", "Role", False),
    ("LEAD-QUAL", "Education lead qualification", "Role", False),
    ("TELESALES", "Telesales & outbound calling", "Role", False),
    ("CRM", "CRM discipline", "Tools", False),
    ("CAREER-COUN", "Career & course counselling", "Role", False),
    ("VERBAL", "Verbal communication", "Core", False),
    ("CUST-ORIENT", "Customer orientation", "Core", False),
    ("DPDP", "Data privacy (DPDP) compliance", "Compliance", True),
    ("POSH", "POSH awareness", "Compliance", True),
    ("ETHICS", "Ethics & code of conduct", "Compliance", True),
    ("CUST-COMM", "Customer communication", "Core", False),
    ("WRITTEN", "Written communication", "Core", False),
    ("TIME", "Time management", "Core", False),
    ("COACHING", "Coaching & feedback", "Leadership", False),
    ("NEGOTIATION", "Negotiation", "Role", False),
    ("COMPLAINTS", "Complaint resolution & service recovery", "Role", False),
    ("SYS-DESIGN", "System design", "Technical", False),
    ("PAYROLL", "Payroll processing", "Role", False),
]

ROLES: dict[str, tuple[str, int, dict[str, int]]] = {
    "Admissions Counsellor": (
        "Admissions",
        2,
        {
            "ADM-COUN": 3,
            "LEAD-QUAL": 3,
            "TELESALES": 3,
            "CRM": 2,
            "CAREER-COUN": 2,
            "VERBAL": 2,
            "CUST-ORIENT": 2,
            "DPDP": 2,
            "POSH": 2,
            "ETHICS": 2,
            "CUST-COMM": 3,
            "WRITTEN": 2,
            "TIME": 2,
        },
    ),
    "Senior Admissions Counsellor": (
        "Admissions",
        3,
        {
            "ADM-COUN": 4,
            "LEAD-QUAL": 4,
            "TELESALES": 3,
            "CRM": 3,
            "CAREER-COUN": 3,
            "VERBAL": 3,
            "DPDP": 3,
            "POSH": 2,
            "CUST-COMM": 4,
            "COACHING": 3,
            "NEGOTIATION": 3,
        },
    ),
    "Admissions Team Leader": (
        "Admissions",
        4,
        {"ADM-COUN": 4, "COACHING": 4, "NEGOTIATION": 3, "DPDP": 3, "POSH": 3, "CUST-COMM": 4, "TIME": 3},
    ),
    "Student Success Executive": (
        "Student Success",
        2,
        {"CUST-ORIENT": 3, "CUST-COMM": 3, "CAREER-COUN": 2, "DPDP": 2, "POSH": 2, "WRITTEN": 2},
    ),
    "Inside Sales Executive": (
        "Sales",
        2,
        {"TELESALES": 3, "LEAD-QUAL": 3, "CRM": 3, "NEGOTIATION": 2, "DPDP": 2, "POSH": 2, "VERBAL": 3},
    ),
    "Customer Success Manager": (
        "Partnerships",
        3,
        {"CUST-ORIENT": 4, "CUST-COMM": 4, "NEGOTIATION": 3, "DPDP": 2, "POSH": 2, "COACHING": 2},
    ),
    "Customer Support Executive": (
        "Support",
        2,
        {"CUST-COMM": 3, "COMPLAINTS": 3, "WRITTEN": 3, "CRM": 2, "DPDP": 2, "POSH": 2, "ETHICS": 2},
    ),
    "Customer Support Team Lead": ("Support", 3, {"CUST-COMM": 4, "COMPLAINTS": 4, "COACHING": 3, "DPDP": 3, "POSH": 2}),
    "Software Engineer": ("Engineering", 2, {"SYS-DESIGN": 3, "WRITTEN": 2, "DPDP": 3, "POSH": 2, "TIME": 2}),
    "HR Executive": ("People", 2, {"PAYROLL": 3, "POSH": 3, "DPDP": 3, "WRITTEN": 3, "ETHICS": 3}),
}

CAREER_MOVES = [
    ("Admissions Counsellor", "Senior Admissions Counsellor", "vertical"),
    ("Senior Admissions Counsellor", "Admissions Team Leader", "vertical"),
    ("Admissions Counsellor", "Student Success Executive", "lateral"),
    ("Admissions Counsellor", "Inside Sales Executive", "lateral"),
    ("Admissions Counsellor", "Customer Success Manager", "lateral"),
    ("Customer Support Executive", "Customer Support Team Lead", "vertical"),
    ("Customer Support Executive", "Student Success Executive", "lateral"),
]

PEOPLE: list[tuple[str, str, str]] = [
    ("Riya Sharma", "Admissions", "Admissions Counsellor"),
    ("Karan Mehta", "Support", "Customer Support Executive"),
    ("Neha Thakur", "Admissions", "Admissions Counsellor"),
    ("Dev Patel", "Student Success", "Student Success Executive"),
    ("Ishaan Rao", "Admissions", "Admissions Counsellor"),
    ("Pooja Nair", "Support", "Customer Support Executive"),
    ("Vikram Singh", "Partnerships", "Customer Success Manager"),
    ("Ananya Iyer", "Admissions", "Admissions Counsellor"),
    ("Rahul Saxena", "People", "HR Executive"),
    ("Priya Natarajan", "People", "HR Executive"),
    ("Arjun Kulkarni", "Engineering", "Software Engineer"),
    ("Sneha Reddy", "Engineering", "Software Engineer"),
    ("Aditya Joshi", "Sales", "Inside Sales Executive"),
    ("Kavya Menon", "Sales", "Inside Sales Executive"),
    ("Rohit Bansal", "Support", "Customer Support Executive"),
    ("Divya Pillai", "Student Success", "Student Success Executive"),
    ("Manish Gupta", "Admissions", "Senior Admissions Counsellor"),
    ("Shreya Das", "Partnerships", "Customer Success Manager"),
    ("Nikhil Verma", "Engineering", "Software Engineer"),
    ("Tanvi Shah", "Admissions", "Admissions Counsellor"),
    ("Harsh Agarwal", "Sales", "Inside Sales Executive"),
    ("Meghna Bose", "Support", "Customer Support Executive"),
    ("Siddharth Jain", "Student Success", "Student Success Executive"),
    ("Lavanya Krishnan", "People", "HR Executive"),
    ("Anil Rao", "Support", "Customer Support Team Lead"),
    ("Anita Desai", "People", "HR Executive"),
    ("Varun Malhotra", "Finance", "HR Executive"),
    ("Ritika Chopra", "Admissions", "Admissions Counsellor"),
    ("Gaurav Kapoor", "Engineering", "Software Engineer"),
    ("Isha Bhatt", "Partnerships", "Customer Success Manager"),
]

COMM_QUESTIONS = [
    (
        "A customer is upset about a late delivery. What do you do first?",
        [
            "Explain why delivery was late",
            "Acknowledge the problem and apologise",
            "Offer a discount straight away",
            "Pass the call to your manager",
        ],
        1,
        "People calm down when they feel heard first.",
    ),
    (
        "A parent asks a question you cannot answer. What is best?",
        ["Guess the answer", "Say you will check and call back by a set time", "Change the topic", "Ask them to email"],
        1,
        "A clear promise with a time builds trust.",
    ),
    (
        "Which closing line is clearest?",
        ["Let me know.", "I will send the fee details by 4 pm today.", "We will see.", "Call us anytime."],
        1,
        "Specific next steps avoid confusion.",
    ),
    (
        "A student speaks quickly and you miss details. You…",
        ["Pretend you understood", "Politely ask them to repeat the key part", "End the call", "Write what you think they said"],
        1,
        "Checking understanding prevents mistakes.",
    ),
    (
        "Best way to start an outbound call?",
        [
            "Start with the price",
            "Greet, say who you are and why you are calling",
            "Ask for their budget",
            "Read the script fast",
        ],
        1,
        "A clear opening earns attention.",
    ),
]

PRIVACY_QUESTIONS = [
    (
        "A colleague asks for a student's phone number for a personal reason. You…",
        ["Share it", "Refuse; personal data is only for its stated purpose", "Share if they promise", "Ask your friend"],
        1,
        "DPDP: use personal data only for the purpose it was collected for.",
    ),
    (
        "Where should student documents be stored?",
        ["Personal email", "The approved CRM / drive", "WhatsApp", "Desktop folder"],
        1,
        "Only approved systems.",
    ),
    (
        "You sent a fee sheet to the wrong person. First step?",
        ["Ignore it", "Report it to the data protection contact at once", "Delete your sent mail", "Wait a week"],
        1,
        "Breaches must be reported quickly.",
    ),
    (
        "Consent must be…",
        ["Assumed", "Clear, informed and recorded", "Verbal only", "Given by a manager"],
        1,
        "DPDP needs clear consent.",
    ),
]

POSH_QUESTIONS = [
    (
        "What does POSH stand for?",
        [
            "Prevention of Sexual Harassment",
            "Policy on Staff Hiring",
            "Protection of Staff Health",
            "Procedure on Safety at Home",
        ],
        0,
        "The POSH Act, 2013.",
    ),
    (
        "Who can file a complaint?",
        ["Only women employees", "Any aggrieved woman at the workplace", "Only managers", "Only HR"],
        1,
        "Includes interns, visitors and contract staff.",
    ),
    (
        "Who handles complaints?",
        ["Your manager", "The Internal Committee (IC)", "The police only", "IT"],
        1,
        "Every workplace with 10+ people needs an IC.",
    ),
    (
        "Is a joke with sexual meaning harassment?",
        ["Never", "It can be, if unwelcome", "Only in writing", "Only at events"],
        1,
        "Unwelcome conduct is what matters.",
    ),
    (
        "Time limit to file a complaint?",
        ["1 week", "3 months (extendable)", "1 year", "No limit"],
        1,
        "Three months, which the IC can extend.",
    ),
]


def _questions(spec: list[tuple[str, list[str], int, str]], n: int) -> list[tuple[str, list[str], int, str]]:
    return [spec[i % len(spec)] for i in range(n)]


async def seed_if_empty(session: AsyncSession) -> bool:
    await ensure_default_workflows(session)
    if int(await session.scalar(select(func.count()).select_from(User)) or 0) > 0:
        return False
    await seed_demo(session)
    return True


async def seed_demo(session: AsyncSession) -> None:
    rng = random.Random(42)
    pw = hash_password(PASSWORD)
    now, day = utcnow(), today()

    depts = {name: Department(name=name) for name in DEPARTMENTS}
    session.add_all(depts.values())
    skills = {code: Skill(code=code, name=name, category=cat, is_mandatory=mand) for code, name, cat, mand in SKILLS}
    session.add_all(skills.values())
    roles = {
        name: JobRole(code=name.upper().replace(" ", "-")[:40], name=name, family=dept, seniority=sen)
        for name, (dept, sen, _) in ROLES.items()
    }
    session.add_all(roles.values())
    await session.flush()
    for name, (_, _, reqs) in ROLES.items():
        for code, level in reqs.items():
            session.add(RoleSkill(job_role_id=roles[name].id, skill_id=skills[code].id, required_level=level))
    for a, b, kind in CAREER_MOVES:
        session.add(CareerMove(from_role_id=roles[a].id, to_role_id=roles[b].id, kind=kind))

    phones = iter(range(1, 10_000))

    def person(name: str, email: str, dept: str, role: str | None, sys_roles: list[str], **kw: Any) -> User:
        kw.setdefault("phone", f"+91 90000 {next(phones):05d}")  # invented numbers, for simulated WhatsApp
        user = User(
            email=email,
            full_name=name,
            password_hash=pw,
            system_roles=["learner", *sys_roles],
            department_id=depts[dept].id,
            job_role_id=roles[role].id if role else None,
            joined_on=day - timedelta(days=rng.randint(60, 900)),
            **kw,
        )
        session.add(user)
        return user

    admin = person(
        "Kavya Admin",
        "admin@example.com",
        "People",
        None,
        ["admin", "knowledge_admin", "expert", "reviewer"],
        employee_code="E900",
    )
    manager = person(
        "Rohan Mehta",
        "manager@example.com",
        "Admissions",
        "Admissions Team Leader",
        ["manager", "function_head"],
        employee_code="E100",
    )
    meera = person(
        "Meera Kapoor",
        "meera@example.com",
        "Support",
        "Customer Support Team Lead",
        ["manager", "expert", "function_head"],
        employee_code="E001",
    )
    await session.flush()
    asha = person(
        "Asha Verma",
        "asha@example.com",
        "Admissions",
        "Admissions Counsellor",
        [],
        manager_id=manager.id,
        employee_code="E021",
        reminder_window=["11:00", "13:00"],
    )
    depts["Admissions"].head_id = manager.id
    depts["Support"].head_id = meera.id
    people: list[User] = [asha]
    for i, (name, dept, role) in enumerate(PEOPLE):
        mgr = manager.id if dept == "Admissions" else meera.id if dept == "Support" else None
        first = name.split()[0].lower()
        people.append(
            person(
                name,
                f"{first}.{name.split()[-1].lower()}@example.com",
                dept,
                role,
                [],
                manager_id=mgr,
                employee_code=f"E{110 + i}",
            )
        )
    people[4].show_name_on_boards = False  # "A colleague" chose to hide their name
    await session.flush()
    everyone = [admin, manager, meera, *people]

    # ---- skill levels (test scores) ----
    for user in everyone:
        if not user.job_role_id:
            continue
        reqs = {
            rs.skill_id: rs.required_level
            for rs in (await session.scalars(select(RoleSkill).where(RoleSkill.job_role_id == user.job_role_id))).all()
        }
        for skill_id, req in reqs.items():
            if rng.random() < 0.25 and user is not asha:
                continue  # not tested yet
            score = max(5, min(98, int(rng.gauss(55 + req * 6, 15))))
            level = next(lv for ms, lv in reversed([[0, 0], [20, 1], [40, 2], [60, 3], [75, 4], [90, 5]]) if score >= ms)
            session.add(
                SkillLevel(
                    user_id=user.id,
                    skill_id=skill_id,
                    level=level,
                    score=score,
                    previous_level=max(0, level - rng.choice([0, 0, 1])),
                    source="test",
                    assessed_at=now - timedelta(days=rng.randint(1, 80)),
                )
            )
    await session.flush()
    # Asha's profile follows the deck: Level 3 in customer communication (68), gaps in privacy & POSH.
    asha_levels = {
        "CUST-COMM": (3, 68),
        "DPDP": (0, 12),
        "POSH": (1, 25),
        "VERBAL": (0, 15),
        "ETHICS": (1, 30),
        "ADM-COUN": (3, 66),
        "LEAD-QUAL": (3, 64),
        "TELESALES": (3, 70),
        "CRM": (3, 61),
        "CAREER-COUN": (2, 50),
    }
    for sl in (await session.scalars(select(SkillLevel).where(SkillLevel.user_id == asha.id))).all():
        code = next(c for c, s in skills.items() if s.id == sl.skill_id)
        if code in asha_levels:
            sl.level, sl.score = asha_levels[code]
        elif code in {"WRITTEN", "TIME", "CUST-ORIENT"}:
            await session.delete(sl)  # still to check
    await session.flush()

    # ---- tests ----
    tests: dict[str, SkillTest] = {}
    for code, spec, n, extra in [
        ("CUST-COMM", COMM_QUESTIONS, 15, {}),
        ("DPDP", PRIVACY_QUESTIONS, 10, {}),
        ("WRITTEN", COMM_QUESTIONS, 10, {}),
        ("TIME", COMM_QUESTIONS, 8, {}),
        ("CUST-ORIENT", COMM_QUESTIONS, 10, {}),
    ]:
        test = SkillTest(skill_id=skills[code].id, title=skills[code].name, duration_minutes=n, **extra)
        session.add(test)
        await session.flush()
        for pos, (text, options, answer, reason) in enumerate(_questions(spec, n), start=1):
            session.add(
                TestQuestion(
                    test_id=test.id,
                    position=pos,
                    text=text if pos <= len(spec) else f"{text} ({pos})",
                    options=options,
                    answer_index=answer,
                    reason=reason,
                )
            )
        tests[code] = test
    posh_test = SkillTest(
        title="POSH awareness test",
        skill_id=skills["POSH"].id,
        duration_minutes=20,
        proctoring="camera",
        pass_mark=80,
        is_mandatory=True,
        certificate_title="POSH awareness",
        validity_months=12,
        instructions="20 questions. Pass mark 80%. Your camera takes a picture about every 45 seconds.",
    )
    session.add(posh_test)
    await session.flush()
    for pos, (text, options, answer, reason) in enumerate(_questions(POSH_QUESTIONS, 20), start=1):
        session.add(
            TestQuestion(test_id=posh_test.id, position=pos, text=text, options=options, answer_index=answer, reason=reason)
        )
    for code in ("WRITTEN", "TIME"):
        session.add(TestInvite(user_id=asha.id, test_id=tests[code].id, due_on=day + timedelta(days=11)))
    session.add(TestInvite(user_id=asha.id, test_id=tests["CUST-ORIENT"].id, due_on=day + timedelta(days=4)))

    # ---- courses ----
    def course(title: str, code: str | None, lessons: list[tuple[str, str, str]], **kw: Any) -> Course:
        kw.setdefault("duration_minutes", 5 * max(1, len(lessons)))
        c = Course(
            title=title,
            skill_id=skills[code].id if code else None,
            status="published",
            languages=["en", "hi"],
            has_video=True,
            approver_id=admin.id,
            approved_at=now,
            created_by_id=admin.id,
            **kw,
        )
        session.add(c)
        c._lessons = lessons  # type: ignore[attr-defined]
        return c

    privacy = course(
        "Data privacy (DPDP) basics",
        "DPDP",
        [
            ("Why personal data matters", "video", "The DPDP Act protects personal data of students, parents and staff."),
            ("Collect only what you need", "video", "Ask only for the data the admission needs. Record consent."),
            ("Store and share safely", "reading", "Use the CRM and approved drives only. Never personal email or WhatsApp."),
            ("If something goes wrong", "video", "Report a data breach to the data protection contact straight away."),
        ],
        from_level=0,
        to_level=2,
        is_mandatory=True,
        duration_minutes=20,
        description="20 minutes. Plain-language basics.",
    )
    phishing = course(
        "Spotting a phishing email",
        None,
        [
            ("What phishing looks like", "video", "Never share your password with anyone."),
            ("Check the sender", "video", "Look at the real address, not the display name."),
            ("Report it", "reading", "Use the Report button. Do not forward it to colleagues."),
        ],
        duration_minutes=15,
    )
    posh = course(
        "POSH awareness",
        "POSH",
        [
            ("What is workplace harassment", "video", "Unwelcome conduct of a sexual nature at the workplace."),
            ("The Internal Committee", "video", "How the IC works and how to file a complaint."),
            ("Being a good bystander", "reading", "What to do if you see something."),
        ],
        from_level=0,
        to_level=2,
        kind="certification",
        is_mandatory=True,
        duration_minutes=25,
        validity_months=12,
    )
    objection = course(
        "Objection handling for counsellors",
        "ADM-COUN",
        [
            ("Listen first", "video", "Let the parent finish. Note the real concern."),
            ("Answer with facts", "video", "Use placement data and fee plans, not pressure."),
        ],
        from_level=2,
        to_level=3,
    )
    verbal = course(
        "Clear verbal communication",
        "VERBAL",
        [
            ("Speak to be understood", "video", "Short sentences, one idea at a time."),
            ("Check understanding", "video", "Ask the customer to repeat the next step."),
        ],
        from_level=0,
        to_level=2,
    )
    ethics = course(
        "Ethics & code of conduct",
        "ETHICS",
        [
            ("Our code in one page", "reading", "Honesty, respect, privacy, no conflicts of interest."),
        ],
        from_level=1,
        to_level=2,
        kind="certification",
    )
    refund = course(
        "Handling refunds",
        "COMPLAINTS",
        [
            ("Why refunds matter", "video", "Refunds keep customer trust when something goes wrong."),
            ("Check eligibility", "video", "Refunds are allowed within 7 days of delivery."),
            ("Process the refund", "reading", "Approve up to ₹5,000 yourself; above that, ask the team lead."),
        ],
        from_level=2,
        to_level=3,
    )
    await session.flush()
    posh.final_test_id = posh_test.id
    for c in (privacy, phishing, posh, objection, verbal, ethics, refund):
        for pos, (title, kind, text) in enumerate(c._lessons, start=1):  # type: ignore[attr-defined]
            session.add(
                Lesson(
                    course_id=c.id,
                    position=pos,
                    title=title,
                    kind=kind,
                    summary=text,
                    body=text,
                    duration_minutes=5,
                    source_ref=f"Source p.{pos * 2}",
                    captions={"en": [{"at": 0, "text": text}], "hi": [{"at": 0, "text": text}]},
                )
            )
    session.add(
        Lesson(
            course_id=privacy.id,
            position=5,
            title="Practice: store a document safely",
            kind="simulation",
            summary="Tap the steps in the right order.",
            duration_minutes=5,
            scenario={
                "title": "Store a parent's ID proof",
                "ar_supported": True,
                "image": None,
                "steps": [
                    {"id": "s1", "label": "Check consent", "x": 20, "y": 30},
                    {"id": "s2", "label": "Upload to CRM", "x": 70, "y": 45},
                    {"id": "s3", "label": "Delete local copy", "x": 45, "y": 70},
                ],
                "correct_order": ["s1", "s2", "s3"],
                "feedback": "Consent first, then the approved system.",
            },
        )
    )
    session.add(
        Lesson(
            course_id=phishing.id,
            position=4,
            title="Hand hygiene drill",
            kind="simulation",
            summary="Sanitiser first, then gloves.",
            scenario={
                "title": "Before handling documents",
                "ar_supported": True,
                "image": None,
                "steps": [{"id": "a", "label": "Sanitiser", "x": 25, "y": 35}, {"id": "b", "label": "Gloves", "x": 70, "y": 55}],
                "correct_order": ["a", "b"],
                "feedback": "Sanitiser first, then gloves.",
            },
        )
    )
    for c, spec in (
        (privacy, PRIVACY_QUESTIONS),
        (phishing, COMM_QUESTIONS[:3]),
        (verbal, COMM_QUESTIONS),
        (refund, COMM_QUESTIONS[:3]),
        (ethics, PRIVACY_QUESTIONS[:3]),
    ):
        for pos, (text, options, answer, reason) in enumerate(spec, start=1):
            session.add(
                CourseQuestion(course_id=c.id, position=pos, text=text, options=options, answer_index=answer, reason=reason)
            )

    # ---- assignments & certificates ----
    for user in everyone:
        for c, days_due in ((privacy, rng.randint(-10, 20)), (posh, 25 if user is asha else rng.randint(-30, 30))):
            done = rng.random() < 0.7 and user is not asha
            due = day + timedelta(days=days_due)
            completed_at = None
            if done:
                completed_at = datetime.combine(due - timedelta(days=rng.randint(-3, 10)), datetime.min.time(), tzinfo=UTC)
            session.add(
                Assignment(
                    user_id=user.id,
                    course_id=c.id,
                    is_mandatory=True,
                    due_on=due,
                    status="completed" if done else "not_started",
                    progress_pct=100 if done else 0,
                    completed_at=completed_at,
                    source="workflow",
                )
            )
            if done and c is posh:
                session.add(
                    Certificate(
                        user_id=user.id,
                        title="POSH awareness",
                        course_id=posh.id,
                        code=f"C-{now.year}-{rng.randint(1, 999999):06d}",
                        score=rng.randint(80, 100),
                        issued_at=completed_at or now,
                        valid_until=(completed_at or now).date() + timedelta(days=364),
                    )
                )
    asha_privacy = (
        await session.scalars(select(Assignment).where(Assignment.user_id == asha.id, Assignment.course_id == privacy.id))
    ).first()
    if asha_privacy:
        asha_privacy.due_on = day + timedelta(days=(4 - day.weekday()) % 7 or 7)  # due Friday
        asha_privacy.status, asha_privacy.progress_pct = "in_progress", 20
    session.add(
        Certificate(
            user_id=asha.id,
            title="Ethics & code of conduct",
            course_id=ethics.id,
            code=f"C-{now.year}-004217",
            score=90,
            issued_at=now - timedelta(days=40),
            valid_until=day + timedelta(days=320),
        )
    )

    # ---- live session ----
    tuesday = day + timedelta(days=(1 - day.weekday()) % 7 or 7)
    start = datetime.combine(tuesday, datetime.min.time(), tzinfo=UTC) + timedelta(hours=5, minutes=30)  # 11:00 IST
    live = LiveSession(
        title="Objection handling",
        course_id=objection.id,
        trainer_id=meera.id,
        starts_at=start,
        ends_at=start + timedelta(hours=1),
        meeting_link="https://meet.example.com/objection-handling",
        audience_label="Role: Admissions Counsellor",
        created_by_id=admin.id,
        invitations_sent_at=now,
    )
    session.add(live)
    await session.flush()
    for user in [u for u in everyone if u.department_id == depts["Admissions"].id]:
        status = "accepted" if user is asha else rng.choice(["accepted", "accepted", "declined", "pending"])
        session.add(
            Invitation(
                session_id=live.id,
                user_id=user.id,
                status=status,
                batch_id=live.id,
                responded_at=now if status != "pending" else None,
            )
        )

    # ---- Asha's pathway (deck slide 7) ----
    pathway = Pathway(user_id=asha.id, status="active", hours_per_week=3, approved_by_id=manager.id, approved_at=now)
    session.add(pathway)
    await session.flush()
    for wave, pos, code, frm, to, step, c in [
        (1, 1, "DPDP", 0, 2, "learn", privacy),
        (1, 2, "VERBAL", 0, 2, "connect", verbal),
        (1, 3, "ETHICS", 1, 2, "prove", ethics),
        (2, 1, "WRITTEN", 0, 2, "learn", None),
        (2, 2, "CUST-ORIENT", 0, 2, "learn", None),
        (2, 3, "TIME", 0, 2, "learn", None),
        (3, 1, "POSH", 1, 2, "learn", posh),
    ]:
        session.add(
            PathwayItem(
                pathway_id=pathway.id,
                wave=wave,
                position=pos,
                skill_id=skills[code].id,
                from_level=frm,
                to_level=to,
                step=step,
                course_id=c.id if c else None,
                mentor_id=meera.id,
                practise_task="Apply the checklist on a live case this week. Your manager signs it off.",
                estimated_hours=round((to - frm) * 1.8, 1),
                certificate_on_pass=code in {"DPDP", "ETHICS"},
            )
        )

    # ---- points, badges, challenge ----
    badges = [
        ("first_step", "First Step", "Finish your first lesson", {"type": "count", "reason": "lesson", "at_least": 1}),
        ("on_a_roll", "On a Roll", "A 3-day learning streak", {"type": "streak", "days": 3}),
        ("test_ready", "Test Ready", "Finish a skill check", {"type": "count", "reason": "test", "at_least": 1}),
        ("level_up", "Level Up", "Go up a level in any skill", {"type": "count", "reason": "level_up", "at_least": 1}),
        ("certified", "Certified", "Earn a certificate", {"type": "count", "reason": "certificate", "at_least": 1}),
        ("safety_first", "Safety First", "Finish a safety simulation", {"type": "count", "reason": "lesson", "at_least": 5}),
        ("respect_at_work", "Respect at Work", "POSH certificate", {"type": "certificate_title", "contains": "POSH"}),
        ("data_guardian", "Data Guardian", "Data privacy certificate", {"type": "certificate_title", "contains": "privacy"}),
        ("week_warrior", "Week Warrior", "A 7-day streak", {"type": "streak", "days": 7}),
        ("skill_champion", "Skill Champion", "Reach level 5 in a skill", {"type": "max_level", "at_least": 5}),
        ("early_bird", "Early Bird", "Earn 500 points", {"type": "points", "at_least": 500}),
        ("mentor_hand", "Mentor Hand", "Earn 2,500 points", {"type": "points", "at_least": 2500}),
        ("team_player", "Team Player", "Win a team challenge", {"type": "count", "reason": "challenge", "at_least": 1}),
    ]
    badge_rows = {code: Badge(code=code, name=n, description=d, rule=r, position=i) for i, (code, n, d, r) in enumerate(badges)}
    session.add_all(badge_rows.values())
    await session.flush()
    for user in everyone:
        total = 1240 if user is asha else rng.randint(150, 2200)
        given = 0
        stamp = now
        days_back = 0
        while given < total:
            pts = min(rng.choice([10, 10, 20, 30, 50]), total - given)
            minutes = 5 if pts == 10 else 0
            session.add(
                PointEntry(
                    user_id=user.id,
                    points=pts,
                    reason="lesson" if pts == 10 else "test" if pts == 20 else "course" if pts == 30 else "level_up",
                    minutes=minutes,
                    at=stamp,
                )
            )
            given += pts
            days_back += 0 if (user is asha and days_back < 4) else rng.choice([0, 1, 2])
            stamp = now - timedelta(days=min(days_back, 120), hours=rng.randint(0, 6))
        earned = 9 if user is asha else rng.randint(1, 8)
        for code in list(badge_rows)[:earned]:
            session.add(UserBadge(user_id=user.id, badge_id=badge_rows[code].id))
    # Asha: a 5-day streak ending today.
    for d in range(5):
        session.add(PointEntry(user_id=asha.id, points=0, minutes=10, reason="lesson", at=now - timedelta(days=d, hours=1)))
    session.add(
        Challenge(
            title="Team week: finish 80% of assigned items together",
            department_id=depts["Admissions"].id,
            goal_pct=80,
            starts_on=day - timedelta(days=4),
            ends_on=day + timedelta(days=3),
            reward_points=50,
            reward_badge_code="team_player",
            created_by_id=admin.id,
        )
    )

    await _seed_knowledge(session, rng, admin, meera, people, depts, privacy)


async def _seed_knowledge(
    session: AsyncSession,
    rng: random.Random,
    admin: User,
    meera: User,
    people: list[User],
    depts: dict[str, Department],
    refund_course: Course,
) -> None:
    day, now = today(), utcnow()
    by_name = {u.full_name: u for u in [admin, meera, *people]}
    anil, priya, anita, rahul = by_name["Anil Rao"], by_name["Priya Natarajan"], by_name["Anita Desai"], by_name["Rahul Saxena"]
    karan, dev, neha, vikram = by_name["Karan Mehta"], by_name["Dev Patel"], by_name["Neha Thakur"], by_name["Vikram Singh"]

    tree: dict[str, list[str]] = {
        "Company-wide": [],
        "HR": [
            "Payroll & benefits",
            "Forms & templates",
            "Hiring",
            "Compliance (POSH, labour law)",
            "Performance & learning",
            "Policies",
            "Onboarding & exit",
        ],
        "Finance": ["Payments & vendors"],
        "Sales": ["Contracts"],
        "Support": ["Support SOPs", "Escalation"],
        "Tech & Product": ["Runbooks"],
        "Legal": ["Data privacy"],
        "Marketing": [],
        "Operations": [],
    }
    heads = {"HR": anita, "Support": meera, "Finance": by_name["Varun Malhotra"], "Tech & Product": by_name["Arjun Kulkarni"]}
    cats: dict[str, KnowledgeCategory] = {}
    for pos, (root, children) in enumerate(tree.items()):
        parent = KnowledgeCategory(name=root, position=pos, head_id=heads[root].id if root in heads else None)
        session.add(parent)
        await session.flush()
        cats[root] = parent
        for cpos, child in enumerate(children):
            cats[child] = KnowledgeCategory(name=child, parent_id=parent.id, position=cpos)
            session.add(cats[child])
    await session.flush()

    def item(
        title: str,
        kind: str,
        cat: str,
        owner: User | None,
        backup: User | None,
        *,
        due_in: int,
        body: str = "",
        critical: bool = False,
        visibility: str = "company",
        team: str | None = None,
        ver: tuple[int, int] = (1, 0),
        **kw: Any,
    ) -> KnowledgeItem:
        it = KnowledgeItem(
            title=title,
            kind=kind,
            category_id=cats[cat].id,
            owner_id=owner.id if owner else None,
            backup_owner_id=backup.id if backup else None,
            is_critical=critical,
            visibility=visibility,
            team_department_id=depts[team].id if team else None,
            version_major=ver[0],
            version_minor=ver[1],
            body=body or f"{title}. Owned by the {cat} team. Follow the steps and ask the owner if unsure.",
            next_review_on=day + timedelta(days=due_in),
            last_verified_at=now - timedelta(days=max(0, 365 - due_in)),
            status="published",
            **kw,
        )
        session.add(it)
        return it

    refund_body = (
        "1. Check the order date. Refunds are allowed within 7 days of delivery.\n"
        "2. Confirm the reason and ask for a photo for damaged items.\n"
        "3. Approve up to ₹5,000 yourself; above that, ask the team lead.\n"
        "4. Enter the refund in the system and tell the customer the expected date.\n"
        "5. If the answer is no, use the polite refusal script below."
    )
    refund = item(
        "Refund process",
        "sop",
        "Support SOPs",
        meera,
        anil,
        due_in=154,
        body=refund_body,
        ver=(3, 2),
        visibility="team",
        team="Support",
        attachments=[{"name": "Refusal_script.docx"}, {"name": "Refund_flow.png"}],
        linked_course_id=refund_course.id,
    )
    items = [
        refund,
        item("Payroll month-end checklist", "checklist", "Payroll & benefits", priya, anita, due_in=-12, ver=(2, 0)),
        item(
            "POSH complaint process", "sop", "Compliance (POSH, labour law)", anita, rahul, due_in=161, ver=(3, 1), critical=True
        ),
        item("Leave policy 2026", "policy", "Policies", rahul, anita, due_in=154, ver=(4, 0)),
        item(
            "Vendor register",
            "list",
            "Payments & vendors",
            karan,
            None,
            due_in=6,
            ver=(1, 4),
            list_columns=["Vendor", "Service", "Owner", "Renewal", "Status"],
        ),
        item("Escalation playbook", "playbook", "Escalation", meera, anil, due_in=-40, ver=(1, 1)),
        item("Customer contract template", "template", "Contracts", dev, None, due_in=320, ver=(2, 2)),
        item("Data privacy notice", "policy", "Data privacy", neha, None, due_in=200, ver=(2, 0)),
        item("Offer letter template", "template", "Forms & templates", meera, anil, due_in=-12),
        item("Travel policy", "policy", "Policies", meera, anil, due_in=6),
        item("Emergency contacts", "contact_list", "Company-wide", admin, None, due_in=80, critical=True),
        item("Business continuity plan", "policy", "Company-wide", admin, vikram, due_in=120, critical=True),
        item("Data breach steps", "sop", "Data privacy", neha, admin, due_in=30, critical=True),
        item("Customer FAQ 5", "faq", "Support SOPs", None, None, due_in=60),
        item("Escalation scripts", "playbook", "Escalation", None, None, due_in=90),
        item("Server runbook", "playbook", "Runbooks", None, None, due_in=-5),
        item("Hiring checklist", "checklist", "Hiring", anita, None, due_in=-20),
        item("Interview feedback form", "template", "Hiring", anita, None, due_in=-8),
        item("Exit interview form", "template", "Onboarding & exit", priya, None, due_in=100),
        item("Performance review guide", "playbook", "Performance & learning", anita, priya, due_in=40),
        item("Expense claim process", "sop", "Payments & vendors", by_name["Varun Malhotra"], None, due_in=25),
        item("Sales discount policy", "policy", "Contracts", by_name["Aditya Joshi"], None, due_in=-3),
        item("Brand guidelines", "playbook", "Marketing", by_name["Shreya Das"], None, due_in=200),
        item("Office opening checklist", "checklist", "Operations", by_name["Rohit Bansal"], None, due_in=15),
        item("Deployment runbook", "playbook", "Runbooks", by_name["Arjun Kulkarni"], by_name["Gaurav Kapoor"], due_in=70),
        item("Referral policy", "policy", "Policies", rahul, None, due_in=300),
    ]
    await session.flush()
    for it in items:
        session.add(
            KnowledgeVersion(
                item_id=it.id,
                label=it.version_label,
                title=it.title,
                body=it.body,
                change_note="Current version",
                author_id=it.owner_id,
            )
        )
    history = [
        ("3.0", "Added the polite refusal script", True, anil, now - timedelta(days=220)),
        ("3.1", "Fixed a typo in step 4", False, None, now - timedelta(days=170)),
        ("2.0", "Moved to the new refund system", True, meera, now - timedelta(days=330)),
    ]
    for label, note, major, approver, at in history:
        body = refund_body.replace("₹5,000", "₹2,000")
        session.add(
            KnowledgeVersion(
                item_id=refund.id,
                label=label,
                title=refund.title,
                body=body,
                change_note=note,
                is_major=major,
                author_id=meera.id,
                approved_by_id=approver.id if approver else None,
                created_at=at,
            )
        )
    session.add(
        KnowledgeReview(
            item_id=refund.id, reviewer_id=meera.id, note="Still correct. No change.", created_at=now - timedelta(days=125)
        )
    )
    vendors = next(i for i in items if i.title == "Vendor register")
    for pos, row in enumerate(
        [
            ("Zoom", "Meetings", "IT", "Jan 2027", "Active"),
            ("Razorpay", "Payments", "Finance", "Mar 2027", "Active"),
            ("Delhivery", "Shipping", "Ops", "Nov 2026", "Renew"),
            ("Keka", "HR system", "People", "Aug 2027", "Active"),
            ("CloudCo", "Hosting", "IT", "Dec 2026", "Renew"),
        ]
    ):
        session.add(KnowledgeListRow(item_id=vendors.id, position=pos, data=dict(zip(vendors.list_columns, row, strict=True))))
