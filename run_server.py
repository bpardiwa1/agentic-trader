# run_server.py
import os

from dotenv import load_dotenv


def main():
    load_dotenv()  # loads .env into os.environ

    import uvicorn

    port = int(os.environ.get("PORT", "8001"))
    reload = os.environ.get("RELOAD", "true").lower() == "true"
    log_level = os.environ.get("LOG_LEVEL", "info")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
        log_level=log_level,
    )


if __name__ == "__main__":
    main()
