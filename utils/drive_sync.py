import streamlit as st
import io
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload
from utils.logger import logger

# --- KONFIGURATION (Hier ist alles sicher an einem Platz) ---
LOCAL_DB = 'vereinsverwaltung.db'
JSON_PATH = 'google_creds.json'
DEINE_GOOGLE_EMAIL = 'yanick.kofmel@gmail.com'  # Falls abweichend, nur hier ändern!

def get_drive_service():
    """Authentifiziert sich direkt über die JSON-Datei im Repository."""
    SCOPES = ['https://www.googleapis.com/auth/drive']
    try:
        if not os.path.exists(JSON_PATH):
            logger.error(f"Authentifizierungsdatei {JSON_PATH} wurde auf GitHub nicht gefunden!")
            return None
        creds = service_account.Credentials.from_service_account_file(
            JSON_PATH, 
            scopes=SCOPES
        )
        return creds
    except Exception as e:
        logger.error(f"Authentifizierungsfehler über JSON-Datei: {e}")
        return None

def upload_db():
    """Backup der Datenbank auf Google Drive."""
    try:
        creds = get_drive_service()
        if not creds: return False
        
        file_id = st.secrets["google_oauth"].get("file_id_database")
        if not file_id:
            logger.error("file_id_database fehlt in Secrets!")
            return False

        service = build('drive', 'v3', credentials=creds, static_discovery=False)
        
        if not os.path.exists(LOCAL_DB):
            return False
            
        media = MediaFileUpload(LOCAL_DB, mimetype='application/x-sqlite3', resumable=True)
        service.files().update(fileId=file_id, media_body=media, supportsAllDrives=True).execute()
        return True
    except Exception as e:
        logger.error(f"DB Upload Fehler: {e}")
        return False

def download_db():
    """Download der Datenbank von Google Drive."""
    try:
        creds = get_drive_service()
        if not creds: return False
        
        file_id = st.secrets["google_oauth"].get("file_id_database")
        if not file_id: return False

        service = build('drive', 'v3', credentials=creds, static_discovery=False)
        
        request = service.files().get_media(fileId=file_id)
        fh = io.FileIO(LOCAL_DB, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        return True
    except Exception as e:
        logger.error(f"DB Download Fehler: {e}")
        return False

def get_or_create_year_folder(year):
    """Management der Jahresordner im Hauptordner."""
    try:
        creds = get_drive_service()
        if not creds: return None
        
        folder_id = st.secrets["google_oauth"].get("folder_id_rechnungen")
        service = build('drive', 'v3', credentials=creds, static_discovery=False)
        
        query = f"name = '{year}' and '{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = service.files().list(q=query, fields='files(id)', supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        files = results.get('files', [])
        
        if files:
            return files[0]['id']
        else:
            folder_metadata = {
                'name': str(year),
                'parents': [folder_id],
                'mimeType': 'application/vnd.google-apps.folder'
            }
            new_folder = service.files().create(body=folder_metadata, fields='id', supportsAllDrives=True).execute()
            return new_folder.get('id')
    except Exception as e:
        logger.error(f"Fehler im Jahresordner-Management: {e}")
        return None

def upload_file_to_drive(file_content, filename, target_folder_id=None):
    """PDF Upload Funktion mit Quota-Bypass via Eigentumsübertragung."""
    try:
        creds = get_drive_service()
        if not creds: return None
        
        if not target_folder_id:
            target_folder_id = st.secrets["google_oauth"].get("folder_id_rechnungen")
            
        service = build('drive', 'v3', credentials=creds, static_discovery=False)
        
        file_metadata = {
            'name': filename,
            'parents': [target_folder_id]
        }
        
        media = MediaIoBaseUpload(io.BytesIO(file_content), mimetype='application/pdf', resumable=True)
        
        # 1. Datei initial erstellen
        file_result = service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()
        
        file_id = file_result.get('id')
        
        # 2. Direkter Transfer des Besitzes auf dein Konto, um die Quota zu umgehen
        try:
            service.permissions().create(
                fileId=file_id,
                body={
                    'type': 'user',
                    'role': 'owner',
                    'emailAddress': DEINE_GOOGLE_EMAIL
                },
                transferOwnership=True,
                supportsAllDrives=True
            ).execute()
        except Exception as perm_e:
            logger.warning(f"Quota-Transfer fehlgeschlagen (evtl. wegen fehlendem Editor-Recht): {perm_e}")

        # 3. Link-Freigabe für die App aktivieren
        service.permissions().create(
            fileId=file_id, 
            body={'type': 'anyone', 'role': 'reader'},
            supportsAllDrives=True
        ).execute()
        
        return file_result.get('webViewLink')
    except Exception as e:
        logger.error(f"Upload Fehler bei {filename}: {e}")
        return None

def download_drive_file(file_id):
    """Download für Ablage."""
    try:
        creds = get_drive_service()
        if not creds: return None
        service = build('drive', 'v3', credentials=creds, static_discovery=False)
        request = service.files().get_media(fileId=file_id)
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        return file_stream.getvalue()
    except Exception as e:
        logger.error(f"Download Fehler: {e}")
        return None