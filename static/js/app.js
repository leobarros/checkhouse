/* ==========================================================================
   CheckHouse — comportamento partilhado de interface
   - Tema claro/escuro (persistente, com opção "sistema")
   - Foco automático só em desktop (evita abrir o teclado no telemóvel)
   - Foco correto ao abrir modais
   - Reposição da posição de scroll e proteção contra submissões duplicadas
   Nenhuma função aqui é obrigatória para o servidor: são melhorias de UX.
   ========================================================================== */
(function () {
  'use strict';

  var CHAVE_TEMA = 'temaCheckHouse';
  var COOKIE_TEMA = 'ch_tema';
  var CHAVE_SCROLL = 'ch:scroll';
  var raiz = document.documentElement;
  var mediaEscuro = window.matchMedia('(prefers-color-scheme: dark)');

  /* ------------------------------------------------------------------ tema */
  function preferenciaValida(valor) {
    return valor === 'light' || valor === 'dark' || valor === 'auto' ? valor : null;
  }

  function lerCookie(nome) {
    var partes = document.cookie ? document.cookie.split('; ') : [];
    for (var i = 0; i < partes.length; i++) {
      var pos = partes[i].indexOf('=');
      if (pos < 1 || partes[i].slice(0, pos) !== nome) continue;
      try {
        return decodeURIComponent(partes[i].slice(pos + 1));
      } catch (e) {
        return null;
      }
    }
    return null;
  }

  function lerPreferencia() {
    var valor = null;
    try {
      valor = window.localStorage.getItem(CHAVE_TEMA);
    } catch (e) {
      valor = null;
    }
    valor = preferenciaValida(valor);
    if (valor) return valor;
    /* Reserva: o localStorage pode estar indisponível no telemóvel. */
    return preferenciaValida(lerCookie(COOKIE_TEMA)) || 'auto';
  }

  function gravarPreferencia(valor) {
    try {
      if (valor === 'auto') {
        window.localStorage.removeItem(CHAVE_TEMA);
      } else {
        window.localStorage.setItem(CHAVE_TEMA, valor);
      }
    } catch (e) {
      /* modo privado: o tema continua a funcionar apenas nesta sessão */
    }
    /* O cookie é lido pelo servidor (data-bs-theme) e pelo arranque da página,
       por isso o tema sobrevive mesmo quando o localStorage está bloqueado. */
    try {
      document.cookie =
        COOKIE_TEMA + '=' + encodeURIComponent(valor) +
        '; path=/; max-age=31536000; SameSite=Lax';
    } catch (e) {
      /* sem cookies: fica só o localStorage */
    }
  }

  function temaEfetivo(preferencia) {
    if (preferencia === 'light' || preferencia === 'dark') return preferencia;
    return mediaEscuro.matches ? 'dark' : 'light';
  }

  function corDaBarra() {
    var barra = document.querySelector('.ch-navbar');
    if (!barra) return null;
    var cor = window.getComputedStyle(barra).backgroundColor;
    return cor && cor !== 'rgba(0, 0, 0, 0)' ? cor : null;
  }

  function pintarControlos(preferencia, efetivo) {
    /* Botão único: mostra a ação disponível (não o estado atual). */
    var acaoRotulo = efetivo === 'dark' ? 'Modo claro' : 'Modo escuro';
    var acaoIcone = efetivo === 'dark' ? 'bi-sun' : 'bi-moon-stars';

    document.querySelectorAll('[data-tema-rotulo]').forEach(function (el) {
      el.textContent = acaoRotulo;
    });
    document.querySelectorAll('[data-tema-icone]').forEach(function (el) {
      el.classList.remove('bi-sun', 'bi-moon-stars');
      el.classList.add(acaoIcone);
    });
    document.querySelectorAll('[data-tema-alternar]').forEach(function (el) {
      el.setAttribute('aria-label', acaoRotulo);
      el.setAttribute('title', acaoRotulo);
    });

    /* Grupo de opções em Configurações. */
    document.querySelectorAll('[data-tema-valor]').forEach(function (el) {
      var ativo = el.getAttribute('data-tema-valor') === preferencia;
      el.classList.toggle('active', ativo);
      el.setAttribute('aria-pressed', ativo ? 'true' : 'false');
    });
  }

  function aplicarTema(preferencia) {
    var efetivo = temaEfetivo(preferencia);
    raiz.setAttribute('data-bs-theme', efetivo);
    raiz.setAttribute('data-ch-tema', preferencia);
    pintarControlos(preferencia, efetivo);

    var meta = document.getElementById('metaCorTema');
    if (meta) {
      meta.setAttribute('content', corDaBarra() || (efetivo === 'dark' ? '#343a40' : '#0d6efd'));
    }
    return efetivo;
  }

  /* Compatibilidade com o código existente (onclick="alternarTema()"). */
  window.alternarTema = function () {
    var efetivo = temaEfetivo(lerPreferencia());
    var novo = efetivo === 'dark' ? 'light' : 'dark';
    /* Gravar é essencial: sem isto o tema mudava só na página atual. */
    gravarPreferencia(novo);
    return aplicarTema(novo);
  };

  window.definirTema = function (valor) {
    gravarPreferencia(valor);
    return aplicarTema(valor);
  };

  window.temaAtual = function () {
    return temaEfetivo(lerPreferencia());
  };

  /* Delegação de eventos: qualquer botão com data-tema-* funciona. */
  document.addEventListener('click', function (evento) {
    var alternar = evento.target.closest('[data-tema-alternar]');
    if (alternar) {
      evento.preventDefault();
      window.alternarTema();
      return;
    }
    var opcao = evento.target.closest('[data-tema-valor]');
    if (opcao) {
      evento.preventDefault();
      window.definirTema(opcao.getAttribute('data-tema-valor'));
    }
  });

  /* Segue o sistema enquanto a preferência for "automático". */
  var aoMudarSistema = function () {
    if (lerPreferencia() === 'auto') aplicarTema('auto');
  };
  if (typeof mediaEscuro.addEventListener === 'function') {
    mediaEscuro.addEventListener('change', aoMudarSistema);
  } else if (typeof mediaEscuro.addListener === 'function') {
    mediaEscuro.addListener(aoMudarSistema);
  }

  /* Mantém o tema igual em todos os separadores abertos. */
  window.addEventListener('storage', function (evento) {
    if (evento.key === CHAVE_TEMA) aplicarTema(lerPreferencia());
  });

  /* -------------------------------------------------- foco e acessibilidade */
  function ecraGrande() {
    return window.innerWidth >= 768 && window.matchMedia('(pointer: fine)').matches;
  }

  /* autofocus="true" em mobile abre o teclado e esconde o conteúdo: só
     aplicamos o foco em desktop. */
  function focoInicial() {
    if (!ecraGrande()) return;
    var alvo = document.querySelector('[data-autofocus]');
    if (alvo) alvo.focus();
  }

  /* Inputs dentro de modais não podem ter autofocus no HTML (o foco iria para
     um elemento invisível); focamos quando o modal aparece. */
  document.querySelectorAll('.modal').forEach(function (modal) {
    modal.addEventListener('shown.bs.modal', function () {
      var campo = modal.querySelector('[data-autofocus-modal]');
      if (campo) {
        campo.focus();
        if (typeof campo.select === 'function') campo.select();
      }
    });
  });

  /* ------------------------------------------------------- scroll e submit */
  if ('scrollRestoration' in window.history) {
    window.history.scrollRestoration = 'manual';
  }

  function guardarPosicao() {
    try {
      window.sessionStorage.setItem(
        CHAVE_SCROLL,
        JSON.stringify({ p: window.location.pathname, y: window.scrollY })
      );
    } catch (e) {
      /* sem sessionStorage: apenas não restauramos a posição */
    }
  }

  document.addEventListener('submit', guardarPosicao, true);

  document.addEventListener(
    'click',
    function (evento) {
      var link = evento.target.closest('a[href]');
      if (!link) return;
      var href = link.getAttribute('href');
      if (!href || href.charAt(0) === '#' || link.hasAttribute('data-bs-toggle')) return;
      guardarPosicao();
    },
    true
  );

  function restaurarPosicao() {
    var dados;
    try {
      dados = JSON.parse(window.sessionStorage.getItem(CHAVE_SCROLL) || 'null');
      window.sessionStorage.removeItem(CHAVE_SCROLL);
    } catch (e) {
      return;
    }
    if (dados && dados.p === window.location.pathname && dados.y > 0) {
      window.requestAnimationFrame(function () {
        window.scrollTo(0, dados.y);
      });
    }
  }

  /* Evita duplicar itens quando o botão é tocado duas vezes seguidas.
     Só se aplica a envios que navegam de facto. Quando outro script trata do
     envio (evento.preventDefault, como a fila offline da Lista e da Despensa),
     a página fica na mesma e o botão tem de continuar utilizável — caso
     contrário ficava desabilitado depois do primeiro item. O preventDefault
     pode ser chamado por um listener registado depois deste, por isso a
     verificação é feita dentro do setTimeout, já depois de todos correrem. */
  document.addEventListener('submit', function (evento) {
    var formulario = evento.target;
    if (formulario.hasAttribute('data-ch-sem-trava')) return;
    window.setTimeout(function () {
      if (evento.defaultPrevented) return;
      var botao = formulario.querySelector('button[type="submit"], input[type="submit"]');
      if (botao && !botao.disabled) {
        botao.disabled = true;
        botao.setAttribute('aria-busy', 'true');
        formulario.setAttribute('aria-busy', 'true');
      }
    }, 0);
  });

  window.addEventListener('pageshow', function (evento) {
    /* Ao voltar com o botão “atrás”, o browser pode restaurar a página tal
       como estava (bfcache) sem correr os scripts outra vez. Reaplicamos o
       tema para a página antiga não reaparecer clara. */
    aplicarTema(lerPreferencia());

    document
      .querySelectorAll('form[aria-busy="true"] button[type="submit"][disabled], input[type="submit"][disabled]')
      .forEach(function (botao) {
        botao.disabled = false;
        botao.removeAttribute('aria-busy');
        var formulario = botao.closest('form');
        if (formulario) formulario.removeAttribute('aria-busy');
      });
  });

  /* --------------------------------------------------------------- arranque */
  function iniciar() {
    var preferencia = lerPreferencia();
    aplicarTema(preferencia);

    /* Quem já tinha o tema guardado só no localStorage passa a ter também o
       cookie, para o servidor o poder aplicar em qualquer página. */
    if (lerCookie(COOKIE_TEMA) !== preferencia) gravarPreferencia(preferencia);

    /* Datalists grandes: o browser filtra sozinho; nada a fazer. */

    var ano = document.getElementById('anoAtual');
    if (ano) ano.textContent = String(new Date().getFullYear());

    focoInicial();
    restaurarPosicao();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }
})();
