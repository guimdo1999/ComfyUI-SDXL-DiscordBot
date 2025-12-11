import configparser
import os

print(f"Pasta atual de trabalho: {os.getcwd()}")
print(f"O arquivo config.properties existe aqui? {os.path.exists('config.properties')}")

config = configparser.ConfigParser()
# Tenta ler
files_read = config.read('config.properties', encoding='utf-8')

print(f"Arquivos lidos com sucesso: {files_read}")

if not files_read:
    print("ERRO: O Python não conseguiu abrir o arquivo. Verifique o nome/caminho.")
else:
    print("\nSeções encontradas:")
    for section in config.sections():
        print(f"[{section}]")
    
    if 'CHECKPOINTS' in config:
        print("\nSUCESSO: Seção CHECKPOINTS encontrada!")
        print(f"Keys: {list(config['CHECKPOINTS'].keys())}")
    else:
        print("\nERRO CRÍTICO: O arquivo foi lido, mas a seção [CHECKPOINTS] NÃO APARECEU.")
        print("Verifique se você salvou o arquivo e se não há erros de sintaxe nas linhas anteriores.")