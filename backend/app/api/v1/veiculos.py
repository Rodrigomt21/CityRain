from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.veiculo import VeiculoResumo
from app.services.veiculo_service import VeiculoService

router = APIRouter()


@router.get("/", response_model=list[VeiculoResumo])
async def listar_veiculos(
    excluir_demo: bool = Query(default=False, description="Ignora capturas de demonstração na última captura"),
    db: AsyncSession = Depends(get_db),
):
    """Veículos ativos com a última captura classificada e a posição dela (público, sem placa e sem imagem)."""
    return await VeiculoService(db).listar(excluir_demo)
