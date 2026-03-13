# Alchemind

Alchemind is an AI system that turns raw ideas into structured execution plans.

It converts an idea into:

- Problem
- Solution
- Tech stack
- Roadmap
- Risks

---

## Architecture

### Frontend
Next.js

### Backend
FastAPI

### AI
OpenAI API

---

## Project Structure


alchemind
│
├── backend
│ └── app
│ ├── api
│ ├── services
│ ├── llm
│ └── main.py
│
├── frontend
│ └── app
│ └── page.tsx
│
└── README.md


---

## Running Locally

### Backend


cd backend
py -m venv .venv
.venv\Scripts\Activate
pip install fastapi uvicorn openai python-dotenv
uvicorn app.main:app --reload


Backend runs on:


http://127.0.0.1:8000


---

### Frontend


cd frontend
npm install
npm run dev


Frontend runs on:


http://localhost:3000


---

## Environment Variables

Create a `.env` file inside the **backend** folder:


OPENAI_API_KEY=your_openai_api_key


---

## Author

Mahesh Reddy Pagadala