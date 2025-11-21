FROM python:3.10-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    wget unzip curl \
    chromium chromium-driver \
    xvfb \
    && apt-get clean

# Set display for headless mode
ENV DISPLAY=:99

# Create work directory
WORKDIR /app

# Copy project
COPY . .

# Install pip requirements
RUN pip install --no-cache-dir -r requirements.txt

# Run start script
CMD ["bash", "start.sh"]
