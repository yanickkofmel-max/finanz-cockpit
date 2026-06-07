import logging

# Konfiguration, wie die Fehlermeldungen im Terminal aussehen sollen
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger("FinanzCockpit")