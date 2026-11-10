"""Cliente HTTP da API oficial de loterias da CAIXA."""
from __future__ import annotations

import json
import logging
import time

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://servicebus2.caixa.gov.br/portaldeloterias/api/megasena"

# A API às vezes recusa clientes sem cabeçalhos de navegador.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Origin": "https://loterias.caixa.gov.br",
    "Referer": "https://loterias.caixa.gov.br/",
}

STATUS_REPETIVEIS = {403, 408, 429, 500, 502, 503, 504}


class ErroAPI(RuntimeError):
    """Falha definitiva ao consultar a API."""


class ClienteCaixa:
    def __init__(self, timeout: float = 30, tentativas: int = 5,
                 backoff: float = 2.0, verificar_ssl: bool = True):
        self.timeout = timeout
        self.tentativas = max(1, tentativas)
        self.backoff = backoff
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.verify = verificar_ssl
        if not verificar_ssl:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _get(self, url: str) -> bytes:
        """GET com novas tentativas. Devolve os bytes originais da resposta."""
        ultimo_erro = "?"
        for tentativa in range(1, self.tentativas + 1):
            try:
                r = self.session.get(url, timeout=self.timeout)
                if r.status_code == 200:
                    json.loads(r.content)  # garante que é JSON antes de aceitar
                    return r.content
                if r.status_code not in STATUS_REPETIVEIS:
                    raise ErroAPI(f"HTTP {r.status_code} em {url}")
                ultimo_erro = f"HTTP {r.status_code}"
            except requests.exceptions.SSLError as e:
                raise ErroAPI(
                    f"falha de certificado SSL ({e}); se persistir, use --insecure"
                ) from e
            except (requests.ConnectionError, requests.Timeout) as e:
                ultimo_erro = f"{type(e).__name__}: {e}"
            except ValueError:
                ultimo_erro = "resposta não é JSON válido"

            if tentativa < self.tentativas:
                espera = self.backoff ** tentativa
                log.warning("%s (tentativa %d/%d) — aguardando %.0fs",
                            ultimo_erro, tentativa, self.tentativas, espera)
                time.sleep(espera)
        raise ErroAPI(f"{ultimo_erro} após {self.tentativas} tentativas em {url}")

    def ultimo_concurso(self) -> int:
        dados = json.loads(self._get(BASE_URL))
        numero = dados.get("numero")
        if not isinstance(numero, int) or numero < 1:
            raise ErroAPI(f"número do último concurso inválido: {numero!r}")
        return numero

    def concurso(self, numero: int) -> bytes:
        return self._get(f"{BASE_URL}/{numero}")
