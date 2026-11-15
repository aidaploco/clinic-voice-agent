# ADR-0001: Use case: a multilingual clinic receptionist

Status: accepted, 2026-11-15

## Context

The project exists to show, in public, how a production-quality voice agent is built: one that takes real phone calls, acts during the call, works in more than one language, and is measured. It must not need real customer data.

## Decision

A fictional physiotherapy clinic, Quillbrook Physio, with a phone receptionist, Emily.

- She answers patients who call, and calls patients about upcoming appointments.
- She can confirm, move or cancel an appointment, take a message, or hand the call to a person.
- She speaks English, Mexican Spanish, Dutch and Bosnian.

All patients, appointments and slots are invented.

## Why this one

- **The work happens during the call.** Moving an appointment needs a lookup and a write while the patient waits, which is where voice agents are hard: hiding the delay, confirming before committing, recovering when the patient changes their mind.
- **Success is checkable.** The appointment either ended up in the right state or it did not, so evals can grade it without opinion.
- **Identity matters.** A clinic must know who it is talking to before it says anything about an appointment, which makes the safety design real rather than decorative.
- **Languages are a fair test.** Spanish and Dutch are well served by speech models; Bosnian much less so. The gap is the interesting part.

## Rejected

- **Customer support for a software product.** Mostly question answering; little that has to be done, and confirmed, mid-call.
- **An open-ended companion or interview agent.** No clear right answer to grade.

## Revisit when

The clinic's mock backend stops being enough to exercise the tools, for example when recurring appointments or several practitioners' calendars are needed.
