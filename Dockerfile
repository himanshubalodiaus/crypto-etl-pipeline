# Start from an official, slim Python image — a minimal Linux with Python 3.11
FROM python:3.11-slim

# Set the working directory inside the container. Everything below happens here.
WORKDIR /app

# Copy ONLY requirements first, then install. This is a Docker optimization:
# as long as requirements.txt doesn't change, Docker reuses the cached install
# layer on rebuilds instead of reinstalling every time.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the pipeline code into the container.
COPY extract.py backfill.py transform.py validate.py load.py ./

# The default command run when the container starts: run the full pipeline.
# (backfill -> transform -> validate -> load, via load.py's __main__ block)
CMD ["python", "load.py"]