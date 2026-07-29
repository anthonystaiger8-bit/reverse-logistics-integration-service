# Devolve Aki
### Serviço de coleta domiciliar para devolução em pontos do Mercado Livre

## O que é

O Devolve Aki resolve um problema específico: quando você precisa devolver um
produto comprado no Mercado Livre, normalmente precisa se deslocar até um
ponto de coleta pra despachar o pacote. O Devolve Aki inverte isso — um
entregador parceiro **vai até a casa do cliente**, recolhe o pacote e leva
até o ponto de coleta do Mercado Livre em nome dele.

Funciona como o oposto de um serviço de entrega: em vez de levar até o
cliente, o Devolve Aki retira do cliente.

## Como funciona hoje (MVP)

1. Cliente cadastra um pedido de coleta informando endereço e detalhes do
   pacote (tamanho, peso aproximado, se já está embalado corretamente).
2. O pedido fica disponível na plataforma como "em aberto".
3. Entregadores cadastrados recebem o alerta no app; o primeiro que aceitar
   fica com a coleta.
4. O cliente acompanha em tempo real, pelo GPS do entregador, desde a saída
   dele até a chegada na casa do cliente, e depois da coleta até a entrega
   no ponto do Mercado Livre.
5. A prova de que o pacote foi de fato coletado e entregue é feita por um
   lacre com QR code, escaneado no momento da coleta (na frente do cliente)
   e novamente ao ser rompido na entrega — registrando local e hora de cada
   escaneamento.
6. Pagamento e repasse ao entregador são registrados na plataforma.

## Arquitetura

O sistema é dividido em três partes:

- **Backend** (este repositório) — o núcleo do sistema: cadastro de
  entregadores e clientes, gestão de coletas, histórico de status,
  posições de GPS, controle de lacres e pagamentos. Construído em
  Python com FastAPI, banco SQLite.
- **App do entregador** — aplicativo Android (Cordova) onde o motoboy se
  cadastra, recebe alertas de coletas disponíveis, aceita corridas e tem
  seu GPS rastreado durante o trajeto.
- **App/página do cliente** — ainda não construído; vai permitir que o
  cliente solicite a coleta e acompanhe o status em tempo real.

Também existe um **mapa ao vivo** (`/mapa`), acessível pelo navegador, que
mostra em tempo real as coletas em aberto e os entregadores online.

## Status atual

- [x] Backend com cadastro de entregadores e clientes
- [x] Fluxo de coleta: criação, listagem de disponíveis, aceite (regra do
      primeiro a aceitar), atualização de status com histórico
- [x] Registro de posições de GPS e endpoint pro mapa ao vivo
- [x] Escaneamento de lacre em duas etapas (coleta e entrega)
- [x] Registro de pagamentos
- [x] App do entregador (Android/Cordova) com tela de cadastro
- [x] Mapa ao vivo com Leaflet
- [ ] Deploy em nuvem (em andamento)
- [ ] App/página do cliente
- [ ] Definição final do modelo de cobrança (por km, taxa fixa, ou misto)

## Rodando localmente

```
pip install -r requirements.txt
python database.py        # cria o banco na primeira vez
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Depois acesse `http://localhost:8000/docs` para testar os endpoints, ou
`http://localhost:8000/mapa` para ver o mapa ao vivo.

## Visão de futuro (pós-MVP)

Ideias para depois que o fluxo básico estiver validado e rodando:

- Ampliar para outros marketplaces além do Mercado Livre
- Ponto de coleta próprio, gerando receita adicional
- Modelo de assinatura mensal como alternativa à taxa por coleta
- Expansão regional por clusters operacionais
