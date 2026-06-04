import streamlit as st
import pandas as pd
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from datetime import datetime
import os
import unicodedata
import re
import json

# Oldal beállításai
st.set_page_config(page_title="OMS 24 Árajánlat", page_icon="📝", layout="wide")

# --- MAPPÁK BEÁLLÍTÁSA (FELHŐHÖZ) ---
# A felhőben egy lokális mappát használunk a futás idejére
mentesi_mappa = "Mentett_Ajanlatok_Felho"
os.makedirs(mentesi_mappa, exist_ok=True)

# --- LOGÓ ÉS FEJLÉC ---
if os.path.exists("OMS.png"):
    st.image("OMS.png", width=300)
st.title("OMS 24 Zrt. - Árajánlat Generáló (Cloud)")

# --- SEGÉDFÜGGVÉNYEK ---
def ekezet_mentesit(szoveg):
    nfkd_form = unicodedata.normalize('NFKD', str(szoveg))
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def general_azonosito(nev, cim, ido_kod):
    nev_tiszta = ekezet_mentesit(nev).replace(" ", "").upper()
    nev_3 = nev_tiszta[:3].ljust(3, 'X') if nev_tiszta else "XXX"
    
    cim_darab = cim.split(',')[0].strip()
    cim_darab = re.sub(r'^\d+\s+', '', cim_darab) 
    telepules_tiszta = ekezet_mentesit(cim_darab.split(' ')[0]).replace(" ", "").upper()
    telep_3 = telepules_tiszta[:3].ljust(3, 'X') if telepules_tiszta else "XXX"
    
    return f"E{nev_3}-{telep_3}{ido_kod}"

# --- ALAPÉRTELMEZETT SZÖVEGEK ---
alap_fizetes = "Előleg előlegbekérő alapján: a teljes bruttó ár 30%-a\nAnyag /eszköz raktárra érkezésekor: a teljes bruttó ár 50%-a\nKivitelezés vége: a teljes bruttó ár 20%-a"
alap_utemezes = "A vállalkozó feladatainak időbeli ütemezését az alábbiak szerint vállalja:\nA megrendelő 30%-os előlegbefizetésétől számítva a vállalkozó 50kVA inverter teljesítményig 10 (tíz) munkanapon belül, 50kVA inverter teljesítmény felett 30 (harminc) munkanapon belül a csatlakozási engedélykérelmet a területileg illetékes elosztói engedélyes szolgáltató felé benyújtja.*\nA területileg illetékes elosztói engedélyes szolgáltató műszaki gazdasági tájékoztató (MGT) kiállítását követően a vállalkozó 50kVA inverter teljesítményig 10 (tíz) munkanapon belül, 50kVA inverter teljesítmény felett 30 (harminc) munkanapon belül a csatlakozási dokumentációt (CSD) az illetékes elosztói engedélyes szolgáltató felé benyújtja.*\nA megrendelő 50%-os előlegbefizetésétől és a területileg illetékes elosztói engedélyes szolgáltató válaszát követően (CSD elfogadása) a vállalkozó a fizikai kivitelezést 120 (egyszázhúsz) naptári napon belül elvégzi, és a területileg illetékes elosztói engedélyes szolgáltató felé a készrejelentési kötelezettségnek eleget tesz.*\nA területileg illetékes elosztói engedélyes szolgáltató felé tett készrejelentéssel a vállalkozó jogosult az fentmaradó 20%-os vállalkozói díjról számla kiállítására a megrendelő felé.*\n* a területileg illetékes elosztói engedélyes szolgáltatóhoz beérkezett dokumentumok elbírálási határidejére a vállalkozónak ráhatása nincs, ezek határidejeiről a megrendelő a területileg illetékes elosztói engedélyes szolgáltató honlapján, vagy ügyfélszolgálati telefonszámán tud tájékoztatást kérni."

# --- MEMÓRIA INICIALIZÁLÁSA ---
alap_mezok = {
    'ugyfel_nev': '', 'ugyfel_cim': '', 'ajanlat_targya': '', 'ugyfel_adoszam': '', 'ugyfel_tel': '', 'ugyfel_email': '',
    'ervenyesseg_szoveg': '15 munkanap, vagy 370Ft/EUR árfolyam',
    'fizetes_szoveg': alap_fizetes,
    'utemezes_szoveg': alap_utemezes,
    'garancia_szoveg': "Solis inverterre 10 év gyártói garancia.\nDyness akkumulátorokra 10év, vagy 6000 ciklus gyártói garancia.\nLeapton napelemekre 25év gyártói és 30 év termelés garancia 87,4%-ra."
}
for kulcs, ertek in alap_mezok.items():
    if kulcs not in st.session_state:
        st.session_state[kulcs] = ertek

if 'df_items' not in st.session_state:
    ures_adatok = {"Kiadási tétel megnevezése:": ["" for _ in range(10)], "Mennyiség:": [None]*10, "Nettó egységár:": [None]*10}
    st.session_state.df_items = pd.DataFrame(ures_adatok)

if 'ido_kod' not in st.session_state:
    st.session_state.ido_kod = datetime.now().strftime("%f")[:3]


# --- 0. OLDALSÁV - SCENÁRIÓ KEZELÉS (ÚJ FELHŐS LOGIKA) ---
st.sidebar.header("📂 Scenárió betöltése")
st.sidebar.info("A felhőben a biztonság kedvéért érdemes letölteni és saját gépről visszatölteni a scenáriókat (.json fájlok)!")

# 1. Opció: Közvetlen fájlfeltöltés a gépről
feltoltott_json = st.sidebar.file_uploader("Tölts fel egy korábbi .json fájlt:", type=["json"])
if feltoltott_json is not None:
    if st.sidebar.button("📥 Adatok betöltése a fájlból", use_container_width=True):
        betoltott_adatok = json.load(feltoltott_json)
        for kulcs in alap_mezok.keys():
            if kulcs in betoltott_adatok:
                st.session_state[kulcs] = betoltott_adatok[kulcs]
        
        if "df_items" in betoltott_adatok:
            betoltott_df = pd.DataFrame(betoltott_adatok["df_items"])
            hianyzo_sorok = 10 - len(betoltott_df)
            if hianyzo_sorok > 0:
                potlas = pd.DataFrame({"Kiadási tétel megnevezése:": [""]*hianyzo_sorok, "Mennyiség:": [None]*hianyzo_sorok, "Nettó egységár:": [None]*hianyzo_sorok})
                betoltott_df = pd.concat([betoltott_df, potlas], ignore_index=True)
            st.session_state.df_items = betoltott_df
            
        st.session_state.ido_kod = datetime.now().strftime("%f")[:3]
        st.rerun()

st.sidebar.markdown("---")

# 2. Opció: A felhő memóriájában maradt fájlok (amíg a szerver újra nem indul)
mentett_fajlok = [f.replace('.json', '') for f in os.listdir(mentesi_mappa) if f.endswith('.json')]
kivalasztott_mentes = st.sidebar.selectbox("Vagy válassz a szerveren maradtak közül:", ["-- Új / Üres lap --"] + sorted(mentett_fajlok, reverse=True))

if st.sidebar.button("🔄 Szerveres adat betöltése", use_container_width=True):
    if kivalasztott_mentes != "-- Új / Üres lap --":
        fajl_utvonal = os.path.join(mentesi_mappa, f"{kivalasztott_mentes}.json")
        with open(fajl_utvonal, 'r', encoding='utf-8') as f:
            betoltott_adatok = json.load(f)
        
        for kulcs in alap_mezok.keys():
            if kulcs in betoltott_adatok:
                st.session_state[kulcs] = betoltott_adatok[kulcs]
        
        if "df_items" in betoltott_adatok:
            betoltott_df = pd.DataFrame(betoltott_adatok["df_items"])
            hianyzo_sorok = 10 - len(betoltott_df)
            if hianyzo_sorok > 0:
                potlas = pd.DataFrame({"Kiadási tétel megnevezése:": [""]*hianyzo_sorok, "Mennyiség:": [None]*hianyzo_sorok, "Nettó egységár:": [None]*hianyzo_sorok})
                betoltott_df = pd.concat([betoltott_df, potlas], ignore_index=True)
            st.session_state.df_items = betoltott_df
            
        st.session_state.ido_kod = datetime.now().strftime("%f")[:3]
        st.rerun()


# --- 1. OLDALSÁV (Adatbevitel) ---
st.sidebar.divider()
st.sidebar.header("Ügyfél és Ajánlat adatai")

ugyfel_nev = st.sidebar.text_input("Ügyfél neve:", key="ugyfel_nev")
ugyfel_cim = st.sidebar.text_input("Ügyfél címe:", key="ugyfel_cim")
    
alap_id = general_azonosito(ugyfel_nev, ugyfel_cim, st.session_state.ido_kod)
ugylet_azonosito = st.sidebar.text_input("Ügylet azonosító:", value=alap_id)

ajanlat_targya = st.sidebar.text_input("Ajánlat tárgya:", key="ajanlat_targya")
ugyfel_adoszam = st.sidebar.text_input("Adószám:", key="ugyfel_adoszam")
ugyfel_tel = st.sidebar.text_input("Telefon:", key="ugyfel_tel")
ugyfel_email = st.sidebar.text_input("E-mail:", key="ugyfel_email")

ceg_adatok = {
    'neve:': 'OMS 24 Zrt.', 
    'címe:': '1117 Budapest, Kaposvár utca 8.', 
    'adószáma:': '27059148-2-43', 
    'cégjegyzék száma:': '01-10-141935', 
    'e-mail:': 'energetika.ugyfel@oms24.hu'
}


# --- 2. FŐABLAK (Excel betöltés és Táblázat) ---
st.subheader("Tételek és Árak")

with st.expander("📊 Excel árazó betöltése", expanded=True):
    feltoltott_excel = st.file_uploader("Húzd ide az Ajanlat.xlsx fájlt (vagy kattints a tallózáshoz):", type=["xlsx"])
    
    if feltoltott_excel is not None:
        if st.button("📥 Adatok átemelése a táblázatba (Felülírás)", type="secondary"):
            try:
                excel_df = pd.read_excel(feltoltott_excel, sheet_name="Ajánlati árak", usecols="A:C")
                excel_df.columns = ["Kiadási tétel megnevezése:", "Mennyiség:", "Nettó egységár:"]
                
                # Vágás az összesítő sornál
                cutoff_indices = excel_df.index[excel_df["Kiadási tétel megnevezése:"].astype(str).str.contains("összesen|osszesen", case=False, na=False, regex=True)].tolist()
                
                if cutoff_indices:
                    elso_ossz_index = cutoff_indices[0]
                    sor_pozicio = excel_df.index.get_loc(elso_ossz_index)
                    excel_df = excel_df.iloc[:sor_pozicio]
                
                excel_df = excel_df.dropna(subset=["Kiadási tétel megnevezése:"])
                
                hianyzo_sorok = 10 - len(excel_df)
                if hianyzo_sorok > 0:
                    potlas = pd.DataFrame({
                        "Kiadási tétel megnevezése:": [""] * hianyzo_sorok, 
                        "Mennyiség:": [None] * hianyzo_sorok, 
                        "Nettó egységár:": [None] * hianyzo_sorok
                    })
                    excel_df = pd.concat([excel_df, potlas], ignore_index=True)
                
                st.session_state.df_items = excel_df
                st.session_state.ido_kod = datetime.now().strftime("%f")[:3]
                st.rerun()
                
            except ValueError:
                st.error("❌ Hiba! Nem találtam 'Ajánlati árak' nevű fület az Excelben. Ellenőrizd a fájlt!")
            except Exception as e:
                st.error(f"❌ Váratlan hiba történt: {e}")

st.info("💡 Töltsd ki az üres sorokat (vagy töltsd be az Excelt)! A nem használt sorok automatikusan törlődnek a PDF-ből.")

edited_df = st.data_editor(st.session_state.df_items, num_rows="dynamic", use_container_width=True)

st.divider()


# --- 3. FELTÉTELEK 4 BOXBAN ---
st.subheader("Szerződéses Feltételek")

col1, col2 = st.columns(2)
with col1:
    ervenyesseg_szoveg = st.text_area("Ajánlat érvényessége:", key="ervenyesseg_szoveg", height=150)
    fizetes_szoveg = st.text_area("Fizetési feltételek:", key="fizetes_szoveg", height=250)
with col2:
    garancia_szoveg = st.text_area("Garanciális feltételek:", key="garancia_szoveg", height=150)
    utemezes_szoveg = st.text_area("Ütemezés:", key="utemezes_szoveg", height=250)

st.divider()


# --- 4. GENERÁLÁS, MATEMATIKA ÉS MENTÉS ---
if st.button("📄 PDF Árajánlat Generálása", type="primary", use_container_width=True):
    with st.spinner('Számítás és mentés folyamatban...'):
        
        uj_ido_kod = datetime.now().strftime("%f")[:3]
        vegleges_azonosito = general_azonosito(ugyfel_nev, ugyfel_cim, uj_ido_kod)
        
        kalkulalt_df = edited_df.copy()
        kalkulalt_df['Mennyiség:'] = pd.to_numeric(kalkulalt_df['Mennyiség:'], errors='coerce').fillna(0)
        kalkulalt_df['Nettó egységár:'] = pd.to_numeric(kalkulalt_df['Nettó egységár:'], errors='coerce').fillna(0)
        
        szamolo_df = kalkulalt_df[(kalkulalt_df['Nettó egységár:'] > 0) & (kalkulalt_df['Mennyiség:'] > 0)].copy()
        szamolo_df['Nettó ár:'] = szamolo_df['Mennyiség:'] * szamolo_df['Nettó egységár:']
        szamolo_df['ÁFA (27%):'] = szamolo_df['Nettó ár:'] * 0.27
        szamolo_df['Bruttó ár:'] = szamolo_df['Nettó ár:'] + szamolo_df['ÁFA (27%):']

        netto_osszesen = szamolo_df['Nettó ár:'].sum()
        afa_osszesen = szamolo_df['ÁFA (27%):'].sum()
        brutto_osszesen = szamolo_df['Bruttó ár:'].sum()
        
        ugyfel_adatok_dict = {
            'Ügylet azonosító:': vegleges_azonosito,
            'Ajánlat tárgya:': ajanlat_targya,
            'neve:': ugyfel_nev,
            'címe:': ugyfel_cim,
            'adószáma:': ugyfel_adoszam,
            'tel./fax:': ugyfel_tel,
            'e-mail:': ugyfel_email
        }
        
        tetelek_lista = szamolo_df.to_dict(orient='records')
        oszlopok_listaja = ["Kiadási tétel megnevezése:", "Mennyiség:", "Nettó egységár:", "Nettó ár:", "ÁFA (27%):", "Bruttó ár:"]
        
        feltetelek_dict = {
            'ervenyesseg': [sor.strip() for sor in ervenyesseg_szoveg.split('\n') if sor.strip()],
            'fizetes': [sor.strip() for sor in fizetes_szoveg.split('\n') if sor.strip()],
            'utemezes': [sor.strip() for sor in utemezes_szoveg.split('\n') if sor.strip()],
            'garancia': [sor.strip() for sor in garancia_szoveg.split('\n') if sor.strip()]
        }
        
        env = Environment(loader=FileSystemLoader(os.path.dirname(os.path.abspath(__file__))))
        template = env.get_template('ajanlat_sablon.html')
        
        html_kimenet = template.render(
            ugyfel=ugyfel_adatok_dict, ceg=ceg_adatok, feltetelek=feltetelek_dict,
            datum=datetime.now().strftime("%Y. %m. %d."),
            oszlopok=oszlopok_listaja, tetelek=tetelek_lista,
            netto_osszesen=netto_osszesen, afa_osszesen=afa_osszesen, brutto_osszesen=brutto_osszesen
        )
        
        tisztitott_nev = str(ugyfel_nev).replace(' ', '_') if ugyfel_nev else "Ugyfel"
        tisztitott_azonosito = str(vegleges_azonosito).replace(' ', '_').replace('/', '-')
        
        pdf_fajlnev = f"Ajanlat_{tisztitott_nev}_{tisztitott_azonosito}_{datetime.now().strftime('%Y%m%d')}.pdf"
        json_fajlnev = f"{tisztitott_azonosito}.json"
        
        teljes_pdf_utvonal = os.path.join(mentesi_mappa, pdf_fajlnev)
        HTML(string=html_kimenet, base_url=os.path.dirname(os.path.abspath(__file__))).write_pdf(teljes_pdf_utvonal)
        
        mentes_adatok = {
            'ugyfel_nev': ugyfel_nev,
            'ugyfel_cim': ugyfel_cim,
            'ajanlat_targya': ajanlat_targya,
            'ugyfel_adoszam': ugyfel_adoszam,
            'ugyfel_tel': ugyfel_tel,
            'ugyfel_email': ugyfel_email,
            'df_items': tetelek_lista,
            'ervenyesseg_szoveg': ervenyesseg_szoveg,
            'fizetes_szoveg': fizetes_szoveg,
            'utemezes_szoveg': utemezes_szoveg,
            'garancia_szoveg': garancia_szoveg
        }
        
        teljes_json_utvonal = os.path.join(mentesi_mappa, json_fajlnev)
        with open(teljes_json_utvonal, 'w', encoding='utf-8') as f:
            json.dump(mentes_adatok, f, ensure_ascii=False, indent=4)
        
        with open(teljes_pdf_utvonal, "rb") as f:
            pdf_bytes = f.read()
            
        with open(teljes_json_utvonal, "rb") as f:
            json_bytes = f.read()
        
        st.session_state.pdf_kesz = pdf_bytes
        st.session_state.json_kesz = json_bytes
        st.session_state.pdf_nev = pdf_fajlnev
        st.session_state.json_nev = json_fajlnev
        st.session_state.vegszamolas = (netto_osszesen, afa_osszesen, brutto_osszesen)
        st.session_state.vegleges_id = vegleges_azonosito


# --- 5. EREDMÉNYEK ÉS LETÖLTÉS MEGJELENÍTÉSE ---
if 'pdf_kesz' in st.session_state:
    st.success(f"🎉 Elkészült! Azonosító: **{st.session_state.vegleges_id}**")
    
    netto, afa, brutto = st.session_state.vegszamolas
    col1, col2, col3 = st.columns(3)
    col1.metric(label="Nettó összesen", value=f"{netto:,.0f} Ft".replace(',', ' '))
    col2.metric(label="ÁFA összesen", value=f"{afa:,.0f} Ft".replace(',', ' '))
    col3.metric(label="Bruttó összesen", value=f"{brutto:,.0f} Ft".replace(',', ' '))
    
    st.markdown("### Letöltések")
    dl_col1, dl_col2 = st.columns(2)
    with dl_col1:
        st.download_button(
            label="📄 Ajánlat letöltése (.pdf)", 
            data=st.session_state.pdf_kesz, 
            file_name=st.session_state.pdf_nev, 
            mime="application/pdf",
            use_container_width=True
        )
    with dl_col2:
        st.download_button(
            label="💾 Scenárió mentése gépre (.json)", 
            data=st.session_state.json_kesz, 
            file_name=st.session_state.json_nev, 
            mime="application/json",
            use_container_width=True
        )
