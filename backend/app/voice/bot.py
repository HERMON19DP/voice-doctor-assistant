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

load_dotenv(override=True)

SYSTEM_INSTRUCTION = """
You are a friendly AI receptionist for a medical clinic.

For this initial version, you are a conversational assistant.
Help callers understand that you can assist with doctor appointments.

Keep responses concise and natural because they will be spoken aloud.
Do not use markdown, bullet points, emojis, or special formatting.
Do not provide medical diagnoses or prescribe medication.
"""


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting Voice AI Doctor Appointment Assistant")

    # Speech-to-text
    stt = ElevenLabsRealtimeSTTService(
        api_key=os.environ["ELEVENLABS_API_KEY"],
    )

    # Text-to-speech
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")

    tts_settings = (
        ElevenLabsTTSService.Settings(voice=voice_id)
        if voice_id
        else ElevenLabsTTSService.Settings()
    )

    tts = ElevenLabsTTSService(
        api_key=os.environ["ELEVENLABS_API_KEY"],
        settings=tts_settings,
    )

    # Large language model
    llm = GoogleLLMService(
        api_key=os.environ["GEMINI_API_KEY"],
        settings=GoogleLLMService.Settings(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            system_instruction=SYSTEM_INSTRUCTION,
        ),
    )

    # Conversation context
    context = LLMContext()

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

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
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
                "content": "Greet the caller and briefly introduce yourself.",
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
