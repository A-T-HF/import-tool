FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py transformer.py bookinglist_reader.py mews_reader.py \
     guests_importer.py guests_schema.sql hs3_csv_reader.py ./
COPY templates/ templates/

ENV FLASK_APP=app
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=8080

EXPOSE 8080

USER nobody

CMD ["flask", "run", "--port", "8080"]
