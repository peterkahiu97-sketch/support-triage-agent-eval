# Support Triage Agent and Trajectory Evaluation Suite

A lightweight Python reference project demonstrating how to build, trace, and evaluate multi step AI agent workflows with strict tool schemas, explicit state tracking, and human in the loop guardrails.

## Architecture Highlights

1. **Strict Tool Schemas and Grounded Arguments**
   Tools require explicit, typed arguments (`order_id`, `amount`, `human_approved`). When required context is missing from the prompt, the planner asks the user for clarification rather than guessing or fabricating parameters.

2. **Explicit State Tracking and Step Limits**
   Verified tool outputs are written to `AgentState.verified_facts` so downstream reasoning steps rely on confirmed data rather than raw prompt assumptions. Every run enforces a `max_steps` ceiling to prevent infinite tool loops.

3. **Human Approval Guardrails**
   High impact actions such as `issue_refund` check for explicit `human_approved` authorization before executing. Unapproved refund attempts are intercepted at the tool boundary and routed to a human review queue.

4. **Step by Step Trajectory Evaluation**
   `eval_traces.py` audits full execution trajectories rather than checking final text alone. It verifies:
   * **Tool ordering:** `lookup_order` always precedes any refund decision.
   * **Policy adherence:** Ineligible orders (`ORD-2099`) never trigger `issue_refund`.
   * **Guardrail enforcement:** Eligible refunds (`ORD-1042`) pause at `BLOCKED_BY_GUARDRAIL` until approved.
   * **No hallucinated tool calls:** Prompts missing an order identifier exit cleanly without calling tools.

## Running Locally

```bash
python agent.py
python eval_traces.py
