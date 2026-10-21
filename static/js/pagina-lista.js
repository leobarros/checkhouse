/* ==========================================================================
   CheckHouse — Lista de compras com fila offline
   --------------------------------------------------------------------------
   Melhoria progressiva: sem JavaScript os formulários continuam a funcionar
   como antes (POST + redirect). Com JavaScript, cada ação atualiza a interface
   na hora e entra na fila (static/js/fila.js), que sincroniza quando há rede.
   ========================================================================== */
(function () {
  'use strict';

  var Fila = window.CheckHouseFila;
  var raiz = document.querySelector('[data-lista]');
  if (!Fila || !raiz) return;

  var localId = raiz.getAttribute('data-local');
  var lista = raiz.querySelector('[data-itens]');
  var modelo = document.getElementById('modelo-item-lista');
  var campoNome = raiz.querySelector('[data-form-adicionar] input[name="nome"]');
  var campoQtd = raiz.querySelector('[data-form-adicionar] input[name="quantidade"]');
  var modalEditar = document.getElementById('modalEditarItem');
  var itemEmEdicao = null;
  var ultimoItem = null;

  function urlItem(id) {
    return '/api/itens/' + (id || '{id}');
  }

  /* --------------------------------------------------------------- utilitários */

  function linha(elemento) {
    return elemento.closest('[data-item]');
  }

  function dadosLinha(elemento) {
    return {
      id: elemento.getAttribute('data-id') || '',
      uid: elemento.getAttribute('data-uid') || '',
      nome: elemento.getAttribute('data-nome') || '',
      quantidade: parseInt(elemento.getAttribute('data-quantidade'), 10) || 1,
      comprado: elemento.getAttribute('data-comprado') === '1'
    };
  }

  function gravarLinha(elemento, info) {
    /* Sem id ainda (item criado no telemóvel) o atributo é removido: o CSS usa
       :not([data-id]) para marcar a linha como "por sincronizar". */
    if (info.id) elemento.setAttribute('data-id', info.id);
    else elemento.removeAttribute('data-id');
    elemento.setAttribute('data-nome', info.nome);
    elemento.setAttribute('data-quantidade', info.quantidade);
    elemento.setAttribute('data-comprado', info.comprado ? '1' : '0');
  }

  function pintarLinha(elemento, info) {
    var nome = info.nome;
    elemento.querySelector('.ch-item-nome').textContent = nome;

    var botaoAlternar = elemento.querySelector('[data-acao="alternar"]');
    var icone = botaoAlternar.querySelector('i');
    botaoAlternar.className = 'btn-icone btn-link ' + (info.comprado ? 'text-success-emphasis' : 'text-secondary');
    icone.className = 'bi ' + (info.comprado ? 'bi-check-circle-fill' : 'bi-circle') + ' fs-4';
    botaoAlternar.setAttribute('aria-label', (info.comprado ? 'Desmarcar ' : 'Marcar ') + nome + ' como comprado');
    botaoAlternar.setAttribute('title', info.comprado ? 'Desmarcar como comprado' : 'Marcar como comprado');

    elemento.classList.toggle('ch-item-concluido', info.comprado);
    elemento.querySelector('[data-controle-qtd]').hidden = info.comprado;
    var badge = elemento.querySelector('[data-badge-qtd]');
    badge.hidden = !info.comprado;
    badge.textContent = info.quantidade;
    elemento.querySelector('.controle-qtd .valor').textContent = info.quantidade;

    var botaoRemover = elemento.querySelector('[data-acao="remover"]');
    botaoRemover.setAttribute('aria-label', 'Remover ' + nome + ' da lista');
    var botaoEditar = elemento.querySelector('[data-acao="editar"]');
    if (botaoEditar) {
      botaoEditar.setAttribute('aria-label', 'Editar ' + nome);
      /* Renomear um item já comprado deixaria o estoque com o nome antigo
         (a baixa da despensa é feita pelo nome). Para editar, desmarca-se. */
      botaoEditar.hidden = info.comprado;
    }
    var botaoMenos = elemento.querySelector('[data-acao="qtd-menos"]');
    botaoMenos.setAttribute('aria-label', 'Diminuir quantidade de ' + nome);
    elemento.querySelector('[data-acao="qtd-mais"]').setAttribute('aria-label', 'Aumentar quantidade de ' + nome);
  }

  function criarLinha(info) {
    var fragmento = modelo.content.cloneNode(true);
    var elemento = fragmento.querySelector('[data-item]');
    elemento.setAttribute('data-nome', info.nome);
    elemento.setAttribute('data-uid', info.uid || '');
    gravarLinha(elemento, info);
    elemento.querySelector('[data-meta-texto]').textContent = info.meta || 'agora mesmo';
    pintarLinha(elemento, info);
    return fragmento;
  }

  function removerLinha(elemento) {
    if (elemento && elemento.parentNode) elemento.parentNode.removeChild(elemento);
    verificarVazio();
  }

  /* Um item novo passa a ser a última linha (antes dos comprados). */
  function inserirLinha(fragmento) {
    var vazio = lista.querySelector('[data-lista-vazia]');
    if (vazio) vazio.remove();
    var concluidos = lista.querySelectorAll('.ch-item-concluido');
    if (concluidos.length) {
      lista.insertBefore(fragmento, concluidos[0]);
    } else {
      lista.appendChild(fragmento);
    }
  }

  function verificarVazio() {
    var temItens = lista.querySelector('[data-item]');
    var vazio = lista.querySelector('[data-lista-vazia]');
    if (!temItens && !vazio && modelo) {
      var div = document.createElement('div');
      div.className = 'list-group-item';
      div.setAttribute('data-lista-vazia', '');
      div.innerHTML = '<div class="ch-vazio"><i class="bi bi-emoji-smile" aria-hidden="true"></i>' +
        '<span class="ch-vazio-titulo">Sua lista está vazia</span>' +
        '<span>Tudo abastecido! Adicione um item acima quando faltar algo.</span></div>';
      lista.appendChild(div);
    } else if (temItens && vazio) {
      vazio.remove();
    }
  }

  function avisar(mensagem, tipo) {
    if (window.CheckHouseEstado) window.CheckHouseEstado.mostrarAviso(mensagem, tipo);
  }

  /* ---------------------------------------------------------------- ações */

  function enviarItem(metodo, elemento, corpo, descricao, desfazer) {
    var info = dadosLinha(elemento);
    var operacao = {
      metodo: metodo,
      url: info.id ? urlItem(info.id) : urlItem(null),
      corpo: corpo,
      descricao: descricao,
      refUid: info.id ? null : info.uid,
      desfazer: desfazer
    };
    return Fila.enfileirar(operacao);
  }

  function alternar(elemento) {
    var info = dadosLinha(elemento);
    var novo = !info.comprado;
    info.comprado = novo;
    gravarLinha(elemento, info);
    pintarLinha(elemento, info);
    enviarItem('PATCH', elemento, { comprado: novo },
      (novo ? 'marcar ' : 'desmarcar ') + info.nome,
      function () {
        info.comprado = !novo;
        gravarLinha(elemento, info);
        pintarLinha(elemento, info);
        avisar('Não foi possível atualizar «' + info.nome + '».', 'erro');
      });
  }

  function alterarQuantidade(elemento, passo) {
    var info = dadosLinha(elemento);
    var nova = Math.max(1, info.quantidade + passo);
    if (nova === info.quantidade) return;
    info.quantidade = nova;
    gravarLinha(elemento, info);
    pintarLinha(elemento, info);
    enviarItem('PATCH', elemento, { quantidade: nova }, 'quantidade de ' + info.nome);
  }

  function renomear(elemento, novoNome) {
    var info = dadosLinha(elemento);
    var anterior = info.nome;
    info.nome = novoNome;
    gravarLinha(elemento, info);
    pintarLinha(elemento, info);
    enviarItem('PATCH', elemento, { nome: novoNome }, 'renomear ' + anterior, function () {
      info.nome = anterior;
      gravarLinha(elemento, info);
      pintarLinha(elemento, info);
      avisar('Não foi possível renomear «' + anterior + '».', 'erro');
    });
  }

  /* Abre o modal já com o nome atual. Chamado no clique do lápis, antes de o
     Bootstrap mostrar o modal (o listener do Bootstrap corre depois). */
  function prepararEdicao(elemento) {
    if (!modalEditar) return;
    itemEmEdicao = elemento;
    modalEditar.querySelector('input[name="nome"]').value = dadosLinha(elemento).nome;
  }

  function remover(elemento) {
    var info = dadosLinha(elemento);
    var pai = elemento.parentNode;
    var seguinte = elemento.nextSibling;
    elemento.remove();
    verificarVazio();
    enviarItem('DELETE', elemento, null, 'remover ' + info.nome, function () {
      pai.insertBefore(elemento, seguinte);
      verificarVazio();
      avisar('Não foi possível remover «' + info.nome + '».', 'erro');
    });
  }

  function adicionar(formulario) {
    var nome = (campoNome.value || '').trim();
    if (!nome) return;
    var quantidade = Math.max(1, parseInt(campoQtd.value, 10) || 1);
    var uid = Fila.novoUid();

    var fragmento = criarLinha({
      nome: nome, quantidade: quantidade, comprado: false, uid: uid,
      meta: 'agora mesmo · aguardando sincronização'
    });
    inserirLinha(fragmento);
    ultimoItem = lista.querySelector('[data-uid="' + uid + '"]');

    campoNome.value = '';
    campoQtd.value = '1';
    campoNome.focus();

    Fila.enfileirar({
      metodo: 'POST',
      url: '/api/locais/' + localId + '/lista/itens',
      corpo: { nome: nome, quantidade: quantidade },
      uid: uid,
      descricao: 'adicionar ' + nome,
      desfazer: function () {
        var linhaCriada = lista.querySelector('[data-uid="' + uid + '"]');
        removerLinha(linhaCriada);
        avisar('Não foi possível adicionar «' + nome + '».', 'erro');
      }
    });
  }

  function limparComprados(formulario) {
    var linhas = Array.prototype.slice.call(lista.querySelectorAll('.ch-item-concluido'));
    linhas.forEach(function (linha) { linha.remove(); });
    verificarVazio();
    Fila.enfileirar({
      metodo: 'POST',
      url: '/api/locais/' + localId + '/lista/limpar',
      descricao: 'limpar comprados',
      desfazer: function () {
        avisar('Não foi possível limpar os itens comprados.', 'erro');
        reconciliar();
      }
    });
  }

  /* --------------------------------------------------------- reconciliação */

  var reconciliando = false;

  function reconciliar() {
    if (reconciliando) return;
    reconciliando = true;
    fetch('/api/locais/' + localId + '/lista', { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (dados) {
        reconciliando = false;
        if (!dados || !dados.itens) return;
        var porId = {};
        dados.itens.forEach(function (item) { porId[String(item.id)] = item; });
        /* Remove linhas que já não existem no servidor (sem uid pendente). */
        Array.prototype.forEach.call(lista.querySelectorAll('[data-item]'), function (linha) {
          var info = dadosLinha(linha);
          if (!info.id) return;
          var servidor = porId[info.id];
          if (!servidor) { linha.remove(); return; }
          info.quantidade = servidor.quantidade;
          info.comprado = servidor.comprado;
          info.nome = servidor.nome;
          linha.setAttribute('data-nome', servidor.nome);
          gravarLinha(linha, info);
          pintarLinha(linha, info);
          delete porId[info.id];
        });
        /* Acrescenta o que existe no servidor e não está na página. */
        Object.keys(porId).forEach(function (id) {
          var item = porId[id];
          inserirLinha(criarLinha({
            nome: item.nome, quantidade: item.quantidade, comprado: item.comprado,
            id: item.id, meta: item.data_criacao
          }));
        });
        verificarVazio();
      })
      .catch(function () { reconciliando = false; });
  }

  /* -------------------------------------------------------------- eventos */

  raiz.addEventListener('click', function (evento) {
    var botao = evento.target.closest('[data-acao]');
    if (!botao || !raiz.contains(botao)) return;
    var elemento = linha(botao);
    if (!elemento) return;
    var acao = botao.getAttribute('data-acao');

    if (acao === 'alternar') { evento.preventDefault(); alternar(elemento); }
    else if (acao === 'qtd-mais') { evento.preventDefault(); alterarQuantidade(elemento, 1); }
    else if (acao === 'qtd-menos') { evento.preventDefault(); alterarQuantidade(elemento, -1); }
    else if (acao === 'editar') {
      /* Só preenche o modal; o Bootstrap abre-o a seguir. */
      prepararEdicao(elemento);
    }
    else if (acao === 'remover') {
      /* Nas linhas vindas do servidor o botão abre o modal de confirmação
         (data-bs-toggle). A remoção só acontece no submit desse modal; se
         apagássemos aqui, o "Sim, remover" seguinte já não encontrava a linha
         e o formulário era enviado a sério para /excluir_item_lista/<id>
         (404, porque o item já tinha sido apagado). Nas linhas criadas no
         telemóvel não há modal: remove-se na hora, como antes. */
      if (botao.hasAttribute('data-bs-toggle')) return;
      evento.preventDefault();
      remover(elemento);
    }
    else { return; }
  });

  /* Modal fechado sem guardar: esquece a linha que estava a ser editada. */
  if (modalEditar) {
    modalEditar.addEventListener('hidden.bs.modal', function () {
      itemEmEdicao = null;
    });
  }

  document.addEventListener('submit', function (evento) {
    var formulario = evento.target.closest('[data-acao-form]');
    if (!formulario) return;
    var acao = formulario.getAttribute('data-acao-form');
    if (acao === 'adicionar-item') {
      evento.preventDefault();
      adicionar(formulario);
    } else if (acao === 'remover-item') {
      /* O formulário está dentro do modal, por isso o item vem em data-item-id.
         O submit é sempre cancelado: se a linha já não existir (duplo toque ou
         outro separador), apenas fecha o modal — nunca navega para a rota
         antiga, que responderia 404. */
      evento.preventDefault();
      var id = formulario.getAttribute('data-item-id');
      var elemento = id ? lista.querySelector('[data-item][data-id="' + id + '"]') : null;
      var dialogo = formulario.closest('.modal');
      if (dialogo && window.bootstrap) window.bootstrap.Modal.getOrCreateInstance(dialogo).hide();
      if (elemento) remover(elemento);
    } else if (acao === 'editar-item') {
      /* O modal é partilhado por todas as linhas; o alvo foi guardado no
         clique do lápis. O submit é cancelado para não recarregar a página. */
      evento.preventDefault();
      var alvo = itemEmEdicao;
      itemEmEdicao = null;
      var entrada = formulario.querySelector('input[name="nome"]');
      var novoNome = (entrada.value || '').trim();
      var dialogoEdicao = formulario.closest('.modal');
      if (dialogoEdicao && window.bootstrap) {
        window.bootstrap.Modal.getOrCreateInstance(dialogoEdicao).hide();
      }
      if (!alvo || !raiz.contains(alvo) || !novoNome) return;
      if (novoNome !== dadosLinha(alvo).nome) renomear(alvo, novoNome);
    } else if (acao === 'limpar-lista') {
      evento.preventDefault();
      var modal = formulario.closest('.modal');
      if (modal && window.bootstrap) window.bootstrap.Modal.getOrCreateInstance(modal).hide();
      limparComprados(formulario);
    }
  });

  /* Fila sincronizou: o item criado ganha id real e a lista é reconciliada. */
  document.addEventListener('ch:fila:operacao', function (evento) {
    var detalhe = evento.detail || {};
    var operacao = detalhe.operacao || {};
    if (detalhe.falhou) return;
    if (operacao.metodo === 'POST' && detalhe.dados && detalhe.dados.item) {
      var elemento = lista.querySelector('[data-uid="' + operacao.uid + '"]');
      if (elemento) {
        var info = dadosLinha(elemento);
        info.id = detalhe.dados.item.id;
        gravarLinha(elemento, info);
        pintarLinha(elemento, info);
        elemento.querySelector('[data-meta-texto]').textContent = detalhe.dados.item.data_criacao;
      }
    }
  });

  document.addEventListener('ch:fila', function (evento) {
    var estado = evento.detail || {};
    if (estado.pendentes === 0 && estado.ultimaSincronizacao) reconciliar();
  });

  /* Botão "Limpar comprados" só aparece quando há itens comprados. */
  function ajustarBotaoLimpar() {
    var botao = raiz.querySelector('[data-botao-limpar]');
    if (!botao) return;
    botao.hidden = !lista.querySelector('.ch-item-concluido');
  }
  ajustarBotaoLimpar();
  document.addEventListener('ch:fila', ajustarBotaoLimpar);
  document.addEventListener('ch:fila:operacao', ajustarBotaoLimpar);

  /* A página pode ter vindo do cache do navegador (uso sem rede em http://IP):
     se não há nada por sincronizar, confirma o estado no servidor. */
  if (Fila.pendentes() === 0 && navigator.onLine !== false) reconciliar();
})();
