import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import hashlib
from supabase import create_client, Client
import parselmouth
import numpy as np

st.set_page_config(page_title="Parkinson Telemonitoring", layout="wide")

# Configurazione Supabase - USA I SECRETS
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except:
    # Fallback per test locale (rimuovi in produzione)
    SUPABASE_URL = "https://viexdcbofgsopcrnnbzi.supabase.co"
    SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZpZXhkY2JvZmdzb3Bjcm5uYnppIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njk1ODk4OTUsImV4cCI6MjA4NTE2NTg5NX0.7Xu5B8Vlz0j-wX39-i5W12Mw5cedX7VS9ACOPjSpLEs"

# Client Supabase globale
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Inizializzazione sessione
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.role = None
    st.session_state.selected_role = None


def hash_password(password: str) -> str:
    """Hash SHA256 della password"""
    return hashlib.sha256(password.encode()).hexdigest()


def login_doctor(username: str, password: str) -> bool:
    """Login medico - ritorna True se successo"""
    try:
        pw_hash = hash_password(password)
        
        # Cerca per username o codice fiscale
        response = supabase.table("doctors").select("*").or_(
            f"username.eq.{username},codice_fiscale.eq.{username}"
        ).eq("password_hash", pw_hash).execute()
        
        if response.data:
            return True
        return False
    except Exception as e:
        st.error(f"Errore login: {e}")
        return False


def login_patient(codice_fiscale: str, password: str) -> dict:
    """Login paziente - ritorna dati paziente se successo, None altrimenti"""
    try:
        pw_hash = hash_password(password)
        
        response = supabase.table("patients").select("*").eq(
            "codice_fiscale", codice_fiscale.upper()
        ).eq("password_hash", pw_hash).execute()
        
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        st.error(f"Errore login: {e}")
        return None


def register_patient(codice_fiscale: str, nome: str, cognome: str, 
                     password: str, age: int, sex: str, doctor_username: str) -> bool:
    """Registra nuovo paziente"""
    try:
        pw_hash = hash_password(password)
        sex_int = 1 if sex == "M" else 0
        
        supabase.table("patients").insert({
            "codice_fiscale": codice_fiscale.upper(),
            "nome": nome,
            "cognome": cognome,
            "password_hash": pw_hash,
            "age": age,
            "sex": sex_int,
            "doctor_username": doctor_username
        }).execute()
        
        return True
    except Exception as e:
        st.error(f"Errore registrazione: {e}")
        return False


def extract_voice_features(audio_file):
    """Estrae feature vocali da file audio usando Parselmouth"""
    try:
        # Salva temporaneamente il file
        temp_path = f"/tmp/{audio_file.name}"
        with open(temp_path, "wb") as f:
            f.write(audio_file.getbuffer())
        
        # Analisi con Parselmouth
        sound = parselmouth.Sound(temp_path)
        
        # Estrai pitch
        pitch = sound.to_pitch()
        mean_f0 = parselmouth.praat.call(pitch, "Get mean", 0, 0, "Hertz")
        
        # Estrai formanti
        formant = sound.to_formant_burg()
        f1 = parselmouth.praat.call(formant, "Get mean", 1, 0, 0, "Hertz")
        f2 = parselmouth.praat.call(formant, "Get mean", 2, 0, 0, "Hertz")
        
        # Calcola jitter e shimmer (approssimati)
        point_process = parselmouth.praat.call(sound, "To PointProcess (periodic, cc)", 75, 500)
        jitter = parselmouth.praat.call(point_process, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
        shimmer = parselmouth.praat.call([sound, point_process], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
        
        return {
            "jitter": float(jitter) if not np.isnan(jitter) else 0.005,
            "shimmer": float(shimmer) if not np.isnan(shimmer) else 0.03,
            "nhr": 0.02,  # Placeholder
            "hnr": 21.0,  # Placeholder
            "mean_f0": float(mean_f0) if not np.isnan(mean_f0) else 150.0,
            "f1": float(f1) if not np.isnan(f1) else 500.0,
            "f2": float(f2) if not np.isnan(f2) else 1500.0
        }
    except Exception as e:
        st.warning(f"Errore estrazione feature: {e}. Uso valori di default.")
        return {
            "jitter": 0.005,
            "shimmer": 0.03,
            "nhr": 0.02,
            "hnr": 21.0,
            "mean_f0": 150.0,
            "f1": 500.0,
            "f2": 1500.0
        }


def save_visit(codice_fiscale: str, motor_updrs: float, features: dict) -> bool:
    """Salva visita nel database"""
    try:
        supabase.table("visits").insert({
            "codice_fiscale": codice_fiscale.upper(),
            "motor_updrs": motor_updrs,
            "jitter": features["jitter"],
            "shimmer": features["shimmer"],
            "nhr": features["nhr"],
            "hnr": features["hnr"],
            "mean_f0": features["mean_f0"],
            "f1": features["f1"],
            "f2": features["f2"]
        }).execute()
        
        return True
    except Exception as e:
        st.error(f"Errore salvataggio visita: {e}")
        return False


def get_patient_visits(codice_fiscale: str) -> pd.DataFrame:
    """Recupera storico visite paziente"""
    try:
        response = supabase.table("visits").select("*").eq(
            "codice_fiscale", codice_fiscale.upper()
        ).order("timestamp", desc=False).execute()
        
        if response.data:
            df = pd.DataFrame(response.data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Errore recupero visite: {e}")
        return pd.DataFrame()


def get_doctor_patients(doctor_username: str) -> list:
    """Recupera lista pazienti del medico"""
    try:
        response = supabase.table("patients").select("*").eq(
            "doctor_username", doctor_username
        ).execute()
        
        return response.data if response.data else []
    except Exception as e:
        st.error(f"Errore recupero pazienti: {e}")
        return []


def reset_patient_password(codice_fiscale: str, new_password: str) -> bool:
    """Reset password paziente"""
    try:
        pw_hash = hash_password(new_password)
        
        supabase.table("patients").update({
            "password_hash": pw_hash
        }).eq("codice_fiscale", codice_fiscale.upper()).execute()
        
        return True
    except Exception as e:
        st.error(f"Errore reset password: {e}")
        return False


def create_updrs_trend_chart(df):
    """Grafico trend UPDRS con intervalli di riferimento"""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['motor_updrs'],
        mode='lines+markers',
        name='UPDRS Motorio',
        line=dict(color='#1f77b4', width=3),
        marker=dict(size=8)
    ))

    # Zone di riferimento clinico
    fig.add_hrect(y0=0, y1=20, fillcolor="green", opacity=0.1, line_width=0, annotation_text="Lieve")
    fig.add_hrect(y0=20, y1=40, fillcolor="yellow", opacity=0.1, line_width=0, annotation_text="Moderato")
    fig.add_hrect(y0=40, y1=108, fillcolor="red", opacity=0.1, line_width=0, annotation_text="Severo")

    fig.update_layout(
        title="Evoluzione UPDRS Motorio nel Tempo",
        xaxis_title="Data",
        yaxis_title="Punteggio UPDRS",
        hovermode='x unified',
        height=400
    )

    return fig


def create_feature_comparison(df):
    """Confronto feature vocali"""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['jitter'],
        name='Jitter',
        yaxis='y',
        line=dict(color='#ff7f0e')
    ))

    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['shimmer'],
        name='Shimmer',
        yaxis='y2',
        line=dict(color='#2ca02c')
    ))

    fig.update_layout(
        title="Parametri Vocali nel Tempo",
        xaxis_title="Data",
        yaxis=dict(
            title=dict(text="Jitter", font=dict(color='#ff7f0e'))
        ),
        yaxis2=dict(
            title=dict(text="Shimmer", font=dict(color='#2ca02c')),
            overlaying='y',
            side='right'
        ),
        hovermode='x unified',
        height=350
    )

    return fig


def create_distribution_plot(df):
    """Distribuzione UPDRS"""
    fig = px.histogram(
        df,
        x='motor_updrs',
        nbins=20,
        title="Distribuzione Misurazioni UPDRS",
        labels={'motor_updrs': 'UPDRS Motorio', 'count': 'Frequenza'}
    )
    fig.update_layout(height=300)
    return fig


# ============= INTERFACCIA STREAMLIT =============

# SELEZIONE RUOLO
if not st.session_state.selected_role and not st.session_state.logged_in:
    st.title("🏥 Portale Telemonitoring Parkinson")
    st.markdown("### Seleziona il tuo ruolo")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("👨‍⚕️ Sono un Medico", use_container_width=True, type="primary"):
            st.session_state.selected_role = "medico"
            st.rerun()
    with col2:
        if st.button("👤 Sono un Paziente", use_container_width=True):
            st.session_state.selected_role = "paziente"
            st.rerun()
    st.stop()

# LOGIN MEDICO
if st.session_state.selected_role == "medico" and not st.session_state.logged_in:
    st.title("🔐 Accesso Medico")

    if st.button("← Indietro"):
        st.session_state.selected_role = None
        st.rerun()

    with st.form("login_medico"):
        username = st.text_input("Username o Codice Fiscale")
        password = st.text_input("Password", type="password")

        if st.form_submit_button("Accedi", use_container_width=True):
            if login_doctor(username, password):
                st.session_state.update({
                    "logged_in": True,
                    "user": username,
                    "role": "medico"
                })
                st.success("✅ Accesso effettuato!")
                st.rerun()
            else:
                st.error("❌ Credenziali non valide")

    st.stop()

# LOGIN PAZIENTE
if st.session_state.selected_role == "paziente" and not st.session_state.logged_in:
    st.title("🔐 Accesso Paziente")

    if st.button("← Indietro"):
        st.session_state.selected_role = None
        st.rerun()

    with st.form("login_paziente"):
        codice_fiscale = st.text_input("Codice Fiscale").upper()
        password = st.text_input("Password", type="password")

        if st.form_submit_button("Accedi", use_container_width=True):
            patient_data = login_patient(codice_fiscale, password)
            if patient_data:
                st.session_state.update({
                    "logged_in": True,
                    "user": codice_fiscale,
                    "nome_completo": f"{patient_data.get('nome', '')} {patient_data.get('cognome', '')}",
                    "role": "paziente"
                })
                st.success("✅ Accesso effettuato!")
                st.rerun()
            else:
                st.error("❌ Credenziali non valide")

    st.stop()

# DASHBOARD MEDICO
if st.session_state.role == "medico":
    st.sidebar.title(f"👨‍⚕️ Dr. {st.session_state.user}")
    if st.sidebar.button("🚪 Logout"):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.session_state.selected_role = None
        st.rerun()

    st.title("📊 Area Medico")
    menu = st.tabs(["📝 Registra Paziente", "🔬 Esegui Visita", "📋 Archivio Pazienti", "🔑 Reset Password"])

    # TAB 1: Registrazione
    with menu[0]:
        st.subheader("Registra Nuovo Paziente")
        with st.form("registra_paziente"):
            col1, col2 = st.columns(2)
            with col1:
                nome = st.text_input("Nome")
                cognome = st.text_input("Cognome")
                codice_fiscale = st.text_input("Codice Fiscale (16 caratteri)").upper()
            with col2:
                age = st.number_input("Età", 18, 100, value=65)
                sex = st.selectbox("Sesso", ["M", "F"])
                password = st.text_input("Password iniziale", type="password")

            if st.form_submit_button("Registra", use_container_width=True):
                if nome and cognome and codice_fiscale and password:
                    if len(codice_fiscale) != 16:
                        st.error("Il codice fiscale deve essere di 16 caratteri")
                    elif register_patient(codice_fiscale, nome, cognome, password, age, sex, st.session_state.user):
                        st.success(f"✅ Paziente {nome} {cognome} registrato")
                        st.info(f"**Credenziali:**\n- CF: `{codice_fiscale}`\n- Password: `{password}`")
                else:
                    st.warning("⚠️ Compila tutti i campi")

    # TAB 2: Visita
    with menu[1]:
        st.subheader("Esegui Visita e Analisi Vocale")
        with st.form("visita"):
            codice_fiscale_visita = st.text_input("Codice Fiscale Paziente").upper()
            motor_updrs = st.number_input("UPDRS Motorio (0-108)", 0.0, 108.0, value=25.0, step=0.5)
            audio = st.file_uploader("Registrazione Vocale (.wav)", type=["wav"])

            if st.form_submit_button("Analizza e Salva", use_container_width=True):
                if codice_fiscale_visita:
                    if audio:
                        with st.spinner("🔬 Analisi in corso..."):
                            features = extract_voice_features(audio)
                    else:
                        # Valori di default se non c'è audio
                        features = {
                            "jitter": 0.005,
                            "shimmer": 0.03,
                            "nhr": 0.02,
                            "hnr": 21.0,
                            "mean_f0": 150.0,
                            "f1": 500.0,
                            "f2": 1500.0
                        }
                    
                    if save_visit(codice_fiscale_visita, motor_updrs, features):
                        st.success("✅ Visita salvata con successo!")
                        
                        # Mostra features estratte
                        st.write("**Feature vocali estratte:**")
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Jitter", f"{features['jitter']:.4f}")
                        col2.metric("Shimmer", f"{features['shimmer']:.4f}")
                        col3.metric("F0 medio", f"{features['mean_f0']:.1f} Hz")
                else:
                    st.warning("⚠️ Inserisci il codice fiscale")

    # TAB 3: Archivio
    with menu[2]:
        st.subheader("Archivio Pazienti")
        
        patients = get_doctor_patients(st.session_state.user)
        
        if patients:
            for patient in patients:
                with st.expander(f"👤 {patient['nome']} {patient['cognome']} - CF: {patient['codice_fiscale']}"):
                    # Recupera visite
                    df_visits = get_patient_visits(patient['codice_fiscale'])
                    
                    if not df_visits.empty:
                        st.write(f"**Numero visite:** {len(df_visits)}")
                        
                        # Grafici
                        st.plotly_chart(create_updrs_trend_chart(df_visits), use_container_width=True)
                        st.plotly_chart(create_feature_comparison(df_visits), use_container_width=True)
                        
                        # Tabella dati
                        st.dataframe(df_visits[['timestamp', 'motor_updrs', 'jitter', 'shimmer']].sort_values('timestamp', ascending=False))
                    else:
                        st.info("Nessuna visita registrata per questo paziente")
        else:
            st.info("Non hai ancora pazienti registrati")

    # TAB 4: Reset Password
    with menu[3]:
        st.subheader("Reset Password Paziente")
        
        patients = get_doctor_patients(st.session_state.user)
        
        if patients:
            patient_options = {f"{p['nome']} {p['cognome']} ({p['codice_fiscale']})": p['codice_fiscale'] for p in patients}
            
            with st.form("reset_password"):
                selected = st.selectbox("Seleziona paziente", list(patient_options.keys()))
                new_password = st.text_input("Nuova password", type="password")
                confirm_password = st.text_input("Conferma password", type="password")
                
                if st.form_submit_button("Reset Password", use_container_width=True):
                    if new_password and new_password == confirm_password:
                        cf = patient_options[selected]
                        if reset_patient_password(cf, new_password):
                            st.success(f"✅ Password aggiornata per {selected}")
                            st.info(f"Nuova password: `{new_password}`")
                    elif new_password != confirm_password:
                        st.error("Le password non corrispondono")
                    else:
                        st.warning("Inserisci una password")
        else:
            st.info("Non hai pazienti registrati")

# DASHBOARD PAZIENTE
if st.session_state.role == "paziente":
    st.sidebar.title(f"👤 {st.session_state.nome_completo}")
    if st.sidebar.button("🚪 Logout"):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.session_state.selected_role = None
        st.rerun()

    st.title(f"📊 Il tuo Monitoraggio")
    
    # Recupera visite
    df_visits = get_patient_visits(st.session_state.user)
    
    if not df_visits.empty:
        # Metriche principali
        col1, col2, col3 = st.columns(3)
        ultimo_updrs = df_visits.iloc[-1]['motor_updrs']
        col1.metric("Ultima misurazione UPDRS", f"{ultimo_updrs:.1f}")
        col2.metric("Numero visite", len(df_visits))
        
        if len(df_visits) > 1:
            variazione = df_visits.iloc[-1]['motor_updrs'] - df_visits.iloc[-2]['motor_updrs']
            col3.metric("Variazione", f"{variazione:+.1f}")
        
        # Grafici
        st.plotly_chart(create_updrs_trend_chart(df_visits), use_container_width=True)
        
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(create_feature_comparison(df_visits), use_container_width=True)
        with col2:
            st.plotly_chart(create_distribution_plot(df_visits), use_container_width=True)
        
        # Storico
        st.subheader("📋 Storico Visite")
        st.dataframe(
            df_visits[['timestamp', 'motor_updrs', 'jitter', 'shimmer', 'mean_f0']].sort_values('timestamp', ascending=False),
            use_container_width=True
        )
    else:
        st.info("📭 Non hai ancora visite registrate. Contatta il tuo medico per la prima valutazione.")
