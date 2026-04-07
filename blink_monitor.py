import asyncio
import logging
from datetime import datetime
from colorama import init, Fore, Style
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, Application
from playwright.async_api import async_playwright
import os
from dotenv import load_dotenv
from aiohttp import web

# Chargement de la configuration
load_dotenv()

# Initialisation de colorama pour Windows
init()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)

# ==========================================
# CONFIGURATION
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TARGET_URL = os.getenv("TARGET_URL", "https://chargefinder.com/fr/station/zk39dp")
CHECK_INTERVAL_SECONDS = 120  # 2 minutes

# État global
was_available = False
is_monitoring = True
status_since = datetime.now()

def get_duration_str():
    if not status_since:
        return "quelques instants"
    diff = datetime.now() - status_since
    minutes = int(diff.total_seconds() / 60)
    if minutes < 1:
        return "moins d'une minute"
    elif minutes < 60:
        return f"{minutes} minute(s)"
    else:
        hours = minutes // 60
        r_mins = minutes % 60
        return f"{hours}h{str(r_mins).zfill(2)}"

# ==========================================
# MINI-SERVEUR WEB POUR RENDER ET CRON-JOB
# ==========================================
async def health_check(request):
    """Page web ultra simple pour prouver à Render que l'application est vivante."""
    return web.Response(text="Bot ChargeAlert En Ligne !", content_type='text/html')

async def start_webserver(application: Application):
    """Démarre le serveur 'fake' sur le port donné par Render, en parallèle du Bot."""
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"{Fore.MAGENTA}🌐 (Render) Mini Serveur HTTP de survie démarré sur le port {port}.{Style.RESET_ALL}")


async def scrape_availability():
    """Scrape la page avec le Navigateur Fantôme Playwright."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            await page.goto(TARGET_URL, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(3000)
            
            content = await page.content()
            html_text = content.lower()
            
            await browser.close()
            
            if "disponible" in html_text or "available" in html_text:
                return True
            return False
            
    except Exception as e:
        print(f"{Fore.RED}[-] Erreur Navigateur Playwright : {e}{Style.RESET_ALL}")
        return None

async def check_job(context_obj: ContextTypes.DEFAULT_TYPE):
    """Boucle exécutée par la JobQueue de Telegram."""
    global was_available, is_monitoring, status_since
    
    if not is_monitoring:
        return
        
    now = datetime.now().strftime("%H:%M:%S")
    is_available = await scrape_availability()
    
    if is_available is None:
        print(f"[{now}] - {Fore.RED}Statut : Erreur{Style.RESET_ALL} - (Nouvelle tentative au prochain cycle)")
        return
        
    if is_available:
        print(f"[{now}] - {Fore.GREEN}Statut : Disponible{Style.RESET_ALL}")
        if not was_available:
            duration = get_duration_str()
            print(f"{Fore.MAGENTA}   [!] CHANGEMENT DE STATUT : Envoi de l'alerte telegram...{Style.RESET_ALL}")
            message = f"✅ <b>Borne Blink (Genappe) DISPONIBLE !</b>\n(Elle était occupée pendant {duration})\n\nLien : {TARGET_URL}"
            await context_obj.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="HTML")
            print(f"{Fore.MAGENTA}   [>] 📩 Message expédié avec succès sur Telegram !{Style.RESET_ALL}")
            was_available = True
            status_since = datetime.now()
    else:
        print(f"[{now}] - {Fore.YELLOW}Statut : Occupé{Style.RESET_ALL}")
        if was_available:
            was_available = False
            status_since = datetime.now()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>ChargeAlert Control Panel</b>\n\n"
        "Je suis actif sur Render.com !\n"
        "👉 /status : Obtenir le statut en temps réel.\n"
        "👉 /pause : Mettre en pause la vérification automatique.\n"
        "👉 /resume : Relancer la surveillance.",
        parse_mode="HTML"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Le Navigateur fantôme s'ouvre pour vérifier Chargefinder. Cela prend quelques secondes...")
    now = datetime.now().strftime("%H:%M:%S")
    print(f"{Fore.CYAN}>> (Telegram) Commande /status initiée par l'utilisateur à {now}...{Style.RESET_ALL}")
    
    is_av = await scrape_availability()
    
    if is_av is None:
        await update.message.reply_text("❌ Impossible de joindre le site Chargefinder.")
    elif is_av:
        duration = get_duration_str()
        await update.message.reply_text(f"✅ La borne est actuellement <b>DISPONIBLE</b> (depuis {duration}) !\n{TARGET_URL}", parse_mode="HTML")
    else:
        duration = get_duration_str()
        await update.message.reply_text(f"⏳ La borne est toujours occupée (depuis {duration}).")

async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_monitoring
    is_monitoring = False
    print(f"{Fore.YELLOW}>> (Telegram) La veille automatique a été suspendue.{Style.RESET_ALL}")
    await update.message.reply_text("⏸️ Surveillance mise en pause.")

async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_monitoring
    is_monitoring = True
    print(f"{Fore.GREEN}>> (Telegram) La veille automatique a été relancée.{Style.RESET_ALL}")
    await update.message.reply_text("▶️ Surveillance relancée. Je continue de guetter !")


if __name__ == '__main__':
    print(f"{Fore.CYAN}===========================================")
    print(f"{Fore.CYAN}⚡ Démarrage de ChargeAlert (Mode Render.com)")
    print(f"{Fore.CYAN}===========================================")
    print(f"{Fore.YELLOW}✅ Initialisation du Bot Telegram...{Style.RESET_ALL}")

    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "VOTRE_TELEGRAM_TOKEN":
        print(f"{Fore.RED}[!] Token Telegram non configuré. Assurez-vous d'avoir défini les variables d'environnement.{Style.RESET_ALL}")
        exit(1)

    # Initialisation de l'application et lancement du mini serveur web en Pre-Boot
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(start_webserver).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))

    app.job_queue.run_repeating(check_job, interval=CHECK_INTERVAL_SECONDS, first=1)

    app.run_polling()
