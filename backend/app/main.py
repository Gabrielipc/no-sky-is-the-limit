from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers.atlas_router import router as atlas_router
from app.routers.dimensions_router import router as dimensions_router
from app.routers.expansion_router import router as expansion_router
from app.routers.minerals_router import router as minerals_router
from app.routers.regional_router import router as regional_router
from app.routers.regions_router import router as regions_router
from app.routers.scenarios_router import router as scenarios_router

app = FastAPI(title='Análogos planetarios · API', version='0.5.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(scenarios_router)
app.include_router(regional_router)
app.include_router(expansion_router)
app.include_router(dimensions_router)
app.include_router(minerals_router)
app.include_router(atlas_router)
app.include_router(regions_router)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if (FRONTEND_DIST / 'index.html').is_file():
    for directory in ('assets', 'analysis', 'regions', 'textures', 'cesium', 'surface'):
        static_directory = FRONTEND_DIST / directory
        if static_directory.is_dir():
            app.mount(
                f'/{directory}',
                StaticFiles(directory=static_directory),
                name=f'frontend-{directory}',
            )

    @app.get('/', include_in_schema=False)
    def frontend_index():
        return FileResponse(FRONTEND_DIST / 'index.html')

# Re-exported for backwards compatibility with prototype (commit 0274759)
from app.routers.regions_router import get_region, regions, search  # noqa: E402
from app.schemas.search import Search, Weights  # noqa: E402
