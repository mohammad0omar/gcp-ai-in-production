# Postmortem: <short title>

This is a blameless postmortem. We describe what the system and the process allowed, not who made a mistake. People acted on the information they had.

- Date of incident: YYYY-MM-DD
- Author and reviewers:
- Status: draft | reviewed | closed
- Severity:

## Summary

Two or three sentences. What broke, for whom, for how long, and how it ended.

## Timeline

All times in UTC. Link a trace, log query or revision name for each line.

| Time | Event | Evidence |
|---|---|---|
| hh:mm | Change deployed (revision name) | Audit log entry |
| hh:mm | First wrong behaviour | Trace ID |
| hh:mm | Alert or report received | |
| hh:mm | Cause found | |
| hh:mm | Rollback deployed (revision name) | |
| hh:mm | Behaviour confirmed normal | |

## Impact

Who was affected and how. Count them with a log query, do not estimate.
For example: number of refused refunds, number of customers sent to a human, money not refunded or refunded wrongly.

## Detection

How did we find out? An alert, a dashboard, a customer, a person reading logs?
How long between the change and the first signal? What would have made it shorter?

## Root cause

What was true in the system that made this possible? Use "why" five times if it helps.
Separate the trigger (the change) from the cause (the missing check, test or limit).

## What went well

Things that limited the damage. For example: the hard refund limit, the currency check, the one log line per tool call, the fast rollback.

## What went badly

Things that made it slower or worse.

## Where we got lucky

Things that could have made it worse but did not.

## Action items

Each item has one owner and a date. No item without an owner.

| Action | Type (prevent, detect, mitigate) | Owner | Due | Link |
|---|---|---|---|---|
| | | | | |

## Lessons

What should other teams copy or avoid?
