# AI-Assisted Packaged Commodity Compliance System

An AI-powered system designed to assist Legal Metrology inspectors in validating compliance of packaged commodities with Legal Metrology (Packaged Commodities) Rules, 2011.

## Overview
This system uses Optical Character Recognition (OCR) to extract text from product labels and automatically validates mandatory declarations (like MRP, Net Quantity, Date of Manufacturing, etc.) based on configurable rules.

Each inspection can include any number of product images. OCR, visual candidates, barcode attempts, and extracted evidence from all images are combined into one inspection result.

It acts as an **inspection-support tool** to highlight potential non-compliances for further review by human inspectors.

## Architecture
- **Frontend:** React + Vite (deployed on Vercel or any static host)
- **Backend:** FastAPI, Python 3.11, SQLAlchemy, PaddleOCR, OpenCV (deployed on external Linux VM/Server)
- **Database:** MySQL (with SQLite development fallback)
- **Reporting:** ReportLab (PDF Generation)

## Project Structure
- `backend/`: FastAPI application containing all business logic.
  - `app/api/`: REST endpoints (scan, history, categories, rules, manual-input).
  - `app/extraction/`: OCR text processing and regex matching.
  - `app/classification/`: AI/NLP category classification (FOOD, COSMETIC, GENERAL).
  - `app/rules/`: Dynamic rule evaluation and applicability filtering.
  - `app/reports/`: PDF report generation.
- `frontend/`: React + Vite application for the inspector dashboard.
- `data/`: Configuration files, including the core `rule_matrix.json`.

## Setup Instructions

### Quick Windows Start (Local Development)
From the project root, run:
```
start_app.bat
```

This launches:
- Backend API: http://localhost:8000
- Frontend UI: http://localhost:5173

To stop the running processes:
```
stop_app.bat
```

If you prefer to start the services manually:

### Prerequisites
- Python 3.11+
- Node.js 18+ & npm (for Frontend)
- MySQL 8.0+ (optional; SQLite fallback enabled by default)

### Database Setup
To use MySQL, create a database and update the `.env` file in the `backend/` directory:
```
DATABASE_ENABLED=true
DATABASE_URL=mysql+pymysql://root:password@localhost:3306/legal_metrology_db
```
For local testing and development, leave `DATABASE_ENABLED=false` to use the bundled SQLite database.

### Backend Setup (Local Development)
1. Navigate to `backend/`: `cd backend`
2. Create virtual environment: `python -m venv venv`
3. Activate virtual environment: `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Linux)
4. Install dependencies: `pip install -r requirements.txt`
5. Run the server: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
The backend will run at `http://localhost:8000`. Swagger docs are available at `http://localhost:8000/docs`.

### Frontend Setup (Local Development)
1. Navigate to `frontend/`: `cd frontend`
2. Install dependencies: `npm install`
3. Configure environment: Copy `.env.example` to `.env` or leave unset to use the local dev proxy.
4. Start the dev server: `npm run dev`
The frontend will run at `http://localhost:5173`.

---

## Production Deployment

### 1. External Backend Deployment (Linux Server / VM)
The FastAPI backend can be hosted on any generic Linux server or cloud VM (e.g. Ubuntu 22.04 LTS / Debian):

1. Provision the Linux instance and install system dependencies:
   ```bash
   sudo apt update && sudo apt install -y python3-pip python3-venv git libgl1 libglib2.0-0
   ```
2. Clone the repository and configure virtual environment:
   ```bash
   git clone <repo-url>
   cd SIH-Project/backend
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
3. Create `.env` from `.env.example`:
   ```bash
   cp .env.example .env
   ```
   Configure the production settings:
   - `DEBUG=false`
   - `PORT=8000` (or your chosen service port)
   - `CORS_ORIGINS=https://your-frontend-app.vercel.app`
   - `PUBLIC_BASE_URL=https://api.yourdomain.com`
4. Run the backend service:
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
   ```
   *(Running under systemd or a process manager like PM2 / supervisor behind an Nginx reverse proxy with HTTPS/SSL is recommended).*

### 2. Frontend Deployment (Vercel)
The React frontend is optimized for deployment on Vercel:

1. Connect your repository to Vercel and set the Root Directory to `frontend`.
2. In the Vercel Project Settings > Environment Variables, set:
   ```
   VITE_API_BASE_URL=https://api.yourdomain.com
   ```
3. Deploy. The frontend SPA will route all API calls, image assets, and report requests directly to your configured external FastAPI backend.

## Features
1. **Automated Scanning:** Upload product labels and automatically extract text using PaddleOCR.
2. **Product Images:** Upload or capture any number of images in one inspection; each image is stored and processed independently.
3. **Category Classification:** Automatically identifies if a product is FOOD, COSMETIC, or GENERAL based on keywords.
4. **Dynamic Rule Validation:** Checks extracted fields against a configurable `rule_matrix.json`.
5. **Manual Override:** Inspectors can correct OCR errors and re-evaluate compliance on the fly.
6. **PDF Reports:** Generates professional compliance reports via ReportLab.
7. **Dashboard & History:** Tracks all inspections with aggregate compliance statistics.

### Barcode behavior
The scanner records a decoded barcode value when it can detect one directly or from valid EAN-13 text recognized by OCR. It then checks Open Food Facts for optional product metadata. A barcode is only an identifier: if the external database does not contain that code, the result reports `NOT_FOUND` and does not invent a product name.

### Regulatory sources
The rule matrix separates `LEGAL_METROLOGY` from `FSSAI_FOOD_LABELING`. Source configuration is based on the official Department of Consumer Affairs Legal Metrology page and the official FSSAI site:
- https://consumeraffairs.gov.in/pages/legal-metrology-act
- https://www.fssai.gov.in/

Rules remain marked `PENDING_VERIFICATION` where the exact gazette provision, amendment, exception, or effective date has not been independently mapped into the matrix. The application is an AI-assisted inspection-support tool, not a final legal certification system.

## Disclaimer
This is a support tool. Final legal verification must be made by an authorized inspector.
