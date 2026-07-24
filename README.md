# 🛠️ Plugin ISTools para QGIS

<div align="center">

<img src="icons/icon_istools.png" width="150">

**Suíte Completa de Geoinformação: Vetorização Avançada, PostGIS e ETL EDGV 3.0**

<div align="center">
  
🌐 **[🚀 VISITE NOSSO SITE OFICIAL - CLIQUE AQUI! 🚀](https://irlansouza93.github.io/istools-website/)**

*Descubra mais plugins, tutoriais e recursos exclusivos para QGIS!*

</div>

[![Versão QGIS](https://img.shields.io/badge/QGIS-3.10+-brightgreen.svg)](https://qgis.org)
[![Versão](https://img.shields.io/badge/Versão-1.5.1-blue.svg)](https://github.com/irlansouza93/istools)
[![Licença](https://img.shields.io/badge/Licença-GPL--3.0-red.svg)](LICENSE)
[![Linguagem](https://img.shields.io/badge/Linguagem-Python-yellow.svg)](https://python.org)

*Aprimore seu fluxo de trabalho no QGIS com ferramentas profissionais de edição e gerenciamento de bancos de dados.*

</div>

---

## 🌟 Visão Geral

O **ISTools** evoluiu! O que antes era apenas um conjunto de ferramentas de vetorização, agora é uma **Suíte de Geoinformação completa**. Desenvolvido para o QGIS, o plugin visa otimizar a produtividade de cartógrafos, analistas e administradores de dados, integrando desde a edição geométrica fina até o gerenciamento complexo de bancos de dados PostGIS.

Sua arquitetura moderna permite lidar com grandes volumes de dados espaciais e fluxos de trabalho que exigem precisão e performance, mantendo uma interface intuitiva e nativa.

---

## ✨ Recursos Principais

### 📐 Suíte de Vetorização (Core)
Ferramentas ágeis para manipulação de geometrias:
- **🔗 Estender Linhas**: Prolonga feições lineares até o alvo mais próximo de forma inteligente (Snapping).
- **📐 Gerador de Polígonos**: Cria áreas a partir de nuvens de pontos com validação rigorosa.
- **📍 Ponto na Superfície**: Garante a criação de centroides representativos dentro de polígonos complexos.
- **✂️ Interseção de Linhas**: Automatiza a criação de vértices em cruzamentos para manter a topologia íntegra.
- **Simplificador Suave**: Reduz vértices de linhas selecionadas com tolerância fina e operação reversível (Ctrl+Z).

### 🗄️ Gerenciamento de Banco de Dados (PostGIS)
- **⚡ Gerenciador PostGIS**: Interface unificada para execução rápida de comandos SQL, manutenção de tabelas e análise espacial direta.
- **📥 Importador de Bases (SHP to DB)**: Ferramenta otimizada para carregamento em massa de Shapefiles diretamente para o PostGIS com mapeamento assistido.

### ⚡ Pipelines de Processamento (ETL)
- **🏗️ ETL EDGV 3.0**: Módulo especializado para converter bases legadas para o padrão EDGV 3.0 (Especificação de Dados Geoespaciais Vetoriais do Exército Brasileiro).

---

## 📥 Instalação

1. Abra o **QGIS**.
2. Vá em **Complementos** > **Gerenciar e Instalar Complementos**.
3. Procure por **ISTools** ou instale a partir do arquivo ZIP da [Release](https://github.com/irlansouza93/istools/releases).

---

## 📋 Requisitos

- 🖥️ **QGIS**: Versão 3.10 ou superior.
- 🐍 **Python**: 3.7+ (Padrão do QGIS moderno).
- 🗄️ **PostGIS**: Necessário para os módulos de banco e ETL.

---

## 🗺️ Contribuição

Contribuições são fundamentais para o crescimento do ISTools! Se você encontrou um erro ou tem uma sugestão estratégica:
1. Faça um **Fork** do projeto oficial.
2. Crie uma **Branch** para sua modificação (`git checkout -b feature/nova_ferramenta`).
3. Abra um **Pull Request** detalhando sua alteração.

---

## 📄 Licença

Este projeto está licenciado sob a licença **GPL-v3.0** - consulte o arquivo [LICENSE](LICENSE) para total transparência.

---

<div align="center">

**Desenvolvido por Irlan Souza**
*2° Sgt do Exército Brasileiro*

[GitHub](https://github.com/irlansouza93) | [LinkedIn](https://www.linkedin.com/in/irlansouza93/)

</div>
