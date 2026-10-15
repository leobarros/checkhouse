#!/usr/bin/env python3
"""Amostra memória e CPU reais de um container Docker via cgroups v2.

Lê os arquivos do cgroup diretamente do hospedeiro (nunca entra no container),
por isso não interfere com a medição.

Uso:
    python3 sampler.py <nome-do-container> <segundos> [intervalo]
Imprime JSON com:
    memoria_atual_bytes      -> última leitura de memory.current
    memoria_pico_bytes       -> máximo observado (ou memory.peak, se existir)
    memoria_min_bytes
    cpu_segundos             -> delta de usage_usec convertido a segundos
    cpu_percent              -> uso médio de CPU durante a janela
"""

import json
import os
import subprocess
import sys
import time

BASE_CGROUP = '/sys/fs/cgroup'


def caminho_cgroup(nome):
    """Descobre a pasta do cgroup do container sem depender de /proc.

    O /proc de outros processos pode não estar visível (namespaces), por isso o
    caminho é derivado do próprio id do container, com uma procura limitada em
    profundidade como alternativa.
    """
    identificador = subprocess.check_output(
        ['docker', 'inspect', '-f', '{{.Id}}', nome], text=True).strip()

    for candidato in ('{0}/system.slice/docker-{1}.scope'.format(BASE_CGROUP, identificador),
                      '{0}/docker/{1}'.format(BASE_CGROUP, identificador),
                      '{0}/{1}'.format(BASE_CGROUP, identificador)):
        if os.path.exists(os.path.join(candidato, 'memory.current')):
            return candidato

    profundidade_base = BASE_CGROUP.count(os.sep)
    for raiz, pastas, _ in os.walk(BASE_CGROUP):
        if raiz.count(os.sep) - profundidade_base > 3:
            pastas[:] = []
            continue
        for pasta in pastas:
            if identificador in pasta:
                return os.path.join(raiz, pasta)

    raise SystemExit('cgroup do container {0} não encontrado'.format(nome))


def ler_numero(caminho, padrao=0):
    try:
        with open(caminho) as arquivo:
            return int(arquivo.read().strip())
    except (OSError, ValueError):
        return padrao


def ler_cpu_usec(caminho):
    try:
        with open(caminho) as arquivo:
            for linha in arquivo:
                if linha.startswith('usage_usec'):
                    return int(linha.split()[1])
    except OSError:
        pass
    return 0


def ler_estatisticas(caminho):
    """Devolve o dicionário de memory.stat (anon, file, kernel, slab...).

    `anon` é a memória realmente ocupada pelo processo (a que interessa para
    dimensionar um limite). `file` é cache de páginas, que o kernel devolve
    sozinho quando falta memória — não conta como consumo real do serviço.
    """
    valores = {}
    try:
        with open(caminho) as arquivo:
            for linha in arquivo:
                partes = linha.split()
                if len(partes) == 2:
                    try:
                        valores[partes[0]] = int(partes[1])
                    except ValueError:
                        pass
    except OSError:
        pass
    return valores


def main():
    nome = sys.argv[1]
    segundos = float(sys.argv[2])
    intervalo = float(sys.argv[3]) if len(sys.argv) > 3 else 0.25

    cgroup = caminho_cgroup(nome)
    memoria_arquivo = cgroup + '/memory.current'
    pico_arquivo = cgroup + '/memory.peak'
    cpu_arquivo = cgroup + '/cpu.stat'
    stat_arquivo = cgroup + '/memory.stat'

    cpu_inicio = ler_cpu_usec(cpu_arquivo)
    t_inicio = time.perf_counter()

    leituras = []
    anon_leituras = []
    pico = 0
    fim = t_inicio + segundos
    while True:
        agora = time.perf_counter()
        if agora >= fim:
            break
        atual = ler_numero(memoria_arquivo)
        leituras.append(atual)
        anon_leituras.append(ler_estatisticas(stat_arquivo).get('anon', 0))
        pico = max(pico, atual)
        time.sleep(intervalo)

    cpu_fim = ler_cpu_usec(cpu_arquivo)
    t_fim = time.perf_counter()
    pico_cgroup = ler_numero(pico_arquivo)

    duracao = t_fim - t_inicio
    cpu_segundos = (cpu_fim - cpu_inicio) / 1_000_000.0
    estatisticas = ler_estatisticas(stat_arquivo)
    resultado = {
        'memoria_atual_bytes': leituras[-1] if leituras else 0,
        'memoria_min_bytes': min(leituras) if leituras else 0,
        'memoria_pico_bytes': max(pico, pico_cgroup),
        'memoria_media_bytes': int(sum(leituras) / len(leituras)) if leituras else 0,
        'anon_atual_bytes': anon_leituras[-1] if anon_leituras else 0,
        'anon_pico_bytes': max(anon_leituras) if anon_leituras else 0,
        'anon_media_bytes': int(sum(anon_leituras) / len(anon_leituras)) if anon_leituras else 0,
        'cache_bytes': estatisticas.get('file', 0),
        'kernel_bytes': estatisticas.get('kernel', 0) + estatisticas.get('slab', 0),
        'cpu_segundos': round(cpu_segundos, 3),
        'cpu_percent': round(100.0 * cpu_segundos / duracao, 1) if duracao else 0.0,
        'duracao_s': round(duracao, 2),
        'amostras': len(leituras),
    }
    print(json.dumps(resultado))


if __name__ == '__main__':
    main()
