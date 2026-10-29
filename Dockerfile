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

# Refresh the RAG artifacts at build time, using the SAME config the server serves.
# There is exactly one config (workspace/publisher.config.json): a second, narrower
# build-time config is what let jaffle_shop/comics ship with no Stage-2 graph, so
# malloy_getContext relayed them to the raw source stub and lost every money measure.
#
# No --fresh: existing graphs are reused and missing ones are built; Chroma is re-indexed
# per context (delete-where-context + upsert), so this is idempotent and works whether
# context/chroma_db is present (local build) or absent (Cloud Build, .gcloudignore).
#
# MOTHERDUCK_TOKEN is required, not optional: Stage 1 compiles every served package and
# jaffle_shop/comics only compile against MotherDuck.  Pass it as a build arg, never as an
# ENV, so it is baked into no layer:
#     docker build --build-arg MOTHERDUCK_TOKEN="$(cat token)" .
# CI supplies it through cloudbuild.yaml, which mounts it from Secret Manager with
# secretEnv (see TASK-08 in DOCUMENTATION/2_Plan_and_Implementation/11_PROJECT_1_RAG_Context_Coverage.md).
ARG MOTHERDUCK_TOKEN

# 1) Report the coverage of the incoming build context (advisory, --soft = never fails).
# 2) Rebuild graphs + vectors for every served package.
# 3) Fail the image if coverage regressed, and require the two measures the original bug
#    destroyed: an image that would answer malloy_getContext without money measures must
#    not be buildable.
ENV PYTHONPATH="/app/context:/app/context/shared"
RUN python3 /app/context/orchestration/verify_index_coverage.py --soft \
      --config /app/workspace/publisher.config.json \
 && MOTHERDUCK_TOKEN="${MOTHERDUCK_TOKEN}" \
    python3 /app/context/orchestration/run_context_pipeline.py --all --index-chroma \
      --config /app/workspace/publisher.config.json \
 && python3 /app/context/orchestration/verify_index_coverage.py \
      --config /app/workspace/publisher.config.json \
      --require jaffle_shop:Total_Revenue \
      --require jaffle_shop:Gross_Margin

# Ensure entrypoint script is executable
RUN chmod +x ./context/deploy/entrypoint.sh

# Cleanup any stale local database files
RUN rm -rf ./workspace/publisher.db* \
           ./workspace/publisher_data/

ENV MALLOY_SERVER_MODE=mcp

EXPOSE 8080

ENTRYPOINT ["/app/context/deploy/entrypoint.sh"]
