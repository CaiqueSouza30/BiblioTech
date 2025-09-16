import requests

def consultar_bot(pergunta):
    url = "https://apifreellm.com/api/chat"
    payload = {
        "message": pergunta
    }
    response = requests.post(url, json=payload)
    js = response.json()
    if js.get("status") == "success":
        return js.get("response")
    else:
        # verificar qual status foi retornado
        return f"Erro: {js.get('status')} - {js.get('error')}"


# Teste
pergunta = "Me recomende outros livros que não seja do mesmo universo mas que seja da mitologia grega"
resposta = consultar_bot(pergunta)
print(resposta)
