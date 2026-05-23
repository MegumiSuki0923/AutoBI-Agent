from fastapi import APIRouter

bb_router = APIRouter()

@bb_router.get("/get")
def get_test():
    return {"method": "bb的get方法"}

@bb_router.put("/put")
def put_test():
    return {"method": "bb的put方法"}

@bb_router.post("/post")
def post_test():
    return {"method": "bb的post方法"}

@bb_router.delete("/delete")
def delete_test():
    return {"method": "bb的delete方法"}