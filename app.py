import sys
import os
import subprocess
import threading
import gettext
import signal
import tkinter as tk
from tkinter import filedialog, messagebox

# ==========================================
# ÁREA DAS "VACINAS" E PATCHES
# ==========================================

# VACINA 1: Correção de Tradução
original_translation = gettext.translation
def safe_translation(domain, localedir=None, languages=None, class_=None, fallback=False):
    try:
        return original_translation(domain, localedir, languages, class_, fallback)
    except FileNotFoundError:
        return gettext.NullTranslations()
gettext.translation = safe_translation

# VACINA 2: Correção de Sinais
original_signal = signal.signal
def safe_signal_handler(signum, frame):
    current = threading.current_thread()
    if current is not threading.main_thread():
        return None
    return original_signal(signum, frame)
signal.signal = safe_signal_handler

# VACINA 3: O FANTASMA (Esconde TODAS as janelas de subprocessos)
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

        # --- MODO SPOTIFY ---
        if "spotify.com" in link or "open.spotify.com" in link:
            sys.argv = [
                "spotdl",
                link,
                "--output", f"{pasta_destino}/{{list-position}}_{{title}}.{{output-ext}}",
                "--format", "mp3",
                "--ffmpeg", caminho_ffmpeg,
                "--headless",
                "--log-level", "CRITICAL"
            ]
            try:
                console_entry_point()
            except SystemExit as e:
                if e.code != 0:
                    raise Exception(f"SpotDL saiu com erro: {e.code}")

        # --- MODO YOUTUBE ---
        else:
            opcoes = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': f'{pasta_destino}/%(title)s.%(ext)s',
                'ffmpeg_location': os.path.dirname(caminho_ffmpeg) 
            }
            with yt_dlp.YoutubeDL(opcoes) as ydl:
                ydl.download([link])

        sys.exit(0)

    except Exception as e:
        print(f"ERRO CRITICO WORKER: {str(e)}", file=sys.stderr)
        sys.exit(1)

# ==========================================
# PARTE 2: A INTERFACE GRÁFICA (GUI)
# ==========================================
def gui_mode():
    def iniciar_download_thread():
        thread = threading.Thread(target=processar_download)
        thread.start()

    def processar_download():
        link = entry_link.get()
        pasta_destino = label_pasta['text']

        if not link:
            messagebox.showwarning("Atenção", "Por favor, cole um link.")
            return
        if "Selecione a pasta" in pasta_destino:
            messagebox.showwarning("Atenção", "Por favor, escolha uma pasta de destino.")
            return

        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        
        caminho_ffmpeg = os.path.join(base_path, "ffmpeg.exe")

        if not os.path.exists(caminho_ffmpeg):
            messagebox.showerror("Erro", f"ffmpeg.exe não encontrado em:\n{caminho_ffmpeg}")
            return

        btn_baixar.config(state="disabled", text="Baixando (Aguarde)...") 
        status_label.config(text="Processando download em segundo plano...")
        janela.update()

        cmd = [
            sys.executable,
            "--worker",
            link,
            pasta_destino,
            caminho_ffmpeg
        ]

        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            processo = subprocess.run(
                cmd,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )

            if processo.returncode == 0:
                status_label.config(text="Download Concluído!")
                
                # --- O AJUSTE DE PRIORIDADE ---
                janela.lift()
                janela.attributes('-topmost', True)
                janela.focus_force()
                messagebox.showinfo("Sucesso", "Download finalizado com sucesso!")
                janela.attributes('-topmost', False)
                # ------------------------------

                entry_link.delete(0, tk.END)
            else:
                status_label.config(text="Erro no download.")
                msg_erro = processo.stderr if processo.stderr else "Erro desconhecido."
                
                janela.lift()
                janela.attributes('-topmost', True)
                messagebox.showerror("Erro Interno", f"O download falhou:\n{msg_erro}")
                janela.attributes('-topmost', False)

        except Exception as e:
            janela.attributes('-topmost', True)
            messagebox.showerror("Erro Crítico", str(e))
            janela.attributes('-topmost', False)
        
        finally:
            btn_baixar.config(state="normal", text="BAIXAR")

    def selecionar_pasta():
        pasta = filedialog.askdirectory()
        if pasta:
            label_pasta.config(text=pasta)

    global entry_link, label_pasta, btn_baixar, status_label, janela
    
    janela = tk.Tk()
    janela.title("Baixador Universal Pro")
    janela.geometry("550x340") # Aumentei um pouco a altura para caber o crédito

    tk.Label(janela, text="Cole o Link (YouTube ou Spotify):").pack(pady=5)
    entry_link = tk.Entry(janela, width=60)
    entry_link.pack(pady=5)

    btn_pasta = tk.Button(janela, text="Selecionar Pasta de Destino", command=selecionar_pasta)
    btn_pasta.pack(pady=10)

    label_pasta = tk.Label(janela, text="Nenhuma pasta selecionada", fg="blue")
    label_pasta.pack(pady=5)

    btn_baixar = tk.Button(janela, text="BAIXAR", bg="#4CAF50", fg="white", font=("Arial", 12, "bold"), command=iniciar_download_thread)
    btn_baixar.pack(pady=20)

    status_label = tk.Label(janela, text="")
    status_label.pack()

    # --- CRÉDITOS ---
    # side="bottom" força ele a ir para o pé da janela
    tk.Label(janela, text="Desenvolvido por Eduardo Wundervald", font=("Arial", 8), fg="gray").pack(side="bottom", pady=10)

    janela.mainloop()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        run_worker_mode()
    else:
        gui_mode()