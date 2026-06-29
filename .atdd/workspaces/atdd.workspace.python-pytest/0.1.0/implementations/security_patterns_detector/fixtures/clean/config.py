"""Clean: no secret literals — values come from the environment."""
import os

API_TIMEOUT = 30
DB_PASSWORD = os.environ["DB_PASSWORD"]
API_KEY = os.environ.get("API_KEY")
