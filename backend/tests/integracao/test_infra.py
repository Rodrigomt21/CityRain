"""A infraestrutura de integração sobe o app contra o banco de teste migrado."""


async def test_health_db_conecta_no_banco_de_teste(client):
    r = await client.get("/health/db")
    assert r.status_code == 200
    assert r.json()["database"] == "connected"


async def test_admin_cria_device_e_recebe_chave(criar_device):
    corpo, chave = await criar_device("teste-infra")
    assert corpo["name"].startswith("teste-infra")
    assert len(chave) > 20
