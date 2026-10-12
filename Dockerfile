FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY web web
COPY examples examples
COPY run.py LICENSE THIRD_PARTY_NOTICES.md ./
# Native local deployment is preferred. Container preview uses the documented
# explicit loopback host-published port and cannot use run.py's loopback bind.
CMD ["python", "-c", "from app import create_app; from waitress import serve; serve(create_app(), host='0.0.0.0', port=8765)"]
