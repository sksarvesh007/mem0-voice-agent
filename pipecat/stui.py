import streamlit as st
import websocket
import threading
import json
import time
import base64
import pyaudio
import numpy as np
from io import BytesIO
import wave
from PIL import Image

# Set page configuration
st.set_page_config(
    page_title="Memory Chat Bot",
    page_icon="🤖",
    layout="centered"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .chat-message {
        padding: 1.5rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        display: flex;
        flex-direction: row;
    }
    .chat-message.user {
        background-color: #e6f7ff;
        border-left: 5px solid #2196F3;
    }
    .chat-message.bot {
        background-color: #f0f0f0;
        border-left: 5px solid #9e9e9e;
    }
    .chat-message .avatar {
        width: 45px;
        height: 45px;
        border-radius: 50%;
        object-fit: cover;
        margin-right: 20px;
    }
    .chat-message .message {
        flex-grow: 1;
    }
    .voice-button {
        font-size: 1.5rem !important;
        padding: 0.5rem 1rem !important;
        height: auto !important;
    }
    .stTextInput>div>div>input {
        padding: 0.75rem !important;
        font-size: 1rem !important;
    }
</style>
""", unsafe_allow_html=True)

# App title and description
st.title("Memory Chat Bot")
st.markdown("Chat with an assistant that remembers your conversations")

# Initialize session state for chat history
if 'messages' not in st.session_state:
    st.session_state.messages = []

if 'ws' not in st.session_state:
    st.session_state.ws = None

if 'recording' not in st.session_state:
    st.session_state.recording = False

if 'audio_frames' not in st.session_state:
    st.session_state.audio_frames = []

# WebSocket connection parameters
WEBSOCKET_URL = "ws://localhost:8000/chat"

# Audio parameters
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024

# Audio recording functionality
def record_audio():
    p = pyaudio.PyAudio()
    
    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )
    
    st.session_state.audio_frames = []
    
    while st.session_state.recording:
        data = stream.read(CHUNK)
        st.session_state.audio_frames.append(data)
        
        # If WebSocket is connected, send audio data
        if st.session_state.ws and st.session_state.ws.sock and st.session_state.ws.sock.connected:
            audio_data = {
                "type": "audio",
                "data": base64.b64encode(data).decode('utf-8'),
                "sample_rate": RATE,
                "channels": CHANNELS
            }
            st.session_state.ws.send(json.dumps(audio_data))
    
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    return b''.join(st.session_state.audio_frames)

# Function to start recording
def start_recording():
    st.session_state.recording = True
    threading.Thread(target=record_audio).start()

# Function to stop recording and send the complete audio
def stop_recording():
    st.session_state.recording = False
    time.sleep(0.5)  # Give time for the recording thread to finish
    
    # Create WAV file in memory
    if st.session_state.audio_frames:
        audio_data = b''.join(st.session_state.audio_frames)
        
        # Create a BytesIO object to hold the WAV file
        wav_buffer = BytesIO()
        
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit audio
            wf.setframerate(RATE)
            wf.writeframes(audio_data)
        
        wav_buffer.seek(0)
        
        # Add user message with audio indicator
        st.session_state.messages.append({"role": "user", "content": "[Voice message]", "has_audio": True})

# WebSocket message handling
def on_message(ws, message):
    try:
        msg_data = json.loads(message)
        
        if msg_data.get("type") == "text":
            content = msg_data.get("content", "")
            st.session_state.messages.append({"role": "assistant", "content": content})
            st.experimental_rerun()
        
        elif msg_data.get("type") == "audio":
            # Handle audio responses if needed
            pass
            
    except Exception as e:
        st.error(f"Error processing message: {str(e)}")

def on_error(ws, error):
    st.error(f"WebSocket error: {str(error)}")

def on_close(ws, close_status_code, close_msg):
    st.warning("WebSocket connection closed")

def on_open(ws):
    st.success("Connected to chat server")

# Connect to WebSocket server
def connect_websocket():
    if st.session_state.ws is None or not (st.session_state.ws.sock and st.session_state.ws.sock.connected):
        try:
            ws = websocket.WebSocketApp(
                WEBSOCKET_URL,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )
            
            wst = threading.Thread(target=ws.run_forever)
            wst.daemon = True
            wst.start()
            
            st.session_state.ws = ws
            time.sleep(1)  # Give time for connection to establish
            
            return True
        except Exception as e:
            st.error(f"Connection error: {str(e)}")
            return False
    return True

# Ensure WebSocket connection
if not connect_websocket():
    st.stop()

# Display chat messages
chat_container = st.container()
with chat_container:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

# Input area
st.markdown("---")
col1, col2 = st.columns([4, 1])

with col1:
    user_input = st.text_input("Type your message:", key="user_input")

with col2:
    voice_button_placeholder = st.empty()
    if st.session_state.recording:
        if voice_button_placeholder.button("⏹️ Stop", key="stop_recording", type="primary", use_container_width=True):
            stop_recording()
    else:
        if voice_button_placeholder.button("🎤 Record", key="start_recording", use_container_width=True):
            start_recording()

# Handle text input
if user_input:
    # Add user message to chat
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    # Send message to WebSocket server
    if st.session_state.ws and st.session_state.ws.sock and st.session_state.ws.sock.connected:
        message_data = {
            "type": "text",
            "content": user_input
        }
        st.session_state.ws.send(json.dumps(message_data))
    
    # Clear input box
    st.session_state.user_input = ""
    
    # Force refresh to display new message
    st.experimental_rerun()

# Show connection status
with st.sidebar:
    st.subheader("Connection Status")
    
    if st.session_state.ws and st.session_state.ws.sock and st.session_state.ws.sock.connected:
        st.success("Connected to server")
    else:
        st.error("Disconnected")
        if st.button("Reconnect"):
            connect_websocket()
    
    st.markdown("---")
    st.subheader("About")
    st.markdown("""
    This chat application connects to a WebSocket server that utilizes:
    - Speech-to-text for voice messages
    - Long-term memory for context
    - LLM for intelligent responses
    """)