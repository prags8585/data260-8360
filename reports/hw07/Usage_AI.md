# AI_USE.md — DATA-260 Homework 7

## 1. What did you use an AI assistant for, and what did you do yourself?

I extended my existing HW4–HW6 project for Homework 7 instead of creating a new copy. I decided to keep the work in the same project, leave everything unpushed until I completed my validation, and use the same report format as the previous homeworks.

I designed the main requirements for the homework, including the JWT migration and role policy, code-quality checks, the agent loop and repair path, the Reflexion module and verifiers, the three tools, the LangGraph agent and UI, the hostile fixtures and attack tests, the file tools, and the safety gate. I used Claude Code to help implement and run these features, tests, `verify_hw07.py`, and the report generator.

For the data-based scenarios, I chose Bay Wheels as the city. I approved downloading one public trip file, `202510-baywheels-tripdata.zip`, and the pricing page. Since the public dataset did not include rider IDs, I decided to construct two rider histories from real trip rows. I was responsible for reviewing the implementation, checking the numbers and outputs, and validating the report before pushing and submitting.

## 2. One AI-produced output that was wrong/unsuitable, or one thing I independently verified

The first versions of the Part 4 agent produced incorrect answers. The Bay Wheels pricing page displayed the rules for five plans in parallel columns, which caused the model to confuse the Day pass’s 30 free minutes with the Month pass’s free-minute allowance. Later versions calculated the correct totals but compared the options in the wrong direction and recommended the more expensive plan.

My first independent recomputation also contained an error. Its regular expression picked up the first “N min free” value on the page, which belonged to the Day pass. Because of this, it produced the same incorrect membership total of `$1,516.72` as the model instead of the correct total of `$1,499.87`.

## 3. How did you detect the problem or verify the result?

I did not rely only on the agent’s figures. I created `bikeshare/reference.py` to recompute the totals, break-even point, and final decision using plain Python from the CSV file and the saved pricing snapshot. The UI also shows whether the agent’s result matches the reference calculation.

The first runs did not match the reference calculation. One scenario had the wrong recommendation, and one break-even result represented the average ride cost instead of the number of rides per month. I found the error in my reference calculation when the scenario-construction script, which used the correct 45-minute rate, produced a different membership total of `$1,499.87` for the same data.

I also performed a citation check against the saved pricing-page text. This identified a quote that the model had incorrectly combined from two separate lists. In addition, the 10-command safety-gate test found a real false allow in the first version of the gate: `sort -o /etc/hosts notes.txt` was incorrectly permitted.

## 4. What did you change and why does it work now?

I changed the retrieval process so it returns complete plan blocks and labels every rule with its corresponding plan. This prevents the model from incorrectly matching rules across the pricing-page columns.

I also moved the total calculations, break-even calculation, and final decision into one SQL template. This reduced the amount of arithmetic and comparison work performed by the model. The model now provides the seven required rates, while the database performs the calculations consistently. I updated the reference implementation to read the Month pass block by position.

After these changes, both acceptance scenarios matched the independent recomputation for the totals and final decision. I describe this as evidence from two temperature-zero runs, not as a measured accuracy rate. The results also showed that an 8B model required this additional retrieval and verification structure.

For the safety gate, I updated `is_destructive()` to inspect output options from allow-listed commands, including `-o`, `--output`, `date -s`, and `uniq IN OUT`, and reject absolute paths when appropriate. The 10-command safety test now passes all 10 cases, and the identified command variants are retained as regression tests.

I also documented two limitations. First, the Part 3 verifier is stricter than the actual facts: it required `course_detail` calls and rejected 10 out of 10 correct case-C answers when the chain guard was disabled. Second, the lint demonstration was run in a temporary worktree so it would not disturb my uncommitted project changes.

## 5. Used Claudd to push the files to my github repo easily.