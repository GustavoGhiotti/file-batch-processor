# Validação

Execução local em 16/09/2026, no Windows com Python 3.14.

| Verificação | Resultado |
| --- | --- |
| `python -m unittest discover -s tests -v` | 14 testes aprovados |
| `python main.py demo` | 12 registros em 3 grupos, com entrega local validada |
| Dados de referência | 4 registros por grupo: ALPHA, BETA e GAMMA |

Os testes verificam o conteúdo esperado das partições, preservação de cabeçalhos e quebras de linha, idempotência, detecção de corrupção, rejeição de entradas inválidas, limpeza de resultados parciais, limites de entrada, configuração de separadores, entrega e execução pela CLI.

Todos os dados de demonstração são fictícios. Não foram acessados bancos de dados, servidores ou serviços externos. A validação não inclui benchmark de desempenho, execução concorrente nem integrações remotas.
