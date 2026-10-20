/* ==========================================================================
   CheckHouse — fila offline ("outbox")
   --------------------------------------------------------------------------
   Problema: no supermercado a rede é má. Cada toque fazia POST + redirect +
   download da página inteira, então a interface ficava à espera do servidor.

   Solução: a interface atualiza na hora (otimista) e a operação entra numa
   fila guardada no telemóvel. A fila é enviada quando há rede — agora, ao
   voltar a rede, ao trazer a app para a frente ou quando o utilizador pedir.

   Garantias:
   - Cada operação tem um uid; o servidor guarda a resposta desse uid, por isso
     reenviar nunca duplica item nem soma quantidade duas vezes.
   - Operações repetidas sobre o mesmo recurso são juntadas (manda o último
     estado), evitando uma fila de pedidos quando se toca várias vezes no "+".
   - Criar e remover o mesmo item antes de sincronizar cancela as duas coisas.
   - Se a sessão expirar (401), nada é perdido: a fila fica parada até novo login.
   ========================================================================== */
(function (global) {
  'use strict';

  var CHAVE_FILA = 'ch:fila:v1';
  var CHAVE_IDS = 'ch:ids:v1';
  var ESPERAS = [2000, 5000, 12000, 30000, 60000, 120000];
  var INTERVALO_VIGIA = 15000;

  var armazem = global.localStorage || null;
  var fila = [];
  var idsResolvidos = {};
  var desfazedores = {};      // uid -> função a executar se o servidor recusar (4xx)
  var processando = false;
  var temporizador = null;
  var vigia = null;
  var tentativasSeguidas = 0;
  var sessaoExpirada = false;
  var ultimoErro = '';
  var ultimaSincronizacao = null;
  var online = global.navigator ? global.navigator.onLine !== false : true;

  /* ------------------------------------------------------------- persistência */

  function lerJson(chave, padrao) {
    if (!armazem) return padrao;
    try {
      var bruto = armazem.getItem(chave);
      if (!bruto) return padrao;
      var valor = JSON.parse(bruto);
      return valor === null || valor === undefined ? padrao : valor;
    } catch (e) {
      return padrao;
    }
  }

  function gravarJson(chave, valor) {
    if (!armazem) return;
    try {
      armazem.setItem(chave, JSON.stringify(valor));
    } catch (e) {
      /* quota cheia ou modo privado: a fila continua em memória */
    }
  }

  function carregar() {
    var guardado = lerJson(CHAVE_FILA, []);
    fila = Array.isArray(guardado) ? guardado : [];
    var ids = lerJson(CHAVE_IDS, {});
    idsResolvidos = ids && typeof ids === 'object' ? ids : {};
  }

  function gravar() {
    gravarJson(CHAVE_FILA, fila);
    gravarJson(CHAVE_IDS, idsResolvidos);
    notificar();
  }

  /* ------------------------------------------------------------------- utils */

  function novoUid() {
    if (global.crypto && typeof global.crypto.randomUUID === 'function') {
      return global.crypto.randomUUID();
    }
    return 'op-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  }

  function agora() {
    return new Date().toISOString();
  }

  function estado() {
    return {
      pendentes: fila.length,
      processando: processando,
      online: online,
      sessaoExpirada: sessaoExpirada,
      ultimoErro: ultimoErro,
      ultimaSincronizacao: ultimaSincronizacao,
      itens: fila.map(function (op) {
        return { descricao: op.descricao, tentativas: op.tentativas || 0 };
      })
    };
  }

  function notificar() {
    if (typeof document === 'undefined' || typeof document.dispatchEvent !== 'function') return;
    try {
      document.dispatchEvent(new CustomEvent('ch:fila', { detail: estado() }));
    } catch (e) {
      /* ambientes sem CustomEvent */
    }
  }

  function avisar(operacao, dados, falhou) {
    if (typeof document === 'undefined' || typeof document.dispatchEvent !== 'function') return;
    try {
      document.dispatchEvent(new CustomEvent('ch:fila:operacao', {
        detail: { operacao: operacao, dados: dados || {}, falhou: !!falhou }
      }));
    } catch (e) {
      /* ignora */
    }
  }

  /* ------------------------------------------------------------- enfileirar */

  /**
   * @param {Object} op
   *   metodo      'POST' | 'PATCH' | 'DELETE'
   *   url         caminho da API (pode conter {id})
   *   corpo       objeto enviado em JSON (opcional)
   *   descricao   texto curto para o indicador ("marcar Leite como comprado")
   *   refUid      uid da operação que cria o recurso (para resolver {id})
   *   desfazer    função chamada se o servidor recusar com 4xx
   *   juntar      false para nunca juntar com uma operação pendente igual
   */
  function enfileirar(op) {
    var operacao = {
      uid: op.uid || novoUid(),
      metodo: (op.metodo || 'POST').toUpperCase(),
      url: op.url,
      corpo: op.corpo || null,
      descricao: op.descricao || op.url,
      refUid: op.refUid || null,
      tentativas: 0,
      criadoEm: agora()
    };

    if (op.desfazer) desfazedores[operacao.uid] = op.desfazer;

    /* Remover algo que ainda nem chegou ao servidor cancela a criação — e a
       remoção também deixa de ser necessária (nada foi criado). */
    if (operacao.metodo === 'DELETE' && operacao.refUid) {
      if (cancelarCriacaoPendente(operacao.refUid)) {
        gravar();
        notificar();
        return { cancelado: true };
      }
    }

    if (op.juntar !== false) {
      var igual = indicePendente(operacao);
      if (igual >= 0) {
        fila[igual].corpo = operacao.corpo;
        fila[igual].descricao = operacao.descricao;
        if (desfazedores[operacao.uid]) {
          desfazedores[fila[igual].uid] = desfazedores[operacao.uid];
          delete desfazedores[operacao.uid];
        }
        gravar();
        processar();
        return fila[igual];
      }
    }

    fila.push(operacao);
    gravar();
    processar();
    return operacao;
  }

  function mesmoAlvo(a, b) {
    return a.url === b.url && (a.refUid || null) === (b.refUid || null);
  }

  /** Índice de uma operação pendente que a nova pode substituir (-1 se nenhuma). */
  function indicePendente(nova) {
    for (var i = 0; i < fila.length; i += 1) {
      var atual = fila[i];
      if (!mesmoAlvo(atual, nova)) continue;

      if (nova.metodo === 'DELETE') {
        if (atual.metodo === 'PATCH') {
          /* O update pendente deixa de fazer sentido. */
          delete desfazedores[atual.uid];
          fila.splice(i, 1);
          i -= 1;
          continue;
        }
        if (atual.metodo === 'DELETE') return i;
        continue; /* POST (criação) não se junta */
      }

      if (nova.metodo === 'PATCH' && atual.metodo === 'PATCH') {
        /* Só junta PATCHes que alteram o mesmo campo (último valor ganha).
           Juntar campos diferentes mudaria a ordem em que o servidor os
           aplica — p.ex. "comprado" antes da quantidade faria a quantidade
           ser ignorada. Nesses casos ficam duas operações, pela ordem certa. */
        var chavesAtuais = Object.keys(atual.corpo || {});
        var chavesNovas = Object.keys(nova.corpo || {});
        var mesmosCampos = chavesAtuais.length === chavesNovas.length &&
          chavesNovas.every(function (chave) { return chavesAtuais.indexOf(chave) !== -1; });
        if (mesmosCampos) return i;
      }
    }
    return -1;
  }

  /** Remove a criação pendente e tudo o que dependia dela.
   *  Devolve true se a própria criação ainda estava na fila. */
  function cancelarCriacaoPendente(refUid) {
    var removeu = false;
    var removeuCriacao = false;
    for (var i = fila.length - 1; i >= 0; i -= 1) {
      var op = fila[i];
      if (op.uid === refUid || op.refUid === refUid) {
        if (op.uid === refUid) removeuCriacao = true;
        delete desfazedores[op.uid];
        fila.splice(i, 1);
        removeu = true;
      }
    }
    delete idsResolvidos[refUid];
    if (removeu) gravarJson(CHAVE_FILA, fila);
    return removeuCriacao;
  }

  /* ------------------------------------------------------------------ envio */

  function urlResolvida(op) {
    if (op.url.indexOf('{id}') === -1) return op.url;
    var id = op.refUid ? idsResolvidos[op.refUid] : null;
    if (!id) return null; /* o recurso ainda não existe no servidor */
    return op.url.replace('{id}', String(id));
  }

  function enviar(op) {
    var url = urlResolvida(op);
    if (!url) return Promise.reject({ bloqueado: true });

    var opcoes = {
      method: op.metodo,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-Idempotency-Key': op.uid
      },
      credentials: 'same-origin',
      cache: 'no-store'
    };
    if (op.corpo) opcoes.body = JSON.stringify(op.corpo);

    return fetch(url, opcoes).then(function (resposta) {
      return resposta.json().catch(function () { return {}; }).then(function (dados) {
        return { resposta: resposta, dados: dados };
      });
    });
  }

  function limparTemporizador() {
    if (temporizador) {
      global.clearTimeout(temporizador);
      temporizador = null;
    }
  }

  function agendar() {
    if (temporizador || !fila.length || sessaoExpirada) return;
    var indice = Math.min(tentativasSeguidas, ESPERAS.length - 1);
    temporizador = global.setTimeout(function () {
      temporizador = null;
      processar();
    }, ESPERAS[indice]);
  }

  function iniciarVigia() {
    if (vigia) return;
    vigia = global.setInterval(function () {
      if (fila.length && !sessaoExpirada) processar();
    }, INTERVALO_VIGIA);
  }

  function pararVigia() {
    if (vigia) {
      global.clearInterval(vigia);
      vigia = null;
    }
  }

  /** Trata a resposta da operação na cabeça da fila.
   *  Devolve true para continuar já com a próxima, false para parar. */
  function tratar(resultado) {
    var resposta = resultado.resposta;

    if (resposta.status === 401 || (resposta.redirected && resposta.url.indexOf('/login') !== -1)) {
      sessaoExpirada = true;
      ultimoErro = 'sessão expirada';
      pararVigia();
      notificar();
      return false;
    }

    if (resposta.ok) {
      var operacao = fila.shift();
      delete desfazedores[operacao.uid];
      tentativasSeguidas = 0;
      ultimoErro = '';
      ultimaSincronizacao = agora();

      /* O item criado ganha um id real: as operações seguintes que apontam para
         o uid temporário passam a usar o id definitivo. */
      if (operacao.metodo === 'POST' && resultado.dados && resultado.dados.item) {
        idsResolvidos[operacao.uid] = resultado.dados.item.id;
      }
      gravar();
      avisar(operacao, resultado.dados);
      return true;
    }

    if (resposta.status >= 400 && resposta.status < 500) {
      /* Pedido inválido: repetir não resolve. Descartamos e avisamos. */
      var rejeitada = fila.shift();
      var desfazer = desfazedores[rejeitada.uid];
      delete desfazedores[rejeitada.uid];
      ultimoErro = (resultado.dados && resultado.dados.erro) || 'operação recusada';

      /* Se a criação falhou, tudo o que dependia dela também não pode correr. */
      if (rejeitada.metodo === 'POST') {
        for (var i = fila.length - 1; i >= 0; i -= 1) {
          if (fila[i].refUid === rejeitada.uid) {
            var dependente = fila[i];
            var desfazerDependente = desfazedores[dependente.uid];
            delete desfazedores[dependente.uid];
            fila.splice(i, 1);
            if (typeof desfazerDependente === 'function') {
              try { desfazerDependente(resultado.dados); } catch (e) { /* ignora */ }
            }
          }
        }
      }
      gravar();
      if (typeof desfazer === 'function') {
        try { desfazer(resultado.dados); } catch (e) { /* ignora */ }
      }
      avisar(rejeitada, resultado.dados, true);
      return true;
    }

    /* 5xx: o servidor está com problemas, tentamos de novo mais tarde. */
    fila[0].tentativas = (fila[0].tentativas || 0) + 1;
    tentativasSeguidas += 1;
    ultimoErro = 'servidor indisponível';
    gravar();
    agendar();
    return false;
  }

  function iterar() {
    if (!fila.length || sessaoExpirada || !online) return Promise.resolve();
    return enviar(fila[0]).then(tratar).then(function (continuar) {
      if (continuar) return iterar();
      return undefined;
    }).catch(function (erro) {
      if (erro && erro.bloqueado) {
        /* O recurso ainda não existe no servidor: espera pela criação. */
        ultimoErro = 'a aguardar o item ser criado';
        agendar();
        return undefined;
      }
      if (!fila.length) return undefined;
      fila[0].tentativas = (fila[0].tentativas || 0) + 1;
      tentativasSeguidas += 1;
      ultimoErro = online ? 'sem resposta do servidor' : 'sem rede';
      if (global.navigator && global.navigator.onLine === false) online = false;
      gravar();
      agendar();
      return undefined;
    });
  }

  function processar() {
    if (processando) return Promise.resolve();
    if (!fila.length) {
      notificar();
      return Promise.resolve();
    }
    if (sessaoExpirada) return Promise.resolve();

    /* O iOS pode perder o evento "online": confirmamos sempre antes de enviar. */
    if (global.navigator && typeof global.navigator.onLine === 'boolean') {
      online = global.navigator.onLine !== false;
    }
    if (!online) {
      ultimoErro = 'sem rede';
      notificar();
      return Promise.resolve();
    }

    limparTemporizador();
    processando = true;
    notificar();

    return iterar().then(function () {
      processando = false;
      notificar();
      if (fila.length && !sessaoExpirada && online && !temporizador) {
        /* Sobrou algo (provável falha de rede): o agendamento já foi feito. */
        agendar();
      }
    });
  }

  /* ----------------------------------------------------------------- eventos */

  function aoVoltarARede() {
    online = true;
    tentativasSeguidas = 0;
    ultimoErro = '';
    notificar();
    processar();
  }

  function aoFicarOffline() {
    online = false;
    notificar();
  }

  function aoFicarVisivel() {
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
    processar();
  }

  if (global.addEventListener) {
    global.addEventListener('online', aoVoltarARede);
    global.addEventListener('offline', aoFicarOffline);
    global.addEventListener('focus', aoFicarVisivel);
    global.addEventListener('pageshow', aoFicarVisivel);
    global.addEventListener('storage', function (evento) {
      if (evento.key === CHAVE_FILA) {
        carregar();
        notificar();
      }
    });
  }
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('visibilitychange', aoFicarVisivel);
  }

  /* ---------------------------------------------------------------- arranque */

  carregar();
  iniciarVigia();
  if (fila.length) {
    /* Pequeno atraso: deixa a página pintar antes de falar com o servidor. */
    global.setTimeout(processar, 600);
  }
  notificar();

  global.CheckHouseFila = {
    enfileirar: enfileirar,
    processar: processar,
    estado: estado,
    novoUid: novoUid,
    pendentes: function () { return fila.length; },
    retomarSessao: function () {
      sessaoExpirada = false;
      ultimoErro = '';
      iniciarVigia();
      return processar();
    },
    _interno: {
      ler: function () { return fila.slice(); },
      limpar: function () {
        fila = [];
        idsResolvidos = {};
        desfazedores = {};
        gravar();
      },
      definirIds: function (mapa) { idsResolvidos = mapa || {}; },
      idsResolvidos: function () { return idsResolvidos; },
      definirOnline: function (valor) { online = !!valor; },
      definirSessaoExpirada: function (valor) { sessaoExpirada = !!valor; }
    }
  };
}(typeof window !== 'undefined' ? window : globalThis));
