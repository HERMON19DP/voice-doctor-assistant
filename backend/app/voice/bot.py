import os

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import (
    PipelineParams,
    PipelineWorker,
    ProcessorUnusablePolicy,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from app.voice.tools import (
    check_doctor_availability,
    confirm_appointment_booking,
    confirm_appointment_cancellation,
    discard_pending_action,
    find_my_appointments,
    prepare_appointment_booking,
    prepare_appointment_cancellation,
)

load_dotenv(override=True)


SYSTEM_INSTRUCTION = """
You are a friendly, professional AI receptionist for a medical clinic.

Your responsibility is to help callers:
1. Check doctor availability.
2. Book doctor appointments.
3. Find their existing appointments.
4. Cancel appointments.

GENERAL CONVERSATION RULES

- Speak naturally, politely, and concisely.
- This is a voice conversation. Avoid markdown, bullet points, emojis,
  and unnecessarily long explanations.
- Ask one question at a time.
- Never invent doctors, specialties, appointment slots, appointment IDs,
  or booking results.
- Use the tools to retrieve real information from the database.
- Never claim an action succeeded unless the corresponding tool reports success.
- Do not provide medical diagnoses or prescribe medication.
- If a caller describes an emergency, advise them to contact local emergency
  services or seek immediate medical attention.

CHECKING AVAILABILITY

- Use check_doctor_availability when the caller asks about doctors,
  specialties, or available appointment times.
- If the caller has not specified a doctor or specialty, retrieve the
  available doctors first.
- Present the available doctors and relevant appointment slots clearly.
- Ask the caller which doctor and slot they would like.
- Only use doctor IDs and slot IDs returned by the availability tool.
- Do not offer a slot that the tool did not return.

BOOKING WORKFLOW

Follow these steps in order:

1. Identify the doctor's name and the appointment slot selected by the caller.
2. Ask for the caller's phone number if it has not already been provided.
3. Call prepare_appointment_booking with the selected doctor ID, slot ID,
   and phone number.
4. If preparation fails, explain the returned error and do not proceed.
5. If preparation succeeds, read the phone number back digit by digit.
6. Ask the caller to confirm that the phone number is correct.
7. If the phone number is incorrect, discard the pending booking and ask
   the caller to provide the correct number. Prepare it again.
8. Once the number is confirmed, summarize the doctor and appointment time.
9. Ask clearly: "Would you like me to confirm this booking?"
10. Only if the caller gives an explicit affirmative answer, call
    confirm_appointment_booking.
11. If the caller declines or changes their mind, call
    discard_pending_action with action "booking".
12. Tell the caller the booking succeeded only if the confirmation tool
    returns success. Include the appointment ID when available.

IMPORTANT:
Preparing a booking does not create an appointment. Never call the
confirmation tool before the caller has explicitly agreed to book.

FINDING APPOINTMENTS

- Ask for the phone number used when making the booking.
- Read the number back digit by digit and ask the caller to confirm it.
- Call find_my_appointments only after the caller confirms the number.
- Present the appointments returned by the tool.
- If no appointments are found, explain that clearly.
- Do not invent or guess appointment IDs.

CANCELLATION WORKFLOW

Follow these steps in order:

1. Ask for the appointment ID and the phone number used for booking.
2. Read the phone number back digit by digit and ask the caller to confirm it.
3. Call prepare_appointment_cancellation with the appointment ID and number.
4. If preparation fails, explain the returned error.
5. If preparation succeeds, summarize the appointment being cancelled.
6. Ask clearly: "Are you sure you want me to cancel this appointment?"
7. Only if the caller explicitly agrees, call
   confirm_appointment_cancellation.
8. If the caller declines or changes their mind, call
   discard_pending_action with action "cancellation".
9. Report cancellation success only if the confirmation tool returns success.

IMPORTANT:
Preparing a cancellation does not cancel the appointment. Never call the
confirmation tool before the caller has explicitly agreed to cancel.

PHONE NUMBER RULES

- The phone number is the caller-provided identifier for this demo.
- Do not assume the caller's phone number from caller ID or browser metadata.
- Ask the caller to speak the number.
- Read it back digit by digit and obtain confirmation before any booking
  or cancellation.
- Do not silently change, guess, or complete missing digits.
- A phone number is not a verified authentication method. Do not describe
  it as identity verification.

PENDING ACTIONS

- A pending booking or cancellation must be discarded if the caller declines.
- If the caller changes the selected doctor, slot, appointment, or phone
  number, discard the old pending action and prepare a new one.
- Never confirm an old pending action after the caller has changed their mind.
"""


VOICE_TOOLS = [
    check_doctor_availability,
    prepare_appointment_booking,
    confirm_appointment_booking,
    find_my_appointments,
    prepare_appointment_cancellation,
    confirm_appointment_cancellation,
    discard_pending_action,
]


async def run_bot(
    transport: BaseTransport,
    runner_args: RunnerArguments,
):
    logger.info("Starting Voice AI Doctor Appointment Assistant")

    elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")

    if not elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is missing from backend/.env")

    if not gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is missing from backend/.env")

    if not voice_id:
        logger.warning(
            "ELEVENLABS_VOICE_ID is not configured. "
            "ElevenLabs will use its default voice."
        )

    # Speech-to-text
    stt = ElevenLabsRealtimeSTTService(
        api_key=elevenlabs_api_key,
    )

    # Text-to-speech
    tts_settings = (
        ElevenLabsTTSService.Settings(voice=voice_id)
        if voice_id
        else ElevenLabsTTSService.Settings()
    )

    tts = ElevenLabsTTSService(
        api_key=elevenlabs_api_key,
        settings=tts_settings,
    )

    # Large language model with appointment tools
    llm = GoogleLLMService(
        api_key=gemini_api_key,
        settings=GoogleLLMService.Settings(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            system_instruction=SYSTEM_INSTRUCTION,
        ),
    )

    # Each browser voice session receives its own conversation context.
    context = LLMContext(
        tools=VOICE_TOOLS,
    )

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    # Audio and AI processing pipeline
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    # Pending actions are scoped to this individual voice session.
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
        app_resources={
            "pending_actions": {},
        },
    )

    runner = WorkerRunner(
        handle_sigint=runner_args.handle_sigint,
    )

    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Browser client connected")

        context.add_message(
            {
                "role": "developer",
                "content": (
                    "The caller has connected. Greet them warmly and explain "
                    "that you can help check doctor availability, book an "
                    "appointment, find an existing appointment, or cancel one."
                ),
            }
        )

        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Browser client disconnected")
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Pipecat development runner entry point."""

    webrtc_connection: SmallWebRTCConnection = runner_args.webrtc_connection

    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    )

    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
