"""Enable `python -m muninn.ui` → launches the PyQt6 desktop.

H.2 (2026-05-12) — companion to the `muninn-ui` console script.
"""
from muninn.ui.main_window import main

if __name__ == "__main__":
    main()
