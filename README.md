<p align="center">
  <img src="assets/DomBot_Pub.png" alt="DomPub Logo" width="120">
</p>

<h1 align="center">DomPub PARC</h1>

<p align="center">
  Automação de publicação de documentos de parcelamento no Domínio Escrita Fiscal
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Windows">
  <img src="https://img.shields.io/badge/UI-CustomTkinter-1F6FEB?style=for-the-badge" alt="CustomTkinter">
  <img src="https://img.shields.io/badge/automation-pywinauto-FF6F00?style=for-the-badge" alt="pywinauto">
  <img src="https://img.shields.io/badge/status-Em%20Produção-2d8a4e?style=for-the-badge" alt="Status">
</p>

---

## Sobre

**DomPub PARC** automatiza a publicação em massa de documentos PDF de parcelamento no software **Domínio Escrita Fiscal** (Thomson Reuters). O sistema processa pastas geradas pelo Spoon ou arquivos ZIP/RAR, identifica as empresas via mapeamento JSON e publica cada documento automaticamente na interface do Domínio.

## Funcionalidades

- **Dois modos de entrada** — Pasta do Spoon (com `mapeamento_empresas.json`) ou arquivo ZIP/RAR
- **Publicação automatizada** — Preenche campos, clica em publicar e confirma diálogos automaticamente
- **Validação prévia** — Verifica mapeamento e PDFs antes de iniciar o processamento
- **Interrupção segura** — Botão "Parar" com 6 checkpoints distribuídos no fluxo de execução
- **Log persistente** — Registro em tela e em arquivo (`publicacao_log.txt`) para auditoria
- **Gerenciamento de estado** — Botões desabilitados durante execução para evitar conflitos
- **Extração inteligente** — Suporte a ZIP e RAR com renomeação automática de pastas e reorganização de PDFs
- **Recompactação opcional** — Gera novo ZIP após renomear pastas (modo ZIP/RAR)

## Arquitetura

O projeto segue o padrão de separação de responsabilidades:

```
DomPub_PARC.py
├── DomBot          # Lógica de automação (sem dependência de UI)
│   ├── Conexão com Domínio Escrita Fiscal
│   ├── Operações de arquivo (ZIP/RAR/pastas)
│   └── Publicação de documentos
│
└── AppUI           # Interface gráfica (sem lógica de automação)
    ├── Seleção de entrada (pasta/ZIP)
    ├── Controles (iniciar/parar/validar)
    └── Log e progresso
```

## Pré-requisitos

| Requisito | Detalhes |
|-----------|----------|
| **Python** | 3.10 ou superior |
| **Sistema** | Windows 10/11 |
| **Domínio** | Escrita Fiscal aberto com a janela "Publicação de Documentos Externos" visível |
| **WinRAR** | Necessário apenas para modo RAR (detectado automaticamente) |

## Instalação

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/DomPub_PARC.git
cd DomPub_PARC

# Instale as dependências
pip install customtkinter pywinauto rarfile pillow pywin32
```

## Uso

```bash
python DomPub_PARC.py
```

### Modo Pasta (Spoon)

1. Clique em **Selecionar** e escolha a pasta de saída do Spoon
2. A pasta deve conter `mapeamento_empresas.json` e subpastas com PDFs por empresa
3. Clique em **Validar Entrada** para verificar se está tudo certo
4. Clique em **Iniciar Processamento**

### Modo ZIP/RAR

1. Clique em **Usar ZIP/RAR...** para expandir o painel
2. Selecione o arquivo compactado
3. Opcionalmente marque "Recompactar em ZIP após renomear"
4. Clique em **Iniciar Processamento**

## Estrutura de Pastas Esperada (Modo Spoon)

```
pasta_saida_spoon/
├── mapeamento_empresas.json      # {"Nome Empresa": "codigo", ...}
├── Empresa A/
│   ├── documento1.pdf
│   └── documento2.pdf
├── Empresa B/
│   └── documento1.pdf
└── ...
```

## Estrutura do Projeto

```
DomPub_PARC/
├── DomPub_PARC.py          # Aplicação principal
├── README.md
└── assets/
    ├── DomBot_Pub.ico       # Ícone da janela
    └── DomBot_Pub.png       # Logo da aplicação
```

## Dependências

| Pacote | Uso |
|--------|-----|
| `customtkinter` | Interface gráfica moderna |
| `pywinauto` | Automação de janelas do Windows |
| `pywin32` | Manipulação de janelas (win32gui/win32con) |
| `rarfile` | Extração de arquivos RAR |
| `Pillow` | Carregamento do logo PNG |

## Licença

Uso interno.

---

<p align="center">
  Desenvolvido para automação de processos contábeis
</p>
