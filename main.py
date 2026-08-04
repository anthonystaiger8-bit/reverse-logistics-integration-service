"""
Devolve Aki - Cérebro (Central)
API principal que os apps do entregador e do cliente vão consumir.

Para rodar:
    pip install -r requirements.txt
    python database.py        # cria o banco na primeira vez
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

Depois abra http://localhost:8000/docs para testar tudo pelo navegador.
"""
import secrets
from datetime import datetime
from typing import List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from database import db_connection, init_db

TAGS_METADATA = [
    {"name": "Entregadores", "description": "Cadastro e status dos motoboys parceiros."},
    {"name": "Clientes", "description": "Cadastro de quem solicita a coleta."},
    {"name": "Coletas", "description": "O pedido em si: criação, aceite, status e consulta."},
    {"name": "GPS", "description": "Posições em tempo real dos entregadores."},
    {"name": "Lacres", "description": "Escaneamento do QR code de segurança (coleta e entrega)."},
    {"name": "Pagamentos", "description": "Registro e confirmação de pagamentos das corridas."},
    {"name": "Sistema", "description": "Rotas gerais do serviço (status, mapa ao vivo)."},
]

app = FastAPI(title="Devolve Aki - Cérebro", openapi_tags=TAGS_METADATA)

# Serve os arquivos estáticos (mapa, etc.)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Libera o acesso pros apps do motoboy e do cliente (rodando em outros
# dispositivos/origens) conseguirem conversar com o cérebro.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATUS_VALIDOS = [
    "aguardando", "aceita", "a_caminho", "cliente_confirmou",
    "coletado", "entregue", "cancelada",
]


@app.on_event("startup")
def startup():
    init_db()


# ---------- Schemas (o formato que os apps precisam mandar) ----------

class EntregadorIn(BaseModel):
    nome: str
    endereco: str
    telefone: str
    documento: str
    cnh: str
    placa_moto: str
    conta_repasse: str


class ClienteIn(BaseModel):
    nome: str
    telefone: str
    endereco: str


class ColetaIn(BaseModel):
    cliente_id: int
    endereco_coleta: str
    complemento: Optional[str] = None  # tipo (Casa/Apto) + referência, só pra exibição
    tamanho_pacote: Optional[str] = None
    peso_aproximado: Optional[float] = None
    embalado_corretamente: Optional[bool] = None
    foto_pacote: Optional[str] = None
    valor_corrida: Optional[float] = None


class StatusIn(BaseModel):
    status: str


class GpsIn(BaseModel):
    entregador_id: int
    coleta_id: Optional[int] = None
    latitude: float
    longitude: float
    timestamp: Optional[str] = None  # hora real da captura no celular (útil se offline)


class GpsPontoIn(BaseModel):
    latitude: float
    longitude: float
    timestamp: str  # hora real da captura no celular, guardada offline até sincronizar


class GpsLoteIn(BaseModel):
    entregador_id: int
    coleta_id: Optional[int] = None
    pontos: List[GpsPontoIn]


class RotaIn(BaseModel):
    """Rota calculada no app do motoboy no momento do aceite (ainda online),
    guardada aqui para permitir navegação e acompanhamento mesmo offline depois."""
    geometria: str
    distancia_km: Optional[float] = None
    tempo_estimado_min: Optional[float] = None


class EscanearQrColetaIn(BaseModel):
    """Escâner inicial: QR exibido no celular do cliente, lido pelo motoboy."""
    qr_coleta_codigo: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class LacreEscaneioIn(BaseModel):
    numero_serie: str
    coleta_id: Optional[int] = None  # obrigatório no primeiro escaneamento
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class PagamentoIn(BaseModel):
    coleta_id: int
    valor: float
    forma_pagamento: Optional[str] = None


def _registrar_status(conn, coleta_id: int, status: str):
    conn.execute(
        "INSERT INTO historico_status (coleta_id, status) VALUES (?, ?)",
        (coleta_id, status),
    )


# Transforma um endereço em texto (rua, número, bairro, cidade) em
# coordenadas (latitude/longitude), usando o Nominatim (OpenStreetMap).
# Isso roda no cérebro, não no celular do cliente, porque aqui a gente
# consegue controlar direito o identificador da aplicação (exigido pelo
# Nominatim) e tratar erro de forma confiável, sem depender de conexão
# instável ou de configuração do aparelho de cada pessoa.
async def geocodificar_endereco(endereco: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resposta = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"format": "json", "limit": 1, "q": endereco},
                headers={
                    "Accept-Language": "pt-BR",
                    # Exigido pela política de uso do Nominatim: identifica quem
                    # está chamando (não pode ser um User-Agent genérico de lib).
                    "User-Agent": "devolve-aki-cerebro/1.0 (contato: suporte@devolveaki.app)",
                },
            )
            resposta.raise_for_status()
            dados = resposta.json()
            if dados:
                return {"lat": float(dados[0]["lat"]), "lng": float(dados[0]["lon"])}
            return None
    except Exception as e:
        print(f"Erro ao geocodificar endereço '{endereco}': {e}")
        return None


# Tenta geocodificar de várias formas antes de desistir: primeiro o endereço
# como foi digitado, depois com ", Brasil" no final (ajuda o Nominatim a não
# confundir com lugares de mesmo nome em outros países), e por fim vai
# tirando pedaços do fim do texto (separados por vírgula) até sobrar só o
# essencial - útil quando o cliente digita algo a mais que atrapalha a busca.
async def geocodificar_com_fallback(endereco: str) -> Optional[dict]:
    tentativas = [endereco]
    if "brasil" not in endereco.lower():
        tentativas.append(endereco + ", Brasil")

    partes = [p.strip() for p in endereco.split(",") if p.strip()]
    while len(partes) > 2:
        partes = partes[:-1]
        tentativas.append(", ".join(partes))

    for tentativa in tentativas:
        posicao = await geocodificar_endereco(tentativa)
        if posicao is not None:
            return posicao
    return None


# ---------- Entregadores ----------

@app.post("/entregadores", tags=["Entregadores"])
def cadastrar_entregador(dados: EntregadorIn):
    with db_connection() as conn:
        cur = conn.execute(
            """INSERT INTO entregadores
               (nome, endereco, telefone, documento, cnh, placa_moto, conta_repasse)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (dados.nome, dados.endereco, dados.telefone, dados.documento,
             dados.cnh, dados.placa_moto, dados.conta_repasse),
        )
        novo_id = cur.lastrowid
    return {"id": novo_id, "mensagem": "Entregador cadastrado com sucesso"}


@app.post("/entregadores/{entregador_id}/online", tags=["Entregadores"])
def marcar_online(entregador_id: int, online: bool = True):
    with db_connection() as conn:
        conn.execute(
            "UPDATE entregadores SET online = ? WHERE id = ?",
            (1 if online else 0, entregador_id),
        )
    return {"mensagem": "Status online atualizado"}


@app.get("/entregadores/online", tags=["Entregadores"])
def listar_entregadores_online():
    with db_connection() as conn:
        linhas = conn.execute(
            "SELECT id, nome, telefone FROM entregadores WHERE online = 1"
        ).fetchall()
        return [dict(l) for l in linhas]


# ---------- Clientes ----------

@app.post("/clientes", tags=["Clientes"])
def cadastrar_cliente(dados: ClienteIn):
    with db_connection() as conn:
        cur = conn.execute(
            "INSERT INTO clientes (nome, telefone, endereco) VALUES (?, ?, ?)",
            (dados.nome, dados.telefone, dados.endereco),
        )
        novo_id = cur.lastrowid
    return {"id": novo_id, "mensagem": "Cliente cadastrado com sucesso"}


# ---------- Coletas ----------

@app.post("/coletas", tags=["Coletas"])
async def criar_coleta(dados: ColetaIn):
    # O cérebro é quem resolve a coordenada do endereço agora - não confiamos
    # mais em latitude/longitude vindas do app do cliente. Geocodifica só o
    # endereço "limpo" (sem tipo de residência/referência, que só atrapalham
    # a busca), com fallback tentando simplificar se não achar de primeira.
    # Fica FORA do "with" de propósito: é uma chamada de rede (pode demorar),
    # e a gente só quer abrir conexão com o banco depois de já ter a posição.
    posicao = await geocodificar_com_fallback(dados.endereco_coleta)
    if posicao is None:
        raise HTTPException(
            422,
            "Não conseguimos localizar esse endereço no mapa. "
            "Peça pro cliente completar com bairro e cidade.",
        )

    endereco_completo = dados.endereco_coleta
    if dados.complemento:
        endereco_completo += " " + dados.complemento

    with db_connection() as conn:
        cur = conn.execute(
            """INSERT INTO coletas
               (cliente_id, endereco_coleta, latitude, longitude, tamanho_pacote,
                peso_aproximado, embalado_corretamente, foto_pacote, valor_corrida, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'aguardando')""",
            (dados.cliente_id, endereco_completo, posicao["lat"], posicao["lng"],
             dados.tamanho_pacote, dados.peso_aproximado,
             int(dados.embalado_corretamente) if dados.embalado_corretamente is not None else None,
             dados.foto_pacote, dados.valor_corrida),
        )
        coleta_id = cur.lastrowid

        # QR "escâner inicial": gerado agora, único por coleta. Fica salvo no
        # banco e o app do cliente exibe ele na tela pro motoboy escanear.
        qr_codigo = f"DVK-{coleta_id}-{secrets.token_hex(4)}"
        conn.execute(
            "UPDATE coletas SET qr_coleta_codigo = ? WHERE id = ?", (qr_codigo, coleta_id)
        )

        _registrar_status(conn, coleta_id, "aguardando")

    return {
        "id": coleta_id,
        "qr_coleta_codigo": qr_codigo,
        "mensagem": "Coleta criada e disponível na fila",
    }


@app.get("/entregadores/{entregador_id}/coletas", tags=["Coletas"])
def listar_coletas_do_entregador(entregador_id: int):
    with db_connection() as conn:
        linhas = conn.execute(
            """SELECT * FROM coletas WHERE entregador_id = ?
               ORDER BY criado_em DESC""",
            (entregador_id,),
        ).fetchall()

    todas = [dict(l) for l in linhas]
    em_andamento = [c for c in todas if c["status"] in ("aceita", "a_caminho", "cliente_confirmou", "coletado")]
    concluidas = [c for c in todas if c["status"] in ("entregue", "cancelada")]
    return {"em_andamento": em_andamento, "concluidas": concluidas}


@app.get("/coletas/disponiveis", tags=["Coletas"])
def listar_coletas_disponiveis():
    with db_connection() as conn:
        linhas = conn.execute(
            "SELECT * FROM coletas WHERE status = 'aguardando' ORDER BY criado_em"
        ).fetchall()
        return [dict(l) for l in linhas]


@app.post("/coletas/{coleta_id}/aceitar", tags=["Coletas"])
def aceitar_coleta(coleta_id: int, entregador_id: int):
    with db_connection() as conn:
        coleta = conn.execute("SELECT * FROM coletas WHERE id = ?", (coleta_id,)).fetchone()
        if coleta is None:
            raise HTTPException(404, "Coleta não encontrada")
        if coleta["status"] != "aguardando":
            raise HTTPException(409, "Essa coleta já foi aceita por outro entregador")

        conn.execute(
            "UPDATE coletas SET entregador_id = ?, status = 'aceita' WHERE id = ?",
            (entregador_id, coleta_id),
        )
        _registrar_status(conn, coleta_id, "aceita")
    return {"mensagem": "Coleta aceita com sucesso"}


@app.post("/coletas/{coleta_id}/escanear-qr-coleta", tags=["Coletas"])
def escanear_qr_coleta(coleta_id: int, dados: EscanearQrColetaIn):
    """Escâner inicial: motoboy lê o QR mostrado na tela do celular do cliente,
    confirmando que a coleta certa foi feita pelo motoboy certo, no local certo."""
    with db_connection() as conn:
        coleta = conn.execute("SELECT * FROM coletas WHERE id = ?", (coleta_id,)).fetchone()
        if coleta is None:
            raise HTTPException(404, "Coleta não encontrada")
        if coleta["qr_coleta_codigo"] != dados.qr_coleta_codigo:
            raise HTTPException(400, "QR code não confere com essa coleta")
        if coleta["qr_coleta_escaneado_em"] is not None:
            raise HTTPException(409, "Esse QR já foi escaneado anteriormente")

        agora = datetime.now().isoformat()
        conn.execute(
            """UPDATE coletas
               SET qr_coleta_escaneado_em = ?, qr_coleta_escaneado_lat = ?, qr_coleta_escaneado_lng = ?
               WHERE id = ?""",
            (agora, dados.latitude, dados.longitude, coleta_id),
        )
    return {"mensagem": "QR de coleta confirmado", "escaneado_em": agora}


@app.post("/coletas/{coleta_id}/rota", tags=["Coletas"])
def salvar_rota(coleta_id: int, dados: RotaIn):
    """Guarda a rota calculada no momento do aceite (enquanto online), pra
    o app conseguir guiar e o cliente acompanhar mesmo sem internet depois."""
    with db_connection() as conn:
        coleta = conn.execute("SELECT id FROM coletas WHERE id = ?", (coleta_id,)).fetchone()
        if coleta is None:
            raise HTTPException(404, "Coleta não encontrada")

        conn.execute(
            """UPDATE coletas
               SET rota_geometria = ?, rota_distancia_km = ?, rota_tempo_estimado_min = ?,
                   rota_calculada_em = ?
               WHERE id = ?""",
            (dados.geometria, dados.distancia_km, dados.tempo_estimado_min,
             datetime.now().isoformat(), coleta_id),
        )
    return {"mensagem": "Rota salva com sucesso"}


@app.get("/coletas/{coleta_id}/rota", tags=["Coletas"])
def consultar_rota(coleta_id: int):
    """Usado pelo app do cliente e pelo app do motoboy pra buscar a rota
    já cacheada e continuar guiando/acompanhando mesmo offline."""
    with db_connection() as conn:
        coleta = conn.execute(
            """SELECT rota_geometria, rota_distancia_km, rota_tempo_estimado_min, rota_calculada_em
               FROM coletas WHERE id = ?""",
            (coleta_id,),
        ).fetchone()
        if coleta is None:
            raise HTTPException(404, "Coleta não encontrada")
        return dict(coleta)


@app.post("/coletas/{coleta_id}/status", tags=["Coletas"])
def atualizar_status(coleta_id: int, dados: StatusIn):
    if dados.status not in STATUS_VALIDOS:
        raise HTTPException(400, f"Status inválido. Use um de: {STATUS_VALIDOS}")

    with db_connection() as conn:
        coleta = conn.execute("SELECT id FROM coletas WHERE id = ?", (coleta_id,)).fetchone()
        if coleta is None:
            raise HTTPException(404, "Coleta não encontrada")

        conn.execute("UPDATE coletas SET status = ? WHERE id = ?", (dados.status, coleta_id))
        _registrar_status(conn, coleta_id, dados.status)
    return {"mensagem": f"Status atualizado para '{dados.status}'"}


@app.get("/coletas/{coleta_id}", tags=["Coletas"])
def consultar_coleta(coleta_id: int):
    with db_connection() as conn:
        coleta = conn.execute("SELECT * FROM coletas WHERE id = ?", (coleta_id,)).fetchone()
        if coleta is None:
            raise HTTPException(404, "Coleta não encontrada")

        ultima_posicao = conn.execute(
            """SELECT latitude, longitude, timestamp FROM posicoes_gps
               WHERE coleta_id = ? ORDER BY timestamp DESC LIMIT 1""",
            (coleta_id,),
        ).fetchone()

        historico = conn.execute(
            "SELECT status, timestamp FROM historico_status WHERE coleta_id = ? ORDER BY timestamp",
            (coleta_id,),
        ).fetchall()

        resultado = dict(coleta)
        resultado["posicao_atual"] = dict(ultima_posicao) if ultima_posicao else None
        resultado["historico"] = [dict(h) for h in historico]
        return resultado


# ---------- GPS ----------

@app.post("/gps", tags=["GPS"])
def registrar_posicao(dados: GpsIn):
    with db_connection() as conn:
        ts = dados.timestamp or datetime.now().isoformat()
        conn.execute(
            """INSERT INTO posicoes_gps (entregador_id, coleta_id, latitude, longitude, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (dados.entregador_id, dados.coleta_id, dados.latitude, dados.longitude, ts),
        )
    return {"mensagem": "Posição registrada"}


@app.post("/gps/lote", tags=["GPS"])
def registrar_posicoes_lote(dados: GpsLoteIn):
    """Sincronização offline: o app do motoboy guarda os pontos localmente
    enquanto está sem internet (cada um com a hora real da captura) e manda
    tudo de uma vez aqui assim que a conexão voltar."""
    if not dados.pontos:
        raise HTTPException(400, "Lista de pontos vazia")

    with db_connection() as conn:
        for ponto in dados.pontos:
            conn.execute(
                """INSERT INTO posicoes_gps (entregador_id, coleta_id, latitude, longitude, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (dados.entregador_id, dados.coleta_id, ponto.latitude, ponto.longitude, ponto.timestamp),
            )
    return {"mensagem": f"{len(dados.pontos)} posições sincronizadas com sucesso"}


@app.get("/gps/motoboys-ativos", tags=["GPS"])
def mapa_motoboys_ativos():
    """Última posição conhecida de cada entregador online - alimenta o mapa do cérebro."""
    with db_connection() as conn:
        linhas = conn.execute(
            """SELECT p.entregador_id, e.nome, p.latitude, p.longitude, p.coleta_id,
                      MAX(p.timestamp) as ultima_atualizacao
               FROM posicoes_gps p
               JOIN entregadores e ON e.id = p.entregador_id
               WHERE e.online = 1
               GROUP BY p.entregador_id"""
        ).fetchall()
        return [dict(l) for l in linhas]


# ---------- Lacres ----------

@app.post("/lacres/escanear", tags=["Lacres"])
def escanear_lacre(dados: LacreEscaneioIn):
    with db_connection() as conn:
        lacre = conn.execute(
            "SELECT * FROM lacres WHERE numero_serie = ?", (dados.numero_serie,)
        ).fetchone()

        agora = datetime.now().isoformat()

        if lacre is None:
            # Primeiro escaneamento: associa o lacre à coleta (coleta)
            if dados.coleta_id is None:
                raise HTTPException(400, "coleta_id é obrigatório no primeiro escaneamento do lacre")
            conn.execute(
                """INSERT INTO lacres
                   (numero_serie, coleta_id, escaneado_coleta_em, escaneado_coleta_lat, escaneado_coleta_lng)
                   VALUES (?, ?, ?, ?, ?)""",
                (dados.numero_serie, dados.coleta_id, agora, dados.latitude, dados.longitude),
            )
            return {"mensagem": "Lacre registrado na coleta", "etapa": "coleta"}

        if lacre["escaneado_entrega_em"] is None:
            # Segundo escaneamento: rompimento na entrega
            conn.execute(
                """UPDATE lacres
                   SET escaneado_entrega_em = ?, escaneado_entrega_lat = ?, escaneado_entrega_lng = ?
                   WHERE numero_serie = ?""",
                (agora, dados.latitude, dados.longitude, dados.numero_serie),
            )
            return {"mensagem": "Lacre rompido na entrega", "etapa": "entrega"}

        raise HTTPException(409, "Esse lacre já foi totalmente utilizado (coleta + entrega)")


# ---------- Pagamentos ----------

@app.post("/pagamentos", tags=["Pagamentos"])
def registrar_pagamento(dados: PagamentoIn):
    with db_connection() as conn:
        cur = conn.execute(
            """INSERT INTO pagamentos (coleta_id, valor, forma_pagamento, status)
               VALUES (?, ?, ?, 'pendente')""",
            (dados.coleta_id, dados.valor, dados.forma_pagamento),
        )
        novo_id = cur.lastrowid
    return {"id": novo_id, "mensagem": "Pagamento registrado como pendente"}


@app.post("/pagamentos/{pagamento_id}/confirmar", tags=["Pagamentos"])
def confirmar_pagamento(pagamento_id: int):
    with db_connection() as conn:
        conn.execute(
            "UPDATE pagamentos SET status = 'pago' WHERE id = ?", (pagamento_id,)
        )
    return {"mensagem": "Pagamento confirmado"}


@app.get("/", tags=["Sistema"])
def raiz():
    return {"servico": "Devolve Aki - Cérebro", "status": "rodando"}


@app.get("/mapa", tags=["Sistema"])
def mapa_ao_vivo():
    """Abre a janela do mapa em tempo real com as coletas e motoboys online."""
    return FileResponse("static/mapa.html")
