#!/bin/bash

# Definição de cores para o terminal
VERDE='\033[0;32m'
AMARELO='\033[1;33m'
VERMELHO='\033[0;31m'
NC='\033[0m' # Sem Cor

echo -e "${AMARELO}A iniciar a instalação/atualização do CheckHouse...${NC}"

# Verifica se o ficheiro docker-compose.yml existe no diretório atual
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${VERMELHO}Erro: Ficheiro docker-compose.yml não encontrado.${NC}"
    echo "Navegue até à pasta do projeto CheckHouse antes de executar este script."
    exit 1
fi

# Descarrega a imagem mais recente do repositório
echo "A descarregar a versão mais recente da imagem..."
docker compose pull

# Inicia ou atualiza o contentor em segundo plano
echo "A iniciar os contentores..."
docker compose up -d

# Verifica se o comando anterior foi bem sucedido
if [ $? -eq 0 ]; then
    echo -e "${VERDE}✨ CheckHouse foi iniciado com sucesso!${NC}"
    echo "Pode aceder à aplicação através do endereço http://<IP-DO-SEU-SERVIDOR>:5000"
else
    echo -e "${VERMELHO}Ocorreu um erro ao tentar iniciar o projeto. Verifique os logs com 'docker compose logs'.${NC}"
fi