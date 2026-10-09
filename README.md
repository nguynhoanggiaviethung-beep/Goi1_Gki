# Goi1_Gki

Starter đồ án full-stack: React + TypeScript + Vite (frontend) và FastAPI (backend).

## Chạy trên Windows PowerShell
Mở hai terminal tại thư mục repo.

Terminal 1:
.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --reload --port 8000

Terminal 2:
cd frontend
npm run dev

Frontend: http://localhost:5173
API docs: http://localhost:8000/docs

Cài lại backend deps: python -m pip install -r backend\requirements.txt
Cài lại frontend deps: cd frontend; npm install

