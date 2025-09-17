from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import requests
import uuid

app = Flask(__name__)

# Banco de dados
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS conversas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            pergunta TEXT,
            resposta TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Função para consultar a API
def consultar_bot(pergunta, historico):
    url = "https://apifreellm.com/api/chat"
    # Instruções de como a IA deve se comportar
    instrucoes = (
    "Você é um assistente literário e acadêmico. Sempre recomende **um único livro por vez**, "
    "E responda somente **perguntas sobre livros**, caso o usuário pergunte sobre qualquer outro assunto, "
    "Responda **Desculpe, eu só posso te ajudar com livros, tem alguma dúvida sobre ?**, "
    "incluindo o **título**, o **autor** e uma **breve explicação** sobre o motivo da recomendação. "
    "Use um tom natural e empático, como se estivesse conversando com um amigo. "
)
    contexto = instrucoes + "\n" + "\n".join(historico + [f"Usuário: {pergunta}"])

    payload = {
        "message": contexto
    }
    # Requisição para a api
    response = requests.post(url, json=payload)
    js = response.json()

    if js.get("status") == "success":
        return js.get("response")
    else:
        return f"Erro: {js.get('status')} - {js.get('error')}"

# Página principal
@app.route('/', methods=['GET', 'POST'])
def chat():
    session_id = request.cookies.get('session_id')
    
    if not session_id:
        session_id = str(uuid.uuid4())  # Gera novo ID de sessão

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    if request.method == 'POST':
        pergunta = request.form['pergunta']

        # Pega o histórico da sessão
        c.execute("SELECT pergunta, resposta FROM conversas WHERE session_id = ?", (session_id,))
        historico_raw = c.fetchall()
        historico = []
        for p, r in historico_raw:
            historico.append(f"Usuário: {p}")
            historico.append(f"Bot: {r}")

        resposta = consultar_bot(pergunta, historico)

        # Salva no banco
        c.execute("INSERT INTO conversas (session_id, pergunta, resposta) VALUES (?, ?, ?)",
                  (session_id, pergunta, resposta))
        conn.commit()

    # Recupera o histórico atualizado
    c.execute("SELECT pergunta, resposta FROM conversas WHERE session_id = ?", (session_id,))
    conversas = c.fetchall()
    conn.close()

    resp = render_template('chat.html', conversas=conversas)
    response = app.make_response(resp)
    response.set_cookie('session_id', session_id)
    return response
# Botão limpar
@app.route('/limpar', methods=['POST'])
def limpar_conversa():
    session_id = request.cookies.get('session_id')

    if session_id:
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("DELETE FROM conversas WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()

    return redirect(url_for('chat'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
