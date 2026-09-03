from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from google.cloud import speech_v2
from google.cloud.speech_v2.types import cloud_speech
import asyncio
import logging
import os
import subprocess
import tempfile


# ============================================================
# Configuration
# ============================================================

APP_NAME = "AIDE Speech-to-Text API"

PROJECT_ID = os.environ["AIDE_GCP_PROJECT_ID"]
LOCATION = "global"

API_KEY = os.environ["AIDE_STT_API_KEY"]

MAX_FILE_SIZE = 25 * 1024 * 1024       # 25 MB
MAX_DURATION_SECONDS = 5 * 60          # 5 minutes
MAX_CONCURRENT_TRANSCRIPTIONS = 10

ALLOWED_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".flac",
    ".ogg",
    ".m4a",
    ".webm",    # browser MediaRecorder default (Chrome/Firefox)
}


# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(APP_NAME)


# ============================================================
# Application
# ============================================================

app = FastAPI(title=APP_NAME)

client = speech_v2.SpeechClient()

transcription_semaphore = asyncio.Semaphore(
    MAX_CONCURRENT_TRANSCRIPTIONS
)


# ============================================================
# Helper: get file extension
# ============================================================

def get_extension(filename: str | None) -> str:
    if not filename:
        return ""

    return os.path.splitext(filename.lower())[1]


# ============================================================
# Helper: validate duration using ffprobe
# ============================================================

def get_audio_duration(audio_data: bytes, extension: str) -> float:
    """
    Write the uploaded audio temporarily and use ffprobe
    to determine its duration.

    The temporary file is deleted automatically.
    """

    suffix = extension if extension else ".audio"

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=suffix,
            delete=False,
        ) as temp_file:

            temp_file.write(audio_data)
            temp_path = temp_file.name

        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                temp_path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            raise ValueError("Unable to read audio duration.")

        duration = float(result.stdout.strip())

        return duration

    except subprocess.TimeoutExpired:
        raise ValueError("Audio validation timed out.")

    except (ValueError, TypeError):
        raise ValueError("Invalid or unreadable audio file.")

    except Exception:
        # Catches FileNotFoundError (ffprobe missing/misconfigured)
        # and anything else unexpected, so nothing escapes this
        # function and bypasses the safe error response below.
        raise ValueError("Invalid or unreadable audio file.")

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# ============================================================
# Health check
# ============================================================

@app.get("/")
def health_check():
    return {
        "status": "ok",
        "service": APP_NAME,
    }


# ============================================================
# Transcription endpoint
# ============================================================

@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    x_api_key: str = Header(default=None),
):

    # --------------------------------------------------------
    # 0. Authenticate the caller
    # --------------------------------------------------------

    if x_api_key != API_KEY:
        logger.warning("Rejected request: missing or invalid API key.")

        raise HTTPException(
            status_code=401,
            detail="Unauthorized.",
        )

    filename = file.filename or "unknown"

    logger.info(
        "Received transcription request: %s",
        filename,
    )

    # --------------------------------------------------------
    # 1. Validate file extension
    # --------------------------------------------------------

    extension = get_extension(filename)

    if extension not in ALLOWED_EXTENSIONS:
        logger.warning(
            "Rejected unsupported file format: %s",
            extension or "unknown",
        )

        raise HTTPException(
            status_code=415,
            detail=(
                "Unsupported audio format. "
                "Allowed formats: WAV, MP3, FLAC, OGG, M4A, WEBM."
            ),
        )

    # --------------------------------------------------------
    # 2. Validate MIME type
    # --------------------------------------------------------

    if not file.content_type or not file.content_type.startswith("audio/"):
        logger.warning(
            "Rejected invalid MIME type: %s",
            file.content_type,
        )

        raise HTTPException(
            status_code=415,
            detail="Uploaded file must be an audio file.",
        )

    # --------------------------------------------------------
    # 3. Read file with size protection
    # --------------------------------------------------------

    audio_data = await file.read()

    file_size = len(audio_data)

    if file_size == 0:
        logger.warning(
            "Rejected empty audio file: %s",
            filename,
        )

        raise HTTPException(
            status_code=400,
            detail="Audio file is empty.",
        )

    if file_size > MAX_FILE_SIZE:
        logger.warning(
            "Rejected oversized file: %s (%.2f MB)",
            filename,
            file_size / (1024 * 1024),
        )

        raise HTTPException(
            status_code=413,
            detail="Audio file exceeds the 25 MB limit.",
        )

    logger.info(
        "Audio accepted: %.2f MB",
        file_size / (1024 * 1024),
    )

    # --------------------------------------------------------
    # 4. Validate audio duration
    # --------------------------------------------------------

    try:
        duration = get_audio_duration(
            audio_data,
            extension,
        )

    except ValueError as exc:

        logger.warning(
            "Audio validation failed: %s",
            str(exc),
        )

        raise HTTPException(
            status_code=400,
            detail="Invalid or unreadable audio file.",
        )

    logger.info(
        "Audio duration: %.2f seconds",
        duration,
    )

    if duration <= 0:
        raise HTTPException(
            status_code=400,
            detail="Audio duration could not be determined.",
        )

    if duration > MAX_DURATION_SECONDS:
        logger.warning(
            "Rejected audio longer than 5 minutes: %.2f seconds",
            duration,
        )

        raise HTTPException(
            status_code=413,
            detail="Audio duration exceeds the 5 minute limit.",
        )

    # --------------------------------------------------------
    # 5. Limit simultaneous transcription requests
    # --------------------------------------------------------

    logger.info(
        "Waiting for transcription slot..."
    )

    async with transcription_semaphore:

        logger.info(
            "Transcription slot acquired."
        )

        try:

            # ------------------------------------------------
            # Google Speech-to-Text configuration
            # English (Australia)
            # ------------------------------------------------

            config = cloud_speech.RecognitionConfig(
                auto_decoding_config=(
                    cloud_speech.AutoDetectDecodingConfig()
                ),
                language_codes=["en-AU"],
                model="long",
            )

            request = cloud_speech.RecognizeRequest(
                recognizer=(
                    f"projects/{PROJECT_ID}"
                    f"/locations/{LOCATION}"
                    f"/recognizers/_"
                ),
                config=config,
                content=audio_data,
            )

            logger.info(
                "Sending audio to Google Speech-to-Text."
            )

            response = client.recognize(
                request=request
            )

            transcript = " ".join(
                result.alternatives[0].transcript
                for result in response.results
                if result.alternatives
            ).strip()

            logger.info(
                "Transcription completed successfully."
            )

            # ------------------------------------------------
            # Return result
            #
            # NOTE: this response contains the raw patient
            # transcript and may include PII (names, room
            # numbers, medical details). Callers must not log,
            # cache, or persist this response casually.
            # ------------------------------------------------

            return {
                "filename": filename,
                "text": transcript,
            }

        except Exception:

            # Do NOT expose Google's internal error details
            # to the API client.

            logger.exception(
                "Speech-to-text processing failed."
            )

            raise HTTPException(
                status_code=500,
                detail="Speech-to-text processing failed.",
            )
