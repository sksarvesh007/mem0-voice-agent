import os
import signal
import sys
from dotenv import load_dotenv
from mem0 import AsyncMemoryClient
from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation, ClientTools
from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface

# Load environment variables from .env file
load_dotenv()

def main():
    # Validate environment variables
    required_vars = {
        'AGENT_ID': os.environ.get('AGENT_ID'),
        'USER_ID': os.environ.get('USER_ID'),
        'MEM0_API_KEY': os.environ.get('MEM0_API_KEY'),
    }
    
    for name, value in required_vars.items():
        if not value:
            sys.stderr.write(f"{name} environment variable must be set\n")
            sys.exit(1)

    elevenlabs_key = os.environ.get('ELEVENLABS_API_KEY')

    # Initialize clients
    client = ElevenLabs(api_key=elevenlabs_key)
    mem0_client = AsyncMemoryClient()
    client_tools = ClientTools()

    # Memory functions
    async def add_memories(parameters):
        """Add memories to Mem0"""
        await mem0_client.add(
            messages=parameters.get("message"),
            user_id=required_vars['USER_ID'],
            output_format="v1.1",
            version="v2"
        )
        return "Memory added successfully"

    async def retrieve_memories(parameters):
        """Retrieve memories from Mem0"""
        results = await mem0_client.search(
            query=parameters.get("message"),
            version="v2",
            filters={"AND": [{"user_id": required_vars['USER_ID']}]}
        )
        memories = ' '.join([result["memory"] for result in results])
        return memories or "No memories found"

    # Register tools
    client_tools.register("addMemories", add_memories, is_async=True)
    client_tools.register("retrieveMemories", retrieve_memories, is_async=True)

    # Configure conversation
    conversation = Conversation(
        client,
        required_vars['AGENT_ID'],
        requires_auth=bool(elevenlabs_key),
        audio_interface=DefaultAudioInterface(),
        client_tools=client_tools,
        callback_agent_response=lambda r: print(f"Agent: {r}"),
        callback_user_transcript=lambda t: print(f"User: {t}"),
    ) 
    # Start conversation
    print(f"Starting conversation with user: {required_vars['USER_ID']}")
    conversation.start_session()
    signal.signal(signal.SIGINT, lambda s, f: conversation.end_session())
    conversation_id = conversation.wait_for_session_end()
    print(f"Conversation ID: {conversation_id}")

if __name__ == '__main__':
    main()