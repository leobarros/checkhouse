#!/usr/bin/env python3
"""Gerador de carga para o CheckHouse.

Simula o cenário real do home lab: 2 usuários com celular (poucas
operações, com pausas) e rajadas de concorrência para descobrir o ponto em que
o servidor deixa de responder bem.

Só usa a biblioteca padrão, para poder rodar em qualquer máquina sem instalar
nada.

Subcomandos:
    setup   cria usuários, locais, produtos e itens de lista
    real    carga realista (N usuários, com pausa de "pensar")
    stress  concorrência fixa, sem pausas, durante X segundos
"""

import argparse
import http.cookiejar
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

PRIMEIRO_NOME = [
    'Arroz', 'Feijão', 'Massa', 'Azeite', 'Sal', 'Açúcar', 'Café', 'Leite',
    'Pão', 'Ovos', 'Queijo', 'Manteiga', 'Atum', 'Cebola', 'Alho', 'Tomate',
]


class Resposta:
    __slots__ = ('estado', 'segundos', 'texto')

    def __init__(self, estado, segundos, texto):
        self.estado = estado
        self.segundos = segundos
        self.texto = texto


class Sessao:
    """Sessão HTTP com cookies (equivalente a um celular autenticado)."""

    def __init__(self, base):
        self.base = base.rstrip('/')
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies))

    def pedir(self, metodo, caminho, dados=None, json_corpo=None, cabecalhos=None):
        cabecalhos = dict(cabecalhos or {})
        corpo = None
        if json_corpo is not None:
            corpo = json.dumps(json_corpo).encode()
            cabecalhos['Content-Type'] = 'application/json'
        elif dados is not None:
            corpo = urllib.parse.urlencode(dados).encode()

        requisição = urllib.request.Request(
            self.base + caminho, data=corpo, method=metodo, headers=cabecalhos)

        inicio = time.perf_counter()
        try:
            with self.opener.open(requisição, timeout=30) as resp:
                texto = resp.read()
                estado = resp.status
        except urllib.error.HTTPError as erro:
            texto = erro.read()
            estado = erro.code
        except Exception:                       # noqa: BLE001 - rede/timeout
            texto = b''
            estado = 0
        return Resposta(estado, time.perf_counter() - inicio, texto)


# --------------------------------------------------------------------------
# Preparação de dados
# --------------------------------------------------------------------------

def preparar(url, usuarios, produtos=16, itens=10):
    info = []
    for indice in range(1, usuarios + 1):
        sessao = Sessao(url)
        nome = 'bench{0}'.format(indice)
        senha = 'senha-bench-123'

        sessao.pedir('POST', '/registrar', dados={'username': nome, 'senha': senha})
        login = sessao.pedir('POST', '/login', dados={'username': nome, 'senha': senha})
        if login.estado != 200:
            raise SystemExit('login falhou para {0}: {1}'.format(nome, login.estado))

        sessao.pedir('POST', '/adicionar_local', dados={'nome': 'Casa {0}'.format(indice)})

        pagina = sessao.pedir('GET', '/')
        # O id do local é sequencial numa banco de dados nova: 1, 2, ...
        local_id = indice

        for posicao in range(produtos):
            sessao.pedir('POST', '/adicionar_produto/{0}'.format(local_id),
                         dados={'nome': PRIMEIRO_NOME[posicao % len(PRIMEIRO_NOME)],
                                'quantidade': (posicao % 5) + 1})

        for posicao in range(itens):
            sessao.pedir('POST', '/api/locais/{0}/lista/itens'.format(local_id),
                         json_corpo={'nome': PRIMEIRO_NOME[(posicao + 3) % len(PRIMEIRO_NOME)],
                                     'quantidade': (posicao % 3) + 1},
                         cabecalhos={'X-Idempotency-Key': str(uuid.uuid4())})

        info.append({'usuario': nome, 'local_id': local_id,
                     'pagina_inicial': pagina.estado})
    return info


def _itens_da_lista(sessao, local_id):
    resposta = sessao.pedir('GET', '/api/locais/{0}/lista'.format(local_id))
    try:
        return json.loads(resposta.texto.decode()).get('itens', [])
    except Exception:                            # noqa: BLE001
        return []


# --------------------------------------------------------------------------
# Carga
# --------------------------------------------------------------------------

class Contador:
    def __init__(self):
        self.trava = threading.Lock()
        self.latencias = []
        self.por_rota = {}
        self.erros = 0
        self.total = 0

    def registrar(self, rota, resposta):
        with self.trava:
            self.total += 1
            self.latencias.append(resposta.segundos)
            if resposta.estado == 0 or resposta.estado >= 500:
                self.erros += 1
            dados = self.por_rota.setdefault(rota, {'total': 0, 'erros': 0, 'soma': 0.0})
            dados['total'] += 1
            dados['soma'] += resposta.segundos
            if resposta.estado == 0 or resposta.estado >= 500:
                dados['erros'] += 1


def _percentil(valores, p):
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    posicao = min(len(ordenados) - 1, int(round((p / 100.0) * len(ordenados) + 0.5)) - 1)
    return ordenados[max(0, posicao)]


def resumir(contador, segundos):
    lat = contador.latencias
    return {
        'total_requisicoes': contador.total,
        'erros': contador.erros,
        'segundos': round(segundos, 2),
        'requisicoes_por_segundo': round(contador.total / segundos, 1) if segundos else 0,
        'latencia_media_ms': round(statistics.fmean(lat) * 1000, 1) if lat else 0,
        'latencia_p50_ms': round(_percentil(lat, 50) * 1000, 1),
        'latencia_p95_ms': round(_percentil(lat, 95) * 1000, 1),
        'latencia_p99_ms': round(_percentil(lat, 99) * 1000, 1),
        'latencia_max_ms': round(max(lat) * 1000, 1) if lat else 0,
        'por_rota': {rota: {'total': d['total'], 'erros': d['erros'],
                            'media_ms': round(d['soma'] / d['total'] * 1000, 1)}
                     for rota, d in sorted(contador.por_rota.items())},
    }


def carga_realista(url, usuarios, segundos, pausa, contador):
    parar = threading.Event()

    def trabalhador(local_id, semente):
        sessao = Sessao(url)
        # Cada usuário já tem sessão logada no "setup"? Não: a sessão é
        # independente, por isso volta a autenticar-se (é o que acontece quando
        # o celular abre a app).
        sessao.pedir('POST', '/login', dados={'username': 'bench{0}'.format(semente),
                                              'senha': 'senha-bench-123'})
        rodada = 0
        while not parar.is_set():
            rodada += 1
            contador.registrar('ping', sessao.pedir('GET', '/api/ping'))
            contador.registrar('api_lista', sessao.pedir(
                'GET', '/api/locais/{0}/lista'.format(local_id)))
            contador.registrar('api_despensa', sessao.pedir(
                'GET', '/api/locais/{0}/despensa'.format(local_id)))
            contador.registrar('pagina_index', sessao.pedir('GET', '/'))
            contador.registrar('pagina_lista', sessao.pedir(
                'GET', '/lista/{0}'.format(local_id)))

            itens = _itens_da_lista(sessao, local_id)
            if itens:
                alvo = itens[rodada % len(itens)]
                contador.registrar('api_marcar', sessao.pedir(
                    'PATCH', '/api/itens/{0}'.format(alvo['id']),
                    json_corpo={'comprado': not alvo['comprado']},
                    cabecalhos={'X-Idempotency-Key': str(uuid.uuid4())}))

            if rodada % 4 == 0:
                contador.registrar('api_criar_item', sessao.pedir(
                    'POST', '/api/locais/{0}/lista/itens'.format(local_id),
                    json_corpo={'nome': 'Item {0}'.format(rodada), 'quantidade': 1},
                    cabecalhos={'X-Idempotency-Key': str(uuid.uuid4())}))

            time.sleep(pausa)

    fios = [threading.Thread(target=trabalhador, args=(i + 1, i + 1), daemon=True)
            for i in range(usuarios)]
    inicio = time.perf_counter()
    for fio in fios:
        fio.start()
    time.sleep(segundos)
    parar.set()
    for fio in fios:
        fio.join(timeout=30)
    return time.perf_counter() - inicio


def carga_stress(url, concorrencia, segundos, contador):
    parar = threading.Event()

    def trabalhador(indice):
        local_id = (indice % 2) + 1
        sessao = Sessao(url)
        sessao.pedir('POST', '/login', dados={'username': 'bench{0}'.format(local_id),
                                              'senha': 'senha-bench-123'})
        rodada = 0
        while not parar.is_set():
            rodada += 1
            contador.registrar('api_lista', sessao.pedir(
                'GET', '/api/locais/{0}/lista'.format(local_id)))
            if rodada % 3 == 0:
                contador.registrar('pagina_despensa', sessao.pedir(
                    'GET', '/despensa/{0}'.format(local_id)))
            else:
                contador.registrar('api_ping', sessao.pedir('GET', '/api/ping'))

    fios = [threading.Thread(target=trabalhador, args=(i,), daemon=True)
            for i in range(concorrencia)]
    inicio = time.perf_counter()
    for fio in fios:
        fio.start()
    time.sleep(segundos)
    parar.set()
    for fio in fios:
        fio.join(timeout=30)
    return time.perf_counter() - inicio


def principal():
    parser = argparse.ArgumentParser()
    parser.add_argument('modo', choices=['setup', 'real', 'stress'])
    parser.add_argument('--url', default='http://127.0.0.1:5000')
    parser.add_argument('--usuarios', type=int, default=2)
    parser.add_argument('--segundos', type=float, default=20)
    parser.add_argument('--pausa', type=float, default=1.0)
    parser.add_argument('--concorrencia', type=int, default=8)
    parser.add_argument('--saida')
    args = parser.parse_args()

    if args.modo == 'setup':
        resultado = {'modo': 'setup', 'usuarios': preparar(args.url, args.usuarios)}
    else:
        contador = Contador()
        if args.modo == 'real':
            segundos = carga_realista(args.url, args.usuarios, args.segundos,
                                      args.pausa, contador)
        else:
            segundos = carga_stress(args.url, args.concorrencia, args.segundos, contador)
        resultado = resumir(contador, segundos)
        resultado['modo'] = args.modo

    texto = json.dumps(resultado, ensure_ascii=False, indent=2)
    if args.saida:
        with open(args.saida, 'w') as arquivo:
            arquivo.write(texto)
    print(texto)
    return 0


if __name__ == '__main__':
    sys.exit(principal())
