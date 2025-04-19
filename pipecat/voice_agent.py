import asyncio
import os
from fastapi import FastAPI, WebSocket
from pipecat.frames.frames import TextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask
from pipecat.pipeline.runner import PipelineRunner
from pipecat.services.mem0 import Mem0MemoryService
from pipecat.services.openai import OpenAILLMService, OpenAIUserContextAggregator, OpenAIAssistantContextAggregator
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams
)
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.services.whisper import WhisperSTTService

app = FastAPI()

@app.websocket("/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Basic setup with minimal configuration
    user_id = "user123"
    
    # WebSocket transport
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_out_enabled=True,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            vad_audio_passthrough=True,
            serializer=ProtobufFrameSerializer(),
        )
    )
    
    # Core services
    user_context = OpenAIUserContextAggregator()
    assistant_context = OpenAIAssistantContextAggregator()
    stt = WhisperSTTService(api_key=os.getenv("OPENAI_API_KEY"))
    
    # Memory service - the key component
    memory = Mem0MemoryService(
        api_key=os.getenv("MEM0_API_KEY"),
        user_id=user_id,
        agent_id="fastapi_memory_bot"
    )
    
    # LLM for response generation
    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-3.5-turbo",
        system_prompt="You are a helpful assistant that remembers past conversations."
    )
    
    # Simple pipeline
    pipeline = Pipeline([
        transport.input(),
        stt,                # Speech-to-text for audio input
        user_context,
        memory,             # Memory service enhances context here
        llm,
        transport.output(),
        assistant_context
    ])
    
    # Run the pipeline
    runner = PipelineRunner()
    task = PipelineTask(pipeline)
    
    # Event handlers for WebSocket connections
    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        # Send welcome message when client connects
        await task.queue_frame(TextFrame("Hello! I'm a memory bot. I'll remember our conversation."))
    
    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        # Clean up when client disconnects
        await task.cancel()
    
    await runner.run(task)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)