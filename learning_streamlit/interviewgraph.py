# from typing import List, Dict, Optional, TypedDict
# from utils import safe_generate
# from langgraph.graph import END


# class InterviewState(TypedDict, total=False):
#     job_title: Optional[str]
#     user_response: Optional[str]
#     messages: List[Dict[str, str]]
#     context: List[str]
#     max_steps: int
#     step: int


# def startup_node(state: InterviewState):
#     print("Startup node ran")
#     question = safe_generate(
#         f"Generate ONLY the first interview question about {state['job_title']}.",
#         "Intrstng",
#     )
#     state.setdefault("messages", []).append({"role": "interviewer", "text": question})
#     return {"messages": state["messages"]}


# def followup_node(state: InterviewState):
#     print("Followup node ran")
#     if state.get("user_response"):
#         state.setdefault("messages", []).append(
#             {"role": "user", "text": state["user_response"]}
#         )

#     state["step"] = state.get("step", 0) + 1
#     if state["step"] >= state.get("max_steps", 3):
#         return {"messages": state["messages"], "step": state["step"]}

#     history_text = "\n".join(f"{m['role']}: {m['text']}" for m in state["messages"])
#     next_q = safe_generate(
#         f"Conversation history:\n{history_text}\nGenerate ONLY the next follow-up question.",
#         "nya",
#     )
#     state["messages"].append({"role": "interviewer", "text": next_q})
#     return {"messages": state["messages"], "message": next_q, "step": state["step"]}


# def rate_questions_node(state: InterviewState):
#     print("Feedback node ran")
#     history_text = "\n".join(
#         m["role"] + ": " + m["text"]
#         for m in state.get("messages", [])
#         if m["role"] != "system"
#     )
#     feedback = safe_generate(
#         f"Provide detailed feedback on this conversation:\n{history_text}", "nyahh"
#     )
#     state["messages"].append({"role": "system", "text": feedback})
#     return {"messages": state["messages"], "feedback": feedback}


# def followup_condition(state: InterviewState):
#     if state.get("step", 0) >= state.get("max_steps", 3):
#         return "feedback"
#     return END


# from langgraph.graph import StateGraph, END
# from langgraph.checkpoint.memory import InMemorySaver

# # Create graph
# graph = StateGraph(InterviewState)
# graph.add_node("startup", startup_node)
# graph.add_node("followup", followup_node)
# graph.add_node("feedback", rate_questions_node)
# graph.add_edge("startup", END)
# graph.add_conditional_edges(
#     "followup", followup_condition, {"feedback": "feedback", END: END}
# )
# graph.add_edge("feedback", END)
# graph.set_entry_point("startup")
# from redis_client import RedisSaver

# # Global checkpointer and compiled graph
# redis_saver = RedisSaver()  # GLOBAL
# compiled_graph = graph.compile(checkpointer=redis_saver)  # GLOBAL

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.redis import RedisSaver
from typing import List, Dict, Optional, TypedDict
from fastapi import FastAPI, Form
from pydantic import BaseModel
import uuid
from utils import safe_generate  # Your custom question generation function


# -------------------
# --- State Typing ---
# -------------------
class InterviewState(TypedDict, total=False):
    job_title: Optional[str]
    user_response: Optional[str]
    messages: List[Dict[str, str]]
    context: List[str]
    max_steps: int
    step: int
    thread_id: str


# -------------------
# --- Node Definitions ---
# -------------------
def startup_node(state: InterviewState):
    question = safe_generate(
        f"Generate ONLY the first interview question about {state['job_title']}.",
        "Intrstng",
    )
    state["messages"].append({"role": "interviewer", "text": question})
    print(f"startup node running... first question: {question}")
    return {"messages": state["messages"]}


def followup_node(state: InterviewState):
    if state.get("user_response"):
        state["messages"].append({"role": "candidate", "text": state["user_response"]})

    current_step = state.get("step", 0) + 1
    state["step"] = current_step

    if current_step >= state.get("max_steps", 3):
        return {"messages": state["messages"], "step": current_step}

    history_text = "\n".join([f"{m['role']}: {m['text']}" for m in state["messages"]])
    next_q = safe_generate(
        f"Conversation history:\n{history_text}\nGenerate ONLY the next follow-up question.",
        "nyahh",
    )
    state["messages"].append({"role": "interviewer", "text": next_q})
    print(f"followup node running... next question: {next_q}")
    return {"messages": state["messages"], "step": current_step, "message": next_q}


def feedback_node(state: InterviewState):
    history_text = "\n".join([f"{m['role']}: {m['text']}" for m in state["messages"]])
    feedback = safe_generate(
        f"Provide detailed feedback on this interview:\n{history_text}", "feedback"
    )
    state["messages"].append({"role": "system", "text": feedback})
    print(f"feedback node running...")
    return {"messages": state["messages"], "feedback": feedback}


def followup_condition(state: InterviewState):
    return (
        "feedback" if state.get("step", 0) >= state.get("max_steps", 3) else "followup"
    )


# -------------------
# --- Graph Setup ---
# -------------------
graph = StateGraph(InterviewState)
graph.add_node("startup", startup_node)
graph.add_node("followup", followup_node)
graph.add_node("feedback", feedback_node)

graph.add_edge("startup", "followup")
graph.add_conditional_edges(
    "followup", followup_condition, {"feedback": "feedback", "followup": "followup"}
)
graph.add_edge("feedback", END)

graph.set_entry_point("startup")

# -------------------
# --- Redis Checkpointer ---
# -------------------
memory = RedisSaver.from_conn_string("redis://localhost:6379")
compiled_graph = graph.compile(checkpointer=memory)

# -------------------
# --- FastAPI Setup ---
# -------------------
app = FastAPI()


class ContinueRequest(BaseModel):
    user_response: str
    thread_id: str


@app.post("/start_interview")
async def start_interview(job_title: str = Form(...)):
    thread_id = str(uuid.uuid4())

    # Invoke with thread_id and checkpoint_ns
    state = compiled_graph.invoke(
        {"job_title": job_title, "messages": [], "step": 0, "max_steps": 3},
        start_at="startup",
        configurable={
            "thread_id": thread_id,
            "checkpoint_ns": "interview",
        },
    )

    return {
        "thread_id": thread_id,
        "status": "ongoing",
        "message": state["messages"][-1]["text"],
    }


@app.post("/continue_interview")
async def continue_interview(req: ContinueRequest):
    # Invoke with same thread_id and checkpoint_ns
    state = compiled_graph.invoke(
        {"user_response": req.user_response},
        start_at="followup",
        configurable={
            "thread_id": req.thread_id,
            "checkpoint_ns": "interview",
        },
    )

    if "feedback" in state:
        return {
            "thread_id": req.thread_id,
            "status": "completed",
            "message": state["feedback"],
        }

    return {
        "thread_id": req.thread_id,
        "status": "ongoing",
        "message": state["messages"][-1]["text"],
    }
