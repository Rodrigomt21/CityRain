#!/usr/bin/env python3
"""
mock_backend.py — Simula o endpoint de upload do backend do CityRain, só pra
validar o uploader.py ponta-a-ponta antes de ter a URL/contrato reais do
Guilherme. Usa só a biblioteca padrão (http.server), roda em Python 3.6.

Uso: python3 mock_backend.py [porta]
Aceita qualquer POST multipart em /upload e responde 201, logando o que
recebeu (nome do arquivo de imagem + o JSON de metadata).
"""

import cgi
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers["Content-Type"]},
        )

        nome_imagem = form["image"].filename if "image" in form else "(sem campo image)"
        tamanho_imagem = len(form["image"].value) if "image" in form else 0
        metadata = form.getvalue("metadata", "(sem campo metadata)")

        print(f"[mock] recebido: imagem={nome_imagem} ({tamanho_imagem} bytes) metadata={metadata}")

        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

    def log_message(self, formato, *args):
        pass  # log próprio acima já basta, evita duplicar no stdout


def main():
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    servidor = HTTPServer(("127.0.0.1", porta), Handler)
    print(f"[mock] escutando em http://127.0.0.1:{porta}/upload (Ctrl+C pra parar)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n[mock] encerrado.")


if __name__ == "__main__":
    main()
