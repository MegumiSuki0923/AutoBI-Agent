from fastapi import APIRouter

aa_router = APIRouter()

@aa_router.get("/get")
def get_test():
    return {"method": "aa的get方法"}

@aa_router.put("/put")
def put_test():
    return {"method": "aa的put方法"}

@aa_router.post("/post")
def post_test():
    return {"method": "aa的post方法"}

@aa_router.delete("/delete")
def delete_test():
    return {"method": "aa的delete方法"}