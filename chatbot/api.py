from flask import Flask, render_template, request, redirect, url_for, make_response
import requests
import uuid
import os
import openai
import json
import re

app = Flask(__name__)

# Configuração da OpenAI
openai.api_key = os.environ.get("OPENAI_API_KEY")

# Histórico das conversas
conversas_armazenadas = {}

# Palavras irrelevantes
palavras_irrelevantes = {"a","o","e","isso","aquilo","ok","sim","não","na","de","do","da","é","eh"}

def contem_portugues(texto):
    palavras_pt = {"o", "a", "de", "é", "em", "para", "com", "como", "do", "da", "uma", "por", "mais", "se"}
    palavras_texto = set(re.findall(r'\b\w+\b', texto.lower()))
    return len(palavras_pt & palavras_texto) >= 3

def traduzir_para_portugues(texto):
    if not texto:
        return None
    try:
        resposta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Traduza para português, apenas o texto."},
                {"role": "user", "content": texto}
            ],
            max_tokens=300
        )
        return resposta.choices[0].message.content.strip()
    except Exception as e:
        print("Erro na tradução:", e)
        return texto

def gerar_justificativa_critica(titulo, autores, ano, descricao, pergunta_usuario):
    try:
        contexto = f"Livro: '{titulo}' de {autores}, publicado em {ano}."
        if descricao:
            contexto += f" Sinopse: {descricao}."
        else:
            contexto += " (Sem sinopse disponível.)"
        contexto += f" Pergunta do usuário: {pergunta_usuario}."

        prompt = (
            "Você é um assistente literário brasileiro e sempre responde em português. "
            "Você só pode responder sobre livros REAIS. Nunca gere informações que não estejam diretamente relacionadas a um livro real e publicado. "
            "Se o livro não existir, diga claramente: 'Não encontrei um livro com esse tema, autor ou título.'. "
            "Com base no contexto abaixo, escreva uma recomendação detalhada, cativante e personalizada APENAS SE o livro for real.\n"
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
            max_tokens=300,
            temperature=0.9
        )

        conteudo = resposta.choices[0].message.content.strip()

        if not conteudo or "não foi possível" in conteudo.lower():
            print("⚠️ Conteúdo vazio ou genérico detectado na resposta da IA.")
            if descricao:
                return f"📘 Este livro, '{titulo}' de {autores}, traz uma narrativa que pode ser interessante para quem se interessa pelo tema abordado. {descricao}"
            else:
                return f"📘 O livro '{titulo}' de {autores}, publicado em {ano}, pode ser uma leitura interessante, mesmo sem uma sinopse disponível."

        if not contem_portugues(conteudo):
            print("🌐 Traduzindo resposta da IA para português...")
            conteudo = traduzir_para_portugues(conteudo) or conteudo

        return conteudo

    except Exception as e:
        print("Erro ao gerar justificativa crítica:", e)
        if descricao:
            return f"📘 '{titulo}' de {autores}. Descrição: {descricao}"
        else:
            return f"📘 '{titulo}' de {autores}, publicado em {ano}. Sem descrição disponível."

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

def buscar_livro_por_subject(subject, pergunta_usuario):
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
    url = "https://www.googleapis.com/books/v1/volumes"
    q = f"intitle:{query}" if tipo == "livro" else f"inauthor:{query}" if tipo == "autor" else query

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

def recomendar_livro_semelhante(livro_base, pergunta_usuario):
    resultado_base = buscar_livro_ou_autor(livro_base, "livro", pergunta_usuario)
    if not resultado_base:
        return f"Não encontrei informações suficientes sobre '{livro_base}' para sugerir algo parecido."

    dados_interpretados = interpretar_pergunta_ia(pergunta_usuario)
    tema_base = dados_interpretados.get("valor", livro_base)

    resultado_similar = buscar_livro_por_subject(tema_base, pergunta_usuario)
    if resultado_similar and livro_base.lower() not in resultado_similar.lower():
        return f"Você mencionou '{livro_base}'. Aqui vai uma sugestão parecida:\n\n{resultado_similar}"

    return f"Encontrei informações sobre '{livro_base}', mas não consegui encontrar algo realmente semelhante. Pode reformular?"

def interpretar_pergunta_ia(pergunta):
    prompt = (
        "Você é um assistente literário e seu dever é manter a conversa estritamente sobre livros reais, publicados. "
        "Não aceite perguntas sobre temas soltos, animais, objetos ou conceitos sem relação clara com literatura. "
        "Responda sempre em português e só continue se identificar um livro, autor ou tema literário legítimo.\n\n"
        "Se a pergunta indicar que o usuário quer um livro similar a outro (ex: 'parecido com', 'semelhante a', 'no estilo de'), o tipo deve ser 'semelhante'.\n\n"
        "Receba qualquer pergunta do usuário sobre livros acadêmicos ou literários e retorne um JSON com:\n"
        "- tipo: 'livro', 'autor', 'tema', 'semelhante', 'saudacao'\n"
        "- valor: o termo principal da busca (ex: nome do livro, autor ou tema)\n\n"
        f"Pergunta do usuário: {pergunta}"
    )
    try:
        resposta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150
        )
        return json.loads(resposta.choices[0].message.content.strip())
    except Exception as e:
        print("Erro IA:", e)
        return {"tipo": "tema", "valor": pergunta}

def entrada_valida(pergunta):
    pergunta_clean = pergunta.strip().lower()
    return len(pergunta_clean) > 1 and pergunta_clean not in palavras_irrelevantes

def eh_saudacao(pergunta):
    saudacoes = ["oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "hey", "hello", "iae",
                 "eae", "fala", "tudo bem", "como vai", "como você está", "tudo certo", "saudações",
                 "salve", "e aí", "beleza", "opa", "i ae", "e ae"]
    pergunta_clean = pergunta.strip().lower()
    return any(palavra in pergunta_clean for palavra in saudacoes)

def gerar_resposta(pergunta):
    if not entrada_valida(pergunta):
        return "Desculpe, só posso recomendar livros acadêmicos ou literários. Qual é a sua dúvida sobre livros?"

    if eh_saudacao(pergunta):
        return "Olá! Pode me dizer o título, autor ou tema do livro que deseja?"

    termos_proibidos = {"cavalos", "cachorros", "gatos", "futebol", "carros", "comida", "filmes", "roupas", "tecnologia", "esportes"}
    if any(palavra in pergunta.lower() for palavra in termos_proibidos):
        return "Desculpe, só posso responder perguntas sobre livros, autores ou temas literários."

    dados = interpretar_pergunta_ia(pergunta)
    tipo = dados.get("tipo")
    valor = dados.get("valor")

    if tipo == "saudacao":
        return "Olá! Pode me dizer o título, autor ou tema do livro que deseja?"
    elif tipo == "livro" and valor:
        resultado = buscar_livro_ou_autor(valor, "livro", pergunta)
        if resultado: return resultado
    elif tipo == "autor" and valor:
        resultado = buscar_livro_ou_autor(valor, "autor", pergunta)
        if resultado: return resultado
    elif tipo == "tema" and valor:
        resultado = buscar_livro_por_subject(valor, pergunta)
        if resultado: return resultado
    elif tipo == "semelhante" and valor:
        resultado = recomendar_livro_semelhante(valor, pergunta)
        if resultado: return resultado

    # Tentativa extra com fallback genérico
    if valor:
        for tipo_busca in ["livro", "autor", "tema"]:
            resultado = buscar_livro_por_subject(valor, pergunta) if tipo_busca == "tema" else buscar_livro_ou_autor(valor, tipo_busca, pergunta)
            if resultado:
                return resultado

    return "Desculpe, não consegui encontrar nenhum livro relacionado. Pode reformular a pergunta?"

# --- Rotas Flask ---
@app.route('/', methods=['GET', 'POST'])
def chat():
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
    if session_id not in conversas_armazenadas:
        conversas_armazenadas[session_id] = []

    if request.method == 'POST':
        pergunta = request.form.get('pergunta')
        if pergunta:
            resposta = gerar_resposta(pergunta)
            conversas_armazenadas[session_id].append((pergunta, resposta))

    conversas = conversas_armazenadas.get(session_id, [])
    resp = render_template('chat.html', conversas=conversas)
    response = make_response(resp)
    response.set_cookie('session_id', session_id, httponly=True, secure=False, samesite='Lax')
    return response

@app.route('/limpar', methods=['POST'])
def limpar_conversa():
    session_id = request.cookies.get('session_id')
    if session_id and session_id in conversas_armazenadas:
        conversas_armazenadas[session_id] = []
    return redirect(url_for('chat'))

if __name__ == "__main__":
    app.run(debug=True)