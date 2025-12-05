import sys
import os
import subprocess
import threading
import gettext
import signal
import tkinter as tk
from tkinter import ttk # Importante para a Barra de Progresso
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
        numero_inicial = int(sys.argv[5]) 

        # --- MODO SPOTIFY ---
        if "spotify.com" in link or "open.spotify.com" in link:
            # Avisa a GUI que é Spotify (para ativar barra indeterminada)
            print("MODE:SPOTIFY", flush=True)
            
            if "/track/" in link:
                template_nome = f"{pasta_destino}/{numero_inicial:02d}_{{title}}.{{output-ext}}"
            else:
                template_nome = f"{pasta_destino}/{{list-position}}_{{title}}.{{output-ext}}"

            sys.argv = [
                "spotdl",
                link,
                "--output", template_nome,
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
            # Função que o yt-dlp chama enquanto baixa
            def progress_hook(d):
                if d['status'] == 'downloading':
                    # Pega a porcentagem (remove cores e símbolos ANSI se houver)
                    p = d.get('_percent_str', '0%').replace('%','')
                    # Imprime para a GUI ler: "PROGRESS:50.5"
                    try:
                        print(f"PROGRESS:{p}", flush=True)
                    except:
                        pass

            opcoes = {
                'format': 'bestaudio/best',
                'postprocessors': [
                    {
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    },
                    {
                        'key': 'MetadataParser',
                        'when': 'pre_process',
                        'actions': [
                            {'action': 'replace', 'field': 'title', 'regex': r'/', 'replace': '-'},
                            {'action': 'replace', 'field': 'title', 'regex': r'\\', 'replace': '-'}
                        ]
                    }
                ],
                'outtmpl': f'{pasta_destino}/%(autonumber)02d_%(title)s.%(ext)s',
                'ffmpeg_location': os.path.dirname(caminho_ffmpeg),
                'autonumber_start': numero_inicial,
                'windowsfilenames': True,
                'progress_hooks': [progress_hook], # Conecta nossa função de progresso
                'quiet': True, # Limpa o terminal para facilitar leitura
                'noprogress': True 
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
    
    def descobrir_proximo_numero(pasta):
        maior_numero = 0
        try:
            arquivos = os.listdir(pasta)
            for arquivo in arquivos:
                partes = arquivo.split('_')
                if len(partes) > 1:
                    prefixo = partes[0]
                    if prefixo.isdigit():
                        numero = int(prefixo)
                        if numero > maior_numero:
                            maior_numero = numero
        except Exception:
            pass 
        return maior_numero + 1

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

        proximo_num = descobrir_proximo_numero(pasta_destino)

        # Configurações Iniciais da Interface
        btn_baixar.config(state="disabled", text=f"Iniciando...") 
        status_label.config(text=f"Preparando download (ID: {proximo_num:02d})...")
        progress_bar['value'] = 0 # Zera a barra
        progress_bar['mode'] = 'determinate' # Modo padrão (enchimento)
        janela.update()

        cmd = [
            sys.executable,
            "--worker",
            link,
            pasta_destino,
            caminho_ffmpeg,
            str(proximo_num)
        ]

        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            # Usamos Popen em vez de run para ler linha a linha em tempo real
            processo = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, # Captura a saída padrão (onde vem o progresso)
                stderr=subprocess.PIPE, # Captura erros
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
                text=True,
                encoding='utf-8',
                errors='replace'
            )

            # Loop de Leitura do Progresso
            while True:
                # Lê uma linha do Worker
                linha = processo.stdout.readline()
                if not linha and processo.poll() is not None:
                    break
                
                if linha:
                    linha = linha.strip()
                    # Se for YouTube, vem "PROGRESS:50.5"
                    if "PROGRESS:" in linha:
                        try:
                            # Pega o número depois dos dois pontos
                            porcentagem = float(linha.split(":")[1])
                            progress_bar['value'] = porcentagem
                            status_label.config(text=f"Baixando... {porcentagem:.1f}%")
                        except:
                            pass
                    
                    # Se for Spotify, vem "MODE:SPOTIFY"
                    elif "MODE:SPOTIFY" in linha:
                        progress_bar['mode'] = 'indeterminate'
                        progress_bar.start(10) # Começa o "vai e vem" da barra
                        status_label.config(text="Baixando do Spotify (Aguarde)...")

            # Espera o processo morrer de vez e pega erros se houver
            stdout, stderr = processo.communicate()
            
            if processo.returncode == 0:
                progress_bar.stop()
                progress_bar['mode'] = 'determinate'
                progress_bar['value'] = 100 # Enche a barra no final
                status_label.config(text="Download Concluído!")
                
                janela.lift()
                janela.attributes('-topmost', True)
                janela.focus_force()
                messagebox.showinfo("Sucesso", "Download finalizado com sucesso!")
                janela.attributes('-topmost', False)

                entry_link.delete(0, tk.END)
                progress_bar['value'] = 0 # Reseta para o próximo
            else:
                progress_bar.stop()
                status_label.config(text="Erro no download.")
                msg_erro = stderr if stderr else "Erro desconhecido."
                
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
            progress_bar.stop()

    def selecionar_pasta():
        pasta = filedialog.askdirectory()
        if pasta:
            label_pasta.config(text=pasta)

    global entry_link, label_pasta, btn_baixar, status_label, janela, progress_bar
    
    janela = tk.Tk()
    janela.title("Baixador Universal Pro")
    janela.geometry("600x450") # Aumentei um pouco para caber a barra
    janela.minsize(550, 400)

    frame_central = tk.Frame(janela)
    frame_central.place(relx=0.5, rely=0.5, anchor="center")

    tk.Label(frame_central, text="Cole o Link (YouTube ou Spotify):", font=("Arial", 10)).pack(pady=5)
    
    entry_link = tk.Entry(frame_central, width=60)
    entry_link.pack(pady=5)

    btn_pasta = tk.Button(frame_central, text="Selecionar Pasta de Destino", command=selecionar_pasta)
    btn_pasta.pack(pady=10)

    label_pasta = tk.Label(frame_central, text="Nenhuma pasta selecionada", fg="blue")
    label_pasta.pack(pady=5)

    btn_baixar = tk.Button(frame_central, text="BAIXAR", bg="#4CAF50", fg="white", font=("Arial", 12, "bold"), command=iniciar_download_thread)
    btn_baixar.pack(pady=15)

    # --- BARRA DE PROGRESSO ---
    # length=400 define a largura visual dela em pixels
    progress_bar = ttk.Progressbar(frame_central, orient='horizontal', length=400, mode='determinate')
    progress_bar.pack(pady=5)

    status_label = tk.Label(frame_central, text="")
    status_label.pack()

    tk.Label(frame_central, text="Desenvolvido por Eduardo Wundervald", font=("Arial", 8), fg="gray").pack(pady=(20, 0))
    tk.Label(frame_central, text="v2.0.0", font=("Arial", 7), fg="gray").pack(pady=(0, 10))

    janela.mainloop()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        run_worker_mode()
    else:
        gui_mode()

# python -m PyInstaller --noconsole --onefile --collect-all spotdl --collect-all yt_dlp --collect-all pykakasi app.py