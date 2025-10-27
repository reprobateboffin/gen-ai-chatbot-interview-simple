import streamlit as st
import requests

st.set_page_config(page_title="AI Interviewer", page_icon="🧠")

# --- Session State ---
if "interview_started" not in st.session_state:
    st.session_state.interview_started = False
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
BACKEND_URL = "http://localhost:8000/start_interview"

# --- PHASE 1: Setup Screen ---
if not st.session_state.interview_started:
    st.title("🧠 AI Interviewer Setup")

    job_title = st.text_input("💼 Job Title", placeholder="e.g. Python Developer")

    difficulty = st.radio(
        "🎯 Select Interview Type",
        ["Behavioral", "Technical", "System Design", "Mixed"],
    )

    cv_file = st.file_uploader("📄 Upload your CV (optional)", type=["pdf", "docx"])

    if st.button("🚀 Start Interview"):
        if not job_title:
            st.warning("Please enter a job title.")
        else:
            files = {"cv": cv_file.getvalue()} if cv_file else None
            data = {"job_title": job_title, "difficulty": difficulty}
            try:
                response = requests.post(BACKEND_URL, data=data, files=files)
                if response.status_code == 200:
                    st.session_state.interview_started = True
                    backend_response = response.json()
                    backend_message = backend_response.get("message", "OK")
                    backend_thread_id = backend_response.get("thread_id")
                    # Store initial backend message in chat history
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": backend_message,
                        }
                    )
                    st.session_state.thread_id = backend_thread_id
                    st.rerun()
                else:
                    st.error(f"❌ Error: {response.status_code}")
            except Exception as e:
                st.error(f"🚨 Backend not reachable: {e}")

# --- PHASE 2: Chat Screen ---
else:
    st.title("💬 AI Interviewer")

    # Display chat messages
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.markdown(msg["content"])
        else:
            with st.chat_message("assistant"):
                st.markdown(msg["content"])

    # Input box for user reply
    if user_input := st.chat_input("Type your answer..."):
        st.session_state.messages.append({"role": "user", "content": user_input})

        # Send to backend (replace with your /continue_interview later)
        try:
            response = requests.post(
                "http://localhost:8000/continue_interview",
                json={
                    "user_response": user_input,
                    "thread_id": st.session_state.thread_id,
                },
            )
            if response.status_code == 200:
                assistant_msg = response.json().get("message", "Got it ✅")
                st.session_state.messages.append(
                    {"role": "assistant", "content": assistant_msg}
                )
            else:
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": f"⚠️ Backend error: {response.status_code}",
                    }
                )
        except Exception as e:
            st.session_state.messages.append(
                {"role": "assistant", "content": f"🚨 Backend not reachable: {e}"}
            )

        st.rerun()
