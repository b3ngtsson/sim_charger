# CLAUDE.md - Development Guidelines

## Commands
- **Run server**: `python app.py` || `flask run`
- **Run server**: `python app.py`
- **Install dependencies**: `pip install -r requirements.txt`
- **Environment setup**: Create `.env` file with `OPENCHARGE_KEY=your_api_key`

## Code Style
- **Imports**: Group imports - standard library, third-party, local modules
- **Typing**: Use type hints (List, Dict, Optional) for function parameters and returns
- **Naming**: snake_case for functions/variables, CamelCase for classes
- **Error Handling**: Use try/except blocks with specific exceptions, log errors
- **Functions**: Document with docstrings using Args/Returns format

## Project Structure
- Flask app with service modules organized by functionality
- Services: chargers, map, route, soc, time
- Constants defined at module level
- Cache API responses when possible (lru_cache)