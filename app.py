import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Parkinson Telemonitoring", layout="wide")

API_URL = "http://127.0.0.1:8000"

# Inizializzazione sessione
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.role = None
    st.session_state.selected_role = None


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


# SELEZIONE RUOLO
if not st.session_state.selected_role and not st.session_state.logged_in:
    st.title("Portale Telemonitoring Parkinson")
    st.markdown("### Seleziona il tuo ruolo")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Sono un Medico", width='stretch', type="primary"):
            st.session_state.selected_role = "medico"
            st.rerun()
    with col2:
        if st.button("Sono un Paziente", width='stretch'):
            st.session_state.selected_role = "paziente"
            st.rerun()
    st.stop()

# LOGIN MEDICO
if st.session_state.selected_role == "medico" and not st.session_state.logged_in:
    st.title("Accesso Medico")

    if st.button("← Indietro"):
        st.session_state.selected_role = None
        st.rerun()

    with st.form("login_medico"):
        username = st.text_input("Username o Codice Fiscale")
        password = st.text_input("Password", type="password")

        if st.form_submit_button("Accedi", width='stretch'):
            try:
                res = requests.post(f"{API_URL}/login_doctor",
                                    data={"username": username, "password": password})
                if res.status_code == 200:
                    st.session_state.update({
                        "logged_in": True,
                        "user": username,
                        "role": "medico"
                    })
                    st.rerun()
                else:
                    st.error("Credenziali non valide")
            except requests.exceptions.ConnectionError:
                st.error("Server non raggiungibile")

    st.stop()

# LOGIN PAZIENTE
if st.session_state.selected_role == "paziente" and not st.session_state.logged_in:
    st.title("Accesso Paziente")

    if st.button("← Indietro"):
        st.session_state.selected_role = None
        st.rerun()

    with st.form("login_paziente"):
        codice_fiscale = st.text_input("Codice Fiscale").upper()
        password = st.text_input("Password", type="password")

        if st.form_submit_button("Accedi", width='stretch'):
            try:
                res = requests.post(f"{API_URL}/login_patient",
                                    data={"codice_fiscale": codice_fiscale, "password": password})
                if res.status_code == 200:
                    data = res.json()
                    st.session_state.update({
                        "logged_in": True,
                        "user": codice_fiscale,
                        "nome_completo": f"{data.get('nome', '')} {data.get('cognome', '')}",
                        "role": "paziente"
                    })
                    st.rerun()
                else:
                    st.error("Credenziali non valide")
            except requests.exceptions.ConnectionError:
                st.error("Server non raggiungibile")

    st.stop()

# DASHBOARD MEDICO
if st.session_state.role == "medico":
    st.sidebar.title(f"Dr. {st.session_state.user}")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.session_state.selected_role = None
        st.rerun()

    # Overview dashboard medico
    try:
        overview = requests.get(f"{API_URL}/doctor_overview/{st.session_state.user}").json()

        col1, col2, col3 = st.columns(3)
        col1.metric("Pazienti in Carico", overview['n_pazienti'])
        col2.metric("Pazienti Critici", len(overview['pazienti_critici']))
        col3.metric("Trend Medio", f"{overview.get('trend_generale', 0):+.2f}")

        if overview['pazienti_critici']:
            st.warning("Attenzione: pazienti che richiedono monitoraggio ravvicinato")
            for p in overview['pazienti_critici'][:3]:
                st.write(f"• {p['nome']} - UPDRS: {p['ultimo_updrs']:.1f} (Δ {p['variazione']:+.1f})")
    except:
        pass

    st.title("Area Medico")
    menu = st.tabs(["Registra Paziente", "Esegui Visita", "Archivio Pazienti", "Reset Password"])

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

            if st.form_submit_button("Registra"):
                if nome and cognome and codice_fiscale and password:
                    try:
                        res = requests.post(f"{API_URL}/register_patient", data={
                            "codice_fiscale": codice_fiscale,
                            "nome": nome,
                            "cognome": cognome,
                            "password": password,
                            "age": age,
                            "sex": sex,
                            "doctor_username": st.session_state.user
                        })
                        if res.status_code == 200:
                            st.success(f"Paziente {nome} {cognome} registrato")
                            st.info(f"Credenziali:\n- CF: `{codice_fiscale}`\n- Password: `{password}`")
                        else:
                            st.error(res.json().get("detail", "Errore"))
                    except requests.exceptions.ConnectionError:
                        st.error("Server non raggiungibile")
                else:
                    st.warning("Compila tutti i campi")

    # TAB 2: Visita
    with menu[1]:
        st.subheader("Esegui Visita e Analisi Vocale")
        with st.form("visita"):
            codice_fiscale_visita = st.text_input("Codice Fiscale Paziente").upper()
            audio = st.file_uploader("Registrazione Vocale (.wav)", type=["wav"])

            if st.form_submit_button("Analizza"):
                if audio and codice_fiscale_visita:
                    with st.spinner("Analisi in corso..."):
                        try:
                            files = {"audio": (audio.name, audio.getvalue(), "audio/wav")}
                            data = {"codice_fiscale": codice_fiscale_visita}
                            res = requests.post(f"{API_URL}/visit", data=data, files=files)

                            if res.status_code == 200:
                                result = res.json()
                                st.success("Analisi completata")

                                col1, col2, col3, col4 = st.columns(4)
                                col1.metric("UPDRS Motorio", f"{result['motor_UPDRS']:.1f}")
                                col2.metric("Jitter", f"{result['jitter']:.6f}")
                                col3.metric("Shimmer", f"{result['shimmer']:.6f}")
                                col4.metric("HNR", f"{result['hnr']:.2f}")

                                with st.expander("Feature Avanzate"):
                                    c1, c2, c3 = st.columns(3)
                                    c1.metric("NHR", f"{result['nhr']:.4f}")
                                    c2.metric("DFA", f"{result['dfa']:.4f}")
                                    c3.metric("PPE", f"{result['ppe']:.4f}")
                            else:
                                st.error("Paziente non trovato")
                        except requests.exceptions.ConnectionError:
                            st.error("Server non raggiungibile")
                else:
                    st.warning("Inserisci codice fiscale e carica audio")

    # TAB 3: Archivio
    with menu[2]:
        st.subheader("I Miei Pazienti")
        try:
            p_list = requests.get(f"{API_URL}/patients",
                                  params={"doctor_username": st.session_state.user}).json()

            if p_list:
                df_pazienti = pd.DataFrame(p_list)
                df_pazienti['sesso'] = df_pazienti['sex'].apply(lambda x: 'M' if x == 1 else 'F')

                st.dataframe(
                    df_pazienti[['nome', 'cognome', 'codice_fiscale', 'age', 'sesso']],
                    width='stretch',
                    hide_index=True
                )

                pazienti_options = {
                    f"{p['nome']} {p['cognome']} ({p['codice_fiscale']})": p['codice_fiscale']
                    for p in p_list
                }
                sel = st.selectbox("Seleziona Paziente", list(pazienti_options.keys()))

                if sel:
                    cf_selected = pazienti_options[sel]
                    hist = requests.get(f"{API_URL}/history/{cf_selected}").json()

                    if hist.get("history") and len(hist["history"]) > 0:
                        df = pd.DataFrame(hist["history"])
                        df['timestamp'] = pd.to_datetime(df['timestamp'])

                        st.plotly_chart(create_updrs_trend_chart(df), width='stretch')

                        col1, col2 = st.columns(2)
                        with col1:
                            st.plotly_chart(create_feature_comparison(df), width='stretch')
                        with col2:
                            st.plotly_chart(create_distribution_plot(df), width='stretch')

                        with st.expander("Dettaglio Misurazioni"):
                            st.dataframe(
                                df[['timestamp', 'motor_updrs', 'jitter', 'shimmer']],
                                width='stretch',
                                hide_index=True
                            )
                    else:
                        st.info("Nessuna misurazione registrata")
            else:
                st.info("Nessun paziente registrato")
        except Exception as e:
            st.warning("Errore caricamento dati")

    # TAB 4: Reset Password
    with menu[3]:
        st.subheader("Reset Password Paziente")

        try:
            p_list = requests.get(f"{API_URL}/patients",
                                  params={"doctor_username": st.session_state.user}).json()

            if p_list:
                pazienti_options = {
                    f"{p['nome']} {p['cognome']} ({p['codice_fiscale']})": p['codice_fiscale']
                    for p in p_list
                }

                with st.form("reset_password"):
                    selected_patient = st.selectbox("Seleziona Paziente", list(pazienti_options.keys()))

                    col1, col2 = st.columns(2)
                    with col1:
                        new_password = st.text_input("Nuova Password", type="password")
                    with col2:
                        confirm_password = st.text_input("Conferma Password", type="password")

                    if st.form_submit_button("Reset Password", type="primary"):
                        if not new_password or not confirm_password:
                            st.error("Compila entrambi i campi")
                        elif new_password != confirm_password:
                            st.error("Le password non corrispondono")
                        else:
                            try:
                                cf_selected = pazienti_options[selected_patient]
                                res = requests.post(f"{API_URL}/reset_patient_password", data={
                                    "doctor_username": st.session_state.user,
                                    "codice_fiscale_paziente": cf_selected,
                                    "new_password": new_password
                                })

                                if res.status_code == 200:
                                    result = res.json()
                                    st.success(f"Password di {result['nome_completo']} aggiornata")
                                    st.info(f"Nuove credenziali:\n- CF: `{cf_selected}`\n- Password: `{new_password}`")
                                elif res.status_code == 403:
                                    st.error("Non hai i permessi")
                                else:
                                    st.error(res.json().get('detail', 'Errore'))
                            except requests.exceptions.ConnectionError:
                                st.error("Server non raggiungibile")
            else:
                st.info("Nessun paziente registrato")
        except requests.exceptions.ConnectionError:
            st.error("Server non raggiungibile")


# DASHBOARD PAZIENTE
else:
    st.sidebar.title(f"{st.session_state.get('nome_completo', 'Paziente')}")
    st.sidebar.info(f"CF: {st.session_state.user}")

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.session_state.selected_role = None
        st.rerun()

    st.title("Il Tuo Monitoraggio")

    try:
        # Statistiche generali
        stats = requests.get(f"{API_URL}/patient_stats/{st.session_state.user}").json()

        if stats['n_misurazioni'] > 0:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Misurazioni", stats['n_misurazioni'])
            col2.metric("Ultimo UPDRS", f"{stats['ultimo_updrs']:.1f}")
            col3.metric("Variazione", f"{stats['variazione']:+.1f}",
                        delta_color="inverse")
            col4.metric("Trend", stats['trend'])

            # Grafico principale
            res = requests.get(f"{API_URL}/history/{st.session_state.user}")
            if res.status_code == 200:
                data = res.json()

                if data.get("history") and len(data["history"]) > 0:
                    df_p = pd.DataFrame(data["history"])
                    df_p['timestamp'] = pd.to_datetime(df_p['timestamp'])

                    st.plotly_chart(create_updrs_trend_chart(df_p), width='stretch')

                    col1, col2 = st.columns(2)
                    with col1:
                        st.plotly_chart(create_feature_comparison(df_p), width='stretch')
                    with col2:
                        # Radar chart parametri vocali
                        latest = df_p.iloc[-1]
                        fig_radar = go.Figure(data=go.Scatterpolar(
                            r=[latest['jitter'] * 1000, latest['shimmer'] * 100,
                               stats['media_jitter'] * 1000, stats['media_shimmer'] * 100],
                            theta=['Jitter Corrente', 'Shimmer Corrente',
                                   'Jitter Medio', 'Shimmer Medio'],
                            fill='toself'
                        ))
                        fig_radar.update_layout(title="Parametri Vocali", height=350)
                        st.plotly_chart(fig_radar, width='stretch')

                    with st.expander("Dettaglio Misurazioni"):
                        st.dataframe(
                            df_p[['timestamp', 'motor_updrs', 'jitter', 'shimmer']],
                            width='stretch',
                            hide_index=True
                        )
        else:
            st.info("Benvenuto! Non ci sono ancora misurazioni.\n\nContatta il tuo medico per la prima visita.")

    except requests.exceptions.ConnectionError:
        st.error("Server non risponde")