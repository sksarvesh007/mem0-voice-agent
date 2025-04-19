import asyncio
import logging
import os
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional

import aiohttp
from dotenv import load_dotenv
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
    metrics,
)
from livekit import rtc, api
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import deepgram, openai, silero
from langchain_openai import ChatOpenAI
from mem0 import AsyncMemoryClient
# Load environment variables
load_dotenv()

# Configure logging

# Path to CSV files
SLOTS_CSV_PATH = "busy_slots.csv"
BOOKINGS_CSV_PATH = "bookings.csv"
USER_ID = "voice_user"

# Initialize Mem0 memory client
mem0 = AsyncMemoryClient()
def prewarm_process(proc: JobProcess):
    # Preload silero VAD in memory to speed up session start
    proc.userdata["vad"] = silero.VAD.load()

def read_available_slots():
    """Read available appointment slots from CSV file"""
    # Create the file with sample data if it doesn't exist
    if not os.path.exists(SLOTS_CSV_PATH):
        with open(SLOTS_CSV_PATH, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['date', 'time', 'available'])
            # Add some sample data
            writer.writerow(['2023-08-15', '10:00', 'True'])
            writer.writerow(['2023-08-15', '14:00', 'True'])
            writer.writerow(['2023-08-16', '11:00', 'True'])
            writer.writerow(['2023-08-16', '15:30', 'True'])
            writer.writerow(['2023-08-17', '09:30', 'True'])
    
    # Read available slots
    available_slots = []
    with open(SLOTS_CSV_PATH, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['available'].lower() == 'true':
                available_slots.append({
                    'date': row['date'],
                    'time': row['time']
                })
    return available_slots

def add_busy_slot(date: str, time: str) -> bool:
    """Add a new busy slot to the CSV file"""
    # Check if the slot already exists
    slots = []
    exists = False
    
    if os.path.exists(SLOTS_CSV_PATH):
        with open(SLOTS_CSV_PATH, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                slot = dict(row)
                if slot['date'] == date and slot['time'] == time:
                    exists = True
                    slot['available'] = 'False'  # Mark as unavailable
                slots.append(slot)
    
    # If the slot doesn't exist, add it
    if not exists:
        slots.append({
            'date': date,
            'time': time,
            'available': 'False'  # New slot is busy
        })
    
    # Write updated slots back to file
    with open(SLOTS_CSV_PATH, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['date', 'time', 'available'])
        writer.writeheader()
        for slot in slots:
            writer.writerow(slot)
    
    return True

def book_appointment(name: str, phone: str, date: str, time: str) -> bool:
    """Book an appointment and write to bookings CSV"""
    # Create bookings file if it doesn't exist
    if not os.path.exists(BOOKINGS_CSV_PATH):
        with open(BOOKINGS_CSV_PATH, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['name', 'phone', 'date', 'time', 'booked_at'])
    
    # Update available slots
    slots = []
    updated = False
    slot_exists = False
    
    with open(SLOTS_CSV_PATH, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            slot = dict(row)
            if slot['date'] == date and slot['time'] == time:
                slot_exists = True
                if slot['available'].lower() == 'true':
                    slot['available'] = 'False'
                    updated = True
            slots.append(slot)
    
    # If the slot doesn't exist at all, add it as busy
    if not slot_exists:
        slots.append({
            'date': date,
            'time': time,
            'available': 'False'  # Mark as unavailable
        })
        updated = True
    
    if not updated:
        return False

    # Write updated slots back to file
    with open(SLOTS_CSV_PATH, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['date', 'time', 'available'])
        writer.writeheader()
        for slot in slots:
            writer.writerow(slot)
    
    # Add to bookings - fixed to ensure proper CSV formatting
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Check if the bookings file already has content (other than header)
    booking_exists = False
    if os.path.exists(BOOKINGS_CSV_PATH) and os.path.getsize(BOOKINGS_CSV_PATH) > 0:
        with open(BOOKINGS_CSV_PATH, 'r', newline='') as f:
            reader = csv.reader(f)
            if sum(1 for _ in reader) > 1:  # More than just the header
                booking_exists = True
    
    # Write the booking data
    if not booking_exists:
        # Create new file with header and data
        with open(BOOKINGS_CSV_PATH, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['name', 'phone', 'date', 'time', 'booked_at'])
            writer.writerow([name, phone, date, time, timestamp])
    else:
        # Append to existing file without writing header again
        with open(BOOKINGS_CSV_PATH, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([name, phone, date, time, timestamp])
    
    return True

def read_busy_slots():
    """Read busy (unavailable) appointment slots from CSV file"""
    busy_slots = []
    
    if os.path.exists(SLOTS_CSV_PATH):
        with open(SLOTS_CSV_PATH, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['available'].lower() == 'false':
                    busy_slots.append({
                        'date': row['date'],
                        'time': row['time']
                    })
    return busy_slots

class CarSalesAssistant(llm.FunctionContext):
    def __init__(self):
        super().__init__()
        
    @llm.ai_callable()
    async def get_available_slots(self) -> str:
        """Get the list of available appointment slots"""
        slots = read_available_slots()
        if not slots:
            return "There are currently no available appointment slots."
        
        result = "Available appointment slots:\n"
        for slot in slots:
            result += f"- {slot['date']} at {slot['time']}\n"
        return result
    
    @llm.ai_callable()
    async def book_customer_appointment(self, name: str, phone: str, date: str, time: str) -> str:
        """Book an appointment for the customer"""
        success = book_appointment(name, phone, date, time)
        if success:
            return f"Appointment successfully booked for {name} on {date} at {time}."
        else:
            return "Sorry, that slot is no longer available. Please choose another time."
    
    @llm.ai_callable()
    async def add_new_busy_slot(self, date: str, time: str) -> str:
        """Add a new busy slot that's not available for booking"""
        success = add_busy_slot(date, time)
        if success:
            return f"Successfully added busy slot on {date} at {time}."
        else:
            return "Failed to add busy slot. Please try again."
    
    @llm.ai_callable()
    async def get_todays_date(self) -> str: 
        """Get the current date"""
        return datetime.now().strftime('%Y-%m-%d')
    
    @llm.ai_callable()
    async def get_busy_slots(self) -> str:
        """Get the list of busy appointment slots"""
        slots = read_busy_slots()
        
        if not slots:
            return "There are currently no busy appointment slots."
        
        result = "Busy appointment slots:\n"
        for slot in slots:
            result += f"- {slot['date']} at {slot['time']}\n"
        return result
    
    @llm.ai_callable()
    async def format_car_features(self, car_model: str) -> str:
        """Get key features for a specific car model"""
        # Mock data for demonstration
        car_features = {
            "sedan": "Our sedan models feature excellent fuel economy averaging 35 MPG, advanced safety features including automated emergency braking, and a spacious interior with premium sound system.",
            "suv": "Our SUVs offer best-in-class cargo space, all-wheel drive capability, third-row seating options, and advanced driver assistance features like adaptive cruise control.",
            "truck": "Our trucks boast impressive towing capacity up to 12,000 pounds, durable bed liners, advanced 4x4 systems, and fuel-efficient engine options.",
            "hybrid": "Our hybrid models deliver exceptional fuel efficiency up to 55 MPG, reduced emissions, regenerative braking systems, and a smooth, quiet ride.",
            "sports": "Our sports models feature high-performance engines with 0-60 times under 5 seconds, sport-tuned suspensions, premium audio systems, and sleek aerodynamic designs."
        }
        
        model = car_model.lower()
        if model in car_features:
            return car_features[model]
        else:
            return "I don't have specific information about that model, but I'd be happy to discuss our popular options when you visit the dealership."


print("Car Sales Cold Caller initialized")

async def entrypoint(ctx: JobContext):
    # Connect to LiveKit room
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    print("Connected to LiveKit room")
    
    # Wait for participant
    participant = await ctx.wait_for_participant()
    print("Participant connected")
    async def _enrich_with_memory(agent: VoicePipelineAgent, chat_ctx: llm.ChatContext):
        """Add memories and Augment chat context with relevant memories"""
        if not chat_ctx.messages:
            return
        
        # Store user message in Mem0
        user_msg = chat_ctx.messages[-1]
        await mem0.add(
            [{"role": "user", "content": user_msg.content}], 
            user_id=USER_ID
        )
        
        # Search for relevant memories
        results = await mem0.search(
            user_msg.content, 
            user_id=USER_ID,
        )
        
        # Augment context with retrieved memories
        if results:
            memories = ' '.join([result["memory"] for result in results])
            
            rag_msg = llm.ChatMessage.create(
                text=f"Relevant Memory: {memories}\n",
                role="assistant",
            )
            
            # Modify chat context with retrieved memories
            chat_ctx.messages[-1] = rag_msg
            chat_ctx.messages.append(user_msg)
    print("Enriching context with memory")
    car_sales = CarSalesAssistant()
    
    # Define initial system context
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            """
            You are a car sales cold caller named Alex from Swift Motors.
            Your job is to call potential customers and persuade them to schedule a test drive appointment at the dealership.
            
            Follow this cold call structure:
            1. Introduce yourself and the company politely
            2. Briefly mention the current promotion or special deals
            3. Ask if they're interested in scheduling a test drive
            4. If they show interest, offer available appointment slots
            5. Collect their name and phone number for the appointment
            6. Confirm the booking and thank them
            
            Current promotion: "0% financing for 72 months on select models"
            
            Be conversational but professional. If the person isn't interested, thank them politely and end the call.
            If they have questions about specific car models, provide brief information and suggest they visit for a full demonstration.
            
            DO NOT be pushy or use high-pressure sales tactics. Be respectful of their time and decisions.
            """
        ),
    )
    
    print("Initial context created")
    
    # Create VoicePipelineAgent
    agent = VoicePipelineAgent(
        chat_ctx=initial_ctx,
        vad=silero.VAD.load(),
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4o"),
        tts=openai.TTS(),
        fnc_ctx=car_sales,
        before_llm_cb=_enrich_with_memory,
    )
    
    print("Agent created")
    
    # Start agent and initial greeting
    agent.start(ctx.room, participant)
    await agent.say(
        "Hi! Alex from Swift Motors here. We have 0% financing for 72 months on select models. Would you be interested in a test drive this week?",
        allow_interruptions=True
    )
    
    print("Initial greeting sent")

# Run the application
if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm_process))