#!/usr/bin/env python3


import subprocess
from datetime import datetime

CONTAINER, DB = "s8360-mongo", "s8360_doc"
USER = "karthik_demo"

COMMANDS = [
    ("show collections", "db.getCollectionNames().sort()"),
    ("course_documents: sample data",
     'db.course_documents.find({}, {title:1, status:1, category:1, start_date:1, created_at:1}).sort({created_at:1})'),
    ("course_documents: validator",
     'db.getCollectionInfos({name:"course_documents"})[0].options'),
    ("course_documents: invalid insert is rejected by the database",
     'try { db.course_documents.insertOne({title:"Bad", status:"archived", category:"Art", start_date:new Date()}) } '
     'catch (e) { print("MongoServerError code " + e.code + ": " + e.message) }'),
    ("messages: last 4 for the demo user",
     f'db.messages.find({{user_id:"{USER}"}}, {{_id:0, session_id:1, role:1, content:1, created_at:1}}).sort({{created_at:-1}}).limit(4)'),
    ("summaries: session + lifetime summaries",
     f'db.summaries.find({{user_id:"{USER}"}}, {{_id:0, scope:1, session_id:1, text:1, created_at:1}})'),
    ("episodes: extracted facts (embedding vectors hidden, length shown)",
     f'db.episodes.aggregate([{{$match:{{user_id:"{USER}"}}}}, {{$project:{{_id:0, fact:1, importance:1, embedding_dims:{{$size:"$embedding"}}}}}}, {{$limit:5}}])'),
    ("collection sizes", 'db.getCollectionNames().sort().map(n => n + ": " + db[n].countDocuments())'),
]


def run(js: str) -> str:
    cmd = ["docker", "exec", CONTAINER, "mongosh", "--quiet", DB, "--eval", js]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return (result.stdout + result.stderr).rstrip()


def main() -> None:
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===  mongosh evidence ({CONTAINER}, database {DB})")
    for label, js in COMMANDS:
        print(f"\n## {label}\n$ mongosh {DB} --eval '{js}'")
        print(run(js))


if __name__ == "__main__":
    main()
