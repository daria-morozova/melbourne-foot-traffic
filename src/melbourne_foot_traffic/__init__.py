"""Melbourne CBD foot traffic: data pipeline, forecast model and analysis."""


def main() -> None:
    """Entry point for `uv run melbourne-foot-traffic`."""
    from .pipeline import main as pipeline_main

    pipeline_main()
