#!/usr/bin/env python3
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import Base, db_session_basede26, engine  # noqa: E402
from perf_models import PerfCourse, PerfCourseReview  # noqa: E402

SEED = 8360
N_COURSES = 5000
N_REVIEWS = 200

DEPARTMENTS = ["Data Science", "Computer Science", "Business", "Engineering"]
SUBJECTS = ["DATA", "CS", "BUS", "ENGR", "MATH", "STAT"]
ADJECTIVES = ["Introduction to", "Advanced", "Applied", "Foundations of", "Topics in", "Seminar in"]
TOPICS = [
    "Distributed Systems", "Machine Learning", "Database Systems", "Cloud Computing",
    "Software Engineering", "Data Structures", "Algorithms", "Networks", "Security",
    "Operating Systems", "Statistics", "Linear Algebra", "Optimization", "Robotics",
    "Human-Computer Interaction", "Compilers", "Computer Vision", "Natural Language Processing",
]
COMMENTS = [
    "Great course, learned a lot.", "Workload was heavy but worth it.",
    "Clear lectures and fair grading.", "Could use more practical examples.",
    "Challenging but rewarding.", "Professor was very responsive.",
    "Group projects were well structured.", "Exams were tough but fair.",
]


def main():
    print(f"Creating tables on {engine.url} ...")
    Base.metadata.create_all(bind=engine)
    print("Tables ready: perf_courses, perf_course_reviews")

    rng = random.Random(SEED)
    db = db_session_basede26()
    try:
        existing_courses = db.query(PerfCourse).count()
        if existing_courses >= N_COURSES:
            print(f"perf_courses already has {existing_courses} rows (>= {N_COURSES}); skipping course seed.")
        else:
            to_add = N_COURSES - existing_courses
            print(f"Seeding {to_add} perf_courses rows (SEED={SEED}) ...")
            batch = []
            for i in range(existing_courses, existing_courses + to_add):
                subject = rng.choice(SUBJECTS)
                number = rng.randint(100, 299)
                title = f"{rng.choice(ADJECTIVES)} {rng.choice(TOPICS)}"
                batch.append(PerfCourse(
                    course_title=title,
                    course_code=f"{subject}-{number}-{i:05d}",
                    department=rng.choice(DEPARTMENTS),
                ))
                if len(batch) >= 500:
                    db.bulk_save_objects(batch)
                    db.commit()
                    batch = []
            if batch:
                db.bulk_save_objects(batch)
                db.commit()
            print(f"perf_courses now has {db.query(PerfCourse).count()} rows.")

        existing_reviews = db.query(PerfCourseReview).count()
        if existing_reviews >= N_REVIEWS:
            print(f"perf_course_reviews already has {existing_reviews} rows (>= {N_REVIEWS}); skipping review seed.")
        else:
            course_ids = [row[0] for row in db.query(PerfCourse.id).all()]
            to_add = N_REVIEWS - existing_reviews
            print(f"Seeding {to_add} perf_course_reviews rows, associated with random perf_courses ...")
            reviews = [
                PerfCourseReview(
                    course_id=rng.choice(course_ids),
                    rating=rng.randint(1, 5),
                    comment=rng.choice(COMMENTS),
                )
                for _ in range(to_add)
            ]
            db.bulk_save_objects(reviews)
            db.commit()
            print(f"perf_course_reviews now has {db.query(PerfCourseReview).count()} rows.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
