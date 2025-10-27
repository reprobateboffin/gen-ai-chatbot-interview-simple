from langgraph.graph import StateGraph, END
from langgraph.checkpoint.redis import RedisSaver
from langgraph.checkpoint.memory import MemorySaver
from typing import List, Dict, Optional, TypedDict
import redis
from utils import safe_generate


class InterviewState(TypedDict, total=False):
    job_title: Optional[str]
    user_response: Optional[str]
    messages: List[Dict[str, str]]
    context: List[str]
    max_steps: int
    step: int
    thread_id: str
    waiting_for_user: bool


def startup_node(state: InterviewState):
    if state.get("step", 0) > 0:
        return state

    question = safe_generate(
        f"Generate ONLY the first interview question about {state['job_title']}.",
        "Intrstng",
    )
    state["messages"].append({"role": "interviewer", "text": question})
    state["step"] = 1
    state["waiting_for_user"] = True
    return state


def followup_node(state: InterviewState):
    if state.get("user_response"):
        state["messages"].append({"role": "candidate", "text": state["user_response"]})

        conversation_history = "\n".join(
            [f"{m['role']}: {m['text']}" for m in state["messages"]]
        )
        next_question = safe_generate(
            f"Based on this conversation, generate ONLY the next follow-up question:\n{conversation_history}",
            "nyahh",
        )

        state["messages"].append({"role": "interviewer", "text": next_question})
        state["step"] = state.get("step", 0) + 1
        state["user_response"] = None
        state["waiting_for_user"] = True

    return state


def feedback_node(state: InterviewState):
    if state.get("user_response"):
        state["messages"].append({"role": "candidate", "text": state["user_response"]})
        state["user_response"] = None

    conversation_history = "\n".join(
        [f"{msg['role']}: {msg['text']}" for msg in state["messages"]]
    )

    feedback = safe_generate(
        f"Based on this complete interview conversation, provide detailed feedback on the candidate's performance.\n\nFull Conversation:\n{conversation_history}",
        "feedback",
    )

    state["messages"].append({"role": "system", "text": feedback})
    state["feedback"] = feedback
    state["waiting_for_user"] = False
    return state


def should_continue(state: InterviewState):
    if state.get("waiting_for_user", False):
        return END
    elif state.get("step", 0) >= state.get("max_steps", 3):
        return "feedback"
    else:
        return "followup"


def create_graph():
    graph = StateGraph(InterviewState)
    graph.add_node("startup", startup_node)
    graph.add_node("followup", followup_node)
    graph.add_node("feedback", feedback_node)

    graph.set_entry_point("startup")
    graph.add_conditional_edges(
        "startup",
        should_continue,
        {"followup": "followup", "feedback": "feedback", END: END},
    )
    graph.add_conditional_edges(
        "followup",
        should_continue,
        {"followup": "followup", "feedback": "feedback", END: END},
    )
    graph.add_conditional_edges("feedback", lambda x: END)

    try:
        redis_client = redis.Redis(
            host="localhost", port=6379, decode_responses=True, db=0
        )
        memory = RedisSaver(redis_client)
    except Exception:
        memory = MemorySaver()

    return graph.compile(checkpointer=memory)


compiled_graph = create_graph()
