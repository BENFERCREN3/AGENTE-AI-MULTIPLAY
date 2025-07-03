# MULTIPLAY MULTIMARCA Chatbot completo con tildes ignoradas, modo soporte, medios de pago, fichas visuales, horario y derivación a humano

from flask import Flask, request, jsonify
import requests
import openai
import os
import logging
import unicodedata
from datetime import datetime, timedelta
from dotenv import load_dotenv
import threading
import time
import hashlib
import re

# Cargar variables de entorno desde .env
load_dotenv()

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ULTRAMSG_TOKEN = os.getenv("ULTRAMSG_TOKEN")
ULTRAMSG_INSTANCE = os.getenv("ULTRAMSG_INSTANCE", "instance129239")

ULTRAMSG_CHAT_URL = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE}/messages/chat"
ULTRAMSG_IMG_URL = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE}/messages/image"

# Validaciones
if not OPENAI_API_KEY or not OPENAI_API_KEY.startswith('sk-'):
    logger.error("❌ OPENAI_API_KEY inválida o no encontrada")
    OPENAI_API_KEY = None
if not ULTRAMSG_TOKEN:
    logger.error("❌ ULTRAMSG_TOKEN no configurado")
    exit(1)

# Cliente OpenAI
client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("✅ Cliente OpenAI listo")
    except Exception as e:
        logger.error(f"❌ Error iniciando OpenAI: {e}")

conversation_memory = {}
clientes_en_soporte = set()
bloqueados_temporalmente = {}
ultimo_saludo = {}
ultimo_fuera_horario = {}
ultimo_mensaje_usuario = {}  # Anti-spam
respuestas_enviadas = {}     # Control de respuestas repetidas
respuestas_previas = {}      # Registro de respuestas por usuario
cache_respuestas = {}

# Función para quitar tildes
def quitar_tildes(texto):
    try:
        if not texto or not isinstance(texto, str):
            return ""
        return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    except Exception as e:
        logger.error(f"Error procesando texto: {e}")
        return str(texto) if texto else ""

def generar_cache_key(texto):
    return hashlib.md5(texto.encode()).hexdigest()

plataformas = {
    "netflix": ("13.000", "https://i.postimg.cc/7ZzgJh3X/NETFLIX.png"),
    "spotify": ("9.000", "https://i.postimg.cc/gj5Znbrf/SPOTIFY.png"),
    "youtube": ("9.000", "https://i.postimg.cc/MGDf1Qv0/YTPREMIUMX1.png"),
    "canva": ("15.000", "https://i.postimg.cc/RVFdhvpb/CANVAPRO.png"),
    "vix": ("9.000", "https://i.postimg.cc/y80ZY5Kb/VIX.png"),
    "disney": ("9.000", "https://i.postimg.cc/YS1fZ0jj/DISNEY.png"),
    "hbo": ("9.000", "https://i.postimg.cc/pXpQxqyw/HBOMAX.png"),
    "prime": ("9.000", "https://i.postimg.cc/C5d8hxMG/PRIMEVIDEO.png"),
    "pornhub": ("12.000", "https://i.postimg.cc/Y9dgBW72/PONHUB.png"),
    "office": ("20.000", "https://i.postimg.cc/bvj1xPLP/OFFICE365.png"),
    "duolingo": ("10.000", "https://i.postimg.cc/1tB0RdGQ/DUOLINGO.png"),
    "onlyfans": ("20.000", "https://i.postimg.cc/TPqgQsHD/ONLYFANS.png"),
    "directv": ("30.000", "https://i.postimg.cc/nzpYJxQ2/DGO.png")
}

system_prompt = """
Eres un asistente virtual experto en ventas para MULTIPLAY MULTIMARCA, tienda colombiana de cuentas premium de entretenimiento digital.

✨ Misión:
- Atender con amabilidad y rapidez
- Informar precios y beneficios claramente
- Guiar hacia la compra
- Resolver dudas frecuentes

✅ Garantías:
- Entrega inmediata
- Soporte 24/7
- Duración 30 días
- Privacidad garantizada

Usa emojis de forma moderada. Responde de forma natural como un asesor humano de ventas.
"""

def generar_respuesta_ia(mensaje_usuario, historial=[]):
    if not client:
        return "😓 Lo siento, no puedo generar respuestas en este momento."
    try:
        cache_key = generar_cache_key(mensaje_usuario)
        if cache_key in cache_respuestas:
            return cache_respuestas[cache_key]

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": mensaje_usuario}
        ]
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.3,
            max_tokens=500
        )
        resultado = response.choices[0].message.content.strip()
        if len(mensaje_usuario) > 10:
            cache_respuestas[cache_key] = resultado
        return resultado
    except Exception as e:
        logger.error(f"❌ Error con OpenAI: {e}")
        return "😓 Lo siento, hubo un problema técnico. Pronto te ayudamos."

def enviar_mensaje_whatsapp(numero, mensaje):
    clave = (numero, mensaje)
    if clave in respuestas_enviadas and time.time() - respuestas_enviadas[clave] < 60:
        logger.info(f"⏳ Mensaje repetido bloqueado para {numero}")
        return None

    if numero in respuestas_previas and respuestas_previas[numero] == mensaje:
        logger.info(f"⛔ Repetición exacta detectada para {numero}")
        return None

    respuestas_enviadas[clave] = time.time()
    respuestas_previas[numero] = mensaje

    payload = {
        "token": ULTRAMSG_TOKEN,
        "to": numero,
        "body": mensaje
    }
    try:
        response = requests.post(ULTRAMSG_CHAT_URL, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"❌ Error enviando mensaje: {e}")
        return None

def enviar_ficha_plataforma(numero, nombre, precio, url_imagen):
    texto = f"""🔴 {nombre}: accede al catálogo global con 1 mes de servicio por solo ${precio} COP 🎥✨\n\n♾️ Garantía incluida\n🛠️ Estabilidad asegurada\n🕐 Soporte rápido 24/7\n📲 Entrega inmediata\n\nEscribe \"metodos de pago\" para conocer nuestras opciones 💳"""
    requests.post(
        ULTRAMSG_IMG_URL,
        data={
            "token": ULTRAMSG_TOKEN,
            "to": numero,
            "image": url_imagen,
            "caption": texto
        }
    )

def enviar_metodos_pago(numero):
    texto = """
Para realizar el pago, puedes usar cualquiera de nuestros métodos:

> 🟦Nequi: 3144413062 (JH** VAR***)

> 🟥Daviplata: 3144413062

> 🟨Bancolombia: 912-683039-91 (Cuenta de Ahorros)

Por favor, envía el comprobante a este *WHATSAPP* y confirmaremos tu pedido. ¡Gracias por tu compra!

> Si tienes alguna duda, escribe "soporte" y te atenderemos de inmediato
"""
    url_pago = "https://i.postimg.cc/SRyhCnY9/Medio-De-Pago-Actualizado.png"
    requests.post(
        ULTRAMSG_IMG_URL,
        data={
            "token": ULTRAMSG_TOKEN,
            "to": numero,
            "image": url_pago,
            "caption": texto
        }
    )

def limpiar_memoria():
    while True:
        time.sleep(3600)
        ahora = datetime.utcnow()
        expirados = [k for k, v in bloqueados_temporalmente.items() if ahora > v]
        for k in expirados:
            bloqueados_temporalmente.pop(k)
            logger.info(f"🧹 Eliminado bloqueo temporal: {k}")

        expiradas = [k for k, v in respuestas_enviadas.items() if time.time() - v > 300]
        for k in expiradas:
            respuestas_enviadas.pop(k)
        expiradas_previas = [k for k, v in respuestas_previas.items() if k not in [x[0] for x in respuestas_enviadas]]
        for k in expiradas_previas:
            respuestas_previas.pop(k)

        logger.info("🧹 Limpieza periódica completada")

threading.Thread(target=limpiar_memoria, daemon=True).start()
