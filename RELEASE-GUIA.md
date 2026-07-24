# 🚀 Guia de Release - ISTools v1.5.1

Este documento descreve o processo oficial de preparação, teste e publicação de uma nova versão do plugin ISTools.

## 1. Verificações de Pré-venda
Antes de gerar o pacote final, confirme:
- [ ] O `version` no `metadata.txt` está correto (ex: `1.5.1`).
- [ ] O posto do autor está atualizado como `2° Sgt`.
- [ ] O `changelog` no `metadata.txt` reflete todas as melhorias da versão.
- [ ] Os ícones novos foram adicionados em `resources.qrc`.

## 2. Tradução e Recursos
O plugin utiliza um sistema híbrido:
1. **i18n/*.qm**: Para traduções nativas do QGIS (Qt).
2. **translations/*.py**: Para o sistema de tradução inteligente (Dicionário).

Se houver novas ferramentas, atualize o `istools/translations/dictionary.py`.

## 3. Empacotamento Oficial
O ISTools utiliza um script Python especializado que garante que apenas arquivos de runtime sejam incluídos, mantendo scripts de desenvolvimento e caches fora do ZIP.

**Comando:**
```bash
python build_qgis_package.py
```

**Resultado:**
Um arquivo `istools-<versão>.zip` será gerado na raiz do diretório de desenvolvimento do plugin.

## 4. Smoke Test (Teste de Fumaça)
Antes de subir para o repositório oficial, instale o ZIP gerado em uma instância limpa do QGIS:
1. Plugins > Gerenciar e Instalar Plugins > Instalar a partir de ZIP.
2. Verifique se o menu **ISTools** aparece.
3. Teste as ferramentas principais:
   - **Carregar Banco Shape** (deve criar árvore organizada).
   - **Gerenciador de Banco** (deve abrir sem erro de importação).
   - **Conversor EDGV** (Processing Toolbox).

## 5. Publicação
1. **GitHub:**
   - Faça commit de todas as alterações (incluindo diretório `scripts/`).
   - Crie uma Tag `v1.5.1`.
   - Crie uma Release anexando o arquivo ZIP gerado.
2. **QGIS Plugin Repository:**
   - Acesse [plugins.qgis.org](https://plugins.qgis.org/).
   - Faça upload do mesmo arquivo ZIP.
   - Aguarde a validação do repositório.

---
*Atualizado em: 26 de Março de 2026*
