# # from fastapi import FastAPI, Form
# # from pydantic import BaseModel
# # import uuid
# # from interviewgraph import compiled_graph  # your LangGraph graph

# # app = FastAPI()
# # sessions = {}


# # class ContinueRequest(BaseModel):
# #     user_response: str
# #     thread_id: str


# # @app.post("/start_interview")
# # async def start_interview(job_title: str = Form(...)):
# #     thread_id = str(uuid.uuid4())

# #     # initial state
# #     state = {
# #         "job_title": job_title,
# #         "messages": [],
# #         "step": 0,
# #         "max_steps": 5,
# #     }

# #     # ✅ pass thread_id in config
# #     result = compiled_graph.invoke(
# #         state,
# #         config={"configurable": {"thread_id": thread_id}},
# #         start_at="startup",
# #     )

# #     sessions[thread_id] = result

# #     print(f"--> start_interview: {thread_id}")
# #     return {
# #         "thread_id": thread_id,
# #         "status": "ongoing",
# #         "message": result["messages"][-1]["text"],
# #     }


# # @app.post("/continue_interview")
# # async def continue_interview(req: ContinueRequest):
# #     state = sessions.get(req.thread_id)
# #     if not state:
# #         return {"status": "error", "message": "Invalid thread_id"}

# #     state["user_response"] = req.user_response

# #     # ✅ again, pass thread_id in config
# #     result = compiled_graph.invoke(
# #         state,
# #         config={"configurable": {"thread_id": req.thread_id}},
# #         start_at="followup",
# #     )

# #     sessions[req.thread_id] = result
# #     print(f"--> continue_interview: {req.thread_id}")

# #     if "feedback" in result:
# #         return {"status": "completed", "message": result["feedback"]}

# #     return {"status": "ongoing", "message": result["messages"][-1]["text"]}
# from fastapi import FastAPI, Form
# from pydantic import BaseModel
# import uuid
# from interviewgraph import compiled_graph  # your compiled graph
# from langgraph.checkpoint.redis import RedisSaver

# app = FastAPI()


# class ContinueRequest(BaseModel):
#     user_response: str
#     thread_id: str


# @app.post("/start_interview")
# async def start_interview(job_title: str = Form(...)):
#     thread_id = str(uuid.uuid4())

#     # Invoke with thread_id and checkpoint_ns
#     state = compiled_graph.invoke(
#         {"job_title": job_title, "messages": [], "step": 0, "max_steps": 3},
#         start_at="startup",
#         configurable={
#             "thread_id": thread_id,
#             "checkpoint_ns": "interview",
#         },
#     )

#     return {
#         "thread_id": thread_id,
#         "status": "ongoing",
#         "message": state["messages"][-1]["text"],
#     }


# @app.post("/continue_interview")
# async def continue_interview(req: ContinueRequest):
#     # Invoke with same thread_id and checkpoint_ns
#     state = compiled_graph.invoke(
#         {"user_response": req.user_response},
#         start_at="followup",
#         configurable={
#             "thread_id": req.thread_id,
#             "checkpoint_ns": "interview",
#         },
#     )

#     if "feedback" in state:
#         return {
#             "thread_id": req.thread_id,
#             "status": "completed",
#             "message": state["feedback"],
#         }

#     return {
#         "thread_id": req.thread_id,
#         "status": "ongoing",
#         "message": state["messages"][-1]["text"],
#     }

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.redis import RedisSaver
from langgraph.checkpoint.memory import MemorySaver
from typing import List, Dict, Optional, TypedDict, Literal
from fastapi import FastAPI, Form, HTTPException
from pydantic import BaseModel
import uuid
import redis
from utils import safe_generate


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
    waiting_for_user: bool  # NEW: Track if we're waiting for user input


# -------------------
# --- Node Definitions ---
# -------------------
def startup_node(state: InterviewState):
    # Generate first question based on job title
    if state.get("step", 0) > 0:
        # Already started, just return current state
        return
    question = safe_generate(
        f"Generate ONLY the first interview question about {state['job_title']}. Make it open-ended to start a conversation.",
        "Intrstng",
    )
    state["messages"].append({"role": "interviewer", "text": question})
    state["step"] = 1
    state["waiting_for_user"] = True  # Now we wait for user response
    print(f"STARTUP: Generated first question, now waiting for user")
    return state


def followup_node(state: InterviewState):
    print(f"FOLLOWUP: Starting with step {state.get('step')}")

    # If we have a user response, analyze it and build next question
    if state.get("user_response"):
        # Add user's response to conversation history
        state["messages"].append({"role": "candidate", "text": state["user_response"]})

        # Generate follow-up question based on the conversation so far
        conversation_history = "\n".join(
            [f"{msg['role']}: {msg['text']}" for msg in state["messages"]]
        )

        next_question = safe_generate(
            f"""Based on this interview conversation so far, generate ONLY the next follow-up question.
            
            Conversation History:
            {conversation_history}
            
            Generate a question that:
            1. Builds on the candidate's last answer
            2. Digs deeper into their understanding
            3. Continues the natural flow of conversation
            4. Is specific and interview-focused
            
            Generate ONLY the question, no other text.""",
            "nyahh",
        )

        state["messages"].append({"role": "interviewer", "text": next_question})
        state["step"] = state.get("step", 0) + 1
        state["user_response"] = None  # Clear the response
        state["waiting_for_user"] = True  # Wait for next user response

        print(f"FOLLOWUP: Generated question {state['step']}, now waiting for user")
    else:
        # This shouldn't normally happen, but if no user response, just wait
        state["waiting_for_user"] = True
        print("FOLLOWUP: No user response provided, waiting...")

    return state


def feedback_node(state: InterviewState):
    # Add final user response if provided
    if state.get("user_response"):
        state["messages"].append({"role": "candidate", "text": state["user_response"]})

    # Generate comprehensive feedback based on entire conversation
    conversation_history = "\n".join(
        [f"{msg['role']}: {msg['text']}" for msg in state["messages"]]
    )

    feedback = safe_generate(
        f"""Based on this complete interview conversation, provide detailed feedback on the candidate's performance.

        Full Conversation:
        {conversation_history}

        Provide constructive feedback covering:
        1. Technical knowledge demonstrated
        2. Communication skills
        3. Strengths and areas for improvement
        4. Overall assessment

        Make the feedback detailed and helpful.""",
        "feedback",
    )

    state["messages"].append({"role": "system", "text": feedback})
    state["feedback"] = feedback
    state["waiting_for_user"] = False  # Conversation ended
    print("FEEDBACK: Generated final feedback")
    return state


# -------------------
# --- Graph Routing ---
# -------------------
def should_continue(state: InterviewState):
    current_step = state.get("step", 0)
    max_steps = state.get("max_steps", 3)

    print(
        f"ROUTING: step {current_step} of {max_steps}, waiting_for_user: {state.get('waiting_for_user')}"
    )

    # If we're waiting for user, we should END this execution and wait for next API call
    if state.get("waiting_for_user", False):
        return END

    # Otherwise, decide next node based on step count
    if current_step >= max_steps:
        return "feedback"
    else:
        return "followup"


# -------------------
# --- Graph Setup ---
# -------------------
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

# Checkpointer setup
try:
    redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True, db=0)
    memory = RedisSaver(redis_client)
except Exception as e:
    print(f"Using MemorySaver: {e}")
    memory = MemorySaver()

compiled_graph = graph.compile(checkpointer=memory)

# -------------------
# --- FastAPI ---
# -------------------
app = FastAPI()


class ContinueRequest(BaseModel):
    user_response: str
    thread_id: str


@app.post("/start_interview")
async def start_interview(job_title: str = Form(...)):
    thread_id = str(uuid.uuid4())
    print(f"Starting interview for: {job_title}, thread: {thread_id}")

    config = {"configurable": {"thread_id": thread_id}}

    try:
        # Run only the startup to get first question
        initial_state = {
            "job_title": job_title,
            "messages": [],
            "step": 0,
            "max_steps": 6,  # 3 questions total
            "waiting_for_user": False,
        }

        final_state = compiled_graph.invoke(initial_state, config=config)

        return {
            "thread_id": thread_id,
            "status": "question",
            "message": final_state["messages"][-1]["text"],
            "current_step": final_state["step"],
            "max_steps": final_state["max_steps"],
        }

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/continue_interview")
async def continue_interview(req: ContinueRequest):
    print(f"Continue interview: {req.thread_id}")

    config = {"configurable": {"thread_id": req.thread_id}}

    try:
        # Use stream to see what actually happens
        events = compiled_graph.stream(
            {"user_response": req.user_response, "waiting_for_user": False},
            config=config,
            stream_mode=["values", "updates"],
        )

        final_state = None
        for event_type, event_data in events:
            print(f"Event: {event_type} -> {event_data}")
            if event_type == "values":
                final_state = event_data
            elif event_type == "updates":
                print(f"Update: {list(event_data.keys())}")

        if not final_state:
            final_state = compiled_graph.invoke(
                {"user_response": req.user_response, "waiting_for_user": False},
                config=config,
            )

        print(f"Final state keys: {list(final_state.keys())}")

        messages = final_state.get("messages", [])
        print(f"Total messages: {len(messages)}")

        # DEBUG: Print all messages to see what we have
        for i, msg in enumerate(messages):
            print(f"Message {i}: {msg['role']} - {msg['text'][:100]}...")

        # CHECK 1: Look for system message (feedback) in messages
        if messages and messages[-1]["role"] == "system":
            feedback_text = messages[-1]["text"]
            print(f"✅ FEEDBACK FOUND IN MESSAGES: {feedback_text[:100]}...")
            return {
                "thread_id": req.thread_id,
                "status": "completed",
                "message": feedback_text,
                "current_step": final_state.get("step", 1),
                "max_steps": final_state.get("max_steps", 3),
            }

        # CHECK 2: Look for feedback field in state (backup check)
        if final_state.get("feedback"):
            print(f"✅ FEEDBACK FOUND IN STATE: {final_state['feedback'][:100]}...")
            return {
                "thread_id": req.thread_id,
                "status": "completed",
                "message": final_state["feedback"],
                "current_step": final_state.get("step", 1),
                "max_steps": final_state.get("max_steps", 3),
            }

        # CHECK 3: Check if we've exceeded max steps (should have triggered feedback)
        current_step = final_state.get("step", 0)
        max_steps = final_state.get("max_steps", 3)
        if current_step >= max_steps:
            print(
                f"⚠️  MAX STEPS REACHED but no feedback found. Step {current_step}/{max_steps}"
            )
            # If we're at max steps but no feedback, maybe generate it manually?
            # Or return a message indicating interview completion

        # If no feedback found, look for the next question
        for msg in reversed(messages):
            if msg["role"] == "interviewer":
                print(f"↳ RETURNING QUESTION: {msg['text'][:100]}...")
                return {
                    "thread_id": req.thread_id,
                    "status": "question",
                    "message": msg["text"],
                    "current_step": current_step,
                    "max_steps": max_steps,
                }

        # Fallback
        if messages:
            print(f"↳ FALLBACK - Last message: {messages[-1]['role']}")
            return {
                "thread_id": req.thread_id,
                "status": (
                    "question" if messages[-1]["role"] == "interviewer" else "unknown"
                ),
                "message": messages[-1]["text"],
                "current_step": current_step,
                "max_steps": max_steps,
            }

        raise HTTPException(status_code=500, detail="No response generated")

    except Exception as e:
        print(f"Error in continue_interview: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/debug/{thread_id}")
async def debug_interview(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}

    try:
        state = compiled_graph.get_state(config)
        if not state:
            return {"error": "No state found"}

        return {
            "thread_id": thread_id,
            "values": state.values,
            "next_node": getattr(state, "next", None),
            "config": state.config,
        }
    except Exception as e:
        return {"error": str(e)}
