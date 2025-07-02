# MULTIPLAY MULTIMARCA Chatbot completo con tildes ignoradas, modo soporte, medios de pago, fichas visuales, horario y derivación a humano

from flask import Flask, request, jsonify
import requests
import openai
import os
import logging
import unicodedata
from datetime import datetime, timedelta
from dotenv import load_dotenv
import time

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

# Variables globales con inicialización segura
conversation_memory = {}
clientes_en_soporte = set()
bloqueados_temporalmente = {}
ultimo_saludo = {}
ultimo_fuera_horario = {}

# Función mejorada para quitar tildes con manejo de errores
def quitar_tildes(texto):
    try:
        if not texto or not isinstance(texto, str):
            return ""
        return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    except Exception as e:
        logger.error(f"Error procesando texto: {e}")
        return str(texto) if texto else ""

# Diccionario de plataformas con validación de URLs
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
    "directv": ("30.000", "https://i.postimg.cc/nzpYJxQ2/DGO.png"),
    "dgo": ("30.000", "https://i.postimg.cc/nzpYJxQ2/DGO.png")
}

# Prompt mejorado
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
Siempre sugiere opciones de plataformas disponibles si el usuario no es específico.
"""

def generar_respuesta_ia(mensaje_usuario, historial=[]):
    try:
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # Agregar historial si existe
        if historial:
            messages.extend(historial[-6:])  # Solo últimos 6 mensajes para evitar límites
        
        messages.append({"role": "user", "content": mensaje_usuario})
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.3,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"❌ Error con OpenAI: {e}")
        return "😓 Lo siento, hubo un problema técnico. Pronto te ayudamos. Puedes escribir el nombre de cualquier plataforma para ver nuestras opciones."

def enviar_mensaje_whatsapp(numero, mensaje):
    if not numero or not mensaje:
        logger.error("Número o mensaje vacío")
        return None
        
    payload = {
        "token": ULTRAMSG_TOKEN,
        "to": numero,
        "body": mensaje
    }
    try:
        response = requests.post(ULTRAMSG_CHAT_URL, json=payload, timeout=15)
        if response.status_code == 200:
            logger.info(f"✅ Mensaje enviado a {numero}")
            return response.json()
        else:
            logger.error(f"Error HTTP {response.status_code}: {response.text}")
            return None
    except requests.exceptions.Timeout:
        logger.error(f"❌ Timeout enviando mensaje a {numero}")
        return None
    except Exception as e:
        logger.error(f"❌ Error enviando mensaje: {e}")
        return None

def enviar_ficha_plataforma(numero, nombre, precio, url_imagen):
    texto = f"""🔴 {nombre}: accede al catálogo global con 1 mes de servicio por solo ${precio} COP 🎥✨

♾️ Garantía incluida
🛠️ Estabilidad asegurada
🕐 Soporte rápido 24/7
📲 Entrega inmediata

Escribe "metodos de pago" para conocer nuestras opciones 💳"""
    
    try:
        payload = {
            "token": ULTRAMSG_TOKEN,
            "to": numero,
            "image": url_imagen,
            "caption": texto
        }
        response = requests.post(ULTRAMSG_IMG_URL, data=payload, timeout=15)
        if response.status_code == 200:
            logger.info(f"✅ Ficha enviada: {nombre} a {numero}")
        else:
            logger.error(f"Error enviando ficha: {response.status_code}")
            # Fallback: enviar solo texto si falla la imagen
            enviar_mensaje_whatsapp(numero, texto)
    except Exception as e:
        logger.error(f"❌ Error enviando ficha: {e}")
        # Fallback: enviar solo texto
        enviar_mensaje_whatsapp(numero, texto)

def enviar_metodos_pago(numero):
    texto = """💳 *MÉTODOS DE PAGO DISPONIBLES*

🟦 *Nequi*: 3144413062 (JH** VAR***)

🟥 *Daviplata*: 3144413062

🟨 *Bancolombia*: 912-683039-91 (Cuenta de Ahorros)

📸 Por favor, envía el comprobante a este *WHATSAPP* y confirmaremos tu pedido. ¡Gracias por tu compra!

🔧 Si tienes alguna duda, escribe "soporte" y te atenderemos de inmediato"""
    
    url_pago = "https://i.postimg.cc/SRyhCnY9/Medio-De-Pago-Actualizado.png"
    
    try:
        payload = {
            "token": ULTRAMSG_TOKEN,
            "to": numero,
            "image": url_pago,
            "caption": texto
        }
        response = requests.post(ULTRAMSG_IMG_URL, data=payload, timeout=15)
        if response.status_code != 200:
            # Fallback: enviar solo texto si falla la imagen
            enviar_mensaje_whatsapp(numero, texto)
    except Exception as e:
        logger.error(f"❌ Error enviando métodos de pago: {e}")
        # Fallback: enviar solo texto
        enviar_mensaje_whatsapp(numero, texto)

def obtener_hora_colombia():
    """Obtiene la hora actual de Colombia (UTC-5)"""
    return datetime.utcnow() - timedelta(hours=5)

def validar_estructura_webhook(data):
    """Valida que el webhook tenga la estructura esperada"""
    try:
        if not data or 'data' not in data:
            return False, "Estructura de webhook inválida"
        
        data_content = data['data']
        required_fields = ['from']
        
        for field in required_fields:
            if field not in data_content:
                return False, f"Campo requerido '{field}' no encontrado"
        
        return True, "OK"
    except Exception as e:
        return False, f"Error validando estructura: {e}"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        
        # Validar estructura del webhook
        is_valid, error_msg = validar_estructura_webhook(data)
        if not is_valid:
            logger.error(f"❌ Webhook inválido: {error_msg}")
            return jsonify({"status": "error", "message": error_msg}), 400
        
        sender = data['data']['from']
        tipo = data['data'].get('type', '')
        body = data['data'].get('body', '').strip()
        
        # Validar número de teléfono
        if not sender or len(sender) < 10:
            logger.error(f"❌ Número de teléfono inválido: {sender}")
            return jsonify({"status": "error", "message": "Número inválido"}), 400
        
        user_msg = quitar_tildes(body.lower()) if body else ''
        now = obtener_hora_colombia()
        
        logger.info(f"📱 Mensaje de {sender}: {body[:50]}{'...' if len(body) > 50 else ''}")
        
        # Manejo de imágenes mejorado
        if tipo == 'image':
            bloqueados_temporalmente[sender] = now + timedelta(hours=1)
            enviar_mensaje_whatsapp(sender, "🕒 Hemos recibido tu solicitud. En un momento uno de nuestros encargados se comunicará contigo. Muchas gracias por tu paciencia.")
            return jsonify({"status": "bloqueado_por_imagen"}), 200

        # Verificar bloqueo temporal
        if sender in bloqueados_temporalmente and now < bloqueados_temporalmente[sender]:
            logger.info(f"⏳ Usuario {sender} bloqueado temporalmente")
            return jsonify({"status": "esperando_bloqueo"}), 200
        else:
            bloqueados_temporalmente.pop(sender, None)

        # Salir del modo soporte
        if sender in clientes_en_soporte and any(palabra in user_msg for palabra in ["solucionado", "ya me ayudaron", "gracias", "ya lo resolvi", "resuelto", "listo"]):
            clientes_en_soporte.remove(sender)
            enviar_mensaje_whatsapp(sender, "✅ Nos alegra que se haya solucionado. Ya puedes continuar con normalidad 😊")
            return jsonify({"status": "soporte_finalizado"}), 200

        # Mantener en modo soporte
        if sender in clientes_en_soporte:
            logger.info(f"🔧 Usuario {sender} en modo soporte")
            return jsonify({"status": "modo_soporte_activo"}), 200

        # Activar modo soporte
        if "soporte" in user_msg or "ayuda" in user_msg:
            clientes_en_soporte.add(sender)
            enviar_mensaje_whatsapp(sender, "🔧 *MODO SOPORTE ACTIVADO*\n\n📸 Por favor, envíanos una foto del error y una breve descripción de lo que sucede. Un asesor te atenderá pronto.\n\nEscribe 'solucionado' cuando se resuelva tu problema.")
            return jsonify({"status": "modo_soporte_activado"}), 200

        # Verificar horario de atención (7 AM - 11 PM Colombia)
        if now.hour < 7 or now.hour >= 23:
            if sender not in ultimo_fuera_horario or now - ultimo_fuera_horario[sender] > timedelta(minutes=30):
                enviar_mensaje_whatsapp(sender, "😴 Nuestro equipo está descansando en este momento (11:00 PM - 7:00 AM). Te atenderemos en el horario habitual. ¡Gracias por tu paciencia!")
                ultimo_fuera_horario[sender] = now
            return jsonify({"status": "fuera_de_horario"}), 200

        # Derivación a humano
        if any(palabra in user_msg for palabra in ["urgente", "asesor", "humano", "ayuda urgente", "hablar con alguien", "operador"]):
            enviar_mensaje_whatsapp(sender, "📩 Ya estamos informando a uno de nuestros asesores para que te contacte. ¡Gracias por tu paciencia!")
            return jsonify({"status": "derivado_a_humano"}), 200

        # Métodos de pago
        if any(palabra in user_msg for palabra in ["metodos de pago", "método de pago", "como pago", "metodos", "medios de pago"]):
            enviar_metodos_pago(sender)
            return jsonify({"status": "metodos_pago_enviado"}), 200

        # Intención de pago/compra
        if any(palabra in user_msg for palabra in [
            "pagar", "quiero pagar", "listo", "quiero comprar", "comprar ahora", 
            "lo compro", "ya lo compro", "si lo compro", "quiero comprarlo", 
            "quiero comprar ahora", "quiero comprar ya", "hacer pedido", "realizar pedido"]):
            enviar_metodos_pago(sender)
            return jsonify({"status": "pago_enviado"}), 200

        # Búsqueda de plataformas mejorada
        plataforma_encontrada = None
        for clave, (precio, imagen) in plataformas.items():
            if clave in user_msg:
                plataforma_encontrada = (clave, precio, imagen)
                break
        
        if plataforma_encontrada:
            clave, precio, imagen = plataforma_encontrada
            enviar_ficha_plataforma(sender, clave.upper(), precio, imagen)
            return jsonify({"status": "plataforma_enviada", "plataforma": clave}), 200

        # Inicializar memoria de conversación
        if sender not in conversation_memory:
            conversation_memory[sender] = []

        # Mensaje de bienvenida mejorado
        if sender not in ultimo_saludo or now - ultimo_saludo[sender] > timedelta(minutes=30):
            mensaje_bienvenida = """¡Hola! 👋 Gracias por comunicarte con *Multiplay Multimarca*. 🌟  

Somos tu tienda digital de confianza para cuentas premium de entretenimiento.

🎁 Te ofrecemos acceso a las mejores plataformas, con garantía, entrega inmediata y soporte 24/7.

📲 *ESCRIBE EL NOMBRE DE LA PLATAFORMA QUE TE INTERESA:*

> 🎨 Canva 
> 🎬 Netflix
> 🎞️ HBO Max 
> 📺 YouTube Premium 
> 🎥 ViX+ 
> ⚽ DGO (WIN Sports)
> 📼 Disney+
> 🎧 Spotify 
> 📦 Prime Video 
> 🔞 Pornhub Premium 
> 🔥 OnlyFans (con saldo) 
> 💼 Office 365 
> 🦉 Duolingo 

🔧 *SOPORTE TÉCNICO*: Si tienes algún problema, escribe "soporte"

✨ ¡Gracias por elegirnos!"""
            
            enviar_mensaje_whatsapp(sender, mensaje_bienvenida)
            ultimo_saludo[sender] = now
            return jsonify({"status": "bienvenida_enviada"}), 200

        # Respuesta con IA
        conversation_memory[sender].append({"role": "user", "content": user_msg})
        
        respuesta = generar_respuesta_ia(user_msg, conversation_memory[sender])
        conversation_memory[sender].append({"role": "assistant", "content": respuesta})
        
        enviar_mensaje_whatsapp(sender, respuesta)

        # Limpiar memoria si es muy larga
        if len(conversation_memory[sender]) > 20:
            conversation_memory[sender] = conversation_memory[sender][-10:]

        return jsonify({"status": "success"}), 200

    except KeyError as e:
        logger.error(f"❌ Campo faltante en webhook: {e}")
        return jsonify({"status": "error", "message": f"Campo faltante: {e}"}), 400
    except Exception as e:
        logger.error(f"❌ Error en webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    try:
        now = obtener_hora_colombia()
        return jsonify({
            "status": "ok",
            "time": now.isoformat(),
            "active_users": len(conversation_memory),
            "soporte_activo": len(clientes_en_soporte),
            "bloqueados": len(bloqueados_temporalmente),
            "version": "1.1"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/')
def home():
    return """
    <html>
    <head><title>MULTIPLAY MULTIMARCA Bot</title></head>
    <body>
        <h2>✅ MULTIPLAY MULTIMARCA Bot en ejecución</h2>
        <p>Status: Activo</p>
        <p>Versión: 1.1</p>
        <a href="/health">Ver Estado del Sistema</a>
    </body>
    </html>
    """

# Endpoint para limpiar memoria (útil para mantenimiento)
@app.route('/clear-memory', methods=['POST'])
def clear_memory():
    try:
        conversation_memory.clear()
        clientes_en_soporte.clear()
        bloqueados_temporalmente.clear()
        ultimo_saludo.clear()
        ultimo_fuera_horario.clear()
        return jsonify({"status": "memoria_limpiada", "message": "Todas las memorias han sido limpiadas"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    logger.info("🚀 MULTIPLAY MULTIMARCA bot iniciado - Versión 1.1")
    app.run(host='0.0.0.0', port=5000, debug=False)