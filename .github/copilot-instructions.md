# Project Guidelines

## Code Style
Follow PEP 8 for Python code. Use 4 spaces for indentation, limit lines to 79 characters.

## Build and Test
Install dependencies with `pip install -r requirements.txt` if present.
Run the main script with `python main.py`.
For testing, use pytest if tests are added: `python -m pytest`.

## Conventions
- Use snake_case for variables and functions, CamelCase for classes.
- For blockchain-related code, store API keys and private keys in environment variables (e.g., using python-dotenv).
- Avoid hardcoding sensitive information.
- Use logging for tracking operations and errors.

## Architecture
As the project grows, organize code into modules under a `src/` directory:
- `wallet.py` for wallet management
- `transaction.py` for transaction handling
- `analytics.py` for financial analysis

Use classes to encapsulate blockchain interactions, such as a `BlockchainClient` class.