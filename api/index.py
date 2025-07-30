from fastapi import FastAPI, File, UploadFile

app = FastAPI()

@app.get("/")
def root():
    return {"message": "It works!"}

@app.post("/test/")
async def test(file: UploadFile = File(...)):
    return {"filename": file.filename}
