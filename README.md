# megasena-coletor

[![testes](https://github.com/fassampaio/megasena/actions/workflows/testes.yml/badge.svg)](https://github.com/fassampaio/megasena/actions/workflows/testes.yml)

Coleta os resultados oficiais da **Mega-Sena** diretamente da API da CAIXA
(`servicebus2.caixa.gov.br`) e grava tudo em um banco **SQLite**.

- Baixa **somente os concursos ausentes** no banco (inclusive buracos no meio da sequência).
- **Retoma** downloads interrompidos (Ctrl+C, queda de rede, processo encerrado): cada concurso é
  gravado numa transação própria, e a próxima execução continua de onde parou.
- **Valida** data e dezenas antes de gravar.
- Armazena as dezenas na **ordem de sorteio** e em **ordem crescente**, além do **rateio por faixa**.
- Preserva o **JSON original** de cada concurso, byte a byte, em `data/raw/megasena/`.

## Instalação

Requer Python 3.10+.

```bash
git clone https://github.com/fassampaio/megasena.git
cd megasena
python -m pip install -e .
```

## Uso

Rode a partir da raiz do projeto (os dados vão para `./data`):

```bash
megasena                   # baixa todos os concursos ausentes
megasena --ate 2500        # coleta só até o concurso 2500
megasena --refazer 2800    # baixa de novo e regrava o concurso 2800
megasena --validar         # confere banco x JSON originais, sem rede
megasena --help            # todas as opções
```

Se o comando `megasena` não for encontrado (pasta `Scripts` do Python fora do `PATH`,
comum no Python da Microsoft Store), use `python -m megasena` com os mesmos argumentos.

| Opção | Padrão | Descrição |
|---|---|---|
| `--db` | `data/megasena.db` | arquivo SQLite |
| `--raw` | `data/raw/megasena` | pasta dos JSON originais |
| `--pausa` | `0.5` | segundos entre requisições |
| `--timeout` | `30` | timeout HTTP (s) |
| `--tentativas` | `5` | tentativas por requisição (espera exponencial) |
| `--insecure` | — | desativa a verificação SSL (só se o certificado da CAIXA estiver quebrado) |

Códigos de saída: `0` sucesso, `1` houve falhas/problemas, `2` API inacessível, `130` interrompido.

## Estrutura dos dados

```
data/
├── megasena.db               # banco SQLite
├── megasena.log              # log das execuções
└── raw/megasena/000001.json  # JSON original de cada concurso
```

### Tabelas

**`concursos`** — um registro por concurso
`numero` (PK), `data_sorteio` (ISO `AAAA-MM-DD`), `acumulado`, `valor_arrecadado`,
`valor_estimado_proximo`, `local_sorteio`, `municipio_uf`, `arquivo_raw`, `json_sha256`, `coletado_em`.

**`dezenas`** — seis registros por concurso
`concurso`, `dezena`, `posicao_crescente` (1–6), `posicao_sorteio` (1–6, `NULL` se a CAIXA não publicou a ordem).

**`rateio`** — prêmio por faixa
`concurso`, `faixa`, `descricao`, `ganhadores`, `valor_premio`.

**`coleta_log`** — situação da coleta de cada concurso
`concurso`, `status` (`ok`/`erro`), `tentativas`, `ultimo_erro`, `avisos`, `atualizado_em`.

### Exemplos de consulta

```sql
-- Dezenas em ordem de sorteio do último concurso
SELECT dezena FROM dezenas
WHERE concurso = (SELECT MAX(numero) FROM concursos)
ORDER BY posicao_sorteio;

-- Frequência de cada dezena
SELECT dezena, COUNT(*) AS vezes FROM dezenas GROUP BY dezena ORDER BY vezes DESC;
```

## Validações

Um concurso só é gravado se:

- o `numero` devolvido for o número pedido e `tipoJogo` for `MEGA_SENA`;
- a data for válida (`dd/mm/aaaa`), não futura, não anterior a 11/03/1996, e estiver
  entre as datas dos concursos vizinhos já gravados;
- houver exatamente 6 dezenas, inteiras, entre 1 e 60, sem repetição;
- a ordem de sorteio (quando publicada) tiver as mesmas dezenas da lista crescente;
- o rateio não tiver faixas repetidas nem valores negativos.

Concursos rejeitados ficam registrados em `coleta_log` e são tentados de novo na próxima execução.

## Testes

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Os testes não acessam a rede (a API é simulada).

## Licença

[MIT](LICENSE).

## Aviso

Projeto independente, sem vínculo com a CAIXA. A API usada é a mesma do portal público de
loterias e pode mudar sem aviso.
