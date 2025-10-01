#!/bin/bash
# A helper script to run linting and type checking.

set -e # Exit immediately if a command exits with a non-zero status.

echo "Running ruff for linting and formatting checks..."
ruff check .
ruff format --check .

echo "Running mypy for static type checking..."
mypy

echo "All checks passed!"
