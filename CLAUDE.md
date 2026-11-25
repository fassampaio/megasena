# Projeto megasena-coletor

## Ponto único de atualização

Quando o usuário pedir para **atualizar** (base, sorteios, dashboards, análises, "tudo"):

1. Rode na raiz: `PYTHONIOENCODING=utf-8 python atualizar.py` (timeout longo; a validação leva ~40 s).
   Ele coleta, valida, roda cada script de `analises/` e lista os painéis a republicar.
2. Para cada pendência listada (ou em `data/atualizacao.json` → `paineis_pendentes`):
   - envie o arquivo como asset: Artifact `publish` com `url` do painel, `asset: true`, `file_path` do arquivo;
   - atualize o dataset correspondente com ArtifactData (`collection: "datasets"`, `doc_id` = nome do
     dataset, `update` com `source.url` = novo `/_blob/<id>` e `updated: {at, by: "Claude"}`,
     sempre com `if_version` lido antes).
3. Depois de publicar tudo: `python atualizar.py --publicado`.
4. Informe: concursos novos (último concurso), etapas com aviso/erro e o que foi republicado.

Para registrar uma análise nova: script em `analises/` (lê `MEGASENA_DB`, grava em `MEGASENA_SAIDA`).
Para um painel novo: entrada em `paineis.json` (url + datasets → arquivos).
