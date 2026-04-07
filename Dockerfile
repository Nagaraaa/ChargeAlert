FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# Définir le répertoire de travail
WORKDIR /app

# Copier les fichiers de dépendances
COPY requirements.txt .

# Installer les dépendances Python
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Installer les navigateurs Playwright (au cas où, l'image le contient déjà, mais par précaution)
RUN playwright install chromium

# Copier le reste du code de l'application
COPY . .

# Exposer le port par défaut (Render écoutera sur le port web, même si notre bot est asynchrone)
EXPOSE 10000

# Commande de démarrage
CMD ["python", "blink_monitor.py"]
