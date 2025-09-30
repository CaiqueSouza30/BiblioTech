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
def gerar_justificativa_critica(titulo, autores, ano, descricao, pergunta_usuario):
    """
    Gera recomendação detalhada e personalizada, evitando respostas genéricas.
    """
    try:
        contexto = f"Livro: '{titulo}' de {autores}, publicado em {ano}."
        if descricao:
            contexto += f" Sinopse: {descricao}."
        else:
            contexto += " (Sem sinopse disponível.)"
        contexto += f" Pergunta do usuário: {pergunta_usuario}."

        prompt = (
            "Você é um assistente literário brasileiro. Com base no contexto abaixo, "
            "escreva uma recomendação detalhada, cativante e personalizada.\n"
            "Regras:\n"
            "- Use de 4 a 6 frases.\n"
            "- Destaque a narrativa, o estilo do autor, os temas centrais e a relevância.\n"
            "- A recomendação deve ser envolvente, persuasiva e única.\n"
            "- NÃO use frases genéricas como 'é relevante para o tema' ou 'oferece uma leitura envolvente'.\n"
            "Se não houver descrição, baseie-se apenas no título e autor.\n"
            f"\nContexto: {contexto}"
        )

        resposta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.9
        )

        conteudo = resposta.choices[0].message.content.strip()

        if not conteudo or "não foi possível" in conteudo.lower():
            # Se resposta for vazia ou parecer uma falha, criar fallback com descrição
            print("⚠️ Conteúdo vazio ou genérico detectado na resposta da IA.")
            if descricao:
                return f"📘 Este livro, '{titulo}' de {autores}, traz uma narrativa que pode ser interessante para quem se interessa pelo tema abordado. {descricao}"
            else:
                return f"📘 O livro '{titulo}' de {autores}, publicado em {ano}, pode ser uma leitura interessante, mesmo sem uma sinopse disponível."

        return conteudo

    except Exception as e:
        print("Erro ao gerar justificativa crítica:", e)
        if descricao:
            return f"📘 '{titulo}' de {autores}. Descrição: {descricao}"
        else:
            return f"📘 '{titulo}' de {autores}, publicado em {ano}. Sem descrição disponível."

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

# --- Busca na Google Books API ---
def buscar_livro_por_subject(subject, pergunta_usuario):
    # Buscar por assunto (tema) no Google Books usando q=subject
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {
        "q": f"subject:{subject}",
        "maxResults": 1,
        "langRestrict": "pt"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        dados = response.json()
    except requests.exceptions.RequestException:
        return None

    items = dados.get("items", [])
    if not items:
        return None

    livro = items[0]["volumeInfo"]
    titulo = livro.get("title", "Desconhecido")
    autores = ", ".join(livro.get("authors", ["Desconhecido"]))
    ano = livro.get("publishedDate", "Desconhecido")
    descricao = livro.get("description", None)
    if descricao:
        descricao = traduzir_para_portugues(descricao)

    justificativa = gerar_justificativa_critica(titulo, autores, ano, descricao, pergunta_usuario)
    return f"📚 {titulo} de {autores}, publicado em {ano}. {justificativa}"

def buscar_livro_ou_autor(query, tipo, pergunta_usuario):
    # Para livro: busca por título; para autor: busca por autor no q
    url = "https://www.googleapis.com/books/v1/volumes"
    if tipo == "livro":
        q = f"intitle:{query}"
    elif tipo == "autor":
        q = f"inauthor:{query}"
    else:
        q = query  # fallback

    params = {
        "q": q,
        "maxResults": 1,
        "langRestrict": "pt"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        dados = response.json()
    except requests.exceptions.RequestException as e:
        return f"Erro ao consultar Google Books: {e}"

    items = dados.get("items", [])
    if not items:
        return None

    livro = items[0]["volumeInfo"]
    titulo = livro.get("title", "Desconhecido")
    autores = ", ".join(livro.get("authors", ["Desconhecido"]))
    ano = livro.get("publishedDate", "Desconhecido")
    descricao = livro.get("description", None)
    if descricao:
        descricao = traduzir_para_portugues(descricao)

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