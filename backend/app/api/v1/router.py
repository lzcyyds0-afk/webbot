from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.llm import router as llm_router
from app.api.v1.cases import router as cases_router
from app.api.v1.projects import router as projects_router
from app.api.v1.test_cases import router as test_cases_router
from app.api.v1.runs import router as runs_router
from app.api.v1.llm_configs import router as llm_configs_router
from app.api.v1.report import router as report_router
from app.api.v1.explain import router as explain_router
from app.api.v1.scout import router as scout_router

v1_router = APIRouter()
v1_router.include_router(health_router, tags=["health"])
v1_router.include_router(projects_router, tags=["projects"])
v1_router.include_router(report_router, tags=["report"])
v1_router.include_router(test_cases_router, tags=["test-cases"])
v1_router.include_router(explain_router, tags=["explain"])
v1_router.include_router(scout_router, tags=["scout"])
v1_router.include_router(runs_router, tags=["runs"])
v1_router.include_router(llm_router, tags=["llm"])
v1_router.include_router(llm_configs_router, tags=["llm-configs"])
v1_router.include_router(cases_router, tags=["cases"])