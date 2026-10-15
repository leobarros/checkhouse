/* ==========================================================================
   CheckHouse — Despensa com fila offline
   --------------------------------------------------------------------------
   Mesma lógica da Lista de compras: atualização imediata da interface e envio
   pela fila (static/js/fila.js). Sem JavaScript, os formulários continuam a
   funcionar como antes.
   ========================================================================== */
(function () {
  'use strict';

  var Fila = window.CheckHouseFila;
  var raiz = document.querySelector('[data-despensa]');
  if (!Fila || !raiz) return;

  var localId = raiz.getAttribute('data-local');
  var lista = raiz.querySelector('[data-produtos]');
  var modelo = document.getElementById('modelo-produto');
  var campoNome = raiz.querySelector('[data-form-adicionar] input[name="nome"]');
  var campoQtd = raiz.querySelector('[data-form-adicionar] input[name="quantidade"]');

  function urlProduto(id) {
    return '/api/produtos/' + (id || '{id}');
  }

  /* --------------------------------------------------------------- utilitários */

  function dadosLinha(elemento) {
    return {
      id: elemento.getAttribute('data-id') || '',
      uid: elemento.getAttribute('data-uid') || '',
      nome: elemento.getAttribute('data-nome') || '',
      quantidade: Math.max(0, parseInt(elemento.getAttribute('data-quantidade'), 10) || 0)
    };
  }

  function gravarLinha(elemento, info) {
    /* Sem id ainda (item criado no telemóvel) o atributo é removido: o CSS usa
       :not([data-id]) para marcar a linha como "por sincronizar". */
    if (info.id) elemento.setAttribute('data-id', info.id);
    else elemento.removeAttribute('data-id');
    elemento.setAttribute('data-quantidade', info.quantidade);
    elemento.setAttribute('data-nome', info.nome);
  }

  function pintarLinha(elemento, info) {
    var nome = info.nome;
    var emFalta = info.quantidade === 0;

    elemento.querySelector('.ch-item-nome').textContent = nome;
    elemento.querySelector('.controle-qtd .valor').textContent = info.quantidade;
    elemento.querySelector('.controle-qtd .valor').classList.toggle('text-danger-emphasis', emFalta);
    elemento.querySelector('.controle-qtd .valor').classList.toggle('fw-bold', emFalta);

    var icone = elemento.querySelector('[data-icone-estado]');
    icone.className = 'bi ' + (emFalta ? 'bi-exclamation-circle-fill text-danger-emphasis' : 'bi-box-seam text-primary-emphasis') + ' fs-5';

    elemento.querySelector('[data-meta-texto]').textContent = emFalta
      ? 'Em falta — foi adicionado à lista de compras'
      : info.quantidade + ' em stock';

    var menos = elemento.querySelector('[data-acao="qtd-menos"]');
    menos.disabled = emFalta;
    menos.setAttribute('aria-label', 'Diminuir quantidade de ' + nome);
    elemento.querySelector('[data-acao="qtd-mais"]').setAttribute('aria-label', 'Aumentar quantidade de ' + nome);
    elemento.querySelector('[data-acao="editar"]').setAttribute('aria-label', 'Editar ' + nome);
    elemento.querySelector('[data-acao="remover"]').setAttribute('aria-label', 'Excluir ' + nome + ' da despensa');
  }

  function criarLinha(info) {
    var fragmento = modelo.content.cloneNode(true);
    var elemento = fragmento.querySelector('[data-produto]');
    elemento.setAttribute('data-uid', info.uid || '');
    gravarLinha(elemento, info);
    pintarLinha(elemento, info);
    return fragmento;
  }

  function inserirLinha(fragmento) {
    var vazio = lista.querySelector('[data-lista-vazia]');
    if (vazio) vazio.remove();
    lista.appendChild(fragmento);
  }

  function removerLinha(elemento) {
    if (elemento && elemento.parentNode) elemento.parentNode.removeChild(elemento);
    verificarVazio();
  }

  function verificarVazio() {
    var temItens = lista.querySelector('[data-produto]');
    var vazio = lista.querySelector('[data-lista-vazia]');
    if (!temItens && !vazio) {
      var div = document.createElement('div');
      div.className = 'list-group-item';
      div.setAttribute('data-lista-vazia', '');
      div.innerHTML = '<div class="ch-vazio"><i class="bi bi-inbox" aria-hidden="true"></i>' +
        '<span class="ch-vazio-titulo">A despensa está vazia</span>' +
        '<span>Adicione o primeiro produto no campo acima.</span></div>';
      lista.appendChild(div);
    } else if (temItens && vazio) {
      vazio.remove();
    }
  }

  function avisar(mensagem, tipo) {
    if (window.CheckHouseEstado) window.CheckHouseEstado.mostrarAviso(mensagem, tipo);
  }

  /* ------------------------------------------------------------------ ações */

  function enviarProduto(metodo, elemento, corpo, descricao, desfazer) {
    var info = dadosLinha(elemento);
    return Fila.enfileirar({
      metodo: metodo,
      url: info.id ? urlProduto(info.id) : urlProduto(null),
      corpo: corpo,
      descricao: descricao,
      refUid: info.id ? null : info.uid,
      desfazer: desfazer
    });
  }

  function alterarQuantidade(elemento, passo) {
    var info = dadosLinha(elemento);
    var anterior = info.quantidade;
    var nova = Math.max(0, anterior + passo);
    if (nova === anterior) return;
    info.quantidade = nova;
    gravarLinha(elemento, info);
    pintarLinha(elemento, info);
    enviarProduto('PATCH', elemento, { quantidade: nova }, 'quantidade de ' + info.nome, function () {
      info.quantidade = anterior;
      gravarLinha(elemento, info);
      pintarLinha(elemento, info);
      avisar('Não foi possível atualizar «' + info.nome + '».', 'erro');
    });
  }

  function renomear(elemento, novoNome) {
    var info = dadosLinha(elemento);
    var anterior = info.nome;
    info.nome = novoNome;
    gravarLinha(elemento, info);
    pintarLinha(elemento, info);
    enviarProduto('PATCH', elemento, { nome: novoNome }, 'renomear ' + anterior, function () {
      info.nome = anterior;
      gravarLinha(elemento, info);
      pintarLinha(elemento, info);
      avisar('Não foi possível renomear «' + anterior + '».', 'erro');
    });
  }

  function remover(elemento) {
    var info = dadosLinha(elemento);
    var pai = elemento.parentNode;
    var seguinte = elemento.nextSibling;
    elemento.remove();
    verificarVazio();
    enviarProduto('DELETE', elemento, null, 'excluir ' + info.nome, function () {
      pai.insertBefore(elemento, seguinte);
      verificarVazio();
      avisar('Não foi possível excluir «' + info.nome + '».', 'erro');
    });
  }

  function adicionar() {
    var nome = (campoNome.value || '').trim();
    if (!nome) return;
    var quantidade = Math.max(1, parseInt(campoQtd.value, 10) || 1);
    var uid = Fila.novoUid();

    inserirLinha(criarLinha({ nome: nome, quantidade: quantidade, uid: uid }));
    campoNome.value = '';
    campoQtd.value = '1';
    campoNome.focus();

    Fila.enfileirar({
      metodo: 'POST',
      url: '/api/locais/' + localId + '/despensa/produtos',
      corpo: { nome: nome, quantidade: quantidade },
      uid: uid,
      descricao: 'adicionar ' + nome,
      desfazer: function () {
        removerLinha(lista.querySelector('[data-uid="' + uid + '"]'));
        avisar('Não foi possível adicionar «' + nome + '».', 'erro');
      }
    });
  }

  /* --------------------------------------------------------- reconciliação */

  var reconciliando = false;

  function reconciliar() {
    if (reconciliando) return;
    reconciliando = true;
    fetch('/api/locais/' + localId + '/despensa', { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (dados) {
        reconciliando = false;
        if (!dados || !dados.produtos) return;
        var porId = {};
        dados.produtos.forEach(function (produto) { porId[String(produto.id)] = produto; });

        Array.prototype.forEach.call(lista.querySelectorAll('[data-produto]'), function (linha) {
          var info = dadosLinha(linha);
          if (!info.id) return;
          var servidor = porId[info.id];
          if (!servidor) { linha.remove(); return; }
          info.quantidade = servidor.quantidade;
          info.nome = servidor.nome;
          gravarLinha(linha, info);
          pintarLinha(linha, info);
          delete porId[info.id];
        });

        Object.keys(porId).forEach(function (id) {
          var produto = porId[id];
          inserirLinha(criarLinha({ nome: produto.nome, quantidade: produto.quantidade, id: produto.id }));
        });
        verificarVazio();
      })
      .catch(function () { reconciliando = false; });
  }

  /* ---------------------------------------------------------------- eventos */

  raiz.addEventListener('click', function (evento) {
    var botao = evento.target.closest('[data-acao]');
    if (!botao || !raiz.contains(botao)) return;
    var elemento = botao.closest('[data-produto]');
    if (!elemento) return;
    var acao = botao.getAttribute('data-acao');

    if (acao === 'qtd-mais') { evento.preventDefault(); alterarQuantidade(elemento, 1); }
    else if (acao === 'qtd-menos') { evento.preventDefault(); alterarQuantidade(elemento, -1); }
  });

  document.addEventListener('submit', function (evento) {
    var formulario = evento.target.closest('[data-acao-form]');
    if (!formulario) return;
    var acao = formulario.getAttribute('data-acao-form');
    var id = formulario.getAttribute('data-produto-id');
    var elemento = id ? lista.querySelector('[data-produto][data-id="' + id + '"]') : null;

    if (acao === 'adicionar-produto') {
      evento.preventDefault();
      adicionar();
    } else if (acao === 'editar-produto' && elemento) {
      evento.preventDefault();
      var campo = formulario.querySelector('input[name="nome"]');
      var novoNome = (campo.value || '').trim();
      var dialogo = formulario.closest('.modal');
      if (dialogo && window.bootstrap) window.bootstrap.Modal.getOrCreateInstance(dialogo).hide();
      if (novoNome && novoNome !== dadosLinha(elemento).nome) renomear(elemento, novoNome);
    } else if (acao === 'remover-produto' && elemento) {
      evento.preventDefault();
      var modal = formulario.closest('.modal');
      if (modal && window.bootstrap) window.bootstrap.Modal.getOrCreateInstance(modal).hide();
      remover(elemento);
    }
  });

  document.addEventListener('ch:fila:operacao', function (evento) {
    var detalhe = evento.detail || {};
    var operacao = detalhe.operacao || {};
    if (detalhe.falhou) return;
    if (operacao.metodo === 'POST' && detalhe.dados && detalhe.dados.produto) {
      var elemento = lista.querySelector('[data-uid="' + operacao.uid + '"]');
      if (elemento) {
        var info = dadosLinha(elemento);
        info.id = detalhe.dados.produto.id;
        gravarLinha(elemento, info);
        pintarLinha(elemento, info);
      }
    }
  });

  document.addEventListener('ch:fila', function (evento) {
    var estado = evento.detail || {};
    if (estado.pendentes === 0 && estado.ultimaSincronizacao) reconciliar();
  });

  /* A página pode ter vindo do cache do navegador (uso sem rede em http://IP):
     se não há nada por sincronizar, confirma o estado no servidor. */
  if (Fila.pendentes() === 0 && navigator.onLine !== false) reconciliar();
})();
