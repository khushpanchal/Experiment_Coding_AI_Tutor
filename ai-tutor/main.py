import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from agent import ChatAgent

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "..", "uploaded_pdfs")

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI()

chat_agent = ChatAgent()

@app.post("/chat")
async def chat(
    query: str = Form(...),
    file: UploadFile | None = File(None)
):
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    pdf_path = None

    if file:
        if file.content_type != "application/pdf":
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are supported"
            )

        pdf_path = os.path.join(UPLOAD_DIR, file.filename)

        with open(pdf_path, "wb") as f:
            f.write(await file.read())

    result = await chat_agent.run(query, pdf_path)

    return {
        "answer": result
    }
