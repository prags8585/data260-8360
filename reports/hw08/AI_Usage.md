# AI_USE.md — DATA-260 Homework 8

## 1. What did you use an AI assistant for, and what did you do yourself?

I extended my existing HW1–HW7 repository for Homework 8 instead of creating a separate project. I decided to keep the same report format as the previous homeworks and leave everything unpushed until I had reviewed and validated the changes.

I used Claude Code to assist with implementing and running the Kafka request/response client, worker, FastAPI wrapper and the report generator.

I made the main design and testing decisions. I reviewed the written code, checked the raw outputs and report numbers, examined the Kafka behavior, investigated incorrect results alongside with AI to resolve faster.

## 2. One AI-produced output that was wrong/unsuitable, or one thing I independently verified

The first end-to-end run of the three-agent pipeline produced an incorrect answer that the Reviewer still approved. The question asked which department had the most available seats and which course in that department had the most seats. The Writer answered Data Science and `DATA-245`, but `DATA-245` had 35 seats while `DATA-260` had 40 seats.

The Writer had only received department-level totals and did not have the individual course seat counts in its prompt, so it guessed the course. The Reviewer only checked whether the course code existed in the catalogue and did not verify whether it was actually the course with the most seats.

The first version of my Part 3 failure-test harness also reported an incorrect result. In the “consumer killed” test, it said the message was redelivered after the restart for the unfixed Writer, even though the restarted Writer had not produced a draft. The harness had matched a log line from the first run instead of the restarted run.

## 3. How did you detect the problem or verify the result?

I compared the final JSON with the catalogue facts provided to the Writer. This showed that the individual course seat counts were missing from the Writer’s prompt. I also noticed that the same answer was returned for three different questions, so I investigated the running processes.

That investigation showed that an older Reviewer process from before my fix was still running in the same consumer group and approving drafts. My original `pkill` pattern searched for lowercase “python,” but macOS displayed the process name as “Python,” so the old process was not stopped.

For the harness problem, the output contradicted itself: it reported `redelivered: True` while also showing `drafts: 0` and consumer-group lag of 0. I did not rely only on the Writer’s log. I checked the Kafka broker’s consumer-group state using `kafka-consumer-groups.sh --describe` before and after the process was killed, and I counted the drafts that actually reached the drafts topic.

## 4. What did you change and why does it work now?

I updated the Writer so it receives the full course list using the existing HW5 `search_courses` and `course_stats` tools. I also added a `superlative_correct` check to the Reviewer so it recomputes the department with the most available seats and the top course in that department from the same facts.

With these changes, the correct answer—Data Science and `DATA-260` with 40 seats—is approved. Incorrect or invented answers are rejected. For example, a second question about Dr. Nair’s available seats was rejected because the model stated 75 seats while the source facts showed 70. I also stopped all older agent processes by PID before running the final tests.

I fixed the failure-test harness so it requires the second occurrence of the “received task” log line after the restart. The final results now agree with the Kafka broker: with early auto-commit, the consumer-group lag was 0 after the process was killed and the message was lost. With commit-after-processing, the lag was 1, the message was redelivered, and exactly one draft was produced.

I also documented the following limitations. The Kafka broker uses a single node with a replication factor of 1. At-least-once delivery combined with the idempotency check provides effectively-once results only when the Writer does not crash between sending the draft and recording the `correlation_id`; that small failure window still exists. The unkeyed message-ordering result is random, so the exact inversion count changes between runs. Finally, keying messages by course code places most of the seeded data on one partition, which causes one Writer to receive more work than the other.

## 5. Used Claudd to push the files to my github repo easily.