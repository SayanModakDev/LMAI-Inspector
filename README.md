# AI-Assisted Packaged Commodity Compliance System

An AI-powered system designed to assist Legal Metrology inspectors in validating compliance of packaged commodities with Legal Metrology (Packaged Commodities) Rules, 2011.

## Overview
This system uses Optical Character Recognition (OCR) to extract text from product labels and automatically validates mandatory declarations (like MRP, Net Quantity, Date of Manufacturing, etc.) based on configurable rules.

Each inspection can include any number of product images. OCR, visual candidates, barcode attempts, and extracted evidence from all images are combined into one inspection result.

It acts as an **inspection-support tool** to highlight potential non-compliances for further review by human inspectors.

## Architecture
- **Backend:** FastAPI, Python, SQLAlchemy, PaddleOCR, OpenCV
- **Database:** MySQL (with SQLite development fallback)
- **Frontend:** React, Vite
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

### Quick Windows Start
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
- Node.js & npm (for Frontend)
- MySQL 8.0+

### Database Setup
Create a MySQL database and update the `.env` file in the `backend/` directory:
```
DB_USER=root
DB_PASSWORD=password
DB_HOST=localhost
DB_PORT=3306
DB_NAME=legal_metrology
```

### Backend Setup
1. Navigate to `backend/`: `cd backend`
2. Create virtual environment: `python -m venv venv`
3. Activate virtual environment: `venv\Scripts\activate` (Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Run the server: `uvicorn app.main:app --reload`
The backend will run at `http://localhost:8000`. Swagger docs available at `http://localhost:8000/docs`.

### Frontend Setup
1. Navigate to `frontend/`: `cd frontend`
2. Install dependencies: `npm install`
3. Start the dev server: `npm run dev`
The frontend will run at `http://localhost:5173`.

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
