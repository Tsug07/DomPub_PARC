import os
import sys
import json
import zipfile
import rarfile
import shutil
import threading
import time
import traceback
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox

from PIL import Image

# NOTA: pywinauto (Application, timings, findwindows) e win32gui/win32con
# são importados dentro do DomBot para evitar conflito COM com tkinter/filedialog

# Configura automaticamente o caminho do UnRAR.exe
possible_paths = [
    r"C:\\Program Files\\WinRAR\\UnRAR.exe",
    r"C:\\Program Files (x86)\\WinRAR\\UnRAR.exe"
]
for path in possible_paths:
    if os.path.exists(path):
        rarfile.UNRAR_TOOL = path
        break

# Tema
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Diretório base do script (para assets)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ==============================================================================
# CLASSE DOMBOT - Lógica de automação (sem dependência de UI)
# ==============================================================================
class DomBot:
    def __init__(self, log_callback=None, progress_callback=None, ui_reference=None):
        # Import tardio para evitar conflito COM com tkinter/filedialog
        from pywinauto import Application, timings, findwindows
        import win32gui
        import win32con

        self._Application = Application
        self._timings = timings
        self._findwindows = findwindows
        self._win32gui = win32gui
        self._win32con = win32con

        self.log_callback = log_callback or print
        self.progress_callback = progress_callback
        self.ui_reference = ui_reference
        self.app = None
        self.main_window = None
        self.empresa_para_numero = {}
        self.total_pdfs = 0
        self.pdfs_processados = 0
        self.pdfs_sucesso = 0

        # Configurações do pywinauto (otimizadas para velocidade)
        timings.Timings.window_find_timeout = 3
        timings.Timings.app_start_timeout = 5
        timings.Timings.exists_timeout = 0.3
        timings.Timings.after_click_wait = 0.05
        timings.Timings.after_editsetedittext_wait = 0.05
        timings.Timings.after_setfocus_wait = 0.05

    def log(self, mensagem):
        formatted = f"{datetime.now().strftime('%H:%M:%S')} - {mensagem}"
        if callable(self.log_callback):
            self.log_callback(formatted)
        with open("publicacao_log.txt", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {mensagem}\n")

    def update_progress(self, current, total, status=""):
        if callable(self.progress_callback):
            progress = (current / total) * 100 if total > 0 else 0
            self.progress_callback(progress, f"{current}/{total} - {status}")

    def check_interrupted(self):
        if self.ui_reference and not self.ui_reference.is_running:
            self.log("Processo interrompido pelo usuario")
            return True
        return False

    # === CONEXÃO COM DOMÍNIO ===
    def find_dominio_window(self):
        """Encontra a janela do Domínio Escrita Fiscal de forma robusta"""
        try:
            self.log("Procurando janela do Domínio Escrita Fiscal...")

            try:
                all_windows = self._findwindows.find_windows()
                self.log(f"Total de janelas abertas: {len(all_windows)}")

                for hwnd in all_windows:
                    try:
                        title = self._win32gui.GetWindowText(hwnd)
                        # Ignorar janela própria
                        if "DomPub" in title or "DomBot" in title:
                            continue
                        if title and "Domínio" in title:
                            self.log(f"Janela encontrada: '{title}'")
                            if "Escrita Fiscal" in title or "Escrita" in title:
                                self.log("Janela do Domínio Escrita Fiscal localizada!")
                                return hwnd
                            if "Versão" in title:
                                self.log("Janela do Domínio localizada (via Versão)!")
                                return hwnd
                    except Exception:
                        continue
            except Exception as e:
                self.log(f"Erro ao listar janelas: {str(e)}")

            windows = self._findwindows.find_windows(title_re=".*Domínio.*Escrita.*")
            if windows:
                self.log(f"Janela do Domínio encontrada via regex (total: {len(windows)})")
                return windows[0]

            windows = self._findwindows.find_windows(title_re=".*Domínio.*")
            if windows:
                for window in windows:
                    try:
                        title = self._win32gui.GetWindowText(window)
                        if "DomPub" not in title and "DomBot" not in title:
                            self.log(f"Janela candidata via regex flexível: '{title}'")
                            return window
                    except:
                        continue

            self.log("Nenhuma janela do Domínio Escrita Fiscal encontrada.")
            return None
        except Exception as e:
            self.log(f"Erro ao procurar a janela do Domínio Escrita Fiscal: {str(e)}")
            self.log(f"Traceback: {traceback.format_exc()}")
            return None

    def connect_to_dominio(self):
        """Conecta à aplicação Domínio Escrita Fiscal"""
        try:
            handle = self.find_dominio_window()
            if not handle:
                self.log("Janela do Domínio Escrita Fiscal não encontrada.")
                return False

            if self._win32gui.IsIconic(handle):
                self._win32gui.ShowWindow(handle, self._win32con.SW_RESTORE)
                time.sleep(1)

            self._win32gui.SetForegroundWindow(handle)
            time.sleep(0.5)

            self.app = self._Application(backend="uia").connect(handle=handle)
            self.main_window = self.app.window(handle=handle)

            self.log("Conectado ao Domínio Escrita Fiscal com sucesso")
            return True

        except Exception as e:
            self.log(f"Erro ao conectar ao Domínio: {str(e)}")
            return False

    # === INTERAÇÃO COM JANELAS ===
    def aguardar_janela_confirmacao_interruptivel(self, timeout=15):
        """Aguarda e encontra janela de confirmação de forma robusta e interruptível"""
        self.log("Procurando janela de confirmação...")

        inicio = time.time()
        while (time.time() - inicio) < timeout:
            if self.check_interrupted():
                return False

            try:
                all_windows = self._findwindows.find_windows()
                for hwnd in all_windows:
                    try:
                        window = self.app.window(handle=hwnd)
                        if window.is_dialog() and window.is_visible():
                            titulo = window.window_text()
                            if titulo and any(palavra in titulo.lower() for palavra in ['atenção', 'confirmação', 'aviso', 'informação', 'sucesso']):
                                self.log(f"Janela de confirmação encontrada: '{titulo}'")
                                return window
                    except:
                        continue
            except Exception as e:
                self.log(f"Erro durante busca: {str(e)}")
            time.sleep(0.5)

        self.log("Timeout: Nenhuma janela de confirmação encontrada")
        return None

    def clicar_botao_ok(self, dialog):
        """Clica no botão OK de forma robusta"""
        textos_botao = ["OK", "Ok", "Confirmar", "Sim", "Yes"]
        auto_ids = ["1", "2", "6", "1001", "2001"]

        for texto in textos_botao:
            try:
                botao = dialog.child_window(title=texto, control_type="Button")
                if botao.exists(timeout=2):
                    botao.click()
                    self.log(f"Botão '{texto}' clicado com sucesso")
                    return True
            except:
                continue

        for auto_id in auto_ids:
            try:
                botao = dialog.child_window(auto_id=auto_id, control_type="Button")
                if botao.exists(timeout=2):
                    botao.click()
                    self.log(f"Botão com auto_id '{auto_id}' clicado com sucesso")
                    return True
            except:
                continue

        try:
            botoes = dialog.children(control_type="Button")
            if botoes:
                botoes[0].click()
                self.log("Primeiro botão encontrado foi clicado")
                return True
        except:
            pass

        self.log("Não foi possível clicar no botão OK")
        return False

    # === FUNÇÕES DE ARQUIVO ===
    def carregar_mapeamento(self, pasta):
        """Carrega o mapeamento empresa->código do JSON gerado pelo Spoon"""
        caminho_json = os.path.join(pasta, "mapeamento_empresas.json")
        if os.path.exists(caminho_json):
            with open(caminho_json, 'r', encoding='utf-8') as f:
                mapeamento = json.load(f)
            self.log(f"Mapeamento JSON carregado: {len(mapeamento)} empresas")
            return mapeamento
        else:
            self.log("JSON não encontrado. Tentando extrair códigos dos nomes das pastas...")
            return self.extrair_mapeamento_das_pastas(pasta)

    def extrair_mapeamento_das_pastas(self, pasta):
        """Fallback: extrai mapeamento {nome_pasta: código} do padrão 'CÓDIGO - NOME'"""
        mapeamento = {}
        for nome_pasta in os.listdir(pasta):
            caminho = os.path.join(pasta, nome_pasta)
            if os.path.isdir(caminho) and ' - ' in nome_pasta:
                partes = nome_pasta.split(' - ', 1)
                if len(partes) > 1:
                    codigo = partes[0].strip()
                    mapeamento[nome_pasta] = codigo
        if mapeamento:
            self.log(f"Mapeamento extraído dos nomes das pastas: {len(mapeamento)} empresas")
        else:
            self.log("AVISO: Nenhuma pasta com padrão 'CÓDIGO - NOME' encontrada!")
        return mapeamento

    def resolver_codigo_empresa(self, nome_pasta):
        """Resolve o código de uma empresa: JSON > nome da pasta > '000'"""
        # 1. Tenta pelo mapeamento (JSON)
        if nome_pasta in self.empresa_para_numero:
            return self.empresa_para_numero[nome_pasta]
        # 2. Tenta extrair do nome da pasta (padrão "CÓDIGO - NOME")
        if ' - ' in nome_pasta:
            codigo = nome_pasta.split(' - ', 1)[0].strip()
            return codigo
        # 3. Sem código encontrado
        return None

    def extrair_zip(self, arquivo_zip, diretorio_destino):
        with zipfile.ZipFile(arquivo_zip, 'r') as zip_ref:
            zip_ref.extractall(diretorio_destino)
        self.log(f"Arquivo ZIP extraído com sucesso: {arquivo_zip}")

    def extrair_rar(self, arquivo_rar, diretorio_destino):
        with rarfile.RarFile(arquivo_rar) as rar_ref:
            rar_ref.extractall(diretorio_destino)
        self.log(f"Arquivo RAR extraído com sucesso: {arquivo_rar}")

    def compactar_em_zip(self, diretorio, saida_zip):
        with zipfile.ZipFile(saida_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for raiz, _, arquivos in os.walk(diretorio):
                for arquivo in arquivos:
                    caminho_arquivo = os.path.join(raiz, arquivo)
                    zipf.write(caminho_arquivo, os.path.relpath(caminho_arquivo, diretorio))
        self.log(f"Recompactado em: {saida_zip}")

    def reorganizar_pastas(self, diretorio_raiz):
        for pasta_empresa in os.listdir(diretorio_raiz):
            caminho_empresa = os.path.join(diretorio_raiz, pasta_empresa)
            if not os.path.isdir(caminho_empresa):
                continue
            contador_docs = 1

            for primeira_subpasta in os.listdir(caminho_empresa):
                caminho_primeira_subpasta = os.path.join(caminho_empresa, primeira_subpasta)
                if os.path.isdir(caminho_primeira_subpasta):
                    for raiz, diretorios, arquivos in os.walk(caminho_primeira_subpasta):
                        for arquivo in arquivos:
                            if arquivo.lower().endswith('.pdf'):
                                caminho_antigo = os.path.join(raiz, arquivo)
                                nome_base, extensao = os.path.splitext(arquivo)
                                novo_nome = f"{nome_base}_{contador_docs:02d}{extensao}"
                                caminho_novo = os.path.join(caminho_empresa, novo_nome)
                                shutil.move(caminho_antigo, caminho_novo)
                                contador_docs += 1

            # Remove subpastas vazias
            for raiz, diretorios, arquivos in os.walk(caminho_empresa, topdown=False):
                for diretorio in diretorios:
                    caminho_diretorio = os.path.join(raiz, diretorio)
                    if not os.listdir(caminho_diretorio):
                        os.rmdir(caminho_diretorio)

    # === AUTOMAÇÃO PRINCIPAL ===
    def localizar_elementos_publicacao(self):
        """Localiza e cacheia os elementos da janela de publicação. Chamado uma vez."""
        pub_window = self.main_window.child_window(title="Publicação de Documentos Externos")
        if not pub_window.exists(timeout=3):
            self.log("Janela 'Publicação de Documentos Externos' não encontrada.")
            return False

        self._pub_window = pub_window
        self._campo_caminho = pub_window.child_window(class_name="Edit", auto_id="1013")
        self._campo_numero = pub_window.child_window(class_name="PBEDIT190", auto_id="1001")
        self._botao_publicar = pub_window.child_window(class_name="Button", auto_id="1003")
        self.log("Elementos da janela de publicação localizados.")
        return True

    def _publicar_pdf(self, pdf_path, numero_empresa):
        """Executa a publicação de um PDF. Lança exceção se falhar."""
        self._campo_numero.set_edit_text("")
        self._campo_caminho.set_edit_text(pdf_path)
        self._campo_numero.set_edit_text(numero_empresa)

        # Verificação rápida
        valor = self._campo_numero.get_value()
        if numero_empresa not in str(valor):
            raise ValueError(f"Campo contém '{valor}' esperava '{numero_empresa}'")

        self._botao_publicar.click()
        time.sleep(0.5)

        dialog = self.aguardar_janela_confirmacao_interruptivel(timeout=10)
        if dialog is False:
            raise InterruptedError("Interrompido")
        elif dialog:
            if not self.clicar_botao_ok(dialog):
                raise RuntimeError("Falha ao clicar OK")
            time.sleep(0.3)
        else:
            raise TimeoutError("Janela de confirmação não apareceu")

    def interact_with_dominio_escrita_fiscal(self, pdf_path, numero_empresa, empresa):
        """Publica um PDF no Domínio Escrita Fiscal. Retorna True se sucesso."""
        if self.check_interrupted():
            return False

        publicacao_bem_sucedida = False

        try:
            self._publicar_pdf(pdf_path, numero_empresa)
            self.log(f"Publicado - {empresa} | {numero_empresa} | {os.path.basename(pdf_path)}")
            publicacao_bem_sucedida = True

        except InterruptedError:
            pass
        except Exception as e:
            # Tenta relocalizar elementos (janela pode ter sido recriada)
            self.log(f"Erro: {str(e)} - Relocalizando elementos...")
            try:
                if self.localizar_elementos_publicacao():
                    self._publicar_pdf(pdf_path, numero_empresa)
                    self.log(f"Publicado (retry) - {empresa} | {numero_empresa} | {os.path.basename(pdf_path)}")
                    publicacao_bem_sucedida = True
                else:
                    self.log(f"FALHA: Não foi possível relocalizar elementos.")
            except Exception as e2:
                self.log(f"FALHA no retry: {str(e2)}")

        finally:
            self.pdfs_processados += 1
            self.update_progress(
                self.pdfs_processados, self.total_pdfs,
                f"{'OK' if publicacao_bem_sucedida else 'FALHA'}: {os.path.basename(pdf_path)}"
            )

        return publicacao_bem_sucedida

    # === PROCESSO PRINCIPAL ===
    def processar(self, modo_pasta, pasta=None, arquivo_zip=None, recompactar=False):
        """Método principal de processamento. Retorna (success, message)."""
        try:
            self.pdfs_processados = 0
            self.pdfs_sucesso = 0
            self.empresa_para_numero = {}

            self.log("Iniciando processamento...")

            if modo_pasta:
                # === MODO PASTA (saída do Spoon) ===
                diretorio = pasta

                # CHECKPOINT 1
                if self.check_interrupted():
                    return False, "Interrompido antes de carregar mapeamento."

                self.log("Carregando mapeamento de empresas...")
                self.empresa_para_numero = self.carregar_mapeamento(diretorio)

                if not self.empresa_para_numero:
                    return False, "Nenhum mapeamento encontrado (nem JSON, nem padrão 'CÓDIGO - NOME' nas pastas)."

                self.total_pdfs = 0
                for empresa in os.listdir(diretorio):
                    caminho_empresa = os.path.join(diretorio, empresa)
                    if os.path.isdir(caminho_empresa) and empresa != "Relatórios Fiscais":
                        for raiz, _, arquivos in os.walk(caminho_empresa):
                            for arquivo in arquivos:
                                if arquivo.lower().endswith('.pdf'):
                                    self.total_pdfs += 1
                self.log(f"Total de PDFs encontrados: {self.total_pdfs}")

                # CHECKPOINT 2
                if self.check_interrupted():
                    return False, "Interrompido antes de conectar ao Domínio."

                if not self.connect_to_dominio():
                    return False, "Não foi possível conectar ao Domínio Escrita Fiscal."

                if not self.localizar_elementos_publicacao():
                    return False, "Janela de Publicação de Documentos Externos não encontrada."

                for empresa in os.listdir(diretorio):
                    # CHECKPOINT 3
                    if self.check_interrupted():
                        break

                    caminho_empresa = os.path.join(diretorio, empresa)
                    if not os.path.isdir(caminho_empresa) or empresa == "Relatórios Fiscais":
                        continue

                    numero_empresa = self.resolver_codigo_empresa(empresa)
                    if not numero_empresa:
                        self.log(f"AVISO: Código não encontrado para '{empresa}', pulando.")
                        continue
                    self.log(f"Processando empresa: {empresa} (Código: {numero_empresa})")

                    for raiz, _, arquivos in os.walk(caminho_empresa):
                        # CHECKPOINT 4
                        if self.check_interrupted():
                            break

                        for arquivo in arquivos:
                            if self.check_interrupted():
                                break

                            if arquivo.lower().endswith('.pdf'):
                                pdf_path = os.path.join(raiz, arquivo)
                                if self.interact_with_dominio_escrita_fiscal(pdf_path, numero_empresa, empresa):
                                    self.pdfs_sucesso += 1

            else:
                # === MODO ZIP/RAR (legado) ===
                arquivo_path = arquivo_zip
                diretorio_destino = os.path.join(
                    os.path.dirname(arquivo_path),
                    "extraido_" + datetime.now().strftime("%Y%m%d_%H%M%S")
                )

                # CHECKPOINT 5
                if self.check_interrupted():
                    return False, "Interrompido antes da extração."

                if arquivo_path.lower().endswith(".zip"):
                    self.extrair_zip(arquivo_path, diretorio_destino)
                elif arquivo_path.lower().endswith(".rar"):
                    self.extrair_rar(arquivo_path, diretorio_destino)

                self.log("Extraindo códigos das pastas...")
                self.empresa_para_numero = self.extrair_mapeamento_das_pastas(diretorio_destino)

                if recompactar:
                    zip_saida = arquivo_path.replace(".rar", "_renomeado.zip").replace(".zip", "_renomeado.zip")
                    self.compactar_em_zip(diretorio_destino, zip_saida)

                self.log("Reorganizando pastas...")
                self.reorganizar_pastas(diretorio_destino)

                self.total_pdfs = sum(
                    len([f for f in files if f.lower().endswith('.pdf')])
                    for _, _, files in os.walk(diretorio_destino)
                )
                self.log(f"Total de PDFs encontrados: {self.total_pdfs}")

                if not self.connect_to_dominio():
                    return False, "Não foi possível conectar ao Domínio Escrita Fiscal."

                if not self.localizar_elementos_publicacao():
                    return False, "Janela de Publicação de Documentos Externos não encontrada."

                for empresa in os.listdir(diretorio_destino):
                    # CHECKPOINT 6
                    if self.check_interrupted():
                        break

                    caminho_empresa = os.path.join(diretorio_destino, empresa)
                    if os.path.isdir(caminho_empresa):
                        numero_empresa = self.resolver_codigo_empresa(empresa)
                        if not numero_empresa:
                            self.log(f"AVISO: Código não encontrado para '{empresa}', pulando.")
                            continue
                        self.log(f"Processando empresa: {empresa} (Código: {numero_empresa})")

                        for raiz, _, arquivos in os.walk(caminho_empresa):
                            if self.check_interrupted():
                                break

                            for arquivo in arquivos:
                                if self.check_interrupted():
                                    break

                                if arquivo.lower().endswith('.pdf'):
                                    pdf_path = os.path.join(raiz, arquivo)
                                    if self.interact_with_dominio_escrita_fiscal(pdf_path, numero_empresa, empresa):
                                        self.pdfs_sucesso += 1

            # Resumo final
            if self.check_interrupted():
                msg = f"Interrompido! {self.pdfs_sucesso}/{self.pdfs_processados} documentos publicados."
                self.log(msg)
                return False, msg
            else:
                msg = f"Concluído! {self.pdfs_sucesso}/{self.total_pdfs} documentos publicados com sucesso."
                self.log(msg)
                return True, msg

        except Exception as e:
            msg = f"Erro: {str(e)}"
            self.log(msg)
            return False, msg


# ==============================================================================
# CLASSE APPUI - Interface gráfica (sem lógica de automação)
# ==============================================================================
class AppUI(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("DomPub")
        self.geometry("700x550")
        self.resizable(True, True)
        self.minsize(600, 450)

        # Ícone
        try:
            icon_path = os.path.join(BASE_DIR, "assets", "DomBot_Pub.ico")
            self.iconbitmap(icon_path)
        except Exception:
            pass

        # Estado
        self.is_running = False
        self.pasta_selecionada = ctk.StringVar()
        self.arquivo_zip_selecionado = ctk.StringVar()
        self.modo_pasta = False
        self.status_var = ctk.StringVar(value="Aguardando início...")
        self.recompactar = ctk.BooleanVar(value=False)
        self.zip_panel_visible = False

        self.setup_ui()

    def setup_ui(self):
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)

        # --- Header com logo ---
        try:
            logo_path = os.path.join(BASE_DIR, "assets", "DomBot_Pub.png")
            img_logo = Image.open(logo_path)
            img_logo = img_logo.resize((64, 100))
            self.logo_ctk = ctk.CTkImage(light_image=img_logo, dark_image=img_logo, size=(64, 80))

            top_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
            top_frame.pack(pady=(5, 15))

            logo_label = ctk.CTkLabel(top_frame, image=self.logo_ctk, text="")
            logo_label.pack(side="left", padx=(0, 10))

            text_label = ctk.CTkLabel(top_frame, text="DomPub", font=ctk.CTkFont(size=22, weight="bold"))
            text_label.pack(side="left")
        except Exception:
            ctk.CTkLabel(main_frame, text="DomPub", font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(5, 15))

        # --- Seleção de pasta (principal) ---
        pasta_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        pasta_frame.pack(fill="x", padx=10, pady=(0, 5))

        ctk.CTkLabel(pasta_frame, text="Pasta (Spoon):").pack(side="left", padx=(0, 5))
        ctk.CTkEntry(pasta_frame, textvariable=self.pasta_selecionada, width=400).pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.btn_selecionar_pasta = ctk.CTkButton(pasta_frame, text="Selecionar", width=100, command=self.selecionar_pasta)
        self.btn_selecionar_pasta.pack(side="right")

        # --- Botão para expandir/colapsar ZIP/RAR ---
        self.toggle_btn = ctk.CTkButton(
            main_frame, text="Usar ZIP/RAR...", width=120, height=25,
            fg_color="transparent", text_color=("gray50", "gray70"),
            hover_color=("gray85", "gray30"), font=ctk.CTkFont(size=11),
            command=self.toggle_zip_panel
        )
        self.toggle_btn.pack(anchor="w", padx=10, pady=(0, 2))

        # --- Painel ZIP/RAR (colapsável) ---
        self.zip_frame = ctk.CTkFrame(main_frame)

        zip_row = ctk.CTkFrame(self.zip_frame, fg_color="transparent")
        zip_row.pack(fill="x", padx=5, pady=5)

        ctk.CTkLabel(zip_row, text="Arquivo ZIP/RAR:").pack(side="left", padx=(0, 5))
        ctk.CTkEntry(zip_row, textvariable=self.arquivo_zip_selecionado, width=350).pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.btn_selecionar_zip = ctk.CTkButton(zip_row, text="Procurar", width=80, command=self.selecionar_zip_ou_rar)
        self.btn_selecionar_zip.pack(side="right")

        ctk.CTkCheckBox(self.zip_frame, text="Recompactar em ZIP após renomear", variable=self.recompactar).pack(anchor="w", padx=10, pady=(0, 5))

        # --- Botões de controle ---
        control_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        control_frame.pack(fill="x", padx=10, pady=(5, 5))

        self.btn_iniciar = ctk.CTkButton(
            control_frame, text="Iniciar Processamento", height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#2d8a4e", hover_color="#236b3c",
            command=self.iniciar_processamento
        )
        self.btn_iniciar.pack(side="left", padx=(0, 10))

        self.btn_parar = ctk.CTkButton(
            control_frame, text="Parar", height=40, width=80,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="red", hover_color="darkred",
            command=self.stop_bot, state="disabled"
        )
        self.btn_parar.pack(side="left", padx=(0, 10))

        self.btn_validar = ctk.CTkButton(
            control_frame, text="Validar Entrada", height=40, width=130,
            command=self.validar_entrada
        )
        self.btn_validar.pack(side="right")

        # --- Barra de progresso ---
        self.progress_bar = ctk.CTkProgressBar(main_frame, width=650)
        self.progress_bar.pack(padx=10, pady=(10, 5))
        self.progress_bar.set(0)

        # --- Status ---
        self.status_label = ctk.CTkLabel(main_frame, textvariable=self.status_var, font=ctk.CTkFont(size=12))
        self.status_label.pack(pady=(0, 5))

        # --- Log ---
        self.log_text = ctk.CTkTextbox(main_frame, height=250, width=650, font=ctk.CTkFont(size=11))
        self.log_text.pack(padx=10, pady=(0, 10))

    # === CONTROLES DA UI ===
    def toggle_zip_panel(self):
        if self.zip_panel_visible:
            self.zip_frame.pack_forget()
            self.toggle_btn.configure(text="Usar ZIP/RAR...")
            self.zip_panel_visible = False
        else:
            self.zip_frame.pack(fill="x", padx=10, pady=(0, 5), after=self.toggle_btn)
            self.toggle_btn.configure(text="Ocultar ZIP/RAR")
            self.zip_panel_visible = True

    def selecionar_zip_ou_rar(self):
        filename = filedialog.askopenfilename(
            title="Selecione o arquivo ZIP ou RAR",
            filetypes=[("Arquivos ZIP/RAR", "*.zip *.rar")]
        )
        if filename:
            self.arquivo_zip_selecionado.set(filename)
            self.pasta_selecionada.set("")

    def selecionar_pasta(self):
        pasta = filedialog.askdirectory(title="Selecione a pasta de saída do Spoon")
        if pasta:
            self.pasta_selecionada.set(pasta)
            self.arquivo_zip_selecionado.set("")

    def log_message(self, msg):
        self.log_text.insert("end", f"{msg}\n")
        self.log_text.see("end")
        self.update_idletasks()

    def update_progress(self, progress, status):
        self.progress_bar.set(progress / 100)
        self.status_var.set(status)
        self.update_idletasks()

    # === VALIDAÇÃO ===
    def validar_entrada(self):
        """Valida as entradas antes de iniciar o processamento"""
        tem_pasta = bool(self.pasta_selecionada.get())
        tem_zip = bool(self.arquivo_zip_selecionado.get())

        if not tem_pasta and not tem_zip:
            messagebox.showwarning("Aviso", "Selecione uma pasta ou arquivo ZIP/RAR primeiro.")
            return

        if tem_pasta:
            pasta = self.pasta_selecionada.get()
            if not os.path.isdir(pasta):
                messagebox.showerror("Erro", "Pasta selecionada não existe.")
                return

            # Verifica fontes de mapeamento
            caminho_json = os.path.join(pasta, "mapeamento_empresas.json")
            tem_json = os.path.exists(caminho_json)
            empresas_com_codigo = 0
            empresas_sem_codigo = []

            pdf_count = 0
            empresas_sem_pdf = []
            mapeamento_json = {}

            if tem_json:
                with open(caminho_json, 'r', encoding='utf-8') as f:
                    mapeamento_json = json.load(f)

            for empresa in os.listdir(pasta):
                caminho = os.path.join(pasta, empresa)
                if os.path.isdir(caminho) and empresa != "Relatórios Fiscais":
                    pdfs = [f for _, _, files in os.walk(caminho) for f in files if f.lower().endswith('.pdf')]
                    pdf_count += len(pdfs)
                    if not pdfs:
                        empresas_sem_pdf.append(empresa)

                    # Verifica se tem código (JSON ou nome da pasta)
                    if empresa in mapeamento_json or ' - ' in empresa:
                        empresas_com_codigo += 1
                    else:
                        empresas_sem_codigo.append(empresa)

            if empresas_com_codigo == 0:
                messagebox.showerror("Erro de Validação",
                    "Nenhuma empresa com código encontrada.\n"
                    "Necessário: mapeamento_empresas.json ou pastas com padrão 'CÓDIGO - NOME'.")
                self.log_message(f"{datetime.now().strftime('%H:%M:%S')} - Validação falhou: nenhum código de empresa encontrado")
                return

            fonte = "JSON" if tem_json else "nomes das pastas"
            msg = (f"Entrada válida!\n"
                   f"Fonte do mapeamento: {fonte}\n"
                   f"Empresas com código: {empresas_com_codigo}\n"
                   f"PDFs encontrados: {pdf_count}")
            if empresas_sem_codigo:
                msg += f"\nEmpresas SEM código (serão puladas): {len(empresas_sem_codigo)}"
            if empresas_sem_pdf:
                msg += f"\nPastas sem PDF: {len(empresas_sem_pdf)}"

            messagebox.showinfo("Validação", msg)
            self.log_message(f"{datetime.now().strftime('%H:%M:%S')} - Validação concluída: {pdf_count} PDFs, {empresas_com_codigo} empresas com código ({fonte})")

        else:
            arquivo = self.arquivo_zip_selecionado.get()
            if not os.path.exists(arquivo):
                messagebox.showerror("Erro", "Arquivo ZIP/RAR não encontrado.")
                return
            messagebox.showinfo("Validação", f"Arquivo encontrado: {os.path.basename(arquivo)}")
            self.log_message(f"{datetime.now().strftime('%H:%M:%S')} - Validação: arquivo {os.path.basename(arquivo)} encontrado")

    # === EXECUÇÃO ===
    def iniciar_processamento(self):
        tem_zip = bool(self.arquivo_zip_selecionado.get())
        tem_pasta = bool(self.pasta_selecionada.get())

        if not tem_zip and not tem_pasta:
            messagebox.showerror("Erro", "Selecione uma pasta ou arquivo ZIP/RAR!")
            return

        if tem_pasta:
            pasta = self.pasta_selecionada.get()
            if not os.path.isdir(pasta):
                messagebox.showerror("Erro", "A pasta selecionada não existe!")
                return
            self.modo_pasta = True
        else:
            self.modo_pasta = False

        # Verifica se o Domínio está aberto
        try:
            from pywinauto import findwindows
            import win32gui
            all_windows = findwindows.find_windows()
            dominio_found = False
            for hwnd in all_windows:
                try:
                    title = win32gui.GetWindowText(hwnd)
                    if "DomPub" in title or "DomBot" in title:
                        continue
                    if "Domínio" in title and ("Escrita" in title or "Versão" in title):
                        dominio_found = True
                        break
                except Exception:
                    continue

            if not dominio_found:
                messagebox.showerror("Erro",
                    "O software Domínio Escrita Fiscal não está aberto.\nAbra-o e tente novamente.")
                return
        except Exception:
            messagebox.showerror("Erro",
                "Não foi possível verificar se o Domínio está aberto.")
            return

        # Gerenciamento de estado dos botões
        self.is_running = True
        self.btn_iniciar.configure(state="disabled")
        self.btn_parar.configure(state="normal")
        self.btn_selecionar_pasta.configure(state="disabled")
        self.btn_validar.configure(state="disabled")
        self.toggle_btn.configure(state="disabled")
        self.btn_selecionar_zip.configure(state="disabled")

        threading.Thread(target=self.executar_bot, daemon=True).start()

    def stop_bot(self):
        self.is_running = False
        self.log_message(f"{datetime.now().strftime('%H:%M:%S')} - Solicitação de parada enviada...")

    def executar_bot(self):
        """Thread target: cria DomBot, executa e restaura estado da UI"""
        try:
            bot = DomBot(
                log_callback=self.log_message,
                progress_callback=self.update_progress,
                ui_reference=self
            )

            if self.modo_pasta:
                success, msg = bot.processar(
                    modo_pasta=True,
                    pasta=self.pasta_selecionada.get()
                )
            else:
                success, msg = bot.processar(
                    modo_pasta=False,
                    arquivo_zip=self.arquivo_zip_selecionado.get(),
                    recompactar=self.recompactar.get()
                )

            if success:
                messagebox.showinfo("Concluído", msg)
            else:
                if "Interrompido" in msg:
                    messagebox.showwarning("Interrompido", msg)
                else:
                    messagebox.showerror("Erro", msg)

        except Exception as e:
            self.log_message(f"{datetime.now().strftime('%H:%M:%S')} - Erro fatal: {str(e)}")
            messagebox.showerror("Erro Fatal", f"Erro inesperado:\n{str(e)}")

        finally:
            self.is_running = False
            self.btn_iniciar.configure(state="normal")
            self.btn_parar.configure(state="disabled")
            self.btn_selecionar_pasta.configure(state="normal")
            self.btn_validar.configure(state="normal")
            self.toggle_btn.configure(state="normal")
            self.btn_selecionar_zip.configure(state="normal")
            self.update_progress(0, "Pronto para iniciar")


# ==============================================================================
# ENTRY POINT
# ==============================================================================
def main():
    app = AppUI()
    app.mainloop()


if __name__ == "__main__":
    main()
