from flask import Flask, request, render_template, send_from_directory, url_for
import os
import torch
import torchaudio
import soundfile as sf
import numpy as np
from demucs.hdemucs import HDemucs
from demucs.apply import apply_model, BagOfModels

app = Flask(__name__)

# Define paths
UPLOAD_FOLDER = "uploads"
PROCESSED_FOLDER = "processed"
MODEL_PATH = "models/vr.pth"

# Create necessary folders
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

# Allow safe model loading
torch.serialization.add_safe_globals([BagOfModels, HDemucs])

# Load trained model
print("Loading trained model...")
try:
    checkpoint = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)

    if isinstance(checkpoint, BagOfModels):
        model = checkpoint.models[0]  # Extract model if it's a BagOfModels
    else:
        model = checkpoint  # Use directly if it's already HDemucs

    model.eval()
    print("✅ Model loaded successfully!")
except Exception as e:
    print(f"❌ Error loading model: {e}")
    model = None

# Function to process audio and apply separation
def process_audio(input_path, filename):
    print(f"Processing: {filename}...")

    # Load audio
    audio, sr = torchaudio.load(input_path)

    # Convert mono to stereo if needed
    if audio.shape[0] == 1:
        audio = torch.cat([audio, audio], dim=0)

    # Run model inference
    with torch.no_grad():
        sources = apply_model(model, audio[None], device="cpu")[0]

    # Convert sources to numpy arrays
    sources = sources.cpu().numpy()

    # Correct source separation
    instrumental = sources[0]  
    vocals = np.sum(sources[1:], axis=0)  

    # Define output folder
    output_dir = os.path.join(PROCESSED_FOLDER, filename.split(".")[0])
    os.makedirs(output_dir, exist_ok=True)

    # Save separated files
    vocal_path = os.path.join(output_dir, "vocals.wav")
    instrumental_path = os.path.join(output_dir, "instrumental.wav")
    sf.write(vocal_path, vocals.T, sr)
    sf.write(instrumental_path, instrumental.T, sr)

    print(f"Processing complete: {filename}")
    return vocal_path, instrumental_path

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if "file" not in request.files:
            return "No file uploaded!"

        file = request.files["file"]
        if file.filename == "":
            return "No selected file!"

        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)

        # Process the audio
        vocal_path, instrumental_path = process_audio(filepath, file.filename)

        return render_template("download.html", 
                               vocal_url=url_for('download_file', folder=file.filename.split(".")[0], filename="vocals.wav"),
                               instrumental_url=url_for('download_file', folder=file.filename.split(".")[0], filename="instrumental.wav"))

    return render_template("index.html")

@app.route("/processed/<folder>/<filename>")
def download_file(folder, filename):
    """Handles file download requests properly"""
    return send_from_directory(os.path.join(PROCESSED_FOLDER, folder), filename, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
