#!/usr/bin/env python3
"""
🔐 Script Amministratore - Gestione Sistema Telemonitoring
===========================================================
Questo script è riservato SOLO all'amministratore del sistema.

Funzionalità:
- Registrazione nuovi medici
- Reset password medici
- Reset password pazienti
- Visualizzazione utenti registrati

IMPORTANTE: Mantieni questo file riservato e sicuro!
"""
import re
import hashlib
from supabase import create_client, Client
from getpass import getpass

# Configurazione Supabase (UGUALE al backend)
SUPABASE_URL = "https://viexdcbofgsopcrnnbzi.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZpZXhkY2JvZmdzb3Bjcm5uYnppIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njk1ODk4OTUsImV4cCI6MjA4NTE2NTg5NX0.7Xu5B8Vlz0j-wX39-i5W12Mw5cedX7VS9ACOPjSpLEs"


def register_doctor():
    """Registra un nuovo medico nel sistema"""

    print("=" * 60)
    print("🏥 REGISTRAZIONE NUOVO MEDICO")
    print("=" * 60)
    print()

    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Connessione al database stabilita")
        print()
    except Exception as e:
        print(f"❌ Errore di connessione: {e}")
        return

    # Input username
    username = input("Username medico: ").strip()
    if not username:
        print("❌ Username non può essere vuoto")
        return

    # Input codice fiscale con validazione
    max_tentativi = 3
    for tentativo in range(1, max_tentativi + 1):
        codice_fiscale = input(f"Codice Fiscale medico (tentativo {tentativo}/{max_tentativi}): ").strip().upper()

        if not codice_fiscale:
            print("❌ Codice Fiscale non può essere vuoto")
            if tentativo == max_tentativi:
                print("⛔ Numero massimo di tentativi raggiunto. Registrazione annullata.")
                return
            continue

        if len(codice_fiscale) == 16:
            break
        else:
            print(f"⚠️ ERRORE: Il codice fiscale deve essere di 16 caratteri (inseriti: {len(codice_fiscale)})")
            if tentativo == max_tentativi:
                print("⛔ Numero massimo di tentativi raggiunto. Registrazione annullata.")
                return

    # Validazione formato CF
    codice_fiscale_regex = r'^[A-Z0-9]{16}$'
    if not re.match(codice_fiscale_regex, codice_fiscale):
        print("❌ Codice Fiscale non valido. Il formato deve essere composto da 16 caratteri alfanumerici.")
        return

    # Input password
    password = getpass("Password medico: ")
    if not password:
        print("❌ Password non può essere vuota")
        return

    password_confirm = getpass("Conferma password: ")
    if password != password_confirm:
        print("❌ Le password non corrispondono!")
        return

    # Hash password
    pw_hash = hashlib.sha256(password.encode()).hexdigest()

    # Inserimento nel database
    try:
        supabase.table("doctors").insert({
            "username": username,
            "codice_fiscale": codice_fiscale,
            "password_hash": pw_hash
        }).execute()

        print()
        print("=" * 60)
        print("✅ MEDICO REGISTRATO CON SUCCESSO!")
        print("=" * 60)
        print(f"Username: {username}")
        print(f"Codice Fiscale: {codice_fiscale}")
        print("Il medico può ora accedere all'applicazione")
        print()

    except Exception as e:
        if "duplicate" in str(e).lower():
            if "username" in str(e).lower():
                print()
                print("❌ ERRORE: Username già esistente nel sistema")
            elif "codice_fiscale" in str(e).lower():
                print()
                print("❌ ERRORE: Codice Fiscale già registrato nel sistema")
            else:
                print()
                print("❌ ERRORE: Username o Codice Fiscale già esistente")
        else:
            print()
            print(f"❌ ERRORE: {e}")


def reset_doctor_password():
    """Reset password di un medico"""

    print("=" * 60)
    print("🔄 RESET PASSWORD MEDICO")
    print("=" * 60)
    print()

    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

        # Mostra lista medici
        response = supabase.table("doctors").select("username, codice_fiscale").execute()

        if not response.data:
            print("❌ Nessun medico registrato")
            return

        print("Medici registrati:")
        for idx, doc in enumerate(response.data, 1):
            print(f"{idx}. {doc['username']} (CF: {doc.get('codice_fiscale', 'N/A')})")

        print()
        username = input("Username del medico da resettare: ").strip()

        if not username:
            print("❌ Username non può essere vuoto")
            return

        # Verifica che esista
        check = supabase.table("doctors").select("*").eq("username", username).execute()
        if not check.data:
            print(f"❌ Medico '{username}' non trovato")
            return

        # Nuova password
        new_password = getpass("Nuova password: ")
        if not new_password:
            print("❌ Password non può essere vuota")
            return

        confirm = getpass("Conferma nuova password: ")
        if new_password != confirm:
            print("❌ Le password non corrispondono")
            return

        # Hash e aggiornamento
        pw_hash = hashlib.sha256(new_password.encode()).hexdigest()

        supabase.table("doctors").update({
            "password_hash": pw_hash
        }).eq("username", username).execute()

        print()
        print("=" * 60)
        print("✅ PASSWORD AGGIORNATA CON SUCCESSO!")
        print("=" * 60)
        print(f"Il Dr. {username} può ora accedere con la nuova password")
        print()

    except Exception as e:
        print(f"❌ Errore: {e}")


def reset_patient_password():
    """Reset password di un paziente"""

    print("=" * 60)
    print("🔄 RESET PASSWORD PAZIENTE")
    print("=" * 60)
    print()

    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

        codice_fiscale = input("Codice Fiscale del paziente: ").strip().upper()

        if len(codice_fiscale) != 16:
            print(f"❌ Codice fiscale non valido (deve essere 16 caratteri)")
            return

        # Verifica che esista
        check = supabase.table("patients").select("*").eq("codice_fiscale", codice_fiscale).execute()
        if not check.data:
            print(f"❌ Paziente con CF '{codice_fiscale}' non trovato")
            return

        patient = check.data[0]
        print(f"\n✅ Paziente trovato: {patient['nome']} {patient['cognome']}")
        print(f"   Medico: Dr. {patient.get('doctor_username', 'N/A')}")
        print()

        # Nuova password
        new_password = getpass("Nuova password per il paziente: ")
        if not new_password:
            print("❌ Password non può essere vuota")
            return

        confirm = getpass("Conferma nuova password: ")
        if new_password != confirm:
            print("❌ Le password non corrispondono")
            return

        # Hash e aggiornamento
        pw_hash = hashlib.sha256(new_password.encode()).hexdigest()

        supabase.table("patients").update({
            "password_hash": pw_hash
        }).eq("codice_fiscale", codice_fiscale).execute()

        print()
        print("=" * 60)
        print("✅ PASSWORD AGGIORNATA CON SUCCESSO!")
        print("=" * 60)
        print(f"{patient['nome']} {patient['cognome']} può ora accedere con la nuova password")
        print()
        print("⚠️  Comunica la nuova password al paziente in modo sicuro!")
        print(f"    Password: {new_password}")
        print()

    except Exception as e:
        print(f"❌ Errore: {e}")


def list_doctors():
    """Mostra tutti i medici registrati"""

    print("=" * 80)
    print("📋 LISTA MEDICI REGISTRATI")
    print("=" * 80)
    print()

    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        response = supabase.table("doctors").select("username, codice_fiscale, created_at").execute()

        if not response.data:
            print("Nessun medico ancora registrato")
        else:
            for idx, doctor in enumerate(response.data, 1):
                cf = doctor.get('codice_fiscale', 'N/A')
                data = doctor.get('created_at', 'N/A')[:10]
                print(f"{idx}. Dr. {doctor['username']} - CF: {cf} (creato il {data})")

        print()

    except Exception as e:
        print(f"❌ Errore: {e}")


def list_all_patients():
    """Mostra tutti i pazienti del sistema"""

    print("=" * 80)
    print("👥 LISTA COMPLETA PAZIENTI")
    print("=" * 80)
    print()

    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        response = supabase.table("patients").select(
            "nome, cognome, codice_fiscale, age, sex, doctor_username, created_at"
        ).execute()

        if not response.data:
            print("Nessun paziente ancora registrato")
        else:
            # Raggruppa per medico
            from collections import defaultdict
            by_doctor = defaultdict(list)

            for patient in response.data:
                by_doctor[patient['doctor_username']].append(patient)

            total = 0
            for doctor, patients in by_doctor.items():
                print(f"\n👨‍⚕️ Dr. {doctor} ({len(patients)} paziente/i):")
                print("-" * 80)
                for idx, p in enumerate(patients, 1):
                    sesso = "M" if p['sex'] == 1 else "F"
                    print(
                        f"  {idx}. {p['nome']} {p['cognome']} - CF: {p['codice_fiscale']} - Età: {p['age']} - Sesso: {sesso}")
                    total += 1

            print()
            print("=" * 80)
            print(f"TOTALE PAZIENTI NEL SISTEMA: {total}")
            print("=" * 80)

        print()

    except Exception as e:
        print(f"❌ Errore: {e}")


def main():
    """Menu principale amministratore"""

    print()
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "PANNELLO AMMINISTRATORE" + " " * 25 + "║")
    print("║" + " " * 10 + "Sistema Telemonitoring Parkinson" + " " * 15 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    while True:
        print("Scegli un'operazione:")
        print("1. 👨‍⚕️ Registra nuovo medico")
        print("2. 📋 Visualizza medici registrati")
        print("3. 👥 Visualizza TUTTI i pazienti")
        print("4. 🔄 Reset password medico")
        print("5. 🔄 Reset password paziente")
        print("6. 🚪 Esci")
        print()

        choice = input("Scelta (1-6): ").strip()
        print()

        if choice == "1":
            register_doctor()
        elif choice == "2":
            list_doctors()
        elif choice == "3":
            list_all_patients()
        elif choice == "4":
            reset_doctor_password()
        elif choice == "5":
            reset_patient_password()
        elif choice == "6":
            print("👋 Arrivederci!")
            break
        else:
            print("❌ Scelta non valida")

        print()


if __name__ == "__main__":
    main()