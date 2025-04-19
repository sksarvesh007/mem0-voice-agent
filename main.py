
import asyncio
import logging
import os
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import deepgram, openai, silero
from mem0 import AsyncMemoryClient

# Load environment variables
load_dotenv()

# Configure logging
#save the logs file in "logs" folder
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/car_sales_agent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("car_sales_agent")

# Path to CSV files
SLOTS_CSV_PATH = "busy_slots.csv"
BOOKINGS_CSV_PATH = "bookings.csv"
USER_ID = input("Enter your username : ")

# Initialize Mem0 memory client
mem0 = AsyncMemoryClient()
logger.info("Mem0 memory client initialized")

def prewarm_process(proc: JobProcess):
    """
    Preload models to speed up session start
    
    Args:
        proc: JobProcess instance for the worker
    """
    logger.info("Prewarming process started")
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("Silero VAD preloaded successfully")

def read_available_slots() -> List[Dict[str, str]]:
    """
    Read available appointment slots from CSV file
    
    Returns:
        List of available appointment slots as dictionaries with date and time
    """
    logger.info(f"Reading available appointment slots from {SLOTS_CSV_PATH}")
    if not os.path.exists(SLOTS_CSV_PATH):
        logger.info(f"Creating {SLOTS_CSV_PATH} with sample data")
        with open(SLOTS_CSV_PATH, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['date', 'time', 'available'])
            writer.writerow(['2023-08-15', '10:00', 'True'])
            writer.writerow(['2023-08-15', '14:00', 'True'])
            writer.writerow(['2023-08-16', '11:00', 'True'])
            writer.writerow(['2023-08-16', '15:30', 'True'])
            writer.writerow(['2023-08-17', '09:30', 'True'])

    available_slots = []
    with open(SLOTS_CSV_PATH, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['available'].lower() == 'true':
                available_slots.append({
                    'date': row['date'],
                    'time': row['time']
                })
    logger.info(f"Found {len(available_slots)} available slots")
    return available_slots

def add_busy_slot(date: str, time: str) -> bool:
    """
    Add a new busy slot to the CSV file
    
    Args:
        date: Date in YYYY-MM-DD format
        time: Time in HH:MM format
        
    Returns:
        Boolean indicating success
    """
    logger.info(f"Adding busy slot for date: {date}, time: {time}")
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
                    logger.info(f"Existing slot found and marked as unavailable")
                slots.append(slot)
    
    if not exists:
        logger.info(f"Slot doesn't exist, creating new busy slot")
        slots.append({
            'date': date,
            'time': time,
            'available': 'False'  # New slot is busy
        })
    
    with open(SLOTS_CSV_PATH, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['date', 'time', 'available'])
        writer.writeheader()
        for slot in slots:
            writer.writerow(slot)
    
    logger.info(f"Successfully updated busy slots in {SLOTS_CSV_PATH}")
    return True

def book_appointment(name: str, phone: str, date: str, time: str) -> bool:
    """
    Book an appointment and write to bookings CSV
    
    Args:
        name: Customer name
        phone: Customer phone number
        date: Appointment date in YYYY-MM-DD format
        time: Appointment time in HH:MM format
        
    Returns:
        Boolean indicating if booking was successful
    """
    logger.info(f"Booking appointment for {name} on {date} at {time}")
    # Create bookings file if it doesn't exist
    if not os.path.exists(BOOKINGS_CSV_PATH):
        logger.info(f"Creating {BOOKINGS_CSV_PATH}")
        with open(BOOKINGS_CSV_PATH, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['name', 'phone', 'date', 'time', 'booked_at'])
    
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
                    logger.info(f"Slot marked as unavailable")
            slots.append(slot)
    
    if not slot_exists:
        logger.info(f"Slot doesn't exist, creating new busy slot")
        slots.append({
            'date': date,
            'time': time,
            'available': 'False' 
        })
        updated = True
    
    if not updated:
        logger.warning(f"Booking failed: slot {date} at {time} is already booked")
        return False

    with open(SLOTS_CSV_PATH, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['date', 'time', 'available'])
        writer.writeheader()
        for slot in slots:
            writer.writerow(slot)
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    booking_exists = False
    if os.path.exists(BOOKINGS_CSV_PATH) and os.path.getsize(BOOKINGS_CSV_PATH) > 0:
        with open(BOOKINGS_CSV_PATH, 'r', newline='') as f:
            reader = csv.reader(f)
            if sum(1 for _ in reader) > 1: 
                booking_exists = True
    
    if not booking_exists:
        logger.info(f"Creating new bookings file")
        with open(BOOKINGS_CSV_PATH, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['name', 'phone', 'date', 'time', 'booked_at'])
            writer.writerow([name, phone, date, time, timestamp])
    else:
        logger.info(f"Appending to existing bookings file")
        with open(BOOKINGS_CSV_PATH, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([name, phone, date, time, timestamp])
    
    logger.info(f"Appointment successfully booked for {name}")
    return True

def read_busy_slots() -> List[Dict[str, str]]:
    logger.info(f"Reading busy appointment slots from {SLOTS_CSV_PATH}")
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
    logger.info(f"Found {len(busy_slots)} busy slots")
    return busy_slots

class CarSalesAssistant(llm.FunctionContext):
    def __init__(self):
        super().__init__()
        logger.info("CarSalesAssistant initialized")
        
    @llm.ai_callable()
    async def get_available_slots(self) -> str:
        """
        Get the list of available appointment slots
        
        Returns:
            Formatted string of available appointment slots
        """
        logger.info("LLM requested available appointment slots")
        slots = read_available_slots()
        if not slots:
            logger.info("No available slots found")
            return "There are currently no available appointment slots."
        
        result = "Available appointment slots:\n"
        for slot in slots:
            result += f"- {slot['date']} at {slot['time']}\n"
        logger.info(f"Returning {len(slots)} available slots to LLM")
        return result
    
    @llm.ai_callable()
    async def book_customer_appointment(self, name: str, phone: str, date: str, time: str) -> str:
        """
        Book an appointment for the customer
        
        Args:
            name: Customer name
            phone: Customer phone number
            date: Appointment date
            time: Appointment time
            
        Returns:
            Confirmation message or error message
        """
        logger.info(f"LLM requested to book appointment for {name} on {date} at {time}")
        success = book_appointment(name, phone, date, time)
        if success:
            logger.info(f"Appointment successfully booked")
            return f"Appointment successfully booked for {name} on {date} at {time}."
        else:
            logger.warning(f"Appointment booking failed - slot unavailable")
            return "Sorry, that slot is no longer available. Please choose another time."
    
    @llm.ai_callable()
    async def add_new_busy_slot(self, date: str, time: str) -> str:
        """
        Add a new busy slot that's not available for booking
        
        Args:
            date: Date to mark as busy
            time: Time to mark as busy
            
        Returns:
            Confirmation message
        """
        logger.info(f"LLM requested to add busy slot on {date} at {time}")
        success = add_busy_slot(date, time)
        if success:
            logger.info("Busy slot added successfully")
            return f"Successfully added busy slot on {date} at {time}."
        else:
            logger.warning("Failed to add busy slot")
            return "Failed to add busy slot. Please try again."
    
    @llm.ai_callable()
    async def get_todays_date(self) -> str: 
        """
        Get the current date
        
        Returns:
            Current date in YYYY-MM-DD format
        """
        today = datetime.now().strftime('%Y-%m-%d')
        logger.info(f"LLM requested today's date: {today}")
        return today
    
    @llm.ai_callable()
    async def get_busy_slots(self) -> str:
        """
        Get the list of busy appointment slots
        
        Returns:
            Formatted string of busy appointment slots
        """
        logger.info("LLM requested busy appointment slots")
        slots = read_busy_slots()
        
        if not slots:
            logger.info("No busy slots found")
            return "There are currently no busy appointment slots."
        
        result = "Busy appointment slots:\n"
        for slot in slots:
            result += f"- {slot['date']} at {slot['time']}\n"
        logger.info(f"Returning {len(slots)} busy slots to LLM")
        return result
    
    @llm.ai_callable()
    async def format_car_features(self, car_model: str) -> str:
        """
        Get key features for a specific car model
        
        Args:
            car_model: The car model to get features for
            
        Returns:
            Formatted string of car features
        """
        logger.info(f"LLM requested features for car model: {car_model}")
        car_features = {
            "sedan": "Our sedan models feature excellent fuel economy averaging 35 MPG, advanced safety features including automated emergency braking, and a spacious interior with premium sound system.",
            "suv": "Our SUVs offer best-in-class cargo space, all-wheel drive capability, third-row seating options, and advanced driver assistance features like adaptive cruise control.",
            "truck": "Our trucks boast impressive towing capacity up to 12,000 pounds, durable bed liners, advanced 4x4 systems, and fuel-efficient engine options.",
            "hybrid": "Our hybrid models deliver exceptional fuel efficiency up to 55 MPG, reduced emissions, regenerative braking systems, and a smooth, quiet ride.",
            "sports": "Our sports models feature high-performance engines with 0-60 times under 5 seconds, sport-tuned suspensions, premium audio systems, and sleek aerodynamic designs."
        }
        
        model = car_model.lower()
        if model in car_features:
            logger.info(f"Returning features for {model}")
            return car_features[model]
        else:
            logger.warning(f"No specific information for model: {car_model}")
            return "I don't have specific information about that model, but I'd be happy to discuss our popular options when you visit the dealership."


logger.info("Car Sales Cold Caller initialized")

async def entrypoint(ctx: JobContext):
    
    logger.info("Entrypoint function started")
    
    logger.info("Connecting to LiveKit room")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info("Connected to LiveKit room")
    
    logger.info("Waiting for participant to join")
    participant = await ctx.wait_for_participant()
    logger.info(f"Participant connected: {participant.identity}")
    
    async def _enrich_with_memory(agent: VoicePipelineAgent, chat_ctx: llm.ChatContext):
        if not chat_ctx.messages:
            return
        
        logger.info("Enriching context with memory")
        user_msg = chat_ctx.messages[-1]
        logger.info(f"Storing user message in Mem0: {user_msg.content[:30]}...")
        
        await mem0.add(
            [{"role": "user", "content": user_msg.content}], 
            user_id=USER_ID
        )
        
        logger.info("Searching for relevant memories")
        results = await mem0.search(
            user_msg.content, 
            user_id=USER_ID,
        )
        
        if results:
            logger.info(f"Found {len(results)} relevant memories")
            memories = ' '.join([result["memory"] for result in results])
            
            rag_msg = llm.ChatMessage.create(
                text=f"Relevant Memory: {memories}\n",
                role="assistant",
            )
            
            chat_ctx.messages[-1] = rag_msg
            chat_ctx.messages.append(user_msg)
            logger.info("Chat context updated with memory-enriched context")
        else:
            logger.info("No relevant memories found")
    
    logger.info("Initializing car sales assistant")
    car_sales = CarSalesAssistant()
    
    logger.info("Creating initial chat context")
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
            
            You can remember past interactions and use them to inform your answers.
            If the name of the customer is retrieved from the memory, use it to personalize the conversation. 
            If the things which the customer is interested in are retrieved from the memory, use it to inform your answers.
            Use semantic memory retrieval to provide contextually relevant responses. 

            Be conversational but professional. If the person isn't interested, thank them politely and end the call.
            If they have questions about specific car models, provide brief information and suggest they visit for a full demonstration.
            
            DO NOT be pushy or use high-pressure sales tactics. Be respectful of their time and decisions.
            """
        ),
    )
    
    logger.info("Initial context created")
    
    logger.info("Creating voice pipeline agent")
    agent = VoicePipelineAgent(
        chat_ctx=initial_ctx,
        vad=silero.VAD.load(),
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4o"),
        tts=openai.TTS(),
        fnc_ctx=car_sales,
        before_llm_cb=_enrich_with_memory,
    )
    
    logger.info("Agent created successfully")
    
    
    logger.info("Starting agent")
    agent.start(ctx.room, participant)
    logger.info("Sending initial greeting")
    await agent.say(
        "Hi! This is Alex from Swift Motors. We’re currently offering top dollar for trade-ins, and it might be a great time to upgrade your ride. Would you be open to stopping by for a quick appraisal and test drive this week?",
        allow_interruptions=True
    )
    
    logger.info("Initial greeting sent")

if __name__ == "__main__":
    logger.info("Starting Car Sales Cold Caller application")
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm_process))
    logger.info("Application stopped")