# Domain Schema — Campus Course Catalogue and Enrolment

**DOMAIN_ID:** 0
**Entity:** Course

## Fields

| Field | Type | Required | Role |
|---|---|---|---|
| courseTitle | text | yes | Primary field — the course's title |
| courseCode | text | yes | Secondary field — the course's catalogue code |
| email | email | yes | Submitter's email address |
| description | textarea | yes | Content field — course description (must be > 25 characters) |
| department | select (dropdown) | yes | Category selection |
| agreeTerms | checkbox | yes | Agreement to terms and conditions |

## Category values (department dropdown)

- Computer Science
- Data Science
- Business
- Engineering

## Example record

```json
{
  "courseTitle": "Introduction to Distributed Systems",
  "courseCode": "DATA-260",
  "email": "student@sjsu.edu",
  "description": "Covers consensus, replication, partitioning, and fault tolerance in large-scale distributed systems, with hands-on labs.",
  "department": "Data Science",
  "agreeTerms": true
}
```
