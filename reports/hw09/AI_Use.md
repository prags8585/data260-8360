# AI_USE.md — DATA-260 Homework 9

## 1. What did you use an AI assistant for, and what did you do yourself?

I extended my existing HW1–HW8 repository for Homework 9. I continued using the same report format as the previous homeworks and decided that nothing would be pushed or tagged until I had reviewed and validated the changes myself.

I implemented and ran the Redis view counter, semantic cache and FastAPI ingress, threshold-sweep scripts, two-agent self-improving system, offline tests, and report generator.

I took help from AI to make some main design and evaluation decisions, including which cases to include in `cache_cases.yaml`, requiring the file to be committed before running any sweep, fixing the cost-model values before the sweep, and defining the rule for keeping a learned lesson. I reviewed the code, examined the raw output files, and compared every number in the report with the underlying results.

## 2. One AI-produced output that was wrong/unsuitable, or one thing I independently verified

Three issues occurred during the implementation and evaluation.

First, my HW8 Reviewer rejected a correct answer. For the question “Which course has the most available seats?”, the Writer answered `CS-146` with 50 seats, which was correct. However, the Reviewer rejected it because its check assumed that every “most seats” question referred to the best course within the department with the most available seats. That logic incorrectly selected Data Science and `DATA-260`, which has 40 seats. This issue appeared in HW9 because the cache demo included a plain course-level question.

Second, my first threshold sweep was not usable. At thresholds 0.90 and 0.95, many misses took approximately 240 seconds, which matched the agent timeout. The Mac had about 8 GB of swap in use and a load average above 30. Kafka consumers lost their group membership, the Writer process crashed, and the pipeline did not complete normally.

Third, my first Part 4 question sets were too easy. The Answering Agent answered all 14 of 14 training questions correctly, so the system had no meaningful failure from which to learn. The Evaluator also marked one correct answer—“The tuition is not provided in the course catalogue.”—as incorrect because my decline-phrase list did not include the phrase “not provided.”

## 3. How did you detect the problem or verify the result?

For the Reviewer issue, I compared the rejected draft with the MySQL rows. The database showed that `CS-146` had 50 seats, the highest number among all six courses, so the answer was correct and the Reviewer’s logic was wrong.

For the threshold sweep, I inspected the individual case latencies in `threshold_sweep.json` instead of relying only on the summary table. The reported mean latency of 132 seconds at threshold 0.95 was not believable because the individual values were close to 240 seconds. The Writer log also ended with `UNKNOWN_MEMBER_ID` and a traceback.

The hit, miss, and false-hit counts were not affected by the timing problem, but the latency measurements were invalid because the pipeline had not completed normally. With permission, the `airbnb-project` containers were stopped to free memory, and I reran all five thresholds from scratch. I kept the discarded run as `threshold_sweep_run1_invalid.json`.

For Part 4, I reviewed the 14 baseline answers individually and manually checked the one reported failure. After correcting the decline-phrase list, I created harder question sets involving opinion-based questions and totals across the full catalogue. I created these questions before running the test set, so I did not tune them based on their results.

## 4. What did you change and why does it work now?

I updated the Reviewer so that `expected_extreme()` determines the expected answer based on the type of superlative question being asked: course-level, department-level, or course-level within a department. I also added offline tests covering these different question types.

After rerunning the threshold sweep, miss latency averaged approximately 4 to 5 seconds at every threshold, with the slowest individual call taking 10 seconds. The rerun completed without timeouts.

Using the preset costs of `$0.01` per miss, `$0.0001` per hit, and `$1.00` per false hit, the cheapest threshold was 0.95. If the false-hit cost were only equal to the cost of one miss, the cheapest threshold would be 0.80. At threshold 0.95, there were still 2 false hits out of 20 because “most” and “fewest” differ by only one word and their embeddings had a similarity of 0.97.

The stale-answer test showed that the cache returned 40 seats after the database value had changed to 12. I fixed this by adding a data-version check, which prevents the stale result at the cost of one additional MySQL read per cache hit.

For Part 4, the baseline answered 10 of 18 test questions correctly. Evaluator repair improved this to 18 of 18. The unvalidated lessons answered 17 of 18 correctly, while the validated lesson answered all 18 correctly.

Validation rejected the “total over all courses” lesson because it caused a validation question that previously passed to fail. The test set confirmed that rejecting this lesson was the correct decision because the unvalidated version lost one question.

I also documented the limitations. The Evaluator is deterministic and has access to the correct answers, so its 18-of-18 result represents an upper bound; a model-based judge would likely be weaker. Lesson loading by embedding similarity is also loose: the one retained lesson was loaded for 13 answers, including questions where it was not relevant. In one case, it caused a correct answer to begin with “The catalogue cannot judge.”

The validation gate contains only 12 questions. A deliberately over-broad lesson that I tested was not rejected by the gate, so I removed it and it is not included in `lessons.json`. Finally, the cost model uses assumed prices rather than measured prices, and the 40 labeled cases are a small sample based on a six-course catalogue.

## 5. Used Claude to assist with writing the code, running the experiments, and preparing the files for review. I reviewed the implementation and results, and nothing was pushed or tagged before my review.

## 6. Used Claudd to push the files to my github repo easily.