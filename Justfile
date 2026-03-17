# newsloupe development tasks

# Default recipe - show available commands
default:
    @just --list

# Start development server with auto-reload
dev:
    uvicorn serve:app --host 0.0.0.0 --port 8001 --reload

# Kill any running server processes
kill:
    @echo "Killing newsloupe server processes..."
    @pkill -f "serve:app" 2>/dev/null || echo "No server processes found"
    @pkill -f "serve.py" 2>/dev/null || true
    @echo "Done"

# Seed database from interests.json
seed file="interests.json":
    python seed.py --file {{file}}

# Run tests
test:
    python -m pytest tests/

# Show current configuration
config:
    @echo "Current configuration:"
    @echo "  INTERESTS_PATH: ${INTERESTS_PATH:-interests.json}"
    @echo "  HN_FEED: ${HN_FEED:-front_page}"
    @echo "  HN_SOURCE: ${HN_SOURCE:-scraper}"
    @echo "  CLICKS_DB_PATH: ${CLICKS_DB_PATH:-clicks.db}"
    @echo "  EMBEDDINGS_CACHE_PATH: ${EMBEDDINGS_CACHE_PATH:-.embeddings_cache.json}"

# View recent click history
clicks limit="10":
    @curl -s http://localhost:8001/api/clicks?limit={{limit}} | python -m json.tool

# Docker build and run
docker-build:
    docker compose build

docker-up:
    docker compose up -d

docker-down:
    docker compose down

docker-logs:
    docker compose logs -f

# Clean up generated files
clean:
    rm -f clicks.db .embeddings_cache.json output.html server.log
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete
