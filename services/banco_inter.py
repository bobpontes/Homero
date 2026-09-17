import os
from pathlib import Path
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class BancoInter:

    def __init__(self):
        self.client_id = os.getenv("INTER_CLIENT_ID")
        self.client_secret = os.getenv("INTER_CLIENT_SECRET")

        certificado_path = os.getenv("INTER_CERTIFICATE_PATH")
        chave_privada_path = os.getenv("INTER_PRIVATE_KEY_PATH")

        self.certificado = BASE_DIR / certificado_path
        self.chave_privada = BASE_DIR / chave_privada_path

    def autenticar(self):

        request_body = (
            f"client_id={self.client_id}"
            f"&client_secret={self.client_secret}"
            "&scope=extrato.read"
            "&grant_type=client_credentials"
        )

        response = requests.post(
            "https://cdpj.partners.bancointer.com.br/oauth/v2/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded"
            },
            cert=(
                str(self.certificado),
                str(self.chave_privada)
            ),
            data=request_body
        )

        response.raise_for_status()

        return response.json().get("access_token")

    def consultar_extrato(self, data_inicio, data_fim):
        token = self.autenticar()

        parametros = {
            "dataInicio": data_inicio,
            "dataFim": data_fim
        }

        cabecalhos = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "Application/json"
        }

        response = requests.get(
            "https://cdpj.partners.bancointer.com.br/banking/v2/extrato",
            params=parametros,
            headers=cabecalhos,
            cert=(
                str(self.certificado),
                str(self.chave_privada)
            )
        )

        response.raise_for_status()

        return response.json()

