# Car Sales Voice Agent

An AI based voice to voice agent which leverages the mem0's functionality for memory handling for much better user experience

## Overview

This application implements a voice agent for car sales cold calling using LiveKit's agent framework. The agent engages with potential customers to schedule test drive appointments using natural speech. The system maintains appointment slots and bookings using CSV files and leverages memory for contextually relevant conversations.

## Features

- **Natural voice conversations**: Uses OpenAI's GPT-4o and TTS for human-like interactions
- **Memory retention**: Remembers past customer interactions for personalized follow-ups through the mem0's memory handling functionality
- **Appointment scheduling**: Manages and books test drive appointments
- **Car model information**: Provides details about different car models
- **Contextual responses**: Uses retrieved memories to personalize conversations

## Prerequisites

- Python 3.8+ (current version of python 3.12.9)
- LiveKit account
- OpenAI API key
- Deepgram API key
- Mem0 API key

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/sksarvesh007/mem0-voice-agent.git
   cd mem0-voice-agent
   ```
2. Create and activate a virtual environment:
   Keeping UV as the package manager

   ```bash
   pip install uv
   uv venv 
   .venv\Scripts\activate
   ```
3. Install dependencies:

   ```bash
   uv pip install -r requirements.txt
   ```
4. Create a `.env` file in the project root with your API keys:

   1. Copy the `.env` file from the `.env.example` file

      ```bash
      cp .env.example .env
      ```

   ```bash
   OPENAI_API_KEY=your_openai_api_key
   DEEPGRAM_API_KEY=your_deepgram_api_key
   MEM0_API_KEY=your_mem0_api_key
   LIVEKIT_API_KEY=your_livekit_api_key
   LIVEKIT_API_SECRET=your_livekit_api_secret
   LIVEKIT_URL=your_livekit_url
   ```
5. Create a `logs` directory for log files:

   ```
   mkdir logs
   ```

## Usage

Run the voice agent:

```bash
python main.py dev
```

Run the python file in the dev mode for seeing the logs in the terminal, When prompted, enter a username to identify the current session. The system will initialize and wait for a participant to join the LiveKit room.

and then proceed to the [Livekit playground](https://agents-playground.livekit.io/) and then select the project name under which you have made the account in Livekit to interact with your agent

## Data Storage

The application uses two CSV files for data storage:

- `busy_slots.csv`: Tracks available and unavailable appointment slots
- `bookings.csv`: Records customer booking information

## System Components

### CarSalesAssistant

Provides the following functions to the AI agent:

- `get_available_slots()`: Returns available appointment slots
- `book_customer_appointment()`: Books an appointment for a customer
- `add_new_busy_slot()`: Marks a slot as busy/unavailable
- `get_todays_date()`: Returns the current date
- `get_busy_slots()`: Returns busy appointment slots
- `format_car_features()`: Provides information about car models

### Memory System

The application uses Mem0's AsyncMemoryClient to:

- Store conversation history
- Retrieve relevant past interactions
- Provide context to the AI for personalized responses

## Configuration

Customize the agent's behavior by modifying:

- System prompt in the `initial_ctx` variable
- Available car models and descriptions in the `car_features` dictionary
- Initial greeting message

## Logging

Logs are stored in the `logs/car_sales_agent.log` file and also output to the console. Log messages include timestamps and detailed information about application operations.

## Dependencies

Key dependencies include:

- LiveKit and related plugins for audio communication
- OpenAI for language model and speech synthesis
- Deepgram for speech-to-text
- Silero for Voice Activity Detection (VAD)
- Mem0 for memory storage and retrieval

See `requirements.txt` for the complete list of dependencies and their versions.
