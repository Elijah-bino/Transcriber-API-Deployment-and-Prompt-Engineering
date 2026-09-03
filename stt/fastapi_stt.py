# ~/aide-stt/main.py

import os
import io
import tempfile
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from google.cloud import speech_v2
from google.cloud.speech_v2.types import cloud_speech
import uuid
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="AIDE Speech-to-Text API",
    description="Convert audio to transcript for AIDE patient communication",
    version="1.0.0"
)

# Initialize Google Speech-to-Text client
try:
    # You can set credentials via environment variable GOOGLE_APPLICATION_CREDENTIALS
    # or use default credentials from the VM
    client = speech_v2.SpeechClient()
    logger.info("Google Speech-to-Text client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Google Speech-to-Text client: {e}")
    raise

# Constants
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")  # Will be set from VM metadata
if not PROJECT_ID:
    # Try to get from gcloud config
    import subprocess
    try:
        PROJECT_ID = subprocess.check_output(["gcloud", "config", "get-value", "project"]).decode().strip()
        logger.info(f"Project ID from gcloud: {PROJECT_ID}")
    except:
        PROJECT_ID = "your-project-id"  # Fallback

RECOGNIZER_ID = f"projects/{PROJECT_ID}/locations/global/recognizers/aide-stt"

class TranscriptResponse(BaseModel):
    transcript: str
    confidence: float
    language_code: str
    request_id: str

@app.get("/")
async def root():
    return {"message": "AIDE Speech-to-Text API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "project_id": PROJECT_ID}

@app.post("/transcribe", response_model=TranscriptResponse)
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Convert uploaded audio file to transcript using Google Cloud Speech-to-Text
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400,
            detail="File must be an audio file"
        )
    
    # Generate unique request ID
    request_id = str(uuid.uuid4())
    
    try:
        # Read audio file into memory
        audio_content = await file.read()
        
        # Check file size (max 10MB for this example)
        if len(audio_content) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail="Audio file too large. Maximum size: 10MB"
            )
        
        logger.info(f"Processing audio file: {file.filename}, size: {len(audio_content)} bytes, request_id: {request_id}")
        
        # Configure recognition request
        # Note: For v2 API, we need to create a recognizer first
        # For simplicity, we'll use the v1 API for now
        
        from google.cloud import speech_v1
        
        client_v1 = speech_v1.SpeechClient()
        
        audio = speech_v1.RecognitionAudio(content=audio_content)
        config = speech_v1.RecognitionConfig(
            encoding=speech_v1.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code="en-US",
            enable_automatic_punctuation=True,
            model="default",
            use_enhanced=True,
        )
        
        # Perform transcription
        logger.info(f"Sending request to Google STT for request_id: {request_id}")
        response = client_v1.recognize(config=config, audio=audio)
        
        # Extract transcript and confidence
        transcript = ""
        confidence = 0.0
        
        for result in response.results:
            alternative = result.alternatives[0]
            transcript = alternative.transcript
            confidence = alternative.confidence
            break  # Get first result
        
        if not transcript:
            logger.warning(f"No transcript found for request_id: {request_id}")
            transcript = "[No speech detected]"
            confidence = 0.0
        
        logger.info(f"Transcript generated for request_id: {request_id}: '{transcript[:50]}...'")
        
        return TranscriptResponse(
            transcript=transcript,
            confidence=confidence,
            language_code="en-US",
            request_id=request_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing audio for request_id {request_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing audio: {str(e)}"
        )

@app.post("/transcribe-long")
async def transcribe_long_audio(file: UploadFile = File(...)):
    """
    Convert long audio file to transcript using Google Cloud Speech-to-Text (async)
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400,
            detail="File must be an audio file"
        )
    
    request_id = str(uuid.uuid4())
    
    try:
        # Save audio temporarily
        audio_content = await file.read()
        
        # Use long-running operation for larger files
        from google.cloud import speech_v1
        
        client_v1 = speech_v1.SpeechClient()
        
        audio = speech_v1.RecognitionAudio(content=audio_content)
        config = speech_v1.RecognitionConfig(
            encoding=speech_v1.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code="en-US",
            enable_automatic_punctuation=True,
            model="video",  # Better for longer audio
            use_enhanced=True,
        )
        
        # Start async operation
        operation = client_v1.long_running_recognize(config=config, audio=audio)
        
        return {
            "request_id": request_id,
            "status": "processing",
            "message": "Audio is being processed. Check status with the operation ID."
        }
        
    except Exception as e:
        logger.error(f"Error starting long transcription: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)