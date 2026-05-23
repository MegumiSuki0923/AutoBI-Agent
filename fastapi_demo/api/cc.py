from fastapi import APIRouter

cc_router = APIRouter()

@cc_router.get("/get")
async def get_test():
    return {"method": "cc的get方法"}

@cc_router.put("/put")
async def put_test():
    return {"method": "cc的put方法"}

@cc_router.post("/post")
async def post_test():
    return {"method": "cc的post方法"}

@cc_router.delete("/delete")
async def delete_test():
    return {"method": "cc的delete方法"}