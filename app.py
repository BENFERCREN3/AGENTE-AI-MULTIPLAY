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

# Variables de estado
conversation_memory = {}
clientes_en_soporte = set()
bloqueados_temporalmente = {}
ultimo_saludo = {}
ultimo_fuera_horario = {}
ultimo_mensaje_usuario = {}  # Anti-spam
respuestas_enviadas = {}     # Control de respuestas repetidas
respuestas_generadas = {}    # Últimas respuestas por usuario
cache_respuestas = {}        # Movido aquí para estar disponible globalmente

# Función para quitar tildes
def quitar_tildes(texto):
    try:
        if not texto or not isinstance(texto, str):
            return ""
        return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    except Exception as e:
        logger.error(f"Error procesando texto: {e}")
        return str(texto) if texto else ""

# Función para generar clave de cache
def generar_cache_key(texto):
    return hashlib.md5(texto.encode()).hexdigest()

# Función para verificar horario comercial
def es_horario_comercial():
    """Verifica si está dentro del horario comercial (8:00 - 20:00 hora Colombia)"""
    try:
        # Asumiendo UTC-5 para Colombia
        ahora = datetime.now()
        hora_colombia = ahora - timedelta(hours=5)  # Ajustar según tu zona horaria
        hora_actual = hora_colombia.hour
        return 8 <= hora_actual <= 20
    except Exception as e:
        logger.error(f"Error verificando horario: {e}")
        return True  # Por defecto, permitir operación

# Función para verificar anti-spam
def es_spam(numero, mensaje):
    """Verifica si el mensaje es spam basado en frecuencia"""
    ahora = time.time()
    
    # Verificar último mensaje del usuario
    if numero in ultimo_mensaje_usuario:
        tiempo_transcurrido = ahora - ultimo_mensaje_usuario[numero]
        if tiempo_transcurrido < 3:  # Menos de 3 segundos
            return True
    
    ultimo_mensaje_usuario[numero] = ahora
    return False

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

# Prompt del sistema
system_prompt = """
Eres un asistente virtual experto en ventas para MULTIPLAY MULTIMARCA, tienda colombiana de cuentas premium de entretenimiento digital.

✨ MISIÓN:
- Atender con amabilidad y rapidez
- Informar precios y beneficios claramente
- Guiar hacia la compra
- Resolver dudas frecuentes

📋 PLATAFORMAS DISPONIBLES:
- Netflix: $13.000 COP
- Spotify: $9.000 COP
- YouTube Premium: $9.000 COP
- Canva Pro: $15.000 COP
- VIX+: $9.000 COP
- Disney+: $9.000 COP
- HBO Max: $9.000 COP
- Prime Video: $9.000 COP
- PornHub Premium: $12.000 COP
- Office 365: $20.000 COP
- Duolingo Plus: $10.000 COP
- OnlyFans: $20.000 COP
- DirectTV GO: $30.000 COP

✅ GARANTÍAS:
- Entrega inmediata
- Soporte 24/7
- Duración 30 días
- Privacidad garantizada

🎯 INSTRUCCIONES:
- Usa emojis moderadamente
- Responde como un asesor humano natural
- Si preguntan por una plataforma específica, menciona precio y beneficios
- Para métodos de pago, guía hacia el comando "metodos de pago"
- Para soporte técnico, guía hacia "soporte"
- Mantén respuestas concisas y útiles
"""

def generar_respuesta_ia(mensaje_usuario, numero_usuario, historial=[]):
    """Genera respuesta usando OpenAI con contexto del usuario"""
    try:
        # Verificar cache
        cache_key = generar_cache_key(f"{numero_usuario}_{mensaje_usuario}")
        if cache_key in cache_respuestas:
            return cache_respuestas[cache_key]

        # Obtener historial del usuario
        historial_usuario = conversation_memory.get(numero_usuario, [])
        
        # Construir mensajes para OpenAI
        messages = [{"role": "system", "content": system_prompt}]
        
        # Agregar historial reciente (últimos 6 mensajes)
        for msg in historial_usuario[-6:]:
            messages.append(msg)
        
        # Agregar mensaje actual
        messages.append({"role": "user", "content": mensaje_usuario})
        
        # Llamar a OpenAI
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.3,
            max_tokens=500
        )
        
        resultado = response.choices[0].message.content.strip()
        
        # Guardar en cache si el mensaje es significativo
        if len(mensaje_usuario) > 10:
            cache_respuestas[cache_key] = resultado
        
        # Actualizar historial
        if numero_usuario not in conversation_memory:
            conversation_memory[numero_usuario] = []
        
        conversation_memory[numero_usuario].append({"role": "user", "content": mensaje_usuario})
        conversation_memory[numero_usuario].append({"role": "assistant", "content": resultado})
        
        # Mantener solo los últimos 20 mensajes
        if len(conversation_memory[numero_usuario]) > 20:
            conversation_memory[numero_usuario] = conversation_memory[numero_usuario][-20:]
        
        return resultado
        
    except Exception as e:
        logger.error(f"❌ Error con OpenAI: {e}")
        return "😓 Lo siento, hubo un problema técnico. Pronto te ayudamos."

def enviar_mensaje_whatsapp(numero, mensaje):
    """Envía mensaje por WhatsApp con control de duplicados"""
    try:
        # Verificar duplicados
        clave = (numero, mensaje)
        if clave in respuestas_enviadas and time.time() - respuestas_enviadas[clave] < 60:
            logger.info(f"⏳ Mensaje repetido bloqueado para {numero}")
            return None
        
        # Verificar respuesta exacta repetida
        if respuestas_generadas.get(numero) == mensaje:
            logger.info(f"⏳ Respuesta exacta repetida detectada para {numero}")
            return None
        
        # Actualizar registros
        respuestas_enviadas[clave] = time.time()
        respuestas_generadas[numero] = mensaje

        # Enviar mensaje
        payload = {
            "token": ULTRAMSG_TOKEN,
            "to": numero,
            "body": mensaje
        }
        
        response = requests.post(ULTRAMSG_CHAT_URL, json=payload, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"✅ Mensaje enviado a {numero}")
            return response.json()
        else:
            logger.error(f"❌ Error HTTP {response.status_code} enviando mensaje")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error enviando mensaje a {numero}: {e}")
        return None

def enviar_ficha_plataforma(numero, nombre, precio, url_imagen):
    """Envía ficha visual de la plataforma"""
    try:
        texto = f"""🔴 *{nombre.upper()}*: Accede al catálogo global con 1 mes de servicio por solo *${precio} COP* 🎥✨

♾️ *Garantía incluida*
🛠️ *Estabilidad asegurada*
🕐 *Soporte rápido 24/7*
📲 *Entrega inmediata*

💳 Escribe *"metodos de pago"* para conocer nuestras opciones de pago"""

        payload = {
            "token": ULTRAMSG_TOKEN,
            "to": numero,
            "image": url_imagen,
            "caption": texto
        }
        
        response = requests.post(ULTRAMSG_IMG_URL, data=payload, timeout=15)
        
        if response.status_code == 200:
            logger.info(f"✅ Ficha enviada: {nombre} a {numero}")
            return response.json()
        else:
            logger.error(f"❌ Error enviando ficha: HTTP {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error enviando ficha de {nombre}: {e}")
        return None

def enviar_metodos_pago(numero):
    """Envía información de métodos de pago"""
    try:
        texto = """💳 *MÉTODOS DE PAGO DISPONIBLES*

🟦 *Nequi:* 3144413062 (JH** VAR***)
🟥 *Daviplata:* 3144413062  
🟨 *Bancolombia:* 912-683039-91 (Cuenta de Ahorros)

📱 *INSTRUCCIONES:*
1️⃣ Realiza tu pago por cualquier método
2️⃣ Envía el comprobante a este WhatsApp
3️⃣ Confirmaremos tu pedido inmediatamente

⚡ *¡Entrega inmediata después del pago!*

❓ Si tienes dudas, escribe *"soporte"* y te atenderemos"""

        url_pago = "https://i.postimg.cc/SRyhCnY9/Medio-De-Pago-Actualizado.png"
        
        payload = {
            "token": ULTRAMSG_TOKEN,
            "to": numero,
            "image": url_pago,
            "caption": texto
        }
        
        response = requests.post(ULTRAMSG_IMG_URL, data=payload, timeout=15)
        
        if response.status_code == 200:
            logger.info(f"✅ Métodos de pago enviados a {numero}")
            return response.json()
        else:
            logger.error(f"❌ Error enviando métodos de pago: HTTP {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error enviando métodos de pago: {e}")
        return None

def procesar_mensaje(numero, mensaje):
    """Procesa mensaje entrante y genera respuesta apropiada"""
    try:
        # Verificar spam
        if es_spam(numero, mensaje):
            logger.info(f"🚫 Spam detectado de {numero}")
            return None
        
        # Verificar si está bloqueado temporalmente
        if numero in bloqueados_temporalmente:
            if datetime.now() < bloqueados_temporalmente[numero]:
                return None
            else:
                bloqueados_temporalmente.pop(numero)
        
        # Limpiar mensaje
        mensaje_limpio = quitar_tildes(mensaje.lower().strip())
        
        # Verificar comandos especiales
        if "metodos de pago" in mensaje_limpio or "como pagar" in mensaje_limpio:
            return enviar_metodos_pago(numero)
        
        if "soporte" in mensaje_limpio:
            clientes_en_soporte.add(numero)
            respuesta = "🔧 *MODO SOPORTE ACTIVADO*\n\n👨‍💻 Un agente humano te atenderá pronto.\n\n⏰ Horario de atención: 8:00 AM - 8:00 PM\n\n📞 Para emergencias: 3144413062"
            return enviar_mensaje_whatsapp(numero, respuesta)
        
        # Verificar si menciona alguna plataforma
        for plataforma, (precio, imagen) in plataformas.items():
            if plataforma in mensaje_limpio:
                return enviar_ficha_plataforma(numero, plataforma, precio, imagen)
        
        # Verificar horario comercial
        if not es_horario_comercial():
            if numero not in ultimo_fuera_horario or (datetime.now() - ultimo_fuera_horario[numero]).seconds > 3600:
                ultimo_fuera_horario[numero] = datetime.now()
                respuesta = "🌙 *FUERA DE HORARIO*\n\nNuestro horario de atención es de *8:00 AM a 8:00 PM*.\n\n📱 Puedes escribirnos y te responderemos en horario comercial.\n\n⚡ Para emergencias: 3144413062"
                return enviar_mensaje_whatsapp(numero, respuesta)
        
        # Generar respuesta con IA
        respuesta = generar_respuesta_ia(mensaje, numero)
        return enviar_mensaje_whatsapp(numero, respuesta)
        
    except Exception as e:
        logger.error(f"❌ Error procesando mensaje de {numero}: {e}")
        return None

# Función de limpieza de memoria
def limpiar_memoria():
    """Limpia memoria cada hora"""
    while True:
        try:
            time.sleep(3600)  # Cada hora
            ahora = datetime.now()
            
            # Limpiar bloqueos temporales expirados
            expirados = [k for k, v in bloqueados_temporalmente.items() if ahora > v]
            for k in expirados:
                bloqueados_temporalmente.pop(k)
                logger.info(f"🧹 Eliminado bloqueo temporal: {k}")
            
            # Limpiar respuestas enviadas antiguas (más de 5 minutos)
            tiempo_limite = time.time() - 300
            expiradas = [k for k, v in respuestas_enviadas.items() if v < tiempo_limite]
            for k in expiradas:
                respuestas_enviadas.pop(k)
            
            # Limpiar respuestas generadas antiguas
            for numero in list(respuestas_generadas.keys()):
                if numero not in [k[0] for k in respuestas_enviadas.keys()]:
                    respuestas_generadas.pop(numero, None)
            
            # Limpiar cache de respuestas (mantener solo 1000 entradas)
            if len(cache_respuestas) > 1000:
                # Eliminar las más antiguas (simple FIFO)
                keys_to_remove = list(cache_respuestas.keys())[:500]
                for k in keys_to_remove:
                    cache_respuestas.pop(k, None)
            
            # Limpiar conversaciones muy largas
            for numero in list(conversation_memory.keys()):
                if len(conversation_memory[numero]) > 50:
                    conversation_memory[numero] = conversation_memory[numero][-30:]
            
            logger.info("🧹 Limpieza de memoria completada")
            
        except Exception as e:
            logger.error(f"❌ Error en limpieza de memoria: {e}")

# Ruta principal del webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook principal para recibir mensajes"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data received"}), 400
        
        # Extraer información del mensaje
        numero = data.get('from', '').replace('@c.us', '')
        mensaje = data.get('body', '')
        
        if not numero or not mensaje:
            return jsonify({"error": "Missing required fields"}), 400
        
        logger.info(f"📨 Mensaje recibido de {numero}: {mensaje[:50]}...")
        
        # Procesar mensaje en hilo separado para no bloquear
        threading.Thread(
            target=procesar_mensaje, 
            args=(numero, mensaje),
            daemon=True
        ).start()
        
        return jsonify({"status": "success", "message": "Message processed"}), 200
        
    except Exception as e:
        logger.error(f"❌ Error en webhook: {e}")
        return jsonify({"error": "Internal server error"}), 500

# Ruta de estado
@app.route('/status', methods=['GET'])
def status():
    """Endpoint para verificar estado del bot"""
    return jsonify({
        "status": "active",
        "timestamp": datetime.now().isoformat(),
        "usuarios_activos": len(conversation_memory),
        "clientes_en_soporte": len(clientes_en_soporte),
        "bloqueados": len(bloqueados_temporalmente)
    })

# Iniciar hilo de limpieza
threading.Thread(target=limpiar_memoria, daemon=True).start()

if __name__ == '__main__':
    logger.info("🚀 Iniciando MULTIPLAY MULTIMARCA Chatbot...")
    app.run(host='0.0.0.0', port=5000, debug=False)