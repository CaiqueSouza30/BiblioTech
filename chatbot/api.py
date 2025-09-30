from flask import Flask, render_template, request, redirect, url_for, make_response
import requests
import uuid
import os
import openai
import json

app = Flask(__name__)

# Configuração da OpenAI
openai.api_key = os.environ.get("OPENAI_API_KEY")

# Histórico das conversas
conversas_armazenadas = {}

# Palavras irrelevantes
palavras_irrelevantes = {"a","o","e","isso","aquilo","ok","sim","não","na","de","do","da","é","eh"}

# --- Tradução ---
def traduzir_para_portugues(texto):
    if not texto:
        return None
    try:
        resposta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role":"system","content":"Traduza para português, apenas o texto."},
                {"role":"user","content":texto}
            ],
            max_tokens=300
        )
        return resposta.choices[0].message.content.strip()
    except Exception as e:
        print("Erro na tradução:", e)
        return texto

# --- Justificativa crítica sem fallback genérico ---
def gerar_justificativa_critica(titulo, autores, ano, descricao, pergunta_usuario):
    """
    Gera recomendação detalhada, cativante e personalizada, sem jamais usar frases genéricas.
    """
    try:
        contexto = f"Livro: '{titulo}' de {autores}, publicado em {ano}."
        if descricao:
            contexto += f" Sinopse: {descricao}."
        contexto += f" Pergunta do usuário: {pergunta_usuario}."

        prompt = (
            "Você é um crítico literário brasileiro renomado. Com base no contexto abaixo, "
            "escreva uma recomendação detalhada e envolvente.\n"
            "Regras:\n"
            "- Use 4 a 6 frases.\n"
            "- Destaque narrativa, estilo do autor, temas explorados e relevância.\n"
            "- A recomendação deve ser cativante, persuasiva e personalizada.\n"
            "- NÃO use frases genéricas como 'é relevante para o tema' ou 'oferece uma leitura envolvente'.\n"
            "- Se não houver informações suficientes, apenas diga 'Não foi possível gerar uma recomendação detalhada neste momento'.\n\n"
            f"Contexto: {contexto}"
        )

        resposta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.9
        )

        conteudo = resposta.choices[0].message.content.strip()
        if not conteudo:
            return "Não foi possível gerar uma recomendação detalhada neste momento."
        return conteudo

    except Exception as e:
        print("Erro ao gerar justificativa crítica:", e)
        return "Não foi possível gerar uma recomendação detalhada neste momento."

# --- Auxiliares ---
def obter_descricao(work_key):
    try:
        url = f"https://openlibrary.org{work_key}.json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        dados = response.json()
        descricao = dados.get("description")
        if isinstance(descricao, dict):
            descricao = descricao.get("value")
        if isinstance(descricao, str):
            return traduzir_para_portugues(descricao)
        return None
    except requests.exceptions.RequestException:
        return None

# --- Busca na OpenLibrary ---
def buscar_livro_por_subject(subject, pergunta_usuario):
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
    titulo = traduzir_para_portugues(livro.get("title", "Desconhecido"))
    autores = ", ".join([traduzir_para_portugues(a.get("name", "Desconhecido")) for a in livro.get("authors", [])])
    ano = livro.get("first_publish_year", "Desconhecido")
    descricao = obter_descricao(livro.get("key")) if livro.get("key") else None

    justificativa = gerar_justificativa_critica(titulo, autores, ano, descricao, pergunta_usuario)
    return f"📚 {titulo} de {autores}, publicado em {ano}. {justificativa}"

def buscar_livro_ou_autor(query, tipo, pergunta_usuario):
    url = f"https://openlibrary.org/search.json?{('title' if tipo=='livro' else 'author')}={query}&limit=1"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        dados = response.json()
    except requests.exceptions.RequestException as e:
        return f"Erro ao consultar Open Library: {e}"

    docs = dados.get("docs", [])
    if not docs:
        return None

    livro = docs[0]
    titulo = traduzir_para_portugues(livro.get("title", "Desconhecido"))
    autores = ", ".join([traduzir_para_portugues(a) for a in livro.get("author_name", ["Desconhecido"])])
    ano = livro.get("first_publish_year", "Desconhecido")
    descricao = obter_descricao(livro.get("key")) if livro.get("key") else None

    justificativa = gerar_justificativa_critica(titulo, autores, ano, descricao, pergunta_usuario)
    return f"📚 {titulo} de {autores}, publicado em {ano}. {justificativa}"

# --- Interpretação com IA ---
def interpretar_pergunta_ia(pergunta):
    prompt = (
        "Você é um assistente literário. Responda sempre em português.\n"
        "Receba qualquer pergunta do usuário sobre livros acadêmicos ou literários "
        "e retorne um JSON com:\n"
        "- tipo: 'livro', 'autor', 'tema', 'saudacao'\n"
        "- valor: título, autor ou tema detectado (ou null)\n"
        "Retorne apenas o JSON. Tente extrair o tema principal mesmo que a pergunta seja genérica.\n\n"
        f"Pergunta do usuário: {pergunta}"
    )
    try:
        resposta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"user","content":prompt}],
            max_tokens=150
        )
        return json.loads(resposta.choices[0].message.content.strip())
    except Exception as e:
        print("Erro IA:", e)
        return {"tipo":"tema","valor":pergunta}

# --- Validação e saudação ---
def entrada_valida(pergunta):
    pergunta_clean = pergunta.strip().lower()
    return len(pergunta_clean) > 1 and pergunta_clean not in palavras_irrelevantes

def eh_saudacao(pergunta):
    saudacoes = ["oi","olá","ola","bom dia","boa tarde","boa noite","hey","hello","iae",
                 "eae","fala","tudo bem","como vai","como você está","tudo certo","saudações",
                 "salve","e aí","beleza","opa","i ae","e ae"]
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
        resultado = buscar_livro_ou_autor(valor, "livro", pergunta)
        if resultado: return resultado
    elif tipo=="autor" and valor:
        resultado = buscar_livro_ou_autor(valor, "autor", pergunta)
        if resultado: return resultado
    elif tipo=="tema" and valor:
        resultado = buscar_livro_por_subject(valor, pergunta)
        if resultado: return resultado

    if valor:
        for tipo_busca in ["livro","autor","tema"]:
            resultado = buscar_livro_por_subject(valor, pergunta) if tipo_busca=="tema" else buscar_livro_ou_autor(valor, tipo_busca, pergunta)
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
