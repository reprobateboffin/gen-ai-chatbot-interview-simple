from fastapi import FastAPI, Form, HTTPException
from pydantic import BaseModel
import uuid
from interviewgraph import compiled_graph

app = FastAPI()


class ContinueRequest(BaseModel):
    user_response: str
    thread_id: str


@app.post("/start_interview")
async def start_interview(job_title: str = Form(...)):
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    try:
        initial_state = {
            "job_title": job_title,
            "messages": [],
            "step": 0,
            "max_steps": 6,
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/continue_interview")
async def continue_interview(req: ContinueRequest):
    config = {"configurable": {"thread_id": req.thread_id}}

    try:
        final_state = None
        events = compiled_graph.stream(
            {"user_response": req.user_response, "waiting_for_user": False},
            config=config,
            stream_mode=["values"],
        )

        for event_type, event_data in events:
            if event_type == "values":
                final_state = event_data

        if not final_state:
            final_state = compiled_graph.invoke(
                {"user_response": req.user_response, "waiting_for_user": False},
                config=config,
            )

        messages = final_state.get("messages", [])

        if messages and messages[-1]["role"] == "system":
            return {
                "thread_id": req.thread_id,
                "status": "completed",
                "message": messages[-1]["text"],
                "current_step": final_state.get("step", 1),
                "max_steps": final_state.get("max_steps", 3),
            }

        if final_state.get("feedback"):
            return {
                "thread_id": req.thread_id,
                "status": "completed",
                "message": final_state["feedback"],
                "current_step": final_state.get("step", 1),
                "max_steps": final_state.get("max_steps", 3),
            }

        for msg in reversed(messages):
            if msg["role"] == "interviewer":
                return {
                    "thread_id": req.thread_id,
                    "status": "question",
                    "message": msg["text"],
                    "current_step": final_state.get("step", 1),
                    "max_steps": final_state.get("max_steps", 3),
                }

        if messages:
            return {
                "thread_id": req.thread_id,
                "status": (
                    "question" if messages[-1]["role"] == "interviewer" else "unknown"
                ),
                "message": messages[-1]["text"],
                "current_step": final_state.get("step", 1),
                "max_steps": final_state.get("max_steps", 3),
            }

        raise HTTPException(status_code=500, detail="No response generated")

    except Exception as e:
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
