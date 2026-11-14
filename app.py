import subprocess
import os
import signal
import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Allow the browser to talk to the local server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state to hold the recording process
recording_process = None
output_file = ""

@app.get("/", response_class=HTMLResponse)
def read_index():
    # Serves the UI
    with open("index.html", "r") as f:
        return f.read()

@app.get("/api/devices")
def get_devices():
    """Scrapes FFmpeg to find the exact names of your Mac's screen, camera, and mic."""
    result = subprocess.run(
        ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True, text=True
    )
    return {"log": result.stderr}

@app.post("/api/start")
def start_recording(use_cam: bool = True, use_mic: bool = True):
    global recording_process, output_file
    if recording_process:
        raise HTTPException(status_code=400, detail="Already recording")

    os.makedirs("recordings", exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_file = f"recordings/lume_{timestamp}.mp4"

    # Base command: Capture Screen (index 1 on most Macs)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "avfoundation", "-capture_cursor", "1", "-framerate", "30", "-i", "1"
    ]

    # Build the complex filter based on UI toggles
    filter_complex = "[0:v]"
    maps = ""
    
    if use_cam:
        # Capture Webcam (index 0)
        cmd.extend(["-f", "avfoundation", "-framerate", "30", "-i", "0"])
        # Overlay webcam in bottom right corner
        filter_complex += "scale=1920:-2[bg];[1:v]scale=320:-2[cam];[bg][cam]overlay=W-w-20:H-h-20[v]"
        maps += "-map [v] "
    else:
        filter_complex += "scale=1920:-2[v]"
        maps += "-map [v] "

    if use_mic:
        # Capture Mic (index 0). Using async resample to fix audio drift/glitches.
        cmd.extend(["-f", "avfoundation", "-i", ":0"])
        maps += "-map 2:a -c:a aac -b:a 128k -ar 44100 "

    # The QuickTime-proof output flags
    cmd.extend([
        "-filter_complex", filter_complex,
        *maps.split(),
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", output_file
    ])

    # Start FFmpeg in the background
    recording_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return {"status": "recording", "file": output_file}

@app.post("/api/stop")
def stop_recording():
    global recording_process, output_file
    if not recording_process:
        raise HTTPException(status_code=400, detail="Not recording")

    # Send 'q' to FFmpeg so it stops gracefully (saves the MP4 perfectly)
    recording_process.stdin.write(b'q\n')
    recording_process.stdin.flush()
    recording_process.wait()
    recording_process = None

    return {"status": "saved", "path": os.path.abspath(output_file)}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Lume is running at http://localhost:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
