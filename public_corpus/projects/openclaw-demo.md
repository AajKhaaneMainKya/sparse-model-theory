# OpenClaw Demo

The OpenClaw demo exposes an open-ended chat-style interface at `/openclaw/agent` while keeping execution bounded. It accepts messages, supports `/think`, `/followup`, and optionally `/capture`, and returns compact replies from agentic analysis.

The implementation documents explicit boundaries: no shell or tool execution, no web access, no outbound messaging, no arbitrary file reads, no schema-note writes, and no automatic `anchor_type` inference. The public value is the separation between an open-ended interface and controlled execution.

This is evidence that Rahul has worked on agentic systems where the model interface feels flexible but the backend contract remains constrained.
