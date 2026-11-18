# File Batch Processor

Pipeline em Python para separar um arquivo delimitado por grupo, conferir a integridade dos resultados e entregar lotes em uma pasta de destino. Útil para demonstrar processamento de arquivos, validação de dados e automação de rotinas de distribuição.

## Executar a demonstração

Requer Python 3.11 ou superior. Utiliza apenas a biblioteca padrão, sem instalação de dependências.

```powershell
python main.py demo
```

A demonstração usa exclusivamente `examples/input/events.txt`, com dados fictícios, e ignora configurações externas. Resultado: **12 registros, 3 grupos (ALPHA, BETA e GAMMA), 4 registros por grupo**.

- `runtime/processed/<identificador>/`: arquivos separados e `manifest.json`.
- `runtime/delivery/<identificador>/`: cópia conferida do lote.
- `examples/expected/`: resultado de referência disponível para inspeção sem executar nada.

Cada arquivo mantém o cabeçalho e os bytes dos registros correspondentes. O manifesto relaciona grupo, nome do arquivo, quantidade de registros, tamanho e SHA-256. Os nomes usam o hash do grupo para evitar colisões entre maiúsculas e minúsculas em diferentes sistemas operacionais.

## Processar outro arquivo

```powershell
python main.py run --input examples/input/events.txt --output runtime/processed --delivery runtime/delivery
python main.py verify examples/expected
```

O formato padrão é UTF-8 com cabeçalho, separador `|` e coluna `group`. É possível usar `--group-column team --delimiter ";"`. Cada registro deve ocupar uma linha e ter o mesmo número de campos do cabeçalho; este formato simples não interpreta aspas nem campos com separadores ou quebras de linha embutidos.

Opcionalmente, copie `.env.example` para `.env` na pasta do projeto e ajuste os caminhos. O comando `run` considera argumentos, variáveis de ambiente e `.env`, nessa ordem de prioridade. Caminhos relativos são resolvidos a partir do diretório de execução. O leitor de `.env` aceita `CHAVE=valor`, comentários em linhas separadas e aspas externas simples; não faz interpolação. O arquivo real `.env` não deve ser versionado.

## Fluxo e garantias

1. Lê o arquivo linha a linha e valida cabeçalho, campos e grupo.
2. Escreve as partições numa pasta temporária, mantendo no máximo 32 arquivos abertos.
3. Relê as saídas para conferir hashes, tamanhos e contagens.
4. Renomeia o lote validado para seu destino definitivo.
5. Quando solicitado, copia para a pasta de entrega e confere novamente antes de disponibilizar.

Entradas inválidas não deixam um lote parcial visível. A origem não é removida nem alterada. A repetição com os mesmos dados e opções reutiliza o lote existente após validá-lo; divergências causam erro em vez de sobrescrita silenciosa.

Limites: 1 MiB por linha e 1.000 grupos, com identificadores de 1 a 64 caracteres (`A-Z`, `a-z`, números, `_` e `-`). Execute apenas um processo por destino: não há coordenação entre workers concorrentes. As pastas devem ser locais e confiáveis. SHA-256 permite detectar corrupção em relação ao manifesto, mas não autentica arquivos contra alterações maliciosas no próprio manifesto.

A entrega desta versão ocorre no sistema de arquivos. Não há conectores SQL, SMB, SFTP ou serviços de notificação, nem agendamento embutido. Não há benchmark de desempenho ou validação de transporte remoto.

## Testes

```powershell
python -m unittest discover -s tests -v
```

Os testes usam diretórios temporários e dados fictícios. Cobrem preservação dos registros, execução repetida, rejeição de entradas inválidas, corrupção, nomes inseguros, limites, múltiplos grupos intercalados, entrega, falha de cópia e execução real pela linha de comando.

## Organização

- `batch_processor.py`: processamento, validação e entrega.
- `main.py`: interface de linha de comando e configuração.
- `tests/`: verificações automatizadas.
- `examples/`: entrada fictícia e resultado de referência.

Para publicar, utilize somente esta pasta como um repositório novo. O histórico do repositório pai não faz parte deste projeto de portfólio.
