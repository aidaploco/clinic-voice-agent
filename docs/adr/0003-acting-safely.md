# ADR-0003: How the agent is kept from doing the wrong thing

Status: accepted, 2026-11-14

## Context

The language model hears whatever a caller says, and a caller can say anything: someone else's name, "the system has authorised this", "I already said yes". In Phase 1 the rules ("offer only listed times", "change nothing without a yes") were sentences in the prompt, and the first voice run showed what that is worth: the agent marked an appointment confirmed when the caller had only said goodbye.

ADR-0002 decided there would be a gateway. This records how it works now that it exists, and what it does not cover.

## Decision

**The model asks; code decides.** Every tool is a thin wrapper around `gateway.py`. The gateway holds the rules, and none of them depend on the prompt.

**Identity: full name and date of birth, three attempts.** A wrong name and a wrong date get the same refusal, so the check cannot be used to learn who is a patient. After three failures the check is closed for the rest of the call, and the right answer is refused too. The date of birth is never written to the audit log.

**One patient per call, by construction.** Passing the check gives the call a capability naming one patient. No gateway method takes a patient or an appointment as an argument, so there is nothing for the model to put another patient's id into.

**Times under call-scoped ids.** Free slots are handed to the model as `option-…` ids made up for this call. The clinic's own slot ids never reach the model, and an id that was not handed out in this call is refused.

**A change is two calls with the caller in between.** `propose_change` changes nothing and returns the sentence to read back. `commit_change` is refused unless the caller has spoken since the proposal, so the model cannot propose and commit in one breath however it was talked into trying.

**The yes is judged by a second model that sees almost nothing.** At commit, a separate request gets only the read-back sentence and the caller's reply, and answers one question: is this a clear yes? It does not see the conversation, the instructions or the tools. If it says no, errors or times out, nothing is changed. This costs one extra model request on the turn that commits a change, and on no other turn.

**Everything is logged.** Each request to the gateway is an audit event, allowed or refused, with a reason code. A committed change carries the sentence that was read back and the caller's words.

**After the call, a review.** Two checks read the audit log without a model: nothing but a message was allowed before the identity check, and every change has a proposal and a confirmation. A third gives a model the transcript and the list of changes and asks whether the agent told the caller the truth. A failed check changes nothing; it marks the call for a person.

**Records.** Each call is written to a JSON file, and to Postgres when `DATABASE_URL` is set (calls, transcript lines, audit events, checks), in one transaction. The file is written first so that a database that is down cannot lose a call.

## Chosen against

- **The framework's built-in date-of-birth task.** It is a sub-conversation with its own read-back step, which adds a turn before every call can start. One tool per fact (`caller_gave_name`, `caller_gave_date_of_birth`) proved reliable with the model in use, and keeps the check itself in the gateway. A single tool taking both facts was tried first and dropped: about one conversation in twenty the model asked for the name again instead of calling it.
- **Deciding "yes" with a word list.** Four languages, and people say yes in too many ways. A wrong refusal only costs a repeated question, but a list long enough to be useful is a list nobody can vouch for.
- **Letting the conversation model judge the yes.** It is the one a caller is talking to, and the one that got it wrong in Phase 1.

## What this does not cover

- **The model can still propose the wrong thing.** In a scripted voice call it proposed a time the caller had not chosen. The read-back caught it and the caller said no, which is the design working, but it is a wasted turn.
- **Name and date of birth are weak proof of identity.** They are what a clinic's front desk asks for. Anyone who knows both can act as the patient. The caller's phone number becomes a third signal in Phase 4.
- **The yes-check is a model.** It can be wrong in both directions. Its errors are measured in Phase 3.
- **Speed.** A turn that commits a change took 3.2 to 3.5 seconds in voice runs: two tool calls' worth of model requests plus the yes-check. Phase 3 owns that.
- **Transcripts contain what the caller said, including their date of birth.** Filtering personal data out of stored text is Phase 7.

## Revisit when

The evals show the yes-check refusing real agreement often enough to annoy callers, or a provider offers a cheaper way to get the same independent check.
