#!/bin/bash
# Setup script pro pre-commit hooks

echo "Installing pre-commit hooks..."

# Instalace pre-commit
pip install pre-commit detect-secrets

# Vytvoření baseline pro detect-secrets
if [ ! -f .secrets.baseline ]; then
    echo "Creating .secrets.baseline..."
    detect-secrets scan > .secrets.baseline
fi

# Instalace hooků
pre-commit install

echo "✅ Pre-commit hooks installed successfully!"
echo ""
echo "Hooks will now check for:"
echo "  - Sensitive files (.env, *.log, *.db)"
echo "  - Hardcoded secrets"
echo "  - Code formatting (black, flake8, isort)"
echo ""
echo "To test: pre-commit run --all-files"

