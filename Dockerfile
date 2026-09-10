FROM python:3.12-slim

WORKDIR /app
COPY index.html style.css script.js ./

EXPOSE 8260

CMD ["python", "-m", "http.server", "8260"]
