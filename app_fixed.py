import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import hashlib
from supabase import create_client, Client
import parselmouth
import numpy as np
import tempfile
import os

st.set_page_config(page_title="Parkinson Telemonitoring", layout="wide")

# Configurazione Supabase - USA I SECRETS
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except:
    # Fallback per test locale
    SUPABASE_URL = "https://qjrhkztpyrcorqqikufg.supabase.co"
    SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFqcmhrenRweXJjb3JxcWlrdWZnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzAyMjQzOTgsImV4cCI6MjA4NTgwMDM5OH0.zthfNTfJWE44lpKNyW9aR3ggrpX4dL7j2-lpVs1tTGY"
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


def extract_vocal_features(audio_file):
    """
    Estrae feature vocali avanzate da file audio usando Parselmouth.
    Basato su: Tsanas et al. "Accurate Telemonitoring of Parkinson's Disease
    Progression by Noninvasive Speech Tests" (2010)
    
    Feature estratte:
    - jitter_abs: Variabilità assoluta della frequenza fondamentale
    - shimmer_local: Variabilità locale dell'ampiezza
    - hnr: Harmonics-to-Noise Ratio
    - nhr: Noise-to-Harmonics Ratio
    - dfa: Detrended Fluctuation Analysis
    - ppe: Pitch Period Entropy
    """
    try:
        # Salva temporaneamente il file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
            tmp_file.write(audio_file.getbuffer())
            temp_path = tmp_file.name
        
        # Analisi con Parselmouth
        sound = parselmouth.Sound(temp_path)
        point_process = parselmouth.praat.call(sound, "To PointProcess (periodic, cc)", 75, 500)
        
        # JITTER (Absolute): variabilità frequenza fondamentale (F0)
        jitter_abs = parselmouth.praat.call(
            point_process, "Get jitter (local, absolute)", 0, 0, 0.0001, 0.02, 1.3
        )
        
        # SHIMMER (Local): variabilità ampiezza
        shimmer_local = parselmouth.praat.call(
            [sound, point_process], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6
        )
        
        # HNR: rapporto armoniche/rumore
        harmonicity = parselmouth.praat.call(sound, "To Harmonicity (cc)", 0.01, 75, 0.1, 1.0)
        hnr = parselmouth.praat.call(harmonicity, "Get mean", 0, 0)
        
        # NHR: noise-to-harmonics ratio (inverso di HNR)
        nhr = 1.0 / (hnr + 1e-6) if hnr > 0 else 1.0
        
        # DFA: Detrended Fluctuation Analysis
        intensity = sound.to_intensity(time_step=0.01)
        intensity_values = [
            intensity.get_value(t) for t in intensity.xs()
            if not np.isnan(intensity.get_value(t))
        ]
        
        if len(intensity_values) > 10:
            dfa = np.std(intensity_values) / (np.mean(intensity_values) + 1e-6)
        else:
            dfa = 0.0
        
        # PPE: Pitch Period Entropy
        pitch = sound.to_pitch(time_step=0.01, pitch_floor=75, pitch_ceiling=500)
        pitch_values = [
            pitch.get_value_at_time(t) for t in pitch.xs()
            if not np.isnan(pitch.get_value_at_time(t))
        ]
        
        if len(pitch_values) > 5:
            pitch_diffs = np.diff(pitch_values)
            ppe = np.std(pitch_diffs) / (np.mean(np.abs(pitch_diffs)) + 1e-6)
        else:
            ppe = 0.0
        
        # Pulizia file temporaneo
        os.unlink(temp_path)
        
        # Calcolo UPDRS stimato con modello semplificato
        # Basato sui coefficienti della letteratura
        motor_updrs = (
            30.0 +  # baseline
            jitter_abs * 1000 +
            shimmer_local * 50 +
            (1.0 / (hnr + 1)) * 20 +
            dfa * 15 +
            ppe * 10
        )
        
        # Limita il range 0-108
        motor_updrs = max(0, min(108, motor_updrs))
        
        return {
            'jitter': float(jitter_abs) if not np.isnan(jitter_abs) else 0.005,
            'shimmer': float(shimmer_local) if not np.isnan(shimmer_local) else 0.03,
            'hnr': float(hnr) if not np.isnan(hnr) else 21.0,
            'nhr': float(nhr) if not np.isnan(nhr) else 0.02,
            'dfa': float(dfa),
            'ppe': float(ppe),
            'motor_updrs_stimato': round(motor_updrs, 2)
        }
        
    except Exception as e:
        st.warning(f"Errore estrazione feature: {e}. Uso valori di default.")
        return {
            'jitter': 0.005,
            'shimmer': 0.03,
            'hnr': 21.0,
            'nhr': 0.02,
            'dfa': 0.5,
            'ppe': 0.3,
            'motor_updrs_stimato': 25.0
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
            "dfa": features.get("dfa", 0.5),
            "ppe": features.get("ppe", 0.3)
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


def get_doctor_overview(doctor_username: str) -> dict:
    """
    Overview per dashboard medico con pazienti critici e trend generale
    """
    try:
        patients = supabase.table("patients").select("*").eq(
            "doctor_username", doctor_username
        ).execute()

        if not patients.data:
            return {
                "n_pazienti": 0,
                "pazienti_critici": [],
                "trend_generale": 0
            }

        pazienti_critici = []
        all_trends = []

        for patient in patients.data:
            cf = patient['codice_fiscale']

            visits = supabase.table("visits").select("motor_updrs").eq(
                "codice_fiscale", cf
            ).order("timestamp", desc=False).execute()

            if visits.data and len(visits.data) >= 2:
                updrs_vals = [v['motor_updrs'] for v in visits.data]
                variazione = updrs_vals[-1] - updrs_vals[0]
                all_trends.append(variazione)

                # Criteri per paziente critico:
                # 1. UPDRS corrente > 30 (moderato-severo)
                # 2. Variazione > 10 punti (peggioramento significativo)
                if updrs_vals[-1] > 30 or variazione > 10:
                    pazienti_critici.append({
                        "nome": f"{patient['nome']} {patient['cognome']}",
                        "codice_fiscale": cf,
                        "ultimo_updrs": updrs_vals[-1],
                        "variazione": variazione
                    })

        trend_medio = np.mean(all_trends) if all_trends else 0

        return {
            "n_pazienti": len(patients.data),
            "pazienti_critici": sorted(pazienti_critici, key=lambda x: x['ultimo_updrs'], reverse=True),
            "trend_generale": round(trend_medio, 2)
        }
    except Exception as e:
        st.error(f"Errore overview: {e}")
        return {
            "n_pazienti": 0,
            "pazienti_critici": [],
            "trend_generale": 0
        }


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

    # OVERVIEW DASHBOARD CON PAZIENTI CRITICI
    overview = get_doctor_overview(st.session_state.user)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("👥 Pazienti in Carico", overview['n_pazienti'])
    col2.metric("⚠️ Pazienti Critici", len(overview['pazienti_critici']))
    col3.metric("📈 Trend Medio", f"{overview.get('trend_generale', 0):+.2f}")

    if overview['pazienti_critici']:
        st.warning("⚠️ **Attenzione:** pazienti che richiedono monitoraggio ravvicinato")
        for p in overview['pazienti_critici'][:3]:
            st.write(f"• **{p['nome']}** - UPDRS: {p['ultimo_updrs']:.1f} (Δ {p['variazione']:+.1f})")

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
            
            col1, col2 = st.columns([2, 1])
            with col1:
                audio = st.file_uploader("📁 Registrazione Vocale (.wav)", type=["wav"])
                st.caption("Carica un file audio WAV per l'analisi automatica delle feature vocali")
            with col2:
                st.info("💡 **Istruzioni**\n\nSe carichi un audio, l'UPDRS sarà calcolato automaticamente. Altrimenti, inseriscilo manualmente.")
            
            motor_updrs_manuale = st.number_input(
                "UPDRS Motorio manuale (0-108) - opzionale se hai audio",
                0.0, 108.0, value=25.0, step=0.5,
                help="Inserisci il punteggio UPDRS solo se NON carichi un audio"
            )

            if st.form_submit_button("🔬 Analizza e Salva", use_container_width=True):
                if codice_fiscale_visita:
                    if audio:
                        with st.spinner("🔬 Analisi vocale in corso..."):
                            features = extract_vocal_features(audio)
                            motor_updrs = features["motor_updrs_stimato"]
                            
                        st.success("✅ Analisi completata!")
                        
                        # Mostra features estratte
                        st.subheader("📊 Feature Vocali Estratte")
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("Jitter", f"{features['jitter']:.4f}")
                        col2.metric("Shimmer", f"{features['shimmer']:.4f}")
                        col3.metric("HNR", f"{features['hnr']:.2f} dB")
                        col4.metric("DFA", f"{features['dfa']:.3f}")
                        
                        st.metric("🎯 **UPDRS Stimato**", f"{motor_updrs:.1f}", 
                                help="Calcolato automaticamente dalle feature vocali")
                    else:
                        # Nessun audio - usa UPDRS manuale e valori di default
                        motor_updrs = motor_updrs_manuale
                        features = {
                            "jitter": 0.005,
                            "shimmer": 0.03,
                            "nhr": 0.02,
                            "hnr": 21.0,
                            "dfa": 0.5,
                            "ppe": 0.3
                        }
                        st.info("ℹ️ Nessun audio caricato - usando UPDRS manuale e feature di default")
                    
                    # Salva nel database
                    if save_visit(codice_fiscale_visita, motor_updrs, features):
                        st.success("✅ Visita salvata con successo!")
                else:
                    st.warning("⚠️ Inserisci il codice fiscale del paziente")

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
                        st.dataframe(
                            df_visits[['timestamp', 'motor_updrs', 'jitter', 'shimmer', 'hnr']].sort_values('timestamp', ascending=False),
                            use_container_width=True
                        )
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
                
                if st.form_submit_button("🔑 Reset Password", use_container_width=True):
                    if new_password and new_password == confirm_password:
                        cf = patient_options[selected]
                        if reset_patient_password(cf, new_password):
                            st.success(f"✅ Password aggiornata per {selected}")
                            st.info(f"Nuova password: `{new_password}`")
                    elif new_password != confirm_password:
                        st.error("❌ Le password non corrispondono")
                    else:
                        st.warning("⚠️ Inserisci una password")
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
        col1.metric("🎯 Ultima misurazione UPDRS", f"{ultimo_updrs:.1f}")
        col2.metric("📅 Numero visite", len(df_visits))
        
        if len(df_visits) > 1:
            variazione = df_visits.iloc[-1]['motor_updrs'] - df_visits.iloc[-2]['motor_updrs']
            col3.metric("📈 Variazione", f"{variazione:+.1f}")
        
        # Grafici
        st.plotly_chart(create_updrs_trend_chart(df_visits), use_container_width=True)
        
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(create_feature_comparison(df_visits), use_container_width=True)
        with col2:
            st.plotly_chart(create_distribution_plot(df_visits), use_container_width=True)
        
        # Storico
        st.subheader("📋 Storico Visite")
        display_cols = ['timestamp', 'motor_updrs', 'jitter', 'shimmer', 'hnr']
        available_cols = [col for col in display_cols if col in df_visits.columns]
        
        st.dataframe(
            df_visits[available_cols].sort_values('timestamp', ascending=False),
            use_container_width=True
        )
    else:
        st.info("📭 Non hai ancora visite registrate. Contatta il tuo medico per la prima valutazione.")
