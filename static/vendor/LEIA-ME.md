# Dependências de front-end empacotadas

Estes ficheiros são servidos pelo próprio Flask (pasta `static/`), para que o
CheckHouse funcione **sem acesso à internet** — importante numa Home Lab e em
redes locais isoladas.

| Ficheiro | Versão | Licença | Origem |
| --- | --- | --- | --- |
| `bootstrap/bootstrap.min.css` | 5.3.0 | MIT | https://getbootstrap.com |
| `bootstrap/bootstrap.bundle.min.js` | 5.3.0 | MIT | https://getbootstrap.com |
| `bootstrap-icons/bootstrap-icons.css` + `fonts/` | 1.11.1 | MIT | https://icons.getbootstrap.com |

## Atualizar

```bash
cd static/vendor
curl -sSLO https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css
curl -sSLO https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js
cd bootstrap-icons
curl -sSL -o bootstrap-icons.css https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css
curl -sSL -o fonts/bootstrap-icons.woff2 https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/fonts/bootstrap-icons.woff2
curl -sSL -o fonts/bootstrap-icons.woff  https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/fonts/bootstrap-icons.woff
```

O `templates/base.html` tem uma rede de segurança: se algum destes ficheiros
faltar (instalação incompleta), o Bootstrap e os ícones são carregados do CDN
automaticamente, de forma a página não ficar sem estilo.
