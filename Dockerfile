FROM python:3.9  # Or your preferred version
RUN apt-get update && apt-get install -y procps
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "main.py"]
