# run_auto.py
from dotenv import load_dotenv

load_dotenv()  # pull VERBOSE, AGENT_* etc from .env if you want

import auto_runner  # uses the same auto_runner.py you already have

auto_runner.loop()
