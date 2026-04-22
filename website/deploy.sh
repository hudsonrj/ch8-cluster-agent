#!/bin/bash
set -e

echo "🚀 Deploying CH8 Agent Website..."
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running!"
    exit 1
fi

# Navigate to website directory
cd "$(dirname "$0")"

# Pull latest changes (if in git repo)
if git rev-parse --git-dir > /dev/null 2>&1; then
    echo "📥 Pulling latest changes..."
    git pull origin master
fi

# Stop existing container
echo "🛑 Stopping existing container..."
docker compose down 2>/dev/null || true

# Build and start
echo "🔨 Building and starting container..."
docker compose up -d --build

# Wait for container to be healthy
echo "⏳ Waiting for container to start..."
sleep 5

# Check if running
if docker compose ps | grep -q "Up"; then
    echo ""
    echo "✅ Deploy successful!"
    echo ""
    echo "🌐 Website running at:"
    echo "   Local:    http://localhost:8080"
    echo "   External: http://$(hostname -I | awk '{print $1}'):8080"
    echo ""
    echo "📋 Useful commands:"
    echo "   docker compose logs -f        # View logs"
    echo "   docker compose ps             # Check status"
    echo "   docker compose restart        # Restart"
    echo "   docker compose down           # Stop"
    echo ""
else
    echo "❌ Deploy failed!"
    docker compose logs
    exit 1
fi
