
FROM python:3.9

WORKDIR /app
RUN ls -l /app
COPY requirements.txt .
RUN mkdir -p /app/logs
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "app.py"]

