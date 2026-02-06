from pdfminer.high_level import extract_text
from pprint import pprint
import re
import sys

try:
    texto = extract_text(r'Requisicao.pdf')
except FileNotFoundError:
    print("Erro: Arquivo 'Requisicao.pdf' não encontrado.")
    sys.exit(1)
except Exception as e:
    print(f"Erro ao extrair texto do PDF: {e}")
    sys.exit(1)

try:
    emails = re.findall(r'((?:bom dia|boa tarde).+?visualizou)', texto, flags=re.I|re.S)
except Exception as e:
    print(f"Erro ao processar regex: {e}")
    sys.exit(1)

for email in emails:
    pprint(email)
