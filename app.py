import sys
import os
import subprocess
import threading
import gettext
import signal
import tkinter as tk 
import ttkbootstrap as ttk 
from ttkbootstrap.constants import *
from tkinter import filedialog
from ttkbootstrap.dialogs import Messagebox 

# ==========================================
# FUNÇÃO MÁGICA: LOCALIZADOR DE ARQUIVOS
# ==========================================
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS 
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ==========================================
# ÁREA DAS "VACINAS"
# ==========================================
original_translation = gettext.translation
def safe_translation(domain, localedir=None, languages=None, class_=None, fallback=False):
    try:
        return original_translation(domain, localedir, languages, class_, fallback)
    except FileNotFoundError:
        return gettext.NullTranslations()
gettext.translation = safe_translation

original_signal = signal.signal
def safe_signal_handler(signum, frame):
    current = threading.current_thread()
    if current is not threading.main_thread(): return None
    return original_signal(signum, frame)
signal.signal = safe_signal_handler

if sys.platform == "win32":
    CREATE_NO_WINDOW = 0x08000000
    _original_Popen = subprocess.Popen
    class Popen(_original_Popen):
        def __init__(self, *args, **kwargs):
            flags = kwargs.get('creationflags', 0)
            kwargs['creationflags'] = flags | CREATE_NO_WINDOW
            super().__init__(*args, **kwargs)
    subprocess.Popen = Popen

# ==========================================
# IMPORTAÇÕES DE LÓGICA
# ==========================================
import yt_dlp
from spotdl.console.entry_point import console_entry_point

# ==========================================
# PARTE 1: O TRABALHADOR (WORKER)
# ==========================================
def run_worker_mode():
    try:
        link = sys.argv[2]
        pasta_destino = sys.argv[3]
        caminho_ffmpeg = sys.argv[4]
        numero_inicial = int(sys.argv[5]) 

        if "spotify.com" in link or "open.spotify.com" in link:
            print("MODE:SPOTIFY", flush=True)
            if "/track/" in link:
                template_nome = f"{pasta_destino}/{numero_inicial:02d}_{{title}}.{{output-ext}}"
            else:
                template_nome = f"{pasta_destino}/{{list-position}}_{{title}}.{{output-ext}}"

            sys.argv = ["spotdl", link, "--output", template_nome, "--format", "mp3", "--ffmpeg", caminho_ffmpeg, "--headless", "--log-level", "CRITICAL"]
            try: console_entry_point()
            except SystemExit as e:
                if e.code != 0: raise Exception(f"SpotDL saiu com erro: {e.code}")

        else:
            def progress_hook(d):
                if d['status'] == 'downloading':
                    p = d.get('_percent_str', '0%').replace('%','')
                    try: print(f"PROGRESS:{p}", flush=True)
                    except: pass

            opcoes = {
                'format': 'bestaudio/best',
                'postprocessors': [
                    {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'},
                    {'key': 'MetadataParser', 'when': 'pre_process', 'actions': [
                        {'action': 'replace', 'field': 'title', 'regex': r'/', 'replace': '-'},
                        {'action': 'replace', 'field': 'title', 'regex': r'\\', 'replace': '-'}
                    ]}
                ],
                'outtmpl': f'{pasta_destino}/%(autonumber)02d_%(title)s.%(ext)s',
                'ffmpeg_location': os.path.dirname(caminho_ffmpeg),
                'autonumber_start': numero_inicial,
                'windowsfilenames': True,
                'progress_hooks': [progress_hook],
                'quiet': True, 'noprogress': True 
            }
            with yt_dlp.YoutubeDL(opcoes) as ydl: ydl.download([link])

        sys.exit(0)
    except Exception as e:
        print(f"ERRO CRITICO WORKER: {str(e)}", file=sys.stderr)
        sys.exit(1)

# ==========================================
# PARTE 2: A INTERFACE GRÁFICA (GUI)
# ==========================================
def gui_mode():
    
    def descobrir_proximo_numero(pasta):
        maior_numero = 0
        try:
            arquivos = os.listdir(pasta)
            for arquivo in arquivos:
                partes = arquivo.split('_')
                if len(partes) > 1 and partes[0].isdigit():
                        numero = int(partes[0])
                        if numero > maior_numero: maior_numero = numero
        except Exception: pass 
        return maior_numero + 1

    def iniciar_download_thread():
        thread = threading.Thread(target=processar_download)
        thread.start()

    def processar_download():
        link = entry_link.get()
        pasta_destino = label_pasta['text']

        if not link:
            Messagebox.show_warning(message="Por favor, cole um link.", title="Atenção", parent=janela)
            return
        if "Selecione a pasta" in pasta_destino:
            Messagebox.show_warning(message="Por favor, escolha uma pasta de destino.", title="Atenção", parent=janela)
            return

        if getattr(sys, 'frozen', False): base_path = os.path.dirname(sys.executable)
        else: base_path = os.path.dirname(os.path.abspath(__file__))
        
        caminho_ffmpeg = os.path.join(base_path, "ffmpeg.exe")
        if not os.path.exists(caminho_ffmpeg):
            Messagebox.show_error(message="ffmpeg.exe não encontrado.", title="Erro", parent=janela)
            return

        proximo_num = descobrir_proximo_numero(pasta_destino)

        btn_baixar.config(state="disabled", text=f"Iniciando...") 
        status_label.config(text=f"Preparando download (ID: {proximo_num:02d})...", foreground="white")
        progress_bar['value'] = 0
        progress_bar['mode'] = 'determinate'
        janela.update()

        cmd = [sys.executable, "--worker", link, pasta_destino, caminho_ffmpeg, str(proximo_num)]

        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            processo = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW, text=True, encoding='utf-8', errors='replace'
            )

            while True:
                linha = processo.stdout.readline()
                if not linha and processo.poll() is not None: break
                if linha:
                    linha = linha.strip()
                    if "PROGRESS:" in linha:
                        try:
                            porcentagem = float(linha.split(":")[1])
                            progress_bar['value'] = porcentagem
                            status_label.config(text=f"Baixando... {porcentagem:.1f}%", foreground="white")
                        except: pass
                    elif "MODE:SPOTIFY" in linha:
                        progress_bar['mode'] = 'indeterminate'
                        progress_bar.start(10)
                        status_label.config(text="Baixando do Spotify (Aguarde)...", foreground="white")

            stdout, stderr = processo.communicate()
            
            if processo.returncode == 0:
                progress_bar.stop()
                progress_bar['mode'] = 'determinate'
                progress_bar['value'] = 100
                status_label.config(text="Download Concluído!", foreground="#00FF00")
                
                janela.lift(); janela.attributes('-topmost', True); janela.focus_force()
                Messagebox.show_info(message="Download finalizado com sucesso!", title="Sucesso", parent=janela)
                janela.attributes('-topmost', False)
                entry_link.delete(0, tk.END)
                progress_bar['value'] = 0
            else:
                progress_bar.stop()
                status_label.config(text="Erro no download.", foreground="#FF0000")
                msg_erro = stderr if stderr else "Erro desconhecido."
                janela.lift(); janela.attributes('-topmost', True)
                Messagebox.show_error(message=f"O download falhou:\n{msg_erro}", title="Erro Interno", parent=janela)
                janela.attributes('-topmost', False)

        except Exception as e:
            janela.attributes('-topmost', True)
            Messagebox.show_error(message=str(e), title="Erro Crítico", parent=janela)
            janela.attributes('-topmost', False)
        
        finally:
            btn_baixar.config(state="normal", text="BAIXAR")
            progress_bar.stop()

    def selecionar_pasta():
        pasta = filedialog.askdirectory()
        if pasta:
            label_pasta.config(text=pasta, foreground="cyan")

    global entry_link, label_pasta, btn_baixar, status_label, janela, progress_bar
    
    # Tema Escuro
    janela = ttk.Window(themename="darkly")
    janela.title("Baixador Universal Pro")
    janela.geometry("600x480")
    janela.minsize(550, 420)

    # --- CORREÇÃO DO ÍCONE ---
    try:
        caminho_icone = resource_path("icone.ico")
        # 1. Aplica na janela principal
        janela.iconbitmap(caminho_icone)
        # 2. Define como padrão para janelas filhas (Popups)
        janela.iconbitmap(default=caminho_icone)
    except Exception:
        pass

    frame_central = ttk.Frame(janela)
    frame_central.place(relx=0.5, rely=0.5, anchor="center")

    ttk.Label(frame_central, text="Cole o Link (YouTube ou Spotify):", font=("Inter", 10), foreground="white").pack(pady=5)
    
    entry_link = ttk.Entry(frame_central, width=60, font=("Inter", 9))
    entry_link.pack(pady=5)

    btn_pasta = ttk.Button(frame_central, text="Selecionar Pasta de Destino", command=selecionar_pasta, bootstyle="outline-light")
    btn_pasta.pack(pady=10)

    label_pasta = ttk.Label(frame_central, text="Nenhuma pasta selecionada", font=("Inter", 9), foreground="white")
    label_pasta.pack(pady=5)

    btn_baixar = ttk.Button(frame_central, text="BAIXAR", command=iniciar_download_thread, bootstyle="success", width=20)
    btn_baixar.pack(pady=15)

    progress_bar = ttk.Progressbar(frame_central, orient='horizontal', length=400, mode='determinate', bootstyle="striped-info")
    progress_bar.pack(pady=5)

    status_label = ttk.Label(frame_central, text="", font=("Inter", 9), foreground="white")
    status_label.pack()

    ttk.Label(frame_central, text="Desenvolvido por Eduardo Wundervald", font=("Inter", 8), foreground="white").pack(pady=(30, 0))
    ttk.Label(frame_central, text="v1.3.2 - Dark Edition", font=("Inter", 7), foreground="white").pack(pady=(0, 10))

    janela.mainloop()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        run_worker_mode()
    else:
        gui_mode()