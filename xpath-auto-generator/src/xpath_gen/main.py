"""Application entry point."""

import xpath_gen.playwright_compat  # noqa: F401 — Windows event loop policy

from xpath_gen.web.app import app


def cli() -> None:
    import uvicorn

    uvicorn.run("xpath_gen.web.app:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    cli()
