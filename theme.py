import streamlit as st
from datetime import datetime

def apply_banking_styles():
    st.markdown("""
        <style>
        .amount-pos { color: #2ECC71; font-weight: 600; }
        .amount-neg { color: #FF6B6B; font-weight: 600; }
        
        [data-testid="stVerticalBlock"] { gap: 0.5rem; }
        
        /* --- KOMPAKTES, EDLES FINTECH KACHEL-DESIGN --- */
        .bank-tile {
            background: linear-gradient(145deg, #161920, #0E1117);
            border: 1px solid #222630;
            border-radius: 14px; 
            padding: 16px; 
            margin-bottom: 14px; 
            width: 100%;
            color: white;
            display: flex;
            flex-direction: column;
            gap: 14px; 
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.2);
            transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
        }
        
        .bank-tile:hover {
            transform: translateY(-2px);
            border-color: #3A4150;
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.35);
        }
        
        .header-box { 
            display: flex; 
            align-items: center; 
            gap: 12px; 
        }
        
        .logo-wrapper {
            background: #FFFFFF;
            border-radius: 10px;
            padding: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 54px; 
            height: 54px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.12);
            flex-shrink: 0;
        }
        
        .logo-img { 
            width: 100%; 
            height: 100%; 
            object-fit: contain; 
        }
        
        .title-text { 
            font-size: 1.0rem; 
            font-weight: 500; 
            color: #E2E8F0;
            letter-spacing: 0.3px;
        }
        
        .grid-box { 
            display: flex; 
            justify-content: space-between;
            background: #1A1E26;
            border-radius: 10px;
            padding: 10px 14px; 
            border: 1px solid #252A35;
        }
        
        .val-col {
            display: flex;
            flex-direction: column;
            gap: 2px; 
        }
        
        .val-col.right {
            text-align: right;
            align-items: flex-end;
        }
        
        .label-text { 
            font-size: 0.65rem; 
            color: #8A8F98; 
            text-transform: uppercase; 
            letter-spacing: 0.6px;
            font-weight: 600;
        }
        
        .val-text { 
            font-size: 1.05rem; 
            font-weight: 700; 
            color: #FFFFFF; 
        }
        
        /* --- Sidebar Navigation --- */
        [data-testid="stSidebar"] div[role="radiogroup"] { gap: 0.1rem !important; }
        [data-testid="stSidebar"] div[role="radiogroup"] label {
            padding-top: 0.2rem !important;
            padding-bottom: 0.2rem !important;
            margin-bottom: 0px !important;
            background-color: transparent;
        }
        [data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] input:checked + div {
            color: #2ECC71; 
            font-weight: bold;
        }

        .txn-title { font-weight: 500; color: var(--text-color); font-size: 0.95rem; }
        .txn-meta { color: var(--text-color); opacity: 0.6; font-size: 0.78rem; margin-top: 3px; display: flex; align-items: center; gap: 6px; }
        
        .status-tag-geplant {
            background-color: rgba(255, 193, 7, 0.12); color: #FFC107; padding: 1px 6px;
            border-radius: 4px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px;
        }
        .status-tag-bestaetigt {
            background-color: rgba(40, 167, 69, 0.12); color: #28A745; padding: 1px 6px;
            border-radius: 4px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px;
        }

        .stButton > button {
            border: 1px solid var(--secondary-background-color) !important;
            background-color: transparent !important;
            color: var(--text-color) !important;
            opacity: 0.8;
            font-size: 0.85rem !important;
            padding: 6px 12px !important;
            border-radius: 10px !important;
            transition: all 0.2s ease-in-out !important;
            width: 100% !important;
            min-height: 34px !important;
            margin-top: 4px !important; 
        }
        .stButton > button:hover {
            background-color: var(--secondary-background-color) !important;
            opacity: 1;
        }
        </style>
    """, unsafe_allow_html=True)

def render_table_header():
    st.markdown("""
        <div style='display: flex; padding: 0px 8px 10px 8px; color: var(--text-color); opacity: 0.7; font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--secondary-background-color); margin-bottom: 8px;'>
            <div style='flex: 3.5;'>Beschreibung</div>
            <div style='flex: 1.5; text-align: right; padding-right: 15px;'>Betrag</div>
            <div style='flex: 2.2; text-align: center;'>Aktionen</div>
        </div>
    """, unsafe_allow_html=True)

def render_transaction_row(row, on_confirm, on_delete):
    is_geplant = row['status'] == "geplant"
    badge_html = '<span class="status-tag-geplant">Geplant</span>' if is_geplant else '<span class="status-tag-bestaetigt">Gebucht</span>'
    
    # ---> NEU: Dynamische Währung je nach Konto <---
    waehrung = "USD" if row.get('konto') == "Yuh USD" else "CHF"
    betrag = row['betrag']
    betrag_str = f"{betrag:+,.2f} {waehrung}".replace('+', '+ ').replace('-', '- ')
    betrag_style = "amount-pos" if betrag >= 0 else "amount-neg"
    
    ist_dauer = "Dauerauftrag" in str(row.get('modus', ''))
    dauer_symbol = "🔄 " if ist_dauer else ""
    
    try:
        dt = datetime.strptime(row['datum'], "%Y-%m-%d")
        datum_anzeige = dt.strftime("%d.%m.%Y")
    except:
        datum_anzeige = row['datum']

    col_text, col_amount, col_actions = st.columns([3.5, 1.5, 2.2])
    
    with col_text:
        st.markdown(f"""
            <div style="padding: 4px 0px;">
                <div class="txn-title">{dauer_symbol}{row['beschreibung']}</div>
                <div class="txn-meta">📅 {datum_anzeige} &nbsp;&bull;&nbsp; {badge_html}</div>
            </div>
        """, unsafe_allow_html=True)
        
    with col_amount:
        st.markdown(f"""
            <div class="{betrag_style}" style="font-size: 1.05rem; text-align: right; padding-top: 12px; padding-right: 15px;">
                {betrag_str}
            </div>
        """, unsafe_allow_html=True)
        
    with col_actions:
        st.markdown("<div style='padding-top: 8px;'></div>", unsafe_allow_html=True)
        btn_col1, btn_col2 = st.columns(2)
        
        with btn_col1:
            btn_label = "✔ Buchen" if is_geplant else "↺ Zurück"
            if st.button(btn_label, key=f"conf_{row['id']}", use_container_width=True):
                on_confirm(row['id'], row['status'])
                
        with btn_col2:
            if st.button("🗑 Löschen", key=f"del_{row['id']}", use_container_width=True):
                on_delete(row['id'])
                
    st.markdown("<div style='border-bottom: 1px solid var(--secondary-background-color); margin-top: 4px; margin-bottom: 4px;'></div>", unsafe_allow_html=True)