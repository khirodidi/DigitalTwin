#!/bin/bash
# =============================================================================
# push_to_github.sh
# Run this script locally (after downloading the zip) to push
# everything to your GitHub repository.
#
# Usage:
#   chmod +x push_to_github.sh
#   ./push_to_github.sh <your-github-username>
#
# Requirements:
#   - git installed
#   - GitHub CLI (gh) OR a personal access token configured
# =============================================================================

set -e

GITHUB_USER="${1:-YOUR_GITHUB_USERNAME}"
REPO_NAME="digitaltwin"
REPO_URL="https://github.com/${GITHUB_USER}/${REPO_NAME}.git"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Digital Twin — Push to GitHub                  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "Target: ${REPO_URL}"
echo ""

# Initialise git
git init
git add .

# Configure initial commit
git commit -m "feat: initial Digital Twin system

Full-stack factory monitoring digital twin:

Core:
- WSN → Mother Station → MQTT Broker → Digital Twin Engine
- Zone-based localisation (grid sensor coverage)
- Asset tracking: workers + mobile objects
- Environmental monitoring: temp, humidity, smoke
- Access control: per-asset sensor/zone authorisation
- Sensor health watchdog (Online/Degraded/Offline)
- If-else scenario engine + predictive alerts
- Real-time SystemState (NOMINAL/DEGRADED/CRITICAL)
- PostgreSQL persistence (9 tables)

AI Layer:
- Movement Optimiser (LSTM + PPO RL)
- Smart Evacuation (XGBoost danger scoring + Dijkstra routing)
- System Monitor (LSTM Autoencoder + Forecaster + Failure predictor)

Architecture diagrams (interactive React/JSX) in docs/"

# Set remote and push
git remote add origin "${REPO_URL}" 2>/dev/null || git remote set-url origin "${REPO_URL}"
git branch -M main
git push -u origin main

echo ""
echo "✓ All files pushed to ${REPO_URL}"
echo ""
