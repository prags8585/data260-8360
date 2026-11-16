# AI_USE.md — DATA-260 Homework 10

## 1. What did you use an AI assistant for, and what did you do yourself?

I extended my existing HW1–HW9 repository for Homework 10 and kept the same report format as before.

I implemented and ran the span-tracing system, including the span writer and instrumentation for the ingress, Planner, Writer, and Reviewer. I took help my AI to implement the evaluator, DeepEval GEval judge wrapper, Streamlit dashboard, experiment scripts, offline tests, and report generator.

I made the main evaluation decisions myself. I manually assigned all 20 human helpfulness labels using the written rubric and the labeling page. I also decided that the labels would remain frozen after the judge was run. I reviewed the raw outputs, examined the judge’s reasons, audited the results against the assignment requirements, and checked the numbers in the report.

## 2. One AI-produced output that was wrong/unsuitable, or one thing I independently verified

Several problems were identified during implementation and evaluation.

First, the older HW8 and HW9 test files wrote spans with fake trace IDs such as `"a"`, `"c1"`, and `"good"` into the real span file because tracing had been enabled for every caller.

Second, the first version of the failed-trace summary incorrectly identified the `request` span as the failing stage. The actual root cause was the Writer. The `request` and `agent_round_trip` spans failed only because no answer was returned.

Third, one timing measurement did not match the pipeline behavior. The Writer took approximately 1.3 seconds when tested alone but approximately 7.9 seconds inside the full pipeline.

Fourth, the Final-vs-Draft score appeared to show an improvement in some requests even though the final answer was exactly the same as the draft. Finally, I found that some of my first human labels were not consistent with my own rubric.

An additional audit identified two problems. The evaluator did not store the Kafka metadata for the messages it scored. Also, a rerun under heavy machine load scored only 43 of 50 requests because one request took 350 seconds and the evaluator’s Kafka consumer was removed from its group after exceeding the default 300-second poll limit.

## 3. How did you detect the problem or verify the result?

I found the fake trace IDs by inspecting the IDs stored in the span file. For the failed trace, I reviewed the span table in chronological order and confirmed that the first error span was not necessarily the root cause.

For the Writer timing, I did not rely on the initial 1.3-second measurement because it came from repeating the same question, which allowed Ollama to use its prompt cache. I tested the Writer with new prompts that it had not previously seen and inspected Ollama’s prefill and generation timings. This showed approximately 7.7 seconds of prefill for 690 tokens. My first probe was also affected by caching, so I rewrote it to use two separate sets of new questions.

For the Final-vs-Draft comparison, I compared the actual texts and confirmed that they were identical. Because the judge runs deterministically at temperature 0, the one-point difference came from the criteria being worded differently rather than from random variation.

I also audited each assignment requirement against the implementation and the saved evidence. For the human labels, Claude Code compared my initial labels with the rubric and identified cases that appeared inconsistent. I reread the rubric and changed some labels myself. The final values remained my own, and the labeling page recorded the time associated with each label.

The report statistics can be recomputed from the saved per-case data, and `verify_hw10.py` performs that verification.

## 4. What did you change and why does it work now?

I updated the tests so that their spans are written to a temporary file instead of the real span file. I also changed the failed-stage logic so it selects the first stage that fails, excluding the `request` and `agent_round_trip` wrapper spans. I added a test to verify this behavior.

The evaluator now stores the topic, partition, offset, and timestamp for every message it scores, along with the exact criteria text used by the judge. I also increased the consumer poll interval so it is longer than the longest possible judge run. The missing requests from the failed rerun were scored afterward, and their scores matched the original results.

The latency values reported in the main table come from the first run, which was performed when the machine was relatively quiet and had a median evaluation latency of 30 seconds. I kept the separate rerun under heavy system load as additional evidence; it had a median latency of 39 seconds and a maximum of 350 seconds.

The results showed that the judge did not agree strongly with my human labels: Spearman correlation was 0.12 with a p-value of 0.61, and the mean absolute difference was 1.45 on the 1–5 scale. The judge was repeatable because it used temperature 0: none of the 20 scores changed across three runs. With sampling enabled, 5 of 20 scores changed. Based on this result, I would not use the judge as the only deployment-gating mechanism.

For latency, the Writer accounted for approximately 69% of a cache miss, with a p50 latency of 7.9 seconds, while the Planner accounted for approximately 30%. The Writer was slow because Ollama reread the full catalogue prompt for every new question. In a separate probe, placing the catalogue earlier in the prompt reduced Writer latency from 11.2 seconds to 3.3 seconds. I documented this finding but did not change the production Writer.

I also documented the limitations. The judge uses the same model family as the Writer it evaluates. Twenty examples and one labeler are not enough to validate a judge, and some of my labels disagreed with my own rubric—for example, some drafts that ignored the question received a score of 5—which reduces the measured agreement.

The latency run also shared the machine with other Docker projects, so the absolute times were higher than in HW9. The failed trace was a controlled dependency failure that I created by stopping the MySQL container, not an organically occurring production failure. Finally, the cache-hit trace showed 0.2 seconds for its first lookup because the embedding model was still cold.

## 5. Used Claude Code to push the code to github 
