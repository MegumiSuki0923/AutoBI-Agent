import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.ask import router as ask_router

app = FastAPI(
    title="AutoBI Agent API",
    description=(
        "## AutoBI 智能问数助手 - API 骨架与交互文档\n\n"
        "本项目是一个面向汽车产业多源数据（品牌产销、新能源渗透率、充电基础设施、动力电池等）的自然语言智能问数体原型。\n"
        "目前处于第一阶段的 **API 骨架与 Mock 仿真数据测试** 状态。\n\n"
        "### 主要功能：\n"
        "* **智能问数 (`/api/ask`)**：输入关于汽车销量、电池、充电桩的提问，输出 SQL、数据表格、分析结论和可视化图表推荐。"
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 允许跨域（CORS）配置，方便后续与前端 Streamlit 或其他前端框架联调
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(ask_router, prefix="/api", tags=["智能问数"])

@app.get("/", tags=["服务检查"])
async def root():
    return {
        "status": "online",
        "message": "Welcome to AutoBI Agent API! Please visit /docs for interactive Swagger UI."
    }

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
