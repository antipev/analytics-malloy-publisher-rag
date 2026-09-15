FROM node:20-slim

# Install system dependencies (curl, python3, pip, venv)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Install Malloy Publisher server globally
RUN npm install -g @malloy-publisher/server@0.0.244

# Create Python virtual environment and install RAG dependencies
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY context/orchestration/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app

# Copy configuration, workspace, and context
COPY malloy-config.json ./
COPY workspace/ ./workspace/
COPY context/ ./context/

# Install context JS dependencies for Malloy AST compilation
WORKDIR /app/context
RUN npm install --omit=dev
WORKDIR /app

# Run context pipeline to refresh ChromaDB and RAG Intent Graph at build time
ENV PYTHONPATH="/app/context:/app/context/shared"
RUN python3 /app/context/orchestration/run_context_pipeline.py --all --fresh --index-chroma

# Ensure entrypoint script is executable
RUN chmod +x ./context/deploy/entrypoint.sh

# Cleanup any stale local database files
RUN rm -rf ./workspace/publisher.db* \
           ./workspace/publisher_data/

ENV MALLOY_SERVER_MODE=ui

EXPOSE 8080

ENTRYPOINT ["/app/context/deploy/entrypoint.sh"]
