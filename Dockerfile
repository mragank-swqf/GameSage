FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

# Install Python dependencies first (cached layer — only re-runs when requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code into the image
COPY . .

# Start FastAPI (app.main:app is created in Feature 4)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
