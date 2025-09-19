from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import requests
import uuid

app = Flask(__name__)

# Banco de dados
def init_db():
    with sqlite3.connect('database.db') as conn:
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

# Função para consultar a API
def consultar_bot(pergunta, historico):
    url = "https://apifreellm.com/api/chat"
    instrucoes = (
        "Você é um assistente literário e acadêmico. Sempre recomende **um único livro por vez**, "
        "Caso o usuário começe a conversa com uma saudação, responda **Olá, como posso te ajudar ?**, "
        "E responda somente **perguntas sobre livros**, caso o usuário pergunte sobre qualquer outro assunto, "
        "Responda **Desculpe, eu só posso te ajudar com livros, tem alguma dúvida sobre ?**, "
        "interprete as mensagens caso o usuário envie somente **um gênero literário ou acadêmico de livro"
        "incluindo o **título**, o **autor** e uma **breve explicação** sobre o motivo da recomendação. "
        "Use um tom natural e empático, como se estivesse conversando com um amigo. "
    )

    contexto = instrucoes + "\n" + "\n".join(historico + [f"Usuário: {pergunta}"])
    payload = {"message": contexto}
    #Tratamento de erros
    try:
        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()  # levanta erro se status != 200
        js = response.json()
    except requests.exceptions.RequestException as e:
        return f"Erro de rede: {e}"
    except ValueError:
        return "Erro: resposta inválida da API (não é JSON)."

    if js.get("status") == "success":
        return js.get("response", "Sem resposta recebida.")
    else:
        return f"Erro da API: {js.get('status')} - {js.get('error')}"

# Página principal
@app.route('/', methods=['GET', 'POST'])
def chat():
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())

    if request.method == 'POST':
        pergunta = request.form.get('pergunta')
        if pergunta:  # só processa se não estiver vazio
            with sqlite3.connect('database.db') as conn:
                c = conn.cursor()
                # Pega o histórico da sessão, ordenado por id
                c.execute(
                    "SELECT pergunta, resposta FROM conversas WHERE session_id = ? ORDER BY id ASC",
                    (session_id,)
                )
                historico_raw = c.fetchall()
                historico = []
                for p, r in historico_raw:
                    historico.append(f"Usuário: {p}")
                    historico.append(f"Bot: {r}")

                resposta = consultar_bot(pergunta, historico)

                # Salva no banco
                c.execute(
                    "INSERT INTO conversas (session_id, pergunta, resposta) VALUES (?, ?, ?)",
                    (session_id, pergunta, resposta)
                )
                conn.commit()

    # Recupera histórico atualizado
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute(
            "SELECT pergunta, resposta FROM conversas WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        )
        conversas = c.fetchall()

    resp = render_template('chat.html', conversas=conversas)
    response = app.make_response(resp)
    response.set_cookie(
        'session_id',
        session_id,
        httponly=True,   # não acessível via JavaScript
        secure=True,     # só envia via HTTPS
        samesite='Lax'   # protege contra CSRF básico
    )
    return response

# Botão limpar
@app.route('/limpar', methods=['POST'])
def limpar_conversa():
    session_id = request.cookies.get('session_id')
    if session_id:
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute("DELETE FROM conversas WHERE session_id = ?", (session_id,))
            conn.commit()
    return redirect(url_for('chat'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
