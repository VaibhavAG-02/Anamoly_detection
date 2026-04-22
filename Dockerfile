FROM nvcr.io/nvidia/l4t-pytorch:r35.2.1-pth2.0-py3

# System deps
RUN apt-get update && apt-get install -y \
    python3-opencv \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip3 install --upgrade pip setuptools wheel

# Remove any conflicting pip cv2, keep system one
RUN pip3 uninstall -y opencv-python opencv-python-headless opencv-contrib-python || true

# Install ultralytics without pulling in its own opencv
RUN pip3 install --no-deps ultralytics
RUN pip3 install rich PyYAML tqdm matplotlib scipy pillow psutil py-cpuinfo ultralytics-thop polars

# Tell ultralytics to use system cv2
ENV PYTHONPATH="/usr/lib/python3/dist-packages:${PYTHONPATH}"

WORKDIR /app
COPY . .

# Test imports
RUN python3 -c "import cv2; print('cv2 OK:', cv2.__version__)"
RUN python3 -c "from ultralytics import YOLO; print('YOLO OK')"

# Download weights
RUN python3 -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

CMD ["python3", "camera.py", "live", "--headless", "--interval", "10"]
