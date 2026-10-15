#!/usr/bin/env python3
"""Compara configurações de servidor para o CheckHouse.

Para cada configuração:
  1. inicia um container com 2 CPUs (equivalente ao home lab dual-core);
  2. mede memória/CPU em repouso (cgroups v2, sem entrar no container);
  3. cria 2 usuários com dados realistas;
  4. mede sob carga realista (2 usuários) e sob rajada de concorrência;
  5. salva tudo em bench/out/resultados.json.

Uso:
    python3 bench/executar.py                 # todas as configurações
    python3 bench/executar.py flask_debug gunicorn_gthread_1w_4t
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(RAIZ, 'bench')
SAIDA = os.path.join(BENCH, 'out')
IMAGEM = 'checkhouse-bench:latest'
PORTA = 5055
URL = 'http://127.0.0.1:{0}'.format(PORTA)
CPU_LIMITE = '2'
MEMORIA_TESTE = '1g'
SEGUNDOS_REAL = 25
SEGUNDOS_STRESS = 15
CONCORRENCIA_STRESS = 8

def gunicorn(*extra, com_registro=True):
    """gunicorn com as mesmas opções base em todas as configurações.

    com_registro=True mantém o registro de acessos ligado, para comparar em pé de
    igualdade com o servidor de desenvolvimento do Flask (que regista sempre).
    """
    cmd = ['gunicorn', '-b', '0.0.0.0:5000', '--timeout', '60']
    if com_registro:
        cmd += ['--access-logfile', '-']
    cmd += ['--error-logfile', '-']
    return cmd + list(extra) + ['app:app']

CONFIGURACOES = [
    {
        'nome': 'flask_debug',
        'descricao': 'Werkzeug dev server, debug=True (o que está publicado hoje)',
        'cmd': ['python', 'app.py'],
        'env': {},
    },
    {
        'nome': 'flask_sem_debug',
        'descricao': 'Werkzeug dev server, sem debug (1 processo)',
        'cmd': ['python', '-m', 'flask', '--app', 'app', 'run',
                '--host=0.0.0.0', '--port=5000'],
        'env': {},
    },
    {
        'nome': 'gunicorn_sync_1w',
        'descricao': 'gunicorn 1 worker síncrono',
        'cmd': gunicorn('-w', '1', '-k', 'sync'),
        'env': {},
    },
    {
        'nome': 'gunicorn_gthread_1w_4t',
        'descricao': 'gunicorn 1 worker gthread, 4 threads',
        'cmd': gunicorn('-w', '1', '-k', 'gthread', '--threads', '4'),
        'env': {},
    },
    {
        'nome': 'gunicorn_gthread_1w_8t',
        'descricao': 'gunicorn 1 worker gthread, 8 threads',
        'cmd': gunicorn('-w', '1', '-k', 'gthread', '--threads', '8'),
        'env': {},
    },
    {
        'nome': 'gunicorn_sync_2w',
        'descricao': 'gunicorn 2 workers síncronos (1 por núcleo)',
        'cmd': gunicorn('-w', '2', '-k', 'sync', '--preload'),
        'env': {},
    },
    {
        'nome': 'waitress_1w_4t',
        'descricao': 'waitress (servidor WSGI puro Python), 4 threads',
        'cmd': ['waitress-serve', '--host=0.0.0.0', '--port=5000',
                '--threads=4', 'app:app'],
        'env': {},
    },
    {
        'nome': 'gthread_arena2',
        'descricao': 'gunicorn 1 worker gthread 4 threads + MALLOC_ARENA_MAX=2',
        'cmd': gunicorn('-w', '1', '-k', 'gthread', '--threads', '4'),
        'env': {'MALLOC_ARENA_MAX': '2'},
    },
    # --- Fase 2: sem registro de acessos (para comparar servidores em igualdade)
    {
        'nome': 'gthread_4t_semlog',
        'descricao': 'gunicorn 1 worker gthread 4 threads, sem registro de acessos',
        'cmd': gunicorn('-w', '1', '-k', 'gthread', '--threads', '4', com_registro=False),
        'env': {},
    },
    {
        'nome': 'gthread_2t_semlog',
        'descricao': 'gunicorn 1 worker gthread 2 threads, sem registro de acessos',
        'cmd': gunicorn('-w', '1', '-k', 'gthread', '--threads', '2', com_registro=False),
        'env': {},
    },
    {
        'nome': 'waitress_2t',
        'descricao': 'waitress com 2 threads',
        'cmd': ['waitress-serve', '--host=0.0.0.0', '--port=5000',
                '--threads=2', 'app:app'],
        'env': {},
    },
    {
        'nome': 'waitress_4t_arena2',
        'descricao': 'waitress 4 threads + MALLOC_ARENA_MAX=2',
        'cmd': ['waitress-serve', '--host=0.0.0.0', '--port=5000',
                '--threads=4', 'app:app'],
        'env': {'MALLOC_ARENA_MAX': '2'},
    },
]


def rodar(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def esperar_inicio(nome, limite=60):
    inicio = time.time()
    while time.time() - inicio < limite:
        estado = rodar(['docker', 'inspect', '-f', '{{.State.Running}}', nome])
        if estado.stdout.strip() != 'true':
            return False
        try:
            with urllib.request.urlopen(URL + '/login', timeout=3) as resposta:
                if resposta.status == 200:
                    return True
        except urllib.error.HTTPError:
            return True                     # responde, mesmo que não seja 200
        except Exception:                   # noqa: BLE001
            pass
        time.sleep(1)
    return False


def amostrar(nome, segundos):
    resultado = rodar(['python3', os.path.join(BENCH, 'sampler.py'), nome, str(segundos)])
    if resultado.returncode != 0:
        return {'erro': resultado.stderr.strip()}
    return json.loads(resultado.stdout)


def amostrar_durante(nome, segundos, acao):
    """Amostra os recursos do container em paralelo com a carga.

    Sem isto, o CPU medido seria o de repouso depois da carga, que não diz nada
    sobre o custo de servir requisições.
    """
    processo = subprocess.Popen(
        ['python3', os.path.join(BENCH, 'sampler.py'), nome, str(segundos)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        resultado_acao = acao()
    finally:
        saida, erro = processo.communicate(timeout=180)
    recursos = json.loads(saida) if saida.strip() else {'erro': erro.strip()[-500:]}
    return recursos, resultado_acao


def carga(*argumentos, saida=None):
    cmd = ['python3', os.path.join(BENCH, 'carga.py')] + list(argumentos)
    if saida:
        cmd += ['--saida', saida]
    resultado = rodar(cmd)
    if resultado.returncode != 0:
        raise RuntimeError('carga falhou: {0}'.format(resultado.stderr[-2000:]))
    return json.loads(resultado.stdout)


def medir(configuracao):
    nome = 'bench_' + configuracao['nome']
    dados = os.path.join(SAIDA, 'dados_' + configuracao['nome'])
    shutil.rmtree(dados, ignore_errors=True)
    os.makedirs(dados, exist_ok=True)

    rodar(['docker', 'rm', '-f', nome])

    argumentos = [
        'docker', 'run', '-d', '--name', nome,
        '--cpus', CPU_LIMITE, '--memory', MEMORIA_TESTE, '--memory-swap', MEMORIA_TESTE,
        '--publish', '{0}:5000'.format(PORTA),
        '--volume', '{0}:/app/dados'.format(dados),
    ]
    for chave, valor in configuracao['env'].items():
        argumentos += ['-e', '{0}={1}'.format(chave, valor)]
    argumentos += [IMAGEM] + configuracao['cmd']

    instante_inicio = time.time()
    criado = rodar(argumentos)
    if criado.returncode != 0:
        return {'nome': configuracao['nome'], 'erro': criado.stderr.strip()}

    registro = {'nome': configuracao['nome'], 'descricao': configuracao['descricao'],
               'comando': ' '.join(configuracao['cmd']), 'env': configuracao['env'],
               'limite_cpu': CPU_LIMITE, 'limite_memoria_teste': MEMORIA_TESTE}

    try:
        if not esperar_inicio(nome):
            registro['erro'] = 'não iniciou'
            registro['logs'] = rodar(['docker', 'logs', nome]).stdout[-2000:]
            return registro

        registro['inicialização_s'] = round(time.time() - instante_inicio, 1)
        time.sleep(5)
        registro['repouso'] = amostrar(nome, 8)

        preparar = carga('setup', '--url', URL, '--usuarios', '2')
        registro['setup'] = {'usuarios': len(preparar['usuarios'])}

        registro['realista_recursos'], registro['realista'] = amostrar_durante(
            nome, SEGUNDOS_REAL + 2,
            lambda: carga('real', '--url', URL, '--usuarios', '2',
                          '--segundos', str(SEGUNDOS_REAL), '--pausa', '1.0'))

        registro['stress_recursos'], registro['stress'] = amostrar_durante(
            nome, SEGUNDOS_STRESS + 2,
            lambda: carga('stress', '--url', URL, '--concorrencia', str(CONCORRENCIA_STRESS),
                          '--segundos', str(SEGUNDOS_STRESS)))

        registro['total'] = amostrar(nome, 3)

        registro['logs'] = rodar(['docker', 'logs', '--tail', '15', nome]).stdout[-1500:]
    except Exception as erro:               # noqa: BLE001
        registro['erro'] = str(erro)
    finally:
        rodar(['docker', 'stop', '-t', '5', nome])
        rodar(['docker', 'rm', '-f', nome])

    return registro


def megabytes(valor):
    return round(valor / (1024.0 * 1024.0), 1) if valor else 0.0


def imprimir_tabela(resultados):
    cabecalho = ('config', 'anon repouso', 'anon real', 'anon pico', 'cache',
                 'CPU real', 'CPU stress', 'p95 real', 'p95 stress', 'req/s', 'erros')
    print('\n{0:<22}{1:>13}{2:>11}{3:>11}{4:>9}{5:>9}{6:>11}{7:>10}{8:>12}{9:>8}{10:>7}'
          .format(*cabecalho))
    for registro in resultados:
        if 'repouso' not in registro or 'erro' in registro:
            print('{0:<22}  ERRO: {1}'.format(registro['nome'], registro.get('erro', '?')))
            continue
        realista = registro['realista']
        stress = registro['stress']
        recursos = registro.get('realista_recursos', {})
        recursos_stress = registro.get('stress_recursos', {})
        pico_anon = max(recursos.get('anon_pico_bytes', 0),
                        recursos_stress.get('anon_pico_bytes', 0))
        cache = registro.get('total', {}).get('cache_bytes', 0)
        print('{0:<22}{1:>11.1f}MB{2:>9.1f}MB{3:>9.1f}MB{4:>7.1f}MB{5:>8.1f}%{6:>10.1f}%'
              '{7:>9.1f}ms{8:>11.1f}ms{9:>7.1f}{10:>7}'.format(
                  registro['nome'],
                  megabytes(registro['repouso'].get('anon_atual_bytes', 0)),
                  megabytes(recursos.get('anon_atual_bytes', 0)),
                  megabytes(pico_anon),
                  megabytes(cache),
                  recursos.get('cpu_percent', 0),
                  recursos_stress.get('cpu_percent', 0),
                  realista['latencia_p95_ms'],
                  stress['latencia_p95_ms'],
                  realista['requisicoes_por_segundo'],
                  realista['erros'] + stress['erros']))
    print('anon = memória do processo (o que conta para o limite); '
          'cache = páginas de arquivo, devolvidas ao sistema quando falta RAM')


def principal():
    os.makedirs(SAIDA, exist_ok=True)
    escolhidas = sys.argv[1:]
    configuracao = [c for c in CONFIGURACOES if not escolhidas or c['nome'] in escolhidas]

    resultados = []
    for indice, item in enumerate(configuracao, 1):
        print('[{0}/{1}] {2} ...'.format(indice, len(configuracao), item['nome']),
              flush=True)
        registro = medir(item)
        resultados.append(registro)
        if 'repouso' in registro:
            print('    repouso={0}MB carga={1}MB CPU={2}% p95_real={3}ms'.format(
                megabytes(registro['repouso']['memoria_atual_bytes']),
                megabytes(registro.get('realista_recursos', {}).get('memoria_atual_bytes', 0)),
                registro.get('realista_recursos', {}).get('cpu_percent', 0),
                registro.get('realista', {}).get('latencia_p95_ms', 0)), flush=True)
        else:
            print('    ERRO: {0}'.format(registro.get('erro')), flush=True)

        with open(os.path.join(SAIDA, 'resultados.json'), 'w') as arquivo:
            json.dump(resultados, arquivo, ensure_ascii=False, indent=2)

    imprimir_tabela(resultados)
    return 0


if __name__ == '__main__':
    sys.exit(principal())
