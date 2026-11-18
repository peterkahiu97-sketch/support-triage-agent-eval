import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


@dataclass
class TraceStep:
    step: int
    thought: str
    tool_name: str
    tool_args: Dict[str, Any]
    observation: str
    status: str


@dataclass
class AgentState:
    user_query: str
    max_steps: int = 5
    verified_facts: Dict[str, Any] = field(default_factory=dict)
    traces: List[TraceStep] = field(default_factory=list)
    completed: bool = False
    final_answer: str = ""


# --- Simulated Domain Tools ---

def lookup_order(order_id: str) -> Dict[str, Any]:
    mock_orders = {
        "ORD-1042": {"status": "delayed", "amount": 145.00, "eligible_for_refund": True},
        "ORD-2099": {"status": "delivered", "amount": 49.99, "eligible_for_refund": False},
    }
    return mock_orders.get(order_id, {"error": f"Order {order_id} not found"})


def issue_refund(order_id: str, amount: float, human_approved: bool = False) -> Dict[str, Any]:
    if not human_approved:
        return {
            "status": "BLOCKED_BY_GUARDRAIL",
            "reason": "Refunds require explicit human approval before execution.",
        }
    return {"status": "SUCCESS", "order_id": order_id, "refunded_amount": amount}


TOOLS: Dict[str, Callable[..., Any]] = {
    "lookup_order": lookup_order,
    "issue_refund": issue_refund,
}


class SupportTriageAgent:
    """Deterministic demo agent showcasing tool schemas, state tracking, and guardrails."""

    def __init__(self, require_human_approval: bool = True):
        self.require_human_approval = require_human_approval

    def plan_next_action(self, state: AgentState) -> Dict[str, Any]:
        # Step 1: Extract order ID and fetch verified order state first
        if "order_data" not in state.verified_facts:
            order_id = next(
                (word.strip(".,!?") for word in state.user_query.split() if word.startswith("ORD-")),
                "",
            )
            if not order_id:
                return {
                    "thought": "No order ID found in prompt. Ask user for order ID instead of guessing.",
                    "action": "final_answer",
                    "answer": "Please provide your order ID (for example, ORD-1042) so I can check its status.",
                }
            return {
                "thought": f"Look up verified order record for {order_id} before taking any action.",
                "action": "tool_call",
                "tool_name": "lookup_order",
                "tool_args": {"order_id": order_id},
            }

        order_data = state.verified_facts["order_data"]
        order_id = state.verified_facts["order_id"]

        # Handle missing order cleanly
        if "error" in order_data:
            return {
                "thought": "Order lookup returned an error. Report clearly without hallucinating.",
                "action": "final_answer",
                "answer": f"I could not locate {order_id}. Please double check the order number.",
            }

        # Step 2: Check refund eligibility and apply human approval guardrail
        if "refund" in state.user_query.lower():
            if not order_data.get("eligible_for_refund"):
                return {
                    "thought": "Order is not eligible for an automated refund per policy.",
                    "action": "final_answer",
                    "answer": f"Order {order_id} was already delivered and is not eligible for an automatic refund.",
                }

            if "refund_result" not in state.verified_facts:
                approved = not self.require_human_approval
                return {
                    "thought": "Order is eligible for refund. Attempting refund tool with guardrail check.",
                    "action": "tool_call",
                    "tool_name": "issue_refund",
                    "tool_args": {
                        "order_id": order_id,
                        "amount": order_data["amount"],
                        "human_approved": approved,
                    },
                }

            refund_result = state.verified_facts["refund_result"]
            if refund_result.get("status") == "BLOCKED_BY_GUARDRAIL":
                return {
                    "thought": "Guardrail paused refund execution. Escalate to human reviewer.",
                    "action": "final_answer",
                    "answer": (
                        f"Order {order_id} (${order_data['amount']:.2f}) is eligible for a refund. "
                        "I have queued this request for human approval before processing the payout."
                    ),
                }

            return {
                "thought": "Refund completed after approval. Confirm with user.",
                "action": "final_answer",
                "answer": f"Refund of ${refund_result['refunded_amount']:.2f} issued for {order_id}.",
            }

        return {
            "thought": "Provide verified order status to user.",
            "action": "final_answer",
            "answer": f"Order {order_id} is currently {order_data['status']}.",
        }

    def run(self, user_query: str) -> AgentState:
        state = AgentState(user_query=user_query)

        for step_num in range(1, state.max_steps + 1):
            plan = self.plan_next_action(state)

            if plan["action"] == "final_answer":
                state.completed = True
                state.final_answer = plan["answer"]
                state.traces.append(
                    TraceStep(
                        step=step_num,
                        thought=plan["thought"],
                        tool_name="NONE",
                        tool_args={},
                        observation=plan["answer"],
                        status="COMPLETED",
                    )
                )
                break

            tool_name = plan["tool_name"]
            tool_args = plan["tool_args"]
            tool_fn = TOOLS.get(tool_name)

            if not tool_fn:
                state.traces.append(
                    TraceStep(
                        step=step_num,
                        thought=plan["thought"],
                        tool_name=tool_name,
                        tool_args=tool_args,
                        observation="Unknown tool error",
                        status="ERROR",
                    )
                )
                break

            result = tool_fn(**tool_args)

            # Update verified state cleanly
            if tool_name == "lookup_order":
                state.verified_facts["order_id"] = tool_args["order_id"]
                state.verified_facts["order_data"] = result
            elif tool_name == "issue_refund":
                state.verified_facts["refund_result"] = result

            state.traces.append(
                TraceStep(
                    step=step_num,
                    thought=plan["thought"],
                    tool_name=tool_name,
                    tool_args=tool_args,
                    observation=json.dumps(result),
                    status=result.get("status", "OK"),
                )
            )

        if not state.completed:
            state.final_answer = "Stopped: maximum step limit reached without resolution."

        return state


if __name__ == "__main__":
    agent = SupportTriageAgent(require_human_approval=True)
    result_state = agent.run("My order ORD-1042 is delayed, please issue a refund.")
    for t in result_state.traces:
        print(f"[Step {t.step}] {t.thought} -> {t.tool_name}({t.tool_args}) => {t.observation}")
    print("\nFinal Response:", result_state.final_answer)
