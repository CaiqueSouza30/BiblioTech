from flask import Flask, render_template, request, redirect, url_for, make_response
import requests
import uuid
import os
import openai
import json

app = Flask(__name__)

# Configuração da OpenAI
openai.api_key = os.environ.get("OPENAI_API_KEY")  # coloque sua chave aqui

# Histórico das conversas por sessão
conversas_armazenadas = {}

# Palavras irrelevantes para filtrar
palavras_irrelevantes = {"a","o","e","isso","aquilo","ok","sim","não","na","de","do","da","é","eh"}

# --- Funções de busca na Open Library ---
def buscar_livro_por_subject(subject):
    url = f"https://openlibrary.org/subjects/{subject.replace(' ','_')}.json?limit=1"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        dados = response.json()
    except requests.exceptions.RequestException:
        return None

    works = dados.get("works", [])
    if not works:
        return None

    livro = works[0]
    titulo = livro.get("title","Desconhecido")
    autores = ", ".join([a.get("name","Desconhecido") for a in livro.get("authors",[])])
    link = f"https://openlibrary.org{livro.get('key')}" if livro.get("key") else "#"

    return f"📚 Aqui está um livro relacionado a '{subject}': <strong>{titulo}</strong> de {autores}. Saiba mais: <a href='{link}' target='_blank'>Open Library</a>"

def buscar_livro_ou_autor(query, tipo="livro"):
    url = f"https://openlibrary.org/search.json?{('title' if tipo=='livro' else 'author')}={query}&limit=1"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        dados = response.json()
    except requests.exceptions.RequestException as e:
        return f"Erro ao consultar Open Library: {e}"

    docs = dados.get("docs",[])
    if not docs:
        return None

    livro = docs[0]
    titulo = livro.get("title","Desconhecido")
    autores = ", ".join(livro.get("author_name",["Desconhecido"]))
    ano = livro.get("first_publish_year","Desconhecido")
    link = f"https://openlibrary.org{livro.get('key')}" if livro.get("key") else "#"

    return f"📚 <strong>{titulo}</strong> de {autores}, publicado em {ano}. Saiba mais: <a href='{link}' target='_blank'>Open Library</a>"

# --- Interpretação com IA ---
def interpretar_pergunta_ia(pergunta):
    prompt = (
        "Você é um assistente literário. Receba qualquer pergunta do usuário sobre livros acadêmicos ou literários "
        "e retorne um JSON com:\n"
        "- tipo: 'livro', 'autor', 'tema', 'saudacao'\n"
        "- valor: título, autor ou tema detectado (ou null)\n"
        "Retorne apenas o JSON. Tente extrair o tema principal mesmo que a pergunta seja genérica, "
        "como 'livro sobre mitologia nórdica'.\n\nPergunta do usuário: " + pergunta
    )
    try:
        resposta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"user","content":prompt}],
            max_tokens=150
        )
        conteudo = resposta.choices[0].message.content.strip()
        return json.loads(conteudo)
    except Exception as e:
        print("Erro IA:", e)
        # fallback: trata toda a pergunta como tema
        return {"tipo":"tema","valor":pergunta}

# --- Validação e saudação ---
def entrada_valida(pergunta):
    pergunta_clean = pergunta.strip().lower()
    return len(pergunta_clean) > 1 and pergunta_clean not in palavras_irrelevantes

def eh_saudacao(pergunta):
    saudacoes = ["oi","olá","ola","bom dia","boa tarde","boa noite","hey","hello"]
    pergunta_clean = pergunta.strip().lower()
    return any(palavra in pergunta_clean for palavra in saudacoes)

# --- Geração da resposta final ---
def gerar_resposta(pergunta):
    if not entrada_valida(pergunta):
        return "Desculpe, só posso recomendar livros acadêmicos ou literários. Qual é a sua dúvida sobre livros?"

    if eh_saudacao(pergunta):
        return "Olá! Pode me dizer o título, autor ou tema do livro que deseja?"

    dados = interpretar_pergunta_ia(pergunta)
    tipo = dados.get("tipo")
    valor = dados.get("valor")

    if tipo=="saudacao":
        return "Olá! Pode me dizer o título, autor ou tema do livro que deseja?"
    elif tipo=="livro" and valor:
        resultado = buscar_livro_ou_autor(valor,"livro")
        if resultado: return resultado
    elif tipo=="autor" and valor:
        resultado = buscar_livro_ou_autor(valor,"autor")
        if resultado: return resultado
    elif tipo=="tema" and valor:
        resultado = buscar_livro_por_subject(valor)
        if resultado: return resultado

    # fallback geral: tenta buscar pelo valor como título, autor ou tema
    if valor:
        for tipo_busca in ["livro","autor","tema"]:
            if tipo_busca=="tema":
                resultado = buscar_livro_por_subject(valor)
            else:
                resultado = buscar_livro_ou_autor(valor,tipo_busca)
            if resultado:
                return resultado

    return "Desculpe, não consegui encontrar nenhum livro relacionado. Pode reformular a pergunta?"

# --- Rotas Flask ---
@app.route('/', methods=['GET','POST'])
def chat():
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
    if session_id not in conversas_armazenadas:
        conversas_armazenadas[session_id] = []

    if request.method=='POST':
        pergunta = request.form.get('pergunta')
        if pergunta:
            resposta = gerar_resposta(pergunta)
            conversas_armazenadas[session_id].append((pergunta,resposta))

    conversas = conversas_armazenadas.get(session_id,[])
    resp = render_template('chat.html', conversas=conversas)
    response = make_response(resp)
    response.set_cookie('session_id',session_id,httponly=True,secure=False,samesite='Lax')
    return response

@app.route('/limpar', methods=['POST'])
def limpar_conversa():
    session_id = request.cookies.get('session_id')
    if session_id and session_id in conversas_armazenadas:
        conversas_armazenadas[session_id] = []
    return redirect(url_for('chat'))

if __name__=="__main__":
    app.run(debug=True)