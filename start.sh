#!/usr/bin/env bash
set -eo pipefail
set -m

# ==============================================================================
# Resume Ranker - Unified Dev Server Runner
# Starts both Backend (FastAPI) and Frontend (Vite) concurrently with
# color-coded logs for clear differentiation between services.
# ==============================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"

BACKEND_PORT="${PORT:-${BACKEND_PORT:-8000}}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

# ANSI color codes (ANSI-C style for bash)
CLR_BACKEND=$'\033[1;36m'   # Bold Cyan
CLR_FRONTEND=$'\033[1;35m'  # Bold Magenta
CLR_BANNER=$'\033[1;34m'    # Bold Blue
CLR_SUCCESS=$'\033[1;32m'   # Bold Green
CLR_WARN=$'\033[1;33m'      # Bold Yellow
CLR_ERROR=$'\033[1;31m'     # Bold Red
CLR_RESET=$'\033[0m'

# Ensure unbuffered output and preserve colors through pipes
export PYTHONUNBUFFERED=1
export FORCE_COLOR=1
export RUN_LOCAL_WORKERS=true

BACKEND_PID=""
FRONTEND_PID=""
CLEANING_UP=0

cleanup() {
    # Prevent duplicate runs
    if [ "${CLEANING_UP}" -eq 1 ]; then
        return
    fi
    CLEANING_UP=1

    trap - SIGINT SIGTERM EXIT
    echo ""
    echo -e "${CLR_WARN}[runner]    Shutting down servers...${CLR_RESET}"

    # Terminate process groups
    if [ -n "${BACKEND_PID}" ]; then
        kill -TERM "-${BACKEND_PID}" 2>/dev/null || kill -TERM "${BACKEND_PID}" 2>/dev/null || true
    fi

    if [ -n "${FRONTEND_PID}" ]; then
        kill -TERM "-${FRONTEND_PID}" 2>/dev/null || kill -TERM "${FRONTEND_PID}" 2>/dev/null || true
    fi

    # Wait briefly for graceful exit
    local timeout=20
    while [ "${timeout}" -gt 0 ]; do
        local still_running=0
        if [ -n "${BACKEND_PID}" ] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
            still_running=1
        fi
        if [ -n "${FRONTEND_PID}" ] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
            still_running=1
        fi
        if [ "${still_running}" -eq 0 ]; then
            break
        fi
        sleep 0.1
        timeout=$((timeout - 1))
    done

    # Force kill if still hanging
    if [ -n "${BACKEND_PID}" ]; then
        kill -KILL "-${BACKEND_PID}" 2>/dev/null || kill -KILL "${BACKEND_PID}" 2>/dev/null || true
    fi
    if [ -n "${FRONTEND_PID}" ]; then
        kill -KILL "-${FRONTEND_PID}" 2>/dev/null || kill -KILL "${FRONTEND_PID}" 2>/dev/null || true
    fi

    echo -e "${CLR_SUCCESS}[runner]    All servers stopped.${CLR_RESET}"
    exit 0
}

# Reset signal masks so SIGINT is processed even in non-interactive parent shells
trap - INT TERM EXIT
trap cleanup INT TERM EXIT

echo -e "${CLR_BANNER}========================================================================${CLR_RESET}"
echo -e "${CLR_BANNER} Resume Intelligence Platform — Development Environment${CLR_RESET}"
echo -e "${CLR_BANNER}========================================================================${CLR_RESET}"
echo -e " ${CLR_BACKEND}[backend]  ${CLR_RESET} FastAPI server  -> http://localhost:${BACKEND_PORT}"
echo -e " ${CLR_FRONTEND}[frontend] ${CLR_RESET} Vite dev server -> http://localhost:${FRONTEND_PORT}"
echo -e " Press ${CLR_WARN}Ctrl+C${CLR_RESET} at any time to stop both servers."
echo -e "${CLR_BANNER}========================================================================${CLR_RESET}\n"

# Verify backend prerequisites
if [ ! -d "${BACKEND_DIR}" ]; then
    echo -e "${CLR_ERROR}[error] Backend directory not found at ${BACKEND_DIR}${CLR_RESET}" >&2
    exit 1
fi

# Verify frontend prerequisites
if [ ! -d "${FRONTEND_DIR}" ]; then
    echo -e "${CLR_ERROR}[error] Frontend directory not found at ${FRONTEND_DIR}${CLR_RESET}" >&2
    exit 1
fi

# Determine backend command
if command -v uv >/dev/null 2>&1; then
    BACKEND_EXEC="uv run uvicorn src.main:app --port ${BACKEND_PORT} --reload --reload-dir src --use-colors"
else
    BACKEND_EXEC="uvicorn src.main:app --port ${BACKEND_PORT} --reload --reload-dir src --use-colors"
fi

# Start backend server
(
    cd "${BACKEND_DIR}"
    if [ -f .venv/bin/activate ]; then
        source .venv/bin/activate
    fi
    exec ${BACKEND_EXEC}
) > >(sed -u "s/^/${CLR_BACKEND}[backend]  ${CLR_RESET}/") 2>&1 &
BACKEND_PID=$!

# Start frontend server
(
    cd "${FRONTEND_DIR}"
    exec npm run dev -- --port "${FRONTEND_PORT}"
) > >(sed -u "s/^/${CLR_FRONTEND}[frontend] ${CLR_RESET}/") 2>&1 &
FRONTEND_PID=$!

# Wait for any process to exit
wait -n "${BACKEND_PID}" "${FRONTEND_PID}" || true
cleanup
