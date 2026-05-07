# Setup Guide

1. Create and activate a virtual environment
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env`
4. Run API: `uvicorn app.main:app --reload`
5. Run tests: `pytest`
6. Run Streamlit demo: `streamlit run ui/streamlit_app.py`
