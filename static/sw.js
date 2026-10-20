/* ==========================================================================
   CheckHouse — Service Worker
   --------------------------------------------------------------------------
   Só é registado em contextos seguros (HTTPS ou localhost). Serve para:
   - abrir a Lista/Despensa já guardada quando não há rede;
   - manter o CSS, o JS e a fonte de ícones disponíveis offline;
   - guardar a última resposta das consultas (GET) da API.

   O que NÃO faz: enviar operações pendentes. O iOS não tem a Background Sync
   API, por isso quem envia a fila é o JavaScript da página (static/js/fila.js)
   enquanto a app estiver aberta.
   ========================================================================== */
'use strict';

/* A versão chega no registo (/sw.js?v=<versao dos assets>), por isso um
   deploy novo invalida automaticamente as caches antigas. */
var VERSAO = (function () {
  try {
    return new URL(self.location.href).searchParams.get('v') || '1';
  } catch (e) {
    return '1';
  }
}());
var CACHE_ESTATICO = 'ch-estatico-' + VERSAO;
var CACHE_PAGINAS = 'ch-paginas-' + VERSAO;
var CACHE_DADOS = 'ch-dados-' + VERSAO;

var ESSENCIAIS = [
  '/static/css/app.css',
  '/static/js/app.js',
  '/static/js/fila.js',
  '/static/js/estado-fila.js',
  '/static/js/pagina-lista.js',
  '/static/js/pagina-despensa.js',
  '/static/icons/favicon.svg',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/offline.html',
  '/static/vendor/bootstrap/bootstrap.min.css',
  '/static/vendor/bootstrap/bootstrap.bundle.min.js',
  '/static/vendor/bootstrap-icons/bootstrap-icons.css',
  '/static/vendor/bootstrap-icons/fonts/bootstrap-icons.woff2'
].map(function (url) {
  /* Guarda com o mesmo ?v= que as páginas pedem: assim o cache primeiro
     acerta na versão certa em vez de servir sempre a cópia antiga. */
  return url + '?v=' + encodeURIComponent(VERSAO);
});

var TEMPO_LIMITE_REDE = 4000;

self.addEventListener('install', function (evento) {
  evento.waitUntil(
    caches.open(CACHE_ESTATICO).then(function (cache) {
      return Promise.all(ESSENCIAIS.map(function (url) {
        return cache.add(new Request(url, { cache: 'reload' })).catch(function () { /* segue */ });
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (evento) {
  var validos = [CACHE_ESTATICO, CACHE_PAGINAS, CACHE_DADOS];
  evento.waitUntil(
    caches.keys().then(function (nomes) {
      return Promise.all(nomes.map(function (nome) {
        if (validos.indexOf(nome) === -1) return caches.delete(nome);
        return null;
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('message', function (evento) {
  var dados = evento.data || {};
  if (dados.tipo === 'limpar') {
    /* Usado no logout: nenhuma página privada fica guardada no aparelho. */
    evento.waitUntil(
      Promise.all([caches.delete(CACHE_PAGINAS), caches.delete(CACHE_DADOS), caches.delete(CACHE_ESTATICO)])
    );
  }
  if (dados.tipo === 'versao') {
    evento.waitUntil(self.clients.matchAll().then(function (clientes) {
      clientes.forEach(function (cliente) { cliente.postMessage({ tipo: 'versao', versao: VERSAO }); });
    }));
  }
});

function comLimiteDeTempo(promessa, ms) {
  return new Promise(function (resolver, rejeitar) {
    var relogio = setTimeout(function () { rejeitar(new Error('tempo-limite')); }, ms);
    promessa.then(function (valor) {
      clearTimeout(relogio);
      resolver(valor);
    }, function (erro) {
      clearTimeout(relogio);
      rejeitar(erro);
    });
  });
}

/** Rede primeiro, com limite de tempo; cache como reserva. */
function redePrimeiro(pedido, nomeCache, reserva) {
  return comLimiteDeTempo(fetch(pedido), TEMPO_LIMITE_REDE).then(function (resposta) {
    if (resposta && (resposta.ok || resposta.type === 'opaque')) {
      var copia = resposta.clone();
      caches.open(nomeCache).then(function (cache) { cache.put(pedido, copia); });
    }
    return resposta;
  }).catch(function () {
    return caches.match(pedido, { ignoreSearch: true }).then(function (guardada) {
      if (guardada) return guardada;
      if (reserva) return caches.match(reserva, { ignoreSearch: true });
      return new Response('', { status: 504, statusText: 'Sem ligação' });
    });
  });
}

/** Cache primeiro por versão exata (?v=). Uma versão nova de um asset vai à
 *  rede em vez de reutilizar a cópia antiga; só offline se aceita a última
 *  versão conhecida (ignoreSearch). Sem isto o ?v= era ignorado e um deploy
 *  podia continuar a servir o JavaScript antigo. */
function cachePrimeiro(pedido) {
  return caches.match(pedido).then(function (guardada) {
    if (guardada) {
      /* Atualiza em segundo plano, sem bloquear. */
      fetch(pedido).then(function (resposta) {
        if (resposta && resposta.ok) {
          caches.open(CACHE_ESTATICO).then(function (cache) { cache.put(pedido, resposta); });
        }
      }).catch(function () { /* offline: fica a versão guardada */ });
      return guardada;
    }
    return fetch(pedido).then(function (resposta) {
      if (resposta && resposta.ok) {
        var copia = resposta.clone();
        caches.open(CACHE_ESTATICO).then(function (cache) { cache.put(pedido, copia); });
      }
      return resposta;
    }).catch(function () {
      /* Offline: usa a última versão guardada, mesmo com outro ?v=. */
      return caches.match(pedido, { ignoreSearch: true }).then(function (antiga) {
        if (antiga) return antiga;
        return new Response('', { status: 504, statusText: 'Sem ligação' });
      });
    });
  });
}

function limparDadosPrivados() {
  return Promise.all([caches.delete(CACHE_PAGINAS), caches.delete(CACHE_DADOS)]);
}

self.addEventListener('fetch', function (evento) {
  var pedido = evento.request;
  var url = new URL(pedido.url);

  if (url.origin !== self.location.origin) return;

  /* Sair da conta: apaga páginas e dados guardados. */
  if (pedido.mode === 'navigate' && (url.pathname === '/logout' || url.pathname === '/login')) {
    evento.waitUntil(limparDadosPrivados());
  }

  /* API: rede primeiro, cache da última resposta como reserva. */
  if (url.pathname.indexOf('/api/') === 0) {
    if (pedido.method !== 'GET') return; /* a fila offline trata destes */
    evento.respondWith(
      comLimiteDeTempo(fetch(pedido), TEMPO_LIMITE_REDE).then(function (resposta) {
        if (resposta && resposta.ok) {
          var copia = resposta.clone();
          caches.open(CACHE_DADOS).then(function (cache) { cache.put(pedido, copia); });
        }
        return resposta;
      }).catch(function () {
        return caches.match(pedido, { ignoreSearch: true }).then(function (guardada) {
          if (guardada) {
            var cabecalhos = new Headers(guardada.headers);
            cabecalhos.set('X-CheckHouse-Cache', '1');
            return guardada.blob().then(function (corpo) {
              return new Response(corpo, { status: 200, headers: cabecalhos });
            });
          }
          return new Response(JSON.stringify({ erro: 'sem_rede' }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
          });
        });
      })
    );
    return;
  }

  /* Navegação (páginas): rede primeiro; offline serve a última versão. */
  if (pedido.mode === 'navigate') {
    evento.respondWith(redePrimeiro(pedido, CACHE_PAGINAS, '/static/offline.html'));
    return;
  }

  if (url.pathname.indexOf('/static/') === 0) {
    evento.respondWith(cachePrimeiro(pedido));
  }
});
