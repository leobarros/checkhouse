1. Requisitos Funcionais (O que o sistema DEVE fazer)

O foco agora é ser um CRUD eficiente e focado em resolver a confusão entre as duas (ou mais) casas.

    Gerenciamento de Locais (Casas): O sistema deve permitir criar, editar e excluir diferentes "Locais" (Ex: Casa Principal, Casa de Praia, Sítio).

    CRUD de Produtos: O usuário deve poder adicionar, visualizar, editar e excluir itens. Cada item deve obrigatoriamente ter: Nome, Quantidade, Data de Validade e estar associado a um Local específico.

    Visão/Filtro por Casa: A tela inicial deve permitir alternar facilmente a visualização entre "Casa 1" e "Casa 2", mostrando apenas o estoque do local selecionado para evitar confusão.

    Painel de Validades (Dashboard): Uma visualização rápida (lista ou tabela) que ordene os produtos pela data de vencimento, destacando com cores (ex: vermelho para vencido, amarelo para próximo de vencer, verde para ok).

    Busca Global: Uma barra de pesquisa onde o usuário digita "Arroz" e o sistema diz em qual casa tem e a quantidade.

2. Requisitos Não Funcionais (Como o sistema DEVE ser)

Aqui entram as especificações para garantir que rode perfeitamente no seu Home Lab com Debian 13 e no celular.

    Design Responsivo (Mobile-First): Como a aplicação é web, a interface deve se adaptar perfeitamente a telas de celulares, parecendo um aplicativo nativo quando aberta no navegador do smartphone (podendo até ser um PWA - Progressive Web App, para adicionar um ícone na tela inicial do celular).

    Containerização (Docker): A aplicação deve ser totalmente empacotada em containers Docker. Deve possuir um arquivo docker-compose.yml para subir toda a aplicação com um único comando (docker compose up -d).

    Portabilidade e Persistência de Dados: O banco de dados (ex: SQLite ou um container PostgreSQL) deve usar Docker Volumes mapeados para um diretório local no Debian 13. Isso garante que, se o usuário precisar formatar o servidor ou migrar de máquina, basta copiar a pasta e rodar o docker compose novamente.

    Baixo Consumo de Recursos (Lightweight): Como vai rodar em um Home Lab (que pode ser um Raspberry Pi, um mini PC ou um servidor antigo), a stack de tecnologia escolhida deve consumir pouca memória RAM e CPU.

    Fácil Instalação: O processo de deploy não deve exigir a instalação de dependências no host (Debian 13), dependendo unicamente do Docker e Docker Compose.                       