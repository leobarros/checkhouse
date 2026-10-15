/* ==========================================================================
   CheckHouse — indicador de estado da fila offline
   --------------------------------------------------------------------------
   Mostra, em qualquer página: quantas operações estão à espera de rede, se a
   sincronização está a correr, se a sessão expirou e avisos pontuais.
   Vive num único sítio (barra inferior) para não haver indicadores diferentes
   em cada ecrã.
   ========================================================================== */
(function () {
  'use strict';

  var Fila = window.CheckHouseFila;
  if (!Fila) return;

  var barra = null;
  var textoBarra = null;
  var botaoSincronizar = null;
  var ligacaoSessao = null;
  var caixaAvisos = null;
  var esconderEm = null;
  var sincronizouAlgumaVez = false;

  function construir() {
    barra = document.createElement('div');
    barra.className = 'ch-barra-fila';
    barra.setAttribute('role', 'status');
    barra.setAttribute('aria-live', 'polite');
    barra.hidden = true;
    barra.innerHTML =
      '<span class="ch-barra-fila-texto" data-fila-texto></span>' +
      '<a class="ch-barra-fila-link" data-fila-sessao hidden>Entrar novamente</a>' +
      '<button type="button" class="btn btn-sm btn-light fw-semibold" data-fila-sincronizar>Sincronizar</button>';
    document.body.appendChild(barra);

    textoBarra = barra.querySelector('[data-fila-texto]');
    botaoSincronizar = barra.querySelector('[data-fila-sincronizar]');
    ligacaoSessao = barra.querySelector('[data-fila-sessao]');

    botaoSincronizar.addEventListener('click', function () {
      botaoSincronizar.disabled = true;
      textoBarra.textContent = 'A sincronizar…';
      Promise.resolve(Fila.processar()).then(function () {
        botaoSincronizar.disabled = false;
      });
    });

    caixaAvisos = document.createElement('div');
    caixaAvisos.className = 'ch-avisos';
    caixaAvisos.setAttribute('aria-live', 'polite');
    document.body.appendChild(caixaAvisos);
  }

  function mostrar(mensagem, tipo, duracao) {
    if (!caixaAvisos) construir();
    var aviso = document.createElement('div');
    aviso.className = 'ch-aviso ch-aviso--' + (tipo || 'info');
    aviso.setAttribute('role', 'status');
    aviso.textContent = mensagem;
    caixaAvisos.appendChild(aviso);
    var tempo = duracao || (tipo === 'erro' ? 7000 : 3500);
    window.setTimeout(function () {
      aviso.classList.add('ch-aviso--saindo');
      window.setTimeout(function () {
        if (aviso.parentNode) aviso.parentNode.removeChild(aviso);
      }, 300);
    }, tempo);
  }

  function pintar(estado) {
    if (!barra) construir();

    window.clearTimeout(esconderEm);

    if (estado.sessaoExpirada) {
      barra.hidden = false;
      barra.classList.add('ch-barra-fila--alerta');
      textoBarra.textContent = 'Sessão expirada · ' + estado.pendentes + ' guardada(s)';
      ligacaoSessao.hidden = false;
      ligacaoSessao.href = '/login?next=' + encodeURIComponent(window.location.pathname);
      botaoSincronizar.hidden = true;
      return;
    }

    ligacaoSessao.hidden = true;
    botaoSincronizar.hidden = false;

    if (estado.pendentes === 0) {
      barra.classList.remove('ch-barra-fila--alerta');
      if (sincronizouAlgumaVez) {
        barra.hidden = false;
        barra.classList.add('ch-barra-fila--ok');
        textoBarra.textContent = 'Tudo sincronizado';
        botaoSincronizar.hidden = true;
        esconderEm = window.setTimeout(function () {
          barra.hidden = true;
          barra.classList.remove('ch-barra-fila--ok');
        }, 2500);
      } else {
        barra.hidden = true;
      }
      return;
    }

    sincronizouAlgumaVez = true;
    barra.hidden = false;
    barra.classList.remove('ch-barra-fila--ok');
    barra.classList.toggle('ch-barra-fila--alerta', !estado.online);
    if (estado.processando) {
      textoBarra.textContent = 'A sincronizar ' + estado.pendentes + '…';
      botaoSincronizar.hidden = true;
    } else if (!estado.online) {
      textoBarra.textContent = 'Sem rede · ' + estado.pendentes + ' guardada(s)';
      botaoSincronizar.hidden = true;
    } else {
      textoBarra.textContent = estado.pendentes + ' por sincronizar';
      botaoSincronizar.hidden = false;
    }
  }

  document.addEventListener('ch:fila', function (evento) {
    pintar(evento.detail || Fila.estado());
  });

  window.CheckHouseEstado = {
    mostrarAviso: mostrar,
    estado: function () { return Fila.estado(); }
  };

  pintar(Fila.estado());
})();
