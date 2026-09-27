# Dockerfile
#
# This is a "recipe" Docker follows to build a self-contained package
# with everything needed to run the pipeline: Python, OpenCV, YOLO,
# llama-cpp-python, and your model weights, all in one place.
#
# Building inside Linux (which this base image uses, even on a Windows
# host) also solves the earlier "path too long" Windows build error for
# llama-cpp-python - Linux doesn't have that path-length limit.

FROM python:3.10-slim

# System libraries OpenCV needs to run (without a GUI/display) -
# without these, "import cv2" fails inside the container.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    build-essential \
    cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Model weights FIRST ---
# Placed early in the file on purpose: Docker caches each step, and
# this is the biggest, least-frequently-changing part. If you only
# change your Python code later, Docker reuses this cached layer
# instead of re-processing the huge model files every time.
COPY models /app/models

# --- Python dependencies next ---
# Also relatively stable - changes less often than your actual code.
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# --- Your actual code LAST ---
# This changes most often during development, so it goes last -
# keeps rebuilds fast since only this layer needs to redo when you
# edit a .py file.
COPY core /app/core
COPY alerts /app/alerts

# Default command when someone runs this image - adjust this once
# your API wrapper exists. For now, this runs the compatibility test
# so you can confirm everything works end-to-end inside the container.
CMD ["python", "core/vlm.py", "models/test_image.jpg"]