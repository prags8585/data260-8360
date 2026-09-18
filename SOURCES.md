# SOURCES.md — HW3 Part 2 domain corpus

Domain: DOMAIN_ID=0, Campus Course Catalogue and Enrolment (San José State University).
All 16 documents are real, public SJSU pages relevant to course catalogues, degree/program
requirements, and enrollment policy, fetched live and saved as clean plain text (HTML
chrome and navigation stripped) under `corpus/hw03/`. Access date for all sources below:
**2026-09-18**. Byte sizes and SHA-256 hashes for each file are in `CORPUS_MANIFEST.json`.

| Local file | Source URL |
|---|---|
| `corpus/hw03/data_science_ms_program.txt` | https://catalog.sjsu.edu/preview_program.php?catoid=17&poid=14075 |
| `corpus/hw03/data_analytics_ms_program.txt` | https://catalog.sjsu.edu/preview_program.php?catoid=13&poid=7675 |
| `corpus/hw03/applied_data_intelligence_ms_program.txt` | https://catalog.sjsu.edu/preview_program.php?catoid=17&poid=13784 |
| `corpus/hw03/msds_admission_requirements.txt` | https://www.sjsu.edu/cs/programs/ms-datascience/admission-requirements.php |
| `corpus/hw03/msda_curriculum_courses.txt` | https://sjsu.edu/applied-data-science/msda/curriculum-courses/index.php |
| `corpus/hw03/msds_faq.txt` | https://www.sjsu.edu/cs/programs/ms-datascience/msds-faq.php |
| `corpus/hw03/course_credit_numbering.txt` | https://catalog.sjsu.edu/content.php?catoid=13&navoid=4902 |
| `corpus/hw03/grades_policy.txt` | https://catalog.sjsu.edu/content.php?catoid=15&navoid=5336 |
| `corpus/hw03/graduate_policies_procedures.txt` | https://catalog.sjsu.edu/content.php?catoid=13&navoid=4899 |
| `corpus/hw03/undergraduate_policies_procedures.txt` | https://catalog.sjsu.edu/content.php?catoid=13&navoid=4884 |
| `corpus/hw03/masters_requirements.txt` | https://catalog.sjsu.edu/content.php?catoid=13&navoid=4886 |
| `corpus/hw03/registration_and_attendance.txt` | https://catalog.sjsu.edu/content.php?catoid=13&navoid=4897 |
| `corpus/hw03/adding_dropping_classes.txt` | https://ischool.sjsu.edu/adding-and-dropping-classes |
| `corpus/hw03/general_education_overview.txt` | https://catalog.sjsu.edu/content.php?catoid=10&navoid=661 |
| `corpus/hw03/general_education_requirements_full.txt` | https://catalog.sjsu.edu/content.php?catoid=10&navoid=659 |
| `corpus/hw03/academic_calendar.txt` | https://catalog.sjsu.edu/content.php?catoid=13&navoid=4974 |

## Extraction method

Most pages (`catalog.sjsu.edu`) return an empty response to plain HTTP clients (bot
protection returns HTTP 202 with no body to `curl`/`urllib`), so those were fetched by
navigating a real browser to each URL and extracting the rendered page text directly —
not summarized or paraphrased by an AI model, and not routed through a fetch tool that
processes content through a summarization model. The three `sjsu.edu`-subdomain pages
fetched cleanly via a plain HTTP request; for those, `scripts/fetch_corpus.py` downloads
the raw HTML and strips it to visible text with BeautifulSoup (script tags, nav, header,
footer removed). Total corpus size: 207,022 bytes across 16 files (minimum required: 200 KB).
