from fastapi import FastAPI
from fastapi import Request
from fastapi.staticfiles import StaticFiles

from api.aa import aa_router
from api.bb import bb_router
from api.cc import cc_router

# web服务器
import uvicorn

app = FastAPI()

app.mount("/upimg", StaticFiles(directory="upimg"), name="upimg")

app.include_router(aa_router, prefix="/aa", tags=["aa接口"])
app.include_router(bb_router, prefix="/bb", tags=["bb接口"])
app.include_router(cc_router, prefix="/cc", tags=["cc接口"])

@app.get("/")
async def root():
    return {"message": "Hello Lain"}

@app.get("/get")
def get_test():
    return {"method": "get方法"}

@app.put("/put")
def put_test():
    return {"method": "put方法"}

@app.post("/post")
def post_test():
    return {"method": "post方法"}

@app.delete("/delete")
def delete_test():
    return {"method": "delete方法"}

@app.get("/get_request")
def get_request(request: Request):
    get_request = request.query_params
    print(get_request)
    return {"message": "get_request方法"}

@app.post("/post_request")
def post_request(request: Request):
    post_request = request.json()
    print(post_request)
    return {"message": "post_request方法"}

if __name__ == "__main__":
    uvicorn.run(app="fastapi_demo:app", host="127.0.0.1", port=8000, reload=True)