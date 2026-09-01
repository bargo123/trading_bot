# Aegis host environment

Captured: 2026-08-19T18:56:50.013217+00:00

- **os**: Windows 11 (10.0.26200)
- **machine**: AMD64
- **cpu**: AMD64 Family 25 Model 80 Stepping 0, AuthenticAMD
- **cpu_logical**: 12
- **python**: 3.12.10
- **python_exe**: C:\Users\Zaid barghouthi\Desktop\trading_bot\.venv\Scripts\python.exe
- **venv**: C:\Users\Zaid barghouthi\Desktop\trading_bot\.venv
- **git**: git version 2.55.0.windows.3
- **node**: v24.19.0
- **uv**: uv 0.12.5 (210d1f678 2026-08-14 x86_64-pc-windows-msvc)
- **serena**: Serena 1.7.1.dev0
- **jedi_language_server**: 0.47.0
- **serena_language_backend**: python_jedi (pure-Python LSP, no Node dependency)
- **metatrader5_python**: MetaTrader5 5.0.6090
- **metatrader5_terminals**: ['C:\\Program Files\\MetaTrader 5\\terminal64.exe', 'C:\\Users\\Zaid barghouthi\\AppData\\Roaming\\MetaQuotes\\Terminal']
- **repo_root**: C:\Users\Zaid barghouthi\Desktop\trading_bot
- **repo_branch**: claude/intelligent-firehose
- **repo_head**: cc9e45e627788abe6d4f89c4532f936378822202

## Setup notes

- Python 3.12 installed via winget (`Python.Python.3.12`); the Microsoft Store
  `python.exe` alias on PATH is a stub and must not be used.
- Project venv at `.venv`; install with
  `.venv/Scripts/python -m pip install -r requirements.txt -r bot/requirements.txt`.
- Serena uses the `python_jedi` backend. The node-based `python` (pyright) backend
  fails to start on this host. `jedi-language-server` must be on PATH:
  `uv tool install jedi-language-server`.
- Serena MCP server is registered in `.mcp.json` at the repo root.
