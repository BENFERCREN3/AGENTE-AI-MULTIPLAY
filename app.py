# MULTIPLAY MULTIMARCA Chatbot completo con tildes ignoradas, modo soporte, medios de pago y fichas visuales

from flask import Flask, request, jsonify
import requests
import openai
import os
import logging
import unicodedata
from datetime import datetime
from dotenv import load_dotenv

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
    exit(1)
if not ULTRAMSG_TOKEN:
    logger.error("❌ ULTRAMSG_TOKEN no configurado")
    exit(1)

# Cliente OpenAI
from openai import OpenAI
try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info("✅ Cliente OpenAI listo")
except Exception as e:
    logger.error(f"❌ Error iniciando OpenAI: {e}")
    exit(1)

conversation_memory = {}
clientes_en_soporte = set()

# Quitar tildes
def quitar_tildes(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

# Diccionario de plataformas
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

# Prompt
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
    try:
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
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"❌ Error con OpenAI: {e}")
        return "😓 Lo siento, hubo un problema técnico. Pronto te ayudamos."

def enviar_mensaje_whatsapp(numero, mensaje):
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
    texto = """💳 Estos son nuestros medios de pago disponibles. Puedes transferir a cualquiera y enviar el comprobante aquí mismo 📲\n\nUna vez recibido, activamos tu cuenta de inmediato. ¿Te confirmo el total a pagar? ✅"""
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

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        logger.info("➡️ Webhook recibido")

        # UltraMsg envía datos como form-urlencoded
        data = request.form.to_dict()
        logger.info(f"📨 Contenido recibido: {data}")

        if not data or 'from' not in data or 'body' not in data:
            logger.warning("⚠️ Campos requeridos no encontrados en el webhook")
            return jsonify({"status": "missing_fields"}), 400

        sender = data['from']
        user_msg = quitar_tildes(data['body'].lower())

        logger.info(f"✅ Mensaje de {sender}: {user_msg}")
        if data.get('event_type') != 'message_received' or sender == ULTRAMSG_INSTANCE:
            return jsonify({"status": "ignored"}), 200

        if sender in clientes_en_soporte and any(p in user_msg for p in ["solucionado", "ya me ayudaron", "gracias", "ya lo resolvi"]):
            clientes_en_soporte.remove(sender)
            enviar_mensaje_whatsapp(sender, "✅ Nos alegra que se haya solucionado. Ya puedes continuar con normalidad 😊.")
            return jsonify({"status": "soporte_finalizado"}), 200

        if sender in clientes_en_soporte:
            return jsonify({"status": "modo_soporte_activo"}), 200

        if "soporte" in user_msg:
            clientes_en_soporte.add(sender)
            enviar_mensaje_whatsapp(sender, "📸 Por favor, envíanos una foto del error y una breve descripción de lo que sucede. Un asesor te atenderá pronto.")
            return jsonify({"status": "modo_soporte_activado"}), 200

        if "metodos de pago" in user_msg:
            enviar_metodos_pago(sender)
            return jsonify({"status": "metodos_pago_enviado"}), 200

        if any(pago in user_msg for pago in [
            "pagar", "medio de pago", "como pago", "quiero pagar", "listo",
            "quiero comprar", "comprar ahora", "lo compro", "ya lo compro", "si lo compro",
            "quiero comprarlo", "quiero comprar ahora", "quiero comprar ya"]):
            enviar_metodos_pago(sender)
            return jsonify({"status": "pago_enviado"}), 200

        for clave, (precio, imagen) in plataformas.items():
            if clave in user_msg:
                enviar_ficha_plataforma(sender, clave.upper(), precio, imagen)
                return jsonify({"status": "plataforma_enviada"}), 200

        if sender not in conversation_memory:
            conversation_memory[sender] = []
        conversation_memory[sender].append({"role": "user", "content": user_msg})

        plataformas_detectadas = any(p in user_msg for p in plataformas)
        intencion_pago = any(p in user_msg for p in ["pagar", "medio de pago", "como pago", "quiero pagar", "listo", "comprar", "lo compro", "metodo de pago", "quiero comprar", "quiero comprar ahora", "quiero comprar ya","metodos de pago"])

        if not plataformas_detectadas and not intencion_pago:
            mensaje_bienvenida = """
¡Hola! 👋 Gracias por comunicarte con *Multiplay Multimarca*. 🌟  
Somos tu tienda digital de confianza para cuentas premium de entretenimiento.

🎁 Te ofrecemos acceso a las mejores plataformas, con garantía, entrega inmediata y soporte 24/7.

Si tienes dudas o necesitas ayuda para elegir la mejor opción, ¡escríbenos! 💬 Estamos aquí para brindarte una atención rápida, segura y personalizada.

📲 Solo escribe la palabra de la plataforma que te interesa y te enviaremos toda la información:

> 🎨 Canva  
> 🎬 Netflix  
> 🎞️ HBO Max  
> 📺 YouTube Premium  
> 🎥 ViX+  
> ⚽ DGO (incluye WIN Sports)  
> 📼 Disney+  
> 🎧 Spotify  
> 📦 Prime Video  
> 🔞 Pornhub Premium  
> 🔥 OnlyFans (con saldo)  
> 💼 Office 365

> *SOPORTE TÉCNICO*🔧: Si tienes algún problema o error, escribe "soporte" y te atenderemos de inmediato. Estamos aquí para ayudarte a resolver cualquier inconveniente.

✨ ¡Gracias por elegirnos y bienvenido a Multiplay Multimarca!
"""
            enviar_mensaje_whatsapp(sender, mensaje_bienvenida)
            return jsonify({"status": "bienvenida_enviada"}), 200

        respuesta = generar_respuesta_ia(user_msg)
        conversation_memory[sender].append({"role": "assistant", "content": respuesta})
        enviar_mensaje_whatsapp(sender, respuesta)

        if len(conversation_memory[sender]) > 20:
            conversation_memory[sender] = conversation_memory[sender][-10:]

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        import traceback
        logger.error(f"❌ ERROR webhook: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "time": datetime.now().isoformat(),
        "active_users": len(conversation_memory)
    })

@app.route('/')
def home():
    return "<h2>✅ MULTIPLAY MULTIMARCA Bot en ejecución</h2>"

if __name__ == '__main__':
    logger.info("🚀 MULTIPLAY MULTIMARCA bot iniciado")
    app.run(host='0.0.0.0', port=5000)