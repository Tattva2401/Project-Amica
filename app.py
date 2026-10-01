"""
===============================================================================
Project Amica - Root Launcher Stub
===============================================================================
In Milestone v0.2+, Project Amica was decoupled into:
  - backend/main.py  (FastAPI Brain Service on port 8000)
  - frontend/app.py  (Flet Desktop Client Face)

This stub delegates to `run.py` so you can launch both services using either:
  $ python run.py
  or
  $ python app.py
===============================================================================
"""

from run import main

if __name__ == "__main__":
    main()
